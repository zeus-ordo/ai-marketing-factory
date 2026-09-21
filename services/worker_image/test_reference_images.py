from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from app import main
from app.schemas import ImageRunRequest, ReferenceImage


def response() -> Mock:
    result = Mock(status_code=200, headers={})
    result.json.return_value = {"steps": [{"content": [{"type": "image", "data": "aW1hZ2U=", "mime_type": "image/png"}]}]}
    return result


def test_gemini_request_contains_actual_reference_image_parts():
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    client.post.return_value = response()

    with patch.object(main.httpx, "Client", return_value=client):
        result = main._generate_gemini_image(
            "Create a visual",
            "1024x1024",
            "key",
            [ReferenceImage(reference_id="ref-1", file_name="ref.png", mime_type="image/png", data="cmVm", folder="General")],
        )

    assert result.startswith("data:image/png;base64,")
    body = client.post.call_args.kwargs["json"]
    assert body["input"] == [
        {"type": "text", "text": "Create a visual"},
        {"type": "image", "data": "cmVm", "mime_type": "image/png", "reference_id": "ref-1"},
    ]


def test_image_worker_rejects_reference_attachment_errors():
    payload = ImageRunRequest(
        task_id="task-1",
        campaign_id="campaign-1",
        company_id="company-1",
        prompt="Create a visual",
        sizes=["1024x1024"],
        reference_images=[],
        reference_audit={"selected_count": 1, "attached_count": 0, "failures": [{"reference_id": "ref-1", "category": "missing_file"}]},
    )

    with pytest.raises(HTTPException) as error:
        main.run_image_worker(payload)

    assert error.value.status_code == 422
    assert "missing_file" in str(error.value.detail)
