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

- the take proof over a planted session record, the trigger record over a session record, the
  grade of a planted end state, and the verdict and report over constructed measurements, each
  a call into the eval pocket (`move_pocket`), the records written by `move_records`.

Their result shapes, pinned here for the production side to meet (a mismatch is a question to
the planner, never a silent driver edit): `moves.take.prove(declaration, arm, record_path)`
returns a frozen dataclass with `scored` (bool), `reason` (str or None) and `trigger_failure`
(bool); `moves.trigger.records(declaration, record_path)` returns one frozen dataclass per
governed check with `check`, `arrivals` (channel -> timing word, in the results file's form),
`final` ("passed" or "failed", or None), `history` and `refusals` (a list of reasons). Channels
are the declaration's names (`session_start`, `path_matched`, `hook_context`, `gate_refusal`,
`project_gating`) and history words may use underscores; the readers below put both in the
scenarios' words. `prove` takes no checkout, so the moved rule's text reaches it through the
declaration.

`moves.checks_git.grade(declaration, check, repo, named_files)` takes the check's name and the
named files as a tuple, and returns `outcome` ("passed" or "failed") and `failed_parts` (a list
of part names). `moves.verdict.move_verdict(measurement)` returns `check_verdicts`, `allowances`
and `discordant` (check -> value) and `complete_pairs`, with `cleared` optional. The measurement
is the JSON of `moves.verdict.Measurement.from_json` and `moves.report.render(measurement)`
returns the report text: arrivals are keyed by the declaration's channel names, history and
timing are the specification's words, and the report prints its figures as the lines
`move_report` documents.

Nothing in this module remains unbound.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import comb
from pathlib import Path
from typing import Any, Literal, cast

from tests.acceptance.drivers import adherence_eval, move_declarations, move_pocket, move_records
from tests.acceptance.drivers.move_eval import TARGET_PAIRS, Arm, Declared, FixtureKind, unbound
from tests.acceptance.drivers.move_records import SessionStart

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


@dataclass(frozen=True)
class PlantedSession:
    """A session record as the harness would leave it, described by what arrived.

    Point-of-use text belongs to the lean arm's delivery, so the flag matters to a lean record only.
    """

    arm: Arm
    at_session_start: SessionStart
    point_of_use_arrived: bool = True


@dataclass(frozen=True)
class Take:
    scored: bool
    reason: str | None  # why scoring was refused; None when scored
    trigger_failure: bool = False  # scored, and the point-of-use text never arrived


_PROVE_TAKE = """
from praxion_evals.adherence.moves import take
emit(dataclasses.asdict(take.prove(declared, request["arm"], Path(request["record"]))))
"""


def prove_take(declared: Declared, planted: PlantedSession) -> Take:
    """Plant one session record from `planted` and ask the runner whether its arm took."""
    payload = move_declarations.declared_payload(declared.move, declared.path)
    with tempfile.TemporaryDirectory(prefix="planted-session-") as scratch:
        record = move_records.plant_session(
            Path(scratch) / "session.jsonl",
            payload,
            planted.arm,
            planted.at_session_start,
            planted.point_of_use_arrived,
        )
        answer = move_pocket.call_with_declaration(
            _PROVE_TAKE, declared.move, declared.path, {"arm": planted.arm, "record": str(record)}
        )
    try:
        return Take(answer["scored"], answer["reason"], answer["trigger_failure"])
    except KeyError as missing:
        raise AssertionError(
            f"the take proof answered {answer!r}, which lacks {missing}: it returns scored,"
            " reason and trigger_failure"
        ) from missing


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


_TRIGGER_RECORDS = """
from praxion_evals.adherence.moves import trigger
emit([dataclasses.asdict(t) for t in trigger.records(declared, Path(request["record"]))])
"""
_CHANNEL_WORDS = {
    "session_start": "session start",
    "path_matched": "path-matched load",
    "hook_context": "hook context",
    "gate_refusal": "gate refusal",
    "project_gating": "project gating",
}
_HISTORY_WORDS = {"never taken": "action never taken"}


