"""Tests for compose_handoff -- the handoff composer and its readiness gate.

Hermetic: pipelines are built under ``tmp_path``; the reconciler is driven
hermetically through a WIP.md with no checklist lines (reconcile() then
returns [] before touching git/WAL/test-status) or through compose()'s own
``_*_override`` pass-through kwargs, mirroring reconcile_pipeline_state.py's
own hooks.

A later section drives the world-read functions in the sibling
``_handoff_inputs.py`` (base-ref resolution, declared-files scope,
artifact listing, recent-log detection) through real throwaway git
repositories and real filesystem fixtures instead of hand-built verdict
dicts -- asserting each read's effect on the composed handoff, never on the
shape of its fallback value.

Run: ``pytest scripts/test_compose_handoff.py`` (or the module directly).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _handoff_readiness  # noqa: E402
import compose_handoff  # noqa: E402

SLUG = "demo-task"

BOUNDARY_ARCH_TO_PLAN = "architecture-to-planning"
BOUNDARY_PLAN_TO_IMPL = "planning-to-implementation"
BOUNDARY_IMPL_TO_VERIFY = "implementation-to-verification"

_PLACEHOLDER = "_[to fill at the checkpoint]_"

# Fixed section order -- the composer's own invariant, asserted below rather
# than assumed.
_SECTION_HEADINGS = [
    "§0 Preflight",
    "§1 State",
    "§2 Next action",
    "§3 Decisions & assumptions in force",
    "§4 Operating constraints from the user",
    "§5 Corrections in force",
    "§6 Do not re-inherit",
    "§7 Start here",
]


# --- fixture builders --------------------------------------------------------


def _setup_pipeline(tmp_path: Path, wip: str, plan: str | None = None) -> Path:
    """Create .ai-work/<slug>/{WIP,IMPLEMENTATION_PLAN}.md under tmp_path."""
    task_dir = tmp_path / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(wip, encoding="utf-8")
    if plan is not None:
        (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    return task_dir


def _minimal_wip() -> str:
    """A WIP.md with no checklist lines -- reconcile() short-circuits to []
    before reading git, the WAL, or TEST_RESULTS.md, so cases that only care
    about section structure or the readiness gate need no git/WAL fixture."""
    return "# WIP: demo\n\n## Current Batch\n\nNo steps tracked yet.\n"


def _render_existing_handoff(
    boundary: str,
    *,
    s3: str = "digest v1",
    s4: str = "constraints v1",
    s5: str = "corrections v1",
    s6: str = "do-not v1",
    readiness_state: str = "clean",
    omit_heading: str | None = None,
) -> str:
    """Render a well-formed (unless ``omit_heading`` is set) HANDOFF.md body."""
    header = [
        f"slug: {SLUG}",
        f"boundary: {boundary}",
        "branch: main",
        "base_sha: deadbeef",
        "worktree_path: /repo",
        "composed_at: 2026-01-01T00:00:00Z",
        "composer_version: 1",
        f"readiness: {readiness_state}",
        "",
    ]
    sections = [
        ("§0 Preflight", "preflight body"),
        ("§1 State", "state body"),
        ("§2 Next action", "next action body"),
        ("§3 Decisions & assumptions in force", s3),
        ("§4 Operating constraints from the user", s4),
        ("§5 Corrections in force", s5),
        ("§6 Do not re-inherit", s6),
        ("§7 Start here", f"start here body\n/resume-pipeline {SLUG}"),
    ]
    body = list(header)
    for heading, text in sections:
        if heading == omit_heading:
            continue
        body.append(f"## {heading}")
        body.append(text)
        body.append("")
    return "\n".join(body)


def _extract_section(text: str, heading: str) -> str:
    """Return the body of ``heading`` up to (not including) the next H2 heading."""
    marker = f"## {heading}"
    start = text.index(marker) + len(marker)
    rest = text[start:]
    cut = len(rest)
    for other in _SECTION_HEADINGS:
        if other == heading:
            continue
        idx = rest.find(f"## {other}")
        if idx != -1 and idx < cut:
            cut = idx
    return rest[:cut].strip()


def _wal_start(agent_id: str, session_id: str = "s1") -> dict:
    return {
        "event_type": "agent_start",
        "agent_id": agent_id,
        "session_id": session_id,
        "timestamp": "2026-01-01T00:00:00Z",
    }


def _wal_stop(agent_id: str, session_id: str = "s1") -> dict:
    return {
        "event_type": "agent_stop",
        "agent_id": agent_id,
        "session_id": session_id,
        "timestamp": "2026-01-01T00:01:00Z",
    }


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    extra_args: list[str],
    readiness_result: dict | None = None,
) -> int:
    """Invoke compose_handoff.main() hermetically against tmp_path.

    Monkeypatches repo-root resolution (same idiom as
    reconcile_pipeline_state.py's own CLI tests) and, when given, the pure
    ``readiness()`` function -- main()'s dispatch on Ready/Blocked/Overridden
    is a distinct concern from readiness()'s own correctness (covered
    separately by direct calls below), so the CLI tests fix the verdict to
    isolate main()'s response to it.
    """
    monkeypatch.setattr(compose_handoff, "resolve_repo_root", lambda *_a, **_k: tmp_path)
    monkeypatch.setattr(compose_handoff, "is_plugin_cache_path", lambda *_a, **_k: False)
    if readiness_result is not None:
        monkeypatch.setattr(compose_handoff, "readiness", lambda *_a, **_k: readiness_result)
    return compose_handoff.main([SLUG, "--repo-root", str(tmp_path), *extra_args])


# --- (a) basic compose with no prior handoff on disk (Absent input) ---------


def test_absent_input_writes_all_eight_sections_with_placeholders(tmp_path):
    _setup_pipeline(tmp_path, _minimal_wip())

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )
    text = result["text"]

    # Fixed section order -- every heading present, each strictly after the last.
    last_index = -1
    for heading in _SECTION_HEADINGS:
        idx = text.index(f"## {heading}")
        assert idx > last_index, f"{heading} out of order"
        last_index = idx

    # Judgement sections start as explicit placeholders; mechanical sections do not.
    for heading in _SECTION_HEADINGS[3:7]:
        assert _extract_section(text, heading) == _PLACEHOLDER
    for heading in ("§0 Preflight", "§1 State", "§2 Next action", "§7 Start here"):
        assert _PLACEHOLDER not in _extract_section(text, heading)


def test_invalid_boundary_is_rejected_and_writes_nothing(tmp_path):
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())

    with pytest.raises(Exception):  # noqa: PT011, B017 -- closed-enum guard, exception class TBD by the implementer
        compose_handoff.compose(
            SLUG,
            tmp_path,
            "not-a-real-boundary",
            None,
            _changed_files_override=[],
            _wal_rows_override=[],
            _test_status_override=None,
        )

    assert not (task_dir / "HANDOFF.md").exists()


# --- (b) carry-forward across an earlier boundary, including the new §4 ----


def test_earlier_boundary_carries_sections_4_through_6_byte_for_byte(tmp_path):
    _setup_pipeline(tmp_path, _minimal_wip())
    existing = _render_existing_handoff(
        BOUNDARY_ARCH_TO_PLAN,
        s3="stale digest from the prior boundary",
        s4="Ask before pushing to origin or releasing a version.",
        s5="Never re-add the deleted retry queue.",
        s6="Do not resurrect the old cache module.",
    )

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        existing,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )
    text = result["text"]

    assert (
        _extract_section(text, "§4 Operating constraints from the user")
        == "Ask before pushing to origin or releasing a version."
    )
    assert (
        _extract_section(text, "§5 Corrections in force") == "Never re-add the deleted retry queue."
    )
    assert (
        _extract_section(text, "§6 Do not re-inherit") == "Do not resurrect the old cache module."
    )
    # §3 resets across a boundary change -- the digest is incremental.
    assert _extract_section(text, "§3 Decisions & assumptions in force") != (
        "stale digest from the prior boundary"
    )
    # The superseded boundary is recorded somewhere in the artifact's history.
    assert BOUNDARY_ARCH_TO_PLAN in text


# --- (c) PresentSameBoundary: re-compose preserves §3-§6 too -----------------


def test_same_boundary_recompose_preserves_decisions_section(tmp_path):
    _setup_pipeline(tmp_path, _minimal_wip())
    existing = _render_existing_handoff(
        BOUNDARY_PLAN_TO_IMPL,
        s3="in-force digest, unchanged",
        s4="Ask before touching the fleet.",
        s5="Corrections carried over.",
        s6="Do not re-inherit the removed shim.",
    )

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        existing,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )
    text = result["text"]

    # Unlike the earlier-boundary case, §3 is NOT reset at the same boundary.
    assert (
        _extract_section(text, "§3 Decisions & assumptions in force")
        == "in-force digest, unchanged"
    )
    assert (
        _extract_section(text, "§4 Operating constraints from the user")
        == "Ask before touching the fleet."
    )
    assert _extract_section(text, "§5 Corrections in force") == "Corrections carried over."
    assert _extract_section(text, "§6 Do not re-inherit") == "Do not re-inherit the removed shim."


# --- (d) ground truth outranks a stale handoff (the critical case) ----------


def test_reports_disagreement_when_reconciler_contradicts_stale_handoff(tmp_path):
    plan = (
        "### Step 1: Build the retry queue\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: scripts/demo_retry_queue.py\n"
        "**Done when**: it works\n"
    )
    # WIP still claims the step pending -- but ground truth (files changed,
    # suite green) says otherwise; this is the "died before the checkbox"
    # case reconcile() classifies verified-complete/needs_mark.
    wip = "# WIP\n\n## Progress\n\n- [ ] Step 1: build the retry queue\n"  # id-citation-discipline:ignore
    _setup_pipeline(tmp_path, wip, plan)

    stale_existing = _render_existing_handoff(
        BOUNDARY_PLAN_TO_IMPL,
        s3="Step 1 is still pending.",  # id-citation-discipline:ignore
    )

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        stale_existing,
        _changed_files_override=["scripts/demo_retry_queue.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )

    assert result["conflicts"], "ground-truth disagreement must be surfaced, not swallowed"
    conflict = result["conflicts"][0]
    assert conflict["step"] == "Step 1"  # id-citation-discipline:ignore
    assert "verified-complete" in conflict["reconciler_verdict"]

    # Ground truth wins in the rendered §1, not the stale claim.
    assert "verified-complete" in _extract_section(result["text"], "§1 State")


# --- (e) PresentUnparseable -- refuse, never destroy -------------------------


def test_unparseable_existing_refuses_to_write(tmp_path, monkeypatch):
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    malformed = _render_existing_handoff(BOUNDARY_PLAN_TO_IMPL, omit_heading="§2 Next action")

    with pytest.raises(Exception) as exc_info:  # noqa: PT011 -- refusal path, exception class TBD by the implementer
        compose_handoff.compose(
            SLUG,
            tmp_path,
            BOUNDARY_PLAN_TO_IMPL,
            malformed,
            _changed_files_override=[],
            _wal_rows_override=[],
            _test_status_override=None,
        )
    assert "HANDOFF.md" in str(exc_info.value)

    # The CLI path: an on-disk malformed handoff is left untouched, exit != 0.
    (task_dir / "HANDOFF.md").write_text(malformed, encoding="utf-8")
    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL],
        readiness_result={"state": "ready", "reasons": []},
    )
    assert code == 3
    assert (task_dir / "HANDOFF.md").read_text(encoding="utf-8") == malformed


# --- (f) byte-size advisory --------------------------------------------------


def test_oversized_judgement_sections_report_a_byte_warning_but_still_write(
    tmp_path, monkeypatch, capsys
):
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    oversized = _render_existing_handoff(BOUNDARY_PLAN_TO_IMPL, s5="x" * 9000)

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        oversized,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )
    assert result["byte_count"] > 8192
    assert result["over_8kib"] is True

    (task_dir / "HANDOFF.md").write_text(oversized, encoding="utf-8")
    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL, "--json"],
        readiness_result={"state": "ready", "reasons": []},
    )
    assert code == 0  # advisory, not fatal -- the write still succeeds
    payload = json.loads(capsys.readouterr().out)
    assert payload["byte_count"] > 8192
    assert payload["over_8kib"] is True
    assert (task_dir / "HANDOFF.md").exists()


# --- purity: compose() is a function of its arguments only -------------------


class _FrozenClock:
    """A clock stand-in for `compose_handoff.datetime` -- freezes `.now(tz)` so
    two calls in the same test can never straddle a real second boundary and
    produce a spuriously different `composed_at` line."""

    @staticmethod
    def now(tz=None):
        from datetime import datetime as _real_datetime

        return _real_datetime(2026, 1, 1, 0, 0, 0, tzinfo=tz)


def _full_compose_context() -> compose_handoff.ComposeContext:
    """A `ComposeContext` with every world fact populated -- the shape `compose()`
    should need nothing beyond, once every world read moves out into `main()`."""
    return compose_handoff.ComposeContext(
        verdicts=[],
        readiness_verdict={"state": "ready", "reasons": []},
        branch="main",
        base_sha="deadbeef",
        worktree_path="/repo",
    )


def test_compose_returns_identical_output_across_repeated_calls_with_the_same_inputs(
    tmp_path, monkeypatch
):
    _setup_pipeline(tmp_path, _minimal_wip())
    monkeypatch.setattr(compose_handoff, "datetime", _FrozenClock)

    context = _full_compose_context()
    first = compose_handoff.compose(SLUG, tmp_path, BOUNDARY_PLAN_TO_IMPL, None, context=context)
    second = compose_handoff.compose(SLUG, tmp_path, BOUNDARY_PLAN_TO_IMPL, None, context=context)
    assert second == first


def test_compose_touches_no_filesystem_or_clock_when_context_is_fully_supplied(
    tmp_path, monkeypatch
):
    _setup_pipeline(tmp_path, _minimal_wip())

    def _boom(*_a, **_k):
        raise AssertionError("compose() must not touch the world")

    monkeypatch.setattr(Path, "iterdir", _boom)
    monkeypatch.setattr(Path, "glob", _boom)
    monkeypatch.setattr(Path, "stat", _boom)
    monkeypatch.setattr(time, "time", _boom)
    monkeypatch.setattr(compose_handoff, "reconcile", _boom)

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        context=_full_compose_context(),
    )
    assert result["text"]


# --- (g) readiness: blocked on an unstopped spawn ----------------------------


def test_blocks_on_unstopped_spawn(tmp_path, monkeypatch):
    verdict = compose_handoff.readiness(
        wal_rows=[_wal_start("agent-1")],
        git_status=[],
        step_files=[],
        force=False,
    )
    assert verdict["state"] == "blocked"
    assert "spawn-in-flight" in verdict["reasons"]

    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    (task_dir / "HANDOFF.md").write_text("PREVIOUS CONTENT MARKER", encoding="utf-8")

    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL],
        readiness_result={"state": "blocked", "reasons": ["spawn-in-flight"]},
    )
    assert code == 1
    assert (task_dir / "HANDOFF.md").read_text(encoding="utf-8") == "PREVIOUS CONTENT MARKER"


# --- (h) readiness: blocked on dirty step files ------------------------------


def test_blocks_on_dirty_step_files(tmp_path, monkeypatch):
    verdict = compose_handoff.readiness(
        wal_rows=[],
        git_status=["scripts/demo_retry_queue.py"],
        step_files=["scripts/demo_retry_queue.py"],
        force=False,
    )
    assert verdict["state"] == "blocked"
    assert "dirty-step-files" in verdict["reasons"]

    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    (task_dir / "HANDOFF.md").write_text("PREVIOUS CONTENT MARKER", encoding="utf-8")

    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL],
        readiness_result={"state": "blocked", "reasons": ["dirty-step-files"]},
    )
    assert code == 1
    assert (task_dir / "HANDOFF.md").read_text(encoding="utf-8") == "PREVIOUS CONTENT MARKER"


# --- (i) --force stamps overridden and records reasons in §1 ----------------


def test_force_stamps_overridden_and_records_reasons_in_state_section(tmp_path, monkeypatch):
    verdict = compose_handoff.readiness(
        wal_rows=[_wal_start("agent-1")],
        git_status=[],
        step_files=[],
        force=True,
    )
    assert verdict["state"] == "overridden"
    assert "spawn-in-flight" in verdict["reasons"]

    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL, "--force"],
        readiness_result={"state": "overridden", "reasons": ["spawn-in-flight"]},
    )
    assert code == 0
    text = (task_dir / "HANDOFF.md").read_text(encoding="utf-8")
    assert "readiness: overridden" in text
    assert "spawn-in-flight" in _extract_section(text, "§1 State")


# --- (j) readiness: clean when nothing fires ---------------------------------


def test_ready_when_no_conditions_fire(tmp_path, monkeypatch):
    verdict = compose_handoff.readiness(
        wal_rows=[_wal_start("agent-1"), _wal_stop("agent-1")],
        git_status=[],
        step_files=["scripts/unrelated.py"],
        force=False,
    )
    assert verdict["state"] == "ready"
    assert verdict["reasons"] == []

    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL],
        readiness_result={"state": "ready", "reasons": []},
    )
    assert code == 0
    assert "readiness: clean" in (task_dir / "HANDOFF.md").read_text(encoding="utf-8")


# --- readiness: fail closed when the WAL itself cannot be trusted -----------


@pytest.mark.parametrize(
    "unreadable_wal_rows",
    [
        pytest.param([], id="empty"),
        pytest.param([{"event_type": "agent_start", "agent_id": "agent-1"}], id="no-session-id"),
    ],
)
def test_blocks_with_wal_unreadable_reason_when_the_wal_cannot_be_trusted(
    tmp_path, monkeypatch, unreadable_wal_rows
):
    verdict = compose_handoff.readiness(
        wal_rows=unreadable_wal_rows,
        git_status=[],
        step_files=[],
        force=False,
    )
    assert verdict["state"] == "blocked"
    assert "wal-unreadable" in verdict["reasons"]

    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    (task_dir / "HANDOFF.md").write_text("PREVIOUS CONTENT MARKER", encoding="utf-8")

    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL],
        readiness_result={"state": "blocked", "reasons": ["wal-unreadable"]},
    )
    assert code == 1
    assert (task_dir / "HANDOFF.md").read_text(encoding="utf-8") == "PREVIOUS CONTENT MARKER"


def test_force_overrides_wal_unreadable_block_and_records_reason_in_state_section(
    tmp_path, monkeypatch
):
    verdict = compose_handoff.readiness(
        wal_rows=[],
        git_status=[],
        step_files=[],
        force=True,
    )
    assert verdict["state"] == "overridden"
    assert "wal-unreadable" in verdict["reasons"]

    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL, "--force"],
        readiness_result={"state": "overridden", "reasons": ["wal-unreadable"]},
    )
    assert code == 0
    text = (task_dir / "HANDOFF.md").read_text(encoding="utf-8")
    assert "readiness: overridden" in text
    assert "wal-unreadable" in _extract_section(text, "§1 State")


# --- (k) recent log mtime is advisory-only, never a readiness reason --------


def test_recent_log_mtime_is_advisory_only_and_never_blocks(tmp_path):
    # readiness() has no path for this condition at all -- it cannot promote
    # to Blocked under any input, since the third condition is not
    # mechanically decidable (no fixed path/schema exists for a detached-suite
    # done-file, so no gate can check for it).
    verdict = compose_handoff.readiness(
        wal_rows=[_wal_start("agent-1"), _wal_stop("agent-1")],
        git_status=[],
        step_files=[],
        force=False,
    )
    assert verdict["state"] == "ready"
    assert verdict["reasons"] == []

    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    log_dir = task_dir / "logs"
    log_dir.mkdir()
    log_path = log_dir / "step-1.log"  # id-citation-discipline:ignore
    log_path.write_text("running...\n", encoding="utf-8")

    fresh = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )
    assert "a test run may still be in progress" in _extract_section(fresh["text"], "§1 State")

    # Age the log past the 60s window -- the advisory note must disappear.
    old_mtime = 0
    os.utime(log_path, (old_mtime, old_mtime))
    stale = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )
    assert "a test run may still be in progress" not in _extract_section(stale["text"], "§1 State")


# --- reconciling against the branch's fork point, not just the working tree -


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _git_capture(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _init_repo_with_step_file(tmp_path: Path, *, commit_step_file: bool) -> Path:
    """A real throwaway git repo: `main` seeded with one commit, a pipeline
    branch forked from it, and a WIP.md claiming step 1 complete -- with its
    declared file either committed on the branch since the fork point (ground
    truth confirms it) or only written to the working tree (ground truth
    cannot confirm it). A quiescent WAL row is seeded too, so the readiness
    gate's own `wal-unreadable` fail-closed reason never masks the behaviour
    under test here."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    plan = (
        "### Step 1: Build the thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: src/thing.py\n"
        "**Done when**: it works\n"
    )
    wip = "# WIP\n\n## Progress\n\n- [x] Step 1: build the thing\n"  # id-citation-discipline:ignore
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task_dir / "WIP.md").write_text(wip, encoding="utf-8")

    state_dir = repo_root / ".ai-state"
    state_dir.mkdir()
    quiescent_wal = [
        {"event_type": "agent_start", "agent_id": "agent-1", "session_id": "s1"},
        {"event_type": "agent_stop", "agent_id": "agent-1", "session_id": "s1"},
    ]
    (state_dir / "observations.jsonl").write_text(
        "\n".join(json.dumps(row) for row in quiescent_wal) + "\n", encoding="utf-8"
    )

    (repo_root / "src").mkdir()
    (repo_root / "src" / "thing.py").write_text("# implementation\n", encoding="utf-8")
    if commit_step_file:
        _run_git(["add", "src/thing.py"], repo_root)
        _run_git(["commit", "-q", "-m", "implement thing"], repo_root)
    return repo_root


