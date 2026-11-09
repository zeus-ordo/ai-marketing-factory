"""Idempotently import iNews Word references through the reference-pack API.

Authenticated runs use ``INEWS_IMPORT_BEARER_TOKEN`` or ``PLATFORM_ADMIN_KEY``
from the process environment. The CLI accepts alternate environment variable
names with ``--bearer-token-env`` and ``--admin-key-env``; it never accepts
credential values as arguments or prints them. ``--dry-run`` makes no request
and does not require credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_PACK_NAME = "iNews 新聞稿參考資料"
METADATA = {
    "source": "inews_word",
    "reference_type": "news_release_style",
    "usage": "style_and_structure_only",
}


@dataclass(frozen=True)
class SourceFile:
    path: Path
    title: str
    sha256: str


@dataclass
class FakeResponse:
    status: int
    data: dict[str, Any]

    def json(self) -> dict[str, Any]:
        return self.data


def scan_unique_docx(source_dir: Path) -> list[SourceFile]:
    seen: set[str] = set()
    files: list[SourceFile] = []
    for path in sorted(source_dir.rglob("*.docx")):
        if not path.is_file():
            continue
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        files.append(SourceFile(path=path, title=path.stem, sha256=digest))
    return files


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        document = archive.read("word/document.xml")
    root = ET.fromstring(document)
    paragraphs: list[str] = []
    paragraph_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
    text_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
    tab_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tab"
    for paragraph in root.iter(paragraph_tag):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == text_tag:
                parts.append(node.text or "")
            elif node.tag == tab_tag:
                parts.append("\t")
        if parts:
            paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def build_txt_payload(source: SourceFile) -> bytes:
    headers = [
        f"source: {METADATA['source']}",
        f"reference_type: {METADATA['reference_type']}",
        f"usage: {METADATA['usage']}",
        f"original_filename: {source.path.name}",
        f"sha256: {source.sha256}",
    ]
    return ("\n".join(headers) + "\n\n" + extract_docx_text(source.path) + "\n").encode("utf-8")


class UrllibTransport:
    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes = b"") -> FakeResponse:
        request = Request(url, data=body or None, headers=headers or {}, method=method)
        with urlopen(request, timeout=30) as response:
            payload = response.read()
            return FakeResponse(response.status, json.loads(payload or b"{}"))


def auth_headers_from_environment(
    environ: dict[str, str] | None = None,
    bearer_env: str = "INEWS_IMPORT_BEARER_TOKEN",
    admin_key_env: str = "PLATFORM_ADMIN_KEY",
    redact: bool = False,
) -> dict[str, str]:
    values = environ if environ is not None else os.environ
    bearer = values.get(bearer_env, "")
    admin_key = values.get(admin_key_env, "")
    if bearer:
        return {"Authorization": "Bearer [REDACTED]" if redact else f"Bearer {bearer}"}
    if admin_key:
        return {"x-platform-key": "[REDACTED]" if redact else admin_key}
    return {}


def _multipart(fields: dict[str, str], filename: str, content: bytes) -> tuple[dict[str, str], bytes]:
    boundary = f"----inews-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n",
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return {"Content-Type": f"multipart/form-data; boundary={boundary}"}, b"".join(chunks)


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"(?:token|key|secret)=[^\s]+", "[redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://[^\s]+", "[redacted-url]", text, flags=re.IGNORECASE)
    text = re.sub(r"[A-Za-z]:[/\\][^\s]+|/(?:[^/\s]+/)+[^/\s]+", "[redacted-path]", text)
    return text[:300]


class Importer:
    def __init__(
        self,
        api_base_url: str,
        transport: Any,
        headers: dict[str, str] | None = None,
        poll_interval_seconds: float = 5,
        readiness_timeout_seconds: float = 300,
        sleep_fn: Any = time.sleep,
        monotonic_fn: Any = time.monotonic,
    ):
        self.base_url = api_base_url.rstrip("/")
        self.transport = transport
        self.headers = headers or {}
        self.poll_interval_seconds = max(0, poll_interval_seconds)
        self.readiness_timeout_seconds = max(0, readiness_timeout_seconds)
        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn

    def _request(self, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> dict[str, Any]:
        request_headers = {**self.headers, **(headers or {})}
        response = self.transport.request(method, self.base_url + path, request_headers, body)
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}")
        return response.json()

    def run(self, source_dir: Path, report_path: Path, pack_name: str = DEFAULT_PACK_NAME, dry_run: bool = False) -> list[dict[str, Any]]:
        files = scan_unique_docx(source_dir)
        report: list[dict[str, Any]] = [
            {"filename": item.path.name, "sha256": item.sha256, "item_id": None, "upload_status": "dry-run" if dry_run else "pending", "ready_status": None, "metadata": METADATA.copy()}
            for item in files
        ]
        if dry_run:
            _write_report(report_path, report)
            return report

        packs = self._request("GET", "/api/v1/reference-packs").get("items", [])
        pack = next((item for item in packs if item.get("name") == pack_name and item.get("scope", "platform") == "platform"), None)
        if pack is None:
            pack = self._request("POST", "/api/v1/reference-packs", json.dumps({"name": pack_name, "role": "style", "selection_mode": "optional", "max_images": 1, "is_active": True}).encode(), {"Content-Type": "application/json"})
        pack_id = str(pack.get("pack_id") or pack.get("id"))
        try:
            existing = self._request("GET", f"/api/v1/reference-packs/{pack_id}/items").get("items", [])
        except Exception as exc:
            existing = []
            for row in report:
                row["metadata_warning"] = _safe_error(exc)

        by_hash = {
            str(item.get("provenance_sha256")): item
            for item in existing
            if item.get("provenance_sha256")
            and item.get("provenance_source") == METADATA["source"]
        }
        for index, source in enumerate(files):
            row = report[index]
            if source.sha256 in by_hash:
                row.update(item_id=by_hash[source.sha256].get("item_id"), upload_status="skipped-existing")
                continue
            try:
                match = next((item for item in existing if _matches_existing(item, source)), None)
                if match is not None:
                    row.update(item_id=match.get("item_id"), upload_status="skipped-existing")
                    continue
                headers, body = _multipart({"title": source.title}, f"{source.title}.txt", build_txt_payload(source))
                item = self._request("POST", f"/api/v1/reference-packs/{pack_id}/items/upload", body, headers)
                row.update(item_id=item.get("item_id"), upload_status="uploaded")
            except Exception as exc:
                row.update(upload_status="failed", error=_safe_error(exc))

        self._poll_readiness(pack_id, report)
        _write_report(report_path, report)
        return report

    def _poll_readiness(self, pack_id: str, report: list[dict[str, Any]]) -> None:
        pending_ids = {row["item_id"] for row in report if row["upload_status"] == "uploaded" and row["item_id"]}
        if not pending_ids:
            return
        deadline = self.monotonic_fn() + self.readiness_timeout_seconds
        while pending_ids:
            try:
                current = self._request("GET", f"/api/v1/reference-packs/{pack_id}/items").get("items", [])
            except Exception as exc:
                for row in report:
                    if row.get("item_id") in pending_ids:
                        row["ready_status"] = "poll-failed"
                        row["error"] = _safe_error(exc)
                return
            for row in report:
                if row.get("item_id") not in pending_ids:
                    continue
                item = next((candidate for candidate in current if candidate.get("item_id") == row["item_id"]), None)
                embedding = (item or {}).get("text_embedding") or (item or {}).get("metadata", {})
                status = embedding.get("embedding_status") if isinstance(embedding, dict) else None
                status = status or (item or {}).get("embedding_status")
                if status in {"ready", "failed"}:
                    row["ready_status"] = status
                    pending_ids.remove(row["item_id"])
            if not pending_ids:
                return
            if self.monotonic_fn() >= deadline:
                for row in report:
                    if row.get("item_id") in pending_ids:
                        row["ready_status"] = "timeout"
                return
            self.sleep_fn(self.poll_interval_seconds)


def _matches_existing(item: dict[str, Any], source: SourceFile) -> bool:
    if str(item.get("title") or "") != source.title:
        return False
    provenance_source = str(item.get("provenance_source") or "")
    provenance_sha256 = str(item.get("provenance_sha256") or "")
    return provenance_source == METADATA["source"] and provenance_sha256 == source.sha256


def _write_report(path: Path, report: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--pack-name", default=DEFAULT_PACK_NAME)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--bearer-token-env", default="INEWS_IMPORT_BEARER_TOKEN", help="Environment variable containing the bearer token")
    parser.add_argument("--admin-key-env", default="PLATFORM_ADMIN_KEY", help="Environment variable containing the platform admin key")
    parser.add_argument("--poll-interval-seconds", type=float, default=5)
    parser.add_argument("--readiness-timeout-seconds", type=float, default=300)
    args = parser.parse_args(argv)
    headers = {} if args.dry_run else auth_headers_from_environment(bearer_env=args.bearer_token_env, admin_key_env=args.admin_key_env)
    if not args.dry_run and not headers:
        parser.error("set a bearer token or platform admin key environment variable")
    Importer(
        args.api_base_url,
        UrllibTransport(),
        headers=headers,
        poll_interval_seconds=args.poll_interval_seconds,
        readiness_timeout_seconds=args.readiness_timeout_seconds,
    ).run(args.source_dir, args.report, args.pack_name, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
