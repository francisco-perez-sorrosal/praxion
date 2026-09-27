"""Tests for `workflow_run_cost.py`'s world-read functions -- `_read_wal`,
`_transcript_stats`, the windowing trio (`_parse_ts`/`_run_window`/`_within`),
and `render_list_table` (td-226).

Kept apart from `test_workflow_run_cost.py`, which is over `coding-style.md`'s
800-line file-size ceiling, so new coverage lands here instead of growing it.

Every fixture here is built entirely in `tmp_path` -- no dependency on
`scripts/test_fixtures/` on disk -- deliberately, so this file (unlike its
sibling `test_workflow_run_cost_fixtures.py`) can be passed to
`scripts/mutation_sensor.py --tests`: that tool's flat, `.py`-only sandbox
never copies a non-Python fixture directory into its execution sandbox.

Reuses `test_workflow_run_cost.py`'s own fixture builders directly via a
plain module import (both files describe one production module's behavior;
DAMP favors composing the existing builders over re-deriving the
run-directory layout a second time).

Import strategy: same `importlib.import_module` RED/GREEN-deferred-import
convention as the sibling files in this directory.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import test_workflow_run_cost as base  # noqa: E402 -- after sys.path insertion


# --------------------------------------------------------------------------- #
# `_single_agent_run` -- the minimal one-agent composition most world-read
# tests below start from; each targets one function's edge case rather than
# a fully-populated report.
# --------------------------------------------------------------------------- #
def _single_agent_run(
    tmp_path,
    monkeypatch,
    *,
    transcript_records=None,
    wal_rows=None,
    main_launch_tokens=205_762,
    main_next_tokens=208_358,
    session="sess-1",
    wf_id="wf_test0001",
):
    agent = dict(base._DEFAULT_AGENTS[0])
    home, project_root = base._project(tmp_path, monkeypatch)
    run_dir = base._run_dir(home, project_root, session, wf_id)
    base._write_journal(run_dir, [agent])
    base._write_meta(run_dir, agent["agent_id"], label=agent["label"], phase=agent["phase"])
    if transcript_records is None:
        transcript_records = base._agent_transcript_records(
            agent["model"], agent["peak_context"], agent["output_tokens"]
        )
    base._write_jsonl(run_dir / f"agent-{agent['agent_id']}.jsonl", transcript_records)
    base._write_main_transcript(
        home,
        project_root,
        session,
        launch_tokens=main_launch_tokens,
        next_tokens=main_next_tokens,
        wf_id=wf_id,
    )
    if wal_rows is None:
        wal_rows = [
            base._wal_agent_stop(
                agent["agent_id"],
                tokens_in=agent["peak_context"],
                tokens_out=agent["output_tokens"],
            )
        ]
    base._write_wal(project_root, wal_rows)
    return project_root, wf_id, agent


# --------------------------------------------------------------------------- #
# `_read_wal` -- last-in-file wins for a repeated `agent_id`; a non-`agent_stop`
# event type and a row missing `agent_id` are both skipped, never raised on
# --------------------------------------------------------------------------- #
def test_read_wal_keeps_the_last_agent_stop_row_and_ignores_unrelated_or_unlabeled_rows(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id, agent = _single_agent_run(tmp_path, monkeypatch, wal_rows=[])
    stale = base._wal_agent_stop(
        agent["agent_id"],
        tokens_in=1,
        tokens_out=1,
        cache_read=1,
        cache_create=1,
        model="stale-model",
        duration_ms=1_000,
        usage_source="parent-transcript",
        timestamp=base._RUN_START,
    )
    fresh = base._wal_agent_stop(
        agent["agent_id"],
        tokens_in=agent["peak_context"],
        tokens_out=agent["output_tokens"],
        cache_read=333,
        cache_create=444,
        duration_ms=9_000,
        timestamp=base._RUN_END,
    )
    noise_event = {"event_type": "session_start", "agent_id": agent["agent_id"], "tokens_out": 42}
    no_agent_id = {"event_type": "agent_stop", "tokens_out": 42}
    base._write_wal(project_root, [stale, noise_event, no_agent_id, fresh])

    _, _, report = base._run_json(project_root, wf_id, capsys)

    row = report["agents"][0]
    # Only `fresh`'s tokens_out matches the transcript -- if `stale` had won
    # instead, this would read "differ". The `wal` object is a reported
    # figure set, so every field is pinned, each distinct from `stale`'s.
    assert row["wal_agreement"] == "agree"
    assert row["wal"] == {key: fresh[key] for key in row["wal"]}
    assert set(row["wal"]) == set(fresh) - {"event_type", "agent_id"}


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores file permission bits; chmod 0o000 would not actually block the read",
)
def test_exits_2_with_wal_unreadable_reason_when_wal_is_unreadable(tmp_path, monkeypatch, capsys):
    """An unreadable WAL must not read as `wal-missing` (every agent silently
    `wal-missing`) -- it must refuse with its own named reason, exit 2, and
    publish no report on stdout."""
    project_root, wf_id, _agent = _single_agent_run(tmp_path, monkeypatch)
    wal_path = project_root / ".ai-state" / "observations.jsonl"
    wal_path.chmod(0o000)
    try:
        exit_code, captured = base._run_cli(
            ["--run", wf_id, "--project-root", str(project_root), "--json"], capsys
        )
    finally:
        wal_path.chmod(0o644)

    assert exit_code == 2
    assert "wal-unreadable" in captured.err
    assert captured.out == ""


def test_every_agent_reads_wal_missing_when_wal_is_simply_absent(tmp_path, monkeypatch, capsys):
    """Inverse guard: a WAL that was never written stays non-fatal -- the run
    still succeeds, and every agent's `wal_agreement` reads `wal-missing`."""
    project_root, wf_id, agent = _single_agent_run(tmp_path, monkeypatch, wal_rows=[])
    (project_root / ".ai-state" / "observations.jsonl").unlink()

    exit_code, _captured, report = base._run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    assert report["agents"][0]["agent_id"] == agent["agent_id"]
    assert all(row["wal_agreement"] == "wal-missing" for row in report["agents"])