def test_committed_steps_since_the_fork_point_are_not_reported_as_disagreements(
    tmp_path, monkeypatch, capsys
):
    repo_root = _init_repo_with_step_file(tmp_path, commit_step_file=True)
    expected_base_sha = _git_capture(["merge-base", "HEAD", "main"], repo_root)
    monkeypatch.chdir(repo_root)

    code = compose_handoff.main(
        [
            SLUG,
            "--repo-root",
            str(repo_root),
            "--boundary",
            BOUNDARY_PLAN_TO_IMPL,
            "--dry-run",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["conflicts"] == []

    context = compose_handoff.gather(SLUG, repo_root, force=False)
    assert context.base_sha == expected_base_sha


def test_uncommitted_step_work_is_not_silently_accepted_as_complete(tmp_path, monkeypatch):
    repo_root = _init_repo_with_step_file(tmp_path, commit_step_file=False)
    monkeypatch.chdir(repo_root)

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    reported_as_mismatch = any(
        v.get("verdict") == "mismatch" or v.get("needs_mark") for v in context.verdicts
    )
    blocked_or_overridden = (context.readiness_verdict or {}).get("state") != "ready"
    assert reported_as_mismatch or blocked_or_overridden, (
        "an uncommitted step file must not be silently accepted as complete -- expected either "
        "a ground-truth mismatch in the reconciled verdicts or a blocked/overridden readiness "
        "state"
    )


# --- dirty_paths(): the real git-status adapter, not just its literal-list callers ---


def _seed_quiescent_wal(repo_root: Path) -> None:
    """A matched, session-scoped agent_start/agent_stop pair -- so the
    `wal-unreadable` fail-closed reason never masks the behaviour under test."""
    state_dir = repo_root / ".ai-state"
    state_dir.mkdir(exist_ok=True)
    quiescent_wal = [
        {"event_type": "agent_start", "agent_id": "agent-1", "session_id": "s1"},
        {"event_type": "agent_stop", "agent_id": "agent-1", "session_id": "s1"},
    ]
    (state_dir / "observations.jsonl").write_text(
        "\n".join(json.dumps(row) for row in quiescent_wal) + "\n", encoding="utf-8"
    )


def _write_pipeline_docs(repo_root: Path, plan: str, wip: str) -> Path:
    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task_dir / "WIP.md").write_text(wip, encoding="utf-8")
    return task_dir


def _repo_with_modified_tracked_file(tmp_path: Path) -> Path:
    """A single-branch git repo with exactly one tracked file, modified but
    uncommitted -- the historical single-dirty-file bug's exact shape (a
    leading-space porcelain status line whose first character a whole-output
    `.strip()` silently eats)."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    tracked = repo_root / "tracked.py"
    tracked.write_text("original\n", encoding="utf-8")
    _run_git(["add", "tracked.py"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    tracked.write_text("modified\n", encoding="utf-8")
    return repo_root


def test_dirty_paths_reports_a_single_modified_tracked_file(tmp_path):
    repo_root = _repo_with_modified_tracked_file(tmp_path)
    assert _handoff_readiness.dirty_paths(repo_root) == ["tracked.py"]


def test_dirty_paths_reports_rename_destination_not_source_alongside_untracked(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "old.py").write_text("content\n", encoding="utf-8")
    _run_git(["add", "old.py"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)

    _run_git(["mv", "old.py", "new.py"], repo_root)
    (repo_root / "untracked.py").write_text("new file\n", encoding="utf-8")

    paths = _handoff_readiness.dirty_paths(repo_root)
    assert "new.py" in paths
    assert "old.py" not in paths
    assert "untracked.py" in paths


def _find_porcelain_parse_helper():
    """The pure parsing core `dirty_paths()`'s I/O wrapper should delegate to,
    once the fix separates "run git" from "parse its output" -- polled by
    name since the implementer's fix (in parallel) owns the exact name."""
    for name in ("parse_porcelain", "_parse_porcelain", "parse_porcelain_z"):
        fn = getattr(_handoff_readiness, name, None)
        if fn is not None:
            return fn
    return None


@pytest.mark.skipif(
    _find_porcelain_parse_helper() is None,
    reason="_handoff_readiness.py exposes no pure porcelain-parsing helper yet",
)
def test_parses_unstripped_porcelain_text_into_repo_relative_paths():
    parse = _find_porcelain_parse_helper()
    # NUL-terminated `git status --porcelain -z` records: a modified file, an
    # untracked file, and a rename (new-path record followed by the bare
    # original-path record git emits as a second, unprefixed record).
    raw = "\0".join([" M a.py", "?? b.py", "R  new.py", "old.py"]) + "\0"
    assert parse(raw) == ["a.py", "b.py", "new.py"]


def test_dirty_step_file_blocks_main_and_writes_nothing(tmp_path, monkeypatch, capsys):
    repo_root = _repo_with_modified_tracked_file(tmp_path)
    plan = (
        "### Step 1: Build the thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: tracked.py\n"
        "**Done when**: it works\n"
    )
    wip = "# WIP\n\n## Progress\n\n- [ ] Step 1: build the thing\n"  # id-citation-discipline:ignore
    task_dir = _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    assert "dirty-step-files" in capsys.readouterr().err
    assert not (task_dir / "HANDOFF.md").exists()


# --- the dirty-step-files fallback chain when the current step names no Files -----


def test_falls_back_to_every_dirty_path_when_the_current_step_declares_no_files(
    tmp_path, monkeypatch, capsys
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    elsewhere = repo_root / "elsewhere.py"
    elsewhere.write_text("original\n", encoding="utf-8")
    _run_git(["add", "elsewhere.py"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    elsewhere.write_text("modified\n", encoding="utf-8")

    plan = (
        "### Step 1: Integration checkpoint\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Done when**: full suite green\n"
    )
    wip = "# WIP\n\n## Progress\n\n- [ ] Step 1: integration checkpoint\n"  # id-citation-discipline:ignore
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    assert "dirty-step-files" in capsys.readouterr().err


def test_dirty_path_under_ai_state_alone_does_not_trigger_the_fallback(
    tmp_path, monkeypatch, capsys
):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)

    plan = (
        "### Step 1: Integration checkpoint\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Done when**: full suite green\n"
    )
    wip = "# WIP\n\n## Progress\n\n- [ ] Step 1: integration checkpoint\n"  # id-citation-discipline:ignore
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    wal_path = repo_root / ".ai-state" / "observations.jsonl"
    _run_git(["add", ".ai-state/observations.jsonl"], repo_root)
    _run_git(["commit", "-q", "-m", "seed wal"], repo_root)
    # The only uncommitted path in the repo lives entirely under .ai-state/.
    with wal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event_type": "agent_start", "agent_id": "agent-2"}) + "\n")

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 0
    assert "dirty-step-files" not in capsys.readouterr().err


# --- an unreadable existing HANDOFF.md is a refusal, never a silent Absent --------


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores file permission bits; chmod 0o000 would not actually block the read",
)
def test_unreadable_existing_handoff_refuses_and_leaves_the_file_untouched(
    tmp_path, monkeypatch, capsys
):
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    handoff_path = task_dir / "HANDOFF.md"
    original_bytes = b"whatever prior content\n"
    handoff_path.write_bytes(original_bytes)
    handoff_path.chmod(0o000)
    try:
        code = _run_main(
            monkeypatch,
            tmp_path,
            ["--boundary", BOUNDARY_PLAN_TO_IMPL],
            readiness_result={"state": "ready", "reasons": []},
        )
        assert code != 0
        assert "HANDOFF.md" in capsys.readouterr().err
    finally:
        handoff_path.chmod(0o644)
    assert handoff_path.read_bytes() == original_bytes


def test_missing_handoff_composes_as_absent_via_main(tmp_path, monkeypatch):
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    assert not (task_dir / "HANDOFF.md").exists()

    code = _run_main(
        monkeypatch,
        tmp_path,
        ["--boundary", BOUNDARY_PLAN_TO_IMPL],
        readiness_result={"state": "ready", "reasons": []},
    )
    assert code == 0
    assert (task_dir / "HANDOFF.md").exists()


# --- dirty-step-files is a union of the three scope rules, not a tiered fallback --


def test_dirty_file_owned_by_a_completed_step_still_blocks(tmp_path, monkeypatch, capsys):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)

    # The completed step's file: committed once (ground truth confirms it),
    # then dirtied again -- the step stays verified-complete, but its file is
    # now uncommitted work the next window would inherit invisibly.
    completed_step_file = repo_root / "done_thing.py"
    completed_step_file.write_text("original\n", encoding="utf-8")
    # The current step's own file: committed and left untouched -- clean.
    current_step_file = repo_root / "clean_thing.py"
    current_step_file.write_text("clean\n", encoding="utf-8")
    _run_git(["add", "done_thing.py", "clean_thing.py"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    completed_step_file.write_text("modified\n", encoding="utf-8")

    plan = (
        "### Step 1: Build the done thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: done_thing.py\n"
        "**Done when**: it works\n\n"
        "### Step 2: Build the clean thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: clean_thing.py\n"
        "**Done when**: it works\n"
    )
    wip = (
        "# WIP\n\n## Progress\n\n"
        "- [x] Step 1: build the done thing\n"  # id-citation-discipline:ignore
        "- [ ] Step 2: build the clean thing\n"  # id-citation-discipline:ignore
    )
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    stderr = capsys.readouterr().err
    assert "dirty-step-files" in stderr
    assert "done_thing.py" in stderr


# --- _handoff_inputs.py's world-read functions, through the real adapters --------
#
# Every case below drives its target function through a real repo, a real
# task directory, or both -- never a hand-built verdict dict standing in for
# what the real read would have produced. Each assertion is on what the read's
# *result* changes about the composed output; mentally replacing the read with
# its fallback value (None, an empty tuple, the wrong verdict) must break the
# assertion, not merely change some untested internal shape.


def test_no_default_branch_or_remote_leaves_base_sha_unresolved(tmp_path):
    """`resolve_base_ref` must exhaust every fallback candidate and report
    unresolved -- not silently default to some other ref -- when neither
    `main` nor `master` exists locally and there is no remote at all."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "trunk"], repo_root)  # neither "main" nor "master"

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    context = compose_handoff.gather(SLUG, repo_root, force=False)
    assert context.base_sha == compose_handoff.UNKNOWN

    result = compose_handoff.compose(SLUG, repo_root, BOUNDARY_PLAN_TO_IMPL, None, context=context)
    assert compose_handoff.UNRESOLVED_BASE_ADVISORY in _extract_section(result["text"], "§1 State")


def test_remote_default_branch_named_neither_main_nor_master_still_resolves_base_sha(
    tmp_path,
):
    """`_base_ref_candidates` must read `refs/remotes/origin/HEAD` -- with the
    remote's default branch named neither `main` nor `master`, the static
    fallback list cannot resolve anything at all, so a real merge-base here
    can only come from that read succeeding."""
    bare = tmp_path / "upstream.git"
    _run_git(["init", "-q", "--bare", str(bare)], tmp_path)

    seed = tmp_path / "seed"
    seed.mkdir()
    _run_git(["init", "-q"], seed)
    _run_git(["config", "user.email", "test@example.com"], seed)
    _run_git(["config", "user.name", "Test User"], seed)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], seed)
    _run_git(["commit", "-q", "-m", "seed"], seed)
    _run_git(["branch", "-M", "trunk"], seed)
    _run_git(["remote", "add", "origin", str(bare)], seed)
    _run_git(["push", "-q", "origin", "trunk"], seed)
    _run_git(["symbolic-ref", "HEAD", "refs/heads/trunk"], bare)

    repo_root = tmp_path / "repo"
    _run_git(["clone", "-q", str(bare), str(repo_root)], tmp_path)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    expected_base_sha = _git_capture(["merge-base", "HEAD", "refs/remotes/origin/HEAD"], repo_root)
    assert expected_base_sha  # sanity: the real repo has a resolvable fork point

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    assert context.base_sha == expected_base_sha


def test_declared_files_unions_the_committed_and_uncommitted_halves(tmp_path, monkeypatch, capsys):
    """A step's declared `Files:` field can span a committed file and an
    uncommitted file at once -- this pins that the uncommitted half being
    dirty still triggers the block. It does NOT, on its own, discriminate a
    dropped union half: the trailing dirty-source catch-all sweeps in any
    dirty path regardless of step attribution, so `b.py` would appear in
    `stderr` here even if `declared_files` silently dropped its unchanged
    half. `test_declared_files_lead_with_the_committed_half_ahead_of_the_uncommitted_half`
    below is the one that actually kills that mutation, via ordering."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    (repo_root / "a.py").write_text("committed\n", encoding="utf-8")
    _run_git(["add", "a.py"], repo_root)
    _run_git(["commit", "-q", "-m", "commit a"], repo_root)
    (repo_root / "b.py").write_text("uncommitted\n", encoding="utf-8")  # untracked, dirty

    plan = (
        "### Step 1: Build both halves\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: a.py, b.py\n"
        "**Done when**: it works\n"
    )
    wip = (
        "# WIP\n\n## Progress\n\n- [ ] Step 1: build both halves\n"  # id-citation-discipline:ignore
    )
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    stderr = capsys.readouterr().err
    assert "dirty-step-files" in stderr
    assert "b.py" in stderr


def test_step_owned_scope_falls_back_to_the_union_of_every_unfinished_step(
    tmp_path, monkeypatch, capsys
):
    """The first unfinished step declares no `Files:` at all -- `_step_owned_paths`
    must widen to the union of every unfinished step's declared files, and the
    composed handoff must say the scope was widened, rather than silently
    narrowing to nothing."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    later = repo_root / "later_step.py"
    later.write_text("original\n", encoding="utf-8")
    _run_git(["add", "later_step.py"], repo_root)
    _run_git(["commit", "-q", "-m", "seed later_step"], repo_root)
    later.write_text("modified\n", encoding="utf-8")

    plan = (
        "### Step 1: Integration checkpoint\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Done when**: full suite green\n\n"
        "### Step 2: Build the later thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: later_step.py, pending_file.py\n"
        "**Done when**: it works\n"
    )
    wip = (
        "# WIP\n\n## Progress\n\n"
        "- [ ] Step 1: integration checkpoint\n"  # id-citation-discipline:ignore
        "- [ ] Step 2: build the later thing\n"  # id-citation-discipline:ignore
    )
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    stderr = capsys.readouterr().err
    assert "dirty-step-files" in stderr
    assert "later_step.py" in stderr

    # Clean the dirty file -- Step 2 stays unfinished (pending_file.py never  # id-citation-discipline:ignore
    # lands), so the widened scope persists and the composed handoff must
    # name it, rather than silently reverting to the empty current step.
    _run_git(["checkout", "-q", "--", "later_step.py"], repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 0
    task_dir = repo_root / ".ai-work" / SLUG
    text = (task_dir / "HANDOFF.md").read_text(encoding="utf-8")
    assert "union of every unfinished step's files" in _extract_section(text, "§1 State")


def test_first_unfinished_steps_own_files_lead_the_refusal_not_a_completed_steps(
    tmp_path, monkeypatch, capsys
):
    """`first_unfinished` must skip a step ground truth already confirmed and
    hand `_step_owned_paths` the next one -- named first in the refusal ahead
    of an unrelated dirty path, per that function's own documented invariant,
    however git status happens to order the raw dirty paths alphabetically."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    # Step 1's file: committed since the fork, clean -- verified-complete.  # id-citation-discipline:ignore
    (repo_root / "a.py").write_text("done\n", encoding="utf-8")
    _run_git(["add", "a.py"], repo_root)
    _run_git(["commit", "-q", "-m", "commit a"], repo_root)

    # Step 2's own dirty file sorts AFTER the unrelated dirty file below, so  # id-citation-discipline:ignore
    # leading-first order in the refusal is only explained by step ownership
    # -- never by git status's own alphabetical listing.
    (repo_root / "zzz_owned.py").write_text("new\n", encoding="utf-8")
    (repo_root / "aaa_other.py").write_text("new\n", encoding="utf-8")

    plan = (
        "### Step 1: Finish the first thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: a.py\n"
        "**Done when**: it works\n\n"
        "### Step 2: Build the second thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: zzz_owned.py\n"
        "**Done when**: it works\n"
    )
    wip = (
        "# WIP\n\n## Progress\n\n"
        "- [ ] Step 1: finish the first thing\n"  # id-citation-discipline:ignore
        "- [ ] Step 2: build the second thing\n"  # id-citation-discipline:ignore
    )
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    stderr = capsys.readouterr().err
    assert "dirty-step-files" in stderr
    assert stderr.index("zzz_owned.py") < stderr.index("aaa_other.py"), (
        "the unfinished step's own file must lead the refusal, not trail behind "
        "an unrelated dirty path in alphabetical order"
    )


def test_artifact_names_lists_only_markdown_files_sorted(tmp_path):
    """`artifact_names` must filter to `.md` files, exclude directories even
    when one is named like a markdown file, and sort the result -- the §1
    State line is the only place an operator sees what is actually on disk."""
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    (task_dir / "NOTES.txt").write_text("not markdown\n", encoding="utf-8")
    (task_dir / "WEIRD.md").mkdir()  # a directory, not a file -- must be excluded
    (task_dir / "logs").mkdir()
    (task_dir / "logs" / "nested.md").write_text("must not count\n", encoding="utf-8")
    (task_dir / "ZZZ_NOTES.md").write_text("notes\n", encoding="utf-8")

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )

    state = _extract_section(result["text"], "§1 State")
    assert "Artifacts present: `WIP.md`, `ZZZ_NOTES.md`." in state
    assert "NOTES.txt" not in state
    assert "WEIRD.md`" not in state
    assert "nested.md" not in state


def test_recent_log_note_names_the_first_log_inside_the_window_not_the_first_by_name(
    tmp_path,
):
    """`recent_log` must return the first log file *inside the advisory
    window*, not simply the first by sorted filename -- an alphabetically
    earlier but stale log must never suppress a genuinely fresh one."""
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    log_dir = task_dir / "logs"
    log_dir.mkdir()
    stale = log_dir / "step-1.log"  # id-citation-discipline:ignore
    fresh = log_dir / "step-2.log"  # id-citation-discipline:ignore
    stale.write_text("old run\n", encoding="utf-8")
    fresh.write_text("new run\n", encoding="utf-8")
    old_mtime = 0
    os.utime(stale, (old_mtime, old_mtime))  # sorts first by name, ages out by mtime

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )

    state = _extract_section(result["text"], "§1 State")
    assert "step-2.log" in state
    assert "step-1.log" not in state


def test_recent_log_note_reports_the_logs_actual_age_in_seconds(tmp_path, monkeypatch):
    """The advisory's age is the log's real seconds-since-mtime, computed
    against the passed-in clock -- not a placeholder and not off by a whole
    window's width."""
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    log_dir = task_dir / "logs"
    log_dir.mkdir()
    log_path = log_dir / "step-1.log"  # id-citation-discipline:ignore
    log_path.write_text("running...\n", encoding="utf-8")
    fixed_now = 2_000_000_000.0
    os.utime(log_path, (fixed_now - 37, fixed_now - 37))
    monkeypatch.setattr(time, "time", lambda: fixed_now)

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )

    state = _extract_section(result["text"], "§1 State")
    assert "`step-1.log` changed 37s ago" in state  # id-citation-discipline:ignore


