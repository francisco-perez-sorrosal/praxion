"""Tests for hooks/precompact_state.py -- the pre-compaction pipeline snapshot.

The snapshot exists so the agent can re-orient after compaction. A document that
grows one section per run is only useful at its end: the newest section is the
one to resume from.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent / "precompact_state.py"
SLUG = "feature"


def _load_module():
    spec = importlib.util.spec_from_file_location("precompact_state", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _numbered(prefix: str, count: int) -> str:
    return "".join(f"{prefix} {n}\n" for n in range(1, count + 1))


def _snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docs: dict[str, str]) -> str:
    task_dir = tmp_path / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    for name, body in docs.items():
        (task_dir / name).write_text(body)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    _load_module().main()
    return (tmp_path / ".ai-work" / "PIPELINE_STATE.md").read_text()


def test_test_results_snapshot_keeps_the_newest_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(tmp_path, monkeypatch, {"TEST_RESULTS.md": _numbered("run line", 100)})

    assert "run line 100\n" in snapshot
    assert "run line 1\n" not in snapshot


def test_other_documents_snapshot_keeps_their_opening_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(tmp_path, monkeypatch, {"WIP.md": _numbered("wip line", 100)})

    assert "wip line 1\n" in snapshot
    assert "wip line 100\n" not in snapshot


def test_short_test_results_is_snapshotted_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(tmp_path, monkeypatch, {"TEST_RESULTS.md": _numbered("run line", 5)})

    assert "run line 1\n" in snapshot
    assert "run line 5\n" in snapshot
