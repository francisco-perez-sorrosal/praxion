#!/usr/bin/env python3
"""Lens-isolation guard over a Workflow-tool run directory: every `Collect`
transcript must be free of its siblings' **artifact identity**.

A **gate**, not a measurement instrument -- and a gate whose only real danger
is passing vacuously. A run it could not actually compare (fewer than two
`Collect` transcripts on disk) is refused with exit 2, never reported clean:
"no contamination found" and "nothing was searched" must not share an exit
code.

Needle set -- artifact identity only. For a target transcript, every *other*
`Collect` agent contributes up to three needles: its fragment path, its agent
id, and its return summary verbatim when long enough to be unmistakable. A
bare lens label ("portability") is an ordinary domain word every lens is free
to use, so it is never a needle; matching on vocabulary would turn the guard
into a thesaurus and produce a finding on correct work.

Needles are drawn from the journal's own `result` payloads -- the lens returns
the launch already recorded -- rather than from a second read of the fragment
files, so the identity set has one source of truth.

Run-directory layout, journal parsing and transcript access are shared with
`workflow_run_cost.py` through the sibling module `_workflow_run.py`; this file
owns only the needle derivation, the search, and the report shape below.

Report envelope:
    {"wf_id": str, "findings": [<finding>, ...]}

Findings:
    {"code": "LI01", "agent_id": str, "sibling_agent_id": str,
     "needle_kind": "fragment_path" | "agent_id" | "summary"}
        one per violating (searched transcript, sibling, needle kind) triple
    {"code": "LI02", "agent_id": str}
        a transcript the search was meant to cover and could not read -- a
        rostered `Collect` agent with no file on disk, or (under
        `--include-main`) an absent main-session transcript. A gap in
        coverage, reported rather than swallowed, but not itself a violation

Under `--include-main` the main-session transcript is searched with the same
needle implementation, against every `Collect` agent's needles; it is not a
rostered workflow agent, so its findings carry the sentinel agent id
`main-session`.

Two layers, mirroring `workflow_run_cost.py`'s split:

    load(...)    -> dict   all I/O -- resolves the run, reads the journal and
                            the transcripts it is allowed to search
    compute(...) -> dict   pure needle search over `load()`'s raw materials

Exit codes: 0 clean, 1 when any `LI01` fired, 2 with a named reason
(`run-not-found`, `journal-unreadable`, `insufficient-collect-agents`).

Run: `python3 scripts/check_lens_isolation.py --run <wf_id|latest>
[--project-root DIR] [--include-main] [--json] [--table]`
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import _workflow_run as wr
from _repo_root import git_toplevel_from_cwd

COLLECT_PHASE = "Collect"
MAIN_SESSION_AGENT_ID = "main-session"

# A summary shorter than this is a phrase several lenses could write
# independently; only a long verbatim run is evidence of a copy.
MIN_SUMMARY_NEEDLE_CHARS = 40

# Two comparable transcripts is the least a cross-contamination search can
# mean anything over -- below it the guard refuses instead of passing.
MIN_COMPARABLE_TRANSCRIPTS = 2


# --------------------------------------------------------------------------- #
# I/O layer
# --------------------------------------------------------------------------- #
def load(transcripts_dir: Path, *, run_arg: str, include_main: bool) -> dict:
    """Resolve one run and read every transcript the guard may search.

    Impure: the only function in this module that touches the filesystem.
    Raises `wr.WorkflowRunError` for the named failure classes, including
    `insufficient-collect-agents` -- the refusal that keeps a run nobody can
    compare from being reported as a run nobody contaminated.
    """
    resolved = wr.resolve_run(transcripts_dir, run_arg)
    run_dir = resolved["run_dir"]
    roster = wr.read_journal(run_dir)
    results = _journal_results(run_dir)

    # Aggregator exemption, explicit: only `Collect`-phase agents are searched,
    # and only `Collect`-phase agents contribute needles. The `Reconcile`
    # aggregator legitimately holds every lens's fragment path -- reading the
    # fragments is its whole job -- so searching its transcript would report
    # the design as a violation. The exemption is this phase filter, stated
    # here rather than emerging by accident from the shape of a fixture.
    collect_ids = [
        agent_id for agent_id, entry in roster.items() if entry.get("phase") == COLLECT_PHASE
    ]

    targets = []
    unsearchable = []
    for agent_id in collect_ids:
        strings = _transcript_strings(wr.agent_transcript_path(run_dir, agent_id))
        if strings is None:
            unsearchable.append(agent_id)
            continue
        targets.append(
            {"agent_id": agent_id, "label": roster[agent_id].get("label"), "strings": strings}
        )

    if len(targets) < MIN_COMPARABLE_TRANSCRIPTS:
        raise wr.WorkflowRunError(
            "insufficient-collect-agents",
            f"{len(targets)} Collect transcript(s) on disk under {run_dir}; "
            f"at least {MIN_COMPARABLE_TRANSCRIPTS} are needed to compare anything",
        )

    main_strings = None
    if include_main:
        main_path = wr.main_transcript_path(transcripts_dir, wr.session_from_run_dir(run_dir))
        main_strings = _transcript_strings(main_path)
        if main_strings is None:
            # `--include-main` asked for a search that cannot happen. Report
            # the coverage gap under the sentinel id instead of letting an
            # absent transcript read as an uncontaminated one.
            unsearchable.append(MAIN_SESSION_AGENT_ID)

    return {
        "wf_id": resolved["wf_id"],
        "targets": targets,
        "unsearchable": unsearchable,
        "needles": {
            agent_id: _needles_for(agent_id, results.get(agent_id) or {})
            for agent_id in collect_ids
        },
        "main_strings": main_strings,
    }


def _journal_results(run_dir: Path) -> dict[str, dict]:
    """`agent_id -> result payload` from the journal's `result` events. The
    last result for a given agent wins, matching the roster's own
    last-event-wins reading of the same file."""
    results: dict[str, dict] = {}
    for record in wr.iter_transcript_records(run_dir / "journal.jsonl"):
        if record.get("type") != "result":
            continue
        agent_id = record.get("agentId")
        result = record.get("result")
        if agent_id and isinstance(result, dict):
            results[agent_id] = result
    return results


def _transcript_strings(path: Path) -> list[str] | None:
    """Every string leaf of every record in a transcript, or `None` when the
    file does not exist -- the distinction between "searched and clean" and
    "never searched", which the caller turns into a finding rather than a
    silent pass."""
    if not path.exists():
        return None
    return [text for record in wr.iter_transcript_records(path) for text in _string_leaves(record)]


def _string_leaves(value: object) -> Iterator[str]:
    """Recursively yield every string value in a decoded JSON structure --
    text blocks, tool inputs, tool results and thinking alike, since a leaked
    identity is contamination wherever in the turn it landed. Searching
    decoded leaves rather than the raw line keeps JSON escaping (quotes,
    non-ASCII) out of the comparison. Object *keys* are schema, not content,
    and are deliberately not searched."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _string_leaves(item)


