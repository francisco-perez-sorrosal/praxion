"""A move run is refused before any launch, or conducted: each session proven from its own record,
graded on its end state, folded into the stop, and written whole after it. A stand-in launcher
plays the harness in process, building the task's real fixture and acting on it as scripted."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from praxion_evals.adherence.infra_stop import COUNTING_KINDS, StopRule
from praxion_evals.adherence.lineage import Finished, Interrupted, SpendRefused
from praxion_evals.adherence.model import Errored, Failed, Passed
from praxion_evals.adherence.moves import declaration, observe, runner
from praxion_evals.adherence.moves.launch import Finished as Launched
from praxion_evals.adherence.moves.lineage import Stopped
from praxion_evals.adherence.moves.model import LaunchOptions, MoveArm, MoveDeclaration
from praxion_evals.adherence.moves.results import FloorRun, PairedRun
from praxion_evals.adherence.moves.runner import Conducted, RunPlan, RunRefusedError
from praxion_evals.adherence.moves.tasks import MoveTask
from praxion_evals.adherence.session_launch import Attempt
from tests.test_moves_session_record import (
    hook_context,
    prompt,
    tool_call,
    tool_output,
    write_record,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MOVE = "git-conventions"
RULE = "rules/swe/vcs/git-conventions.md"
READ_TREES = ("rules", "lib", "hooks")
READ_FILES = (
    "cursor/config/export-cursor-rules.py",
    "codex/config/export-codex-rules-bridge.py",
    *(
        f"codex/config/{path.name}"
        for path in (REPO_ROOT / "codex/config").glob("rules_bridge_*.py")
    ),
    "claude/config/CLAUDE.md.tmpl",
    "scripts/render_claude_md.py",
)
STOP_RULE = StopRule.parse(3, COUNTING_KINDS, 2000)
SEED = 7
FLOOR_TASKS = runner.FLOOR_MINIMUM
STARTED = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
CONFORMING, VIOLATING, LEAKING = "conforming", "violating", "leaking"


@pytest.fixture(scope="module")
def checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The files an arm build reads, as the repository has them; no test writes here."""
    root = tmp_path_factory.mktemp("runner") / "checkout"
    for tree in READ_TREES:
        shutil.copytree(REPO_ROOT / tree, root / tree, ignore=shutil.ignore_patterns("__pycache__"))
    for relpath in READ_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    return root


@pytest.fixture(scope="module")
def move() -> MoveDeclaration:
    return declaration.kit(MOVE)


# --- a stand-in for the harness ---


@dataclass
class StandIn:
    """Launches one scripted session: the fixture, its commits, and the record the harness keeps.

    ``script`` answers per (arm, launch number) with what the session does: ``CONFORMING`` stages
    the named files and commits by the rule, ``VIOLATING`` stages everything and commits badly,
    ``LEAKING`` also sees the rule at start in a floor arm, and any other word is an error kind
    (``launch_refused`` among them).
    """

    checkout: Path
    moves_dir: Path
    script: Callable[[MoveArm, int], str] = lambda arm, n: CONFORMING
    launches: list[tuple[str, MoveArm]] = field(default_factory=list)
    results_when_launched: list[dict | None] = field(default_factory=list)

    def __call__(self, config, ledger, task: MoveTask, arm: MoveArm, copy, build_fixture, assess):
        self.launches.append((task.task_id, arm))
        self.results_when_launched.append(self._declared())
        what = self.script(arm, len(self.launches))
        if what == "interrupt":
            raise KeyboardInterrupt
        if what not in (CONFORMING, VIOLATING, LEAKING):
            return ledger, _attempt(
                Errored(what, "scripted"), 0.0 if what == "launch_refused" else 1.0
            )
        repo = config.run_root / "fixture" / str(len(self.launches)) / task.task_id
        build_fixture(repo)
        record = self._act(config.run_root, repo, task, arm, copy, what)
        finished = Launched(None, None, record, repo, config.run_root)  # type: ignore[arg-type]
        return ledger.settle(0.0, 0.25), _attempt(assess(finished), 0.25)

    def _declared(self) -> dict | None:
        found = sorted(self.moves_dir.glob("*.json"))
        found = [path for path in found if path.name != "index.json"]
        return json.loads(found[-1].read_text(encoding="utf-8")) if found else None

    def _act(self, root: Path, repo: Path, task: MoveTask, arm: MoveArm, copy: Path, what: str):
        start = "\n".join(observe.session_start(copy).lines)  # type: ignore[union-attr]
        rule = (self.checkout / RULE).read_text(encoding="utf-8")
        if what == LEAKING:
            start += "\n" + rule
        stage = "git add -A" if what == VIOLATING else "git add " + " ".join(task.named_files)
        message = "Added all the things." if what == VIOLATING else "Add the notes"
        commands = [stage, f'git commit -m "{message}"']
        entries = [hook_context("SessionStart", start), prompt(task.wording)]
        if arm == "lean":
            entries.append(hook_context("PreToolUse", rule))
        for number, command in enumerate(commands):
            entries.append(tool_call(f"toolu_{number}", "Bash", {"command": command}))
            entries.append(tool_output(f"toolu_{number}", "ok"))
            subprocess.run(command, shell=True, cwd=repo, check=True, capture_output=True)
        path = root / "records" / f"{task.task_id}-{arm}-{len(self.launches)}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return write_record(path, entries)


