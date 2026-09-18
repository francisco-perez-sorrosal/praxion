"""Tests for compose_handoff -- the handoff composer and its readiness gate.

Hermetic: pipelines are built under ``tmp_path``; the reconciler is driven
hermetically through a WIP.md with no checklist lines (reconcile() then
returns [] before touching git/WAL/test-status) or through compose()'s own
``_*_override`` pass-through kwargs, mirroring reconcile_pipeline_state.py's
own hooks. Do not read compose_handoff.py -- it does not exist yet; this file
is expected to fail at collection with ModuleNotFoundError (RED) until the
paired implementation step lands.

Run: ``pytest scripts/test_compose_handoff.py`` (or the module directly).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

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
    import os

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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
