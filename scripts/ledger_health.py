#!/usr/bin/env python3
"""Tech-debt ledger probe: which active rows has the project state moved past?

`ledger_snapshot.py` computes each active row's delta against the current state;
this probe applies policy to those deltas. A row is a **candidate** for triage
iff its delta carries at least one signal, and each signal class has a fixed
tier in `CLASS_POLICY` -- *strong* when the state itself contradicts the row
(a path gone, a cited decision superseded, a commit that touched the row
without closing it), *medium* when the row only records that its own premise
was revisited in place. Context -- ADRs overlapping the row's location, churn on
its files, days since it was last seen -- rides along for the judge and never
makes a row a candidate: overlap links half the live ledger, live rows included,
and age says nothing about whether a premise still holds.

The golden bad case: a row whose cited decision has been superseded must come
out as a strong-tier candidate whose evidence names the decision and its
successor.

Output modes:

    (default)  a short text summary of candidates by class
    --digest   one `ledger-triage-digest/1` JSON envelope for a judge: every
               selected row with the row verbatim, its key facts, its evidence
               and context kept apart, and what was withheld and why
    --index    the same envelope with the selected ids in rank order instead of
               the row bodies: what a run fans out to judges, each of which then
               asks for its own batch with `--digest --ids`

Selection: candidates only, unless `--all` (every active row, candidates
first) or `--ids td-NNN[,td-NNN]`; `--class <name>` keeps rows carrying that
evidence class. The envelope's `anchor` is the sha a judge stamps with -- HEAD,
which is the merge-base when the probe runs on the default branch.

Advisory by construction: reads the ledger pair, the ADR corpus and git history,
writes nothing, and exits 0 whatever it finds. Exit 2 only on a script error --
an unreadable ledger or ADR file, or a plugin-cache repo root -- with the cause on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, assert_never

from _git_runner import GitUnavailableError, run_git
from _repo_root import is_plugin_cache_path, resolve_repo_root
from ledger_delta import (
    ActiveRow,
    AdrGoal,
    AnchorWindow,
    CitationDecay,
    CitedByCommit,
    CitedDecisionChanged,
    DraftGoal,
    DuplicatePeer,
    EvidenceMoved,
    FirstSeenWindow,
    GitFacts,
    GoalLinkUnresolved,
    GoalRef,
    Judged,
    JudgmentUnusable,
    LocationDecay,
    MalformedGoal,
    NoGoal,
    NoWindow,
    OtherGoal,
    PathCause,
    RelatedDecision,
    RowDelta,
    SelfAmended,
    Signal,
    StampMalformed,
    SupersedingDecisionOnLocation,
    TriageStamp,
    Unjudged,
    Withheld,
)
from ledger_snapshot import (
    StateSnapshot,
    discard_recurrences,
    gather,
    parse_stamp,
    row_delta,
    signal_class_name,
    split_segments,
    stamp_anchors,
    stamp_state,
    with_stamp,
)

SCRIPT_DIR = Path(__file__).resolve().parent

Tier = Literal["strong", "medium"]

# Evidence class -> tier. Only classes the reader emits appear here; a signal
# the table does not name is a programming error, not a silent medium.
CLASS_POLICY: Mapping[str, Tier] = {
    "location-decay": "strong",
    "citation-decay": "strong",
    "decision-drift": "strong",
    "goal-link-unresolved": "strong",
    "cited-by-commit": "strong",
    "possible-duplicate": "strong",
    "self-amended": "medium",
    "evidence-moved": "medium",
    "judgment-unusable": "strong",
}
_TIER_ORDER: Mapping[Tier, int] = {"strong": 0, "medium": 1}

CHECK_ID = "TD07"
_TD07_BOUND = (
    "TD07 clean means no active tech-debt row carries evidence that the project state "
    "moved past its premise since it was filed or last triaged; WARN per strong-tier "
    "candidate, INFO per medium-tier one. Advisory: it recommends /triage-debt and "
    "never writes a ledger row."
)
_TD07_SEVERITY: Mapping[Tier, str] = {"strong": "warn", "medium": "info"}

DIGEST_SCHEMA = "ledger-triage-digest/1"
INDEX_SCHEMA = "ledger-triage-index/1"
RELATED_DECISIONS_CAP = 5
DETAIL_LIMIT = 280  # characters of a quoted notes segment in one evidence detail
SHORT_SHA_LENGTH = 12


@dataclass(frozen=True)
class Assessment:
    """One active row with its delta and the policy's verdict on it."""

    row: ActiveRow
    delta: RowDelta
    classes: tuple[str, ...]  # distinct evidence classes, in signal order
    tier: Tier | None  # None == not a candidate

    @property
    def is_candidate(self) -> bool:
        return self.tier is not None


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        print(f"error: refusing a plugin-cache repo root: {repo_root}", file=sys.stderr)
        return 2
    try:
        snapshot = gather(repo_root)
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"error: could not read the ledger pair or an ADR under {repo_root}: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.check_stamp is not None:
        return _report_stamp_check(snapshot, args.row, args.check_stamp, args.notes)

    assessments = assess(snapshot)
    ids = tuple(part.strip() for part in (args.ids or "").split(",") if part.strip())
    unknown = sorted(set(ids) - {item.row.id for item in assessments})
    if unknown:
        print(f"note: not an active row: {', '.join(unknown)}", file=sys.stderr)
    selected = select(assessments, ids=ids, every_row=args.all, only_class=args.only)

    if args.json:
        print(json.dumps(render_td07(snapshot, assessments), indent=2))
    elif args.digest:
        print(json.dumps(render_digest(snapshot, assessments, selected, _utc_now()), indent=2))
    elif args.index:
        print(json.dumps(render_index(snapshot, assessments, selected, _utc_now()), indent=2))
    else:
        print(render_summary(snapshot, assessments, selected))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tech-debt ledger triage probe (advisory).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--digest", action="store_true", help="emit the judge digest as JSON")
    mode.add_argument(
        "--index", action="store_true", help="emit the digest envelope with ids, not row bodies"
    )
    mode.add_argument("--json", action="store_true", help="emit the sentinel TD07 family envelope")
    parser.add_argument("--all", action="store_true", help="every active row, candidates first")
    parser.add_argument("--ids", help="comma-separated td-NNN ids to report")
    parser.add_argument(
        "--class", dest="only", choices=sorted(CLASS_POLICY), help="keep rows with this class"
    )
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    parser.add_argument(
        "--check-stamp",
        metavar="STAMP",
        help="validate one stamp for --row before it is written: grammar, then every anchor",
    )
    parser.add_argument("--row", help="the td-NNN id the --check-stamp stamp is for")
    parser.add_argument(
        "--notes",
        help="the notes the stamp is appended to, when the apply step rewrites them (a realign); "
        "defaults to the row's current notes",
    )
    args = parser.parse_args(argv)
    if (args.check_stamp is None) != (args.row is None):
        parser.error("--check-stamp and --row go together")
    if args.notes is not None and args.check_stamp is None:
        parser.error("--notes goes with --check-stamp")
    return args


