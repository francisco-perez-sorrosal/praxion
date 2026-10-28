"""Driver for grading a move's sessions: the take, the trigger record, the checks and the verdict.

Scenarios describe sessions and outcomes in the specification's words; this module turns them
into what the runner reads. Nothing here asks a session to report anything: a session's take
and its arrivals are read from the session's own record.

Bound here, because the specification or the base commit fixes them:

- the shared verdict rule, reached through the adherence driver's `role_verdict` (the flip rule
  of dec-459 as dec-462 amends it), with each governed check graded on final state as a
  mechanical check;
- the exact one-sided allowance (dec-462 clause 1), computed here independently: under
  exchangeable arms each of `n` discordant pairs is a fair coin, the net discordance is
  `2B - n` with `B ~ Binomial(n, 1/2)`, and the allowance is the smallest `a` with
  `P(net > a) <= 1 - confidence`;
- planted end states: scratch git repositories with a git identity, the commits and untracked
  files a scenario names;
- a session record the reader cannot read: a file of lines that are not JSON;
- the frozen copies of real main-session records, each with the Claude Code version it was
  recorded on, read from `tests/fixtures/main_session_probes/`, found by walking up to the `tests/fixtures` directory.

Unbound until a binding step ties them to the designed surface: proving a planted session's
take; reading a trigger record; grading an end state by a governed check; the move verdict and
the move report over constructed pairs.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import comb
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.move_eval import Arm, Declared, FixtureKind, unbound

Final = Literal["passed", "failed"]
History = Literal["right first time", "repaired", "not repaired", "action never taken"]
Timing = Literal["before composition", "before execution", "after execution", "never", "unknown"]
Channel = Literal[
    "session start", "path-matched load", "hook context", "gate refusal", "project gating"
]
DEFAULT_CONFIDENCE = 0.95
DEFAULT_MARGIN_PP = 10.0


def _fixtures_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "fixtures"
        if parent.name == "tests" and candidate.is_dir():
            return candidate
    raise AssertionError("no tests/fixtures directory above this driver")


PROBES_DIR = _fixtures_dir() / "main_session_probes"
ProbeName = Literal[
    "a commit composed before its point-of-use context arrived, then amended",
    "a commit refused by a gate with a reason, then recomposed conforming",
    "a rule delivered at session start",
    "a path-matched load on a creating write",
]


# -- The take ---------------------------------------------------------------------------------

SessionStart = Literal[
    "the whole rule", "the resident kernel only", "one line of the rule", "no line of the rule"
]


@dataclass(frozen=True)
class PlantedSession:
    """A session record as the harness would leave it, described by what arrived."""

    arm: Arm
    at_session_start: SessionStart
    point_of_use_arrived: bool = True


@dataclass(frozen=True)
class Take:
    scored: bool
    reason: str | None  # why scoring was refused; None when scored
    trigger_failure: bool = False  # scored, and the point-of-use text never arrived


def prove_take(declared: Declared, planted: PlantedSession) -> Take:
    unbound(
        "the runner's take proof can be asked about one planted session record of a move's arm,"
        " with the record written in the harness's own form, and answers whether it is scored"
        " and why not"
    )


# -- The trigger record -----------------------------------------------------------------------


@dataclass(frozen=True)
class CheckTrigger:
    check: str
    arrivals: Mapping[Channel, Timing]  # every channel that carried the governing text
    final: Final | None  # None when the check grades no end state for this record
    history: History | None
    refusals: tuple[str, ...]  # a gate's refusal reasons, as recorded


def probe_record(name: ProbeName) -> Path:
    """A frozen real main-session record and, beside it, the Claude Code version that wrote it.

    Each kind is frozen as `<slug>.jsonl` (the session's own record, byte for byte) next to
    `<slug>.version` (one line: the Claude Code version it was recorded on, e.g. `2.1.310`).
    Until both exist the clause it proves is unproven over real records, and says so.
    """
    stem = PROBES_DIR / name.replace(" ", "-").replace(",", "")
    record, version = stem.with_suffix(".jsonl"), stem.with_suffix(".version")
    if not (record.is_file() and version.is_file() and version.read_text().strip()):
        unbound(
            "unproven over real records: no frozen real main-session record of this kind, with"
            f" the Claude Code version it was recorded on, is in tests/fixtures/main_session_probes/"
            f" (expected {record.name} and {version.name})"
        )
    return record


UnreadableShape = Literal["lines that are not JSON", "events of a later harness no reader knows"]
_UNREADABLE = {
    "lines that are not JSON": "not a session record\n{\x00 neither is this\n",
    "events of a later harness no reader knows": (
        '{"type": "session-v9", "version": "99.0.0", "payload": "opaque"}\n'
        '{"type": "attachments-v9", "version": "99.0.0", "blob": "b64:AAAA"}\n'
    ),
}


def unreadable_record(workspace: Path, shape: UnreadableShape = "lines that are not JSON") -> Path:
    """A constructed session record from which no arrival can be read."""
    path = workspace / "unreadable-session.jsonl"
    path.write_text(_UNREADABLE[shape], encoding="utf-8")
    return path


def trigger_records(declared: Declared, record: Path) -> tuple[CheckTrigger, ...]:
    """The trigger record of every governed check of the move over one session record."""
    unbound(
        "the runner's trigger record can be read for each governed check of a move over one"
        " session record, naming each channel's arrival timing, the final-state and history"
        " outcomes and any gate refusal"
    )


# -- Planted end states -----------------------------------------------------------------------


@dataclass(frozen=True)
class PlantedCommit:
    message: str
    files: Mapping[str, str]  # path -> content committed


@dataclass(frozen=True)
class EndState:
    repo: Path
    named_files: tuple[str, ...]


GIT_IDENTITY = {"user.name": "Fixture Person", "user.email": "fixture@example.invalid"}


def end_state(
    workspace: Path,
    commits: Sequence[PlantedCommit],
    untracked: Mapping[str, str],
    named_files: Sequence[str],
) -> EndState:
    """A repository left as a session might leave it: these commits, these files never added."""
    repo = workspace / "end-state"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Start the fixture")
    for commit in commits:
        for relpath, content in commit.files.items():
            (repo / relpath).parent.mkdir(parents=True, exist_ok=True)
            (repo / relpath).write_text(content, encoding="utf-8")
            _git(repo, "add", "--", relpath)
        _git(repo, "commit", "-q", "-m", commit.message)
    for relpath, content in untracked.items():
        (repo / relpath).write_text(content, encoding="utf-8")
    return EndState(repo, tuple(named_files))


def _git(root: Path, *args: str) -> str:
    identity = [arg for key, value in GIT_IDENTITY.items() for arg in ("-c", f"{key}={value}")]
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.run(
        ["git", *identity, "-c", "commit.gpgsign=false", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@dataclass(frozen=True)
class Grade:
    outcome: Final
    failed_parts: frozenset[str]  # the parts of the check that failed, each reported


def grade_end_state(declared: Declared, check: str, state: EndState) -> Grade:
    unbound(
        "a move's governed check can grade a planted end state (a repository and the files its"
        " request named) with no session, reporting the outcome and each failed part"
    )


# -- Constructed pairs, the verdict and the report --------------------------------------------


@dataclass(frozen=True)
class ArmOutcome:
    final: Mapping[str, Final]
    history: Mapping[str, History] = field(default_factory=dict)
    arrivals: Mapping[str, Mapping[Channel, Timing]] = field(default_factory=dict)


ERRORED = None  # an arm's session that errored: no outcome


@dataclass(frozen=True)
class MovePair:
    task_id: str
    fixture_kind: FixtureKind
    full: ArmOutcome | None
    lean: ArmOutcome | None


@dataclass(frozen=True)
class MoveMeasurement:
    move: str
    checks: tuple[str, ...]
    pairs: tuple[MovePair, ...]
    floor: tuple[ArmOutcome | None, ...] = ()
    margin_pp: float = DEFAULT_MARGIN_PP
    restricted_to: FixtureKind | None = None


@dataclass(frozen=True)
class MoveVerdict:
    check_verdicts: Mapping[str, str]  # "no regression" or "regression"
    allowances: Mapping[str, int]  # pairs, per governed check
    discordant: Mapping[str, int]
    complete_pairs: int
    cleared: bool | None  # None: underpowered, no clearance verdict


def move_verdict(measurement: MoveMeasurement) -> MoveVerdict:
    unbound(
        "the move verdict can be computed over constructed move pairs (final state, history and"
        " arrivals per arm and governed check) and floor sessions, with the move in the role's"
        " place"
    )


@dataclass(frozen=True)
class CheckReport:
    floor_failures: int
    floor_sessions: int
    final_failures: Mapping[Arm, int]
    history: Mapping[Arm, Mapping[History, int]]
    timing: Mapping[Arm, Mapping[Channel, Mapping[Timing, int]]]
    trigger_failures: Mapping[Arm, int]  # failures with no arrival
    failures_with_arrival: Mapping[Arm, int]
    allowance_pp: float
    sensitivity_shown: str  # the sensitivity line's figure as printed, to one decimal place
    not_covered: bool


@dataclass(frozen=True)
class MoveReport:
    text: str
    checks: Mapping[str, CheckReport]
    per_kind_pairs: Mapping[FixtureKind, int]
    pooled_verdict: Mapping[str, str]
    restriction: FixtureKind | None
    clearance_claim: str
    margin_pp: float


def move_report(measurement: MoveMeasurement) -> MoveReport:
    unbound(
        "the move report can be rendered from constructed move pairs and floor sessions, and its"
        " per-check figures, per-kind counts, restriction and clearance claim read back from it"
    )


def shared_rule_verdict(measurement: MoveMeasurement) -> Mapping[str, str]:
    """The shared flip rule's verdict over the same pairs, each governed check on final state."""
    checks = [adherence_eval.CheckSpec(name, "mechanical") for name in measurement.checks]
    pairs = [_role_pair(pair) for pair in measurement.pairs]
    settings = adherence_eval.FlipSettings(margin_pp=measurement.margin_pp)
    return dict(adherence_eval.role_verdict(checks, pairs, settings).check_verdicts)


def _role_pair(pair: MovePair) -> adherence_eval.Pair:
    errored = frozenset(
        arm for arm, side in (("full", pair.full), ("lean", pair.lean)) if side is None
    )
    return adherence_eval.Pair(
        dict(pair.full.final) if pair.full else {},
        dict(pair.lean.final) if pair.lean else {},
        errored,
    )


def exact_allowance(discordant: int, confidence: float = DEFAULT_CONFIDENCE) -> int:
    """The smallest net discordance an exchangeable pair of arms exceeds with at most 1 - confidence."""
    alpha = 1 - confidence
    for allowance in range(discordant + 1):
        exceed = sum(
            comb(discordant, lean_worse)
            for lean_worse in range(discordant + 1)
            if 2 * lean_worse - discordant > allowance
        )
        if exceed / 2**discordant <= alpha + 1e-12:
            return allowance
    return discordant


def pairs_of(
    count: int,
    kind: FixtureKind,
    full: Mapping[str, Final],
    lean: Mapping[str, Final],
    start: int = 0,
) -> tuple[MovePair, ...]:
    """`count` pairs over distinct tasks of one fixture kind, each with these final states."""
    return tuple(
        MovePair(
            f"{kind}-task-{start + i:03d}", kind, ArmOutcome(dict(full)), ArmOutcome(dict(lean))
        )
        for i in range(count)
    )