def _attempt(result, cost: float) -> Attempt:
    return Attempt(result, cost, 12, STARTED.isoformat(), "claude-opus-5-5")


def _plan(checkout: Path, moves_dir: Path, declared: MoveDeclaration, **changes) -> RunPlan:
    fields = {
        "declaration": declared,
        "kind": "floor",
        "checkout": checkout,
        "moves_dir": moves_dir,
        "seed": SEED,
        "stop_rule": STOP_RULE,
        "harness_version": "2.1.312",
        "margin_pp": 10.0,
        "session_budget_usd": 1.0,
        "run_cap_usd": 100.0,
        "ambient": {},
        "model": "opus",
        "effort": "medium",
        "max_tasks": FLOOR_TASKS,
    }
    return RunPlan(**{**fields, **changes})  # type: ignore[arg-type]


@pytest.fixture
def moves_dir(tmp_path: Path) -> Path:
    return tmp_path / ".ai-state" / "eval_ledger" / "adherence" / "moves"


@pytest.fixture
def stand_in(checkout: Path, moves_dir: Path) -> StandIn:
    return StandIn(checkout, moves_dir)


def _clock() -> datetime:
    return datetime(2026, 10, 28, 9, 0, tzinfo=UTC)


def _conduct(plan: RunPlan, stand_in: StandIn) -> Conducted:
    return runner.conduct(plan, launcher=stand_in, clock=_clock)


def _floor(checkout, moves_dir, move, stand_in, **changes) -> Conducted:
    return _conduct(_plan(checkout, moves_dir, move, **changes), stand_in)


def _files(moves_dir: Path) -> list[str]:
    return sorted(p.name for p in moves_dir.glob("*")) if moves_dir.exists() else []


# --- a floor run ---


def test_a_floor_run_launches_one_floor_session_per_task_and_writes_one_results_file(
    checkout, moves_dir, move, stand_in
):
    done = _floor(checkout, moves_dir, move, stand_in)

    assert isinstance(done.run, FloorRun)
    assert [arm for _, arm in stand_in.launches] == ["floor"] * FLOOR_TASKS
    assert isinstance(done.run.common.ending, Finished)
    assert _files(moves_dir) == sorted(["index.json", done.path.name])


def test_every_governed_check_is_graded_on_each_scored_session_and_no_other(
    checkout, moves_dir, move, stand_in
):
    stand_in.script = lambda arm, n: VIOLATING if n == 1 else CONFORMING

    done = _floor(checkout, moves_dir, move, stand_in)

    graded = [s.checks for s in done.run.common.sessions]
    assert all(set(checks) == {"commit message form", "staging by name"} for checks in graded)
    assert [isinstance(c["staging by name"].final, Failed) for c in graded] == [True] + [False] * 5
    assert isinstance(graded[1]["staging by name"].final, Passed)


def test_the_settings_are_recorded_before_the_first_launch_and_equal_in_every_arm(
    checkout, moves_dir, move, stand_in
):
    stand_in.script = lambda arm, n: VIOLATING
    floor = _floor(checkout, moves_dir, move, stand_in, max_tasks=FLOOR_TASKS)

    written_before_launch = stand_in.results_when_launched[0]
    assert written_before_launch is not None
    assert written_before_launch["sessions"] == []
    assert written_before_launch["pinned"] == {"floor": written_before_launch["pinned"]["floor"]}
    paired = _paired(checkout, moves_dir, move, stand_in, floor)
    assert set(paired.run.common.pinned) == {"full", "lean"}
    assert len({tuple(vars(p).items()) for p in paired.run.common.pinned.values()}) == 1
    assert paired.run.common.settings.stop_rule == STOP_RULE


