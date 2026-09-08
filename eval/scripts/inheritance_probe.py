#!/usr/bin/env python3
"""Scenario 6 — inheritance-probe (process-economy P0.7 / P0.3).

Spawns a fresh, out-of-band `claude -p` session and asserts the file paths it
reports from its own `claudeMd` system block — the executable guard for the
Step 2 subagent-inheritance correction (a fresh Claude Code session inherits
the user's global CLAUDE.md, the project's own CLAUDE.md, and every
always-loaded rule; it does NOT inherit `agent-model-routing.md` or
`git-conventions.md`). Those two are `install: hook-deliver` rules
(`load: always_on` in `rules/_manifest.yaml`) — always-on, not path-scoped —
injected into `additionalContext` by `inject_rules.py`, which is wired only
under the `SessionStart` hook event (`hooks/hooks.json`). `SessionStart` fires
for a top-level interactive session; it does not fire when a subagent session
is spawned (that lifecycle uses `SubagentStart`/`SubagentStop` instead), so a
subagent never receives the `inject_rules.py` injection and these two rules
are absent from its `claudeMd` block regardless of which files it touches.

Why a standalone script, not a SeededScenarioFamily check: grading a static
fixture can prove a checker is correct, but it cannot prove what a *live*
session actually inherits — the seeded-scenario family's fixtures are golden
captures of past agent output, not live process spawns. This script is the
one place in the eval surface that shells out to a real `claude` session.

Cost: **one full headless Claude Code session per invocation** (API-metered,
not free) — this is why it is registered judged-tier-only in the seeded
scenario family (skipped under `--mechanical-only`) and documented in
`eval/EVAL_PLAN.md` as "run once per M-confidence slice", not on every
mechanical pass.

This module is deliberately split into three pure/impure layers so the
checker is unit-testable without ever spawning a process:
    build_prompt()      -- pure: the instruction text
    build_invocation()  -- pure: the argv list (never executed here)
    check_inheritance()  -- pure: paths in, verdict out
    main()               -- impure: the only place that calls subprocess.run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Prompt + invocation (pure — build the request, never send it here)
# ---------------------------------------------------------------------------

_PROMPT = (
    "List, as a JSON array of strings and nothing else, the file paths named "
    "in your claudeMd system block (the 'Contents of <path>' headers you were "
    "given at session start). Return exactly the paths as written there — no "
    "commentary, no markdown fences, just the JSON array."
)


def build_prompt() -> str:
    """The instruction sent to the fresh session. Pure — no I/O."""
    return _PROMPT


def build_invocation(prompt: str | None = None) -> list[str]:
    """The `claude` CLI argv for a fresh, non-interactive, single-turn session.

    Never executed by this module except inside `main()`. Flags, per
    `claude --help`:
        -p, --print              Print response and exit (non-interactive;
                                  required for any scripted/headless call).
        --output-format json     "json" (single result) rather than the
                                  interactive-default "text" -- gives a
                                  parseable envelope (a `result` field
                                  carrying the model's final text) instead of
                                  a raw terminal transcript.

    Deliberately does NOT pass `--agent <name>`: the claim under test is what
    a *bare* fresh session inherits (the Step 2 correction is about the
    baseline claudeMd stack every session gets, not a named subagent
    persona's tool-specific instructions) -- see this script's module
    docstring and the assumption recorded in LEARNINGS.md.
    """
    return [
        "claude",
        "-p",
        prompt if prompt is not None else build_prompt(),
        "--output-format",
        "json",
    ]


# ---------------------------------------------------------------------------
# Checker (pure — the only function this scenario's mechanical test exercises)
# ---------------------------------------------------------------------------

# Suffixes matched against whatever form a session reports its own paths in
# (absolute, as this very transcript's own system-prompt injection shows --
# e.g. "/Users/x/.claude/CLAUDE.md" -- never assume the tilde-shorthand form).
_EXPECTED_SUFFIXES: tuple[str, ...] = (
    "/.claude/CLAUDE.md",  # global CLAUDE.md (user scope)
    "/rules/CLAUDE.md",  # rules catalog readme
    "agent-behavioral-contract.md",
    "adr-conventions.md",
    "swe-agent-coordination-protocol.md",
    "agent-intermediate-documents.md",
)

# install: hook-deliver rules injected by inject_rules.py only on SessionStart
# (a top-level interactive session) -- a bare `claude -p` subagent probe gets
# no SessionStart firing, so these must NEVER appear in its claudeMd block.
_FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    "agent-model-routing.md",
    "git-conventions.md",
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


@dataclass(frozen=True)
class InheritanceVerdict:
    """Result of checking a reported path list against the expected stack.

    Fields:
        verdict: PASS when all 7 expected paths are present and neither
            forbidden path-scoped rule appears; FAIL otherwise.
        missing: Expected identifiers not found in any reported path.
        unexpected: Reported paths matching a forbidden path-scoped rule.
        findings: Human-readable summary lines.
    """

    verdict: Literal["PASS", "FAIL"]
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]
    findings: tuple[str, ...]


def check_inheritance(paths: list[str]) -> InheritanceVerdict:
    """Pure checker: does *paths* carry the 7 expected identifiers and
    neither forbidden one? No subprocess, no I/O -- unit-testable directly.
    """
    missing = [
        suffix for suffix in _EXPECTED_SUFFIXES if not any(p.endswith(suffix) for p in paths)
    ]
    if not any(_is_project_root_claude_md(p) for p in paths):
        missing.append(_PROJECT_CLAUDE_MD_LABEL)

    unexpected = [
        path for path in paths if any(path.endswith(suffix) for suffix in _FORBIDDEN_SUFFIXES)
    ]

    findings: list[str] = []
    if missing:
        findings.append(f"missing expected path(s): {missing}")
    if unexpected:
        findings.append(
            f"path-scoped rule(s) present that should only be hook-delivered on demand: {unexpected}"
        )
    if not findings:
        findings.append("all 7 expected paths present; both path-scoped rules correctly absent")

    verdict: Literal["PASS", "FAIL"] = "FAIL" if (missing or unexpected) else "PASS"
    return InheritanceVerdict(
        verdict=verdict,
        missing=tuple(missing),
        unexpected=tuple(unexpected),
        findings=tuple(findings),
    )


# ---------------------------------------------------------------------------
# main() — the only impure entry point; not exercised by any test
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Spawn the fresh session, parse its JSON array, print the verdict.

    Costs one full headless Claude Code session (API-metered) -- run
    deliberately, never from a test or a mechanical eval pass.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    invocation = build_invocation()
    completed = subprocess.run(invocation, capture_output=True, text=True, check=False)  # noqa: S603
    if completed.returncode != 0:
        print(
            f"error: claude exited {completed.returncode}: {completed.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    envelope = json.loads(completed.stdout)
    paths = json.loads(envelope["result"])
    verdict = check_inheritance(paths)

    print(f"verdict: {verdict.verdict}")
    for finding in verdict.findings:
        print(f"  - {finding}")
    return 0 if verdict.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
