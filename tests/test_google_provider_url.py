import pytest

from FilePromptForge.file_handler import (
    _build_google_generate_content_url,
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