def test_master_only_repo_resolves_base_sha_via_the_static_fallback(tmp_path):
    """No `main` branch and no remote at all -- the static fallback list must
    still include `master`, or resolution has nothing left to try and reports
    unresolved instead of finding the real fork point."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "master"], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    expected_base_sha = _git_capture(["merge-base", "HEAD", "master"], repo_root)
    assert expected_base_sha  # sanity: the real repo has a resolvable fork point

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    assert context.base_sha == expected_base_sha


def test_origin_tracking_branch_is_preferred_over_a_diverged_bare_branch_of_the_same_name(
    tmp_path,
):
    """When no `refs/remotes/origin/HEAD` exists at all (a plain `fetch`, never
    a `clone`), the static fallback list must still try `origin/main` before
    the bare `main` -- a diverged local `main` must never win over the
    remote-tracking branch of the same name."""
    bare = tmp_path / "upstream.git"
    _run_git(["init", "-q", "--bare", str(bare)], tmp_path)

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed A"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    seed_a = _git_capture(["rev-parse", "HEAD"], repo_root)

    (repo_root / "b.txt").write_text("b\n", encoding="utf-8")
    _run_git(["add", "b.txt"], repo_root)
    _run_git(["commit", "-q", "-m", "seed B"], repo_root)
    seed_b = _git_capture(["rev-parse", "HEAD"], repo_root)

    _run_git(["remote", "add", "origin", str(bare)], repo_root)
    _run_git(["push", "-q", "origin", "main"], repo_root)
    _run_git(["fetch", "-q", "origin"], repo_root)  # populates origin/main, never origin/HEAD

    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)
    (repo_root / "c.txt").write_text("c\n", encoding="utf-8")
    _run_git(["add", "c.txt"], repo_root)
    _run_git(["commit", "-q", "-m", "commit C"], repo_root)
    # Diverge the local branch backward -- only safe once it is no longer checked out.
    _run_git(["branch", "-f", "main", seed_a], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    assert context.base_sha == seed_b
    assert context.base_sha != seed_a


def test_declared_files_lead_with_the_committed_half_ahead_of_the_uncommitted_half(
    tmp_path, monkeypatch, capsys
):
    """`declared_files` concatenates the committed half first -- swapping the
    concatenation order must be observable in which path leads the refusal,
    independent of git status's own alphabetical ordering of the two paths."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    # Committed-then-redirtied, named to sort AFTER the untracked file below --
    # so leading-first order can only come from the changed/unchanged split.
    changed = repo_root / "zzz_changed.py"
    changed.write_text("committed\n", encoding="utf-8")
    _run_git(["add", "zzz_changed.py"], repo_root)
    _run_git(["commit", "-q", "-m", "commit zzz_changed"], repo_root)
    changed.write_text("modified\n", encoding="utf-8")
    # Never committed at all -- sorts first alphabetically and by git status.
    (repo_root / "aaa_unchanged.py").write_text("new\n", encoding="utf-8")

    plan = (
        "### Step 1: Build both halves\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: zzz_changed.py, aaa_unchanged.py\n"
        "**Done when**: it works\n"
    )
    wip = (
        "# WIP\n\n## Progress\n\n- [ ] Step 1: build both halves\n"  # id-citation-discipline:ignore
    )
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    stderr = capsys.readouterr().err
    assert stderr.index("zzz_changed.py") < stderr.index("aaa_unchanged.py"), (
        "the committed-then-redirtied half must lead, matching declared_files' "
        "changed-before-unchanged concatenation order"
    )


