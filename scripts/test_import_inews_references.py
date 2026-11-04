import hashlib
import json
from pathlib import Path

import pytest

from import_inews_references import (
    FakeResponse,
    Importer,
    scan_unique_docx,
)


class FakeTransport:
    def __init__(self, responses=None, error_on=None):
        self.responses = list(responses or [])
        self.error_on = error_on
        self.requests = []

    def request(self, method, url, headers=None, body=b""):
        self.requests.append((method, url, headers or {}, body))
        if self.error_on and url.endswith(self.error_on):
            raise RuntimeError("token=secret-token local=C:\\private\\news.docx")
        if not self.responses:
            raise AssertionError("unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_scan_recurses_docx_deduplicates_sha_and_derives_title(tmp_path):
    first = tmp_path / "nested" / "release.docx"
    duplicate = tmp_path / "copy.docx"
    ignored = tmp_path / "notes.txt"
    first.parent.mkdir()
    first.write_bytes(b"same article")
    duplicate.write_bytes(b"same article")
    ignored.write_bytes(b"ignore")

    files = scan_unique_docx(tmp_path)

    assert len(files) == 1
    assert files[0].title in {"release", "copy"}
    assert files[0].sha256 == hashlib.sha256(b"same article").hexdigest()
    assert files[0].path.suffix == ".docx"


def test_import_sends_required_metadata_and_reports_ready_item(tmp_path):
    source = tmp_path / "brief.docx"
    source.write_bytes(b"article")
    transport = FakeTransport(
        responses=[
            FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
            FakeResponse(200, {"items": []}),
            FakeResponse(200, {"item_id": "item-1", "title": "brief", "metadata": {"sha256": "not-used"}}),
            FakeResponse(200, {"items": [{"item_id": "item-1", "title": "brief", "metadata": {"sha256": "", "analysis_status": "ready"}, "analysis": {"analysis_status": "ready"}}]}),
        ]
    )
    report = tmp_path / "report.json"

    result = Importer("http://example.test", transport).run(tmp_path, report)

    upload = next(request for request in transport.requests if "/items/upload" in request[1])
    body = upload[3]
    assert b'name="source"' in body and b"inews_word" in body
    assert b'name="reference_type"' in body and b"news_release_style" in body
    assert b'name="usage"' in body and b"style_and_structure_only" in body
    assert result[0]["item_id"] == "item-1"
    assert result[0]["ready_status"] == "ready"
    assert json.loads(report.read_text(encoding="utf-8"))[0]["filename"] == "brief.docx"


def test_dry_run_makes_no_requests_and_writes_safe_report(tmp_path):
    source = tmp_path / "secret.docx"
    source.write_bytes(b"article")
    transport = FakeTransport()
    report = tmp_path / "report.json"

    result = Importer("https://api.example.test", transport).run(tmp_path, report, dry_run=True)

    assert transport.requests == []
    assert result[0]["upload_status"] == "dry-run"
    assert str(tmp_path) not in report.read_text(encoding="utf-8")


def test_http_failure_is_per_file_and_sanitized(tmp_path):
    source = tmp_path / "private.docx"
    source.write_bytes(b"article")
    transport = FakeTransport(
        responses=[
            FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
            FakeResponse(200, {"items": []}),
        ],
        error_on="/items/upload",
    )

    result = Importer("https://api.example.test", transport).run(tmp_path, tmp_path / "report.json")

    assert result[0]["upload_status"] == "failed"
    assert "secret-token" not in result[0]["error"]
    assert str(tmp_path) not in result[0]["error"]
    assert result[0]["filename"] == "private.docx"
