import hashlib
import json
import zipfile
from pathlib import Path

from import_inews_references import (
    FakeResponse,
    Importer,
    auth_headers_from_environment,
    extract_docx_text,
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


def write_docx(path, paragraphs):
    document = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
    )
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{document}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


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
    write_docx(source, ["First paragraph", "Second paragraph"])
    original = source.read_bytes()
    transport = FakeTransport(
        responses=[
            FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
            FakeResponse(200, {"items": []}),
            FakeResponse(200, {"item_id": "item-1", "title": "brief", "metadata": {"sha256": "not-used"}}),
            FakeResponse(200, {"items": [{"item_id": "item-1", "title": "brief", "text_embedding": {"embedding_status": "ready"}}]}),
        ]
    )
    report = tmp_path / "report.json"

    result = Importer("http://example.test", transport).run(tmp_path, report)

    upload = next(request for request in transport.requests if "/items/upload" in request[1])
    body = upload[3]
    assert b'filename="brief.txt"' in body
    assert b"source: inews_word" in body
    assert b"reference_type: news_release_style" in body
    assert b"usage: style_and_structure_only" in body
    assert b"original_filename: brief.docx" in body
    assert b"First paragraph\nSecond paragraph" in body
    assert result[0]["item_id"] == "item-1"
    assert result[0]["ready_status"] == "ready"
    assert json.loads(report.read_text(encoding="utf-8"))[0]["filename"] == "brief.docx"
    assert source.read_bytes() == original
    assert list(tmp_path.rglob("*.txt")) == []


def test_docx_open_xml_paragraph_extraction_is_utf8_text(tmp_path):
    source = tmp_path / "release.docx"
    write_docx(source, ["中文標題", "Body text"])

    assert extract_docx_text(source) == "中文標題\nBody text"


