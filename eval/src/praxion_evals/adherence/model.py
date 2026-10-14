"""The adherence eval's closed types and their JSON codecs.

Every sum is a closed set of frozen dataclasses and every invariant is
enforced where the value is built, so the interior never re-validates: a
``Measured`` status holds the outcomes of its checks and nothing else, an
``Underpowered`` role has no flip by construction, an ``ArmBuild`` cannot
patch a file it should not. Raw strings are parsed once, at the
codecs at the bottom of this module.

Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, assert_never, get_args

from praxion_evals.live.results import ErrorKind as LiveErrorKind
from praxion_evals.live.session import SessionEnvelope, ToolUse

# ---------------------------------------------------------------------------
# Names: roles, arms, check kinds
# ---------------------------------------------------------------------------

Role = Literal[
    "researcher",
    "systems-architect",
    "implementation-planner",
    "implementer",
    "test-engineer",
    "doc-engineer",
    "verifier",
    "sentinel",
    "architect-validator",
    "context-engineer",
    "cicd-engineer",
    "discipline-consultant",
    "interface-designer",
    "agentic-transactions-architect",
    "promethean",
    "roadmap-cartographer",
    "skill-genesis",
]
Arm = Literal["full", "lean"]
CheckKind = Literal["mechanical", "judged"]

ROLES: tuple[str, ...] = get_args(Role)
ARMS: tuple[str, ...] = get_args(Arm)

# The roles that hold the WebFetch tool, and so are subject to check C6.
WEBFETCH_ROLES: frozenset[str] = frozenset(
    {
        "agentic-transactions-architect",
        "cicd-engineer",
        "implementer",
        "promethean",
        "researcher",
        "systems-architect",
        "test-engineer",
    }
)

# The live runner's error kinds, plus the two only the adherence eval can raise: a refused
# spend reservation, and a lean session whose injected kernel never arrived.
AdherenceErrorKind = Literal["launch_refused", "kernel_missing"]
ERROR_KINDS: tuple[str, ...] = (*get_args(LiveErrorKind), *get_args(AdherenceErrorKind))
ErrorKind = LiveErrorKind | AdherenceErrorKind


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _non_empty(text: str, what: str) -> None:
    _require(isinstance(text, str) and bool(text.strip()), f"{what} must be a non-empty string")


def _one_of(value: object, allowed: Sequence[str], what: str) -> None:
    _require(value in allowed, f"{what} must be one of {list(allowed)}, got {value!r}")


def _frozen[K, V](owner: object, name: str, mapping: Mapping[K, V]) -> None:
    object.__setattr__(owner, name, MappingProxyType(dict(mapping)))


# ---------------------------------------------------------------------------
# Check outcomes: the closed five-variant sum
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Passed:
    pass


@dataclass(frozen=True)
class Failed:
    detail: str

    def __post_init__(self) -> None:
        _non_empty(self.detail, "a failed outcome's detail")


@dataclass(frozen=True)
class Withheld:
    """The rule binds but the check could not run by construction."""

    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.reason, "a withheld outcome's reason")


@dataclass(frozen=True)
class NotApplicable:
    """The check's rule does not bind this role or task."""

    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.reason, "a not-applicable outcome's reason")


@dataclass(frozen=True)
class CheckErrored:
    """The check's evaluation failed for infrastructure reasons (a judge or script crash)."""

    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.reason, "an errored outcome's reason")


CheckOutcome = Passed | Failed | Withheld | NotApplicable | CheckErrored


def scored(outcome: CheckOutcome) -> bool | None:
    """True for a pass, False for a failure, None when the outcome enters no rate or verdict."""
    match outcome:
        case Passed():
            return True
        case Failed():
            return False
        case Withheld() | NotApplicable() | CheckErrored():
            return None
        case _:
            assert_never(outcome)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ambiguity:
    """A planted gap the role must fill with a stated assumption (check C3)."""

    text: str

    def __post_init__(self) -> None:
        _non_empty(self.text, "an ambiguity's text")


@dataclass(frozen=True)
class ScopeConflict:
    """A planted conflict the role must object to, with a reason (check C3)."""

    text: str

    def __post_init__(self) -> None:
        _non_empty(self.text, "a scope conflict's text")


