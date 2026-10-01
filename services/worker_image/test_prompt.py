from app.prompt_utils import fit_minimax_prompt
from app.schemas import RevisionRequest
from pydantic import ValidationError


def test_fit_minimax_prompt_keeps_short_prompt_unchanged():
    prompt = "Campaign: demo\nCreate a campaign key visual."
    assert fit_minimax_prompt(prompt) == prompt


def test_fit_minimax_prompt_keeps_prompt_under_provider_limit_and_preserves_edges():
    prompt = "Campaign: final testing 001\n" + ("reference context " * 200) + "\nCreate a campaign key visual aligned with the brief."
    fitted = fit_minimax_prompt(prompt)

    assert len(fitted) <= 1400
    assert fitted.startswith("Campaign: final testing 001")
    assert fitted.endswith("Create a campaign key visual aligned with the brief.")


def test_image_revision_request_requires_company_id():
    try:
        RevisionRequest.model_validate({
            "task_id": "task-1", "campaign_id": "campaign-1", "prompt": "prompt",
            "reject_reason": "quality", "sizes": ["1024x1024"],
        })
    except ValidationError as exc:
        assert "company_id" in str(exc)
    else:
        raise AssertionError("company_id must be required")
