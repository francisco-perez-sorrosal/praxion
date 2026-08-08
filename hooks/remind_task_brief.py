#!/usr/bin/env python3
"""TASK_BRIEF reminder hook -- advisory when a Standard/Full pipeline stage is
spawned without an Intake Clarity Gate brief.

PreToolUse(Agent|Task) hook. Fires when the orchestrator spawns a
brief-consuming pipeline stage carrying a `Task slug: <slug>` in its prompt
while `.ai-work/<slug>/TASK_BRIEF.md` does not exist, and writes one advisory
line to stderr.

Why an advisory and not a gate. The obligation is unconditional at
Standard/Full but nothing intervened at the moment it applied, so it lapsed
silently and completely. A hard block is the wrong correction: refusing the
first spawn of a pipeline strands the user whenever the tier guess is wrong,
and the tier is exactly what a hook cannot know. Detection after the fact
already exists in the ecosystem auditor; what was missing was a nudge at the
moment of the lapse. This hook is that nudge and nothing more.

Advisory by construction, three independent ways:

  * It never writes stdout. That makes it structurally incapable of emitting
    `updatedInput` and contending with `inject_subagent_context.py`, the
    single updatedInput emitter registered on this same matcher. Two emitters
    for one spawn was a real defect once; this hook cannot reintroduce it.
  * It exits 0 unconditionally. The harness treats any PreToolUse exit other
    than 2 as approval, so the spawn always proceeds -- including when the
    hook itself errors.
  * It never denies and never asks. `permissionDecision` is never emitted.

Fast-skip conditions (exit 0, silent):
  (a) tool_name is neither "Agent" nor its "Task" alias
  (b) tool_input is not a JSON object
  (c) subagent_type is not a brief-consuming stage
  (d) the prompt carries no `Task slug: <slug>` -- never guess a slug
  (e) the repo root is not resolvable from git
  (f) `.ai-work/<slug>/TASK_BRIEF.md` already exists
  (g) PRAXION_DISABLE_TASK_BRIEF_REMINDER is set
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from _hook_utils import is_disabled

DISABLE_FLAG = "PRAXION_DISABLE_TASK_BRIEF_REMINDER"
PREFIX = "[task-brief-reminder]"
SUBPROCESS_TIMEOUT_SECONDS = 3

# Stages that consume the brief AND can still act on its absence.
#
# Deliberately narrower than "every agent that reads the brief". The verifier
# consumes it too, but a reminder at verification time cannot be acted on --
# the brief seeds the rubric that pass is already applying. The implementer
# and test-engineer fan out N-wide on one plan, so reminding there would emit
# N stderr lines for a single lapse. These two stages are the earliest
# deterministic Standard/Full signal and the last point where writing the
# brief still changes a downstream artifact.
BRIEF_CONSUMING_STAGES = frozenset(
    {
        "systems-architect",
        "implementation-planner",
    }
)

# `Task slug: <slug>` per the task-slug propagation contract. Backticks are
# optional because orchestrators write the slug both ways.
TASK_SLUG_RE = re.compile(r"Task slug:\s*`?([A-Za-z0-9][A-Za-z0-9._-]*)`?")


def _log(msg: str) -> None:
    """Write the advisory to stderr. stdout stays empty -- see module docstring."""
    print(f"{PREFIX} {msg}", file=sys.stderr)


def _normalize_stage(subagent_type: str) -> str:
    """Strip a plugin namespace prefix (`praxion:researcher` -> `researcher`)."""
    return subagent_type.split(":")[-1].strip()


def _repo_root(cwd: str) -> Path | None:
    """Resolve the worktree root from git, never from ``__file__``.

    ``.ai-work/`` is worktree-scoped, so the answer must come from the
    spawning session's cwd. Resolving from this file's location would point
    at the plugin cache in every managed project.
    """
    try:
        result = subprocess.run(
            ["git", "-C", cwd or ".", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    toplevel = result.stdout.strip()
    return Path(toplevel) if toplevel else None


def _process(payload: dict) -> None:
    if is_disabled(DISABLE_FLAG):
        return

    if payload.get("tool_name", "") not in ("Agent", "Task"):
        return

    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return

    stage = _normalize_stage(str(tool_input.get("subagent_type", "")))
    if stage not in BRIEF_CONSUMING_STAGES:
        return

    match = TASK_SLUG_RE.search(str(tool_input.get("prompt", "")))
    if match is None:
        return
    slug = match.group(1)

    root = _repo_root(str(payload.get("cwd", "")))
    if root is None:
        return

    if (root / ".ai-work" / slug / "TASK_BRIEF.md").exists():
        return

    _log(
        f".ai-work/{slug}/TASK_BRIEF.md is missing while spawning `{stage}`. "
        "The Intake Clarity Gate requires it at Standard/Full before the first "
        "agent spawn -- it seeds every downstream stage and the verifier's "
        "rubric. Write it now (Intent / Key Signals / Health Guards / "
        "Uncertainty Flag), or re-tier if this is not Standard/Full."
    )


def main() -> None:
    """Read the PreToolUse payload from stdin and advise. Never blocks."""
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, TypeError, ValueError):
        return
    if not isinstance(payload, dict):
        return
    _process(payload)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: a reminder must never be the reason a spawn fails.
        pass
