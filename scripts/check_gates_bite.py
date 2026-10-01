#!/usr/bin/env python3
"""Gate liveness: does each gate still bite on known input, in production shape?

    check_gates_bite.py [--gate ID]... [--json] [--repo-root DIR]

Runs one probe per selected gate (`mutation-sensor`, `observation-hooks`,
`spawn-count`, `selection-audit`; all four when no `--gate` is given), always in
that fixed order, and prints one verdict per gate. A probe is a module under
`scripts/gate_probes/` exposing `run(repo_root, env) -> Verdict`; this command
holds no probe logic, only the registry, containment and rendering.

Nothing passes by default. A probe module that does not exist, raises, returns
something other than its own gate's verdict, or outlives its time limit becomes
a failed verdict whose reason reads `expected ...; observed ...`, and the
remaining probes still run. Each probe runs in its own process group, so a
timeout kills the probe together with whatever it started.

Probes see a scrubbed environment: no session, credential or git-plumbing
variables (`CLAUDE*`, `PRAXION_*`, `GIT_*`, `ANTHROPIC_*`, `GH_TOKEN`,
`GITHUB_TOKEN`), so a run on a developer machine reads the same as a scheduled
one with no secret.

The report is the schema-1 JSON of `gate_probes/verdict.py` (`--json`) or one
`PASS`/`FAIL` line per gate. Exit codes: 0 every selected gate passes, 1 any
fails, 2 usage error or no usable repository root. The root is `--repo-root`, else
the git toplevel of the working directory; it is never derived from this file's
location (managed projects run scripts through a symlink into the plugin), and a
plugin-cache root is refused.

Stdlib-only: the scheduled job runs it on a bare interpreter. Tests:
`scripts/test_check_gates_bite.py`.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _repo_root import git_toplevel_from_cwd, is_plugin_cache_path  # noqa: E402
from gate_probes.verdict import GateId, Verdict, parse_json, render_json  # noqa: E402

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

# Gate id -> "module:function", imported lazily so an absent probe is a failed
# verdict ("not implemented"), not an import error that hides the other gates.
PROBE_ENTRYPOINTS: dict[GateId, str] = {
    GateId.MUTATION_SENSOR: "gate_probes.mutation:run",
    GateId.OBSERVATION_HOOKS: "gate_probes.observation:run",
    GateId.SPAWN_COUNT: "gate_probes.spawn_count:run",
    GateId.SELECTION_AUDIT: "gate_probes.selection:run",
}

TIME_LIMITS_S: dict[GateId, float] = {
    GateId.MUTATION_SENSOR: 300.0,
    GateId.OBSERVATION_HOOKS: 60.0,
    GateId.SPAWN_COUNT: 120.0,
    GateId.SELECTION_AUDIT: 900.0,
}

_SCRUBBED_PREFIXES = ("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_")
_SCRUBBED_NAMES = frozenset({"GH_TOKEN", "GITHUB_TOKEN"})

_TAIL_CHARS = 300

# Child exit codes; the bootstrap below hard-codes the same numbers.
_EXIT_ERROR = 3
_EXIT_UNIMPLEMENTED = 4

# The probe process: a fresh interpreter that inherits the parent's import path
# (made absolute, so a changed working directory cannot break it), loads the
# probe, and prints its verdict as a one-entry schema-1 report on the real
# stdout. Anything the probe prints goes to stderr instead.
_PROBE_CHILD = """
import os, sys
from pathlib import Path
entrypoint, repo_root, search_path = sys.argv[1:4]
sys.path[:0] = [entry for entry in search_path.split(os.pathsep) if entry]
real_stdout, sys.stdout = sys.stdout, sys.stderr
module_name, _, function_name = entrypoint.partition(":")
try:
    import importlib
    probe = getattr(importlib.import_module(module_name), function_name)
except ModuleNotFoundError as exc:
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(4 if exc.name == module_name else 3)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(3)
try:
    from gate_probes.verdict import Verdict, render_json
    verdict = probe(Path(repo_root), dict(os.environ))
    if not isinstance(verdict, Verdict):
        raise TypeError(f"the probe returned {verdict!r}, not a Verdict")
    real_stdout.write(render_json((verdict,)))
