"""Tests for inject_compaction_orientation.py -- SessionStart post-compaction restore."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_NAME = "inject_compaction_orientation"
MODULE_DIR = Path(__file__).parent
MODULE_PATH = MODULE_DIR / f"{MODULE_NAME}.py"


def _load_module():
    """Load the hook by inserting hooks/ onto sys.path and importing it.

    Uses `importlib.import_module` (not `spec_from_file_location`) so that the
    not-yet-written module surfaces as `ModuleNotFoundError` -- the correct RED
    state for this step -- rather than a `FileNotFoundError` from the loader
    trying to open a script that does not exist yet.
    """
    sys.path.insert(0, str(MODULE_DIR))
    return importlib.import_module(MODULE_NAME)


# Forces collection to fail RED (ModuleNotFoundError) until the hook exists.
# Also the one definition of the forbidden-verb list: read from the module
# under test (`_mod.ORCHESTRATION_VERBS`) rather than duplicating the tuple
# here, so the test and the hook cannot drift apart.
_mod = _load_module()


def _run_hook(
    payload_text: str, cwd: Path, extra_env: dict | None = None
) -> subprocess.CompletedProcess:
    """Invoke the hook as a subprocess with a raw stdin payload.

    `cwd` sets the subprocess's actual working directory -- the hook derives
    everything from the filesystem, never from a payload field, so fixtures
    control location purely through where the process runs.
    """
    env = {**os.environ, **(extra_env or {})}
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=payload_text,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )


def _additional_context(result: subprocess.CompletedProcess) -> str:
    parsed = json.loads(result.stdout)
    return parsed["hookSpecificOutput"]["additionalContext"]


def _ai_work_root(tmp_path: Path) -> Path:
    root = tmp_path / ".ai-work"
    root.mkdir(exist_ok=True)
    return root


def _write_wip(task_dir: Path, current_step_body: str) -> None:
    """Write a sequential-mode WIP.md with a `## Current Step` section."""
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "WIP.md").write_text(
        "# WIP: Fixture Feature\n\n"
        "## Current Step\n\n"
        f"{current_step_body}\n\n"
        "## Progress\n\n"
        "- [x] Registry entry\n"
        "- [ ] Wire up the retry queue\n",
        encoding="utf-8",
    )


def _write_plan(task_dir: Path) -> None:
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text("# Plan: Fixture Feature\n", encoding="utf-8")


def _write_systems_plan(task_dir: Path) -> None:
    (task_dir / "SYSTEMS_PLAN.md").write_text("# Systems Plan: Fixture Feature\n", encoding="utf-8")


def _write_handoff(task_dir: Path, readiness: str) -> None:
    (task_dir / "HANDOFF.md").write_text(
        f"# HANDOFF: fixture-feature\n\nreadiness: {readiness}\n\n## Preflight\n...\n",
        encoding="utf-8",
    )


def _set_mtime(path: Path, when: float) -> None:
    """Force a deterministic mtime so newest-WIP.md selection is reproducible."""
    os.utime(path, (when, when))


class TestPositiveEmit:
    """A `compact` restart with an in-flight pipeline gets oriented."""

    def test_emits_orientation_naming_slug_and_current_step(self, tmp_path: Path) -> None:
        ai_work = _ai_work_root(tmp_path)
        _write_wip(ai_work / "fixture-feature", "Wire up the retry queue (in progress)")

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        assert result.returncode == 0
        context = _additional_context(result)
        assert "fixture-feature" in context
        assert "Wire up the retry queue" in context


class TestNonCompactSource:
    """Every other `source` value is a silent no-op."""

    @pytest.mark.parametrize("source", ["startup", "resume", "clear"])
    def test_emits_nothing_for_non_compact_sources(self, tmp_path: Path, source: str) -> None:
        ai_work = _ai_work_root(tmp_path)
        _write_wip(ai_work / "fixture-feature", "Wire up the retry queue (in progress)")

        result = _run_hook(json.dumps({"source": source}), tmp_path)

        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestSilentFailurePaths:
    """Every documented failure path degrades to no output, exit 0 -- never a
    traceback on stdout, so a broken hook can never corrupt or block a turn."""

    def test_silent_when_no_ai_work_tree_exists(self, tmp_path: Path) -> None:
        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        assert result.returncode == 0
        assert result.stdout.strip() == ""

    @pytest.mark.parametrize(
        "wip_body",
        ["", "Just some prose, no headers, no checklist.\n"],
        ids=["empty-file", "unparseable-prose"],
    )
    def test_silent_when_wip_has_no_recognizable_current_step(
        self, tmp_path: Path, wip_body: str
    ) -> None:
        ai_work = _ai_work_root(tmp_path)
        task_dir = ai_work / "fixture-feature"
        task_dir.mkdir(parents=True)
        (task_dir / "WIP.md").write_text(wip_body, encoding="utf-8")

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        assert result.returncode == 0
        assert result.stdout.strip() == ""

    @pytest.mark.parametrize(
        "payload_text", ["", "not-json"], ids=["empty-stdin", "malformed-json"]
    )
    def test_silent_on_empty_or_malformed_stdin_payload(
        self, tmp_path: Path, payload_text: str
    ) -> None:
        ai_work = _ai_work_root(tmp_path)
        _write_wip(ai_work / "fixture-feature", "Wire up the retry queue (in progress)")

        result = _run_hook(payload_text, tmp_path)

        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_silent_when_reading_a_pipeline_document_raises(self, tmp_path: Path) -> None:
        """WIP.md is a directory, not a file -- any read on it raises. The hook
        must degrade to no output rather than let the exception propagate."""
        ai_work = _ai_work_root(tmp_path)
        task_dir = ai_work / "fixture-feature"
        (task_dir / "WIP.md").mkdir(parents=True)

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestByteCeiling:
    """The restore never costs more context than it saves."""

    def test_orientation_stays_within_byte_ceiling_with_truncation_marker(
        self, tmp_path: Path
    ) -> None:
        ai_work = _ai_work_root(tmp_path)
        now = 2_000_000_000.0  # fixed reference instant, not wall-clock dependent

        # 49 sibling pipelines, older mtimes -- named only, never elaborated.
        for i in range(49):
            sibling_dir = ai_work / f"sibling-task-slug-{i:03d}-with-a-long-descriptive-name"
            _write_wip(sibling_dir, f"Filler item {i}: a long filler description")
            _set_mtime(sibling_dir / "WIP.md", now - 1000 + i)

        # The elaborated pipeline: newest mtime, an oversized current-step body
        # that alone exceeds the ceiling.
        target_dir = ai_work / "target-task-slug-with-the-newest-wip-mtime"
        oversized_body = "Working on: " + ("x" * 2000)
        _write_wip(target_dir, oversized_body)
        _set_mtime(target_dir / "WIP.md", now)

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        assert result.returncode == 0
        context = _additional_context(result)
        assert len(context.encode("utf-8")) <= 1024
        assert "…[truncated]" in context


class TestRoleNeutralContent:
    """The block reads identically in a main window and a subagent window."""

    @pytest.mark.parametrize("verb", _mod.ORCHESTRATION_VERBS)
    def test_orientation_names_no_orchestration_verb(self, tmp_path: Path, verb: str) -> None:
        ai_work = _ai_work_root(tmp_path)
        _write_wip(ai_work / "fixture-feature", "Wire up the retry queue (in progress)")

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        context = _additional_context(result).lower()
        assert verb not in context

    def test_current_step_position_survives_but_orchestration_verb_is_filtered(
        self, tmp_path: Path
    ) -> None:
        """A step title that itself contains a directive-shaped verb still
        reports its position -- but the verb itself must not survive into the
        block, on this line or any other."""
        ai_work = _ai_work_root(tmp_path)
        _write_wip(
            ai_work / "fixture-feature",
            "Step 9: Commit and merge the worktree",  # id-citation-discipline:ignore
        )

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        context = _additional_context(result)
        assert "Step 9" in context  # id-citation-discipline:ignore
        lowered = context.lower()
        assert not any(verb in lowered for verb in _mod.ORCHESTRATION_VERBS)


class TestPointerOrder:
    """Pointer order is part of the contract: a handoff, when present, is read
    before any other pipeline document."""

    def test_handoff_named_first_and_overridden_readiness_noted_inline(
        self, tmp_path: Path
    ) -> None:
        ai_work = _ai_work_root(tmp_path)
        task_dir = ai_work / "fixture-feature"
        _write_wip(task_dir, "Wire up the retry queue (in progress)")
        _write_plan(task_dir)
        _write_systems_plan(task_dir)
        _write_handoff(task_dir, readiness="overridden")

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        context = _additional_context(result)
        handoff_index = context.index("HANDOFF.md")
        assert handoff_index < context.index("IMPLEMENTATION_PLAN.md")
        assert handoff_index < context.index("WIP.md")
        assert handoff_index < context.index("SYSTEMS_PLAN.md")

        handoff_line = next(line for line in context.splitlines() if "HANDOFF.md" in line)
        assert "overridden" in handoff_line

    def test_pointer_set_omits_handoff_when_absent(self, tmp_path: Path) -> None:
        ai_work = _ai_work_root(tmp_path)
        task_dir = ai_work / "fixture-feature"
        _write_wip(task_dir, "Wire up the retry queue (in progress)")
        _write_plan(task_dir)

        result = _run_hook(json.dumps({"source": "compact"}), tmp_path)

        context = _additional_context(result)
        assert "HANDOFF.md" not in context