def test_a_removal_and_the_whole_copy_are_recorded_in_each_arms_identity(
    checkout, moves_dir, move, stand_in
):
    done = _floor(checkout, moves_dir, move, stand_in)

    identity = done.run.common.identity
    assert identity.moved_rule_text == (checkout / RULE).read_text(encoding="utf-8")
    assert {c.path for c in identity.arms["floor"]} >= {RULE, runner.TREE_ENTRY, runner.TASKS_ENTRY}
    assert {c.path for c in identity.arms["full"]} == {runner.TREE_ENTRY, runner.TASKS_ENTRY}
    assert len({c.sha256 for c in identity.arms["floor"] if c.path == runner.TREE_ENTRY}) == 1


def test_a_floor_session_that_saw_the_rule_is_refused_its_score_with_the_reason(
    checkout, moves_dir, move, stand_in
):
    stand_in.script = lambda arm, n: LEAKING if n == 2 else VIOLATING

    done = _floor(checkout, moves_dir, move, stand_in)

    refused = [s for s in done.run.common.sessions if s.status == "refused"]
    assert [s.task_id for s in refused] == [stand_in.launches[1][0]]
    assert refused[0].checks == {}
    assert refused[0].reason


# --- the stop and the ending ---


def test_the_third_identical_floor_failure_in_a_row_stops_the_run_and_launches_no_more(
    checkout, moves_dir, move, stand_in
):
    stand_in.script = lambda arm, n: "result_error"

    done = _floor(checkout, moves_dir, move, stand_in)

    assert len(stand_in.launches) == 3
    assert isinstance(done.run.common.ending, Stopped)
    assert [s.status for s in done.run.common.sessions] == ["errored"] * 3


def test_a_stopped_run_blocks_a_fresh_run_of_its_move_until_it_is_closed_or_continued(
    checkout, moves_dir, move, stand_in
):
    stand_in.script = lambda arm, n: "result_error"
    stopped = _floor(checkout, moves_dir, move, stand_in)
    again = StandIn(checkout, moves_dir)

    with pytest.raises(RunRefusedError, match=f"{stopped.run.common.run_id}.*neither continued"):
        _floor(checkout, moves_dir, move, again)

    assert again.launches == []


def test_a_launch_the_cap_refused_records_no_session_and_ends_the_run_spend_refused(
    checkout, moves_dir, move, stand_in
):
    stand_in.script = lambda arm, n: CONFORMING if n == 1 else "launch_refused"

    done = _floor(checkout, moves_dir, move, stand_in)

    assert len(stand_in.launches) == 2
    assert len(done.run.common.sessions) == 1
    assert done.run.common.ending == SpendRefused((stand_in.launches[1][0],))


def test_an_interrupt_keeps_the_sessions_already_recorded(checkout, moves_dir, move, stand_in):
    stand_in.script = lambda arm, n: "interrupt" if n == 3 else CONFORMING

    done = _floor(checkout, moves_dir, move, stand_in)

    assert len(done.run.common.sessions) == 2
    assert isinstance(done.run.common.ending, Interrupted)


# --- a paired run ---


def _paired(checkout, moves_dir, move, stand_in, floor: Conducted, **changes) -> Conducted:
    changes = {"kind": "paired", "max_tasks": 2, "floor_run": floor.run.common.run_id, **changes}
    return _conduct(_plan(checkout, moves_dir, move, **changes), stand_in)


@pytest.fixture
def cited_floor(checkout, moves_dir, move) -> Conducted:
    violating = StandIn(checkout, moves_dir, lambda arm, n: VIOLATING)
    return _floor(checkout, moves_dir, move, violating)


def test_a_paired_run_launches_both_arms_of_each_task_in_its_recorded_order_and_cites_the_floor(
    checkout, moves_dir, move, stand_in, cited_floor
):
    paired = _paired(checkout, moves_dir, move, stand_in, cited_floor)

    run = paired.run
    assert isinstance(run, PairedRun)
    assert run.cited_floor == (cited_floor.run.common.run_id,)
    assert sorted(stand_in.launches) == sorted(
        (task, arm) for task in run.common.launch_orders for arm in ("full", "lean")
    )
    for task, order in run.common.launch_orders.items():
        assert [arm for t, arm in stand_in.launches if t == task] == list(order)
    assert run.complete_pairs == 2
    assert run.flip == "underpowered"


