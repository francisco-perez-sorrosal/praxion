"""Tests for `workflow_run_cost.py` -- the per-run cost reader over a
Workflow-tool run directory (`journal.jsonl` + `agent-<id>.meta.json` +
`agent-<id>.jsonl`, joined against the `.ai-state/observations.jsonl` WAL and
the main-session transcript). Run-directory layout as measured live
2026-09-19 against a real run (the harness's `workflow-authoring` skill is the
upstream reference; a test file cannot load it, so the layout is restated in
the fixture builders below).

Exercised entirely through the real adapter (`main()` / the CLI), never the
pure core directly -- a stubbed-return unit test would pass with the actual
world-read deleted, exactly the failure class the mutation sensor targets for
this instrument's implementation step.

Report envelope (a design choice this suite pins; the implementation was
handed the rationale and satisfied it as written):
    {
      "wf_id": str,
      "agents": [<cost-report row>, ...],      # kind == "workflow-agent"
      "unobserved": [<cost-report row>, ...],   # kind == "unobserved-helper"
      "orchestrator": {launch_turn_tokens, next_turn_tokens, delta, return_bytes},
    }

Cost-report row keys (the full set, exact):
    agent_id, kind, label, phase, agent_type, model, peak_context_tokens,
    output_tokens, turns, tool_uses, duration_ms, transcript, journal_result,
    wal, wal_agreement

Import strategy: `importlib.import_module` (not `spec_from_file_location`,
which raises `FileNotFoundError` for a missing file) so the RED failure mode
is `ModuleNotFoundError`, matching an import that genuinely does not exist
yet -- the same strategy `scripts/test_context_baseline.py` uses.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _load():
    return importlib.import_module("workflow_run_cost")


wfc = _load()


# --------------------------------------------------------------------------- #
# fixture builders -- a synthetic run directory + WAL + main transcript,
# matching the live-measured run-directory layout. Low-level pieces compose
# into `_standard_run()`, the default fully-populated fixture most tests use.
# --------------------------------------------------------------------------- #
_DEFAULT_AGENTS = [
    {
        "agent_id": "agent-econ-001",
        "label": "economy",
        "phase": "Collect",
        "model": "claude-sonnet-5",
        "peak_context": 42_000,
        "output_tokens": 1_800,
    },
    {
        "agent_id": "agent-port-002",
        "label": "portability",
        "phase": "Collect",
        "model": "claude-sonnet-5",
        "peak_context": 39_000,
        "output_tokens": 1_500,
    },
    {
        "agent_id": "agent-aggr-003",
        "label": "aggregator",
        "phase": "Reconcile",
        "model": "claude-opus-5",
        "peak_context": 61_000,
        "output_tokens": 2_600,
    },
]


# The synthetic run's wall-clock window. Every agent-transcript record and every
# in-window WAL row carries a timestamp inside it; the unobserved-helper section
# is windowed by it, so a WAL row outside it belongs to some other run.
_RUN_START = "2026-09-19T10:00:00.000Z"
_RUN_END = "2026-09-19T10:05:00.000Z"
_OUTSIDE_WINDOW = "2026-09-18T08:00:00.000Z"


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _project(tmp_path, monkeypatch):
    """Home + project root pair, with `Path.home()` monkeypatched so the
    instrument's `~/.claude/projects/<mangled>/` resolution lands under
    `tmp_path` instead of this machine's real home directory."""
    home = tmp_path / "home"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(wfc.Path, "home", lambda: home)
    return home, project_root


def _project_transcripts_dir(home, project_root):
    # The harness mangles both "/" and "." to "-" (a worktree under
    # `.claude/worktrees/` lands in `...-praxion--claude-worktrees-...`).
    mangled = str(project_root).replace("/", "-").replace(".", "-")
    return home / ".claude" / "projects" / mangled


def _run_dir(home, project_root, session, wf_id):
    d = _project_transcripts_dir(home, project_root) / session / "subagents" / "workflows" / wf_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_journal(run_dir, agents):
    """The launched/started[/result] triad per agent, keyed by `type` as
    the harness writes it. An agent dict with `"result": False` gets no
    result event -- a started-but-never-resulted roster entry."""
    records = []
    for i, agent in enumerate(agents):
        key = f"call_{i}"
        records.append({"type": "launched", "key": key})
        records.append(
            {
                "type": "started",
                "key": key,
                "agentId": agent["agent_id"],
                "label": agent["label"],
                "phase": agent["phase"],
            }
        )
        if agent.get("result", True):
            records.append(
                {
                    "type": "result",
                    "key": key,
                    "agentId": agent["agent_id"],
                    "result": {"marker": "[COMPLETE]"},
                }
            )
    _write_jsonl(run_dir / "journal.jsonl", records)


