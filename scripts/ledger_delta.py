"""Typed rows and the state snapshot for the tech-debt ledger reader.

`ledger_snapshot.py` is the imperative shell -- it parses the ledger and reads the
ADR corpus and version-control history once, into the frozen types defined here.
`ledger_delta_signals.py` is the pure computation core: `row_delta(snapshot, row)`
computes one row's signals and context from a `StateSnapshot` alone, so every
signal is testable against a hand-built snapshot with no I/O. This module carries
neither shell nor computation -- only the schema both share, plus the handful of
parsing primitives (`cite_path`, `parse_iso_date`) small enough to travel with the
types they parse into.

Callers take the entry points (`gather`, `row_delta`) from `ledger_snapshot` and
the types from here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, NewType, assert_never

# -- Closed vocabularies ---------------------------------------------------------

TdId = NewType("TdId", str)
ActiveStatus = Literal["open", "in-flight"]
TerminalStatus = Literal["resolved", "wontfix"]
Outcome = Literal["kept", "realigned", "discarded", "merged"]
KeyStatus = Literal["plain", "discriminated", "collision-blocked", "nonconforming"]
PathCause = Literal["renamed", "deleted", "vanished", "unclassified"]
DecisionChange = Literal["superseded", "retired", "rejected", "narrowed"]
Oracle = Literal["git-history", "adr-corpus", "lifecycle-table"]

STAMP_PREFIX = "[triage "

# -- Notes citations ------------------------------------------------------------------
# `_BACKTICK_SPAN` / `_BARE_LINE_CITE` / `_PATH_SHAPE` (the citation-*finding* patterns)
# live in `ledger_delta_signals.py`, next to `notes_path_citations`, their only reader.
_CITE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?|::[\w.]+|#.*|§.*)$")


def cite_path(cite: str) -> str:
    """The repo path a cite names: line range, `::symbol`, `#anchor`, `§section` stripped."""
    return _CITE_SUFFIX.sub("", cite).removeprefix("./")


def parse_iso_date(cell: str) -> date | None:
    try:
        return date.fromisoformat(cell.strip())
    except ValueError:
        return None


# -- Parsed rows -------------------------------------------------------------------------


@dataclass(frozen=True)
class PathRef:
    path: str  # line range stripped
    raw: str


@dataclass(frozen=True)
class OpaqueRef:
    """A location that is not path-shaped (a DSL element id); no location oracle."""

    raw: str


LocationRef = PathRef | OpaqueRef


@dataclass(frozen=True)
class NoGoal:
    pass


@dataclass(frozen=True)
class AdrGoal:
    dec_id: str


@dataclass(frozen=True)
class DraftGoal:
    draft_id: str


@dataclass(frozen=True)
class OtherGoal:
    kind: str
    value: str


@dataclass(frozen=True)
class MalformedGoal:
    kind_raw: str
    value: str
    reason: str


GoalRef = NoGoal | AdrGoal | DraftGoal | OtherGoal | MalformedGoal


@dataclass(frozen=True)
class DecisionCitation:
    dec_id: str
    via: Literal["goal-ref", "notes"]


@dataclass(frozen=True)
class TriageStamp:
    date: date
    anchor: str
    outcome: Outcome
    text: str
    evidence_path: str | None  # `kept` only
    prior_key: str | None  # `realigned from <key>` only


@dataclass(frozen=True)
class Unjudged:
    pass


@dataclass(frozen=True)
class Judged:
    stamp: TriageStamp
    segment_index: int


@dataclass(frozen=True)
class StampMalformed:
    raw: str
    segment_index: int


StampState = Unjudged | Judged | StampMalformed


@dataclass(frozen=True)
class Anchored:
    """A stamp's `@<sha>` is an ancestor of HEAD: `sha` and its commit date."""

    sha: str
    date: date


@dataclass(frozen=True)
class Unanchored:
    """A stamp's `@<sha>` could not be resolved against HEAD, and why."""

    sha: str
    reason: Literal["unknown-object", "not-ancestor"]


