import pytest

from FilePromptForge.file_handler import (
    _build_google_generate_content_url,
    _select_google_provider_origin,
)


@pytest.mark.parametrize(
    ("configured", "model", "expected"),
    [
        (
            "http://searchbox.internal.apicostx.com:8317",
            "gemini-3.6-flash-high",
            "http://searchbox.internal.apicostx.com:8317/v1beta/models/gemini-3.6-flash-high:generateContent",
        ),
        (
            "https://generativelanguage.googleapis.com",
            "gemini-2.5-pro",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
        ),
        (
            "https://generativelanguage.googleapis.com/v1beta",
            "gemini-2.5-flash",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        ),
        (
            "https://generativelanguage.googleapis.com/v1beta/models/old-model:generateContent",
            "gemini-3-flash",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash:generateContent",
        ),
        (
            "http://gateway.internal/v1beta/models/{model}:generateContent",
            "gemini/model with spaces",
            "http://gateway.internal/v1beta/models/gemini%2Fmodel%20with%20spaces:generateContent",
        ),
    ],
)
def test_build_google_generate_content_url(configured: str, model: str, expected: str) -> None:
    assert _build_google_generate_content_url(configured, model) == expected


@pytest.mark.parametrize("configured", ["not-a-url", "ftp://gateway.internal", "http://gateway.internal?x=1"])
def test_build_google_generate_content_url_rejects_invalid_origins(configured: str) -> None:
    with pytest.raises(RuntimeError):
        _build_google_generate_content_url(configured, "gemini-3-flash")


def test_build_google_generate_content_url_requires_model() -> None:
    with pytest.raises(RuntimeError, match="requires cfg\\['model'\\]"):
        _build_google_generate_content_url("http://gateway.internal", "")


def test_select_google_provider_origin_preserves_direct_google_models() -> None:
    cfg = {"google_antigravity_models": ["gemini-3.1-pro-preview"]}
    urls = {
        "google": "https://generativelanguage.googleapis.com",
        "google_antigravity": "http://searchbox.internal:8317",
    }

    assert _select_google_provider_origin(cfg, urls, "gemini-2.5-pro") == urls["google"]
    assert _select_google_provider_origin(cfg, urls, "gemini-3.1-pro-preview") == urls["google_antigravity"]


def test_select_google_provider_origin_requires_gateway_for_listed_model() -> None:
    with pytest.raises(RuntimeError, match="provider_urls.google_antigravity"):
        _select_google_provider_origin(
            {"google_antigravity_models": ["gemini-3.1-pro-preview"]},
            {"google": "https://generativelanguage.googleapis.com"},
            "gemini-3.1-pro-preview",
        )


def test_select_google_provider_origin_rejects_non_list_model_config() -> None:
    with pytest.raises(RuntimeError, match="must be a list"):
        _select_google_provider_origin(
            {"google_antigravity_models": "gemini-3.1-pro-preview"},
            {"google": "https://generativelanguage.googleapis.com"},
            "gemini-3.1-pro-preview",
        )
