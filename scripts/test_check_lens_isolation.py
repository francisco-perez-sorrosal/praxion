"""Tests for `check_lens_isolation.py` -- the guard that fires truly or
refuses (dec-378's mandate): every `Collect`-phase transcript must be free of
its siblings' *artifact identity* -- never a bare lens label. Run-directory
layout is `WORKFLOW_CONTRACT.md § Where the run lands`, measured live
2026-09-19 -- this test file cannot load the harness's own `workflow-authoring`
skill and cites that document instead.

Exercised entirely through the real adapter (`main()` / the CLI), never the
pure core directly -- a stubbed-return unit test would pass with the actual
transcript read deleted.

Needle set (O3, artifact-identity only, never vocabulary): for a target
`Collect` agent A, and every sibling B with phase `Collect` and B != A --
`RESEARCH_<B.label>.md` (B's `fragment_path`, DS2 shape), `B.agent_id`, and
`B.summary` verbatim when >=40 chars. A bare lens label (e.g. the word
"portability") is never a needle and must never produce a finding.

Report envelope + finding shape (a design choice this suite pins, not
otherwise fixed in `SYSTEMS_PLAN.md § I4/S3` beyond the finding codes and
exit-code contract -- see `LEARNINGS.md` for the full rationale handed to the
implementer):
    {"wf_id": str, "findings": [<finding>, ...]}
    <finding> := {"code": "LI01", "agent_id": str, "sibling_agent_id": str,
                  "needle_kind": "fragment_path" | "agent_id" | "summary"}
              |  {"code": "LI02", "agent_id": str}
A main-session finding (`--include-main`) uses the sentinel `agent_id`
`"main-session"` -- the main transcript is not a rostered workflow agent.

Import strategy: `importlib.import_module` (not `spec_from_file_location`,
which raises `FileNotFoundError` for a missing file) so the RED failure mode
is `ModuleNotFoundError`, matching an import that genuinely does not exist
yet -- the same strategy `scripts/test_workflow_run_cost.py` uses.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _load():
    return importlib.import_module("check_lens_isolation")


cli = _load()


# --------------------------------------------------------------------------- #
# fixture builders -- a synthetic run directory + main transcript, matching
# WORKFLOW_CONTRACT.md's measured layout and DS2's lens-return shape. Low-level
# pieces compose into `_standard_run()`, the default clean fixture most tests
# start from.
# --------------------------------------------------------------------------- #
_SLUG = "demo-slug"

# A summary >=40 chars, per O3's needle-set threshold -- short enough to read,
# long enough to qualify as a verbatim-summary needle.
_ECON_SUMMARY = "Economy lens: subscription pricing dominates unit cost."
_PORT_SUMMARY = "Portability lens: cross-runtime packaging drives the cost curve."

_DEFAULT_AGENTS = [
    {
        "agent_id": "agent-econ-001",
        "label": "economy",
        "phase": "Collect",
        "summary": _ECON_SUMMARY,
        "claims_count": 4,
        "certainty": "high",
    },
    {
        "agent_id": "agent-port-002",
        "label": "portability",
        "phase": "Collect",
        "summary": _PORT_SUMMARY,
        "claims_count": 3,
        "certainty": "medium",
    },
    {
        "agent_id": "agent-aggr-003",
        "label": "aggregator",
        "phase": "Reconcile",
        "summary": None,
        "claims_count": None,
        "certainty": None,
    },
]


def _fragment_path(label: str) -> str:
    return f".ai-work/{_SLUG}/RESEARCH_{label}.md"


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _project(tmp_path, monkeypatch):
    """Home + project root pair, with `Path.home()` monkeypatched so the
    guard's `~/.claude/projects/<mangled>/` resolution lands under
    `tmp_path` instead of this machine's real home directory."""
    home = tmp_path / "home"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli.Path, "home", lambda: home)
    return home, project_root


def _project_transcripts_dir(home, project_root):
    mangled = str(project_root).replace("/", "-")
    return home / ".claude" / "projects" / mangled