def test_step_owned_scope_reports_dirty_source_advisory_when_no_unfinished_step_has_files(
    tmp_path,
    monkeypatch,
):
    """When no unfinished step declares `Files:` at all, `_step_owned_paths`
    must fall all the way through to the dirty-source rule and the composed
    handoff must name that widened scope explicitly."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    plan = (
        "### Step 1: Integration checkpoint\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Done when**: full suite green\n"
    )
    wip = "# WIP\n\n## Progress\n\n- [ ] Step 1: integration checkpoint\n"  # id-citation-discipline:ignore
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 0
    task_dir = repo_root / ".ai-work" / SLUG
    text = (task_dir / "HANDOFF.md").read_text(encoding="utf-8")
    assert "no step-owned paths to lead with" in _extract_section(text, "§1 State")


def test_main_only_repo_resolves_base_sha_via_the_static_fallback(tmp_path):
    """No `master` branch and no remote at all -- the static fallback list
    must still include bare `main`, distinctly from `master` (covered by the
    sibling master-only case) and from `origin/main` (covered by the
    origin-preference case)."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    expected_base_sha = _git_capture(["merge-base", "HEAD", "main"], repo_root)
    assert expected_base_sha  # sanity: the real repo has a resolvable fork point

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    assert context.base_sha == expected_base_sha


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores directory permission bits; chmod 0o000 would not actually block the read",
)
def test_recent_log_returns_no_advisory_when_the_logs_directory_cannot_be_listed(tmp_path):
    """An unreadable `logs/` directory is a no-answer, not a crash -- the
    advisory silently disappears rather than raising through `compose()`."""
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    log_dir = task_dir / "logs"
    log_dir.mkdir()
    (log_dir / "step-1.log").write_text("log\n", encoding="utf-8")  # id-citation-discipline:ignore
    log_dir.chmod(0o000)
    try:
        result = compose_handoff.compose(
            SLUG,
            tmp_path,
            BOUNDARY_PLAN_TO_IMPL,
            None,
            _changed_files_override=[],
            _wal_rows_override=[],
            _test_status_override=None,
        )
    finally:
        log_dir.chmod(0o755)

    assert "a test run may still be in progress" not in _extract_section(result["text"], "§1 State")


