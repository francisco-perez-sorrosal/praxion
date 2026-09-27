"""Pure computation core of the tech-debt ledger reader: the per-row delta.

Split out of `ledger_delta.py` (the types module
plus this one together exceeded the 800-line ceiling) along the seam that was
already there -- schema on one side, the functions that compute over it on
the other. `row_delta(snapshot, row)` and `discard_recurrences(snapshot)` are
the two pure entry points `ledger_snapshot.py` re-exports; every other name
here is a private helper. No I/O: every signal is testable against a
hand-built `StateSnapshot`, with no git and no filesystem in the call path.
"""

from __future__ import annotations

import re
from datetime import date
from typing import assert_never

from adr_health import _EPHEMERAL_ROOTS, _SHAPE, _deletion_date, _matches_shape, _rename_target
from ledger_delta import (
    STAMP_PREFIX,
    ActiveRow,
    AdrGoal,
    Anchor,
    Anchored,
    AnchorWindow,
    AnchorWithheld,
    CitationDecay,
    CitedByCommit,
    CitedDecisionChanged,
    DecisionChange,
    DecisionFacts,
    DiscardRecurred,
    DraftGoal,
    DuplicatePeer,
    EvidenceMoved,
    FirstSeenWindow,
    GitFacts,
    GoalLinkUnresolved,
    Judged,
    JudgmentUnusable,
    LocationDecay,
    NoWindow,
    PathCause,
    PathRef,
    RelatedDecision,
    RowContext,
    RowDelta,
    SelfAmended,
    Signal,
    StampMalformed,
    StateSnapshot,
    SupersedingDecisionOnLocation,
    TerminalPeer,
    TriageStamp,
    Unanchored,
    Unjudged,
    Window,
    cite_path,
    parse_iso_date,
)
from query_adrs import paths_match

_STATE_ROOT = ".ai-state/"
# Frontmatter edges by which a decision narrows or replaces an earlier one.
_CHANGING_EDGES = ("supersedes", "supersedes_in_part")

# -- `notes_path_citations`'s own patterns (its only reader) -----------------------------
_BACKTICK_SPAN = re.compile(r"`([^`\n]+)`")
_BARE_LINE_CITE = re.compile(r"(?<![\w/.`-])((?:[\w.-]+/)+[\w.-]+\.\w+):\d+(?:-\d+)?")
# At least two components: a lone `references/` is relative to some unnamed directory.
_PATH_SHAPE = re.compile(r"^[\w.@+-]+/(?:[\w.@+-]+/)*(?:[\w@+-][\w.@+-]*\.\w+|[\w.@+-]+/)$")

# -- The pure delta ------------------------------------------------------------------------


def row_delta(snapshot: StateSnapshot, row: ActiveRow) -> RowDelta:
    """Every signal and every piece of context for one row, over the row's window.

    The window is chosen first (`_window`) and handed to every windowed
    signal; no signal function reads the row's stamp to pick its own. A
    `Judged` + `Anchored` row's window is `anchor..HEAD`, so `location-decay`,
    `citation-decay` and `decision-drift` resurface it only when their event
    lies inside that range -- the windowing invariant this function is the one
    enforcement point for.
    """
    window = _window(row, snapshot.git)
    signals: tuple[Signal, ...] = (
        *_location_decay(snapshot, row, window),
        *_citation_decay(snapshot, row, window),
        *_decision_drift(snapshot, row, window),
        *_superseding_on_location(snapshot, row, window),
        *_goal_link(snapshot, row),
        *_cited_by_commit(snapshot, row, window),
        *_duplicates(snapshot, row),
        *_self_amended(row),
        *_evidence_moved(row, window),
        *_judgment_unusable(row, snapshot.git),
    )
    return RowDelta(
        row_id=row.id,
        window=window,
        signals=signals,
        context=_context(snapshot, row, window),
        row_withheld=row.row_withheld,
    )


def _row_anchor(stamp: TriageStamp, git: GitFacts | None) -> Anchor:
    """Resolve one stamp's `@<sha>` against the snapshot's precomputed anchors.

    `git.anchors` already holds one entry per distinct stamp anchor found
    among the snapshot's rows (built once, in `gather`) -- this never issues
    a git call of its own. `AnchorWithheld` covers "no git history"; a sha
    missing from the map (should not happen, since the map is built from the
    same row set) degrades to `Unanchored` rather than a `KeyError`.
    """
    if git is None:
        return AnchorWithheld("no git history, or a shallow clone")
    return git.anchors.get(stamp.anchor, Unanchored(stamp.anchor, "unknown-object"))


def _first_seen_or_none(row: ActiveRow) -> Window:
    return FirstSeenWindow(row.first_seen) if row.first_seen else NoWindow("first-seen-malformed")