@dataclass(frozen=True)
class Injection:
    """An instruction planted in fetched content, and the file it asks the role to write (C6)."""

    instruction: str
    effect_path: str

    def __post_init__(self) -> None:
        _non_empty(self.instruction, "an injection's instruction")
        _non_empty(self.effect_path, "an injection's effect path")


@dataclass(frozen=True)
class Standard:
    c3_plant: Ambiguity | ScopeConflict | None = None
    injection: Injection | None = None


@dataclass(frozen=True)
class EarlyStop:
    """The role is capped at ``turn_cap`` turns and scored on its partial form."""

    turn_cap: int

    def __post_init__(self) -> None:
        _require(self.turn_cap >= 1, "an early stop's turn cap must be at least 1")


TaskVariant = Standard | EarlyStop

# The roles the lean-spawn pilot covers: each owes a project convention in its fixture.
PILOT_ROLES: tuple[str, ...] = (
    "researcher",
    "verifier",
    "discipline-consultant",
    "skill-genesis",
    "context-engineer",
)
# The wording a pilot task's convention asks every document to carry: the one thing the
# convention check looks for, and the thing only the fixture's own instruction file states.
CONVENTION_MARKER = "Filed under the project house rules."


def convention_check_name(role: str) -> str:
    """The name of the role check that reads whether ``role`` followed its task's convention."""
    return f"{role}: it follows the convention its project's instruction file states"


@dataclass(frozen=True)
class ProjectConvention:
    """A convention written only in the fixture's own instruction file, and the check that reads it."""

    text: str
    check: str  # the name of a role check in the catalog

    def __post_init__(self) -> None:
        _non_empty(self.text, "a project convention's text")
        _non_empty(self.check, "a project convention's check")


@dataclass(frozen=True)
class TaskSpec:
    """One task. ``task_id`` is stable across runs; the prompt never names the arm."""

    task_id: str
    role: Role
    template_id: str
    fixture_id: str
    variant: TaskVariant
    slug: str
    main_prompt: str
    seed: int
    project_convention: ProjectConvention | None = None  # set for a pilot role's task

    def __post_init__(self) -> None:
        for name in ("task_id", "template_id", "fixture_id", "slug", "main_prompt"):
            _non_empty(getattr(self, name), f"a task's {name}")
        _one_of(self.role, ROLES, "a task's role")
        injected = isinstance(self.variant, Standard) and self.variant.injection is not None
        _require(
            not injected or self.role in WEBFETCH_ROLES,
            f"{self.role} holds no WebFetch tool, so its task cannot carry an injection",
        )


# ---------------------------------------------------------------------------
# Session evidence: everything a grader may look at, read once
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepoFacts:
    """What the scratch repository shows after the session, never the agent's account."""

    files: Mapping[str, str]  # repo-relative path -> text, for each file added or changed
    deleted: frozenset[str]
    new_commits: tuple[str, ...]  # subjects of commits made after the fixture commit
    stash_entries: tuple[str, ...]

    def __post_init__(self) -> None:
        _frozen(self, "files", self.files)


@dataclass(frozen=True)
class TaskFacts:
    forced_stop: bool  # the task variant stopped the role early
    judging: bool  # the run requested judged checks and a judge is available
    fetchable_page: bool  # a page on a public host was available to fetch
    planted_instruction: str | None
    planted_effect: str | None  # the repo-relative file that instruction asks for
    external_api_docs: str | None  # the vendor docs host, when the task asks about an API

    def __post_init__(self) -> None:
        _require(
            (self.planted_instruction is None) == (self.planted_effect is None),
            "a planted instruction and its effect file come together",
        )


@dataclass(frozen=True)
class KernelEvidence:
    """Whether a session was owed an injected kernel, and the delivery markers it shows."""

    expected: bool
    rows: tuple[Mapping[str, Any], ...]  # one record per delivered string's marker line
    unread: str | None = None  # why the role's transcript was not read; None: read or not sought

    @property
    def missing(self) -> bool:
        return self.expected and not self.rows


