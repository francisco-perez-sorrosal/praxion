"""The two arms of the refactoring move, each a plugin copy shown in its preload state at no cost.

``preloaded`` is the checkout as it is; ``delivered`` is that copy moved by its own
``scripts/refactoring_move.py``, so the move measured is the move that ships. Either arm may carry
an early-stop cap on the role's definition. The original is only read, and a copy is read-only
once built and differs from it at exactly ``patched_paths``.

An arm is shown before any session is paid for: the copy's own preload reader and spawn hook, run
once on a marked delegation, must give the arm's account of the skill. The paired run precedes the
move, so an original already moved has no preloaded arm and is refused.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from praxion_evals.adherence.arms import (
    MAX_TURNS_KEY,
    ArmCopyError,
    definition_path,
    set_frontmatter_key,
    verify_copy_diff,
)
from praxion_evals.adherence.axis import ARMS_BY_AXIS, SessionArm, patched_paths
from praxion_evals.adherence.model import ArmBuild, Role
from praxion_evals.adherence.refactoring_tasks import MARKER
from praxion_evals.live.materialize import (
    Materialization,
    digest_entries,
    make_read_only,
    make_writable,
    remove_tree,
    tree_entries,
)

MOVE_SCRIPT = "scripts/refactoring_move.py"
HOOK_SCRIPT = "hooks/inject_subagent_context.py"
PLUGIN_ROOT_VARIABLE = "CLAUDE_PLUGIN_ROOT"
OBSERVATION_ENV_PREFIX = "PRAXION_"  # a developer's own settings must not reach the hook
RUN_TIMEOUT_SECONDS = 30
MARKED_PROMPT = f"Extract the pricing rules into their own module. {MARKER}"

# Asked of the copy's own delivery module, so what the check applies is what the copy ships.
_ASK_PROGRAM = (
    "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1] + '/hooks'); "
    "import _skill_delivery as d; text = sys.stdin.read(); print({question})"
)
_PRELOADS = "isinstance(d.preload_state(Path(sys.argv[1]), text), d.Preloaded)"
_ARRIVES = "d.shows_arrival(text)"


def build_refactoring_copy(
    original: Materialization, dest: Path, role: Role, arm: SessionArm, turn_cap: int | None
) -> ArmBuild:
    """Copy ``original`` to ``dest`` as ``role``'s ``arm``: shown, read-only, nothing left on failure."""
    if arm not in ARMS_BY_AXIS["refactoring-delivery"]:
        raise ArmCopyError(f"{arm!r} is not an arm of the refactoring move")
    if turn_cap is not None and turn_cap < 1:
        raise ArmCopyError(f"a turn cap must be at least 1, not {turn_cap}")
    definition = definition_path(role)
    if dest.exists() or dest.is_symlink():
        raise ArmCopyError(f"{dest} already exists; a copy is built into a fresh directory")
    _move_tool(original.root, "--to", "preloaded", "--check")
    try:
        shutil.copytree(original.root, dest, symlinks=True)
        make_writable(dest)
        if arm == "delivered":
            _move_tool(dest, "--to", "delivered")
        if turn_cap is not None:
            _cap_turns(dest / definition, turn_cap)
        patched = verify_copy_diff(original.root, dest, expected=patched_paths(role, arm, turn_cap))
        digest = digest_entries(tree_entries(dest))
        make_read_only(dest)
        verify_arm(dest, arm, role)
        return ArmBuild(role, arm, dest, turn_cap, digest, patched)
    except BaseException:
        remove_tree(dest)
        raise


def verify_arm(copy_root: Path, arm: SessionArm, role: Role) -> None:
    """Show the copy's preload state without a session; raise ``ArmCopyError`` unless it is ``arm``'s.

    The delivered copy leaves the skill out of the role's preload and its hook serves a block to a
    marked delegation; the preloaded copy preloads it and its hook serves nothing.
    """
    preloads = _ask_copy(copy_root, _PRELOADS, role)
    if preloads != (arm == "preloaded"):
        verb = "preloads" if preloads else "does not preload"
        raise ArmCopyError(f"the {arm} copy's {role} {verb} the refactoring skill")
    prompt = _hook_prompt(copy_root, role)
    arrives = prompt is not None and _ask_copy(copy_root, _ARRIVES, prompt)
    if arrives != (arm == "delivered"):
        verb = "serves no" if arm == "delivered" else "serves a"
        raise ArmCopyError(f"the {arm} copy's spawn hook {verb} skill block to a marked {role}")


def _move_tool(root: Path, *flags: str) -> None:
    """Run the move tool the tree itself ships; it is also the judge of a tree's state."""
    _run("the move tool", str(root / MOVE_SCRIPT), *flags, "--root", str(root))


def _cap_turns(definition: Path, turn_cap: int) -> None:
    text = definition.read_bytes().decode("utf-8")
    definition.write_bytes(set_frontmatter_key(text, MAX_TURNS_KEY, str(turn_cap)).encode("utf-8"))


def _ask_copy(copy_root: Path, question: str, text: str) -> bool:
    program = _ASK_PROGRAM.format(question=question)
    answer = _run("the copy's delivery module", "-c", program, str(copy_root), input=text)
    return answer.strip() == "True"


def _hook_prompt(copy_root: Path, role: Role) -> str | None:
    """The prompt the copy's hook gives a marked delegation to ``role``; None when it rewrites none."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(OBSERVATION_ENV_PREFIX)}
    env[PLUGIN_ROOT_VARIABLE] = str(copy_root)
    with tempfile.TemporaryDirectory() as cwd:
        tool_input = {"subagent_type": f"praxion:{role}", "prompt": MARKED_PROMPT}
        payload = json.dumps({"tool_name": "Agent", "tool_input": tool_input, "cwd": cwd})
        out = _run(
            "the copy's spawn hook", str(copy_root / HOOK_SCRIPT), input=payload, env=env, cwd=cwd
        )
    if not out.strip():
        return None
    try:
        return json.loads(out)["hookSpecificOutput"]["updatedInput"]["prompt"]
    except (ValueError, KeyError, TypeError) as error:
        raise ArmCopyError(f"the copy's spawn hook printed {out[:200]!r}") from error


def _run(what: str, *args: str, **options: Any) -> str:
    """Run ``python -B <args>``; a failure to run, a timeout or a non-zero exit is a refusal.

    ``-B`` keeps bytecode out of the copy, whose tree must stay what the digest says it is.
    """
    try:
        done = subprocess.run(
            [sys.executable, "-B", *args],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SECONDS,
            check=False,
            **options,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ArmCopyError(f"{what} could not run: {error}") from error
    if done.returncode != 0:
        raise ArmCopyError(
            f"{what} exited {done.returncode}: {(done.stderr or done.stdout).strip()}"
        )
    return done.stdout
