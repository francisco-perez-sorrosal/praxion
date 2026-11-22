"""The loop's checkpoint: each waiting pocket's whole suite, run once before `complete`.

When every step is done and a pocket waits (`_step_loop_checkpoint.waiting_pockets`),
`run_checkpoint` asks the test scope once for every pocket's whole-suite invocations and runs a
waiting pocket's the way a gate runs a widened pocket: detached, under the pocket's own bound,
found again by a later call, one pocket after another. A pocket's finished runs are read with
the gate's own reader and a rule that pends nothing (once every step is done no later step owns
a node), and recorded in one block of their own that belongs to no step.

A pocket's runs live in a directory keyed by the pocket, `HEAD` and the requests of its waiting
steps, so the same call made again attaches to the runs it started, and a remedy commit or a
new deferring step starts fresh ones. The block's heading names only the pocket and `HEAD`: at
one `HEAD` the waiting steps cannot change, because a deferral counts only once its step's commit
is made, so a heading already in the results file is the block of these runs and is never
written twice.

This module imports the gate's reader; the gate never imports it, so no cycle can form.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Union

from _step_loop_checkpoint import WaitingPocket, checkpoint_heading, covers_line
from _step_loop_files import STEP_LABEL, write_atomic
from _step_loop_gate import GateRun, render_result_line
from _step_loop_io import (
    RESOLVER,
    RESOLVER_TIMEOUT_SECONDS,
    PocketScope,
    ScopeRuns,
    head_sha,
    run_command,
    run_in_order,
    warned_bound,
)
from _step_loop_pocket_runs import (
    Observed,
    RunSpec,
    StillRunning,
    with_outcome_reports,
)
from _step_loop_record_gate import (
    GATE_DIRECTORY,
    RESULTS_FILE,
    SCOPE_COMMAND,
    SHORT_SHA_LENGTH,
    ScopeReading,
    read_scope,
)
from _step_loop_state import bare_id
from _step_schema import NoRun

if TYPE_CHECKING:
    from iteration_ledger import IterationRecord

RUN_DIRECTORY_PREFIX = "checkpoint-"
DIGEST_LENGTH = 12
_ROOT_SLUG = "root"  # the run directory's name for the root pocket, `.`
_NOT_A_NAME_CHARACTER = re.compile(r"[^A-Za-z0-9]+")
_WIDENED = "widened"  # the scope decision a whole-suite run is read under
_EVIDENCE_SEPARATOR = " | "

Invocation = tuple[str, tuple[str, ...]]  # (working directory under the repository, argv)


@dataclass(frozen=True)
class CheckpointGreen:
    """Every waiting pocket's whole suite passed: the loop may print `complete`."""


@dataclass(frozen=True)
class RedPocket:
    """A waiting pocket whose whole suite did not pass, with what its block says of the run."""

    pocket: WaitingPocket
    notes: tuple[str, ...]  # the `Cut off:` and `Failed:` lines
    deciding: str  # the `Result:` line

    @property
    def evidence(self) -> str:
        steps = ", ".join(f"{STEP_LABEL}{step_id}" for step_id in self.pocket.steps)
        shown = "; ".join((self.deciding, *self.notes))
        return f"pocket {self.pocket.root} is red (waiting steps: {steps}): {shown}"


@dataclass(frozen=True)
class CheckpointRed:
    """At least one waiting pocket is red; a pocket green in the same checkpoint is not listed."""

    pockets: tuple[RedPocket, ...]

    @property
    def evidence(self) -> str:
        return _EVIDENCE_SEPARATOR.join(pocket.evidence for pocket in self.pockets)


@dataclass(frozen=True)
class CheckpointRunning:
    """A pocket's run is still inside its bound when the call's wait ended; nothing after it
    started. The same call made again attaches to it."""

    run: StillRunning

    @property
    def description(self) -> str:
        run = self.run
        return f"{run.pocket} after {run.elapsed:.0f}s (bound {run.bound.seconds:g}s)"


CheckpointOutcome = Union[CheckpointGreen, CheckpointRed, CheckpointRunning]  # noqa: UP007 -- runtime value, 3.9 floor


