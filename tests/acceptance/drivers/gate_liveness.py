"""Driver for the scheduled gate-liveness run, and the scratch copies it runs in.

The liveness run is reached only through the command the scheduled job runs. A
scenario never runs it in this checkout: it runs it inside a *scratch copy* of
this repository, so a run that writes where it should not is caught in the copy
and never touches the work in progress. A scenario may change one gate in its
copy before the run (replace a script, rewrite the hook registration) to show
that a check fails when only its gate changed.

The copy is a clone of the current commit plus the working tree's uncommitted
changes and new files, committed so the copy starts with a clean status. It is
built from git objects rather than by reading every working-tree file, so a
selection audit observing this test's reads does not see it read the whole
repository. `.venv` is linked in so the copy runs on the same interpreter and
dependencies as this checkout.

Isolation: runs get no inherited `CLAUDE_*`, `PRAXION_*`, `GIT_*`,
`ANTHROPIC_*`, `GH_TOKEN` or `GITHUB_TOKEN` (the scheduled run has no secret and
no assistant session); a scenario that stands for a run started inside a session
adds the session's variables back explicitly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

PROJECT_LOG = Path(".ai-state") / "observations.jsonl"
PROJECT_LOG_ARCHIVE = Path(".ai-state") / "observations.jsonl.1"

_STRIPPED_PREFIXES = ("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_")
_STRIPPED_NAMES = ("GH_TOKEN", "GITHUB_TOKEN")
_GIT_IDENTITY = (
    "-c",
    "user.name=Liveness Acceptance",
    "-c",
    "user.email=liveness-acceptance@example.invalid",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "core.hooksPath=/dev/null",
)


class Gate(Enum):
    MUTATION_SENSOR = "mutation sensor"
    OBSERVATION_HOOKS = "observation-log hooks"
    SPAWN_COUNT = "spawn counter"
    SELECTION_AUDIT = "test-scope resolver (selection audit)"


ALL_GATES = tuple(Gate)
QUICK_GATES = (Gate.MUTATION_SENSOR, Gate.OBSERVATION_HOOKS, Gate.SPAWN_COUNT)

LIVENESS_COMMAND = "scripts/check_gates_bite.py"
_GATE_IDS = {
    Gate.MUTATION_SENSOR: "mutation-sensor",
    Gate.OBSERVATION_HOOKS: "observation-hooks",
    Gate.SPAWN_COUNT: "spawn-count",
    Gate.SELECTION_AUDIT: "selection-audit",
}


@dataclass(frozen=True)
class Verdict:
    """One liveness check's result, as the run reports it."""

    passed: bool
    reason: str  # why it failed: what was expected against what was observed
    unselected: tuple[tuple[str, str], ...] = ()  # selection audit: (test file, file it read)


@dataclass(frozen=True)
class LivenessRun:
    exit_code: int | None  # None: the run outlived the scenario's own time limit
    output: str
    verdicts: Mapping[Gate, Verdict]

    def verdict(self, gate: Gate) -> Verdict:
        if gate not in self.verdicts:
            raise AssertionError(
                f"the run reported no verdict for the {gate.value} check "
                f"(skipped or never run):\n{self.describe()}"
            )
        return self.verdicts[gate]

    def describe(self) -> str:
        lines = [f"exit={self.exit_code}"]
        for gate, verdict in self.verdicts.items():
            state = "passed" if verdict.passed else "FAILED"
            lines.append(f"  {gate.value}: {state} {verdict.reason.strip()!r}")
        lines.append("output:\n" + self.output[-4000:])
        return "\n".join(lines)


# -- The scratch copy -----------------------------------------------------------


def _git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(cwd: Path, *args: str, stdin: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "--no-optional-locks", *_GIT_IDENTITY, *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        env=_git_env(),
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.decode(errors='replace')}"
        )
    return result.stdout


