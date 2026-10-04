"""Tests for context_baseline.py -- the P3.1 context guard report.

`compute(rows, band=None, *, generated_at, source_root) -> report` is a pure
function: no filesystem access, no clock read. `load(project_root)` is the
separate I/O layer (walks `~/.claude/projects/<project>/*.jsonl` +
`.ai-state/observations.jsonl`) and is out of scope here -- fixtures only,
never real transcripts, so this suite stays reproducible in CI and on
another machine.

Row shape `compute()` consumes (see LEARNINGS.md for the full contract handed
to the implementer):
    kind         "main" | "subagent"
    atype        subagent type name; ignored for kind="main"
    slug         pipeline slug; ignored for kind="main"
    peak         peak context tokens across assistant turns
    first_turn   context tokens at the first assistant turn
    turns        number of assistant records carrying usage
    requests     number of distinct API requests (subagent only)
    max_turns    the agent file's declared `maxTurns`, or None (subagent only)
    tools        tool_use block count; ignored for kind="main"
    compactions  count of isCompactSummary rows seen
    spawns       list of [context_at_spawn, spawned_agent_type]; kind="main" only

Percentile convention pinned to `baseline/baseline.py`'s `q(xs, p)`: a
floor-indexed pick (`sorted(xs)[min(len(xs)-1, int(p*len(xs)))]`), not
`statistics.median` -- the guard must reproduce numbers already published in
`BASELINE.md`, which were computed with this exact formula.

Import strategy: `importlib.import_module` (not `spec_from_file_location`,
which raises `FileNotFoundError` for a missing file) so the RED failure mode
is `ModuleNotFoundError`, matching an import that genuinely does not exist
yet.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _load():
    return importlib.import_module("context_baseline")


ctx = _load()

GENERATED_AT = "2026-09-18T00:00:00Z"
SOURCE_ROOT = "/Users/example/.claude/projects/-Users-example-dev-praxion"


def _main_row(
    peak: int = 100_000,
    first_turn: int = 10_000,
    turns: int = 5,
    compactions: int = 0,
    spawns: list[list] | None = None,
) -> dict:
    """A main-session row -- the orchestrator's own window."""
    return {
        "kind": "main",
        "atype": None,
        "slug": None,
        "peak": peak,
        "first_turn": first_turn,
        "turns": turns,
        "tools": 0,
        "compactions": compactions,
        "spawns": spawns or [],
    }


def _subagent_row(
    atype: str = "implementer",
    slug: str = "some-slug",
    peak: int = 100_000,
    first_turn: int = 10_000,
    turns: int = 5,
    tools: int = 5,
    compactions: int = 0,
    requests: int = 3,
    max_turns: int | None = None,
) -> dict:
    """A subagent row -- one spawned agent's transcript."""
    return {
        "kind": "subagent",
        "atype": atype,
        "slug": slug,
        "peak": peak,
        "first_turn": first_turn,
        "turns": turns,
        "requests": requests,
        "max_turns": max_turns,
        "tools": tools,
        "compactions": compactions,
        "spawns": [],
    }


# --------------------------------------------------------------------------- #
# (a) full report shape exactly
# --------------------------------------------------------------------------- #
def test_report_shape_matches_ds3_exactly():
    rows = [
        _main_row(spawns=[[50_000, "implementer"], [60_000, "test-engineer"]]),
        _main_row(spawns=[[70_000, "implementer"]]),
        _subagent_row(atype="implementer", slug="alpha", peak=200_000),
        _subagent_row(atype="implementer", slug="alpha", peak=300_000),
        _subagent_row(atype="test-engineer", slug="beta", peak=150_000),
    ]
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)

    assert set(report.keys()) == {
        "generated_at",
        "source_root",
        "sessions",
        "subagents",
        "main",
        "by_agent_type",
        "by_pipeline",
        "cap_outs",
    }
    assert report["sessions"] == 2
    assert report["subagents"] == 3

    assert set(report["main"].keys()) == {"peak", "first_turn", "spawn_context"}
    assert set(report["main"]["peak"].keys()) == {"p50", "p90", "max"}
    assert set(report["main"]["first_turn"].keys()) == {"p50"}
    assert set(report["main"]["spawn_context"].keys()) == {"implementer", "test-engineer"}
    assert set(report["main"]["spawn_context"]["implementer"].keys()) == {
        "n",
        "p50",
        "p90",
        "max",
    }

    assert set(report["by_agent_type"].keys()) == {"implementer", "test-engineer"}
    assert set(report["by_agent_type"]["implementer"].keys()) == {
        "n",
        "first_turn_p50",
        "peak_p50",
        "peak_p90",
        "peak_max",
        "turns_p50",
        "tools_p50",
        "compacted",
    }

    assert set(report["by_pipeline"].keys()) == {"alpha", "beta"}
    assert set(report["by_pipeline"]["alpha"].keys()) == {
        "agents",
        "sum_peak",
        "max_peak",
        "over_100k",
        "over_150k",
    }


