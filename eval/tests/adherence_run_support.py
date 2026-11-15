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
from typing import Any

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
from praxion_evals.adherence.model import (
    ROLES,
    ArmBuild,
    Errored,
    Role,
    SessionRecord,
    SessionSetup,
)
from praxion_evals.adherence.session_launch import Launch
from praxion_evals.adherence.session_loop import OUTPUT_DIR
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.test_adherence_results import run_results

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


# -- one session's launch, under a stand-in for the function that starts ``claude`` -------------


def copy_with_definition(
    role: Role, root: Path, cap: int | None = None, patched: tuple[str, ...] = ()
) -> ArmBuild:
    """An arm copy holding the role's definition, which is all a session's spec reads of it."""
    (root / "agents").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "agents" / f"{role}.md", root / "agents" / f"{role}.md")
    return ArmBuild(role, "full", root, cap, "digest", patched)


def launch_in(tmp_path: Path, **overrides: Any) -> Launch:
    """A launch of seed 7 whose environment adds nothing and whose home is ``tmp_path / "home"``."""
    fields: dict[str, Any] = {
        "run_root": tmp_path / "run",
        "checkout_commit": "abc",
        "page_url": "",
        "judge": None,
        "seed": 7,
        "model": "m",
        "effort": "low",
        "session_budget_usd": 1.0,
        "keep_sandbox": True,
        "env_for": lambda root, path_first: {},
        "real_home": tmp_path / "home",
        "ambient": {"PATH": "/usr/bin"},
    }
    return Launch(**{**fields, **overrides})


def stop_run(spec: SessionSpec, env: dict[str, str]) -> SessionRun:
    """In place of ``run_session``: ends the attempt where the launch's inputs have been built."""
    raise RuntimeError("stop here: only the launch's inputs are under test")


# -- a stopped run of the paired axis, planted in a results directory ----------------------------

PAIRED = "refactoring-delivery"
PAIRED_ROLE = "implementer"
PAIRED_ARMS = ("preloaded", "delivered")
STARTED_AT = "2026-10-12T09:00:00Z"
TASKS = ("task-0", "task-1", "task-2")


def _failed(task: str, arm: str, axis: str) -> SessionRecord:
    setup = SessionSetup(
        arm,  # type: ignore[arg-type]
        "c" * 40,
        PAIRED_ROLE,
        task,
        "template",
        7,
        axis,
    )
    return SessionRecord(
        setup, Errored("result_error", "the session failed"), 0.01, 1000, STARTED_AT
    )


def _stopped_run(run_id: str, axis: str, ending: Any) -> results.RunResults:
    arms = PAIRED_ARMS if axis == PAIRED else ("full", "lean")
    extra: dict[str, Any] = {
        "ending": ending_to_json(ending),
        "roles": [PAIRED_ROLE],
        "tasks": {PAIRED_ROLE: list(TASKS)},
        "identity": {"tree": "a" * 64, "model": "claude-opus-5-5", "roles": {}},
    }
    if axis == PAIRED:
        extra["axis"] = axis
    sessions = [_failed(task, arms[0], axis) for task in TASKS]
    run = run_results(sessions, run_id=run_id, roles=(PAIRED_ROLE,), extra=extra)
    return replace(run, arms={PAIRED_ROLE: {arm: {"built": True} for arm in arms}})


def planted(tmp_path: Path, run_id: str, axis: str, ending: Any) -> Path:
    """``tmp_path``'s results directory, holding one run of ``axis`` that ended as ``ending``."""
    directory = tmp_path / OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    results.write_atomic(directory / f"{run_id}.json", _stopped_run(run_id, axis, ending))
    return directory


def snapshot(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir()}


def cli_in(directory: Path, *options: str) -> int:
    where = ["--output", str(directory / "new.json")]  # its directory is where the runs are
    return cli.main([str(scripted_checkout()), *options, *where])