except BaseException as exc:
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(3)
"""


class RootError(RuntimeError):
    """No usable repository root: the run cannot say anything about a checkout."""


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse exits on usage errors; keep the int contract
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    try:
        repo_root = _resolve_root(args.repo_root)
    except RootError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    verdicts = run_gates(_selected(args.gate), repo_root, _scrubbed_env(os.environ))
    print(render_json(verdicts) if args.json else _render_text(verdicts))
    return EXIT_PASS if all(verdict.passed for verdict in verdicts) else EXIT_FAILED


def run_gates(gates: Sequence[GateId], repo_root: Path, env: Mapping[str, str]) -> list[Verdict]:
    return [run_probe(gate, repo_root, env) for gate in gates]


def run_probe(gate: GateId, repo_root: Path, env: Mapping[str, str]) -> Verdict:
    """One probe in its own process group, contained: always returns a verdict for `gate`."""
    limit = TIME_LIMITS_S[gate]
    command = [
        sys.executable,
        "-c",
        _PROBE_CHILD,
        PROBE_ENTRYPOINTS[gate],
        str(repo_root),
        os.pathsep.join(os.path.abspath(entry or ".") for entry in sys.path),
    ]
    started = time.monotonic()
    outcome = _run_child(command, repo_root, env, limit)
    return _judge(gate, outcome, limit, time.monotonic() - started)


def _run_child(
    command: list[str], cwd: Path, env: Mapping[str, str], limit: float
) -> subprocess.CompletedProcess[str] | None:
    """The finished child, or None when it outlived `limit` (killed with its whole group)."""
    try:
        child = subprocess.Popen(
            command,
            cwd=cwd,
            env=dict(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, _EXIT_ERROR, "", f"{type(exc).__name__}: {exc}")
    try:
        stdout, stderr = child.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate()
        return None
    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)


def _judge(
    gate: GateId, outcome: subprocess.CompletedProcess[str] | None, limit: float, elapsed: float
) -> Verdict:
    """Turn what the probe process did into the verdict for `gate`."""
    if outcome is None:
        return _failed(
            gate, f"the probe to finish within {limit:g} s", "it was still running", elapsed
        )
    if outcome.returncode == _EXIT_UNIMPLEMENTED:
        module = PROBE_ENTRYPOINTS[gate].partition(":")[0]
        observed = f"probe not implemented ({_tail(outcome.stderr)})"
        return _failed(gate, f"a probe module {module}", observed, elapsed)
    if outcome.returncode != 0:
        observed = f"it failed with exit {outcome.returncode}: {_tail(outcome.stderr)}"
        return _failed(gate, "the probe to return a verdict", observed, elapsed)
    try:
        (verdict,) = parse_json(outcome.stdout)
    except (ValueError, KeyError, TypeError) as exc:
        return _failed(gate, "a readable verdict", f"{type(exc).__name__}: {exc}", elapsed)
    if verdict.gate != gate:
        return _failed(
            gate, f"a verdict for {gate.value}", f"one for {verdict.gate.value}", elapsed
        )
    return dataclasses.replace(verdict, elapsed_s=elapsed)


def _tail(text: str) -> str:
    """The last of a child's stderr, on one line: the exception line, not the traceback."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:_TAIL_CHARS] if lines else "no output"


def _failed(gate: GateId, expected: str, observed: str, elapsed: float) -> Verdict:
    return Verdict(
        gate=gate,
        passed=False,
        reason=f"expected {expected}; observed {observed}",
        elapsed_s=elapsed,
    )


def _resolve_root(cli_root: str | None) -> Path:
    root = Path(cli_root).resolve() if cli_root else git_toplevel_from_cwd()
    if root is None:
        raise RootError("not inside a git repository; pass --repo-root")
    root = root.resolve()
    if is_plugin_cache_path(root):
        raise RootError(f"{root} is a plugin cache, not a checkout")
    return root


def _scrubbed_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in environ.items()
        if not name.startswith(_SCRUBBED_PREFIXES) and name not in _SCRUBBED_NAMES
    }


def _selected(requested: Sequence[str] | None) -> list[GateId]:
    chosen = {GateId(value) for value in requested} if requested else set(GateId)
    return [gate for gate in GateId if gate in chosen]


def _render_text(verdicts: Sequence[Verdict]) -> str:
    lines = []
    for verdict in verdicts:
        state = "PASS" if verdict.passed else "FAIL"
        lines.append(f"{state} {verdict.gate.value} ({verdict.elapsed_s:.1f}s)")
        if verdict.reason:
            lines.append(f"  {verdict.reason}")
        lines.extend(f"  unselected read: {test} reads {read}" for test, read in verdict.unselected)
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prove each gate still bites on known input.")
    parser.add_argument(
        "--gate",
        action="append",
        choices=[gate.value for gate in GateId],
        help="run only this gate (repeatable); default all four",
    )
    parser.add_argument("--json", action="store_true", help="emit the schema-1 JSON report")
    parser.add_argument("--repo-root", help="repo root override (default: git toplevel of cwd)")
    return parser


if __name__ == "__main__":
    sys.exit(main())