def _write_meta(run_dir, agent_id, *, label, phase, agent_type="general-purpose", spawn_depth=1):
    meta = {
        "agentType": agent_type,
        "description": label,
        "workflowPhase": phase,
        "spawnDepth": spawn_depth,
        "requestShape": "single",
        "requestNonInteractive": True,
    }
    (run_dir / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _assistant_turn(model, context_tokens, output_tokens, tool_uses, timestamp=_RUN_START):
    content = [{"type": "text", "text": "..."}]
    content += [
        {"type": "tool_use", "name": "Read", "id": f"toolu_{i}", "input": {}}
        for i in range(tool_uses)
    ]
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": context_tokens,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "output_tokens": output_tokens,
            },
            "content": content,
        },
    }


def _agent_transcript_records(model, peak_context, output_tokens, turns=3, tool_uses=2):
    """One turn carries the peak context tokens and all output tokens; the
    remaining padding turns carry neither -- so `turns` counts distinctly
    from the peak/output totals a single high-water-mark turn would
    otherwise conflate."""
    records = [_assistant_turn(model, peak_context, output_tokens, tool_uses)]
    for _ in range(max(0, turns - 1)):
        records.append(
            _assistant_turn(model, max(1_000, peak_context - 5_000), 0, 0, timestamp=_RUN_END)
        )
    return records


def _write_transcript(run_dir, agent_id, *, model, peak_context, output_tokens):
    _write_jsonl(
        run_dir / f"agent-{agent_id}.jsonl",
        _agent_transcript_records(model, peak_context, output_tokens),
    )


def _main_transcript_records(launch_tokens, next_tokens, wf_id="wf_test0001", tool_id="toolu_wf"):
    """The `Workflow` launch turn, the harness's `tool_result` answering it (which
    names the run directory, hence the `wf_id` -- the key the reader correlates
    on), and the next assistant turn."""
    launch_turn = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-5",
            "usage": {
                "input_tokens": launch_tokens,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "output_tokens": 50,
            },
            "content": [
                {"type": "text", "text": "Launching the fan-out."},
                {
                    "type": "tool_use",
                    "name": "Workflow",
                    "id": tool_id,
                    "input": {"scriptPath": "..."},
                },
            ],
        },
    }
    next_turn = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-5",
            "usage": {
                "input_tokens": next_tokens,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "output_tokens": 120,
            },
            "content": [{"type": "text", "text": "Fan-out complete."}],
        },
    }
    launch_result = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": (
                        "Workflow launched in background. Task ID: task01\n"
                        "Summary: synthetic run.\n"
                        "Transcript dir: /home/x/.claude/projects/p/sess/subagents/workflows/"
                        f"{wf_id}\nRun ID: {wf_id}"
                    ),
                }
            ],
        },
    }
    return [launch_turn, launch_result, next_turn]


def _write_main_transcript(
    home, project_root, session, *, launch_tokens, next_tokens, wf_id="wf_test0001"
):
    _write_jsonl(
        _project_transcripts_dir(home, project_root) / f"{session}.jsonl",
        _main_transcript_records(launch_tokens, next_tokens, wf_id=wf_id),
    )


def _wal_agent_stop(
    agent_id,
    *,
    tokens_in,
    tokens_out,
    cache_read=0,
    cache_create=0,
    model="claude-sonnet-5",
    duration_ms=12_000,
    usage_source="subagent-transcript",
    timestamp=_RUN_START,
):
    return {
        "event_type": "agent_stop",
        "timestamp": timestamp,
        "agent_id": agent_id,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read": cache_read,
        "cache_create": cache_create,
        "model": model,
        "duration_ms": duration_ms,
        "usage_source": usage_source,
    }


def _write_wal(project_root, rows):
    _write_jsonl(project_root / ".ai-state" / "observations.jsonl", rows)