@dataclass(frozen=True)
class AnchorWithheld:
    """No git history to resolve a stamp anchor against."""

    reason: str


Anchor = Anchored | Unanchored | AnchorWithheld


@dataclass(frozen=True)
class KeyFacts:
    written: str
    base: str
    resolved: str
    status: KeyStatus


@dataclass(frozen=True)
class Withheld:
    class_name: str
    reason: str
    scope: Literal["corpus", "row"]
    row_ids: tuple[str, ...]


@dataclass(frozen=True)
class ActiveRow:
    id: TdId
    status: ActiveStatus
    klass: str
    severity: str
    owner_role: str
    direction: str
    source: str
    locations: tuple[LocationRef, ...]
    goal: GoalRef
    first_seen: date | None
    last_seen: date | None
    notes: str
    segments: tuple[str, ...]
    stamp: StampState
    cited_decisions: tuple[DecisionCitation, ...]
    key: KeyFacts
    row_withheld: tuple[Withheld, ...]  # known at parse time: goal kind, dates, opaque refs
    line_no: int


@dataclass(frozen=True)
class TerminalPeer:
    id: TdId
    status: TerminalStatus
    klass: str
    base_key: str
    locations: tuple[LocationRef, ...]
    first_seen: date | None
    last_seen: date | None
    stamp: StampState


@dataclass(frozen=True)
class UnparseableRow:
    id_raw: str
    line_no: int
    reason: str


# -- World facts -------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionFacts:
    dec_id: str
    status: str
    date: str
    title: str
    summary: str
    affected_files: tuple[str, ...]
    edges: Mapping[str, tuple[str, ...]]  # frontmatter edge field -> ids
    # The ADR file, repo-relative: whether it sits in an anchor's tree is what
    # places the decision before or after a judgment. None when unknown.
    path: str | None = None


@dataclass(frozen=True)
class Commit:
    sha: str
    date: date
    subject: str
    td_ids: frozenset[str]
    paths: tuple[str, ...]


@dataclass(frozen=True)
class GitFacts:
    head_tree: frozenset[str]
    renames: dict[str, str]  # adr_health's index shape; never mutated
    deletions: dict[str, str]
    commits: tuple[Commit, ...]  # newest first
    merge_base: str | None  # merge-base(HEAD, default branch): the digest's stamp-with anchor
    anchors: Mapping[str, Anchor]  # every distinct stamp `@<sha>` among Judged rows, resolved once
    anchor_windows: Mapping[str, AnchorWindow]  # one entry per `Anchored` sha in `anchors`


@dataclass(frozen=True)
class StateSnapshot:
    repo_root: Path
    today: date
    head: str | None
    anchor: str | None  # `git.merge_base`, falling back to `head`; None when git is unavailable
    active_rows: tuple[ActiveRow, ...]
    terminal_peers: tuple[TerminalPeer, ...]
    unparseable: tuple[UnparseableRow, ...]
    decisions: Mapping[str, DecisionFacts]
    git: GitFacts | None
    lazy_shapes: tuple[str, ...] | None
    present_paths: frozenset[str]  # every referenced path found on disk, checked by the shell
    oracles: Mapping[Oracle, str | None]  # None == available, else the withheld reason
    withheld: tuple[Withheld, ...]


# -- Signals (the state delta) ---------------------------------------------------


@dataclass(frozen=True)
class LocationDecay:
    path: str
    cause: PathCause
    target: str | None  # renamed only
    event_at: date | None


@dataclass(frozen=True)
class CitationDecay:
    cite: str
    path: str
    cause: PathCause
    target: str | None  # the current path, when the rename index knows it
    event_at: date | None


@dataclass(frozen=True)
class CitedDecisionChanged:
    dec_id: str
    via: Literal["goal-ref", "notes"]
    change: DecisionChange
    by: tuple[str, ...]
    event_at: date | None


@dataclass(frozen=True)
class GoalLinkUnresolved:
    dec_id: str
    reason: Literal["absent", "draft-id"]


@dataclass(frozen=True)
class CitedByCommit:
    sha: str
    event_at: date
    subject: str