def trigger_records(declared: Declared, record: Path) -> tuple[CheckTrigger, ...]:
    """The trigger record of every governed check of the move over one session record."""
    answer = move_pocket.call_with_declaration(
        _TRIGGER_RECORDS, declared.move, declared.path, {"record": str(record)}
    )
    return tuple(_check_trigger(entry) for entry in answer)


def _check_trigger(entry: Mapping[str, Any]) -> CheckTrigger:
    return CheckTrigger(
        entry["check"],
        {
            cast(Channel, _CHANNEL_WORDS.get(channel, channel)): cast(Timing, timing)
            for channel, timing in entry["arrivals"].items()
        },
        entry["final"],
        _history_word(entry["history"]),
        tuple(entry["refusals"]),
    )


def _history_word(history: str | None) -> History | None:
    if history is None:
        return None
    spaced = history.replace("_", " ")
    return cast(History, _HISTORY_WORDS.get(spaced, spaced))


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


_GRADE_END_STATE = """
from praxion_evals.adherence.moves import checks_git
emit(
    dataclasses.asdict(
        checks_git.grade(
            declared, request["check"], Path(request["repo"]), tuple(request["named_files"])
        )
    )
)
"""


def grade_end_state(declared: Declared, check: str, state: EndState) -> Grade:
    """Ask the named governed check to grade a planted end state, with no session."""
    answer = move_pocket.call_with_declaration(
        _GRADE_END_STATE,
        declared.move,
        declared.path,
        {"check": check, "repo": str(state.repo), "named_files": list(state.named_files)},
    )
    try:
        return Grade(answer["outcome"], frozenset(answer["failed_parts"]))
    except KeyError as missing:
        raise AssertionError(
            f"the grade answered {answer!r}, which lacks {missing}: it returns outcome and"
            " failed_parts"
        ) from missing


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


_CHANNEL_NAMES = {words: name for name, words in _CHANNEL_WORDS.items()}


def _measurement_json(measurement: MoveMeasurement) -> dict[str, Any]:
    """The measurement in the form `Measurement.from_json` reads."""
    return {
        "checks": list(measurement.checks),
        "margin_pp": measurement.margin_pp,
        "target_pairs": TARGET_PAIRS,
        "kind_restriction": measurement.restricted_to,
        "pairs": [
            {
                "task_id": pair.task_id,
                "fixture_kind": pair.fixture_kind,
                "full": _side_json(pair.full),
                "lean": _side_json(pair.lean),
            }
            for pair in measurement.pairs
        ],
        "floor": [None if s is None else {"final": dict(s.final)} for s in measurement.floor],
    }


def _side_json(outcome: ArmOutcome | None) -> dict[str, Any] | None:
    if outcome is None:
        return None  # the arm's session errored
    return {
        "final": dict(outcome.final),
        "history": dict(outcome.history),
        "arrivals": {
            check: {_CHANNEL_NAMES[channel]: timing for channel, timing in arrived.items()}
            for check, arrived in outcome.arrivals.items()
        },
    }


_MOVE_VERDICT = """
from praxion_evals.adherence.moves.verdict import Measurement, move_verdict
emit(dataclasses.asdict(move_verdict(Measurement.from_json(request["measurement"]))))
"""


def move_verdict(measurement: MoveMeasurement) -> MoveVerdict:
    """The move verdict over constructed pairs and floor sessions."""
    answer = move_pocket.call_in_pocket(
        _MOVE_VERDICT, {"measurement": _measurement_json(measurement)}
    )
    try:
        return MoveVerdict(
            answer["check_verdicts"],
            answer["allowances"],
            answer["discordant"],
            answer["complete_pairs"],
            answer.get("cleared"),
        )
    except KeyError as missing:
        raise AssertionError(
            f"the verdict answered {answer!r}, which lacks {missing}: it returns check_verdicts,"
            " allowances, discordant and complete_pairs"
        ) from missing


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


_MOVE_REPORT = """
from praxion_evals.adherence.moves import report
from praxion_evals.adherence.moves.verdict import Measurement
emit(report.render(Measurement.from_json(request["measurement"])))
"""
_FIGURE = "figure | "


