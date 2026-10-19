"""What the tests that drive ``cli.main`` over a scripted ``claude`` share.

``Script`` stands in for the one function that starts ``claude`` (``session_launch.run_session``);
no process is ever started. The ``paid``, ``full_first``, ``no_launch`` and ``unswitched_checkout``
fixtures that install it live in ``conftest.py``; a module that runs the loop applies
``unswitched_checkout`` through ``pytestmark`` (it is not autouse, so the rest of the suite is
untouched).
"""

from __future__ import annotations

import atexit
import functools
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import cli, results, transcript
from praxion_evals.adherence.arms import NO_MARKER_REPLY, PROOF_LABEL
from praxion_evals.adherence.infra_stop import Launched, StopReason
from praxion_evals.adherence.lineage import (
    InfraStopped,
    RunEnding,
    SpendRefused,
    ending_to_json,
)
from praxion_evals.adherence.model import ROLES
from praxion_evals.live.session import SessionRun, SessionSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = "researcher"

# What a scripted run reads of the checkout it measures: each role's definition and kernel
# adoption (the arm copies and the run identity), the install primitives every proof and task
# sandbox runs (the renderer, its template and the rule linker) and the rules they link.
# Anything else in the real checkout is copied once per arm and digested for no reader.
_CHECKOUT_FILES = (
    ".ai-state/kernel_adoption.yaml",
    "claude/kernels/index.json",
    "claude/config/CLAUDE.md.tmpl",
    "scripts/render_claude_md.py",
    "lib/install_shared.sh",
    *(f"agents/{role}.md" for role in ROLES),
)
_CHECKOUT_TREES = ("rules",)


@functools.cache
def scripted_checkout() -> Path:
    """A small git checkout the scripted runs measure: the files they read, copied once.

    Every run still materializes its own copy of it per role and arm, and digests it, as it
    does the real checkout; the copy is just 40 files rather than 3000. Built once per test
    process and never written by a run, so every test shares it.
    """
    root = Path(tempfile.mkdtemp(prefix="adherence-checkout-")).resolve()
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    for relpath in _CHECKOUT_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    for tree in _CHECKOUT_TREES:
        shutil.copytree(REPO_ROOT / tree, root / tree, symlinks=True)
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.org"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run(
        [*git, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "checkout"], check=True
    )
    return root


SMALL_RUN = [
    "--required-pairs",
    "1",
    "--pair-slack",
    "0",
    "--no-judge",
    "--session-budget-usd",
    "1",
]
FULL_TOKENS, LEAN_TOKENS = 5000, 1000
SESSION_ID, AGENT_ID = "scripted-session", "a0123456789abcdef"
DELIVERED = {
    "type": "hook_additional_context",
    "hookEvent": "SubagentStart",
    "content": ["[praxion 0a1b2c3d #1]\n\nThe kernel."],
}
KERNEL_TRANSCRIPT = json.dumps({"type": "attachment", "attachment": DELIVERED}) + "\n"


class Script:
    """Answers each launch like a session would, and records what was launched."""

    delivers_kernel = True  # a lean spawn records its kernel in the role's own transcript

    def __init__(
        self, *, cost: float | None = 0.01, fail_launch: Callable[[int], bool] | None = None
    ):
        self.cost = cost
        self.fail_launch = fail_launch or (lambda number: False)
        self.specs: list[SessionSpec] = []

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        self.specs.append(spec)
        if self.fail_launch(len(self.specs)):
            return SessionRun("", "scripted failure", 3)
        return SessionRun(self._stream(spec, env), "", 0)

    def _stream(self, spec: SessionSpec, env: dict[str, str]) -> str:
        role = re.search(r"praxion:([a-z-]+)", spec.prompt).group(1)  # type: ignore[union-attr]
        lean = "lean" in spec.plugin_dir.name
        answer = self._answer(spec, env, lean)
        if lean and self.delivers_kernel:
            config_dir = Path(env["CLAUDE_CONFIG_DIR"])
            path = transcript.transcript_path(config_dir, str(spec.cwd), SESSION_ID, AGENT_ID)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(KERNEL_TRANSCRIPT)
        spawned = f"{answer}\nagentId: {AGENT_ID} (to resume)"
        tokens = LEAN_TOKENS if lean else FULL_TOKENS
        usage = {
            "input_tokens": 2,
            "cache_creation_input_tokens": tokens,
            "cache_read_input_tokens": 0,
        }
        plugin = {"name": "praxion", "source": "praxion@inline", "path": str(spec.plugin_dir)}
        result = {"type": "result", "subtype": "success", "is_error": False, "result": answer}
        result["session_id"] = SESSION_ID
        if self.cost is not None:
            result["total_cost_usd"] = self.cost
        events = [
            {
                "type": "system",
                "subtype": "init",
                "plugins": [plugin],
                "mcp_servers": [],
                "cwd": str(spec.cwd),
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Agent",
                            "input": {"subagent_type": f"praxion:{role}", "prompt": "do it"},
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "parent_tool_use_id": "t1",
                "message": {"content": [{"type": "text", "text": answer}], "usage": usage},
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "t1", "content": spawned}]
                },
            },
            result,
        ]
        return "\n".join(json.dumps(event) for event in events)

    @staticmethod
    def _answer(spec: SessionSpec, env: dict[str, str], lean: bool) -> str:
        if PROOF_LABEL not in spec.prompt:
            return "Findings are in the report.\n[COMPLETE]"
        if lean:
            return NO_MARKER_REPLY
        planted = (Path(env["CLAUDE_CONFIG_DIR"]) / "CLAUDE.md").read_text(encoding="utf-8")
        return re.findall(rf"{PROOF_LABEL}-[0-9a-f]+", planted)[-1]


def run_small(
    tmp_path: Path, *options: str, name: str = "out.json"
) -> tuple[int, results.RunResults]:
    """One small run of ROLE into ``tmp_path / name``: its exit code and the results it wrote."""
    output = tmp_path / name
    code = cli.main(
        [str(scripted_checkout()), "--role", ROLE, "--output", str(output), *SMALL_RUN, *options]
    )
    return code, results.load(output)


def sessions_of(loaded: results.RunResults) -> list[tuple[str, str]]:
    return [(r.setup.arm, type(r.status).__name__) for r in loaded.sessions]


def dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path, *options: str) -> list[dict]:
    argv = [str(scripted_checkout()), "--output", str(tmp_path / "out.json"), "--dry-run", *options]
    assert cli.main(argv) == 0
    assert not (tmp_path / "out.json").exists()
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


REASON = "the credit was cut off for an unrelated audit"
STOPPED_BOTH_ARMS = SpendRefused(("task-001",))
STOPPED_ONE_ARM = InfraStopped(
    StopReason(
        "result_error",
        "credit",
        ROLE,
        "lean",
        tuple(Launched("task-001", "lean", 1) for _ in range(3)),
        "one-arm",
    )
)


def ended_as(tmp_path: Path, ending: RunEnding, name: str = "stopped.json") -> results.RunResults:
    """A small run of ROLE in ``tmp_path``, its results rewritten to say it ended as ``ending``."""
    loaded = run_small(tmp_path, name=name)[1]
    extra = {**loaded.run.extra, "ending": ending_to_json(ending)}
    rewritten = replace(loaded, run=replace(loaded.run, extra=extra))
    results.write_atomic(tmp_path / name, rewritten)
    return rewritten


def close_run(tmp_path: Path, run_id: str, *options: str) -> int:
    where = ["--output", str(tmp_path / "closing.json")]  # its directory is where the runs are
    return cli.main([str(scripted_checkout()), "--close", run_id, *options, *where])
