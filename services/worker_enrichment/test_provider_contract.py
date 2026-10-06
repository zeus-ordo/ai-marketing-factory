import math

import pytest
from services.shared.image_enrichment import validate_safe_attributes

from app import providers
from app.providers import EmbeddingProvider, ImageAnalysisProvider, validate_embedding, validate_attributes


def test_provider_interfaces_expose_required_methods():
    assert callable(getattr(ImageAnalysisProvider, "analyze"))
    assert callable(getattr(EmbeddingProvider, "embed"))


def test_analysis_attributes_are_json_only_and_reject_private_values():
    assert validate_attributes({"objects": ["bowl"], "confidence": 0.9}) == {
        "objects": ["bowl"],
        "confidence": 0.9,
    }

    with pytest.raises(ValueError):
        validate_attributes({"stored_path": "/private/image.png"})


def test_embedding_must_be_finite_numbers():
    assert validate_embedding([0.1, -2, 3.5]) == [0.1, -2.0, 3.5]
    with pytest.raises(ValueError):
        validate_embedding([math.nan])


@pytest.mark.parametrize(
    "attributes",
    [
        {"path": "../../secret.png"},
        {"relative": "../secret.png"},
        {"payload": "data:image/png;base64,AAAA"},
        {"binary_data": "AA=="},
    ],
)
def test_standalone_runtime_validator_rejects_private_path_and_binary_values(monkeypatch, attributes):
    monkeypatch.setattr(providers, "_campaign_validate_attributes", validate_safe_attributes)

    with pytest.raises((TypeError, ValueError)):
        providers.validate_attributes(attributes)