@dataclass(frozen=True)
class RepoCopy:
    """A self-contained clone of this repository's current state."""

    root: Path

    def path(self, relpath: str | Path) -> Path:
        return self.root / relpath

    def read(self, relpath: str | Path) -> str:
        return self.path(relpath).read_text(encoding="utf-8")

    def write(self, relpath: str | Path, text: str, *, executable: bool = False) -> None:
        target = self.path(relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if executable:
            target.chmod(0o755)

    def remove(self, relpath: str | Path) -> None:
        self.path(relpath).unlink()

    def commit(self, message: str) -> None:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "--allow-empty", "--no-verify", "-m", message)

    def status(self) -> str:
        """Tracked changes and untracked, unignored files; empty when clean."""
        return _git(self.root, "status", "--porcelain", "--untracked-files=all").decode()

    def seed_project_log(self, rows: list[str]) -> bytes:
        """Give the copy its own observation log (ignored by git); returns its bytes."""
        log = self.path(PROJECT_LOG)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return log.read_bytes()


def make_copy(workspace: Path, name: str = "praxion") -> RepoCopy:
    """A clean, committed copy of this repository's working state under `workspace`."""
    root = workspace / name
    workspace.mkdir(parents=True, exist_ok=True)
    head = _git(REPO_ROOT, "rev-parse", "HEAD").decode().strip()
    _git(workspace, "clone", "-q", "--shared", "--no-checkout", "--no-tags", str(REPO_ROOT), name)
    _git(root, "checkout", "-q", "--detach", head)
    patch = _git(REPO_ROOT, "diff", "--binary", "HEAD")
    if patch.strip():
        _git(root, "apply", "--binary", "--whitespace=nowarn", "-", stdin=patch)
    untracked = _git(REPO_ROOT, "ls-files", "-z", "--others", "--exclude-standard").split(b"\0")
    for raw in filter(None, untracked):
        relpath = raw.decode()
        source = REPO_ROOT / relpath
        if source.is_file():
            target = root / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
    venv = REPO_ROOT / ".venv"
    if venv.exists():
        (root / ".venv").symlink_to(venv)
        with (root / ".git" / "info" / "exclude").open("a", encoding="utf-8") as exclude:
            exclude.write("\n.venv\n")
    copy = RepoCopy(root)
    copy.commit("liveness acceptance: copy of the working state")
    return copy


# -- Running the liveness checks ------------------------------------------------


def isolated_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(_STRIPPED_PREFIXES) and k not in _STRIPPED_NAMES
    }
    env.update(extra or {})
    return env


def _text(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode(errors="replace")


def _parse_verdicts(stdout: str) -> dict[Gate, Verdict]:
    """The `verdicts` of the command's JSON report; empty when it printed none."""
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    gate_by_id = {gate_id: gate for gate, gate_id in _GATE_IDS.items()}
    verdicts: dict[Gate, Verdict] = {}
    for entry in report.get("verdicts", []):
        gate = gate_by_id.get(entry["gate"])
        if gate is None:
            raise AssertionError(f"the run reported a check this driver does not know: {entry!r}")
        verdicts[gate] = Verdict(
            passed=entry["passed"],
            reason=entry.get("reason", ""),
            unselected=tuple((test, read) for test, read in entry.get("unselected", ())),
        )
    return verdicts


def run_liveness(
    copy: RepoCopy,
    gates: Collection[Gate] = ALL_GATES,
    *,
    extra_env: Mapping[str, str] | None = None,
    timeout: float = 900,
) -> LivenessRun:
    """Run the liveness checks for `gates` from the copy's root, as the scheduled job does."""
    copy_python = copy.path(".venv") / "bin" / "python"
    python = str(copy_python) if copy_python.exists() else sys.executable
    selected = [gate for gate in ALL_GATES if gate in gates]
    command = [python, LIVENESS_COMMAND, "--json"]
    for gate in selected:
        command += ["--gate", _GATE_IDS[gate]]
    try:
        result = subprocess.run(
            command,
            cwd=copy.root,
            env=isolated_env(extra_env),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as expired:
        output = _text(expired.stdout) + _text(expired.stderr)
        return LivenessRun(exit_code=None, output=output, verdicts={})
    return LivenessRun(
        exit_code=result.returncode,
        output=result.stdout + result.stderr,
        verdicts=_parse_verdicts(result.stdout),
    )


def liveness_step_marker() -> str:
    """Text that appears in the `run:` of a workflow step that starts the liveness run."""
    return LIVENESS_COMMAND
