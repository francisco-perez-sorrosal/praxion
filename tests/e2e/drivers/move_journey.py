"""A move run, end to end, that spends nothing: stand-in main sessions over planted records.

The operator's journey crosses the console entry, the `claude` binary it launches each task's
main session through, the fixture repository the session works in, and the results files and
run index it writes. This driver points the entry at a narrowed checkout (`move_eval`), puts a
stand-in `claude` first on PATH, runs floor and paired runs, and hands back what each run
launched and wrote.

The stand-in plays a headless main session the way the harness would present one to the
runner: per launch it learns the arm from the words of the `--plugin-dir` path and the task from
a path component of its working directory that is a task id (never from the prompt), leaves in
the session's own record (`move_records` writes it) the arrivals the arm owes, or what the
scenario scripts instead, acts in the task's fixture as scripted (a conforming commit of the
named files, or a violating one), or fails with an identical infrastructure error, and records
the launch: its arm, task, working directory and prompt. The runner must therefore place each
fixture in a directory named by its task id and name each arm copy by its arm.

The tasks the stand-in knows come from the kit, once per process and variant, and are written
into its config by `run`, so a module shares one floor run and one paired run at the size its
scenarios need. A script counts an arm's launches from the last `rescript`. No real `claude` ever
starts; the run carries a dummy credential and the stand-in never reads the session token.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.move_eval import (
    FIRST_MOVE,
    Arm,
    CliResult,
    Declared,
    MoveRun,
    RunKind,
    move_tasks,
    run_move,
)

Ending = Literal[
    "conforming",  # commits exactly the named files with a well-formed message
    "violating",  # stages every change at once and commits with a malformed message
    "violating the message only",  # commits the named files with a malformed message
    "kernel never arrived",  # a lean session whose resident kernel is absent from its record
    "infrastructure error",  # exits non-zero with the same error text every time
]


@dataclass(frozen=True)
class Script:
    """What the stand-in does for each session: by arm, then by the arm's nth launch (1-based)."""

    default: Ending = "conforming"
    by_arm: Mapping[Arm, Ending] = field(default_factory=dict)
    by_launch: Mapping[tuple[Arm, int], Ending] = field(default_factory=dict)


@dataclass(frozen=True)
class MoveLaunch:
    arm: Arm
    task_id: str
    cwd: Path
    prompt: str


STAND_IN_VERSION = "9.9.9-stand-in"
_TASK_TABLES: dict[tuple[str, str], dict[str, list[str]]] = {}  # (move, variant) -> task -> files


@dataclass(frozen=True)
class StandIn:
    root: Path

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def log_dir(self) -> Path:
        return self.root / "log"

    @property
    def _config(self) -> Path:
        return self.root / "config.json"

    def launches(self) -> list[MoveLaunch]:
        paths = sorted(self.log_dir.glob("launch-*.json"), key=lambda p: int(p.stem.split("-")[1]))
        raws = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        return [
            MoveLaunch(raw["arm"], raw["task_id"], Path(raw["cwd"]), raw["prompt"]) for raw in raws
        ]

    def rescript(self, script: Script) -> None:
        """Answer the launches from now on as `script` says, counting each arm's from here."""
        self._update(script=_script_json(script), epoch=len(self.launches()))

    def prepare(self, move: str, declared: Declared | None) -> None:
        """Tell the stand-in which move it answers and the tasks that move's kit lists."""
        variant = Declared(move, "as declared") if declared is None else declared
        key = (move, variant.variant)
        if key not in _TASK_TABLES:
            _TASK_TABLES[key] = {t.task_id: list(t.named_files) for t in move_tasks(variant)}
        path = None if variant.path is None else str(variant.path)
        self._update(move=move, declaration=path, tasks=_TASK_TABLES[key])

    def _update(self, **changes: object) -> None:
        config = json.loads(self._config.read_text(encoding="utf-8"))
        self._config.write_text(json.dumps({**config, **changes}), encoding="utf-8")


def _script_json(script: Script) -> dict[str, object]:
    return {
        "default": script.default,
        "by_arm": dict(script.by_arm),
        "by_launch": {f"{arm}|{nth}": ending for (arm, nth), ending in script.by_launch.items()},
    }


def install_stand_in(workspace: Path, script: Script) -> StandIn:
    """Write the stand-in `claude` first on a `bin` directory under `workspace`.

    Its launcher runs under the suite's own interpreter and imports only the record writer.
    """
    stand_in = StandIn(workspace / "move-stand-in")
    stand_in.bin_dir.mkdir(parents=True)
    stand_in._config.write_text(
        json.dumps(
            {
                "log_dir": str(stand_in.log_dir),
                "records_dir": str(stand_in.root / "records"),
                "version": STAND_IN_VERSION,
                "script": _script_json(script),
                "epoch": 0,
                "move": FIRST_MOVE,
                "declaration": None,
                "tasks": {},
            }
        ),
        encoding="utf-8",
    )
    launcher = stand_in.bin_dir / "claude"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(adherence_eval.REPO_ROOT)!r})\n"
        "from tests.acceptance.drivers.move_records import serve\n"
        f"sys.exit(serve({str(stand_in._config)!r}))\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return stand_in


def results_dir(checkout: Path) -> Path:
    return checkout / ".ai-state" / "eval_ledger" / "adherence"


def _results_files(checkout: Path) -> set[Path]:
    # A move run's file sits one level down (moves/<run_id>.json), a role run's at the top.
    return {p for p in results_dir(checkout).rglob("*.json") if p.name != "index.json"}


@dataclass(frozen=True)
class RunOutcome:
    cli: CliResult
    launches: tuple[MoveLaunch, ...]  # the launches this invocation made
    written: tuple[Path, ...]  # results files this invocation added

    @property
    def results(self) -> Path:
        (only,) = self.written
        return only

    def describe(self) -> str:
        return f"exit {self.cli.exit_code}; stderr: {self.cli.stderr[-1500:]}"


def run(
    stand_in: StandIn,
    checkout: Path,
    kind: RunKind,
    *,
    max_tasks: int,
    floor_citation: Path | None = None,
    stop_count: int | None = None,
    move: str = FIRST_MOVE,
    declared=None,
) -> RunOutcome:
    """Launch one floor or paired run of `move` with the stand-in, and say what it did."""
    stand_in.prepare(move, declared)
    request = MoveRun(
        move,
        checkout,
        kind=kind,
        max_tasks=max_tasks,
        floor_citation=floor_citation,
        stop_count=stop_count,
        declared=declared,
    )
    return observe(stand_in, checkout, lambda: run_move(request, stand_in.bin_dir))


def observe(stand_in: StandIn, checkout: Path, invoke) -> RunOutcome:
    """Run `invoke` and report the launches and results files it added."""
    files_before, launched_before = _results_files(checkout), len(stand_in.launches())
    cli = invoke()
    launches = tuple(stand_in.launches()[launched_before:])
    written = tuple(sorted(_results_files(checkout) - files_before))
    return RunOutcome(cli, launches, written)


def copy_checkout(checkout: Path, workspace: Path) -> Path:
    """An independent copy of a checkout and every results file it holds, for one scenario."""
    target = workspace / "checkout-copy"
    shutil.copytree(checkout, target, symlinks=True)
    return target


def commit_change(checkout: Path, relpath: str, text: str) -> None:
    """Change one file of the checkout and commit it, as a maintainer would between runs."""
    (checkout / relpath).write_text(text, encoding="utf-8")
    adherence_eval._git(checkout, "add", "--", relpath)
    adherence_eval._git(checkout, "commit", "-q", "-m", f"Change {relpath}")
