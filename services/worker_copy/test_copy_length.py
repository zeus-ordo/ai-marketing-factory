import json
import re
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


def sectioned_news_response(section_length: int = 220) -> object:
    sections = {
        name: name[0].upper() * section_length
        for name in ("lead", "details", "background", "significance", "closing")
    }
    return response({"title": "Launch", "cta": "Read", **sections})


def sectioned_news_content(section_length: int = 220, title: str = "Launch") -> dict:
    return {
        "title": title,
        "cta": "Read",
        **{
            name: name[0].upper() * section_length
            for name in ("lead", "details", "background", "significance", "closing")
        },
    }


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


@pytest.mark.parametrize("body_length", [1000, 1400])
def test_news_release_boundaries_are_accepted(body_length):
    parsed = main._parse_copy_variant(
        json.dumps({"title": "Launch", "body": "A" * body_length, "cta": "Read more"}),
        1000,
        1400,
    )

    assert len(parsed["body"]) == body_length


@pytest.mark.parametrize("body_length", [999, 1401])
def test_news_release_values_outside_boundaries_are_rejected(body_length):
    with pytest.raises(ValueError, match="body length"):
        main._parse_copy_variant(
            json.dumps({"title": "Launch", "body": "A" * body_length, "cta": "Read more"}),
            1000,
            1400,
        )


def test_news_release_prompt_contains_required_range(monkeypatch):
    FakeClient.responses = [response({"title": "Launch", "body": "A" * 1000, "cta": "Read"})]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    main.run_copy_worker(run_payload(body_min_length=1000, body_max_length=1400))

    assert '"body" 1000-1400 chars' in FakeClient.requests[0]["messages"][0]["content"]


def test_copy_request_sets_completion_budget_from_body_max_length(monkeypatch):
    FakeClient.responses = [response({"title": "Launch", "body": "A" * 1400, "cta": "Read"})]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    main.run_copy_worker(run_payload(body_min_length=1000, body_max_length=1400))

    assert FakeClient.requests[0]["max_tokens"] >= 1600


@pytest.mark.parametrize(
    ("body_max_length", "expected_budget"),
    [(80, 512), (200, 600), (500, 1500), (1400, 4096), (100_000, 4096)],
)
def test_completion_budget_scales_for_long_form_without_exceeding_bounds(
    body_max_length, expected_budget
):
    assert main._completion_token_budget(body_max_length) == expected_budget


def test_news_sectioned_repair_supports_exact_body_length_contract():
    section_names = ("lead", "details", "background", "significance", "closing")
    _, _, section_ranges = main._news_repair_section_ranges(1000, 1000)
    sections = {
        name: name[0].upper() * section_minimum
        for name, (section_minimum, _) in zip(section_names, section_ranges)
    }

    parsed = main._parse_news_sectioned_variant(
        json.dumps({"title": "Launch", "cta": "Read", **sections}),
        1000,
        1000,
    )

    assert len(parsed["body"]) == 1000


def test_news_sectioned_repair_accepts_short_section_when_combined_body_is_valid():
    sections = {
        "lead": "L" * 120,
        "details": "D" * 230,
        "background": "B" * 230,
        "significance": "S" * 230,
        "closing": "C" * 230,
    }

    parsed = main._parse_news_sectioned_variant(
        json.dumps({"title": "Launch", "cta": "Read", **sections}),
        1000,
        1400,
    )

    assert parsed["body"] == "\n\n".join(sections.values())
    assert 1000 <= len(parsed["body"]) <= 1400


def test_news_sectioned_repair_rejects_nonempty_sections_when_combined_body_is_short():
    sections = {
        name: name[0].upper() * 190
        for name in ("lead", "details", "background", "significance", "closing")
    }

    with pytest.raises(ValueError, match="body length must be between 1000 and 1400 chars"):
        main._parse_news_sectioned_variant(
            json.dumps({"title": "Launch", "cta": "Read", **sections}),
            1000,
            1400,
        )