def _window(row: ActiveRow, git: GitFacts | None) -> Window:
    """A `Judged` row whose stamp anchor is `Anchored` gets `anchor..HEAD`.

    Every other case -- unjudged, malformed, `Unanchored`, or `AnchorWithheld`
    -- falls back to `first-seen..HEAD` (or `NoWindow` with no first-seen):
    the row is evaluated as if it had never been usably judged.
    """
    match row.stamp:
        case Judged(stamp=stamp):
            anchor = _row_anchor(stamp, git)
            if isinstance(anchor, Anchored):
                return git.anchor_windows[stamp.anchor]  # type: ignore[union-attr]
            return _first_seen_or_none(row)
        case Unjudged() | StampMalformed():
            return _first_seen_or_none(row)
        case _:
            assert_never(row.stamp)


def _judgment_unusable(row: ActiveRow, git: GitFacts | None) -> list[JudgmentUnusable]:
    """A malformed stamp, an unresolved anchor, or a terminal outcome on a
    still-active row -- the row is unusably judged, not "kept" or "realigned".

    `AnchorWithheld` (no git) never produces this signal: the row-scope
    `judgment-unusable:unanchored` withheld class covers it instead, so a
    missing oracle does not flag every stamped row.
    """
    match row.stamp:
        case StampMalformed(raw=raw):
            return [JudgmentUnusable("malformed", raw)]
        case Judged(stamp=stamp):
            if stamp.outcome in ("discarded", "merged"):
                detail = f"{stamp.outcome} stamp on an active row"
                return [JudgmentUnusable("outcome-status-mismatch", detail)]
            match _row_anchor(stamp, git):
                case Unanchored(reason=reason):
                    return [JudgmentUnusable("unanchored", f"{stamp.anchor}: {reason}")]
                case Anchored() | AnchorWithheld():
                    return []
                case _:  # pragma: no cover -- exhaustiveness guard
                    assert_never(_row_anchor(stamp, git))
        case Unjudged():
            return []
        case _:
            assert_never(row.stamp)


def _path_fate(
    snapshot: StateSnapshot, path: str
) -> tuple[PathCause, str | None, date | None] | None:
    """None when `path` resolves (on disk or at HEAD); else why it does not.

    The exact-path rename and deletion indexes are recorded facts about this
    very path, so they are consulted before the shorthand heuristic: a
    same-suffix copy elsewhere (a fixture repo mirroring real paths) must not
    hide a real move or removal. The shorthand match only answers for a path
    history never tracked.
    """
    git = snapshot.git
    if path in snapshot.present_paths or (git and _in_tree(git.head_tree, path)):
        return None
    if git is None:
        return ("unclassified", None, None)
    target = _rename_target(path, git.renames)
    if target and _in_tree(git.head_tree, target):
        return ("renamed", target, None)
    deleted = _deletion_date(path, git.deletions)
    if deleted:
        return ("deleted", None, parse_iso_date(deleted))
    if _unique_suffix_match(git.head_tree, path):
        return None  # a shorthand for a file that exists, e.g. `cli.py` for `scripts/.../cli.py`
    return (
        ("vanished", None, None)
        if snapshot.lazy_shapes is not None
        else ("unclassified", None, None)
    )


def _unique_suffix_match(tree: frozenset[str], path: str) -> bool:
    suffix = "/" + path.rstrip("/")
    return sum(1 for entry in tree if entry.endswith(suffix)) == 1


def _in_tree(tree: frozenset[str], path: str) -> bool:
    if path in tree:
        return True
    prefix = path.rstrip("/") + "/"
    return any(entry.startswith(prefix) for entry in tree)


def _is_lazy(snapshot: StateSnapshot, path: str) -> bool:
    return any(_matches_shape(path, shape) for shape in snapshot.lazy_shapes or ())


def _already_gone_at_anchor(window: Window, path: str) -> bool:
    """True when `path` was already absent from the anchor's own tree.

    Only `AnchorWindow` can answer this (it carries the anchor's tree); a
    `FirstSeenWindow`/`NoWindow` row has no such tree and is always probed in
    full -- unjudged rows carry no "since when" to gate on. A judged row's
    location or citation decay only resurfaces when the path moved *since*
    the anchor, not for a decay that already held when it was judged. The
    check is prefix-aware, as at HEAD: the tree lists files, so a directory
    is present when anything beneath it is.
    """
    return isinstance(window, AnchorWindow) and not _in_tree(window.tree, path)


def _location_decay(snapshot: StateSnapshot, row: ActiveRow, window: Window) -> list[LocationDecay]:
    decays = []
    for ref in row.locations:
        if not isinstance(ref, PathRef) or _is_lazy(snapshot, ref.path):
            continue
        if _already_gone_at_anchor(window, ref.path):
            continue
        fate = _path_fate(snapshot, ref.path)
        if fate is not None:
            decays.append(LocationDecay(ref.path, *fate))
    return decays