# --------------------------------------------------------------------------- #
# pure search (fixture-testable without touching the filesystem)
# --------------------------------------------------------------------------- #
def compute(loaded: dict) -> dict:
    """Search every readable transcript for its siblings' artifact identity.
    Pure: every input is a value already in memory."""
    findings = []
    for target in loaded["targets"]:
        findings += _scan_transcript(
            target["strings"],
            loaded["needles"],
            target_id=target["agent_id"],
            skip_sibling_id=target["agent_id"],
        )
    if loaded["main_strings"] is not None:
        # The main session is nobody's sibling, so no needle set is skipped.
        findings += _scan_transcript(
            loaded["main_strings"],
            loaded["needles"],
            target_id=MAIN_SESSION_AGENT_ID,
            skip_sibling_id=None,
        )
    findings += [{"code": "LI02", "agent_id": agent_id} for agent_id in loaded["unsearchable"]]
    return {"wf_id": loaded["wf_id"], "findings": findings}


def _scan_transcript(
    strings: list[str],
    needles: dict[str, list[tuple[str, str]]],
    *,
    target_id: str,
    skip_sibling_id: str | None,
) -> list[dict]:
    """The needle search -- the single implementation, used for both a lens's
    own transcript and (under `--include-main`) the main session's. One
    finding per (sibling, needle kind) that hit -- every kind is reported, so
    a pointer-shaped hit (`fragment_path`, which the main transcript carries
    by construction) never masks a payload-shaped one (`summary`)."""
    findings = []
    for sibling_id, sibling_needles in needles.items():
        if sibling_id == skip_sibling_id:
            continue
        findings += [
            {
                "code": "LI01",
                "agent_id": target_id,
                "sibling_agent_id": sibling_id,
                "needle_kind": kind,
            }
            for kind, needle in sibling_needles
            if any(needle in text for text in strings)
        ]
    return findings