def test_existing_title_and_provenance_skip_upload(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    transport = FakeTransport(
        responses=[
            FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
            FakeResponse(200, {"items": [{"item_id": "existing", "title": "brief", "metadata": {"sha256": "different"}}]}),
            FakeResponse(200, {"item_id": "new-item", "title": "brief"}),
            FakeResponse(200, {"items": [{"item_id": "new-item", "title": "brief", "text_embedding": {"embedding_status": "ready"}}]}),
        ]
    )

    result = Importer("http://example.test", transport).run(tmp_path, tmp_path / "report.json")

    assert result[0]["item_id"] == "new-item"
    assert result[0]["upload_status"] == "uploaded"
    assert any("/items/upload" in request[1] for request in transport.requests)


def test_matching_hash_skips_same_title_item(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    from import_inews_references import scan_unique_docx
    digest = scan_unique_docx(tmp_path)[0].sha256
    transport = FakeTransport(responses=[
        FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
        FakeResponse(200, {"items": [{"item_id": "existing", "title": "brief", "file_name": "brief.txt", "provenance_sha256": digest, "provenance_source": "inews_word"}]}),
    ])

    result = Importer("http://example.test", transport).run(tmp_path, tmp_path / "report.json")

    assert result[0]["upload_status"] == "skipped-existing"
    assert result[0]["item_id"] == "existing"
    assert not any("/items/upload" in request[1] for request in transport.requests)


def test_matching_hash_with_different_provenance_source_uploads(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    from import_inews_references import scan_unique_docx
    digest = scan_unique_docx(tmp_path)[0].sha256
    transport = FakeTransport(responses=[
        FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
        FakeResponse(200, {"items": [{"item_id": "existing", "title": "brief", "provenance_sha256": digest, "provenance_source": "other_source"}]}),
        FakeResponse(200, {"item_id": "new-item", "title": "brief"}),
        FakeResponse(200, {"items": [{"item_id": "new-item", "embedding_status": "ready"}]}),
    ])

    result = Importer("http://example.test", transport, poll_interval_seconds=0).run(tmp_path, tmp_path / "report.json")

    assert result[0]["upload_status"] == "uploaded"
    assert result[0]["item_id"] == "new-item"
    assert any("/items/upload" in request[1] for request in transport.requests)


def test_auth_headers_use_environment_without_exposing_credentials(monkeypatch):
    monkeypatch.setenv("INEWS_IMPORT_BEARER_TOKEN", "fake-bearer")
    monkeypatch.delenv("PLATFORM_ADMIN_KEY", raising=False)

    headers = auth_headers_from_environment()

    assert headers == {"Authorization": "Bearer fake-bearer"}
    assert "fake-bearer" not in repr(auth_headers_from_environment(redact=True))


def test_authenticated_transport_receives_bearer_header(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    transport = FakeTransport(responses=[
        FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
        FakeResponse(200, {"items": []}),
        FakeResponse(200, {"item_id": "item-1", "title": "brief"}),
        FakeResponse(200, {"items": [{"item_id": "item-1", "text_embedding": {"embedding_status": "ready"}}]}),
    ])

    Importer("http://example.test", transport, headers={"Authorization": "Bearer fake-bearer"}).run(
        tmp_path, tmp_path / "report.json"
    )

    assert all(request[2]["Authorization"] == "Bearer fake-bearer" for request in transport.requests)


def test_readiness_polls_pending_until_ready(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    transport = FakeTransport(responses=[
        FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
        FakeResponse(200, {"items": []}),
        FakeResponse(200, {"item_id": "item-1", "title": "brief"}),
        FakeResponse(200, {"items": [{"item_id": "item-1", "text_embedding": {"embedding_status": "pending"}}]}),
        FakeResponse(200, {"items": [{"item_id": "item-1", "text_embedding": {"embedding_status": "ready"}}]}),
    ])

    result = Importer("http://example.test", transport, poll_interval_seconds=0, readiness_timeout_seconds=1).run(
        tmp_path, tmp_path / "report.json"
    )

    assert result[0]["ready_status"] == "ready"
    assert len([request for request in transport.requests if request[1].endswith("/items")]) == 3


def test_readiness_records_failed_status(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    transport = FakeTransport(responses=[
        FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
        FakeResponse(200, {"items": []}),
        FakeResponse(200, {"item_id": "item-1", "title": "brief"}),
        FakeResponse(200, {"items": [{"item_id": "item-1", "text_embedding": {"embedding_status": "failed"}}]}),
    ])

    result = Importer("http://example.test", transport, poll_interval_seconds=0).run(tmp_path, tmp_path / "report.json")

    assert result[0]["ready_status"] == "failed"


def test_readiness_uses_text_embedding_status(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    transport = FakeTransport(responses=[
        FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
        FakeResponse(200, {"items": []}),
        FakeResponse(200, {"item_id": "item-1", "title": "brief"}),
        FakeResponse(200, {"items": [{"item_id": "item-1", "embedding_status": "pending", "chunk_count": 2, "ready_chunk_count": 0}]}),
        FakeResponse(200, {"items": [{"item_id": "item-1", "embedding_status": "ready", "chunk_count": 2, "ready_chunk_count": 2}]}),
    ])

    result = Importer("http://example.test", transport, poll_interval_seconds=0, readiness_timeout_seconds=1).run(
        tmp_path, tmp_path / "report.json"
    )

    assert result[0]["ready_status"] == "ready"


def test_readiness_records_bounded_timeout(tmp_path):
    source = tmp_path / "brief.docx"
    write_docx(source, ["Article"])
    transport = FakeTransport(responses=[
        FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
        FakeResponse(200, {"items": []}),
        FakeResponse(200, {"item_id": "item-1", "title": "brief"}),
        FakeResponse(200, {"items": [{"item_id": "item-1", "text_embedding": {"embedding_status": "pending"}}]}),
    ])

    result = Importer("http://example.test", transport, poll_interval_seconds=0, readiness_timeout_seconds=0).run(
        tmp_path, tmp_path / "report.json"
    )

    assert result[0]["ready_status"] == "timeout"


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
    write_docx(source, ["article"])
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


def test_malformed_docx_isolated_from_other_file_conversion(tmp_path):
    malformed = tmp_path / "bad.docx"
    valid = tmp_path / "good.docx"
    malformed.write_bytes(b"not a zip document")
    write_docx(valid, ["valid article"])
    transport = FakeTransport(
        responses=[
            FakeResponse(200, {"items": [{"pack_id": "pack-1", "name": "iNews 新聞稿參考資料"}]}),
            FakeResponse(200, {"items": []}),
            FakeResponse(200, {"item_id": "good-item", "title": "good"}),
            FakeResponse(200, {"items": [{"item_id": "good-item", "title": "good", "text_embedding": {"embedding_status": "ready"}}]}),
        ]
    )

    result = Importer("http://example.test", transport).run(tmp_path, tmp_path / "report.json")

    by_filename = {row["filename"]: row for row in result}
    assert by_filename["bad.docx"]["upload_status"] == "failed"
    assert by_filename["good.docx"]["upload_status"] == "uploaded"
    assert by_filename["good.docx"]["item_id"] == "good-item"
    assert len([request for request in transport.requests if "/items/upload" in request[1]]) == 1