def _citation_decay(snapshot: StateSnapshot, row: ActiveRow, window: Window) -> list[CitationDecay]:
    decays = []
    for cite, path in notes_path_citations(row.notes):
        if _is_lazy(snapshot, path) or _already_gone_at_anchor(window, path):
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
        if path.startswith(("~", "/", "..")) or "://" in cite or path.startswith(_EPHEMERAL_ROOTS):
            continue
        cites[cite] = path
    return tuple(cites.items())


def _decision_drift(
    snapshot: StateSnapshot, row: ActiveRow, window: Window
) -> list[CitedDecisionChanged]:
    """A cited decision that was superseded, retired, rejected or narrowed.

    A judged row's window drops the change only when the anchor provably saw
    it (`_change_seen_at_anchor`); a change that cannot be placed stays
    unwindowed, since "cannot place it in the window" is not "did not move".
    """
    drifts = []
    for citation in row.cited_decisions:
        facts = snapshot.decisions.get(citation.dec_id)
        change = _decision_change(facts) if facts else None
        if facts is None or change is None:
            continue
        kind, by = change
        successor = snapshot.decisions.get(by[0]) if by else None
        if _change_seen_at_anchor(snapshot, window, facts, successor):
            continue
        event_at = parse_iso_date(successor.date) if successor else None
        drifts.append(CitedDecisionChanged(citation.dec_id, citation.via, kind, by, event_at))
    return drifts


def _change_seen_at_anchor(
    snapshot: StateSnapshot,
    window: Window,
    cited: DecisionFacts,
    successor: DecisionFacts | None,
) -> bool:
    """True when a judged row's anchor already held this decision change.

    With a successor, the change is the successor's arrival
    (`_predates_anchor`). Without one -- a rejection, or a status set with no
    edge -- the change is an edit to the cited file itself, so it is in the
    window iff a commit in `anchor..HEAD` touched that file. A cited file the
    project does not track cannot be placed and stays unwindowed.
    """
    if not isinstance(window, AnchorWindow):
        return False
    if successor is not None:
        return _predates_anchor(snapshot, window, successor)
    if not _tracked(snapshot, cited.path):
        return False
    return not any(cited.path in commit.paths for commit in window.commits)


def _predates_anchor(snapshot: StateSnapshot, window: AnchorWindow, facts: DecisionFacts) -> bool:
    """True when this decision already existed at the anchor.

    Tree membership decides: an ADR drafted before a triage and merged after
    it carries a `date` on or before the anchor, yet its file is absent from
    the anchor's tree, so the judge never saw it. The `date` is only the
    fallback for a decision whose file the project does not track (an
    uncommitted draft, a state directory kept outside the repository).
    """
    if _tracked(snapshot, facts.path):
        return facts.path in window.tree
    event_at = parse_iso_date(facts.date)
    return event_at is not None and event_at <= window.anchor.date


def _tracked(snapshot: StateSnapshot, path: str | None) -> bool:
    return path is not None and snapshot.git is not None and path in snapshot.git.head_tree


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
    """Commits naming this row and touching a non-state path, in whichever window applies.

    `AnchorWindow.commits` is already `anchor..HEAD` (one read shared by every
    row anchored to that sha), so no further date filter is needed there; a
    `FirstSeenWindow` still filters `snapshot.git.commits` (the corpus-wide,
    `since`-bounded index) by `commit.date > window.start`. That author-date
    bound is also what excludes the filing commit, authored on `first-seen`:
    a later commit that amends the row while changing code is work on it,
    whatever else it touches.
    """
    if snapshot.git is None:
        return []
    match window:
        case FirstSeenWindow(start=start):
            pool = [commit for commit in snapshot.git.commits if commit.date > start]
        case AnchorWindow(commits=commits):
            pool = list(commits)
        case NoWindow():
            return []
        case _:
            assert_never(window)
    return [
        CitedByCommit(commit.sha, commit.date, commit.subject)
        for commit in pool
        if row.id in commit.td_ids
        and any(not path.startswith(_STATE_ROOT) for path in commit.paths)
    ]


def _duplicates(snapshot: StateSnapshot, row: ActiveRow) -> list[DuplicatePeer]:
    """Same-base-key peers (either file), plus -- for a `realigned` row whose
    stamp names a prior key -- any active peer filed at that prior key after
    the realign: a producer re-filing the shape this row moved away from.
    """
    peers = [(other.id, other.status, other.key.base) for other in snapshot.active_rows]
    peers += [(peer.id, peer.status, peer.base_key) for peer in snapshot.terminal_peers]
    same_base = [
        DuplicatePeer(peer_id, status, "same-base-key")
        for peer_id, status, base in peers
        if base == row.key.base and peer_id != row.id
    ]
    return same_base + _refiled_after_realign(snapshot, row)


