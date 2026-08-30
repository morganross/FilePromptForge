from pathlib import Path

from FilePromptForge.file_handler import _uses_cliproxy_anthropic
from FilePromptForge.helpers import load_config


def test_anthropic_provider_uses_private_cliproxy_origin() -> None:
    cfg = load_config(str(Path(__file__).parents[1] / "FilePromptForge" / "fpf_config.yaml"))
    assert cfg["provider_urls"]["anthropic"] == "http://searchbox.internal.apicostx.com:8317/v1/messages"
    assert _uses_cliproxy_anthropic(cfg, "anthropic") is True


def test_other_anthropic_origins_are_not_treated_as_cliproxy() -> None:
    assert _uses_cliproxy_anthropic(
        {"provider_urls": {"anthropic": "https://api.anthropic.com/v1/messages"}},
        "anthropic",
    ) is False
    assert _uses_cliproxy_anthropic(
        {"provider_urls": {"anthropic": "http://searchbox.internal.apicostx.com:8317/v1/messages"}},
        "openai",
    ) is False