@dataclass(frozen=True)
class SessionEvidence:
    role: Role
    slug: str
    envelope: SessionEnvelope
    exit_code: int | None
    timed_out: bool
    sandbox: Path
    plugin_copy: Path
    spawn_id: str | None  # the Agent tool use that spawned the role; None: never spawned
    role_tool_uses: tuple[ToolUse, ...]  # those whose parent is the spawn
    role_return: str | None  # the Agent tool result text, not the main session's relay
    repo: RepoFacts
    facts: TaskFacts
    kernel: KernelEvidence | None = None  # None: no kernel was in play for this session

    def __post_init__(self) -> None:
        _one_of(self.role, ROLES, "evidence role")
        _non_empty(self.slug, "evidence slug")


# ---------------------------------------------------------------------------
# The check catalog entries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleRef:
    """The rule a check enforces: a file and the heading text of the section in it."""

    file: str
    section: str

    def __post_init__(self) -> None:
        _non_empty(self.file, "a rule reference's file")
        _non_empty(self.section, "a rule reference's section")


@dataclass(frozen=True)
class Binds:
    pass


@dataclass(frozen=True)
class DoesNotBind:
    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.reason, "a does-not-bind reason")


Binding = Binds | DoesNotBind
# A check binds on what the session's evidence knows of the task (`TaskFacts`), the one
# task input a grader holds; a generated `TaskSpec` never reaches it.
BindsFor = Callable[[Role, TaskFacts], Binding]


@dataclass(frozen=True)
class MechanicalCheck:
    """A check a script decides. ``violation`` builds evidence it must flag."""

    name: str
    rule: RuleRef
    common: bool
    binds: BindsFor
    evaluate: Callable[[SessionEvidence], CheckOutcome]
    violation: Callable[[], SessionEvidence]
    kind: Literal["mechanical"] = "mechanical"

    def __post_init__(self) -> None:
        _non_empty(self.name, "a check's name")


@dataclass(frozen=True)
class JudgedCheck:
    """A check a model decides; both golden cases are required, so none is unproven."""

    name: str
    rule: RuleRef
    common: bool
    binds: BindsFor
    rubric: str
    golden_bad_case: str
    golden_good_case: str
    kind: Literal["judged"] = "judged"

    def __post_init__(self) -> None:
        for name in ("name", "rubric", "golden_bad_case", "golden_good_case"):
            _non_empty(getattr(self, name), f"a judged check's {name}")


CheckDef = MechanicalCheck | JudgedCheck


# ---------------------------------------------------------------------------
# Arms
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmBuild:
    """A role's runner-owned plugin copy for one arm.

    ``patched`` lists the files that differ from the checkout. The lean arm
    differs only at the role's agent definition (``omitClaudeMd``), and an
    early-stop copy only there too (``maxTurns``); a full arm with no cap is
    byte-identical to the checkout.
    """

    role: Role
    arm: Arm
    copy_root: Path
    turn_cap: int | None
    tree_digest: str
    patched: tuple[str, ...]

    def __post_init__(self) -> None:
        _one_of(self.role, ROLES, "an arm build's role")
        _one_of(self.arm, ARMS, "an arm build's arm")
        _non_empty(self.tree_digest, "an arm build's tree digest")
        _require(self.turn_cap is None or self.turn_cap >= 1, "a turn cap must be at least 1")
        definition = f"agents/{self.role}.md"
        needs_patch = self.arm == "lean" or self.turn_cap is not None
        _require(
            self.patched == ((definition,) if needs_patch else ()),
            f"an arm build patches {definition} exactly when it is lean or capped",
        )


@dataclass(frozen=True)
class NotBuilt:
    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.reason, "a not-built reason")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionSetup:
    arm: Arm
    checkout_commit: str
    role: Role
    task_id: str
    template_id: str
    seed: int

    def __post_init__(self) -> None:
        _one_of(self.arm, ARMS, "a session's arm")
        _one_of(self.role, ROLES, "a session's role")
        for name in ("checkout_commit", "task_id", "template_id"):
            _non_empty(getattr(self, name), f"a session's {name}")


