"""CLI integration tests — no subprocess, no network."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from praxion_evals.cli import main


def test_list_subcommand_exits_zero(capsys: pytest.CaptureFixture[str]):
    exit_code = main(["list"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "behavioral" in captured.out
    assert "regression" in captured.out


def test_default_list_when_no_args(capsys: pytest.CaptureFixture[str]):
    exit_code = main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Tier" in captured.out


def test_behavioral_no_subprocess_no_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """EC-3.1.3: behavioral eval must not spawn subprocesses or import phoenix."""
    # Fingerprint subprocess.run + phoenix import — any attempt should flag the test.
    import subprocess

    def _fail_subprocess(*_args: object, **_kwargs: object):
        raise AssertionError("behavioral eval must not invoke subprocesses")

    monkeypatch.setattr(subprocess, "run", _fail_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _fail_subprocess)

    # Sabotage a potential phoenix import to detect accidental hot path.
    class _Boom:
        def __getattr__(self, _name: str):
            raise AssertionError("behavioral eval must not import phoenix")

    monkeypatch.setitem(sys.modules, "phoenix", _Boom())

    # Seed a minimal pipeline.
    slug = "demo"
    task_dir = tmp_path / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    for fname in (
        "SYSTEMS_PLAN.md",
        "IMPLEMENTATION_PLAN.md",
        "WIP.md",
        "VERIFICATION_REPORT.md",
    ):
        (task_dir / fname).write_text("x", encoding="utf-8")

    exit_code = main(
        [
            "behavioral",
            "--task-slug",
            slug,
            "--repo-root",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert "Behavioral Eval — demo" in captured.out
    assert exit_code == 0


def test_regression_missing_baseline_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    missing = tmp_path / "no-baseline.json"
    exit_code = main(["regression", "--baseline", str(missing)])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Baseline not found" in captured.err