def test_a_paired_run_declares_the_own_discordance_allowance_method_and_no_calibration_source(
    checkout, moves_dir, move, stand_in, cited_floor
):
    paired = _paired(checkout, moves_dir, move, stand_in, cited_floor)

    settings = paired.run.common.settings
    assert (settings.allowance_method, settings.allowance_source) == ("own-discordance-exact", None)
    assert cited_floor.run.common.settings.allowance_method is None


def test_an_errored_session_leaves_its_pair_incomplete_and_is_not_retried(
    checkout, moves_dir, move, stand_in, cited_floor
):
    stand_in.script = lambda arm, n: "timeout" if n == 1 else CONFORMING

    paired = _paired(checkout, moves_dir, move, stand_in, cited_floor)

    assert len(stand_in.launches) == 4
    assert paired.run.complete_pairs == 1


def test_a_lean_session_whose_point_of_use_text_never_arrived_is_scored(
    checkout, moves_dir, move, stand_in, cited_floor
):
    paired = _paired(checkout, moves_dir, move, stand_in, cited_floor, max_tasks=1)

    lean = next(s for s in paired.run.common.sessions if s.arm == "lean")
    assert lean.status == "scored"
    assert all(
        a.__class__.__name__ != "Unknown" for t in lean.checks.values() for a in t.arrivals.values()
    )


# --- refusals: nothing launched, nothing written ---


def _refused(plan: RunPlan, stand_in: StandIn, moves_dir: Path, match: str) -> None:
    before = _files(moves_dir)

    with pytest.raises(RunRefusedError, match=match):
        _conduct(plan, stand_in)

    assert stand_in.launches == []
    assert _files(moves_dir) == before


def test_a_paired_run_citing_no_floor_run_is_refused(checkout, moves_dir, move, stand_in):
    _refused(
        _plan(checkout, moves_dir, move, kind="paired"), stand_in, moves_dir, "cites a finished"
    )


def test_a_paired_run_citing_a_floor_run_that_never_failed_a_check_is_refused_naming_it(
    checkout, moves_dir, move, stand_in
):
    conforming = _floor(checkout, moves_dir, move, StandIn(checkout, moves_dir))
    plan = _plan(checkout, moves_dir, move, kind="paired", floor_run=conforming.run.common.run_id)

    _refused(plan, stand_in, moves_dir, "never failed commit message form, staging by name")


def test_a_paired_run_on_a_checkout_the_floor_run_was_not_measured_on_is_refused(
    checkout, moves_dir, move, stand_in, cited_floor, tmp_path
):
    changed = tmp_path / "changed"
    shutil.copytree(checkout, changed)
    (changed / "hooks" / "extra.txt").write_text("not measured\n", encoding="utf-8")
    plan = _plan(changed, moves_dir, move, kind="paired", floor_run=cited_floor.run.common.run_id)

    _refused(plan, stand_in, moves_dir, "another identity.*tree")


def test_arms_that_would_differ_in_a_pinned_setting_are_refused_naming_it(
    checkout, moves_dir, move, stand_in
):
    differing = replace(move, launch={"floor": LaunchOptions(model="other-model")})

    _refused(_plan(checkout, moves_dir, differing), stand_in, moves_dir, "arms:.*model")


def test_a_move_without_a_task_kit_is_refused(checkout, moves_dir, stand_in):
    _refused(
        _plan(checkout, moves_dir, declaration.kit("adr-conventions")),
        stand_in,
        moves_dir,
        "no task kit",
    )


def test_a_floor_run_of_fewer_tasks_than_the_minimum_is_refused(
    checkout, moves_dir, move, stand_in
):
    _refused(_plan(checkout, moves_dir, move, max_tasks=5), stand_in, moves_dir, "at least 6")


# --- the plan of tasks ---


def _task(number: int) -> MoveTask:
    return MoveTask(f"t{number}", "f", "managed", "plain", f"w{number}", ("a.txt",))


def test_a_floor_run_takes_the_declared_handful_and_a_cap_lowers_both_kinds_of_run():
    drawn = tuple(_task(n) for n in range(24))

    assert len(runner.planned_tasks("floor", drawn, None)) == runner.DEFAULT_FLOOR_TASKS
    assert len(runner.planned_tasks("paired", drawn, None)) == 24
    assert len(runner.planned_tasks("paired", drawn, 3)) == 3
    assert runner.planned_tasks("floor", drawn, 7) == drawn[:7]


def test_a_cap_below_one_is_refused():
    with pytest.raises(RunRefusedError, match="at least one task"):
        runner.planned_tasks("paired", (_task(1),), 0)
