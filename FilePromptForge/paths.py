"""User-writable paths used by FilePromptForge."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_log_path

APP_NAME = "FilePromptForge"
APP_AUTHOR = "Morgan Ross"


def config_dir() -> Path:
    path = user_config_path(APP_NAME, APP_AUTHOR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = user_cache_path(APP_NAME, APP_AUTHOR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = user_log_path(APP_NAME, APP_AUTHOR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_env_file() -> Path:
    return config_dir() / ".env"


def default_log_file(process_id: int) -> Path:
    return log_dir() / f"fpf_run_{process_id}.log"


def default_pricing_index() -> Path:
    return cache_dir() / "pricing_index.json"

