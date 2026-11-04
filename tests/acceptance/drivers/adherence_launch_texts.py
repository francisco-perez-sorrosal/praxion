"""Driver for what each session the adherence eval launches receives at its start.

The eval runs through `adherence_runs` with every launch answered by `stand_in_claude`; no
`claude` starts and nothing is paid for. A launch spy stands first on the run's `PATH` and, at each
launch before the stand-in answers, reads what that session would receive with
`session_start_text`: the instruction files of the launch's configuration directory
(`CLAUDE_CONFIG_DIR`, else its HOME's `.claude`) and of its working directory, plus the
`SessionStart` hooks of its `--plugin-dir` copy run in that directory; and what the role it spawns
would receive, by `session_start_text.spawn_start` against the same plugin copy. The readings are
taken from copies of the launch's directories, so a hook that writes cannot change what the run
goes on to measure, and are masked to tokens, so two runs compare.

Each reading is keyed by arm, task and proof (`<arm>/<task id>`, `<arm>/proof` for an arm's proof,
`#<n>` after a retried task's first session) and paired with the reading the same run gave at the
pipeline base, frozen in `tests/acceptance/fixtures/project_gating/base_launch_texts.json`. The
checks graded are the names each task session was graded on, read from the run's results file.

Freeze the base's readings from a tree that is the pipeline base:
`python -m tests.acceptance.drivers.adherence_launch_texts`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers import stand_in_claude
from tests.acceptance.drivers.adherence_eval import FAKE_CLAUDE_VERSION
from tests.acceptance.drivers.process_text_oracles import FIXTURES, REPO_ROOT, fixture_json, mask
from tests.acceptance.drivers.session_start_text import (
    HEADLESS,
    Machine,
    session_start,
    spawn_start,
)

BASE_FIXTURE = "base_launch_texts.json"
EVERY_FIXTURE = 24  # the role's planned tasks by default: `max_tasks` high enough to take them all
PROOF = "proof"
PROOF_NONCE = re.compile(r"PRXARM-[0-9a-f]+")  # an arm proof plants a fresh nonce in each run


@dataclass(frozen=True)
class Reading:
    """What one launch's session received, and what the role it spawns received."""

    session: str
    role: str


NOTHING = Reading("", "")


@dataclass(frozen=True)
class LaunchTexts:
    now: Mapping[str, Reading]  # launch key -> this run's reading
    base: Mapping[str, Reading]  # launch key -> the pipeline base's, frozen
    graded: Mapping[str, list[str]]  # task session key -> the checks it was graded on
    todays_graded: Mapping[str, list[str]]

    def session_pairs(self, arm: str) -> dict[str, tuple[str, str]]:
        """Launch key -> (today's process text, this run's), for every session of `arm`."""
        return self._pairs(arm, lambda reading: reading.session)

    def role_pairs(self, arm: str) -> dict[str, tuple[str, str]]:
        """Launch key -> (today's, this run's) process text of the role the session spawned."""
        return self._pairs(arm, lambda reading: reading.role)

    def graded_checks(self) -> dict[str, list[str]]:
        return dict(self.graded)

    def todays_graded_checks(self) -> dict[str, list[str]]:
        return dict(self.todays_graded)

    def _pairs(self, arm: str, text) -> dict[str, tuple[str, str]]:
        keys = sorted(k for k in {*self.now, *self.base} if k.startswith(f"{arm}/"))
        return {
            key: (text(self.base.get(key, NOTHING)), text(self.now.get(key, NOTHING)))
            for key in keys
        }


def run_recording_launch_texts(workspace: Path) -> LaunchTexts:
    """The eval run on a fresh checkout of this tree, its launches read; paired with the base's."""
    run = _run_reading_launches(workspace)
    base = fixture_json(BASE_FIXTURE)
    return LaunchTexts(
        now=run.readings,
        base=_unpack(base),
        graded=run.graded,
        todays_graded=base["graded"],
    )


# -- The run, every launch read ------------------------------------------------------------------


@dataclass(frozen=True)
class ReadRun:
    readings: dict[str, Reading]
    graded: dict[str, list[str]]


def _run_reading_launches(workspace: Path) -> ReadRun:
    plan = runs.Plan(max_tasks=EVERY_FIXTURE)
    checkout = runs.new_checkout(workspace)
    root = runs._fresh_directory(workspace, "launch-texts")
    stand_in = stand_in_claude.install(
        root / "claude",
        version=FAKE_CLAUDE_VERSION,
        role=plan.role,
        tasks=runs._planned_places(root, checkout, plan),
        by_arm={},
        by_task={},
        default=runs.ran(),
    )
    readings_dir = root / "readings"
    spy_bin = _install_spy(root / "spy", stand_in.bin_dir / "claude", readings_dir, plan.role)
    done = runs._console(checkout, spy_bin, runs._run_options(plan, checkout))
    assert done.returncode == 0, f"the adherence run failed: {done.stderr[-2000:]}"
    launched = stand_in.launches()
    taken = _recorded(readings_dir)
    assert len(taken) == len(launched), (
        f"the spy read {len(taken)} launches, the stand-in answered {len(launched)}"
    )
    readings = {_key(launch): reading for launch, reading in zip(launched, taken, strict=True)}
    results = runs._results_path(checkout, set(), done.stdout)
    return ReadRun(readings, _graded_checks(results))


