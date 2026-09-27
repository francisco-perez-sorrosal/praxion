"""Pure core of the tech-debt ledger reader: typed rows, the snapshot, the per-row delta.

`ledger_snapshot.py` is the imperative shell -- it parses the ledger and reads git
and the ADR corpus once, into the frozen types defined here. This module does no
I/O: `row_delta(snapshot, row)` computes one row's signals and context from the
snapshot alone, so every signal is testable against a hand-built snapshot.

Consumers import the reader's public surface from `ledger_snapshot`, which
re-exports what they need from here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, NewType, assert_never

from adr_health import _EPHEMERAL_ROOTS, _SHAPE, _deletion_date, _matches_shape, _rename_target
from query_adrs import paths_match

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
_STATE_ROOT = ".ai-state/"
# Frontmatter edges by which a decision narrows or replaces an earlier one.
_CHANGING_EDGES = ("supersedes", "supersedes_in_part")

# -- Notes citations ------------------------------------------------------------------
_BACKTICK_SPAN = re.compile(r"`([^`\n]+)`")
_BARE_LINE_CITE = re.compile(r"(?<![\w/.`-])((?:[\w.-]+/)+[\w.-]+\.\w+):\d+(?:-\d+)?")
_CITE_SUFFIX = re.compile(r"(?::\d+(?:-\d+)?|::[\w.]+|#.*|§.*)$")
# At least two components: a lone `references/` is relative to some unnamed directory.
_PATH_SHAPE = re.compile(r"^[\w.@+-]+/(?:[\w.@+-]+/)*(?:[\w@+-][\w.@+-]*\.\w+|[\w.@+-]+/)$")


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
    renames: Mapping[str, str]
    deletions: Mapping[str, str]
    commits: tuple[Commit, ...]  # newest first


@dataclass(frozen=True)
class StateSnapshot:
    repo_root: Path
    today: date
    head: str | None
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
    basis: Literal["same-base-key"]


@dataclass(frozen=True)
class SelfAmended:
    segments: tuple[str, ...]


Signal = (
    LocationDecay
    | CitationDecay
    | CitedDecisionChanged
    | GoalLinkUnresolved
    | CitedByCommit
    | DuplicatePeer
    | SelfAmended
)


def signal_class_name(signal: Signal) -> str:
    """The class name the digest and the probe's policy table key on."""
    match signal:
        case LocationDecay():
            return "location-decay"
        case CitationDecay():
            return "citation-decay"
        case CitedDecisionChanged():
            return "decision-drift"
        case GoalLinkUnresolved():
            return "goal-link-unresolved"
        case CitedByCommit():
            return "cited-by-commit"
        case DuplicatePeer():
            return "possible-duplicate"
        case SelfAmended():
            return "self-amended"
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


@dataclass(frozen=True)
class FirstSeenWindow:
    start: date


@dataclass(frozen=True)
class NoWindow:
    reason: str


Window = FirstSeenWindow | NoWindow


@dataclass(frozen=True)
class RowDelta:
    row_id: str
    window: Window
    signals: tuple[Signal, ...]
    context: RowContext
    row_withheld: tuple[Withheld, ...]


# -- The pure delta ------------------------------------------------------------------------


def row_delta(snapshot: StateSnapshot, row: ActiveRow) -> RowDelta:
    """Every signal and every piece of context for one row, over the row's window.

    The window is chosen first and handed to each windowed signal; no signal
    function reads the row's stamp to pick its own.
    """
    window: Window = (
        FirstSeenWindow(row.first_seen) if row.first_seen else NoWindow("first-seen-malformed")
    )
    signals: tuple[Signal, ...] = (
        *_location_decay(snapshot, row),
        *_citation_decay(snapshot, row),
        *_decision_drift(snapshot, row),
        *_goal_link(snapshot, row),
        *_cited_by_commit(snapshot, row, window),
        *_duplicates(snapshot, row),
        *_self_amended(row),
    )
    return RowDelta(
        row_id=row.id,
        window=window,
        signals=signals,
        context=_context(snapshot, row, window),
        row_withheld=row.row_withheld,
    )


def _path_fate(
    snapshot: StateSnapshot, path: str
) -> tuple[PathCause, str | None, date | None] | None:
    """None when `path` resolves (on disk or at HEAD); else why it does not."""
    git = snapshot.git
    if path in snapshot.present_paths or (git and _in_tree(git.head_tree, path)):
        return None
    if git is None:
        return ("unclassified", None, None)
    target = _rename_target(path, git.renames)
    if target:
        return ("renamed", target, None)
    deleted = _deletion_date(path, git.deletions)
    if deleted:
        return ("deleted", None, parse_iso_date(deleted))
    return (
        ("vanished", None, None)
        if snapshot.lazy_shapes is not None
        else ("unclassified", None, None)
    )


def _in_tree(tree: frozenset[str], path: str) -> bool:
    if path in tree:
        return True
    prefix = path.rstrip("/") + "/"
    return any(entry.startswith(prefix) for entry in tree)


def _is_lazy(snapshot: StateSnapshot, path: str) -> bool:
    return any(_matches_shape(path, shape) for shape in snapshot.lazy_shapes or ())


def _location_decay(snapshot: StateSnapshot, row: ActiveRow) -> list[LocationDecay]:
    decays = []
    for ref in row.locations:
        if not isinstance(ref, PathRef) or _is_lazy(snapshot, ref.path):
            continue
        fate = _path_fate(snapshot, ref.path)
        if fate is not None:
            decays.append(LocationDecay(ref.path, *fate))
    return decays