def run_checkpoint(
    repo: Path,
    task_dir: Path,
    waiting: Sequence[WaitingPocket],
    records: Sequence[IterationRecord],
    give_up_at: float,
    environ: Mapping[str, str],
) -> CheckpointOutcome:
    """Run each waiting pocket's whole suite once, waiting until `give_up_at`, and record each
    finished pocket's block once. Still running wins over red, red over green."""
    head = head_sha(repo)[:SHORT_SHA_LENGTH]
    suites = whole_suites(repo)
    red = []
    for pocket in waiting:
        invocations = _suite_of(suites, pocket.root)
        if isinstance(invocations, NoRun):
            unrun = render_result_line(GateRun(SCOPE_COMMAND, invocations))
            red.append(RedPocket(pocket, (), unrun))
            continue
        run_dir = run_directory(task_dir, pocket, head, records)
        bound = warned_bound(repo, pocket.root, environ)
        specs = [
            RunSpec(run_dir, number, with_outcome_reports(argv), repo / cwd, bound)
            for number, (cwd, argv) in enumerate(invocations, start=1)
        ]
        runs = run_in_order(specs, give_up_at)
        if isinstance(runs[-1], StillRunning):
            return CheckpointRunning(runs[-1])
        reading = read_scope(_whole_suite(pocket.root, runs), _NOTHING_PENDS, repo)
        heading = checkpoint_heading(pocket.root, head)
        record_once(task_dir / RESULTS_FILE, heading, block(pocket, reading))
        if reading.deciding.red:
            red.append(RedPocket(pocket, reading.notes, render_result_line(reading.deciding)))
    return CheckpointRed(tuple(red)) if red else CheckpointGreen()


def block(pocket: WaitingPocket, reading: ScopeReading) -> tuple[str, ...]:
    """A finished pocket's block body: the steps it answers for, the gate's own `Scope:`,
    `Cut off:` and `Failed:` lines, and the deciding `Result:` line last."""
    return (
        covers_line(pocket.steps),
        *reading.scopes,
        *reading.notes,
        render_result_line(reading.deciding),
    )


def run_directory(
    task_dir: Path, pocket: WaitingPocket, head: str, records: Iterable[IterationRecord]
) -> Path:
    """Where a checkpoint run of `pocket` at `head` lives: one directory per pocket, `HEAD` and
    the requests of its waiting steps' committed attempts (the digest covers the root too, so
    two roots that read alike in a name never share one)."""
    requests = sorted(
        record.request
        for record in records
        if record.request is not None
        and record.commit is not None
        and bare_id(record.step) in pocket.steps
    )
    keyed = "\n".join((pocket.root, *requests)).encode("utf-8")
    digest = hashlib.sha256(keyed).hexdigest()[:DIGEST_LENGTH]
    slug = _NOT_A_NAME_CHARACTER.sub("-", pocket.root).strip("-") or _ROOT_SLUG
    return task_dir / GATE_DIRECTORY / f"{RUN_DIRECTORY_PREFIX}{slug}-{head}-{digest}"


def whole_suites(repo: Path) -> dict[str, tuple[Invocation, ...]] | NoRun:
    """Each pocket root's whole-suite invocations as the test scope lists them, or why the scope
    gave none."""
    ask = (sys.executable, str(RESOLVER), "--repo-root", str(repo), "--full", "--json")
    resolver = run_command(ask, repo, RESOLVER_TIMEOUT_SECONDS)
    if resolver.returncode != 0:
        return NoRun(
            f"the test scope did not resolve ({resolver.problem or f'exit {resolver.returncode}'})"
        )
    try:
        plan = json.loads(resolver.output)
    except json.JSONDecodeError:
        return NoRun("the test scope did not resolve (its answer is not JSON)")
    if not isinstance(plan, dict) or not isinstance(plan.get("pockets"), list):
        return NoRun("the test scope did not resolve (its answer lists no pockets)")
    return {
        entry["root"]: tuple((i["cwd"], tuple(i["argv"])) for i in entry["invocations"])
        for entry in plan["pockets"]
    }


def record_once(results: Path, heading: str, body: Sequence[str]) -> None:
    """Append the block under `heading` unless the results file holds that heading already."""
    text = results.read_text("utf-8") if results.is_file() else ""
    if heading in text.splitlines():
        return
    # No blank line is added before the heading: the last block above keeps its bytes, so the
    # append changes nothing but the new block, however a reader compares blocks across it.
    ended = text if not text or text.endswith("\n") else text + "\n"
    write_atomic(results, ended + "\n".join([heading, "", *body]) + "\n")


class _NothingPends:
    """The pending rule of a checkpoint run: every failure is the checkpoint's own."""

    def is_pending(self, node_id: str) -> bool:
        return False

    def is_pending_error(self, node_id: str) -> bool:
        return False


_NOTHING_PENDS = _NothingPends()


def _suite_of(
    suites: Mapping[str, tuple[Invocation, ...]] | NoRun, root: str
) -> tuple[Invocation, ...] | NoRun:
    """The pocket's whole-suite invocations, or why there are none to run."""
    if isinstance(suites, NoRun):
        return suites
    return suites.get(root) or NoRun(f"the test scope lists no whole suite for {root}")


def _whole_suite(root: str, runs: tuple[Observed, ...]) -> ScopeRuns:
    """The runs as the gate's reader takes a widened pocket's: listing no test file of its own."""
    return ScopeRuns(_WIDENED, (PocketScope(root, True, 0, runs),))