def _needles_for(agent_id: str, result: dict) -> list[tuple[str, str]]:
    """One agent's artifact identity as `(kind, value)` pairs, most specific
    first -- the fragment path names exactly one artifact, the agent id
    exactly one agent, and a long verbatim summary exactly one return. A
    missing or too-short field contributes nothing; the lens *label* is never
    here, because naming a domain is not evidence of reading a sibling."""
    summary = result.get("summary")
    candidates = [
        ("fragment_path", _repo_relative(result.get("fragment_path"))),
        ("agent_id", agent_id),
        (
            "summary",
            summary
            if isinstance(summary, str) and len(summary) >= MIN_SUMMARY_NEEDLE_CHARS
            else None,
        ),
    ]
    return [(kind, value) for kind, value in candidates if isinstance(value, str) and value]


def _repo_relative(path):
    """The `.ai-work/...` tail of a fragment path, whatever prefix the lens
    returned it with. An absolute path contains the repo-relative form, so
    the tail matches a sibling quoting either form; a value with no such
    tail is used verbatim."""
    if not isinstance(path, str):
        return path
    index = path.find(".ai-work/")
    return path[index:] if index > 0 else path


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render_table(report: dict, targets: list[dict]) -> str:
    findings = report["findings"]
    lines = [
        f"wf_id={report['wf_id']}  searched={len(targets)}  findings={len(findings)}",
        "",
        f"{'searched':20} {'agent_id':26}",
    ]
    lines += [f"{(target['label'] or '?'):20} {target['agent_id']:26}" for target in targets]
    lines += ["", "clean -- no sibling artifact identity found" if not findings else "findings:"]
    lines += [
        f"  {finding['code']} {finding['agent_id']}"
        + (
            f" <- {finding['sibling_agent_id']} ({finding['needle_kind']})"
            if finding["code"] == "LI01"
            else " (no transcript on disk -- not searched)"
        )
        for finding in findings
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Lens-isolation guard over a Workflow-tool run: every Collect transcript "
            "must be free of its siblings' artifact identity."
        )
    )
    parser.add_argument(
        "--run", required=True, help="Workflow run id, or 'latest'. Never inferred."
    )
    parser.add_argument(
        "--project-root", default=None, help="Project root; defaults to git toplevel of CWD."
    )
    parser.add_argument(
        "--include-main",
        action="store_true",
        help="Also search the main-session transcript for the same needles.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    parser.add_argument(
        "--table", action="store_true", help="Emit the report as a table (default)."
    )
    args = parser.parse_args(argv)

    project_root = (
        Path(args.project_root).resolve() if args.project_root else git_toplevel_from_cwd()
    )
    if project_root is None:
        print("error: not inside a git worktree and no --project-root given", file=sys.stderr)
        return 2
    transcripts_dir = wr.transcripts_dir(project_root)

    try:
        loaded = load(transcripts_dir, run_arg=args.run, include_main=args.include_main)
    except wr.WorkflowRunError as exc:
        print(f"error: {exc.reason}: {exc}", file=sys.stderr)
        return 2

    report = compute(loaded)
    print(json.dumps(report, indent=2) if args.json else render_table(report, loaded["targets"]))
    return 1 if any(finding["code"] == "LI01" for finding in report["findings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
