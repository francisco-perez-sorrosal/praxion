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
    """Behavioral eval must not spawn subprocesses or import phoenix."""
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


def test_regression_prints_slug_keyed_banner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """regression must emit the slug-keyed-baseline TODO banner before running."""
    from types import SimpleNamespace

    from praxion_evals.regression.baselines import (
        BaselineSummary,
        utc_now,
        write_baseline,
    )

    baseline_path = tmp_path / "baseline.json"
    write_baseline(
        BaselineSummary(task_slug="demo", captured_at=utc_now(), span_count=10),
        baseline_path,
    )

    fake_client = SimpleNamespace(get_spans_dataframe=lambda **_: None)
    monkeypatch.setitem(
        sys.modules,
        "phoenix",
        SimpleNamespace(Client=lambda *_a, **_k: fake_client),
    )

    main(["regression", "--baseline", str(baseline_path), "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert "TODO" in captured.err
    assert "slug-keyed" in captured.err
    assert "td-005" in captured.err


def test_capture_baseline_prints_slug_keyed_banner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """capture-baseline must emit the slug-keyed-baseline TODO banner before running."""
    from types import SimpleNamespace

    import pandas as pd

    fake_client = SimpleNamespace(get_spans_dataframe=lambda **_: pd.DataFrame())
    monkeypatch.setitem(
        sys.modules,
        "phoenix",
        SimpleNamespace(Client=lambda *_a, **_k: fake_client),
    )

    main(
        [
            "capture-baseline",
            "--task-slug",
            "demo",
            "--output",
            str(tmp_path / "b.json"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert "TODO" in captured.err
    assert "slug-keyed" in captured.err
    assert "td-005" in captured.err


def test_regression_warns_when_baseline_has_no_numeric_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Regression against a numeric-less baseline must print a WARNING to stderr."""
    from praxion_evals.regression.baselines import (
        BaselineSummary,
        utc_now,
        write_baseline,
    )

    baseline_path = tmp_path / "baseline.json"
    write_baseline(
        BaselineSummary(
            task_slug="demo",
            captured_at=utc_now(),
            expected_phases=("research",),
        ),
        baseline_path,
    )

    # Stub Phoenix so read_current_summary returns empty without network.
    from types import SimpleNamespace

    fake_client = SimpleNamespace(get_spans_dataframe=lambda **_: None)
    monkeypatch.setitem(
        sys.modules,
        "phoenix",
        SimpleNamespace(Client=lambda *_a, **_k: fake_client),
    )

    exit_code = main(
        [
            "regression",
            "--baseline",
            str(baseline_path),
            "--repo-root",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "no numeric fields" in captured.err
    assert exit_code == 0  # no numeric drift is possible


def test_capture_baseline_subcommand_writes_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """capture-baseline writes to the conventional path and reports numeric fields."""
    # Stub Phoenix to return a synthetic DataFrame.
    from types import SimpleNamespace

    import pandas as pd

    df = pd.DataFrame(
        [
            {"span_kind": "CHAIN", "name": "root"},
            {"span_kind": "TOOL", "name": "Read"},
            {"span_kind": "AGENT", "name": "researcher"},
        ]
    )
    fake_client = SimpleNamespace(get_spans_dataframe=lambda **_: df)
    monkeypatch.setitem(
        sys.modules,
        "phoenix",
        SimpleNamespace(Client=lambda *_a, **_k: fake_client),
    )

    # Seed a deliverable under .ai-work/demo/.
    task_dir = tmp_path / ".ai-work" / "demo"
    task_dir.mkdir(parents=True)
    (task_dir / "SYSTEMS_PLAN.md").write_text("x", encoding="utf-8")

    exit_code = main(
        [
            "capture-baseline",
            "--task-slug",
            "demo",
            "--repo-root",
            str(tmp_path),
        ]
    )

    expected_output = tmp_path / ".ai-state" / "evals" / "baselines" / "demo.json"
    captured = capsys.readouterr()
    assert exit_code == 0
    assert expected_output.exists()
    assert "span_count=3" in captured.out
    assert "tool_call_count=1" in captured.out
    assert "discovered 1 deliverables" in captured.out


def test_capture_baseline_respects_output_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """--output overrides the default baseline path."""
    from types import SimpleNamespace

    import pandas as pd

    fake_client = SimpleNamespace(get_spans_dataframe=lambda **_: pd.DataFrame())
    monkeypatch.setitem(
        sys.modules,
        "phoenix",
        SimpleNamespace(Client=lambda *_a, **_k: fake_client),
    )

    custom_output = tmp_path / "custom" / "baseline.json"
    exit_code = main(
        [
            "capture-baseline",
            "--task-slug",
            "demo",
            "--output",
            str(custom_output),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    assert custom_output.exists()
    assert not (tmp_path / ".ai-state").exists()