def _report_stamp_check(snapshot: StateSnapshot, row_id: str, stamp: str, notes: str | None) -> int:
    reasons = stamp_refusals(snapshot, row_id, stamp, notes)
    for reason in reasons:
        print(f"refused: {reason}")
    if not reasons:
        print("ok")
    return 1 if reasons else 0


def stamp_refusals(
    snapshot: StateSnapshot, row_id: str, stamp: str, notes: str | None = None
) -> list[str]:
    """Why `stamp` must not be written onto `row_id`; empty when it may.

    The grammar proves an anchor is shaped right; this proves the write is sound:
    the stamp reads back as the row's latest judgment once appended to `notes` (the
    row's current notes unless the apply step rewrites them), and every anchor it
    cites is real at HEAD. The row itself must be active.
    """
    rows: dict[str, ActiveRow] = {row.id: row for row in snapshot.active_rows}
    if row_id not in rows:
        return [f"{row_id} is not an active row"]
    parsed = parse_stamp(stamp)
    if isinstance(parsed, StampMalformed):
        return ["malformed stamp (see tech-debt-ledger.md § Triage for the grammar)"]
    if snapshot.git is None:
        return ["no git history here, so no anchor can be checked at HEAD"]
    base_notes = rows[row_id].notes if notes is None else notes
    return _cell_refusals(base_notes, stamp, parsed) + _anchor_refusals(
        snapshot, snapshot.git, row_id, parsed
    )


