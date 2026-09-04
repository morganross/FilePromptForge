from FilePromptForge.providers.google.fpf_google_main import build_payload


def test_gemini_3_preserves_medium_thinking_level() -> None:
    payload, headers = build_payload(
        "research this",
        {
            "model": "gemini-3.7-flash",
            "reasoning": {"effort": "medium"},
        },
    )

    assert headers is None
    assert payload["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "medium",
        "includeThoughts": True,
    }