def test_origin_head_branch_wins_over_a_working_fallback_candidate(tmp_path):
    """When `refs/remotes/origin/HEAD` resolves, `_base_ref_candidates` must
    return early with it -- never falling through to the static fallback list
    -- even when a fallback candidate (`main`) would also resolve, just to a
    different, earlier commit."""
    bare = tmp_path / "upstream.git"
    _run_git(["init", "-q", "--bare", str(bare)], tmp_path)

    seed = tmp_path / "seed"
    seed.mkdir()
    _run_git(["init", "-q"], seed)
    _run_git(["config", "user.email", "test@example.com"], seed)
    _run_git(["config", "user.name", "Test User"], seed)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], seed)
    _run_git(["commit", "-q", "-m", "seed A"], seed)
    _run_git(["branch", "-M", "trunk"], seed)

    (seed / "b.txt").write_text("b\n", encoding="utf-8")
    _run_git(["add", "b.txt"], seed)
    _run_git(["commit", "-q", "-m", "seed B"], seed)
    seed_b = _git_capture(["rev-parse", "HEAD"], seed)

    _run_git(["remote", "add", "origin", str(bare)], seed)
    _run_git(["push", "-q", "origin", "trunk"], seed)
    _run_git(["symbolic-ref", "HEAD", "refs/heads/trunk"], bare)

    repo_root = tmp_path / "repo"
    _run_git(["clone", "-q", str(bare), str(repo_root)], tmp_path)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    # A local `main` that ALSO resolves -- but to the earlier commit, so the
    # two candidates disagree and whichever wins is directly observable.
    seed_a = _git_capture(["rev-parse", "HEAD~1"], repo_root)
    _run_git(["branch", "main", seed_a], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)
    (repo_root / "c.txt").write_text("c\n", encoding="utf-8")
    _run_git(["add", "c.txt"], repo_root)
    _run_git(["commit", "-q", "-m", "commit C"], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    assert context.base_sha == seed_b  # via origin/HEAD -> trunk
    assert context.base_sha != seed_a  # NOT via the also-working `main` fallback


def test_origin_head_absent_falls_through_to_the_static_fallback(tmp_path):
    """The companion case: with no `refs/remotes/origin/HEAD` at all (a plain
    local repo, never cloned), resolution must still succeed via the static
    fallback list -- the early-return branch is not the only path to an
    answer."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)
    (repo_root / "c.txt").write_text("c\n", encoding="utf-8")
    _run_git(["add", "c.txt"], repo_root)
    _run_git(["commit", "-q", "-m", "commit C"], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    expected_base_sha = _git_capture(["merge-base", "HEAD", "main"], repo_root)
    assert expected_base_sha

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    assert context.base_sha == expected_base_sha


def test_step_owned_union_deduplicates_and_sorts_across_multiple_unfinished_steps(
    tmp_path, monkeypatch, capsys
):
    """The union-of-unfinished-steps scope must de-duplicate a file declared
    by more than one step and present the result sorted -- not a naive
    concatenation that could repeat a path or leave it in declaration order."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    # All three declared files stay untracked -- never committed -- so every
    # step below stays "pending" (unfinished) regardless of the WIP checkbox.
    (repo_root / "zzz_two.py").write_text("new\n", encoding="utf-8")
    (repo_root / "mmm_shared.py").write_text("new\n", encoding="utf-8")
    (repo_root / "aaa_three.py").write_text("new\n", encoding="utf-8")

    plan = (
        "### Step 1: Integration checkpoint\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Done when**: full suite green\n\n"
        "### Step 2: Build the second thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: mmm_shared.py, zzz_two.py\n"
        "**Done when**: it works\n\n"
        "### Step 3: Build the third thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: aaa_three.py, mmm_shared.py\n"
        "**Done when**: it works\n"
    )
    wip = (
        "# WIP\n\n## Progress\n\n"
        "- [ ] Step 1: integration checkpoint\n"  # id-citation-discipline:ignore
        "- [ ] Step 2: build the second thing\n"  # id-citation-discipline:ignore
        "- [ ] Step 3: build the third thing\n"  # id-citation-discipline:ignore
    )
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    stderr = capsys.readouterr().err
    assert stderr.count("mmm_shared.py") == 1, "a file declared by two steps must appear once"
    assert (
        stderr.index("aaa_three.py") < stderr.index("mmm_shared.py") < stderr.index("zzz_two.py")
    ), "the union must be reported sorted, not in step-declaration order"


def test_step_owned_union_excludes_a_verified_complete_steps_files(tmp_path, monkeypatch, capsys):
    """The union-of-unfinished-steps scope must exclude a step ground truth
    already confirmed -- even though its file is also dirty and would
    otherwise be swept in by the trailing dirty-source catch-all regardless,
    a wrongly-included verified-complete step's file would LEAD the refusal
    instead of trailing behind the genuinely unfinished step's own file."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "main"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    # Step 1's file: committed since the fork, then re-dirtied -- stays  # id-citation-discipline:ignore
    # verified-complete (ground truth still sees it as "changed"), but its
    # working-tree state is dirty, so the trailing catch-all alone would mask
    # a union bug that wrongly includes it.
    complete_file = repo_root / "aaa_complete.py"
    complete_file.write_text("done\n", encoding="utf-8")
    _run_git(["add", "aaa_complete.py"], repo_root)
    _run_git(["commit", "-q", "-m", "commit aaa_complete"], repo_root)
    complete_file.write_text("done again\n", encoding="utf-8")

    # Step 3's own dirty file, alphabetically AFTER Step 1's -- so leading  # id-citation-discipline:ignore
    # order can only come from correct union membership, never from git
    # status's own alphabetical listing.
    (repo_root / "zzz_unfinished.py").write_text("new\n", encoding="utf-8")

    plan = (
        "### Step 1: Finish the complete thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: aaa_complete.py\n"
        "**Done when**: it works\n\n"
        "### Step 2: Integration checkpoint\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Done when**: full suite green\n\n"
        "### Step 3: Build the unfinished thing\n"  # id-citation-discipline:ignore
        "**Assignee**: implementer\n"
        "**Files**: zzz_unfinished.py\n"
        "**Done when**: it works\n"
    )
    wip = (
        "# WIP\n\n## Progress\n\n"
        "- [ ] Step 1: finish the complete thing\n"  # id-citation-discipline:ignore
        "- [ ] Step 2: integration checkpoint\n"  # id-citation-discipline:ignore
        "- [ ] Step 3: build the unfinished thing\n"  # id-citation-discipline:ignore
    )
    _write_pipeline_docs(repo_root, plan, wip)
    _seed_quiescent_wal(repo_root)

    monkeypatch.chdir(repo_root)
    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo_root), "--boundary", BOUNDARY_PLAN_TO_IMPL]
    )
    assert code == 1
    stderr = capsys.readouterr().err
    assert stderr.index("zzz_unfinished.py") < stderr.index("aaa_complete.py"), (
        "the genuinely unfinished step's file must lead; a verified-complete "
        "step's file must trail via the dirty-source catch-all, never the union"
    )


def test_recent_log_boundary_at_exactly_the_window_width_is_not_recent(tmp_path, monkeypatch):
    """The advisory window is a strict `<`, not `<=` -- a log aged exactly at
    the window's width must already be treated as stale, not recent."""
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    log_dir = task_dir / "logs"
    log_dir.mkdir()
    log_path = log_dir / "step-1.log"  # id-citation-discipline:ignore
    log_path.write_text("running...\n", encoding="utf-8")
    fixed_now = 2_000_000_000.0
    os.utime(log_path, (fixed_now - 60, fixed_now - 60))  # exactly the window's width, in seconds
    monkeypatch.setattr(time, "time", lambda: fixed_now)

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )

    assert "a test run may still be in progress" not in _extract_section(result["text"], "§1 State")