def _cell_refusals(notes: str, stamp: str, parsed: TriageStamp) -> list[str]:
    """A stamp that splits on its own ` // `, or that an unbalanced backtick folds into
    a code span, is written but never read back: the row would carry a judgment the
    probe cannot see, or amend itself the moment it is judged."""
    segments = split_segments(with_stamp(notes, stamp))
    state = stamp_state(segments)
    if (
        isinstance(state, Judged)
        and state.segment_index == len(segments) - 1
        and state.stamp == parsed
    ):
        return []
    return [
        "appended to the row's notes, the stamp does not read back as its latest judgment "
        "(a ` // ` inside it, or an unbalanced backtick, splits or hides it)"
    ]


def _anchor_refusals(
    snapshot: StateSnapshot, git: GitFacts, row_id: str, stamp: TriageStamp
) -> list[str]:
    """Every anchor resolved against HEAD: a path tracked in its tree (a file merely on
    disk may be gitignored scratch), a commit HEAD reaches (an object on an unmerged
    branch is not history), a finalized decision, a ledger row other than this one."""
    active = {row.id for row in snapshot.active_rows}
    known_rows = active | {peer.id for peer in snapshot.terminal_peers}
    anchors = stamp_anchors(stamp.text)
    paths = set(anchors["path"]) | ({stamp.evidence_path} if stamp.evidence_path else set())
    reasons = []
    if not _reaches_head(snapshot.repo_root, stamp.anchor):
        reasons.append(f"the stamp's anchor {stamp.anchor} is not a commit HEAD reaches")
    reasons += [
        f"{path} is not tracked at HEAD" for path in sorted(paths) if path not in git.head_tree
    ]
    reasons += [
        f"{dec} is not a finalized decision"
        for dec in anchors["dec"]
        if dec not in snapshot.decisions
    ]
    reasons += [f"{td} is not a ledger row" for td in anchors["td"] if td not in known_rows]
    reasons += [f"{row_id} cannot anchor its own stamp" for td in anchors["td"] if td == row_id]
    reasons += [
        f"{sha} is not a commit HEAD reaches"
        for sha in anchors["sha"]
        if not _reaches_head(snapshot.repo_root, sha)
    ]
    if stamp.outcome == "merged" and not set(anchors["td"]) & (active - {row_id}):
        reasons.append("a merge must name another active row as its survivor")
    return reasons


def _reaches_head(repo_root: Path, sha: str) -> bool:
    """Is `sha` an ancestor of HEAD? Existence alone is not enough."""
    try:
        return run_git(repo_root, "merge-base", "--is-ancestor", sha, "HEAD").returncode == 0
    except GitUnavailableError:
        return False


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# -- Policy --------------------------------------------------------------------------


def assess(snapshot: StateSnapshot) -> list[Assessment]:
    """Every active row with its verdict, candidates first, strongest first."""
    assessments = []
    for row in snapshot.active_rows:
        delta = row_delta(snapshot, row)
        classes = tuple(dict.fromkeys(signal_class_name(signal) for signal in delta.signals))
        tiers: list[Tier] = [_signal_tier(signal) for signal in delta.signals]
        tier = min(tiers, key=_TIER_ORDER.__getitem__) if tiers else None
        assessments.append(Assessment(row, delta, classes, tier))
    return sorted(assessments, key=_rank_key)


def _signal_tier(signal: Signal) -> Tier:
    """A superseding decision that merely overlaps a judged row's files is a reason to
    re-judge, not a contradiction, so it ranks below the class's other basis."""
    if isinstance(signal, SupersedingDecisionOnLocation):
        return "medium"
    return CLASS_POLICY[signal_class_name(signal)]