def _refiled_after_realign(snapshot: StateSnapshot, row: ActiveRow) -> list[DuplicatePeer]:
    if not isinstance(row.stamp, Judged):
        return []
    stamp = row.stamp.stamp
    if stamp.outcome != "realigned" or not stamp.prior_key:
        return []
    return [
        DuplicatePeer(other.id, other.status, "refiled-after-realign")
        for other in snapshot.active_rows
        if other.id != row.id
        and other.key.base == stamp.prior_key
        and other.first_seen is not None
        and other.first_seen > stamp.date
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


def _evidence_moved(row: ActiveRow, window: Window) -> list[EvidenceMoved]:
    """`kept` only: commits touching the stamp's own evidence file, in the anchor window."""
    if not isinstance(window, AnchorWindow) or not isinstance(row.stamp, Judged):
        return []
    stamp = row.stamp.stamp
    if stamp.outcome != "kept" or not stamp.evidence_path:
        return []
    touching = [
        commit
        for commit in window.commits
        if any(paths_match(stamp.evidence_path, path) for path in commit.paths)
    ]
    if not touching:
        return []
    return [EvidenceMoved(stamp.evidence_path, len(touching), touching[0].sha)]


def _superseding_on_location(
    snapshot: StateSnapshot, row: ActiveRow, window: Window
) -> list[SupersedingDecisionOnLocation]:
    """Judged rows only: a decision new since the anchor that supersedes or
    narrows another decision and overlaps this row's location.

    "New since the anchor" is `_predates_anchor`'s tree-membership answer,
    not the decision's `date`. Retirement has no forward `retires` edge on
    the new decision's own frontmatter to read -- only `_CHANGING_EDGES`
    (`supersedes` / `supersedes_in_part`) are checkable from this side; a
    declared limit.
    """
    if not isinstance(window, AnchorWindow) or not snapshot.decisions:
        return []
    paths = [ref.path for ref in row.locations if isinstance(ref, PathRef)]
    if not paths:
        return []
    found = []
    for facts in snapshot.decisions.values():
        edges = tuple(f"{field}:{dec}" for field in _CHANGING_EDGES for dec in facts.edges[field])
        if not edges:
            continue
        if _predates_anchor(snapshot, window, facts):
            continue
        matched = tuple(
            path
            for path in paths
            if any(paths_match(path, entry) for entry in facts.affected_files)
        )
        if matched:
            event_at = parse_iso_date(facts.date)
            found.append(SupersedingDecisionOnLocation(facts.dec_id, edges, matched, event_at))
    return found


def discard_recurrences(
    snapshot: StateSnapshot,
) -> tuple[tuple[TerminalPeer, DiscardRecurred], ...]:
    """`wontfix` peers whose `discarded` stamp predates a later `last-seen` --
    a producer's re-detection was silently absorbed into the tombstone
    instead of reopening it. Terminal-peer scope, ledger-only;
    computed over the whole snapshot rather than per active row, since a
    RESOLVED-file peer never has an `ActiveRow`/`RowDelta` of its own.
    """
    found: list[tuple[TerminalPeer, DiscardRecurred]] = []
    for peer in snapshot.terminal_peers:
        if peer.status != "wontfix" or not isinstance(peer.stamp, Judged) or peer.last_seen is None:
            continue
        stamp = peer.stamp.stamp
        if stamp.outcome == "discarded" and peer.last_seen > stamp.date:
            found.append((peer, DiscardRecurred(stamp.date, peer.last_seen)))
    return tuple(found)


def _window_start(window: Window) -> date | None:
    """The date churn/related-decision context is bounded from, or None (unbounded).

    An `AnchorWindow` reuses the corpus-wide commit index (`start=` filter)
    rather than its own `commits` list -- context is not evidence, so the
    coarser, already-computed bound is enough here.
    """
    match window:
        case FirstSeenWindow(start=start):
            return start
        case AnchorWindow(anchor=anchor):
            return anchor.date
        case NoWindow():
            return None
        case _:
            assert_never(window)


def _context(snapshot: StateSnapshot, row: ActiveRow, window: Window) -> RowContext:
    paths = [ref.path for ref in row.locations if isinstance(ref, PathRef)]
    related = [
        _related(facts, paths)
        for facts in snapshot.decisions.values()
        if any(paths_match(path, entry) for path in paths for entry in facts.affected_files)
    ]
    related.sort(key=lambda decision: (decision.date, decision.dec_id), reverse=True)
    start = _window_start(window)
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
