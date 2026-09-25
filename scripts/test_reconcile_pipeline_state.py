"""Tests for reconcile_pipeline_state — verdict state machine + gate-liveness canary.

Hermetic: the three external reads (git diff, the WAL, the test status) are
injected via reconcile()'s ``_*_override`` hooks, so no real git repo is needed.
WIP.md / IMPLEMENTATION_PLAN.md are written into a tmp_path .ai-work/<slug>/ dir.

Run: ``python3 scripts/test_reconcile_pipeline_state.py`` or ``pytest``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import mutation_sensor as ms  # noqa: E402
import reconcile_pipeline_state as rps  # noqa: E402

SLUG = "demo-task"


def _setup(tmp_path: Path, wip: str, plan: str | None = None) -> Path:
    """Create .ai-work/<slug>/{WIP,IMPLEMENTATION_PLAN}.md under tmp_path."""
    task_dir = tmp_path / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(wip, encoding="utf-8")
    if plan is not None:
        (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    return tmp_path


def _verdict_for(verdicts: list[dict], step: str) -> dict:
    return next(v for v in verdicts if v["step"] == step)


def _wal_write(agent_id: str, agent_type: str, path: str, ts: str) -> dict:
    return {
        "event_type": "tool_use",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "file_paths": [path],
        "timestamp": ts,
    }


def _wal_stop(agent_id: str) -> dict:
    return {"event_type": "agent_stop", "agent_id": agent_id}


PLAN_ONE_STEP = """## Steps

