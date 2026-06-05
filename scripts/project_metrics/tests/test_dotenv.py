"""Behavioral tests for the stdlib ``.env`` loader used by the metrics CLI.

Each test writes a ``.env`` fixture under ``tmp_path`` and asserts how
``load_dotenv`` / ``find_dotenv`` merge it into ``os.environ``. The loader is
pure-with-respect-to-the-filesystem and deterministic — no network, no clocks —
so a fixed file always yields the same result. ``monkeypatch`` isolates
``os.environ`` and the working directory so no test leaks state.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.project_metrics._dotenv import find_dotenv, load_dotenv


def _write_env(directory: Path, body: str) -> Path:
    path = directory / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_key_into_unset_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = _write_env(tmp_path, "CLAUDE_CODE_OAUTH_TOKEN=sk-from-dotenv\n")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    parsed = load_dotenv(env_path)

    assert parsed["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-from-dotenv"
    assert os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-from-dotenv"


def test_does_not_override_already_set_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = _write_env(tmp_path, "ANTHROPIC_API_KEY=sk-from-dotenv\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-inline-export")

    load_dotenv(env_path)

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-inline-export"


def test_override_true_replaces_existing_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = _write_env(tmp_path, "ANTHROPIC_API_KEY=sk-from-dotenv\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-inline-export")

    load_dotenv(env_path, override=True)

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-dotenv"


def test_missing_file_is_a_noop(tmp_path: Path) -> None:
    assert load_dotenv(tmp_path / "does-not-exist.env") == {}


def test_parses_comments_blanks_export_and_quotes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "\n".join(
        [
            "# a comment",
            "",
            "export CLAUDE_CODE_OAUTH_TOKEN=sk-exported",
            'ANTHROPIC_API_KEY="sk-quoted-value"',
            "PLAIN=value  # trailing comment",
        ]
    )
    env_path = _write_env(tmp_path, body + "\n")
    for key in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "PLAIN"):
        monkeypatch.delenv(key, raising=False)

    parsed = load_dotenv(env_path)

    assert parsed["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-exported"
    assert parsed["ANTHROPIC_API_KEY"] == "sk-quoted-value"
    assert parsed["PLAIN"] == "value"


def test_skips_malformed_lines_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = _write_env(tmp_path, "no-equals-sign\n=missing-key\nGOOD=ok\n")
    monkeypatch.delenv("GOOD", raising=False)

    parsed = load_dotenv(env_path)

    assert parsed == {"GOOD": "ok"}


def test_find_dotenv_searches_cwd_upward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = _write_env(tmp_path, "KEY=value\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    found = find_dotenv()

    assert found == env_path.resolve()


def test_find_dotenv_returns_none_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    # tmp_path is isolated; ensure no .env exists in it or its (test-controlled) tree.
    assert not (tmp_path / ".env").exists()
    # find_dotenv may still locate a real .env above tmp_path on some machines;
    # constrain the search to the isolated tree by passing an explicit start.
    assert find_dotenv(start=tmp_path, filename="definitely-absent.env") is None
