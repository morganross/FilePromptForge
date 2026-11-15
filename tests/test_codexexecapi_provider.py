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


def test_codexexecapi_address_comes_only_from_the_environment(monkeypatch) -> None:
    from FilePromptForge.providers.codexexecapi import fpf_codexexecapi_main as provider
    import pytest

    monkeypatch.delenv("CODEX_EXEC_API_URL", raising=False)
    with pytest.raises(RuntimeError, match="CODEX_EXEC_API_URL is required"):
        provider._resolve_provider_url()

    monkeypatch.setenv("CODEX_EXEC_API_URL", "http://cliproxy.invalid:8317")
    assert provider._resolve_provider_url() == "http://cliproxy.invalid:8317/v1/chat/completions"


def test_codexexecapi_token_comes_only_from_the_authorization_header(monkeypatch) -> None:
    import pytest

    monkeypatch.setenv("CODEX_EXEC_API_TOKEN", "from-environment")
    monkeypatch.setenv("CODEXEXECAPI_API_KEY", "from-environment")
    with pytest.raises(RuntimeError, match="Authorization: Bearer"):
        provider._extract_bearer_token({})
    assert provider._extract_bearer_token({"Authorization": "Bearer from-header"}) == "from-header"


@pytest.mark.parametrize("model", ["gpt-6-luna", "claude-haiku-5-5", "gemini-3.8-flash-high"])
def test_codexexecapi_supports_the_models_cliproxy_serves(model: str) -> None:
    payload, _ = provider.build_payload("Research this topic", {"model": f"codexexecapi:{model}"})

    assert payload["model"] == model


def test_codexexecapi_still_refuses_a_model_it_does_not_list() -> None:
    with pytest.raises(RuntimeError, match="is not supported"):
        provider.build_payload("Research this topic", {"model": "gpt-4o"})