### Step 1: Build the thing
**Assignee**: implementer
**Files**: src/foo.py
**Done when**: it works
"""

PLAN_TWO_FILES = """### Step 1: Build the thing
**Files**: src/a.py, src/b.py
"""


# --- genuine completion confirmed from ground truth ------------------------


def test_verified_complete_when_files_changed_and_tests_green(tmp_path):
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"


# --- THE CANARY — a false [COMPLETE] must be flagged ------------------------


def test_canary_complete_but_files_unchanged_is_flagged(tmp_path):
    """GATE-LIVENESS CANARY (golden bad-case).

    A step claims [COMPLETE] but its Files show zero git change — the exact
    truncation signature. The reconciler MUST NOT return verified-complete.

    Proof it bites (mutation-verified): replace _classify_step's
    verified-complete guard condition `changed and not unchanged and not
    tests_red` with an unconditional `if True:` (i.e. trust the checkbox), and
    this test goes red — the false [COMPLETE] claim then returns
    verified-complete. (Mutating only the `not unchanged` term does NOT bite,
    because `changed` is already empty here.)
    """
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=[],  # nothing changed in git
        _wal_rows_override=[],
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"] != "verified-complete"
    assert v["verdict"] == "mismatch"
    assert "src/foo.py" in v["resume_scope"]


def test_canary_red_tests_block_verified_complete(tmp_path):
    """A [COMPLETE] step whose files changed but suite is red → mismatch."""
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],
        _test_status_override="red",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "mismatch"


# --- partial localizes to the last write -----------------------------------


def test_partial_localizes_remainder(tmp_path):
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_TWO_FILES)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/a.py"],  # a done, b not
        _wal_rows_override=[
            _wal_write("ag1", "praxion:implementer", "/repo/src/a.py", "2026-06-22T19:00:00Z"),
            _wal_stop("ag1"),
        ],
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"].startswith("partial@")
    assert v["resume_scope"] == ["src/b.py"]
    assert v["tier2"]["agent_stop_seen"] is True


# --- Tier-1 overrides Tier-2 loss (dropped WAL lines) ----------------------


def test_tier1_overrides_wal_loss(tmp_path):
    """Files changed + tests green, but the WAL has no matching rows → still
    verified-complete. A dropped WAL line costs a hint, never a Tier-1 verdict."""
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],  # WAL dropped everything
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"] == "verified-complete"
    assert v["tier2"]["correlated_agent_ids"] == []


# --- ambiguous correlation (no declared Files) degrades to unknown ---------


def test_complete_without_declared_files_is_unknown(tmp_path):
    """A [COMPLETE] step with no Files: cannot be tied to ground truth → unknown,
    never a guessed verified-complete."""
    root = _setup(tmp_path, "- [x] Step 1: build\n")  # no plan, no Files
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/something.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "unknown"


# --- in-flight and pending ----------------------------------------------------


def test_in_flight_when_changed_but_no_stop(tmp_path):
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_TWO_FILES)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/a.py"],
        _wal_rows_override=[
            _wal_write("ag1", "praxion:implementer", "/repo/src/a.py", "2026-06-22T19:00:00Z"),
        ],  # tool_use but NO agent_stop
        _test_status_override="absent",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "in-flight"


def test_pending_when_nothing_changed(tmp_path):
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_TWO_FILES)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override="absent",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "pending"


# --- read-only — reconcile() mutates nothing -------------------------------


def test_reconcile_is_side_effect_free(tmp_path):
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after, "reconcile() must not write or modify any file"


# --- exit-code precedence ----------------------------------------------------


def test_exit_codes():
    assert rps._exit_code([{"verdict": "verified-complete"}]) == 0
    assert rps._exit_code([{"verdict": "pending"}]) == 0
    assert rps._exit_code([{"verdict": "mismatch"}]) == 1
    assert rps._exit_code([{"verdict": "partial@src/x.py"}]) == 1
    assert rps._exit_code([{"verdict": "in-flight"}]) == 1
    assert rps._exit_code([{"verdict": "unknown"}]) == 2
    # unknown outranks recovery-needed
    assert rps._exit_code([{"verdict": "mismatch"}, {"verdict": "unknown"}]) == 2


# --- parsing helpers ----------------------------------------------------------


def test_parse_wip_claims(tmp_path):
    wip = (
        "- [x] Step 1: done **[COMPLETE]**\n"
        "- [ ] Step 2: pending\n"
        "- [ ] Step 3 (implementer) [IN-PROGRESS]: working\n"
    )
    p = tmp_path / "WIP.md"
    p.write_text(wip, encoding="utf-8")
    claims = rps._parse_wip_steps(p)
    assert claims == {"Step 1": "COMPLETE", "Step 2": "PENDING", "Step 3": "IN-PROGRESS"}


def test_scan_step_files(tmp_path):
    p = tmp_path / "IMPLEMENTATION_PLAN.md"
    p.write_text(PLAN_TWO_FILES, encoding="utf-8")
    assert rps._scan_step_files(p) == {"Step 1": ["src/a.py", "src/b.py"]}


def test_missing_wip_returns_empty(tmp_path):
    assert rps.reconcile("nonexistent", tmp_path, None, _changed_files_override=[]) == []


def test_path_match_boundary_aware():
    assert rps._path_match("src/foo.py", "/repo/src/foo.py")
    assert rps._path_match("src/foo.py", "src/foo.py")
    assert not rps._path_match("src/foo.py", "/repo/other/bar.py")


def test_path_match_expands_globs():
    # git emits concrete paths; a glob in Files: must still match (no false mismatch)
    assert rps._path_match("scenarios/*.yaml", "pkg/scenarios/foo.yaml")
    assert rps._path_match("src/evals/scenarios/*.yaml", "src/evals/scenarios/contradiction.yaml")
    assert not rps._path_match("scenarios/*.yaml", "pkg/other/foo.py")


# --- ground truth drives verified-complete, not the checkbox ------------------


def test_verified_complete_overrides_unmarked_checkbox(tmp_path):
    """Died-before-checkbox: files all changed + tests green but WIP still '- [ ]'
    → verified-complete with needs_mark=True (resume auto-marks, does not respawn)."""
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[_wal_stop("ag1")],
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"] == "verified-complete"
    assert v["needs_mark"] is True


# --- Bug B: conflicting step claims across workstreams → AMBIGUOUS -------------


def test_conflicting_wip_claims_mark_ambiguous(tmp_path):
    wip = (
        "## WS-1\n- [x] Step 1: done in ws1 **[COMPLETE]**\n"
        "## WS-2\n- [ ] Step 1: not done in ws2\n"
    )
    p = tmp_path / "WIP.md"
    p.write_text(wip, encoding="utf-8")
    claims = rps._parse_wip_steps(p)
    assert claims["Step 1"] == "AMBIGUOUS"


def test_ambiguous_claim_never_false_mismatch(tmp_path):
    """An AMBIGUOUS step with no confirming git change degrades safely, never to
    a mismatch (which would wrongly auto-resume)."""
    wip = "## WS-1\n- [x] Step 1 **[COMPLETE]**\n## WS-2\n- [ ] Step 1\n"
    root = _setup(tmp_path, wip, PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] != "mismatch"


# --- Bug A: test status comes from the FINAL summary, not any occurrence -------


def test_test_status_uses_final_summary(tmp_path):
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\nEarly iteration: 3 failed, 50 passed\n"
        "## Step 2\nFinal run: 3579 passed, 2 skipped in 12.3s\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "green"


def test_test_status_red_when_final_run_fails(tmp_path):
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text("All passed earlier: 100 passed\nThen: 2 failed, 98 passed\n", encoding="utf-8")
    assert rps._read_test_status(p) == "red"


def test_test_status_green_for_fixed_shape_result_line(tmp_path):
    """A file in the canonical per-step shape (dec-386) whose last section's
    ``Result:`` line reports fail=0 reads as green."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=12 fail=0 skip=0\n"
        "Duration: 0.5s\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "green"