def _rank_key(item: Assessment) -> tuple[int, int, str]:
    tier_rank = _TIER_ORDER[item.tier] if item.tier else len(_TIER_ORDER)
    return (tier_rank, -len(item.delta.signals), item.row.id)


def select(
    assessments: list[Assessment], *, ids: tuple[str, ...], every_row: bool, only_class: str | None
) -> list[Assessment]:
    """Named rows, or every row, or the candidates -- then keep one class if asked."""
    if ids:
        chosen = [item for item in assessments if item.row.id in ids]
    elif every_row:
        chosen = list(assessments)
    else:
        chosen = [item for item in assessments if item.is_candidate]
    if only_class:
        chosen = [item for item in chosen if only_class in item.classes]
    return chosen


# -- TD07: the sentinel family envelope ------------------------------------------------


def render_td07(snapshot: StateSnapshot, assessments: list[Assessment]) -> dict:
    """One finding per candidate row; a withheld oracle is a finding, never silence."""
    candidates = [item for item in assessments if item.tier is not None]
    findings = [_td07_finding(item) for item in candidates]
    findings += [
        {
            "check": CHECK_ID,
            "severity": "warn",
            "entity": entry.class_name,
            "kind": "triage-withheld",
            "message": entry.reason,
        }
        for entry in snapshot.withheld
    ]
    findings += [
        {
            "check": CHECK_ID,
            "severity": "warn",
            "entity": recurred["id"],
            "kind": "discard-recurred",
            "message": f"discarded on {recurred['discarded_on']}, re-detected by {recurred['last_seen']}",
        }
        for recurred in _discard_recurred(snapshot)
    ]
    return {
        "check": CHECK_ID,
        "skipped": None,
        "examined": {
            "active": len(assessments),
            "candidates": len(candidates),
            "judged": sum(isinstance(item.row.stamp, Judged) for item in assessments),
            "by_class": dict(Counter(name for item in candidates for name in item.classes)),
            "unparseable": len(snapshot.unparseable),
        },
        "findings": findings,
        "info": {"anchor": snapshot.anchor, "recommend": "/triage-debt"},
        "bound": _TD07_BOUND,
    }


def _td07_finding(item: Assessment) -> dict:
    first = _evidence(item.delta.signals[0])
    return {
        "check": CHECK_ID,
        "severity": _TD07_SEVERITY[item.tier or "medium"],
        "entity": item.row.id,
        "kind": item.classes[0],
        "message": first["detail"],
    }


# -- Digest ----------------------------------------------------------------------------


def render_digest(
    snapshot: StateSnapshot,
    assessments: list[Assessment],
    selected: list[Assessment],
    generated_at: str,
) -> dict:
    """The `ledger-triage-digest/1` envelope: additive-only within the version."""
    envelope = _envelope(snapshot, assessments, generated_at)
    return {"schema": DIGEST_SCHEMA, **envelope, "rows": [_row_digest(item) for item in selected]}


def render_index(
    snapshot: StateSnapshot,
    assessments: list[Assessment],
    selected: list[Assessment],
    generated_at: str,
) -> dict:
    """The digest's envelope with the selected ids in rank order: a few hundred bytes where
    the digest of a whole ledger runs to hundreds of kilobytes."""
    envelope = _envelope(snapshot, assessments, generated_at)
    return {"schema": INDEX_SCHEMA, **envelope, "ids": [item.row.id for item in selected]}


def _envelope(snapshot: StateSnapshot, assessments: list[Assessment], generated_at: str) -> dict:
    return {
        "head": snapshot.head,
        "anchor": snapshot.anchor,
        "generated_at": generated_at,
        "oracles": {
            name: {"state": "available"}
            if reason is None
            else {"state": "withheld", "reason": reason}
            for name, reason in snapshot.oracles.items()
        },
        "withheld": [_withheld(entry) for entry in snapshot.withheld],
        "examined": {
            "active": len(assessments),
            "candidates": sum(item.is_candidate for item in assessments),
            "unparseable": len(snapshot.unparseable),
        },
        "discard_recurred": _discard_recurred(snapshot),
    }


