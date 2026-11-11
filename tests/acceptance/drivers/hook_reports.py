"""Driver for what the plugin's first-session hook tells the user, read as Claude Code reads it.

Claude Code shows the user the `systemMessage` of the JSON object a `SessionStart` hook writes as
its whole standard output; the standard error of a hook that exits 0 reaches neither Claude nor
the user. So a report is read here from that one field, and a stream is "quiet" only when it is
empty.

The system is reached only through its public entry point: `hooks/auto_complete_install.py`, run
from a version's directory of the plugin cache with `HOME` and `CLAUDE_PLUGIN_ROOT` set, the
session-start payload on standard input, under the `python3` that comes first on `PATH` (every
hook is registered as `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/<hook>.py`). The scratch machine and
its cache are `plugin_update`'s.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import plugin_update as pu

PREFIX = "[Praxion]"
FINISH_BY_HAND = "/praxion-complete-install"
COMPLETED = "[Praxion] Auto-install complete."
DISABLE = "PRAXION_DISABLE_AUTO_COMPLETE"


# -- Reading a session's output -------------------------------------------------------------------


def message(session: pu.Session) -> str:
    """The `systemMessage` of the one JSON object that is the session's whole standard output.

    Raises AssertionError saying what Claude Code would have read instead."""
    try:
        payload = json.loads(session.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"standard output is not one JSON object ({exc.msg}); Claude Code would not show it "
            f"as a message. stdout={session.stdout[:600]!r} stderr={session.stderr[:600]!r}"
        ) from None
    if not isinstance(payload, dict) or not isinstance(payload.get("systemMessage"), str):
        raise AssertionError(f"the JSON object carries no systemMessage text: {payload!r}")
    return payload["systemMessage"]


def message_lines(session: pu.Session) -> list[str]:
    return message(session).splitlines()


# -- Interpreters ---------------------------------------------------------------------------------


def below_floor_python(dest: Path) -> Path | None:
    """A `python3` below the hooks' floor (Python 3.11 or newer with PyYAML): this interpreter's
    version in an environment of its own that has no PyYAML. None when no such environment can be
    made here (PyYAML reachable from the base interpreter itself)."""
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(dest)], check=True, capture_output=True
    )
    python = dest / "bin" / "python3"
    probe = subprocess.run([str(python), "-I", "-c", "import yaml"], capture_output=True)
    return None if probe.returncode == 0 else python


# -- Session starts -------------------------------------------------------------------------------


def start(
    machine: pu.Machine,
    version: str,
    *,
    python: Path | None = None,
    plugin_root: bool = True,
    extra_env: dict[str, str] | None = None,
    timeout: float = 180,
) -> pu.Session:
    """A session start of `version`: its hook run as Claude Code runs it, under `python` (this
    interpreter by default), which is also the `python3` first on the machine's `PATH`. Without
    `plugin_root`, `CLAUDE_PLUGIN_ROOT` is absent from the hook's environment."""
    interpreter = Path(python or sys.executable)
    shim = machine.root / "shims" / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{interpreter}" "$@"\n')
    shim.chmod(0o755)
    plugin = machine.version(version)
    env = machine.env(plugin if plugin_root else None)
    env.update(extra_env or {})
    started = time.monotonic()
    proc = subprocess.Popen(
        [str(interpreter), str(plugin / pu.HOOK)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=machine.root / "work", env=env, text=True, start_new_session=True,
    )  # fmt: skip
    try:
        out, err = proc.communicate(pu.SESSION_START_PAYLOAD, timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        timed_out = True
    return pu.Session(proc.returncode, out, err, time.monotonic() - started, timed_out)


@dataclass
class Scene:
    """A scratch machine and the session start under observation."""

    machine: pu.Machine
    session: pu.Session

    @property
    def identity_values(self) -> set[str]:
        return {pu.FIRST.name, pu.FIRST.email}


def _blocked(path: Path) -> tuple[Path, int]:
    """Make `path` (a directory, created when absent) not writable; returns what to restore."""
    path.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o7777
    path.chmod(0o555)
    return path, mode


def _blocked_directory(machine: pu.Machine, how: str) -> Path:
    return {
        "scripts-directory-not-writable": machine.bin,
        "claude-directory-not-writable": machine.home / ".claude",
    }[how]


def first_install(
    scratch: Path, tree: Path, *, failing: str | None = None, python: Path | None = None
) -> Scene:
    """A marketplace install's first session on a machine that holds only a git identity;
    `failing` names a directory the install needs that is not writable."""
    machine = pu.Machine(scratch)
    machine.set_identity(pu.FIRST)
    machine.install_version(pu.BEFORE, tree)
    restore = _blocked(_blocked_directory(machine, failing)) if failing else None
    try:
        session = start(machine, pu.BEFORE, python=python)
    finally:
        if restore:
            restore[0].chmod(restore[1])
    return Scene(machine, session)


def update(
    scratch: Path, tree: Path, *, failing: str | None = None, python: Path | None = None
) -> Scene:
    """N installed and used for a day, then N+1 in the cache; the session is N+1's first one.
    `failing` names a directory the refresh needs that is not writable."""
    machine = pu.Machine(scratch)
    machine.set_identity(pu.FIRST)
    machine.first_install(pu.BEFORE, tree)
    machine.let_time_pass()
    machine.install_version(pu.AFTER, tree)
    restore = _blocked(_blocked_directory(machine, failing)) if failing else None
    try:
        session = start(machine, pu.AFTER, python=python)
    finally:
        if restore:
            restore[0].chmod(restore[1])
    return Scene(machine, session)


def later_session(scratch: Path, tree: Path) -> Scene:
    """A second session of a version whose first session already ran."""
    machine = pu.Machine(scratch)
    machine.set_identity(pu.FIRST)
    machine.first_install(pu.BEFORE, tree)
    return Scene(machine, start(machine, pu.BEFORE))


def opted_out(scratch: Path, tree: Path) -> Scene:
    """A first session with the opt-out set to 1."""
    machine = pu.Machine(scratch)
    machine.set_identity(pu.FIRST)
    machine.install_version(pu.BEFORE, tree)
    return Scene(machine, start(machine, pu.BEFORE, extra_env={DISABLE: "1"}))


def _registry(machine: pu.Machine) -> Path:
    return machine.home / ".claude" / "plugins" / "installed_plugins.json"


def no_plugin_root_anywhere(scratch: Path, tree: Path) -> Scene:
    """A session start with no `CLAUDE_PLUGIN_ROOT` and no plugin registry."""
    machine = pu.Machine(scratch)
    machine.set_identity(pu.FIRST)
    machine.install_version(pu.BEFORE, tree)
    _registry(machine).unlink()
    return Scene(machine, start(machine, pu.BEFORE, plugin_root=False))


def plugin_root_naming_nothing(scratch: Path, tree: Path) -> Scene:
    """A session start whose `CLAUDE_PLUGIN_ROOT` and registered praxion install path both name
    directories that do not exist."""
    machine = pu.Machine(scratch)
    machine.set_identity(pu.FIRST)
    machine.install_version(pu.BEFORE, tree)
    missing = machine.root / "no-such-plugin"
    _registry(machine).write_text(
        json.dumps({"plugins": {"praxion@bit-agora": [
            {"scope": "user", "installPath": str(missing / "registered"), "version": pu.BEFORE}]}}),
        encoding="utf-8",
    )  # fmt: skip
    env = {"CLAUDE_PLUGIN_ROOT": str(missing / "variable")}
    return Scene(machine, start(machine, pu.BEFORE, plugin_root=False, extra_env=env))