# --------------------------------------------------------------------------- #
# `_transcript_stats` -- a usage-less assistant turn is not a turn; an empty
# transcript file reads as missing, same as no file at all; tool_uses sums
# across every turn, not just the peak one.
# --------------------------------------------------------------------------- #
def test_transcript_stats_does_not_count_an_assistant_turn_with_no_usage_key(
    tmp_path, monkeypatch, capsys
):
    agent = dict(base._DEFAULT_AGENTS[0])
    no_usage_turn = {
        "type": "assistant",
        "timestamp": base._RUN_START,
        "message": {"model": agent["model"], "content": [{"type": "text", "text": "..."}]},
    }
    real_turn = base._assistant_turn(
        agent["model"], agent["peak_context"], agent["output_tokens"], 2, timestamp=base._RUN_END
    )
    project_root, wf_id, _ = _single_agent_run(
        tmp_path, monkeypatch, transcript_records=[no_usage_turn, real_turn], wal_rows=[]
    )

    _, _, report = base._run_json(project_root, wf_id, capsys)

    row = report["agents"][0]
    assert row["turns"] == 1
    assert row["output_tokens"] == agent["output_tokens"]


def test_transcript_stats_treats_an_empty_transcript_file_as_missing_same_as_no_file(
    tmp_path, monkeypatch, capsys
):
    """`_transcript_stats` returns `None` for a file that exists but is
    empty, exactly as it does for one that does not exist at all -- the
    production docstring names this equivalence. Two agents are rostered so
    the empty-transcript agent alone does not trip `load()`'s
    all-transcripts-missing guard."""
    agents = [dict(a) for a in base._DEFAULT_AGENTS[:2]]
    project_root, wf_id = base._standard_run(tmp_path, monkeypatch, agents=agents)
    home = tmp_path / "home"
    run_dir = base._run_dir(home, project_root, "sess-1", wf_id)
    (run_dir / f"agent-{agents[0]['agent_id']}.jsonl").write_text("", encoding="utf-8")

    _, _, report = base._run_json(project_root, wf_id, capsys)

    empty = next(row for row in report["agents"] if row["agent_id"] == agents[0]["agent_id"])
    assert empty["transcript"] is None
    assert empty["wal_agreement"] == "transcript-missing"


def test_transcript_stats_sums_tool_uses_across_every_turn_not_just_the_peak_turn(
    tmp_path, monkeypatch, capsys
):
    agent = dict(base._DEFAULT_AGENTS[0])
    turn_a = base._assistant_turn(
        agent["model"], agent["peak_context"], 100, 2, timestamp=base._RUN_START
    )
    turn_b = base._assistant_turn(agent["model"], 1_000, 50, 3, timestamp=base._RUN_END)
    project_root, wf_id, _ = _single_agent_run(
        tmp_path, monkeypatch, transcript_records=[turn_a, turn_b], wal_rows=[]
    )

    _, _, report = base._run_json(project_root, wf_id, capsys)

    row = report["agents"][0]
    assert row["tool_uses"] == 5
    assert row["turns"] == 2


