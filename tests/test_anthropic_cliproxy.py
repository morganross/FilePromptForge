from pathlib import Path

from FilePromptForge.helpers import load_config


def test_anthropic_provider_defaults_to_public_origin() -> None:
    cfg = load_config(str(Path(__file__).parents[1] / "FilePromptForge" / "fpf_config.yaml"))
    assert cfg["provider_urls"]["anthropic"] == "https://api.anthropic.com/v1/messages"


def test_default_provider_origins_are_public() -> None:
    cfg = load_config(str(Path(__file__).parents[1] / "FilePromptForge" / "fpf_config.yaml"))
    for url in cfg["provider_urls"].values():
        assert "searchbox.internal" not in url
        assert "10.0.1." not in url
