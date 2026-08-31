import json

from FilePromptForge.pricing.fetch_pricing import (
    _merge_provider_native_records,
    normalize_model_entry,
)


def test_openrouter_anthropic_paid_models_are_included() -> None:
    record = normalize_model_entry(
        {
            "id": "anthropic/claude-opus-5",
            "pricing": {"prompt": "0.000005", "completion": "0.000025"},
        },
        "2026-08-30",
    )

    assert record is not None
    assert record["provider"] == "anthropic"
    assert record["model"] == "anthropic/claude-opus-5"
    assert record["input_price_per_million_usd"] == 5.0
    assert record["output_price_per_million_usd"] == 25.0


def test_unscoped_paid_provider_models_remain_excluded() -> None:
    record = normalize_model_entry(
        {
            "id": "mistralai/mistral-large-2512",
            "pricing": {"prompt": "0.000002", "completion": "0.000006"},
        },
        "2026-08-30",
    )

    assert record is None


def test_zero_priced_openrouter_models_remain_included() -> None:
    record = normalize_model_entry(
        {
            "id": "anthropic/claude-fable-5",
            "pricing": {"prompt": "0", "completion": "0"},
        },
        "2026-08-30",
    )

    assert record is not None
    assert record["input_price_per_million_usd"] == 0.0
    assert record["output_price_per_million_usd"] == 0.0


def test_refresh_preserves_provider_native_records(tmp_path) -> None:
    path = tmp_path / "pricing_index.json"
    path.write_text(
        json.dumps(
            [
                {
                    "provider": "anthropic",
                    "model": "anthropic/claude-opus-4-8",
                    "input_price_per_million_usd": 5.0,
                    "output_price_per_million_usd": 25.0,
                    "source": "anthropic",
                },
                {
                    "provider": "openrouter",
                    "model": "openrouter/old-model",
                    "input_price_per_million_usd": 1.0,
                    "output_price_per_million_usd": 1.0,
                    "source": "openrouter",
                },
            ]
        ),
        encoding="utf-8",
    )

    merged = _merge_provider_native_records(
        [
            {
                "provider": "anthropic",
                "model": "anthropic/claude-opus-4-8",
                "input_price_per_million_usd": 6.0,
                "output_price_per_million_usd": 30.0,
                "source": "openrouter",
            },
            {
                "provider": "anthropic",
                "model": "anthropic/claude-opus-5",
                "input_price_per_million_usd": 5.0,
                "output_price_per_million_usd": 25.0,
                "source": "openrouter",
            },
        ],
        path,
    )

    by_key = {f"{item['provider']}:{item['model'].rsplit('/', 1)[-1]}": item for item in merged}
    assert by_key["anthropic:claude-opus-4-8"]["source"] == "anthropic"
    assert by_key["anthropic:claude-opus-4-8"]["input_price_per_million_usd"] == 5.0
    assert "openrouter:old-model" not in by_key
    assert "anthropic:claude-opus-5" in by_key