@dataclass(frozen=True)
class DuplicatePeer:
    peer_id: str
    peer_status: str
    basis: Literal["same-base-key", "refiled-after-realign"]


@dataclass(frozen=True)
class SelfAmended:
    segments: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceMoved:
    """`kept` only: the stamp's own evidence file was touched in the anchor window."""

    path: str
    commits: int
    latest_sha: str


@dataclass(frozen=True)
class SupersedingDecisionOnLocation:
    """Judged rows only: a decision new since the anchor supersedes or narrows
    another decision and overlaps this row's location -- read from the new
    decision's own edges, so a change to any decision counts, cited or not."""

    dec_id: str
    edges: tuple[str, ...]
    matched_paths: tuple[str, ...]
    event_at: date | None


@dataclass(frozen=True)
class JudgmentUnusable:
    reason: Literal["malformed", "unanchored", "outcome-status-mismatch"]
    detail: str


@dataclass(frozen=True)
class DiscardRecurred:
    """Terminal `wontfix` peers only: a discarded stamp whose row's `last-seen`
    moved later -- a producer silently absorbed a recurrence into the tombstone."""

    stamp_date: date
    last_seen: date


Signal = (
    LocationDecay
    | CitationDecay
    | CitedDecisionChanged
    | GoalLinkUnresolved
    | CitedByCommit
    | DuplicatePeer
    | SelfAmended
    | EvidenceMoved
    | SupersedingDecisionOnLocation
    | JudgmentUnusable
)


def signal_class_name(signal: Signal) -> str:
    """The class name the digest and the probe's policy table key on.

    `SupersedingDecisionOnLocation` shares `decision-drift`'s class name with
    `CitedDecisionChanged` -- they are the same evidence class at two tiers,
    distinguished by basis in the rendered detail, not by class name.
    """
    match signal:
        case LocationDecay():
            return "location-decay"
        case CitationDecay():
            return "citation-decay"
        case CitedDecisionChanged() | SupersedingDecisionOnLocation():
            return "decision-drift"
        case GoalLinkUnresolved():
            return "goal-link-unresolved"
        case CitedByCommit():
            return "cited-by-commit"
        case DuplicatePeer():
            return "possible-duplicate"
        case SelfAmended():
            return "self-amended"
        case EvidenceMoved():
            return "evidence-moved"
        case JudgmentUnusable():
            return "judgment-unusable"
        case _:
            assert_never(signal)


@dataclass(frozen=True)
class RelatedDecision:
    """An ADR linked to the row only by file overlap -- context, never evidence."""

    dec_id: str
    status: str
    date: str
    title: str
    summary: str
    edges: tuple[str, ...]
    matched_paths: tuple[str, ...]
    changes_prior: bool


@dataclass(frozen=True)
class RowContext:
    related_decisions: tuple[RelatedDecision, ...]  # newest first
    churn_commits: int
    churn_latest: date | None
    quiet_days: int | None
    # Every same-base-key peer in either file, never windowed: what a realign landed on,
    # whether or not the peer is still evidence against a judged row.
    same_base_peers: tuple[DuplicatePeer, ...]


@dataclass(frozen=True)
class FirstSeenWindow:
    start: date


@dataclass(frozen=True)
class AnchorWindow:
    """A `Judged` + `Anchored` row's window: `anchor..HEAD`, not `first-seen..HEAD`.

    `tree` is the anchor commit's own tree (what existed *then*, so a new
    superseding ADR or a since-deleted location can be told apart from one
    that was already gone). `commits` is `rev-list anchor..HEAD`, one read
    shared by every windowed signal for this anchor -- never a per-row call.
    """

    anchor: Anchored
    tree: frozenset[str]
    commits: tuple[Commit, ...]


@dataclass(frozen=True)
class NoWindow:
    reason: str


Window = FirstSeenWindow | AnchorWindow | NoWindow


@dataclass(frozen=True)
class RowDelta:
    row_id: str
    window: Window
    signals: tuple[Signal, ...]
    context: RowContext
    row_withheld: tuple[Withheld, ...]