def move_report(measurement: MoveMeasurement) -> MoveReport:
    """Render the report over constructed pairs and floor sessions, and read its figures back.

    The report is prose with its figures also printed as lines `figure | <subject> | <topic> |
    <values...>`, fields separated by ` | `, in the specification's words (channels by the
    declaration's names). The subject is a governed check's name, or `run`:

        figure | <check> | floor | <failures> | <scored sessions>
        figure | <check> | final | <arm> | <failures>
        figure | <check> | history | <arm> | <history word> | <sessions>
        figure | <check> | timing | <arm> | <channel> | <timing word> | <sessions>
        figure | <check> | trigger | <arm> | <trigger failures> | <failures with arrival>
        figure | <check> | allowance | <points, one decimal>
        figure | <check> | sensitivity | <figure as printed, one decimal>
        figure | <check> | coverage | covered | not covered
        figure | <check> | verdict | <word>
        figure | run | kind | <fixture kind> | <pairs>
        figure | run | restriction | <fixture kind> | none
        figure | run | margin | <points>
        figure | run | clearance | <the clearance claim, as one line>
    """
    text = move_pocket.call_in_pocket(_MOVE_REPORT, {"measurement": _measurement_json(measurement)})
    return _read_report(text, measurement.checks)


def _read_report(text: str, checks: Sequence[str]) -> MoveReport:
    rows: dict[str, list[tuple[str, list[str]]]] = {}
    for line in text.splitlines():
        if line.startswith(_FIGURE):
            _, subject, topic, *values = line.split(" | ")
            rows.setdefault(subject, []).append((topic, values))
    run = rows.get("run", [])
    return MoveReport(
        text=text,
        checks={check: _check_report(check, rows.get(check, [])) for check in checks},
        per_kind_pairs={cast(FixtureKind, v[0]): int(v[1]) for t, v in run if t == "kind"},
        pooled_verdict={check: _only(check, rows.get(check, []), "verdict")[0] for check in checks},
        restriction=_restriction(_only("run", run, "restriction")[0]),
        clearance_claim=_only("run", run, "clearance")[0],
        margin_pp=float(_only("run", run, "margin")[0]),
    )


def _check_report(check: str, rows: list[tuple[str, list[str]]]) -> CheckReport:
    history: dict[str, dict[str, int]] = {}
    timing: dict[str, dict[str, dict[str, int]]] = {}
    for topic, values in rows:
        if topic == "history":
            arm, word, sessions = values
            history.setdefault(arm, {})[_history_word(word) or word] = int(sessions)
        elif topic == "timing":
            arm, channel, when, sessions = values
            channel_words = _CHANNEL_WORDS.get(channel, channel)
            timing.setdefault(arm, {}).setdefault(channel_words, {})[when] = int(sessions)
    floor_failures, floor_sessions = _only(check, rows, "floor")
    return CheckReport(
        floor_failures=int(floor_failures),
        floor_sessions=int(floor_sessions),
        final_failures=_per_arm(rows, "final", 1),
        history=cast(Any, history),
        timing=cast(Any, timing),
        trigger_failures=_per_arm(rows, "trigger", 1),
        failures_with_arrival=_per_arm(rows, "trigger", 2),
        allowance_pp=float(_only(check, rows, "allowance")[0]),
        sensitivity_shown=_only(check, rows, "sensitivity")[0],
        not_covered=_only(check, rows, "coverage")[0] == "not covered",
    )


def _per_arm(rows: list[tuple[str, list[str]]], topic: str, index: int) -> dict[Arm, int]:
    return {cast(Arm, values[0]): int(values[index]) for t, values in rows if t == topic}


def _only(subject: str, rows: list[tuple[str, list[str]]], topic: str) -> list[str]:
    found = [values for row_topic, values in rows if row_topic == topic]
    assert len(found) == 1, (
        f"the report prints {len(found)} lines `{_FIGURE}{subject} | {topic} | ...`, not one"
    )
    return found[0]


def _restriction(word: str) -> FixtureKind | None:
    return None if word == "none" else cast(FixtureKind, word)


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