def test_test_status_red_for_fixed_shape_result_line_with_failures(tmp_path):
    """A fixed-shape Result: line with fail=2 reads as red for that line."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=10 fail=2 skip=0\n"
        "Duration: 0.5s\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "red"


def test_test_status_mixed_shapes_last_fixed_shape_section_wins(tmp_path):
    """A pytest-style red line followed by a later fixed-shape green section —
    last line wins overall, across shapes."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Early iteration: 3 failed, 50 passed\n"
        "## Step 2\n"  # id-citation-discipline:ignore
        "Result: pass=53 fail=0 skip=0\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "green"


def test_test_status_prose_summary_then_fixed_shape_green_wins(tmp_path):
    """A prose line resembling a pytest summary, followed by a fixed-shape
    green section, reads as green — the fixed-shape line is authoritative."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "Historical note: 11 passed / 1 failed in an earlier run\n"
        "## Step 1\n"  # id-citation-discipline:ignore
        "Result: pass=11 fail=0 skip=0\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "green"


def test_test_status_red_for_fixed_shape_all_zero_result_line(tmp_path):
    """A fixed-shape Result: line with pass=0 fail=0 skip=0 is a pytest collection
    error (e.g. ModuleNotFoundError above a ### Failures block) rendering exactly
    that all-zero shape — it must read red, never green, since nothing was proven."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=0 fail=0 skip=0\n"
        "Duration: 0.1s\n"
        "### Failures\n"
        "ModuleNotFoundError: No module named 'missing_thing'\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "red"


def test_test_status_all_zero_section_then_green_section_last_wins(tmp_path):
    """An all-zero (collection error) fixed-shape section followed by a later
    green fixed-shape section — last line wins, so the file reads green."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Result: pass=0 fail=0 skip=0\n"
        "## Step 2\n"  # id-citation-discipline:ignore
        "Result: pass=5 fail=0 skip=0\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "green"


# --- backward compatibility: the optional `Mutation:` step-section line -----
#
# Both fixture lines are built by calling the shipped scripts/mutation_sensor.py
# directly (imported below) rather than hand-copied strings, so a future
# change to the runner's exact rendering re-derives the fixture instead of
# silently drifting from it.


def _mutation_survivors_line_at_cap() -> str:
    """The real `survivors=` rendering, sized so it lands exactly at the
    runner's 240-byte hard cap -- the boundary where a regression could
    silently push a green section's byte count somewhere unexpected."""
    per_function = {
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 19,
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": 9,
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc": 8,
        "d": 4,
        "e": 4,
        "f": 3,
        "g": 2,
    }
    histogram = {
        "killed": 0,
        "survived": sum(per_function.values()),
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "segfault": 0,
    }
    outcome = ms.Ran(
        targets=("a.py",),
        mutants=sum(per_function.values()),
        histogram=histogram,
        per_function=per_function,
        elapsed_s=1.0,
    )
    line = ms.render_line(outcome)
    assert len(line.encode("utf-8")) == ms.LINE_BYTE_CAP, (
        f"fixture drifted off the byte cap: {len(line.encode('utf-8'))} bytes, "
        f"expected exactly {ms.LINE_BYTE_CAP}"
    )
    return line


def _mutation_unavailable_line() -> str:
    """The real `unavailable` refusal rendering, built the same way the
    runner's own `_emit` renders a `toolchain-missing` refusal."""
    reason = ms.ReasonCode.TOOLCHAIN_MISSING.value
    detail = ms._one_line("uv not found on PATH")
    return f"Mutation: unavailable reason={reason} ({detail})"


def test_test_status_green_with_mutation_survivors_line_matches_shape_without_it(tmp_path):
    """A green fixed-shape section carrying the `survivors=` line at exactly
    its byte cap classifies exactly as it would without the line -- green."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=12 fail=0 skip=0\n"
        "Duration: 0.5s\n"
        f"{_mutation_survivors_line_at_cap()}\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "green"


def test_test_status_green_with_mutation_unavailable_line_matches_shape_without_it(tmp_path):
    """A green fixed-shape section carrying the `unavailable` refusal line
    classifies exactly as it would without the line -- green. A legitimate
    refusal must never read as a failure."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=12 fail=0 skip=0\n"
        "Duration: 0.5s\n"
        f"{_mutation_unavailable_line()}\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "green"


def test_test_status_red_result_line_wins_regardless_of_mutation_line(tmp_path):
    """Canary: a red Result: line (fail > 0) still classifies red even when a
    Mutation: line is present -- the line must never launder a real failure
    into green, whichever of the two shapes it carries. `survivors=3` and
    `(fn: 2)` must never be read as a passing count by the pytest-count
    regexes this reader also scans for."""
    p = tmp_path / "TEST_RESULTS.md"
    p.write_text(
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=10 fail=2 skip=0\n"
        "Duration: 0.5s\n"
        f"{_mutation_survivors_line_at_cap()}\n",
        encoding="utf-8",
    )
    assert rps._read_test_status(p) == "red"


# --- windowed WAL read + cross-boundary recovery (Step 5 / Group B) ----------
#
# These tests call _read_wal(obs_path, max_age_days=7, now=<datetime>) — the
# new windowed signature that does NOT yet exist. All 6 are expected RED until
# the implementer's Step 4 lands the 2-file windowed _read_wal.
#
# RED trigger: TypeError — _read_wal() got an unexpected keyword argument 'now'
#
# Scenario 6 (WIP.md pre-mortem): active-file rows are retained unconditionally;
# only the .1 segment is mtime/timestamp-pruned. A malformed-timestamp row in
# the active file must never be dropped. _keeps_active_row_with_malformed_timestamp
# guards this contract.


_NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)
_WITHIN_WINDOW_TS = "2026-06-25T12:00:00+00:00"  # 1 day before _NOW
_OUTSIDE_WINDOW_TS = "2026-06-10T12:00:00+00:00"  # 16 days before _NOW