# --------------------------------------------------------------------------- #
# (b) band key absent/present, exact shape, no pct
# --------------------------------------------------------------------------- #
def test_band_key_absent_without_band_argument():
    rows = [_main_row(), _subagent_row()]
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    assert "band" not in report


def test_band_key_present_with_exact_shape_and_no_pct_field():
    rows = [
        _main_row(peak=600_000),
        _main_row(peak=100_000),
        _subagent_row(atype="implementer", peak=100_000),
    ]
    report = ctx.compute(rows, band=500_000, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    assert set(report["band"].keys()) == {"threshold", "window_tokens", "would_compact"}
    assert "pct" not in report["band"]
    assert report["band"]["threshold"] == 500_000

    would_compact = report["band"]["would_compact"]
    assert would_compact["main"] == {"n": 1, "of": 2}
    assert would_compact["implementer"] == {"n": 0, "of": 1}


# --------------------------------------------------------------------------- #
# (c) percentile math exact on synthetic rows
# --------------------------------------------------------------------------- #
def test_by_agent_type_percentiles_use_floor_indexed_formula():
    # 4 rows of one type, known values -- statistics.median would give 250_000 for
    # the p50 of [100k,200k,300k,400k] (average of the two middle values); the
    # floor-indexed q(xs,.5) picks sorted[int(0.5*4)] = sorted[2] = 300_000.
    rows = [
        _subagent_row(atype="implementer", peak=p, first_turn=ft, turns=t, tools=tl)
        for p, ft, t, tl in [
            (100_000, 1_000, 1, 5),
            (200_000, 2_000, 2, 10),
            (300_000, 3_000, 3, 15),
            (400_000, 4_000, 4, 20),
        ]
    ]
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    by_type = report["by_agent_type"]["implementer"]

    assert by_type["n"] == 4
    assert by_type["peak_p50"] == 300_000  # sorted[int(0.5*4)] = sorted[2]
    assert by_type["peak_p90"] == 400_000  # sorted[int(0.9*4)] = sorted[3]
    assert by_type["peak_max"] == 400_000
    assert by_type["first_turn_p50"] == 3_000
    assert by_type["turns_p50"] == 3
    assert by_type["tools_p50"] == 15


def test_main_peak_percentiles_use_floor_indexed_formula():
    rows = [_main_row(peak=p) for p in (100_000, 200_000, 300_000, 400_000)]
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    peak = report["main"]["peak"]
    assert peak["p50"] == 300_000
    assert peak["p90"] == 400_000
    assert peak["max"] == 400_000


def test_by_pipeline_aggregates_sum_and_threshold_counts():
    rows = [
        _subagent_row(atype="implementer", slug="alpha", peak=120_000),
        _subagent_row(atype="test-engineer", slug="alpha", peak=160_000),
        _subagent_row(atype="implementer", slug="alpha", peak=90_000),
    ]
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    alpha = report["by_pipeline"]["alpha"]
    assert alpha["agents"] == 3
    assert alpha["sum_peak"] == 120_000 + 160_000 + 90_000
    assert alpha["max_peak"] == 160_000
    assert alpha["over_100k"] == 2  # 120k, 160k
    assert alpha["over_150k"] == 1  # 160k only


# --------------------------------------------------------------------------- #
# (d) unknown/multi agent types reported as their own rows
# --------------------------------------------------------------------------- #
def test_unknown_and_multi_agent_types_are_reported_as_their_own_rows():
    rows = [
        _subagent_row(atype="unknown", slug="alpha", peak=50_000),
        _subagent_row(atype="multi", slug="alpha", peak=60_000),
        _subagent_row(atype="implementer", slug="alpha", peak=70_000),
    ]
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    assert "unknown" in report["by_agent_type"]
    assert "multi" in report["by_agent_type"]
    assert report["by_agent_type"]["unknown"]["n"] == 1
    assert report["by_agent_type"]["multi"]["n"] == 1
    # Neither collapses into a shared "other" bucket, nor is dropped from the total.
    assert report["subagents"] == 3


# --------------------------------------------------------------------------- #
# (e) compute() is pure -- no filesystem, no clock, fixed generated_at echoed
# --------------------------------------------------------------------------- #
def test_generated_at_and_source_root_echo_back_unchanged():
    rows = [_main_row()]
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    assert report["generated_at"] == GENERATED_AT
    assert report["source_root"] == SOURCE_ROOT

    # Calling again with the same fixed inputs must be fully deterministic --
    # nothing inside compute() may read a clock or the filesystem to vary the
    # result.
    report_again = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    assert report_again == report


def test_compute_source_contains_no_filesystem_or_clock_calls():
    source = inspect.getsource(ctx.compute)
    for forbidden in ("Path(", "open(", "datetime.now(", "os.walk", "glob."):
        assert forbidden not in source, (
            f"compute() must stay pure -- found {forbidden!r} in its source; "
            "filesystem/clock access belongs only in load()"
        )


# --------------------------------------------------------------------------- #
# (f) an empty project directory warns loudly rather than silently reporting 0
# --------------------------------------------------------------------------- #
def test_subagent_transcript_paths_include_workflow_run_directories(tmp_path):
    """Workflow-tool agents file their transcripts one level deeper than
    Agent-tool spawns (`subagents/workflows/<run>/`); the guard must count
    both, and must not mistake a run's journal for an agent."""
    session = tmp_path / "-Users-x-proj" / "sess-1" / "subagents"
    sibling = session / "agent-a1.jsonl"
    nested = session / "workflows" / "wf_1234" / "agent-a2.jsonl"
    journal = session / "workflows" / "wf_1234" / "journal.jsonl"
    for path in (sibling, nested, journal):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    found = ctx._subagent_transcript_paths(tmp_path / "-Users-x-proj")

    assert found == [sibling, nested]


def test_no_transcripts_found_warns_on_stderr_and_exits_2(tmp_path, monkeypatch, capsys):
    # Redirect Path.home() so `_transcripts_dir` cannot fall through to this
    # machine's real ~/.claude/projects/ and mask the empty-input case.
    monkeypatch.setattr(ctx.Path, "home", lambda: tmp_path / "home")
    empty_project = tmp_path / "empty-project"
    empty_project.mkdir()

    exit_code = ctx.main(["--project-root", str(empty_project), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no session transcripts found" in captured.err
    assert "--project-root" in captured.err

    # Still emits a parseable (empty) report on stdout -- a caller scripting
    # against --json must not get silence just because the exit code is 2.
    report = json.loads(captured.out)
    assert report["sessions"] == 0
    assert report["subagents"] == 0


# --------------------------------------------------------------------------- #
# _agent_types_from_wal -- characterization (pre-migration baseline)
# --------------------------------------------------------------------------- #


def test_agent_types_from_wal_skips_malformed_lines_not_raised(tmp_path):
    wal_path = tmp_path / "observations.jsonl"
    wal_path.write_text(
        "not-json{{{\n"
        + json.dumps({"event_type": "agent_start", "agent_id": "a1", "agent_type": "implementer"})
        + "\n"
        + '{"event_type": "agent_start", "agent_id": "a2", "agent_ty',  # torn tail line
        encoding="utf-8",
    )

    result = ctx._agent_types_from_wal(wal_path)

    assert result == {"a1": "implementer"}


def test_agent_types_from_wal_reads_only_the_active_segment(tmp_path):
    wal_path = tmp_path / "observations.jsonl"
    archive_path = tmp_path / "observations.jsonl.1"
    archive_path.write_text(
        json.dumps(
            {"event_type": "agent_start", "agent_id": "archived", "agent_type": "researcher"}
        )
        + "\n",
        encoding="utf-8",
    )
    wal_path.write_text(
        json.dumps({"event_type": "agent_start", "agent_id": "active", "agent_type": "implementer"})
        + "\n",
        encoding="utf-8",
    )

    result = ctx._agent_types_from_wal(wal_path)

    assert result == {"active": "implementer"}


def test_agent_types_from_wal_returns_empty_for_a_missing_wal(tmp_path):
    assert ctx._agent_types_from_wal(tmp_path / "observations.jsonl") == {}


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores file permission bits; chmod 0o000 would not actually block the read",
)
def test_agent_types_from_wal_raises_wal_unreadable_for_an_unreadable_wal(tmp_path):
    """Unlike a missing WAL (empty `{}`, non-fatal), an unreadable one must
    not silently degrade -- degrading here would relabel every subagent's
    percentile bucket instead of naming the read failure."""
    wal_path = tmp_path / "observations.jsonl"
    wal_path.write_text(
        json.dumps({"event_type": "agent_start", "agent_id": "a1", "agent_type": "implementer"})
        + "\n",
        encoding="utf-8",
    )
    wal_path.chmod(0o000)
    try:
        with pytest.raises(ctx._WalUnreadableError):
            ctx._agent_types_from_wal(wal_path)
    finally:
        wal_path.chmod(0o644)


def test_main_exits_2_with_wal_unreadable_reason_for_an_unreadable_wal(
    tmp_path, monkeypatch, capsys
):
    """`main()`'s CLI contract: an unreadable WAL exits 2 with the named
    reason on stderr and no report on stdout -- distinct from the missing-WAL
    case, which proceeds and prints a report."""
    monkeypatch.setattr(ctx.Path, "home", lambda: tmp_path / "home")
    project_root = tmp_path / "project"
    ai_state = project_root / ".ai-state"
    ai_state.mkdir(parents=True)
    wal_path = ai_state / "observations.jsonl"
    wal_path.write_text(
        json.dumps({"event_type": "agent_start", "agent_id": "a1", "agent_type": "implementer"})
        + "\n",
        encoding="utf-8",
    )
    wal_path.chmod(0o000)
    try:
        exit_code = ctx.main(["--project-root", str(project_root), "--json"])
    finally:
        wal_path.chmod(0o644)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "wal-unreadable" in captured.err
    assert captured.out == ""


# --------------------------------------------------------------------------- #
# (g) cap-outs: spawns whose request count reached their agent's declared maxTurns
# --------------------------------------------------------------------------- #
def _cap_outs(rows: list[dict]) -> dict:
    report = ctx.compute(rows, generated_at=GENERATED_AT, source_root=SOURCE_ROOT)
    return report["cap_outs"]


def test_spawn_at_its_declared_cap_counts_as_capped():
    rows = [
        _subagent_row(requests=100, max_turns=100),
        _subagent_row(requests=106, max_turns=100),  # resumed past the cap: still one spawn
        _subagent_row(requests=36, max_turns=100),
        _subagent_row(requests=99, max_turns=100),
    ]

    assert _cap_outs(rows) == {
        "implementer": {"n": 4, "capped": 2, "rate": 0.5, "max_turns": 100, "basis": "estimate"}
    }


def test_spawns_below_their_declared_cap_are_not_capped():
    rows = [_subagent_row(requests=20, max_turns=80), _subagent_row(requests=79, max_turns=80)]

    entry = _cap_outs(rows)["implementer"]

    assert (entry["n"], entry["capped"], entry["rate"]) == (2, 0, 0.0)


def test_each_agent_type_is_judged_against_its_own_cap():
    rows = [
        _subagent_row(atype="implementer", requests=90, max_turns=100),
        _subagent_row(atype="verifier", requests=90, max_turns=80),
    ]

    cap_outs = _cap_outs(rows)

    assert cap_outs["implementer"]["capped"] == 0
    assert cap_outs["verifier"]["capped"] == 1
    assert cap_outs["verifier"]["max_turns"] == 80


def test_agent_type_with_no_declared_cap_is_left_out():
    rows = [
        _subagent_row(atype="unknown", requests=500, max_turns=None),
        _subagent_row(atype="implementer", requests=10, max_turns=100),
    ]

    assert set(_cap_outs(rows)) == {"implementer"}


def test_cap_outs_rate_is_rounded_to_three_places():
    rows = [_subagent_row(requests=100, max_turns=100)] + [
        _subagent_row(requests=5, max_turns=100) for _ in range(2)
    ]

    assert _cap_outs(rows)["implementer"]["rate"] == 0.333


def test_cap_outs_is_empty_without_subagent_rows():
    assert _cap_outs([_main_row()]) == {}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nname: x\nmaxTurns: 100\n---\nbody\n", 100),
        ("---\nname: x\n---\nmaxTurns: 100\n", None),  # the body is not frontmatter
        ("---\nname: x\nmaxTurnsX: 100\n---\n", None),
        ("name: x\nmaxTurns: 100\n", None),  # no frontmatter block at all
        ("", None),
    ],
)
def test_frontmatter_max_turns_reads_only_the_leading_block(text, expected):
    assert ctx._frontmatter_max_turns(text) == expected


