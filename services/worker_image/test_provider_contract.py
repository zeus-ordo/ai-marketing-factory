from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from fastapi import HTTPException

from app import main
from app.schemas import ImageRunRequest


FAKE_API_KEY = "fake-provider-key"
FULL_PROVIDER_BODY = "provider body containing sensitive diagnostic details"


def _response(status_code: int, body: dict, headers: dict[str, str] | None = None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = body
    response.text = FULL_PROVIDER_BODY
    return response


def _client_for(responses: list[Mock]) -> Mock:
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    client.post.side_effect = responses
    return client


def test_gemini_valid_image_response_returns_data_url():
    response = _response(
        200,
        {"steps": [{"content": [{"type": "image", "data": "aW1hZ2U=", "mime_type": "image/png"}]}]},
    )
    with patch.object(main.httpx, "Client", return_value=_client_for([response])):
        result = main._generate_gemini_image("safe prompt", "1024x1024", FAKE_API_KEY)

    assert result == "data:image/png;base64,aW1hZ2U="


def test_gemini_empty_steps_raises_retryable_provider_error():
    response = _response(200, {"steps": []})
    with patch.object(main.httpx, "Client", return_value=_client_for([response, response, response])):
        with patch.object(main.time, "sleep") as sleep:
            with pytest.raises(main.ProviderError) as error:
                main._generate_gemini_image("safe prompt", "1024x1024", FAKE_API_KEY)

    assert error.value.provider == "gemini"
    assert error.value.status_code == 200
    assert error.value.retryable is True
    assert error.value.attempts == 3
    assert sleep.call_count == 2


def test_gemini_alternate_content_shape_is_rejected_without_secret_logging():
    response = _response(
        200,
        {"steps": [{"content": [{"type": "text", "text": FULL_PROVIDER_BODY, "api_key": FAKE_API_KEY}]}]},
    )
    with patch.object(main.httpx, "Client", return_value=_client_for([response, response, response])):
        with patch.object(main.time, "sleep"):
            with pytest.raises(main.ProviderError) as error:
                main._generate_gemini_image("safe prompt", "1024x1024", FAKE_API_KEY)

    assert error.value.retryable is True
    assert FAKE_API_KEY not in str(error.value)
    assert FULL_PROVIDER_BODY not in str(error.value)


def test_provider_429_retries_and_honors_retry_after():
    responses = [
        _response(429, {}, {"Retry-After": "0.25"}),
        _response(200, {"steps": [{"content": [{"type": "image", "data": "aW1hZ2U="}]}]}),
    ]
    client = _client_for(responses)
    with patch.object(main.httpx, "Client", return_value=client):
        with patch.object(main.time, "sleep") as sleep:
            result = main._generate_gemini_image("safe prompt", "1024x1024", FAKE_API_KEY)

    assert result.startswith("data:image/")
    assert client.post.call_count == 2
    assert sleep.call_args.args[0] == 0.25
    assert sleep.call_args.args[0] <= main.MAX_RETRY_DELAY_SECONDS


def test_provider_500_retries_three_times_then_fails():
    responses = [_response(500, {}), _response(500, {}), _response(500, {})]
    client = _client_for(responses)
    with patch.object(main.httpx, "Client", return_value=client):
        with patch.object(main.time, "sleep") as sleep:
            with pytest.raises(main.ProviderError) as error:
                main._generate_gemini_image("safe prompt", "1024x1024", FAKE_API_KEY)

    assert error.value.status_code == 500
    assert error.value.retryable is True
    assert error.value.attempts == 3
    assert client.post.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [0.5, 1.0]
    assert all(delay <= main.MAX_RETRY_DELAY_SECONDS for delay in [0.5, 1.0])


def test_provider_400_does_not_retry():
    response = _response(400, {})
    client = _client_for([response])
    with patch.object(main.httpx, "Client", return_value=client):
        with patch.object(main.time, "sleep") as sleep:
            with pytest.raises(main.ProviderError) as error:
                main._generate_gemini_image("safe prompt", "1024x1024", FAKE_API_KEY)

    assert error.value.status_code == 400
    assert error.value.retryable is False
    assert error.value.attempts == 1
    assert client.post.call_count == 1
    assert sleep.call_count == 0


def test_run_endpoint_never_returns_success_with_empty_real_assets():
    payload = ImageRunRequest(
        task_id="task-1",
        campaign_id="campaign-1",
        company_id="company-1",
        prompt="safe prompt",
        sizes=["1024x1024"],
    )
    with patch.object(main, "STRICT_REAL_MODE", True), patch.object(main, "_active_api_key", return_value=FAKE_API_KEY):
        with patch.object(main, "_generate_image_asset_url", return_value=""):
            with pytest.raises(HTTPException) as error:
                main.run_image_worker(payload)

    assert error.value.status_code >= 400