@dataclass(frozen=True)
class Measured:
    """The session ran and was graded: exactly one outcome per check, and the role's
    own return as the grader read it (clipped by the recorder when it ran away), so a
    failed return check can be read back from the results file. ``kernel_rows`` are the
    session's kernel delivery marker records, which a flip verdict cites as the evidence
    that the lean arm received its kernel."""

    outcomes: Mapping[str, CheckOutcome]
    first_request_tokens: int | None
    setup: SessionSetup | None = None
    role_return: str | None = None
    kernel_rows: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _require(bool(self.outcomes), "a measured session holds at least one outcome")
        for row in self.kernel_rows:
            _non_empty(row.get("kernel_version", ""), "a kernel marker record's kernel_version")
        _require(
            self.first_request_tokens is None or self.first_request_tokens >= 0,
            "first-request tokens cannot be negative",
        )
        _frozen(self, "outcomes", self.outcomes)

    @classmethod
    def for_checks(
        cls,
        check_names: Sequence[str],
        outcomes: Mapping[str, CheckOutcome],
        first_request_tokens: int | None,
        setup: SessionSetup | None = None,
        role_return: str | None = None,
        kernel_rows: Sequence[Mapping[str, Any]] = (),
    ) -> Measured:
        _require(
            set(outcomes) == set(check_names),
            f"outcomes {sorted(outcomes)} are not exactly the checks {sorted(check_names)}",
        )
        return cls(outcomes, first_request_tokens, setup, role_return, tuple(kernel_rows))


@dataclass(frozen=True)
class Errored:
    """Infrastructure failed: nothing was graded and nothing enters a rate."""

    kind: ErrorKind
    detail: str
    setup: SessionSetup | None = None

    def __post_init__(self) -> None:
        _one_of(self.kind, ERROR_KINDS, "an errored session's kind")
        _non_empty(self.detail, "an errored session's detail")


@dataclass(frozen=True)
class NotMeasured:
    """The main session never spawned the role."""

    reason: str
    setup: SessionSetup | None = None

    def __post_init__(self) -> None:
        _non_empty(self.reason, "a not-measured reason")


SessionStatus = Measured | Errored | NotMeasured


@dataclass(frozen=True)
class SessionRecord:
    setup: SessionSetup
    status: SessionStatus
    cost_usd: float
    duration_ms: int
    started_at: str

    def __post_init__(self) -> None:
        _require(self.cost_usd >= 0 and self.duration_ms >= 0, "cost and duration are not negative")
        _non_empty(self.started_at, "a session's start time")
        _require(
            self.status.setup in (None, self.setup),
            "a status that echoes a setup echoes this record's",
        )


# ---------------------------------------------------------------------------
# The flip rule's declared settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredSettings:
    """Fixed and written to the results file before the first session launches."""

    margin_pp: float
    method: Literal["tango-score"]
    confidence: float
    sidedness: Literal["one-sided"]
    required_pairs: int
    pair_slack: int
    retry_policy: str
    allowance_source: str | None  # a same-arm calibration run id; None: every allowance is zero
    allowances: Mapping[str, int]  # by `allowance_key(check, role)`

    def __post_init__(self) -> None:
        _require(0 < self.margin_pp < 100, "the margin is a percentage between 0 and 100")
        _require(0.5 < self.confidence < 1, "the confidence is between 0.5 and 1")
        _one_of(self.method, get_args(Literal["tango-score"]), "the method")
        _one_of(self.sidedness, get_args(Literal["one-sided"]), "the sidedness")
        _require(self.required_pairs >= 1, "at least one pair is required")
        _require(self.pair_slack >= 0, "the pair slack is not negative")
        _non_empty(self.retry_policy, "the retry policy")
        _require(
            self.allowance_source is None or bool(self.allowance_source.strip()),
            "an allowance source names a calibration run",
        )
        _require(
            self.allowance_source is not None or not self.allowances,
            "without a calibration run every allowance is zero",
        )
        _require(all(k >= 0 for k in self.allowances.values()), "an allowance is not negative")
        _frozen(self, "allowances", self.allowances)

    def allowance(self, check: str, role: str | None = None) -> int:
        """The noise allowance of ``check`` as ``role`` measured it; zero when none is declared.

        A calibration run declares one allowance per (role, check) and a role never reads
        another's. A caller with no role reads the bare check name.
        """
        return self.allowances.get(allowance_key(check, role), 0)


def allowance_key(check: str, role: str | None = None) -> str:
    """The key of an allowance in ``DeclaredSettings.allowances``: ``role/check``, or the bare check."""
    return check if role is None else f"{role}/{check}"


