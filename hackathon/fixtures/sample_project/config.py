"""Configuration loading helpers."""

import json
from pathlib import Path

DEFAULT_CONFIG = {"timeout": 30, "retries": 3, "endpoint": "https://api.example.com"}


def merge_config(base: dict, overrides: dict) -> dict:
    """Merge two config dicts; overrides take precedence."""
    return {**base, **overrides}


def config_path_for(env: str) -> Path:
    """Return the conventional config path for a given environment name."""
    return Path("config") / f"{env}.json"