def _citation_decay(snapshot: StateSnapshot, row: ActiveRow) -> list[CitationDecay]:
    decays = []
    for cite, path in notes_path_citations(row.notes):
        if _is_lazy(snapshot, path):
            continue
        fate = _path_fate(snapshot, path)
        if fate is not None:
            decays.append(CitationDecay(cite, path, *fate))
    return decays


def notes_path_citations(notes: str) -> tuple[tuple[str, str], ...]:
    """(cite as written, repo path) for every backticked path and bare `path:line`.

    Ephemeral roots, home-relative and absolute paths, URLs and placeholder shapes
    are not claims about this repository's tree, so they are never cited paths.
    """
    candidates = [span.strip() for span in _BACKTICK_SPAN.findall(notes)]
    candidates += [found.group(0) for found in _BARE_LINE_CITE.finditer(notes)]
    cites: dict[str, str] = {}
    for cite in candidates:
        path = cite_path(cite)
        if cite in cites or not _PATH_SHAPE.match(path) or _SHAPE.search(path):
            continue
        if path.startswith(("~", "/")) or "://" in cite or path.startswith(_EPHEMERAL_ROOTS):
            continue
        cites[cite] = path
    return tuple(cites.items())


def _decision_drift(snapshot: StateSnapshot, row: ActiveRow) -> list[CitedDecisionChanged]:
    drifts = []
    for citation in row.cited_decisions:
        facts = snapshot.decisions.get(citation.dec_id)
        change = _decision_change(facts) if facts else None
        if facts is None or change is None:
            continue
        kind, by = change
        successor = snapshot.decisions.get(by[0]) if by else None
        event_at = parse_iso_date(successor.date) if successor else None
        drifts.append(CitedDecisionChanged(citation.dec_id, citation.via, kind, by, event_at))
    return drifts


def _decision_change(facts: DecisionFacts) -> tuple[DecisionChange, tuple[str, ...]] | None:
    if facts.status == "superseded":
        return ("superseded", facts.edges["superseded_by"])
    if facts.status == "retired":
        return ("retired", facts.edges["retired_by"])
    if facts.status == "rejected":
        return ("rejected", ())
    narrowed = facts.edges["superseded_in_part_by"]
    return ("narrowed", narrowed) if narrowed else None


def _goal_link(snapshot: StateSnapshot, row: ActiveRow) -> list[GoalLinkUnresolved]:
    if not snapshot.decisions:
        return []
    match row.goal:
        case AdrGoal(dec_id=dec_id) if dec_id not in snapshot.decisions:
            return [GoalLinkUnresolved(dec_id, "absent")]
        case DraftGoal(draft_id=draft_id):
            return [GoalLinkUnresolved(draft_id, "draft-id")]
        case _:
            return []


def _cited_by_commit(
    snapshot: StateSnapshot, row: ActiveRow, window: Window
) -> list[CitedByCommit]:
    if snapshot.git is None or not isinstance(window, FirstSeenWindow):
        return []
    return [
        CitedByCommit(commit.sha, commit.date, commit.subject)
        for commit in snapshot.git.commits
        if row.id in commit.td_ids
        and commit.date > window.start
        and any(not path.startswith(_STATE_ROOT) for path in commit.paths)
    ]


def _duplicates(snapshot: StateSnapshot, row: ActiveRow) -> list[DuplicatePeer]:
    peers = [(other.id, other.status, other.key.base) for other in snapshot.active_rows]
    peers += [(peer.id, peer.status, peer.base_key) for peer in snapshot.terminal_peers]
    return [
        DuplicatePeer(peer_id, status, "same-base-key")
        for peer_id, status, base in peers
        if base == row.key.base and peer_id != row.id
    ]


def _self_amended(row: ActiveRow) -> list[SelfAmended]:
    """Non-stamp segments written after the latest usable judgment.

    Unjudged (or unusably judged): the first segment is the filing, so any later
    one is an amendment. Judged: every non-stamp segment after the stamp is.
    """
    start = row.stamp.segment_index + 1 if isinstance(row.stamp, Judged) else 1
    later = tuple(
        segment
        for index, segment in enumerate(row.segments)
        if index >= start and not segment.startswith(STAMP_PREFIX)
    )
    return [SelfAmended(later)] if later else []


def _context(snapshot: StateSnapshot, row: ActiveRow, window: Window) -> RowContext:
    paths = [ref.path for ref in row.locations if isinstance(ref, PathRef)]
    related = [
        _related(facts, paths)
        for facts in snapshot.decisions.values()
        if any(paths_match(path, entry) for path in paths for entry in facts.affected_files)
    ]
    related.sort(key=lambda decision: (decision.date, decision.dec_id), reverse=True)
    start = window.start if isinstance(window, FirstSeenWindow) else None
    churn = [
        commit.date
        for commit in (snapshot.git.commits if snapshot.git else ())
        if (start is None or commit.date > start)
        and any(paths_match(path, touched) for path in paths for touched in commit.paths)
    ]
    quiet = (snapshot.today - row.last_seen).days if row.last_seen else None
    return RowContext(tuple(related), len(churn), max(churn, default=None), quiet)


def _related(facts: DecisionFacts, paths: list[str]) -> RelatedDecision:
    edges = tuple(f"{field}:{dec}" for field, ids in facts.edges.items() for dec in ids)
    matched = tuple(
        path for path in paths if any(paths_match(path, entry) for entry in facts.affected_files)
    )
    changes_prior = any(facts.edges[field] for field in _CHANGING_EDGES)
    return RelatedDecision(
        facts.dec_id,
        facts.status,
        facts.date,
        facts.title,
        facts.summary,
        edges,
        matched,
        changes_prior,
    )