def _key(launch: stand_in_claude.LaunchRecord) -> str:
    task = PROOF if launch.proof else launch.task_id
    return f"{launch.arm}/{task}" + (f"#{launch.attempt}" if launch.attempt > 1 else "")


def _graded_checks(results_path: Path) -> dict[str, list[str]]:
    sessions = json.loads(results_path.read_text(encoding="utf-8"))["sessions"]
    return {
        f"{s['setup']['arm']}/{s['setup']['task_id']}": sorted(s["status"].get("outcomes", {}))
        for s in sessions
    }


def _recorded(readings_dir: Path) -> list[Reading]:
    files = sorted(readings_dir.glob("launch-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return [Reading(**json.loads(f.read_text(encoding="utf-8"))) for f in files]


# -- The spy: the first `claude` on the run's PATH, which reads a launch and hands it on -----------


def _install_spy(root: Path, stand_in: Path, readings_dir: Path, role: str) -> Path:
    """A `claude` that reads every launch, then becomes the stand-in. Returns its directory."""
    root.mkdir(parents=True)
    spy = root / "claude"
    spy.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from tests.acceptance.drivers.adherence_launch_texts import spy_launch\n"
        f"spy_launch({str(readings_dir)!r}, {str(stand_in)!r}, {role!r})\n",
        encoding="utf-8",
    )
    spy.chmod(0o755)
    return root


def spy_launch(readings_dir: str, stand_in: str, role: str) -> None:
    """Read the launch (`claude -p ...`) from its own directories, then exec the stand-in."""
    argv = sys.argv[1:]
    if "-p" in argv:
        readings_dir_path = Path(readings_dir)
        readings_dir_path.mkdir(parents=True, exist_ok=True)
        reading = read_launch(argv, os.environ, Path.cwd(), role)
        taken = len(list(readings_dir_path.glob("launch-*.json")))
        (readings_dir_path / f"launch-{taken}.json").write_text(
            json.dumps({"session": reading.session, "role": reading.role}), encoding="utf-8"
        )
    os.execv(stand_in, [stand_in, *argv])


def read_launch(argv: Sequence[str], environ: Mapping[str, str], cwd: Path, role: str) -> Reading:
    """What the launch's session, and the role it spawns, receive at start.

    The reading is taken from copies of the launch's working directory and configuration
    directory, against its plugin copy; the plugin copy itself is only read.
    """
    plugin = Path(argv[argv.index("--plugin-dir") + 1])
    home = Path(environ["HOME"])
    config_dir = Path(environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    with tempfile.TemporaryDirectory(prefix="launch-reading-") as scratch:
        sandbox = Path(scratch).resolve()
        project = sandbox / "project"
        shutil.copytree(cwd, project, symlinks=True)
        shutil.copytree(config_dir, sandbox / "home" / ".claude", symlinks=True)
        machine = Machine(sandbox / "home", plugin, sandbox)
        tokens = {**machine.tokens(), home: "<home>", cwd: "<project>", project: "<project>"}
        session = session_start(machine, project, entrypoint=HEADLESS).process_text
        spawned = spawn_start(machine, project, f"praxion:{role}").process_text
        return Reading(_masked(session, tokens), _masked(spawned, tokens))


def _masked(text: str, tokens: Mapping[Path, str]) -> str:
    return PROOF_NONCE.sub("PRXARM-<nonce>", mask(text, dict(tokens)))


# -- The frozen base ---------------------------------------------------------------------------------


def _unpack(frozen: Mapping) -> dict[str, Reading]:
    texts = frozen["texts"]
    return {
        key: Reading(texts[launch["session"]], texts[launch["role"]])
        for key, launch in frozen["launches"].items()
    }


def _pack(readings: Mapping[str, Reading], graded: Mapping[str, list[str]]) -> dict:
    """Each distinct text once, the launches pointing to it by digest."""
    texts: dict[str, str] = {}

    def keep(text: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()[:12]
        texts[digest] = text
        return digest

    launches = {
        key: {"session": keep(r.session), "role": keep(r.role)} for key, r in readings.items()
    }
    return {"texts": texts, "launches": launches, "graded": dict(graded)}


def freeze(workspace: Path) -> None:
    """Write the base's readings from this tree, which must be the pipeline base."""
    run = _run_reading_launches(workspace)
    packed = _pack(run.readings, run.graded)
    (FIXTURES / BASE_FIXTURE).write_text(
        json.dumps(packed, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="freeze-launch-texts-") as scratch:
        freeze(Path(scratch))