def _standard_run(
    tmp_path,
    monkeypatch,
    *,
    agents=None,
    wal_rows=None,
    main_launch_tokens=205_762,
    main_next_tokens=208_358,
    session="sess-1",
    wf_id="wf_test0001",
):
    """Two `Collect` agents + one `Reconcile` aggregator, a WAL row per
    agent that agrees with its transcript's output tokens, and a main
    transcript carrying the `Workflow` launch turn + the next turn -- the
    fully-populated default fixture most tests start from."""
    agents = agents if agents is not None else [dict(a) for a in _DEFAULT_AGENTS]
    home, project_root = _project(tmp_path, monkeypatch)
    run_dir = _run_dir(home, project_root, session, wf_id)

    _write_journal(run_dir, agents)
    for agent in agents:
        _write_meta(run_dir, agent["agent_id"], label=agent["label"], phase=agent["phase"])
        if agent.get("has_transcript", True):
            _write_transcript(
                run_dir,
                agent["agent_id"],
                model=agent["model"],
                peak_context=agent["peak_context"],
                output_tokens=agent["output_tokens"],
            )
    _write_main_transcript(
        home,
        project_root,
        session,
        launch_tokens=main_launch_tokens,
        next_tokens=main_next_tokens,
        wf_id=wf_id,
    )

    if wal_rows is None:
        wal_rows = [
            _wal_agent_stop(
                agent["agent_id"],
                tokens_in=agent["peak_context"],
                tokens_out=agent["output_tokens"],
            )
            for agent in agents
            if agent.get("has_transcript", True)
        ]
    _write_wal(project_root, wal_rows)

    return project_root, wf_id


def _run_cli(args, capsys):
    exit_code = wfc.main(args)
    return exit_code, capsys.readouterr()


def _run_json(project_root, wf_id, capsys):
    exit_code, captured = _run_cli(
        ["--run", wf_id, "--project-root", str(project_root), "--json"], capsys
    )
    report = json.loads(captured.out) if captured.out.strip() else None
    return exit_code, captured, report


# --------------------------------------------------------------------------- #
# (a) cost-report row shape + envelope, exact
# --------------------------------------------------------------------------- #
def test_workflow_agent_rows_carry_the_exact_cost_report_key_set(tmp_path, monkeypatch, capsys):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    assert report["wf_id"] == wf_id
    assert set(report.keys()) == {"wf_id", "agents", "unobserved", "orchestrator", "window"}
    assert len(report["agents"]) == 3
    for row in report["agents"]:
        assert set(row.keys()) == {
            "agent_id",
            "kind",
            "label",
            "phase",
            "agent_type",
            "model",
            "peak_context_tokens",
            "output_tokens",
            "turns",
            "tool_uses",
            "duration_ms",
            "transcript",
            "journal_result",
            "wal",
            "wal_agreement",
        }
        assert row["kind"] == "workflow-agent"


def test_agent_row_values_reflect_the_journal_meta_and_transcript_for_one_agent(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)

    _, _, report = _run_json(project_root, wf_id, capsys)

    econ = next(row for row in report["agents"] if row["agent_id"] == "agent-econ-001")
    assert econ["label"] == "economy"
    assert econ["phase"] == "Collect"
    assert econ["model"] == "claude-sonnet-5"
    assert econ["peak_context_tokens"] == 42_000
    assert econ["output_tokens"] == 1_800
    assert econ["journal_result"] == "present"
    assert econ["transcript"] is not None


# --------------------------------------------------------------------------- #
# (b) wal_agreement -- all four verdicts, never gates
# --------------------------------------------------------------------------- #
def test_wal_agreement_is_agree_when_wal_tokens_match_transcript_output(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)

    _, _, report = _run_json(project_root, wf_id, capsys)

    for row in report["agents"]:
        assert row["wal_agreement"] == "agree"
        assert row["wal"] is not None


