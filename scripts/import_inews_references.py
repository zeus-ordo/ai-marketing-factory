"""Idempotently import iNews Word references through the reference-pack API."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import re
import uuid
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


class UrllibTransport:
    def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: bytes = b"") -> FakeResponse:
        request = Request(url, data=body or None, headers=headers or {}, method=method)
        with urlopen(request, timeout=30) as response:
            payload = response.read()
            return FakeResponse(response.status, json.loads(payload or b"{}"))


def _multipart(fields: dict[str, str], file_path: Path) -> tuple[dict[str, str], bytes]:
    boundary = f"----inews-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        file_path.read_bytes(),
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
    def __init__(self, api_base_url: str, transport: Any):
        self.base_url = api_base_url.rstrip("/")
        self.transport = transport

    def _request(self, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> dict[str, Any]:
        response = self.transport.request(method, self.base_url + path, headers, body)
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
            for row in report:
                row["upload_status"] = "failed"
                row["error"] = _safe_error(exc)
            _write_report(report_path, report)
            return report

        by_hash = {str(item.get("metadata", {}).get("sha256")): item for item in existing if isinstance(item.get("metadata"), dict) and item.get("metadata", {}).get("sha256")}
        for index, source in enumerate(files):
            row = report[index]
            if source.sha256 in by_hash:
                row.update(item_id=by_hash[source.sha256].get("item_id"), upload_status="skipped-existing")
                continue
            try:
                headers, body = _multipart({"title": source.title, **METADATA}, source.path)
                item = self._request("POST", f"/api/v1/reference-packs/{pack_id}/items/upload", body, headers)
                row.update(item_id=item.get("item_id"), upload_status="uploaded")
            except Exception as exc:
                row.update(upload_status="failed", error=_safe_error(exc))

        try:
            current = self._request("GET", f"/api/v1/reference-packs/{pack_id}/items").get("items", [])
            for row in report:
                item = next((candidate for candidate in current if candidate.get("item_id") == row["item_id"]), None)
                analysis = (item or {}).get("analysis") or (item or {}).get("metadata", {})
                row["ready_status"] = analysis.get("analysis_status") if isinstance(analysis, dict) else None
        except Exception as exc:
            for row in report:
                if row["upload_status"] != "failed":
                    row["ready_status"] = "poll-failed"
                    row["error"] = _safe_error(exc)
        _write_report(report_path, report)
        return report


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
    args = parser.parse_args(argv)
    Importer(args.api_base_url, UrllibTransport()).run(args.source_dir, args.report, args.pack_name, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
