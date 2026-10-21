import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent))

from app import main
from app.schemas import CopyRunRequest, RevisionRequest


def response(content: dict) -> object:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": json.dumps(content)}}]}

    return Response()


class FakeClient:
    responses: list[object] = []
    requests: list[dict] = []

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, _url: str, **kwargs) -> object:
        self.requests.append(kwargs["json"])
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FailingResponse:
    def raise_for_status(self) -> None:
        raise RuntimeError("repair transport failed")

    def json(self) -> dict:
        return {}


def run_payload(**overrides) -> CopyRunRequest:
    values = {
        "task_id": "task-1",
        "campaign_id": "campaign-1",
        "company_id": "company-1",
        "prompt": "Write public relations copy.",
        "variants": 1,
    }
    values.update(overrides)
    return CopyRunRequest(**values)


def revision_payload(**overrides) -> RevisionRequest:
    values = {
        "task_id": "task-1",
        "campaign_id": "campaign-1",
        "company_id": "company-1",
        "prompt": "Write public relations copy.",
        "reject_reason": "Needs a stronger lead.",
        "variants": 1,
    }
    values.update(overrides)
    return RevisionRequest(**values)


def test_copy_requests_default_to_the_backward_compatible_range():
    assert run_payload().body_min_length == 80
    assert run_payload().body_max_length == 200
    assert revision_payload().body_min_length == 80
    assert revision_payload().body_max_length == 200


@pytest.mark.parametrize(
    "overrides",
    [{"body_min_length": -1}, {"body_max_length": -1}, {"body_min_length": 201, "body_max_length": 200}],
)
def test_copy_requests_reject_invalid_ranges(overrides):
    with pytest.raises(ValidationError):
        run_payload(**overrides)

    with pytest.raises(ValidationError):
        revision_payload(**overrides)


def test_normal_generation_uses_dynamic_range_and_accepts_unicode_character_count(monkeypatch):
    body = "公關稿" * 100
    FakeClient.responses = [response({"title": "Launch", "body": body, "cta": "Read more"})]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.run_copy_worker(run_payload(body_min_length=300, body_max_length=500))

    content = FakeClient.requests[0]["messages"][0]["content"]
    assert '"body" 300-500 chars' in content
    assert '"body" 80-200 chars' not in content
    assert len(result.variants[0].body) == 300


def test_invalid_normal_output_gets_exactly_one_bounded_repair(monkeypatch):
    FakeClient.responses = [
        response({"title": "Launch", "body": "too short", "cta": "Read"}),
        response({"title": "Launch", "body": "A" * 300, "cta": "Read"}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.run_copy_worker(run_payload(body_min_length=300, body_max_length=500))

    assert len(FakeClient.requests) == 2
    repair = FakeClient.requests[1]["messages"][0]["content"]
    assert "300-500" in repair
    assert '"title"' in repair and '"body"' in repair and '"cta"' in repair
    assert result.variants[0].body == "A" * 300


def test_invalid_normal_output_gets_at_most_two_repairs(monkeypatch):
    FakeClient.responses = [
        response({"title": "Launch", "body": "A" * 600, "cta": "Read"}),
        response({"title": "Launch", "body": "B" * 700, "cta": "Read"}),
        response({"title": "Launch", "body": "C" * 300, "cta": "Read"}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.run_copy_worker(run_payload(body_min_length=300, body_max_length=500))

    assert len(FakeClient.requests) == 3
    first_repair = FakeClient.requests[1]["messages"][0]["content"]
    second_repair = FakeClient.requests[2]["messages"][0]["content"]
    assert "current body length: 600" in first_repair
    assert "current body length: 700" in second_repair
    assert "300-500" in first_repair
    assert "300-500" in second_repair
    assert result.variants[0].body == "C" * 300


def test_invalid_repair_returns_502_after_two_repairs(monkeypatch):
    FakeClient.responses = [
        response({"title": "Launch", "body": "short", "cta": "Read"}),
        response({"title": "Launch", "body": "still short", "cta": "Read"}),
        response({"title": "Launch", "body": "still too short", "cta": "Read"}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    with pytest.raises(HTTPException) as exc_info:
        main.run_copy_worker(run_payload(body_min_length=300, body_max_length=500))

    assert exc_info.value.status_code == 502
    assert "body length" in exc_info.value.detail.lower()
    assert len(FakeClient.requests) == 3


def test_repair_transport_failure_makes_exactly_one_repair_request(monkeypatch):
    FakeClient.responses = [
        response({"title": "Launch", "body": "short", "cta": "Read"}),
        FailingResponse(),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    with pytest.raises(HTTPException) as exc_info:
        main.run_copy_worker(run_payload(body_min_length=300, body_max_length=500))

    assert exc_info.value.status_code == 502
    assert len(FakeClient.requests) == 2


def test_stub_preserves_useful_body_for_ordinary_range(monkeypatch):
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "")

    result = main.run_copy_worker(run_payload(body_min_length=80, body_max_length=200))

    assert 80 <= len(result.variants[0].body) <= 200
    assert "Premium campaign copy variant" in result.variants[0].body


def test_stub_rejects_impossible_non_empty_zero_length_contract(monkeypatch):
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "")

    with pytest.raises(HTTPException) as exc_info:
        main.run_copy_worker(run_payload(body_min_length=0, body_max_length=0))

    assert exc_info.value.status_code == 502
    assert "non-empty" in exc_info.value.detail.lower()


@pytest.mark.parametrize("minimum, maximum", [(0, 100), (80, 200), (300, 500)])
def test_parse_copy_variant_rejects_empty_body_for_every_contract(minimum, maximum):
    with pytest.raises(ValueError, match="body length"):
        main._parse_copy_variant(
            json.dumps({"title": "Valid", "body": "", "cta": "Read"}),
            minimum,
            maximum,
        )


@pytest.mark.parametrize("invalid_field", ["title", "cta"])
def test_title_and_cta_limits_are_validated_and_repaired(monkeypatch, invalid_field):
    invalid = {"title": "Valid", "body": "A" * 80, "cta": "Read"}
    invalid[invalid_field] = "X" * (31 if invalid_field == "title" else 16)
    FakeClient.responses = [response(invalid), response({"title": "Valid", "body": "B" * 80, "cta": "Read"})]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.run_copy_worker(run_payload())

    assert result.variants[0].title == "Valid"
    assert result.variants[0].cta == "Read"
    assert len(FakeClient.requests) == 2


def test_regeneration_uses_the_same_dynamic_validation_and_repair(monkeypatch):
    FakeClient.responses = [
        response({"title": "Revision", "body": "short", "cta": "Read"}),
        response({"title": "Revision", "body": "B" * 300, "cta": "Read"}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.regenerate_copy(revision_payload(body_min_length=300, body_max_length=500))

    assert len(FakeClient.requests) == 2
    initial = FakeClient.requests[0]["messages"][0]["content"]
    repair = FakeClient.requests[1]["messages"][0]["content"]
    assert '"body" 300-500 chars' in initial
    assert '"body" 300-500 chars' in repair
    assert result.variants[0].body == "B" * 300