def _run_dir(home, project_root, session, wf_id):
    d = _project_transcripts_dir(home, project_root) / session / "subagents" / "workflows" / wf_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_journal(run_dir, agents):
    """The launched/started/result triad per agent, with each `Collect`
    agent's `result` carrying the full DS2 (`LENS_SCHEMA`) shape -- the
    source of the artifact-identity needle set (S3). The `Reconcile`
    aggregator's result is a bare completion marker; its own identity is
    never part of the needle set (S3 draws needles from `Collect` siblings
    only)."""
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
        if agent["phase"] == "Collect":
            result = {
                "marker": "[COMPLETE]",
                "lens": agent["label"],
                "fragment_path": _fragment_path(agent["label"]),
                "claims_count": agent["claims_count"],
                "certainty": agent["certainty"],
                "summary": agent["summary"],
            }
        else:
            result = {"marker": "[COMPLETE]"}
        records.append(
            {"type": "result", "key": key, "agentId": agent["agent_id"], "result": result}
        )
    _write_jsonl(run_dir / "journal.jsonl", records)


def _write_meta(run_dir, agent_id, *, label, phase):
    meta = {
        "agentType": "general-purpose",
        "description": label,
        "workflowPhase": phase,
        "spawnDepth": 1,
        "requestShape": "single",
        "requestNonInteractive": True,
    }
    (run_dir / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _assistant_turn(texts):
    return {
        "type": "assistant",
        "message": {
            "model": "claude-sonnet-5",
            "usage": {
                "input_tokens": 1_000,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "output_tokens": 200,
            },
            "content": [{"type": "text", "text": text} for text in texts],
        },
    }


def _write_transcript(run_dir, agent_id, texts):
    """A single-turn transcript whose text content is exactly `texts` --
    the vehicle for planting (or omitting) a contamination needle."""
    _write_jsonl(run_dir / f"agent-{agent_id}.jsonl", [_assistant_turn(texts)])


def _write_main_transcript(home, project_root, session, texts):
    _write_jsonl(
        _project_transcripts_dir(home, project_root) / f"{session}.jsonl", [_assistant_turn(texts)]
    )


def _standard_run(
    tmp_path,
    monkeypatch,
    *,
    agents=None,
    texts_by_agent=None,
    write_transcript_for=None,
    session="sess-1",
    wf_id="wf_test0001",
):
    """Two `Collect` agents + one `Reconcile` aggregator, every transcript
    clean by default (no sibling needles) -- the fully-populated default
    fixture most tests start from. `texts_by_agent` overrides one or more
    agents' transcript text content (the contamination vehicle);
    `write_transcript_for` restricts which agents get a transcript file at
    all (default: every agent)."""
    agents = agents if agents is not None else [dict(a) for a in _DEFAULT_AGENTS]
    texts_by_agent = texts_by_agent or {}
    write_transcript_for = (
        write_transcript_for
        if write_transcript_for is not None
        else [a["agent_id"] for a in agents]
    )
    home, project_root = _project(tmp_path, monkeypatch)
    run_dir = _run_dir(home, project_root, session, wf_id)

    _write_journal(run_dir, agents)
    for agent in agents:
        _write_meta(run_dir, agent["agent_id"], label=agent["label"], phase=agent["phase"])
        if agent["agent_id"] in write_transcript_for:
            default_text = [f"Working on the {agent['label']} lens."]
            _write_transcript(
                run_dir, agent["agent_id"], texts_by_agent.get(agent["agent_id"], default_text)
            )
    return project_root, wf_id


def _run_cli(args, capsys):
    exit_code = cli.main(args)
    return exit_code, capsys.readouterr()


def _run_json(project_root, wf_id, capsys, extra_args=None):
    args = ["--run", wf_id, "--project-root", str(project_root), "--json"]
    args += extra_args or []
    exit_code, captured = _run_cli(args, capsys)
    report = json.loads(captured.out) if captured.out.strip() else None
    return exit_code, captured, report


# --------------------------------------------------------------------------- #
# (a) positive contamination -- artifact-identity needles, one per kind
# --------------------------------------------------------------------------- #
def test_sibling_fragment_path_in_a_collect_transcript_reports_li01_and_exits_1(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={
            "agent-econ-001": [f"Also see {_fragment_path('portability')} for context."]
        },
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 1
    li01 = [f for f in report["findings"] if f["code"] == "LI01"]
    assert len(li01) == 1
    assert li01[0]["agent_id"] == "agent-econ-001"
    assert li01[0]["sibling_agent_id"] == "agent-port-002"
    assert li01[0]["needle_kind"] == "fragment_path"


def test_sibling_agent_id_in_a_collect_transcript_reports_li01(tmp_path, monkeypatch, capsys):
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={"agent-econ-001": ["See agent-port-002's earlier notes."]},
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 1
    li01 = [f for f in report["findings"] if f["code"] == "LI01"]
    assert len(li01) == 1
    assert li01[0]["needle_kind"] == "agent_id"


def test_sibling_summary_verbatim_in_a_collect_transcript_reports_li01(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={"agent-econ-001": [f"I recall reading: {_PORT_SUMMARY}"]},
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 1
    li01 = [f for f in report["findings"] if f["code"] == "LI01"]
    assert len(li01) == 1
    assert li01[0]["needle_kind"] == "summary"


def test_bare_lens_label_in_a_sibling_transcript_is_not_a_finding(tmp_path, monkeypatch, capsys):
    # "portability" is an ordinary domain word (O3) -- naming it in prose is
    # not evidence of contamination, only artifact identity is.
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={
            "agent-econ-001": [
                "Portability of subscription pricing across regions is out of scope here."
            ]
        },
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    assert report["findings"] == []


# --------------------------------------------------------------------------- #
# (b) vacuous-run refusal -- fewer than two Collect transcripts
# --------------------------------------------------------------------------- #
def test_run_with_zero_collect_transcripts_exits_2_insufficient_collect_agents(
    tmp_path, monkeypatch, capsys
):
    # Only the Reconcile aggregator is rostered -- no Collect agent at all.
    agents = [dict(a) for a in _DEFAULT_AGENTS if a["phase"] == "Reconcile"]
    project_root, wf_id = _standard_run(tmp_path, monkeypatch, agents=agents)

    exit_code, captured = _run_cli(
        ["--run", wf_id, "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "insufficient-collect-agents" in captured.err


def test_run_with_only_one_collect_transcript_on_disk_exits_2_insufficient_collect_agents(
    tmp_path, monkeypatch, capsys
):
    # Two Collect agents rostered, but only one has a transcript on disk --
    # the guard can only compare one side, so it refuses rather than pass
    # vacuously (SYSTEMS_PLAN.md § Step Risk Tags: "a guard tested only on
    # clean input is untested").
    project_root, wf_id = _standard_run(
        tmp_path, monkeypatch, write_transcript_for=["agent-econ-001", "agent-aggr-003"]
    )

    exit_code, captured = _run_cli(
        ["--run", wf_id, "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "insufficient-collect-agents" in captured.err


# --------------------------------------------------------------------------- #
# (c) aggregator exemption -- legitimately holds every sibling fragment path
# --------------------------------------------------------------------------- #
def test_aggregator_transcript_holding_every_fragment_path_is_excluded_from_the_needle_search(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={
            # The aggregator is *supposed* to read every fragment -- this is
            # legitimate Reconcile behaviour, not contamination, and it must
            # never be searched as a target.
            "agent-aggr-003": [
                f"Reading {_fragment_path('economy')} and {_fragment_path('portability')}."
            ]
        },
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    assert report["findings"] == []


# --------------------------------------------------------------------------- #
# (d) --include-main -- search the main-session transcript for the same
# artifact-identity needle set
# --------------------------------------------------------------------------- #
def test_include_main_flag_detects_a_planted_needle_in_the_main_session_transcript(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    home = cli.Path.home()
    _write_main_transcript(
        home, project_root, "sess-1", [f"Launching lenses; see {_fragment_path('economy')}."]
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys, extra_args=["--include-main"])

    assert exit_code == 1
    li01 = [f for f in report["findings"] if f["code"] == "LI01"]
    assert len(li01) == 1
    assert li01[0]["agent_id"] == "main-session"


def test_include_main_flag_reports_clean_when_the_main_transcript_has_no_needles(
    tmp_path, monkeypatch, capsys
):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)
    home = cli.Path.home()
    _write_main_transcript(home, project_root, "sess-1", ["Launching the fan-out."])

    exit_code, _, report = _run_json(project_root, wf_id, capsys, extra_args=["--include-main"])

    assert exit_code == 0
    assert report["findings"] == []


# --------------------------------------------------------------------------- #
# LI02 -- a rostered Collect agent with no transcript (warn, not a refusal
# when at least two other Collect transcripts remain comparable)
# --------------------------------------------------------------------------- #
def test_rostered_collect_agent_with_no_transcript_reports_li02_and_still_exits_0_when_clean(
    tmp_path, monkeypatch, capsys
):
    agents = [dict(a) for a in _DEFAULT_AGENTS]
    agents.append(
        {
            "agent_id": "agent-miss-004",
            "label": "recovery",
            "phase": "Collect",
            "summary": "Recovery-handshake lens: retries dominate the cost of a partial run.",
            "claims_count": 2,
            "certainty": "low",
        }
    )
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        agents=agents,
        write_transcript_for=["agent-econ-001", "agent-port-002", "agent-aggr-003"],
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    li02 = [f for f in report["findings"] if f["code"] == "LI02"]
    assert li02 == [{"code": "LI02", "agent_id": "agent-miss-004"}]


# --------------------------------------------------------------------------- #
# run-not-found / journal-unreadable exit-2 reasons
# --------------------------------------------------------------------------- #
def test_exits_2_with_run_not_found_reason_for_unknown_wf_id(tmp_path, monkeypatch, capsys):
    project_root, _ = _standard_run(tmp_path, monkeypatch)

    exit_code, captured = _run_cli(
        ["--run", "wf_does_not_exist", "--project-root", str(project_root), "--json"], capsys
    )

    assert exit_code == 2
    assert "run-not-found" in captured.err


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


# --------------------------------------------------------------------------- #
# --json / --table output shapes
# --------------------------------------------------------------------------- #
def test_json_output_reports_wf_id_and_empty_findings_on_a_clean_run(tmp_path, monkeypatch, capsys):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 0
    assert report == {"wf_id": wf_id, "findings": []}


def test_table_output_names_the_run_and_a_collect_agent_label(tmp_path, monkeypatch, capsys):
    project_root, wf_id = _standard_run(tmp_path, monkeypatch)

    exit_code, captured = _run_cli(
        ["--run", wf_id, "--project-root", str(project_root), "--table"], capsys
    )

    assert exit_code == 0
    assert wf_id in captured.out
    assert "economy" in captured.out


# --------------------------------------------------------------------------- #
# the harness's own journal shape, verbatim -- the discriminator key is `type`
# --------------------------------------------------------------------------- #
def test_journal_keyed_by_type_as_the_harness_writes_it_yields_the_needle_set(
    tmp_path, monkeypatch, capsys
):
    """A literal journal in the shape the Workflow tool wrote on the first
    live run (2026-09-21), discriminated by `type`, with a planted sibling
    fragment path in the economy transcript. Both the roster and the needle
    derivation read the journal; a fixture mirroring an invented key would
    keep the suite green while the live guard reads `run-empty` -- or,
    one level down, derives an empty needle set and reports clean."""
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={"agent-econ-001": [f"See {_fragment_path('portability')} for detail."]},
    )
    home = tmp_path / "home"
    run_dir = _run_dir(home, project_root, "sess-1", wf_id)

    def lens_result(label, agent):
        return {
            "marker": "[COMPLETE]",
            "lens": label,
            "fragment_path": _fragment_path(label),
            "claims_count": agent["claims_count"],
            "certainty": agent["certainty"],
            "summary": agent["summary"],
        }

    econ, port, aggr = _DEFAULT_AGENTS
    harness_journal = [
        {"type": "launched"},
        {
            "type": "started",
            "key": "v2:aaa",
            "agentId": econ["agent_id"],
            "label": "economy",
            "phase": "Collect",
        },
        {
            "type": "started",
            "key": "v2:bbb",
            "agentId": port["agent_id"],
            "label": "portability",
            "phase": "Collect",
        },
        {
            "type": "result",
            "key": "v2:aaa",
            "agentId": econ["agent_id"],
            "result": lens_result("economy", econ),
        },
        {
            "type": "result",
            "key": "v2:bbb",
            "agentId": port["agent_id"],
            "result": lens_result("portability", port),
        },
        {
            "type": "started",
            "key": "v2:ccc",
            "agentId": aggr["agent_id"],
            "label": "reconcile",
            "phase": "Reconcile",
        },
        {
            "type": "result",
            "key": "v2:ccc",
            "agentId": aggr["agent_id"],
            "result": {"marker": "[COMPLETE]"},
        },
    ]
    _write_jsonl(run_dir / "journal.jsonl", harness_journal)

    exit_code, captured, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 1, captured.err
    assert {
        (f["code"], f["agent_id"], f["sibling_agent_id"], f["needle_kind"])
        for f in report["findings"]
    } == {("LI01", econ["agent_id"], port["agent_id"], "fragment_path")}


# --------------------------------------------------------------------------- #
# every matching needle kind is reported -- a pointer hit never masks a payload hit
# --------------------------------------------------------------------------- #
def test_every_matching_needle_kind_is_reported_per_sibling(tmp_path, monkeypatch, capsys):
    """Under `--include-main` a completed run always hits `fragment_path` (the
    pointer return delivers it); if that hit swallowed the `summary` kind the
    flag could never report the one leak it exists to catch."""
    econ, port = _DEFAULT_AGENTS[0], _DEFAULT_AGENTS[1]
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={
            econ["agent_id"]: [
                f"See {_fragment_path('portability')}.",
                f"Sibling {port['agent_id']}.",
            ]
        },
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 1
    assert {
        (f["agent_id"], f["sibling_agent_id"], f["needle_kind"]) for f in report["findings"]
    } == {
        (econ["agent_id"], port["agent_id"], "fragment_path"),
        (econ["agent_id"], port["agent_id"], "agent_id"),
    }


def test_absolute_fragment_path_in_the_journal_still_matches_a_relative_quote(
    tmp_path, monkeypatch, capsys
):
    """A lens may return its fragment path absolute or repo-relative; the
    needle is the repo-relative tail either way, so a sibling quoting either
    form is caught."""
    econ, port, aggr = _DEFAULT_AGENTS
    project_root, wf_id = _standard_run(
        tmp_path,
        monkeypatch,
        texts_by_agent={econ["agent_id"]: [f"See {_fragment_path('portability')} for detail."]},
    )
    home = tmp_path / "home"
    run_dir = _run_dir(home, project_root, "sess-1", wf_id)

    def result(label, agent, fragment_path):
        return {
            "marker": "[COMPLETE]",
            "lens": label,
            "fragment_path": fragment_path,
            "claims_count": agent["claims_count"],
            "certainty": agent["certainty"],
            "summary": agent["summary"],
        }

    absolute_port = f"/abs/worktree/{_fragment_path('portability')}"
    _write_jsonl(
        run_dir / "journal.jsonl",
        [
            {"type": "launched"},
            {
                "type": "started",
                "key": "a",
                "agentId": econ["agent_id"],
                "label": "economy",
                "phase": "Collect",
            },
            {
                "type": "started",
                "key": "b",
                "agentId": port["agent_id"],
                "label": "portability",
                "phase": "Collect",
            },
            {
                "type": "result",
                "key": "a",
                "agentId": econ["agent_id"],
                "result": result("economy", econ, _fragment_path("economy")),
            },
            {
                "type": "result",
                "key": "b",
                "agentId": port["agent_id"],
                "result": result("portability", port, absolute_port),
            },
            {
                "type": "started",
                "key": "c",
                "agentId": aggr["agent_id"],
                "label": "reconcile",
                "phase": "Reconcile",
            },
            {
                "type": "result",
                "key": "c",
                "agentId": aggr["agent_id"],
                "result": {"marker": "[COMPLETE]"},
            },
        ],
    )

    exit_code, _, report = _run_json(project_root, wf_id, capsys)

    assert exit_code == 1
    assert [
        (f["agent_id"], f["sibling_agent_id"], f["needle_kind"]) for f in report["findings"]
    ] == [(econ["agent_id"], port["agent_id"], "fragment_path")]