def test_short_news_release_reaches_range_through_bounded_appendix_requests(monkeypatch):
    initial_body = "Taipei hosted the Green Mobility Forum."
    appendix = "New supplied event details. " + ("Fact. " * 45)
    FakeClient.responses = [
        response({"title": "Forum", "body": initial_body, "cta": "Read"}),
        response({"appendix": appendix, "title": "Forum", "cta": "Read"}),
        response({"appendix": "Final supplied context. " + ("Fact. " * 45)}),
        response({"appendix": "Additional supplied significance. " + ("Fact. " * 45)}),
        response({"appendix": "Closing supplied detail. " + ("Fact. " * 45)}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.run_copy_worker(run_payload(body_min_length=1000, body_max_length=1400))

    assert len(FakeClient.requests) == 5
    assert 1000 <= len(result.variants[0].body) <= 1400
    assert result.variants[0].body.startswith(initial_body + "\n\n")
    assert '"appendix"' in FakeClient.requests[1]["messages"][0]["content"]
    assert "250-350 new characters" in FakeClient.requests[1]["messages"][0]["content"]
    assert "style-only" in FakeClient.requests[1]["messages"][0]["content"]
    assert "do not invent facts" in FakeClient.requests[1]["messages"][0]["content"].lower()


def test_duplicate_news_appendix_does_not_count_as_progress(monkeypatch):
    initial_body = "Initial supplied fact. " * 6
    appendix = "Additional supplied fact. " + ("Fact. " * 45)
    FakeClient.responses = [
        response({"title": "Launch", "body": initial_body, "cta": "Read"}),
        response({"appendix": appendix}),
        response({"appendix": appendix}),
        response({"appendix": "More supplied context. " + ("Fact. " * 45)}),
        response({"appendix": "Further supplied context. " + ("Fact. " * 45)}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.run_copy_worker(run_payload(body_min_length=1000, body_max_length=1400))

    assert len(FakeClient.requests) == 5
    assert result.variants[0].body.count(appendix.strip()) == 1
    assert 1000 <= len(result.variants[0].body) <= 1400


def test_news_appendix_over_maximum_is_trimmed_at_paragraph_boundary(monkeypatch):
    initial_body = "Initial fact. " + ("Fact. " * 150)
    kept = "Kept supplied paragraph. " + ("Fact. " * 12)
    omitted = "Omitted supplied paragraph. " + ("Fact. " * 30)
    FakeClient.responses = [
        response({"title": "Launch", "body": initial_body, "cta": "Read"}),
        response({"appendix": kept + "\n\n" + omitted}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    result = main.run_copy_worker(run_payload(body_min_length=1000, body_max_length=1100))

    body = result.variants[0].body
    assert len(body) <= 1100
    assert len(body) >= 1000
    assert kept.strip() in body
    assert omitted.strip() not in body
    assert body == body.rstrip()


def test_news_continuations_fail_after_four_bounded_requests_without_padding(monkeypatch):
    repeated_appendix = "Repeated supplied fact. " + ("Fact. " * 45)
    FakeClient.responses = [
        response({"title": "Launch", "body": "Short supplied fact.", "cta": "Read"}),
        response({"appendix": repeated_appendix}),
        response({"appendix": repeated_appendix}),
        response({"appendix": repeated_appendix}),
        response({"appendix": repeated_appendix}),
    ]
    FakeClient.requests = []
    monkeypatch.setattr(main, "DEEPSEEK_API_KEY", "real-key")
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    with pytest.raises(HTTPException) as exc_info:
        main.run_copy_worker(run_payload(body_min_length=1000, body_max_length=1400))

    assert exc_info.value.status_code == 502
    assert "body length" in exc_info.value.detail.lower()
    assert len(FakeClient.requests) == 5


def test_news_repair_section_ranges_are_safe_across_valid_boundary_sweep():
    for minimum in range(0, 2001):
        for maximum in (minimum, minimum + 1, minimum + 100, minimum + 400):
            target_minimum, target_maximum, section_ranges = main._news_repair_section_ranges(
                minimum, maximum
            )

            assert minimum <= target_minimum <= target_maximum <= maximum
            assert len(section_ranges) == 5
            assert sum(section_minimum for section_minimum, _ in section_ranges) == max(0, target_minimum - 8)
            assert sum(section_maximum for _, section_maximum in section_ranges) == max(0, target_maximum - 8)
            assert all(
                isinstance(section_minimum, int)
                and isinstance(section_maximum, int)
                and section_minimum <= section_maximum
                for section_minimum, section_maximum in section_ranges
            )


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
        main.run_copy_worker(run_payload(body_min_length=1000, body_max_length=1400))

    assert exc_info.value.status_code == 502
    assert "body length" in exc_info.value.detail.lower()
    assert len(FakeClient.requests) == 5


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
