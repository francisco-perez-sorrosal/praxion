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
    turns        number of assistant turns
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
import sys
from pathlib import Path

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
) -> dict:
    """A subagent row -- one spawned agent's transcript."""
    return {
        "kind": "subagent",
        "atype": atype,
        "slug": slug,
        "peak": peak,
        "first_turn": first_turn,
        "turns": turns,
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