def test_cross_boundary_canary_reconciler_sees_events_split_across_rotation(tmp_path):
    """Load-bearing canary: agent_start+tool_use in .1, agent_stop in active —
    _read_wal must return all 3 rows AND _correlate_agents must see the stop."""
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    declared_file = "src/cross_boundary_feature.py"

    # Two rows written to the rotated segment (.1) — the "old session"
    seg_rows = [
        {
            "event_type": "agent_start",
            "agent_id": "agent-A",
            "agent_type": "praxion:implementer",
            "timestamp": _WITHIN_WINDOW_TS,
        },
        {
            "event_type": "tool_use",
            "agent_id": "agent-A",
            "agent_type": "praxion:implementer",
            "file_paths": [f"/repo/{declared_file}"],
            "timestamp": _WITHIN_WINDOW_TS,
        },
    ]
    seg_path.write_text("\n".join(json.dumps(r) for r in seg_rows) + "\n", encoding="utf-8")

    # One row in the active file — the stop that arrived after rotation
    stop_row = {
        "event_type": "agent_stop",
        "agent_id": "agent-A",
        "timestamp": _WITHIN_WINDOW_TS,
    }
    obs_path.write_text(json.dumps(stop_row) + "\n", encoding="utf-8")

    # Windowed 2-file read must return all 3 rows (2 from .1 + 1 from active)
    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 3, f"expected 3 rows across boundary, got {len(rows)}"

    # Correlation must surface the agent_stop even though it lived in the active file
    tier2 = rps._correlate_agents([declared_file], rows)
    assert tier2["agent_stop_seen"] is True, (
        "agent_stop in active file must be visible after 2-file stitch"
    )