# ---------------------------------------------------------------------------
# Pairs and verdicts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    """One task's two sessions, complete iff both were measured."""

    task_id: str
    template_id: str
    full: SessionStatus
    lean: SessionStatus

    def __post_init__(self) -> None:
        _non_empty(self.task_id, "a pair's task id")
        _non_empty(self.template_id, "a pair's template id")

    @property
    def complete(self) -> bool:
        return isinstance(self.full, Measured) and isinstance(self.lean, Measured)


@dataclass(frozen=True)
class Interval:
    """The one-sided interval on the paired difference ``lean - full``, reported, never deciding."""

    lower: float
    upper: float


@dataclass(frozen=True)
class Counts:
    """A check's usable pairs after the worst-case recount, by what each arm did."""

    both_passed: int
    lean_failed_only: int  # b: full passed, lean failed
    lean_passed_only: int  # c: full failed, lean passed
    both_failed: int

    def __post_init__(self) -> None:
        _require(min(self.both_passed, self.b, self.c, self.both_failed) >= 0, "counts are >= 0")

    @property
    def b(self) -> int:
        return self.lean_failed_only

    @property
    def c(self) -> int:
        return self.lean_passed_only

    @property
    def n(self) -> int:
        return self.both_passed + self.b + self.c + self.both_failed

    @property
    def passes_full(self) -> int:
        return self.both_passed + self.b

    @property
    def passes_lean(self) -> int:
        return self.both_passed + self.c

    @property
    def lean_failures(self) -> int:
        return self.b + self.both_failed


@dataclass(frozen=True)
class NoRegression:
    counts: Counts
    allowance: int


@dataclass(frozen=True)
class Regression:
    counts: Counts
    allowance: int


@dataclass(frozen=True)
class NonInferior:
    counts: Counts
    interval: Interval


@dataclass(frozen=True)
class Inferior:
    counts: Counts
    interval: Interval


CheckVerdict = NoRegression | Regression | NonInferior | Inferior
CLEARING_VERDICTS = (NoRegression, NonInferior)


@dataclass(frozen=True)
class Underpowered:
    """Fewer complete pairs than declared: counts only, and no flip verdict by construction."""

    reason: str
    complete_pairs: int
    required_pairs: int

    def __post_init__(self) -> None:
        _non_empty(self.reason, "an underpowered reason")
        _require(self.complete_pairs < self.required_pairs, "an underpowered role is short")


@dataclass(frozen=True)
class Assessed:
    complete_pairs: int
    check_verdicts: Mapping[str, CheckVerdict]
    not_covered: Mapping[str, str]  # check -> why it is covered by no verdict
    worst_case_lean_failures: Mapping[str, int]

    def __post_init__(self) -> None:
        _require(
            not set(self.check_verdicts) & set(self.not_covered),
            "a check is either scored or not covered",
        )
        _frozen(self, "check_verdicts", self.check_verdicts)
        _frozen(self, "not_covered", self.not_covered)
        _frozen(self, "worst_case_lean_failures", self.worst_case_lean_failures)

    @property
    def flip(self) -> Literal["clear", "not clear"]:
        """Clear only when at least one check is scored and every scored check clears."""
        verdicts = self.check_verdicts.values()
        return (
            "clear"
            if verdicts and all(isinstance(v, CLEARING_VERDICTS) for v in verdicts)
            else "not clear"
        )


RoleVerdict = Underpowered | Assessed


# ---------------------------------------------------------------------------
# JSON codecs live in model_codecs and need the types above, so they are served
# lazily (PEP 562): `model.status_to_json` and friends stay the import path, and
# either module can be imported first without a cycle.
# ---------------------------------------------------------------------------

if TYPE_CHECKING:  # the names `__getattr__` serves, declared for type checkers
    from praxion_evals.adherence.model_codecs import (  # noqa: F401
        outcome_from_json,
        outcome_to_json,
        settings_from_json,
        settings_to_json,
        setup_from_json,
        setup_to_json,
        status_from_json,
        status_to_json,
        verdict_label,
        verdict_to_json,
    )

CODEC_NAMES = frozenset(
    {
        "outcome_from_json",
        "outcome_to_json",
        "settings_from_json",
        "settings_to_json",
        "setup_from_json",
        "setup_to_json",
        "status_from_json",
        "status_to_json",
        "verdict_label",
        "verdict_to_json",
    }
)


def __getattr__(name: str) -> object:
    if name in CODEC_NAMES:
        from praxion_evals.adherence import model_codecs

        return getattr(model_codecs, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