def _discard_recurred(snapshot: StateSnapshot) -> list[dict]:
    return [
        {
            "id": peer.id,
            "discarded_on": found.stamp_date.isoformat(),
            "last_seen": found.last_seen.isoformat(),
        }
        for peer, found in discard_recurrences(snapshot)
    ]


def _row_digest(item: Assessment) -> dict:
    row, delta = item.row, item.delta
    goal_type, goal_value = _goal_cells(row.goal)
    return {
        "id": row.id,
        "row": {
            "status": row.status,
            "severity": row.severity,
            "class": row.klass,
            "direction": row.direction,
            "location": [ref.raw for ref in row.locations],
            "goal_ref": {"type": goal_type, "value": goal_value},
            "source": row.source,
            "first_seen": _iso(row.first_seen),
            "last_seen": _iso(row.last_seen),
            "owner_role": row.owner_role,
            "notes": row.notes,
        },
        "key": {
            "status": row.key.status,
            "dedup_key": row.key.written,
            "base_key": row.key.base,
            "resolved_key": row.key.resolved,
            "rekeys_on_notes_edit": row.key.status == "discriminated",
        },
        "judgment": _judgment(item),
        "candidate_classes": list(item.classes),
        "evidence": [_evidence(signal) for signal in delta.signals],
        "context": _context(delta),
        "withheld": [_withheld(entry) for entry in delta.row_withheld],
        "rank": {"tier": item.tier, "evidence_count": len(delta.signals)},
    }


def _goal_cells(goal: GoalRef) -> tuple[str, str]:
    match goal:
        case NoGoal():
            return ("code-quality", "")
        case AdrGoal(dec_id=dec_id):
            return ("adr", dec_id)
        case DraftGoal(draft_id=draft_id):
            return ("adr", draft_id)
        case OtherGoal(kind=kind, value=value):
            return (kind, value)
        case MalformedGoal(kind_raw=kind, value=value):
            return (kind, value)
        case _:
            assert_never(goal)


def _judgment(item: Assessment) -> dict:
    stamp, window = item.row.stamp, item.delta.window
    match window:
        case FirstSeenWindow(start=start):
            window_cell = {"kind": "first-seen", "start": start.isoformat()}
        case AnchorWindow(anchor=anchor):
            window_cell = {"kind": "anchor", "start": anchor.date.isoformat(), "sha": anchor.sha}
        case NoWindow(reason=reason):
            window_cell = {"kind": "none", "reason": reason}
        case _:
            assert_never(window)
    match stamp:
        case Unjudged():
            return {"state": "unjudged", "last": None, "window": window_cell}
        case Judged(stamp=last):
            judged = {"date": last.date.isoformat(), "anchor": last.anchor, "outcome": last.outcome}
            return {"state": "judged", "last": {**judged, "text": last.text}, "window": window_cell}
        case StampMalformed(raw=raw):
            return {"state": "unusable", "last": {"raw": raw}, "window": window_cell}
        case _:
            assert_never(stamp)


def _evidence(signal: Signal) -> dict:
    basis, detail, event_at = _basis_detail_event(signal)
    return {
        "class": signal_class_name(signal),
        "basis": basis,
        "detail": detail,
        "event_at": _iso(event_at),
    }


