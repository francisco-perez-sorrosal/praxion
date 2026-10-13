"""Builders shared by the spawn-hook tests: a scratch plugin, a scratch project and one spawn.

Not a test module. Every behavior runs `hooks/inject_kernel.py` as a separate process on a
synthetic `SubagentStart` payload, the way the harness runs it: the payload on stdin,
`CLAUDE_PLUGIN_ROOT` in the environment, one `--slot N` per injected string. The plugin is a
scratch directory holding a kernel index and an adoption ledger; the project is a scratch git
working tree.

The observation log is read in the test modules, never here: the log reader's consumer
registry counts every importer that is not a test module as a production consumer.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
HOOK = HOOKS_DIR / "inject_kernel.py"
sys.path.insert(0, str(HOOKS_DIR))

import inject_kernel  # noqa: E402

ROLE = "researcher"
AGENT_TYPE = f"praxion:{ROLE}"
VERSION = "kernel-version-1"
MARKER_VERSION = VERSION[: inject_kernel.MARKER_VERSION_CHARS]
PLUGIN_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
CAP = inject_kernel.INJECTION_CAP
PART_HEADING = "[project CLAUDE.md, part"
ASTRAL = "\U0001f600"  # one character, two UTF-16 units


def ledger_text(status: str | None, role: str = ROLE) -> str:
    """The adoption ledger as its writers emit it (block style), the role at `status` if any."""
    roles = f"  {role}:\n    status: {status}\n    since: '2026-10-12'\n    runs: []\n"
    return (
        "version: 1\neligible:\n- researcher\n- verifier\n"
        f"roles:{' {}' if status is None else chr(10) + roles}"
    )


def make_plugin(
    tmp_path: Path,
    strings=("KERNEL ONE",),
    status: str | None = "trial",
    slots=9,
    ledger: str | None = "",
    index_status: str | None = None,
    **index,
) -> Path:
    """A plugin root whose ledger puts `ROLE` at `status` and whose index holds `strings`.

    `ledger` replaces the ledger's text; None writes no ledger. The index carries no status
    unless `index_status` says so: the ledger alone decides who receives a kernel.
    """
    entry = {"status": index_status, "strings": list(strings)}
    document = {
        "schema": 1,
        "kernel_version": VERSION,
        "slots": slots,
        "roles": {ROLE: entry},
        **index,
    }
    root = tmp_path / "plugin"
    (root / "claude" / "kernels").mkdir(parents=True)
    (root / "claude" / "kernels" / "index.json").write_text(json.dumps(document), encoding="utf-8")
    if ledger is not None:
        (root / ".ai-state").mkdir()
        text = ledger or ledger_text(status)
        (root / ".ai-state" / "kernel_adoption.yaml").write_text(text, encoding="utf-8")
    return root


def make_project(tmp_path: Path, claude_md: str | None = None, managed: bool = True) -> Path:
    """A git working tree; `managed` gives it `.ai-state/`, `claude_md` a root CLAUDE.md."""
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, env=_env(tmp_path, None))
    if managed:
        (project / ".ai-state").mkdir()
    if claude_md is not None:
        (project / "CLAUDE.md").write_text(claude_md, encoding="utf-8", newline="")
    return project


def _env(tmp_path: Path, plugin: Path | None, **extra: str) -> dict:
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home")}
    if plugin is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
    return {**env, **extra}


def payload(project: Path, agent_type: str = AGENT_TYPE, **fields) -> str:
    return json.dumps(
        {
            "session_id": "session-1",
            "cwd": str(project),
            "hook_event_name": "SubagentStart",
            "agent_id": "agent-0001",
            "agent_type": agent_type,
            **fields,
        }
    )


def run_hook(tmp_path, plugin, stdin, slot="1", **extra_env) -> subprocess.CompletedProcess:
    args = [] if slot is None else ["--slot", slot]
    return subprocess.run(
        [sys.executable, str(HOOK), *args],
        input=stdin,
        env=_env(tmp_path, plugin, **extra_env),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )


def injected(done: subprocess.CompletedProcess) -> str | None:
    """The additionalContext the hook printed; None when it printed nothing."""
    if not done.stdout:
        return None
    output = json.loads(done.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SubagentStart"
    return output["additionalContext"]


def spawn(tmp_path, plugin, project, agent_type=AGENT_TYPE, slots=9, **env) -> list:
    """What each slot printed for one spawn, in slot order (None where nothing)."""
    stdin = payload(project, agent_type)
    return [injected(run_hook(tmp_path, plugin, stdin, str(n), **env)) for n in range(1, slots + 1)]


def delivered(strings: list) -> list:
    return [s for s in strings if s is not None]


def project_text(lines: int) -> str:
    return "".join(
        f"Project convention line {n:04d}: keep fixtures under data/.\n" for n in range(lines)
    )


def part_bodies(strings: list) -> list:
    """The project-file text of each delivered part: the string minus marker and header."""
    return [s.split("\n", 3)[3] for s in strings if PART_HEADING in s]
