#!/usr/bin/env python3
"""Scenario 6 — inheritance-probe (process-economy P0.7 / P0.3).

Spawns two fresh, out-of-band `claude -p` sessions — one top-level, one that
is instructed to spawn a `praxion:researcher` subagent — and asserts the
**difference** between what each reports about its own context. This is the
executable guard for the subagent-inheritance correction (`skills/agent-crafting/SKILL.md`):
a top-level Claude Code session inherits the user's global CLAUDE.md, the
project's own CLAUDE.md, every always-loaded rule, AND the two
`install: hook-deliver` rules (`agent-model-routing.md`,
`git-conventions.md` -- `load: always_on` in `rules/_manifest.yaml`, injected
into `additionalContext` by `inject_rules.py` on the `SessionStart` hook
event). A subagent session never fires `SessionStart` (its lifecycle uses
`SubagentStart`/`SubagentStop` instead), so it inherits the first set but
never the hook-delivered rules.

A single-run probe cannot exercise this claim: any assertion "the subagent's
context lacks X" is unfalsifiable without a paired run proving a top-level
session *would* have reported X present under the identical question. That
was v1's bug — a bare top-level `claude -p` invocation
was checked against a claim that is specifically about subagent inheritance,
so the guard could never fail. v2 makes both runs report a discriminating
fact -- whether a section headed `## Agent Model Routing` (the hook-delivered
rule's own heading) appears anywhere in context -- and requires the two runs
to disagree on it.

Why a standalone script, not a SeededScenarioFamily check: grading a static
fixture can prove a checker is correct, but it cannot prove what a *live*
session actually inherits — the seeded-scenario family's fixtures are golden
captures of past agent output, not live process spawns. This script is the
one place in the eval surface that shells out to real `claude` sessions.

Cost: **two full headless Claude Code sessions per invocation** (API-metered,
not free) — this is why it is registered judged-tier-only in the seeded
scenario family (skipped under `--mechanical-only`) and documented in
`eval/EVAL_PLAN.md` as "run once per M-confidence slice", not on every
mechanical pass.

This module is deliberately split into pure/impure layers so the checker is
unit-testable without ever spawning a process:
    build_prompt()       -- pure: the instruction text for a given run kind
    build_invocation()   -- pure: the argv list (never executed here)
    parse_report()       -- pure: raw JSON text in, RunReport out
    check_differential()  -- pure: two RunReports in, verdict out
    main()                -- impure: the only place that calls subprocess.run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Kind = Literal["top-level", "subagent"]

# ---------------------------------------------------------------------------
# Prompt + invocation (pure — build the request, never send it here)
# ---------------------------------------------------------------------------

_ROUTING_HEADING = "## Agent Model Routing"

_QUESTION = (
    "Answer with ONLY a JSON object and nothing else -- no markdown fences, "
    "no commentary -- of exactly this shape: "
    '{"claude_md_paths": [...], "routing_heading_present": true|false}. '
    '"claude_md_paths" lists every file path named in your claudeMd system '
    "block (the 'Contents of <path>' headers you were given at session "
    'start), exactly as written there. "routing_heading_present" is true iff '
    f'a markdown section headed exactly "{_ROUTING_HEADING}" appears '
    "anywhere in your context, false otherwise."
)

_SUBAGENT_WRAPPER = (
    "Use the Agent tool to spawn exactly one subagent with subagent_type "
    "'praxion:researcher'. Its full prompt must be exactly the text between "
    "the BEGIN/END markers below, verbatim, with no additions:\n"
    "-----BEGIN QUESTION-----\n"
    f"{_QUESTION}\n"
    "-----END QUESTION-----\n"
    "Wait for the subagent to finish, then print its final response "
    "verbatim as your own ONLY output -- no markdown fences, no commentary, "
    "nothing before or after it."
)


def build_prompt(kind: Kind) -> str:
    """The instruction sent to the fresh session for *kind*. Pure — no I/O."""
    if kind == "top-level":
        return _QUESTION
    if kind == "subagent":
        return _SUBAGENT_WRAPPER
    raise ValueError(f"unknown probe kind: {kind!r}")


def build_invocation(kind: Kind, prompt: str | None = None) -> list[str]:
    """The `claude` CLI argv for a fresh, non-interactive, single-turn session.

    Never executed by this module except inside `main()`. Flags, per
    `claude --help`:
        -p, --print                Non-interactive; required for any
                                    scripted/headless call.
        --output-format json       Parseable envelope (a `result` field
                                    carrying the model's final text) instead
                                    of a raw terminal transcript.
        --model sonnet              Cheapest model class that reliably
                                    follows a structured-JSON + tool-use
                                    instruction; this probe checks context
                                    inheritance, not model capability.
        --permission-mode
            bypassPermissions        The `subagent` kind's prompt requires
                                    using the Agent tool; a headless `-p`
                                    session has no human to approve a tool
                                    permission prompt, so bypass is required
                                    for that kind to complete at all. Applied
                                    to both kinds for a like-for-like
                                    invocation shape.

    Note: `claude --help` in this environment offers no `--max-turns`/turn-cap
    flag; a single-turn -p call is naturally turn-bounded by the model
    producing one final response, so no additional cap is passed.
    """
    return [
        "claude",
        "-p",
        prompt if prompt is not None else build_prompt(kind),
        "--output-format",
        "json",
        "--model",
        "sonnet",
        "--permission-mode",
        "bypassPermissions",
    ]


# ---------------------------------------------------------------------------
# Checker (pure — the only functions this scenario's mechanical test exercises)
# ---------------------------------------------------------------------------

# The 7 identifiers every session -- top-level or subagent -- must report,
# regardless of the `SessionStart` hook-delivery difference under test.
# Suffixes matched against whatever form a session reports its own paths in
# (absolute, as this very transcript's own system-prompt injection shows --
# e.g. "/Users/x/.claude/CLAUDE.md" -- never assume the tilde-shorthand form).
#
# Cross-checked by hand against `scripts/measure_token_budget.py`'s
# `always_loaded_files()` (the always-loaded surface, minus its two
# hook-delivered entries below) rather than imported at runtime: that
# function returns `Path` objects keyed by rule *name*
# (`rules/<subpath>` relative to whichever rules-tree root delivered it), not
# ready-made path suffixes, so deriving suffixes from it needs a
# name-to-suffix mapping step that isn't worth the added surface for a set
# that is this small and this stable.
_EXPECTED_SUFFIXES: tuple[str, ...] = (
    "/.claude/CLAUDE.md",  # global CLAUDE.md (user scope)
    "/rules/CLAUDE.md",  # rules catalog readme
    "agent-behavioral-contract.md",
    "adr-conventions.md",
    "swe-agent-coordination-protocol.md",
    "agent-intermediate-documents.md",
)

_PROJECT_CLAUDE_MD_LABEL = "<project-root>/CLAUDE.md"


def _is_project_root_claude_md(path: str) -> bool:
    """True for the project's own root CLAUDE.md -- distinguished from the
    global (`/.claude/CLAUDE.md`) and rules-catalog (`/rules/CLAUDE.md`)
    CLAUDE.md's by exclusion, since "project CLAUDE.md" has no fixed suffix
    of its own (the project root varies per checkout)."""
    return (
        path.endswith("/CLAUDE.md") and "/.claude/CLAUDE.md" not in path and "/rules/" not in path
    )


def _missing_expected(paths: tuple[str, ...]) -> list[str]:
    """Expected identifiers absent from *paths*. Pure — no I/O."""
    missing = [
        suffix for suffix in _EXPECTED_SUFFIXES if not any(p.endswith(suffix) for p in paths)
    ]
    if not any(_is_project_root_claude_md(p) for p in paths):
        missing.append(_PROJECT_CLAUDE_MD_LABEL)
    return missing


@dataclass(frozen=True)
class RunReport:
    """One session's answer to `_QUESTION`, parsed from its JSON reply."""

    kind: Kind
    claude_md_paths: tuple[str, ...]
    routing_heading_present: bool


def parse_report(kind: Kind, raw_json_text: str) -> RunReport:
    """Parse a session's raw JSON reply into a `RunReport`. Pure — no I/O.

    Raises `json.JSONDecodeError` if the model did not reply with valid JSON,
    and `KeyError` if it replied with JSON missing a required field -- both
    real failure modes for a live session that main() surfaces to the caller
    rather than masking.
    """
    data = json.loads(raw_json_text)
    return RunReport(
        kind=kind,
        claude_md_paths=tuple(str(p) for p in data["claude_md_paths"]),
        routing_heading_present=bool(data["routing_heading_present"]),
    )


@dataclass(frozen=True)
class InheritanceVerdict:
    """Result of comparing a top-level run's report against a subagent run's.

    Fields:
        verdict: PASS when both runs carry the 7 expected paths AND the
            top-level run reports the routing heading present while the
            subagent run reports it absent; FAIL otherwise.
        findings: Human-readable summary lines.
    """

    verdict: Literal["PASS", "FAIL"]
    findings: tuple[str, ...]


def check_differential(top_level: RunReport, subagent: RunReport) -> InheritanceVerdict:
    """Pure differential checker: do the two reports disagree the way the
    subagent-inheritance claim predicts? No subprocess, no I/O.
    """
    findings: list[str] = []

    top_missing = _missing_expected(top_level.claude_md_paths)
    if top_missing:
        findings.append(f"top-level run missing expected path(s): {top_missing}")
    sub_missing = _missing_expected(subagent.claude_md_paths)
    if sub_missing:
        findings.append(f"subagent run missing expected path(s): {sub_missing}")

    if not top_level.routing_heading_present:
        findings.append(
            f"top-level run did not report {_ROUTING_HEADING!r} present -- "
            "expected present via the SessionStart hook delivery"
        )
    if subagent.routing_heading_present:
        findings.append(
            f"subagent run reported {_ROUTING_HEADING!r} present -- the "
            "guard is vacuous: SessionStart never fires for a subagent, so "
            "it must never see a hook-delivered rule's heading"
        )

    verdict: Literal["PASS", "FAIL"] = "FAIL" if findings else "PASS"
    if not findings:
        findings = (
            "both runs carry the 7 always-loaded paths; top-level reports "
            f"{_ROUTING_HEADING!r} present, subagent reports it absent",
        )
    return InheritanceVerdict(verdict=verdict, findings=tuple(findings))


# ---------------------------------------------------------------------------
# main() — the only impure entry point
# ---------------------------------------------------------------------------


def _run(kind: Kind, *, record_dir: Path | None) -> RunReport:
    """Spawn one session of *kind*, optionally recording its raw stdout."""
    invocation = build_invocation(kind)
    completed = subprocess.run(invocation, capture_output=True, text=True, check=False)  # noqa: S603
    if completed.returncode != 0:
        raise RuntimeError(
            f"{kind} run: claude exited {completed.returncode}: {completed.stderr.strip()}"
        )
    if record_dir is not None:
        record_dir.mkdir(parents=True, exist_ok=True)
        (record_dir / f"{kind}.json").write_text(completed.stdout, encoding="utf-8")
    envelope = json.loads(completed.stdout)
    return parse_report(kind, envelope["result"])


def main(argv: list[str] | None = None) -> int:
    """Spawn both sessions, parse their JSON replies, print the verdict.

    Costs two full headless Claude Code sessions (API-metered) unless
    `--dry-run` is passed -- run deliberately, never from a test or a
    mechanical eval pass.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print both invocations without running them, then exit 0.",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="Directory to save both runs' raw stdout as fixtures.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        for kind in ("top-level", "subagent"):
            print(f"{kind}: {build_invocation(kind)}")
        return 0

    try:
        top_level = _run("top-level", record_dir=args.record)
        subagent = _run("subagent", record_dir=args.record)
    except (RuntimeError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    verdict = check_differential(top_level, subagent)
    print(f"verdict: {verdict.verdict}")
    for finding in verdict.findings:
        print(f"  - {finding}")
    return 0 if verdict.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