def test_dangling_origin_head_falls_through_to_the_short_branch_name(tmp_path):
    """A `refs/remotes/origin/HEAD` pointing at a remote-tracking ref that was
    never fetched (or has since been deleted) must fall through to the bare
    short branch name -- `git symbolic-ref` never validates its target
    exists, so the exact ref it names can be unresolvable while the plain
    name still is. This is the one real-adapter path where the second
    `_base_ref_candidates` tuple element is actually consulted, not dead
    code -- proving `ref.rsplit("/", 1)[-1]` computes the right short name."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    _run_git(["branch", "-M", "ghost"], repo_root)
    _run_git(["checkout", "-q", "-b", "worktree-demo"], repo_root)

    _run_git(["symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/ghost"], repo_root)

    task_dir = repo_root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(_minimal_wip(), encoding="utf-8")

    expected_base_sha = _git_capture(["merge-base", "HEAD", "ghost"], repo_root)
    assert expected_base_sha  # sanity: the bare local branch resolves

    context = compose_handoff.gather(SLUG, repo_root, force=False)

    assert context.base_sha == expected_base_sha


def test_recent_log_skips_a_dangling_symlink_and_reports_the_real_log_behind_it(
    tmp_path, monkeypatch
):
    """A dangling symlink among the raw logs must not abort the scan -- its
    name sorts first and `Path.glob` lists it, but `.stat()` on a broken
    symlink raises `FileNotFoundError` (an `OSError` subclass). The loop must
    continue past it to the real log behind it, not stop the search there."""
    task_dir = _setup_pipeline(tmp_path, _minimal_wip())
    log_dir = task_dir / "logs"
    log_dir.mkdir()
    real_log = log_dir / "step-2.log"  # id-citation-discipline:ignore
    real_log.write_text("running...\n", encoding="utf-8")
    (log_dir / "step-1.log").symlink_to(
        log_dir / "does-not-exist.log"
    )  # id-citation-discipline:ignore
    fixed_now = real_log.stat().st_mtime
    monkeypatch.setattr(time, "time", lambda: fixed_now)

    result = compose_handoff.compose(
        SLUG,
        tmp_path,
        BOUNDARY_PLAN_TO_IMPL,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override=None,
    )

    state = _extract_section(result["text"], "§1 State")
    assert "`step-2.log` changed 0s ago" in state
    assert "step-1.log" not in state


# --- the next-action picker skips a file-less `unknown` step ----------------
#
# A step reconciled to `unknown` means "claimed complete, no attributable
# ground truth" -- it is not actionable, only verifiable. The picker must
# never name it as the next action while later work is still actionable, and
# must surface it separately as human verification owed rather than dropping
# it silently.


def _verdict(step: str, verdict: str, **extra) -> dict:
    """A minimal verdict dict -- just the fields the next-action picker reads."""
    return {"step": step, "verdict": verdict, **extra}


def test_skips_the_unknown_step_and_lists_it_as_owed_verification_alongside_the_mismatch():
    verdicts = [
        _verdict("Step 1", "verified-complete"),  # id-citation-discipline:ignore
        _verdict("Step 2", "unknown"),  # id-citation-discipline:ignore
        _verdict("Step 3", "verified-complete"),  # id-citation-discipline:ignore
        _verdict("Step 4", "mismatch"),  # id-citation-discipline:ignore
    ]
    text = compose_handoff._render_next_action(verdicts)
    assert text.startswith("`Step 4`"), (  # id-citation-discipline:ignore
        "the file-less unknown step must never be named as next action while a "
        "mismatch step is still actionable"
    )
    assert "Step 2" in text, "the unknown step must still be named"  # id-citation-discipline:ignore
    assert re.search(r"verif", text, re.IGNORECASE), (
        "the unknown step must read as verification owed, not as an ordinary next action"
    )


def test_falls_back_to_the_first_unknown_when_nothing_else_is_actionable():
    verdicts = [
        _verdict("Step 1", "verified-complete"),  # id-citation-discipline:ignore
        _verdict("Step 2", "unknown"),  # id-citation-discipline:ignore
        _verdict("Step 3", "unknown"),  # id-citation-discipline:ignore
    ]
    text = compose_handoff._render_next_action(verdicts)
    assert "Step 2" in text  # id-citation-discipline:ignore
    assert re.search(r"verif", text, re.IGNORECASE)


def test_reports_the_phase_next_move_when_every_step_is_verified_complete():
    verdicts = [
        _verdict("Step 1", "verified-complete"),  # id-citation-discipline:ignore
        _verdict("Step 2", "verified-complete"),  # id-citation-discipline:ignore
    ]
    text = compose_handoff._render_next_action(verdicts)
    assert "verified-complete against ground truth" in text
    assert "Step 1" not in text  # id-citation-discipline:ignore
    assert "Step 2" not in text  # id-citation-discipline:ignore


def test_default_boundary_shares_the_picker_and_skips_an_unknown_step():
    verdicts = [
        _verdict("Step 1", "verified-complete"),  # id-citation-discipline:ignore
        _verdict("Step 2", "unknown"),  # id-citation-discipline:ignore
        _verdict("Step 3", "mismatch"),  # id-citation-discipline:ignore
    ]
    boundary = compose_handoff._default_boundary(verdicts)
    assert boundary == f"{compose_handoff.MID_PHASE_PREFIX}Step 3"  # id-citation-discipline:ignore


def test_default_boundary_falls_back_to_the_first_unknown_when_it_is_all_that_is_left():
    verdicts = [
        _verdict("Step 1", "verified-complete"),  # id-citation-discipline:ignore
        _verdict("Step 2", "unknown"),  # id-citation-discipline:ignore
    ]
    boundary = compose_handoff._default_boundary(verdicts)
    assert boundary == f"{compose_handoff.MID_PHASE_PREFIX}Step 2"  # id-citation-discipline:ignore


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
