"""Tests for scripts/check_ruff_pin_drift.py.

The gate exists because two independently-versioned ruffs formatting the same
files never converge, and the resulting commit loop has silently reverted work
in this repository via pre-commit's stash/restore. These tests pin both halves
of that contract: the drift shapes it must catch, and — equally important — the
absent-input shapes it must NOT fail on, since this ships to managed projects
whose stacks differ and a gate that fires on a non-Python repo is noise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts" / "check_ruff_pin_drift.py"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import check_ruff_pin_drift as mod  # noqa: E402


def _config(version: str | None) -> str:
    if version is None:
        return "repos:\n  - repo: https://github.com/psf/black\n    rev: 24.1.0\n"
    return (
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        f"    rev: v{version}\n"
        "    hooks:\n      - id: ruff\n"
    )


def _pyproject(version: str | None) -> str:
    if version is None:
        return '[project]\nname = "x"\n'
    return f'[dependency-groups]\ndev = [\n    "pytest",\n    "ruff=={version}",\n]\n'


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args], capture_output=True, text=True, cwd=str(cwd)
    )


# --- parsing ---------------------------------------------------------------


def test_reads_the_pinned_hook_version():
    assert mod.pinned_hook_version(_config("0.15.22")) == "0.15.22"


def test_reads_the_pinned_hook_version_through_interleaved_comments():
    """The real config carries a comment block between `- repo:` and `rev:`."""
    text = (
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    # a rationale comment\n"
        "    # spanning two lines\n"
        "    rev: v0.15.22\n"
    )
    assert mod.pinned_hook_version(text) == "0.15.22"


def test_floating_dependency_constraint_is_read_as_no_pin():
    """`>=` cannot guarantee the equality this gate enforces, so it must not be
    mistaken for a pin — reporting a match there would be a false clear."""
    assert mod.declared_dep_version('dev = ["ruff>=0.15.22"]') is None
    assert mod.declared_dep_version('dev = ["ruff"]') is None
    assert mod.declared_dep_version('dev = ["ruff==0.15.22"]') == "0.15.22"


# --- drift detection (the canaries) ----------------------------------------


def test_flags_hook_versus_declared_dependency_drift():
    findings = mod.find_drift(_config("0.15.22"), _pyproject("0.8.6"), None)
    assert len(findings) == 1, findings
    assert "0.15.22" in findings[0], "the message must name the pinned version"
    assert "0.8.6" in findings[0], "the message must name the declared version"


def test_flags_hook_versus_installed_ruff_drift():
    findings = mod.find_drift(_config("0.15.22"), _pyproject("0.15.22"), ("0.15.4", "PATH"))
    assert len(findings) == 1, findings
    assert "0.15.4" in findings[0]


def test_reports_both_drifts_independently():
    """Two distinct disagreements must produce two findings, not one merged
    message — they have different fixes (edit pyproject vs reinstall)."""
    findings = mod.find_drift(_config("0.15.22"), _pyproject("0.8.6"), ("0.14.0", "PATH"))
    assert len(findings) == 2, findings


def test_cli_exits_nonzero_on_drift(tmp_path: Path):
    (tmp_path / ".pre-commit-config.yaml").write_text(_config("0.15.22"))
    (tmp_path / "pyproject.toml").write_text(_pyproject("0.8.6"))
    result = _run(["--repo-root", str(tmp_path), "--skip-path-check"], cwd=tmp_path)
    assert result.returncode == 1, result.stdout
    assert "ruff pin drift" in result.stdout


# --- the shapes that must NOT fire -----------------------------------------


def test_agreeing_pins_are_clean():
    assert mod.find_drift(_config("0.15.22"), _pyproject("0.15.22"), ("0.15.22", "PATH")) == []


def test_a_repo_without_a_ruff_hook_is_out_of_scope():
    """Absent hook is not drift — the gate ships to managed projects that may
    have no Python surface at all."""
    assert mod.find_drift(_config(None), _pyproject("0.15.22"), ("0.9.0", "PATH")) == []


def test_a_repo_that_has_not_adopted_the_dependency_pin_is_not_flagged_for_it():
    """No declared dep is not drift; only a *disagreeing* one is."""
    assert mod.find_drift(_config("0.15.22"), _pyproject(None), ("0.15.22", "PATH")) == []


def test_cli_exits_zero_when_pins_agree(tmp_path: Path):
    (tmp_path / ".pre-commit-config.yaml").write_text(_config("0.15.22"))
    (tmp_path / "pyproject.toml").write_text(_pyproject("0.15.22"))
    result = _run(["--repo-root", str(tmp_path), "--skip-path-check"], cwd=tmp_path)
    assert result.returncode == 0, result.stdout


def test_missing_precommit_config_is_not_an_error(tmp_path: Path):
    result = _run(["--repo-root", str(tmp_path)], cwd=tmp_path)
    assert result.returncode == 0, result.stdout


# --- resolution order ------------------------------------------------------


def test_project_environment_ruff_wins_over_path(tmp_path: Path, monkeypatch):
    """A uv-managed project's own ruff is the one a developer runs. Comparing
    against an unrelated global binary first would fail someone doing
    everything correctly — a gate that punishes correct behaviour gets
    bypassed, and a bypassed gate protects nothing."""
    venv_ruff = tmp_path / ".venv" / "bin" / "ruff"
    venv_ruff.parent.mkdir(parents=True)
    venv_ruff.write_text("#!/bin/sh\necho 'ruff 0.15.22'\n")
    venv_ruff.chmod(0o755)
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/local/bin/ruff")

    resolved = mod.resolve_local_ruff(tmp_path)

    assert resolved is not None
    assert resolved == ("0.15.22", ".venv/bin/ruff"), (
        "the project environment's ruff must win over PATH"
    )


def test_path_ruff_is_used_when_the_project_manages_none(tmp_path: Path, monkeypatch):
    """With no project-managed ruff, the global binary IS the one that will
    fight the hook, so it must still be compared."""
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/local/bin/ruff")
    monkeypatch.setattr(mod, "_version_of", lambda _: "0.9.9")

    assert mod.resolve_local_ruff(tmp_path) == ("0.9.9", "PATH")


@pytest.mark.parametrize("returned", [None])
def test_unresolvable_ruff_is_not_drift(tmp_path: Path, monkeypatch, returned):
    """An unreadable or absent ruff yields no comparison rather than a
    fabricated mismatch."""
    monkeypatch.setattr(mod.shutil, "which", lambda _: returned)
    assert mod.resolve_local_ruff(tmp_path) is None