def test_wal_agreement_is_differ_and_the_instrument_still_exits_zero_when_tokens_mismatch(
    tmp_path, monkeypatch, capsys
):
    agents = [dict(a) for a in _DEFAULT_AGENTS]
    mismatched_wal = [
        _wal_agent_stop(
            agents[0]["agent_id"], tokens_in=agents[0]["peak_context"], tokens_out=99_999
        ),
        _wal_agent_stop(
            agents[1]["agent_id"],
            tokens_in=agents[1]["peak_context"],
            tokens_out=agents[1]["output_tokens"],
        ),
        _wal_agent_stop(
            agents[2]["agent_id"],
            tokens_in=agents[2]["peak_context"],
            tokens_out=agents[2]["output_tokens"],
        ),
    ]
    project_root, wf_id = _standard_run(
        tmp_path, monkeypatch, agents=agents, wal_rows=mismatched_wal
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    econ = next(row for row in report["agents"] if row["agent_id"] == "agent-econ-001")
    assert econ["wal_agreement"] == "differ"
    # A measurement instrument never gates on the disagreement it exists to surface.
    assert exit_code == 0


def test_wal_agreement_is_wal_missing_when_no_agent_stop_row_exists(tmp_path, monkeypatch, capsys):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch, wal_rows=[])

    _, _, report = _run_json(project_root, wf_id, capsys)

    for row in report["agents"]:
        assert row["wal_agreement"] == "wal-missing"
        assert row["wal"] is None


def test_wal_agreement_is_transcript_missing_when_an_agent_has_no_transcript_file(
    tmp_path, monkeypatch, capsys
):
    agents = [dict(a) for a in _DEFAULT_AGENTS]
    agents[0]["has_transcript"] = False
    wal_rows = [
        _wal_agent_stop(a["agent_id"], tokens_in=a["peak_context"], tokens_out=a["output_tokens"])
        for a in agents
    ]
    project_root, wf_id = _standard_run(tmp_path, monkeypatch, agents=agents, wal_rows=wal_rows)

    _, _, report = _run_json(project_root, wf_id, capsys)

    missing = next(row for row in report["agents"] if row["agent_id"] == "agent-econ-001")
    assert missing["transcript"] is None
    assert missing["wal_agreement"] == "transcript-missing"
    # The two agents whose transcripts do exist are unaffected by the third's gap.
    assert len(report["agents"]) == 3


# --------------------------------------------------------------------------- #
# (c) journal_result, unobserved-agent helper rows kept separate
# --------------------------------------------------------------------------- #
def test_journal_result_is_absent_when_no_result_event_recorded_for_an_agent(
    tmp_path, monkeypatch, capsys
):
    agents = [dict(a) for a in _DEFAULT_AGENTS]
    agents[1]["result"] = False  # "portability": started, never resulted (died mid-flight)
    project_root, wf_id = _standard_run(tmp_path, monkeypatch, agents=agents)

    _, _, report = _run_json(project_root, wf_id, capsys)

    portability = next(row for row in report["agents"] if row["agent_id"] == "agent-port-002")
    assert portability["journal_result"] == "absent"
    # An unfinished result is reported as a row, never dropped from the roster.
    assert len(report["agents"]) == 3