def _basis_detail_event(signal: Signal) -> tuple[str, str, date | None]:
    match signal:
        case LocationDecay(path=path, cause=cause, target=target, event_at=event_at):
            return (cause, f"location {path} {_fate(cause, target, event_at)}", event_at)
        case CitationDecay(cite=cite, path=path, cause=cause, target=target, event_at=event_at):
            return (
                cause,
                f"notes cite `{cite}`: {path} {_fate(cause, target, event_at)}",
                event_at,
            )
        case CitedDecisionChanged(dec_id=dec_id, via=via, change=change, by=by, event_at=event_at):
            successor = f" by {', '.join(by)}" if by else ""
            detail = f"{dec_id} (cited in {via}) is {change}{successor}"
            return ("cited-decision-changed", detail, event_at)
        case GoalLinkUnresolved(dec_id=dec_id, reason=reason):
            gap = "is a draft id" if reason == "draft-id" else "resolves to no finalized ADR"
            return (reason, f"adr goal-ref {dec_id} {gap}", None)
        case CitedByCommit(sha=sha, event_at=event_at, subject=subject):
            return ("commit", f"{sha[:SHORT_SHA_LENGTH]} {subject}", event_at)
        case DuplicatePeer(peer_id=peer_id, peer_status=status, basis=basis):
            shared = (
                "the same base dedup key"
                if basis == "same-base-key"
                else "the base key this row was realigned from"
            )
            return (basis, f"{peer_id} ({status}) has {shared}", None)
        case SelfAmended(segments=segments):
            return ("notes-segment", _clip(" // ".join(segments)), None)
        case EvidenceMoved(path=path, commits=commits, latest_sha=latest):
            detail = f"kept evidence {path} changed in {commits} commit(s) since the stamp"
            return ("evidence-moved", f"{detail}, latest {latest[:SHORT_SHA_LENGTH]}", None)
        case SupersedingDecisionOnLocation(
            dec_id=dec_id, edges=edges, matched_paths=paths, event_at=event_at
        ):
            detail = f"{dec_id} ({', '.join(edges)}) is new since the stamp and touches "
            return ("superseding-decision-on-location", detail + ", ".join(paths), event_at)
        case JudgmentUnusable(reason=reason, detail=detail):
            return (reason, f"the last triage stamp is unusable ({reason}): {detail}", None)
        case _:
            assert_never(signal)


def _fate(cause: PathCause, target: str | None, event_at: date | None) -> str:
    match cause:
        case "renamed":
            return f"was renamed to {target}"
        case "deleted":
            return f"was deleted on {_iso(event_at)}"
        case "vanished":
            return "is absent at HEAD with no rename or deletion recorded"
        case "unclassified":
            return "is absent at HEAD; its cause is withheld"
        case _:
            assert_never(cause)


def _context(delta: RowDelta) -> dict:
    related = delta.context.related_decisions
    return {
        "related_decisions": [_related(decision) for decision in related[:RELATED_DECISIONS_CAP]],
        "related_decisions_total": len(related),
        "location_churn": {
            "commits": delta.context.churn_commits,
            "latest": _iso(delta.context.churn_latest),
        },
        "quiet_days": delta.context.quiet_days,
        "same_base_peers": [
            {"id": peer.peer_id, "status": peer.peer_status}
            for peer in delta.context.same_base_peers
        ],
    }


def _related(decision: RelatedDecision) -> dict:
    return {
        "id": decision.dec_id,
        "status": decision.status,
        "date": decision.date,
        "title": decision.title,
        "summary": decision.summary,
        "edges": list(decision.edges),
        "matched_paths": list(decision.matched_paths),
        "changes_prior": decision.changes_prior,
    }


def _withheld(entry: Withheld) -> dict:
    return {"class": entry.class_name, "reason": entry.reason, "scope": entry.scope}


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _clip(text: str) -> str:
    return text if len(text) <= DETAIL_LIMIT else text[: DETAIL_LIMIT - 1] + "…"


# -- Summary -------------------------------------------------------------------------------


def render_summary(
    snapshot: StateSnapshot, assessments: list[Assessment], selected: list[Assessment]
) -> str:
    candidates = [item for item in assessments if item.is_candidate]
    by_class = Counter(name for item in candidates for name in item.classes)
    lines = [f"{len(assessments)} active rows, {len(candidates)} triage candidates"]
    lines += [f"  {name:22} {by_class[name]:4}" for name in CLASS_POLICY if by_class[name]]
    lines += [f"  WITHHELD {entry.class_name} -- {entry.reason}" for entry in snapshot.withheld]
    if snapshot.unparseable:
        lines.append(f"  UNPARSEABLE {len(snapshot.unparseable)} row(s) skipped")
    for item in selected:
        tier = item.tier or "-"
        lines.append(f"  {item.row.id} [{tier}] {', '.join(item.classes) or 'no evidence'}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