def test_read_wal_excludes_rows_older_than_window(tmp_path):
    """Rows with timestamps older than max_age_days in the .1 segment are pruned."""
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    stale_row = {"event_type": "tool_use", "agent_id": "stale", "timestamp": _OUTSIDE_WINDOW_TS}
    seg_path.write_text(json.dumps(stale_row) + "\n", encoding="utf-8")
    obs_path.write_text("", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 0, "stale segment row must be excluded from the windowed read"


def test_read_wal_skips_segment_when_mtime_out_of_window(tmp_path):
    """When .1 mtime is older than max_age_days, the segment is not read at all."""
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    # Segment has a row with a recent-looking timestamp but the FILE is old
    recent_looking_row = {"event_type": "tool_use", "timestamp": _WITHIN_WINDOW_TS}
    seg_path.write_text(json.dumps(recent_looking_row) + "\n", encoding="utf-8")

    # Set mtime to 10 days before _NOW — outside the 7-day window
    old_mtime = (_NOW - timedelta(days=10)).timestamp()
    os.utime(seg_path, (old_mtime, old_mtime))

    obs_path.write_text("", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 0, "segment with out-of-window mtime must be skipped entirely"


def test_read_wal_handles_missing_segment_gracefully(tmp_path):
    """When .1 is absent, _read_wal returns active rows without error."""
    obs_path = tmp_path / "observations.jsonl"
    # No seg_path created — .1 does not exist

    active_row = {"event_type": "agent_stop", "agent_id": "agent-B", "timestamp": _WITHIN_WINDOW_TS}
    obs_path.write_text(json.dumps(active_row) + "\n", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "agent_stop"


def test_canary_single_file_read_misses_current_session_events_after_rotation(tmp_path):
    """Gate-liveness canary: when active file is empty and .1 holds recent rows,
    _read_wal must return the .1 rows — proving 2-file read is required.

    If _read_wal read only the active file (the pre-Step-4 behaviour), this
    assertion would fail (0 rows returned) — the regression this canary catches.
    """
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    # Post-rotation state: fresh empty active + prior session events in .1
    obs_path.write_text("", encoding="utf-8")
    seg_row = {
        "event_type": "tool_use",
        "agent_id": "agent-C",
        "agent_type": "praxion:implementer",
        "timestamp": _WITHIN_WINDOW_TS,
    }
    seg_path.write_text(json.dumps(seg_row) + "\n", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 1, "post-rotation .1 rows must be returned by the 2-file windowed read"
    assert rows[0]["agent_id"] == "agent-C"


def test_read_wal_keeps_active_row_with_malformed_timestamp(tmp_path):
    """Active-file rows with missing or garbage timestamps are retained unconditionally.

    Contrast: an equivalently malformed timestamp in the .1 segment is pruned
    (malformed timestamp parses as epoch → epoch is outside any reasonable window).
    This guards the pre-mortem scenario 6 correctness refinement: recovery errs
    toward inclusion; a bad correlation degrades to unknown→user, never a false verdict.
    """
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    # Active file: row with garbage timestamp — must be retained
    malformed_active = {
        "event_type": "tool_use",
        "agent_id": "agent-D",
        "timestamp": "NOT_A_TIMESTAMP",
    }
    obs_path.write_text(json.dumps(malformed_active) + "\n", encoding="utf-8")

    # Segment: row with same garbage timestamp — must be pruned (epoch → old → outside window)
    malformed_seg = {
        "event_type": "tool_use",
        "agent_id": "agent-E",
        "timestamp": "NOT_A_TIMESTAMP",
    }
    seg_path.write_text(json.dumps(malformed_seg) + "\n", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)

    agent_ids_returned = {r.get("agent_id") for r in rows}
    assert "agent-D" in agent_ids_returned, (
        "active-file row with malformed timestamp must be retained unconditionally"
    )
    assert "agent-E" not in agent_ids_returned, (
        "segment row with malformed timestamp must be pruned (parsed as epoch → outside window)"
    )


# --- graceful degradation on a fully absent raw WAL (fresh clone, since the raw
# WAL left git tracking) -----------------------------------------------------


def test_read_wal_handles_missing_active_file_gracefully(tmp_path):
    """No observations.jsonl at all (not even an empty one) must not raise.

    This is the fresh-clone scenario every future clone hits once the raw WAL
    left git tracking: the file is absent, not empty.
    """
    obs_path = tmp_path / "observations.jsonl"  # never created

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert rows == []


def test_reconcile_ignores_absent_wal_and_trusts_tier1(tmp_path):
    """reconcile() with a real (absent) .ai-state/observations.jsonl must still
    classify from Tier-1 (files changed + tests) — Tier-2 correlation degrades
    to empty, it never blocks or corrupts the Tier-1 verdict."""
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_ONE_STEP)
    # No .ai-state/ directory at all — the real absent-WAL shape, not an override.
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _test_status_override="green",
    )
    verdict = _verdict_for(out, "Step 1")
    assert verdict["verdict"] == "verified-complete"
    assert verdict["tier2"]["agent_stop_seen"] is False


def test_main_reports_no_local_wal_on_stderr_when_absent(tmp_path, capsys, monkeypatch):
    """main() surfaces an explicit INFO line when the raw WAL is absent —
    Tier-1 classification proceeds unaffected (no traceback, no crash)."""
    _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(rps, "resolve_repo_root", lambda *_a, **_k: tmp_path)
    monkeypatch.setattr(rps, "is_plugin_cache_path", lambda *_a, **_k: False)
    monkeypatch.setattr(rps, "_git_changed_files", lambda *_a, **_k: {"src/foo.py"})
    monkeypatch.setattr(rps, "_read_test_status", lambda *_a, **_k: "green")

    exit_code = rps.main([SLUG, "--json"])
    err = capsys.readouterr().err
    assert "no local WAL" in err
    assert exit_code == 0


# --- Files: field admission ignores a trailing parenthetical rationale ------


def test_split_files_admits_only_the_declared_path_when_followed_by_a_parenthetical_rationale():
    """A rationale in parentheses naming an unrelated document must never be
    read as a second declared file, and the rationale's own trailing token
    must never survive as a bare fragment either."""
    assert rps._split_files("scripts/a.py (see .ai-work/x/WIP.md, n/a)") == ["scripts/a.py"]


def test_split_files_recognizes_a_bare_none_declaration_with_stray_leading_emphasis():
    """A ``**Files:** none`` field renders its captured value with a leading
    ``**`` still attached to the token -- the none/n-a check must strip
    markdown emphasis before testing, not only surrounding whitespace."""
    assert rps._split_files("** none") == []


def test_split_files_admits_backtick_quoted_comma_separated_paths():
    assert rps._split_files("`src/a.py`, `src/b.py`") == ["src/a.py", "src/b.py"]


def test_split_files_admits_bare_comma_separated_paths():
    assert rps._split_files("src/a.py, src/b.py") == ["src/a.py", "src/b.py"]


def test_split_files_does_not_admit_an_extensionless_top_level_name():
    """Declared limit: a bare top-level filename with no directory separator
    and no extension (e.g. ``Makefile``) is never treated as a declared file."""
    assert rps._split_files("Makefile") == []


# --- a wrapped Files: field keeps every trailing-comma continuation line ----
#
# Verbatim excerpt of a real harvested plan's Files: field -- roughly 38 of
# 296 real fields wrap this way, and every continuation line must be gathered
# before the admission predicate runs, not just the opening line.

_P3_5_WRAPPED_FILES_FIELD = (
    "**Files**: `scripts/project_metrics/tests/test_cost_collector.py`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/attributed.jsonl`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/pre_attribution.jsonl`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/unparsed.jsonl`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/parent_sourced_synthetic.jsonl`\n"
)


def test_scan_step_files_keeps_every_line_of_a_wrapped_trailing_comma_continuation(tmp_path):
    plan_path = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan_path.write_text("### Step 1: RED\n" + _P3_5_WRAPPED_FILES_FIELD, encoding="utf-8")
    assert rps._scan_step_files(plan_path)["Step 1"] == [
        "scripts/project_metrics/tests/test_cost_collector.py",
        "scripts/project_metrics/tests/fixtures/cost/attributed.jsonl",
        "scripts/project_metrics/tests/fixtures/cost/pre_attribution.jsonl",
        "scripts/project_metrics/tests/fixtures/cost/unparsed.jsonl",
        "scripts/project_metrics/tests/fixtures/cost/parent_sourced_synthetic.jsonl",
    ]


# --- a declared glob matches only under its own directory -------------------


def test_path_match_anchored_glob_never_falls_back_to_a_bare_basename_match():
    """A glob's own trailing ``*`` must not become a wildcard for any filename
    anywhere in the repo once its directory prefix stops matching."""
    assert rps._path_match(
        "eval/tests/fixtures/scenarios/*", "eval/tests/fixtures/scenarios/foo.yaml"
    )
    assert not rps._path_match("eval/tests/fixtures/scenarios/*", "unrelated/other/x.py")


# --- production call shape: a real git repo drives the same anchored-glob fix -


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _git_capture(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def test_reconcile_never_confirms_a_step_from_a_file_that_only_matches_a_globs_basename(tmp_path):
    """Through ``reconcile()``'s own production call shape, over a real git
    repo -- not just the ``_path_match`` unit. A step declaring a glob must
    stay unconfirmed when the only real change lives outside the glob's
    directory, even though the change's basename incidentally matches ``*``."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    base_sha = _git_capture(["rev-parse", "HEAD"], repo_root)

    plan = (
        "### Step 1: Add scenario fixtures\n"
        "**Files**: eval/tests/fixtures/scenarios/*\n"
        "**Done when**: fixtures land\n"
    )
    _setup(repo_root, "- [x] Step 1: add scenario fixtures\n", plan)

    (repo_root / "unrelated" / "other").mkdir(parents=True)
    (repo_root / "unrelated" / "other" / "x.py").write_text("# unrelated\n", encoding="utf-8")
    _run_git(["add", "unrelated/other/x.py"], repo_root)
    _run_git(["commit", "-q", "-m", "unrelated change"], repo_root)

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    verdict = _verdict_for(out, "Step 1")
    assert verdict["verdict"] != "verified-complete", (
        "an unrelated file must not confirm a glob-declared Files: field via "
        "basename-only fallback matching"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