def test_unobserved_helper_stops_are_reported_separately_and_never_merged_into_agent_rows(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    # A WAL agent_stop row for an agent_id the journal roster never names --
    # the dec-370 unobserved-agent (harness-helper) class.
    wal_path = project_root / ".ai-state" / "observations.jsonl"
    existing = [json.loads(line) for line in wal_path.read_text(encoding="utf-8").splitlines()]
    existing.append(_wal_agent_stop("helper-xyz", tokens_in=800, tokens_out=50))
    _write_wal(project_root, existing)

    _, _, report = _run_json(project_root, wf_id, capsys)

    assert len(report["agents"]) == 3
    assert all(row["agent_id"] != "helper-xyz" for row in report["agents"])
    assert len(report["unobserved"]) == 1
    assert report["unobserved"][0]["agent_id"] == "helper-xyz"
    assert report["unobserved"][0]["kind"] == "unobserved-helper"


# --------------------------------------------------------------------------- #
# (d) orchestrator section
# --------------------------------------------------------------------------- #
def test_orchestrator_section_reports_launch_next_and_delta_tokens(tmp_path, monkeypatch, capsys):
    project_root, wf_id = _standard_run(
        tmp_path, monkeypatch, main_launch_tokens=205_762, main_next_tokens=208_358
    )

    _, _, report = _run_json(project_root, wf_id, capsys)

    assert set(report["orchestrator"].keys()) == {
        "launch_turn_tokens",
        "next_turn_tokens",
        "delta",
        "return_bytes",
    }
    assert report["orchestrator"]["launch_turn_tokens"] == 205_762
    assert report["orchestrator"]["next_turn_tokens"] == 208_358
    assert report["orchestrator"]["delta"] == 208_358 - 205_762
    # the harness's tool_result answering the launch is measured, not left null
    assert report["orchestrator"]["return_bytes"] > 0


def test_session_flag_overrides_the_default_main_transcript_path(tmp_path, monkeypatch, capsys):
    agents = [dict(a) for a in _DEFAULT_AGENTS]
    home, project_root = _project(tmp_path, monkeypatch)
    run_dir = _run_dir(home, project_root, "sess-1", "wf_test0001")
    _write_journal(run_dir, agents)
    for agent in agents:
        _write_meta(run_dir, agent["agent_id"], label=agent["label"], phase=agent["phase"])
        _write_transcript(
            run_dir,
            agent["agent_id"],
            model=agent["model"],
            peak_context=agent["peak_context"],
            output_tokens=agent["output_tokens"],
        )
    _write_wal(
        project_root,
        [
            _wal_agent_stop(
                a["agent_id"], tokens_in=a["peak_context"], tokens_out=a["output_tokens"]
            )
            for a in agents
        ],
    )
    # The default sibling-of-the-run-directory resolution would look for
    # sess-1.jsonl -- deliberately never written, so only --session can supply
    # the orchestrator numbers.
    other_transcript = _project_transcripts_dir(home, project_root) / "sess-2.jsonl"
    _write_jsonl(other_transcript, _main_transcript_records(999_000, 1_005_000))

    exit_code, captured = _run_cli(
        [
            "--run",
            "wf_test0001",
            "--project-root",
            str(project_root),
            "--session",
            str(other_transcript),
            "--json",
        ],
        capsys,
    )
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["orchestrator"]["launch_turn_tokens"] == 999_000


# --------------------------------------------------------------------------- #
# (e) CLI surface -- --list, --table
# --------------------------------------------------------------------------- #
def test_list_flag_enumerates_known_runs_with_timestamps(tmp_path, monkeypatch, capsys):
    home, project_root = _project(tmp_path, monkeypatch)
    seed = _DEFAULT_AGENTS[0]
    for session, wf_id in (("sess-1", "wf_aaaa0001"), ("sess-2", "wf_bbbb0002")):
        run_dir = _run_dir(home, project_root, session, wf_id)
        _write_journal(run_dir, [seed])
        _write_meta(run_dir, seed["agent_id"], label=seed["label"], phase=seed["phase"])
        _write_transcript(
            run_dir,
            seed["agent_id"],
            model=seed["model"],
            peak_context=seed["peak_context"],
            output_tokens=seed["output_tokens"],
        )

    exit_code, captured = _run_cli(
        ["--list", "--project-root", str(project_root), "--json"], capsys
    )
    runs = json.loads(captured.out)

    assert exit_code == 0
    found_ids = {run["wf_id"] for run in runs}
    assert found_ids == {"wf_aaaa0001", "wf_bbbb0002"}
    assert all("launched_at" in run for run in runs)


def test_project_root_with_dotted_segments_resolves_the_harness_directory(
    tmp_path, monkeypatch, capsys
):
    home = tmp_path / "home"
    project_root = tmp_path / ".claude" / "worktrees" / "wt"
    project_root.mkdir(parents=True)
    monkeypatch.setattr(wfc.Path, "home", lambda: home)
    seed = _DEFAULT_AGENTS[0]
    run_dir = _run_dir(home, project_root, "sess-1", "wf_dotted001")
    _write_journal(run_dir, [seed])
    _write_meta(run_dir, seed["agent_id"], label=seed["label"], phase=seed["phase"])
    _write_transcript(
        run_dir,
        seed["agent_id"],
        model=seed["model"],
        peak_context=seed["peak_context"],
        output_tokens=seed["output_tokens"],
    )

    exit_code, captured = _run_cli(
        ["--list", "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 0
    assert {run["wf_id"] for run in json.loads(captured.out)} == {"wf_dotted001"}


def test_table_output_names_the_run_in_human_readable_form(tmp_path, monkeypatch, capsys):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)

    exit_code, captured = _run_cli(
        ["--run", wf_id, "--project-root", str(project_root), "--table"], capsys
    )

    assert exit_code == 0
    assert wf_id in captured.out
    assert "economy" in captured.out


# --------------------------------------------------------------------------- #
# (f) exit 2 + named reason -- run-not-found, run-ambiguous,
# journal-unreadable, run-empty, transcripts-missing
# --------------------------------------------------------------------------- #
def test_exits_2_with_run_not_found_reason_for_unknown_wf_id(tmp_path, monkeypatch, capsys):
    project_root, _ = _standard_run(tmp_path, monkeypatch)

    exit_code, captured = _run_cli(
        ["--run", "wf_does_not_exist", "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "run-not-found" in captured.err


def test_exits_2_with_run_ambiguous_reason_when_latest_is_tied_between_two_runs(
    tmp_path, monkeypatch, capsys
):
    home, project_root = _project(tmp_path, monkeypatch)
    seed = _DEFAULT_AGENTS[0]
    journals = []
    for session, wf_id in (("sess-1", "wf_aaaa0001"), ("sess-2", "wf_bbbb0002")):
        run_dir = _run_dir(home, project_root, session, wf_id)
        _write_journal(run_dir, [seed])
        journals.append(run_dir / "journal.jsonl")
    # "latest" is resolved by newest journal mtime; an exact tie makes
    # that resolution genuinely ambiguous rather than arbitrary.
    tied_time = 1_726_800_000
    for journal in journals:
        os.utime(journal, (tied_time, tied_time))

    exit_code, captured = _run_cli(
        ["--run", "latest", "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "run-ambiguous" in captured.err


def test_exits_2_with_journal_unreadable_reason_when_journal_is_malformed(
    tmp_path, monkeypatch, capsys
):
    home, project_root = _project(tmp_path, monkeypatch)
    run_dir = _run_dir(home, project_root, "sess-1", "wf_test0001")
    (run_dir / "journal.jsonl").write_text("not valid json\n{also not valid\n", encoding="utf-8")

    exit_code, captured = _run_cli(
        ["--run", "wf_test0001", "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "journal-unreadable" in captured.err


def test_exits_2_with_run_empty_reason_when_journal_has_no_agent_rows(
    tmp_path, monkeypatch, capsys
):
    home, project_root = _project(tmp_path, monkeypatch)
    run_dir = _run_dir(home, project_root, "sess-1", "wf_test0001")
    (run_dir / "journal.jsonl").write_text("", encoding="utf-8")

    exit_code, captured = _run_cli(
        ["--run", "wf_test0001", "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "run-empty" in captured.err


def test_exits_2_with_transcripts_missing_reason_when_no_agent_transcripts_exist_on_disk(
    tmp_path, monkeypatch, capsys
):
    home, project_root = _project(tmp_path, monkeypatch)
    run_dir = _run_dir(home, project_root, "sess-1", "wf_test0001")
    agents = [dict(a) for a in _DEFAULT_AGENTS]
    _write_journal(run_dir, agents)
    for agent in agents:
        _write_meta(run_dir, agent["agent_id"], label=agent["label"], phase=agent["phase"])
    # No agent-<id>.jsonl written for anyone: the roster exists but zero
    # transcripts can be attributed to it on disk.

    exit_code, captured = _run_cli(
        ["--run", "wf_test0001", "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "transcripts-missing" in captured.err


# --------------------------------------------------------------------------- #
# the harness's own journal shape, verbatim -- the discriminator key is `type`
# --------------------------------------------------------------------------- #
def test_journal_keyed_by_type_as_the_harness_writes_it_populates_the_roster(
    tmp_path, monkeypatch, capsys
):
    """A literal journal in the shape the Workflow tool wrote on the first
    live run (2026-09-21): `{"type": "launched"}` with no key, then
    `started`/`result` records discriminated by `type`. Independent of
    `_write_journal` on purpose -- a fixture that mirrors an invented key
    keeps a suite green while every live run reads `run-empty`."""
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    home = tmp_path / "home"
    run_dir = _run_dir(home, project_root, "sess-1", wf_id)
    harness_journal = [
        {"type": "launched"},
        {
            "type": "started",
            "key": "v2:aaa",
            "agentId": "agent-econ-001",
            "label": "economy",
            "phase": "Collect",
        },
        {
            "type": "started",
            "key": "v2:bbb",
            "agentId": "agent-port-002",
            "label": "portability",
            "phase": "Collect",
        },
        {
            "type": "result",
            "key": "v2:aaa",
            "agentId": "agent-econ-001",
            "result": {"marker": "[COMPLETE]"},
        },
        {
            "type": "result",
            "key": "v2:bbb",
            "agentId": "agent-port-002",
            "result": {"marker": "[COMPLETE]"},
        },
        {
            "type": "started",
            "key": "v2:ccc",
            "agentId": "agent-aggr-003",
            "label": "reconcile",
            "phase": "Reconcile",
        },
        {
            "type": "result",
            "key": "v2:ccc",
            "agentId": "agent-aggr-003",
            "result": {"marker": "[COMPLETE]"},
        },
    ]
    _write_jsonl(run_dir / "journal.jsonl", harness_journal)

    exit_code, captured, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 0, captured.err
    assert {row["agent_id"]: row["journal_result"] for row in report["agents"]} == {
        "agent-econ-001": "present",
        "agent-port-002": "present",
        "agent-aggr-003": "present",
    }


# --------------------------------------------------------------------------- #
# the orchestrator section is keyed by the run, never by launch position
# --------------------------------------------------------------------------- #
def test_orchestrator_section_is_keyed_by_the_run_id_not_the_first_workflow_launch(
    tmp_path, monkeypatch, capsys
):
    """A session holding two fan-outs: `--run` on the second must report the
    second launch's turns. The harness's `tool_result` names the run
    directory, so the launch is found by that key -- the module's own
    "never by position" contract applied to its one positional read."""
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    home = tmp_path / "home"
    records = _main_transcript_records(100_000, 101_000, wf_id="wf_other0001", tool_id="toolu_a")
    records += _main_transcript_records(205_762, 208_358, wf_id=wf_id, tool_id="toolu_b")
    _write_jsonl(_project_transcripts_dir(home, project_root) / "sess-1.jsonl", records)

    _, _, report = _run_json(project_root, wf_id, capsys)

    assert report["orchestrator"]["launch_turn_tokens"] == 205_762
    assert report["orchestrator"]["next_turn_tokens"] == 208_358
    assert report["orchestrator"]["delta"] == 208_358 - 205_762


def test_orchestrator_section_is_null_when_no_launch_in_the_session_names_the_run(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _write_jsonl(
        _project_transcripts_dir(home, project_root) / "sess-1.jsonl",
        _main_transcript_records(100_000, 101_000, wf_id="wf_other0001"),
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    assert report["orchestrator"] == {
        "launch_turn_tokens": None,
        "next_turn_tokens": None,
        "delta": None,
        "return_bytes": None,
    }


# --------------------------------------------------------------------------- #
# unobserved helpers are windowed to the run's own wall-clock span
# --------------------------------------------------------------------------- #
def test_unobserved_helper_rows_are_windowed_to_the_run_and_carry_their_attribution(
    tmp_path, monkeypatch, capsys
):
    """The WAL spans every session of the project; a helper stop outside the
    run's transcript window is some other run's business. Every row that
    survives the window says how it got there."""
    from datetime import datetime

    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    wal_path = project_root / ".ai-state" / "observations.jsonl"
    existing = [json.loads(line) for line in wal_path.read_text(encoding="utf-8").splitlines()]
    existing.append(_wal_agent_stop("helper-in", tokens_in=800, tokens_out=50))
    existing.append(
        _wal_agent_stop("helper-out", tokens_in=800, tokens_out=50, timestamp=_OUTSIDE_WINDOW)
    )
    _write_wal(project_root, existing)

    _, _, report = _run_json(project_root, wf_id, capsys)

    assert [row["agent_id"] for row in report["unobserved"]] == ["helper-in"]
    assert report["unobserved"][0]["attribution"] == "time-window-heuristic"
    assert report["window"] == {
        "start": datetime.fromisoformat(_RUN_START.replace("Z", "+00:00")).isoformat(),
        "end": datetime.fromisoformat(_RUN_END.replace("Z", "+00:00")).isoformat(),
    }


# --------------------------------------------------------------------------- #
# a partly corrupt journal is refused, not read as a smaller roster
# --------------------------------------------------------------------------- #
def test_exits_2_with_journal_unreadable_reason_when_any_journal_line_is_malformed(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    home = tmp_path / "home"
    journal = _run_dir(home, project_root, "sess-1", wf_id) / "journal.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")

    exit_code, captured = _run_cli(
        ["--run", wf_id, "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "journal-unreadable" in captured.err