# --------------------------------------------------------------------------- #
# windowing -- `_parse_ts` / `_run_window` / `_within`: `Z` and offset forms
# parse to the same instant, both window boundaries are inclusive, and an
# unparseable timestamp is excluded rather than raised on.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "boundary_ts",
    [pytest.param(base._RUN_START, id="start"), pytest.param(base._RUN_END, id="end")],
)
def test_within_includes_a_helper_stop_timestamped_exactly_on_the_window_boundary(
    tmp_path, monkeypatch, capsys, boundary_ts
):
    """`_within`'s window check is `start <= stamp <= end` on both ends -- a
    helper stop landing exactly on either boundary must still be reported,
    not silently dropped by a strict `<`."""
    project_root, wf_id, _ = _single_agent_run(tmp_path, monkeypatch)
    wal_path = project_root / ".ai-state" / "observations.jsonl"
    existing = [json.loads(line) for line in wal_path.read_text(encoding="utf-8").splitlines()]
    existing.append(
        base._wal_agent_stop("helper-boundary", tokens_in=1, tokens_out=1, timestamp=boundary_ts)
    )
    base._write_wal(project_root, existing)

    _, _, report = base._run_json(project_root, wf_id, capsys)

    assert [row["agent_id"] for row in report["unobserved"]] == ["helper-boundary"]


def test_within_treats_z_and_offset_timestamps_as_equal_at_the_exact_boundary(
    tmp_path, monkeypatch, capsys
):
    """The WAL writes explicit `+00:00` offsets while transcripts write `Z`
    -- `_parse_ts` must normalize both to the same instant, or a helper stop
    at the run's own start would be wrongly excluded depending on which form
    it happens to use."""
    project_root, wf_id, _ = _single_agent_run(tmp_path, monkeypatch)
    wal_path = project_root / ".ai-state" / "observations.jsonl"
    existing = [json.loads(line) for line in wal_path.read_text(encoding="utf-8").splitlines()]
    existing.append(
        base._wal_agent_stop(
            "helper-offset", tokens_in=1, tokens_out=1, timestamp="2026-09-19T10:00:00.000+00:00"
        )
    )
    base._write_wal(project_root, existing)

    _, _, report = base._run_json(project_root, wf_id, capsys)

    assert [row["agent_id"] for row in report["unobserved"]] == ["helper-offset"]


def test_within_excludes_a_helper_stop_with_a_malformed_or_non_string_timestamp(
    tmp_path, monkeypatch, capsys
):
    """A WAL row whose timestamp cannot be parsed is treated as outside the
    window (excluded), never crashes the report -- an honest absence, not a
    guessed inclusion."""
    project_root, wf_id, _ = _single_agent_run(tmp_path, monkeypatch)
    wal_path = project_root / ".ai-state" / "observations.jsonl"
    existing = [json.loads(line) for line in wal_path.read_text(encoding="utf-8").splitlines()]
    existing.append(
        base._wal_agent_stop("helper-bad-ts", tokens_in=1, tokens_out=1, timestamp="not-a-date")
    )
    existing.append(
        {**base._wal_agent_stop("helper-null-ts", tokens_in=1, tokens_out=1), "timestamp": None}
    )
    base._write_wal(project_root, existing)

    exit_code, _, report = base._run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    assert report["unobserved"] == []


# --------------------------------------------------------------------------- #
# `render_list_table` -- the `--list` non-JSON table path. The only existing
# `--list` test (`test_list_flag_enumerates_known_runs_with_timestamps`) only
# ever exercises `--list --json`.
# --------------------------------------------------------------------------- #
def test_list_flag_without_json_renders_a_header_row_and_one_line_per_run(
    tmp_path, monkeypatch, capsys
):
    home, project_root = base._project(tmp_path, monkeypatch)
    seed = base._DEFAULT_AGENTS[0]
    run_dir = base._run_dir(home, project_root, "sess-1", "wf_table0001")
    base._write_journal(run_dir, [seed])
    base._write_meta(run_dir, seed["agent_id"], label=seed["label"], phase=seed["phase"])
    base._write_transcript(
        run_dir,
        seed["agent_id"],
        model=seed["model"],
        peak_context=seed["peak_context"],
        output_tokens=seed["output_tokens"],
    )

    exit_code, captured = base._run_cli(["--list", "--project-root", str(project_root)], capsys)

    lines = captured.out.splitlines()
    assert exit_code == 0
    assert lines[0].split()[0] == "wf_id"
    assert any(line.startswith("wf_table0001") for line in lines[1:])