def _write_transcript(path: Path, requests: list[tuple[str, int]]) -> None:
    """A subagent transcript: a first prompt, then per request the given number
    of assistant records sharing one `requestId` (the harness splits a request
    into a thinking record and a tool-use record)."""
    usage = {"input_tokens": 1, "cache_creation_input_tokens": 1, "cache_read_input_tokens": 0}
    lines = [{"type": "user", "message": {"content": "You are the implementer. Task slug: s"}}]
    for request_id, records in requests:
        for _ in range(records):
            lines.append(
                {
                    "type": "assistant",
                    "requestId": request_id,
                    "message": {"id": "msg_" + request_id, "usage": usage, "content": []},
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def _project_with_transcripts(tmp_path, monkeypatch) -> tuple[Path, Path]:
    """(project_root, subagents_dir) with `Path.home()` pointed at `tmp_path`."""
    monkeypatch.setattr(ctx.Path, "home", lambda: tmp_path / "home")
    project_root = tmp_path / "project"
    (project_root / ".ai-state").mkdir(parents=True)
    subagents = ctx._transcripts_dir(project_root) / "sess-1" / "subagents"
    return project_root, subagents


def test_load_counts_distinct_requests_not_assistant_records(tmp_path, monkeypatch):
    project_root, subagents = _project_with_transcripts(tmp_path, monkeypatch)
    _write_transcript(subagents / "agent-a1.jsonl", [("req_1", 2), ("req_2", 2), ("req_3", 1)])
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "implementer.md").write_text("---\nmaxTurns: 3\n---\n", encoding="utf-8")

    (row,) = ctx.load(project_root, agents_dir)

    assert (row["turns"], row["requests"], row["max_turns"]) == (5, 3, 3)
    assert _cap_outs([row])["implementer"]["capped"] == 1


def test_load_leaves_max_turns_unset_when_the_agent_file_is_absent(tmp_path, monkeypatch):
    project_root, subagents = _project_with_transcripts(tmp_path, monkeypatch)
    _write_transcript(subagents / "agent-a1.jsonl", [("req_1", 1)])

    (row,) = ctx.load(project_root, tmp_path / "no-agents-here")

    assert row["max_turns"] is None
    assert _cap_outs([row]) == {}


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores file permission bits; chmod 0o000 would not actually block the read",
)
def test_load_skips_an_unreadable_transcript_and_names_it_on_stderr(tmp_path, monkeypatch, capsys):
    project_root, subagents = _project_with_transcripts(tmp_path, monkeypatch)
    readable = subagents / "agent-a1.jsonl"
    unreadable = subagents / "agent-a2.jsonl"
    _write_transcript(readable, [("req_1", 1)])
    _write_transcript(unreadable, [("req_9", 1)])
    unreadable.chmod(0o000)
    try:
        rows = ctx.load(project_root, tmp_path / "agents")
    finally:
        unreadable.chmod(0o644)

    assert len(rows) == 1
    assert "unreadable transcript" in capsys.readouterr().err
