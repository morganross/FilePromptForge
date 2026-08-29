import pytest

from FilePromptForge.providers.codexexecapi import fpf_codexexecapi_main as provider


@pytest.mark.parametrize("model", ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"])
def test_codexexecapi_supports_gpt_56_family(model: str) -> None:
    payload, files = provider.build_payload(
        "Research this topic",
        {"model": model, "reasoning_effort": "high"},
    )

    assert files is None
    assert payload["model"] == model
    assert payload["reasoning_effort"] == "high"
    assert payload["reasoning"] == {"effort": "high"}


def test_codexexecapi_defaults_reasoning_to_medium() -> None:
    payload, _ = provider.build_payload("Research this topic", {"model": "gpt-5.6-luna"})

    assert payload["reasoning_effort"] == "medium"
