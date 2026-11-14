"""Rendering for the tech-debt ledger triage probe: what `ledger_health.py` prints.

The probe decides which rows are candidates; this module only shapes an assessed
snapshot for its readers -- the text summary, the `ledger-triage-digest/1` and
`ledger-triage-index/1` envelopes for a judge, and the sentinel TD07 family
envelope. It holds no policy: the order the summary lists evidence classes in is
passed in, and `Assessment` is the one shape the two modules share.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, assert_never

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
    Unjudged,
    Withheld,
)
from ledger_snapshot import StateSnapshot, discard_recurrences, signal_class_name

Tier = Literal["strong", "medium"]


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
    snapshot: StateSnapshot,
    assessments: list[Assessment],
    selected: list[Assessment],
    class_order: Sequence[str],
) -> str:
    candidates = [item for item in assessments if item.is_candidate]
    by_class = Counter(name for item in candidates for name in item.classes)
    lines = [f"{len(assessments)} active rows, {len(candidates)} triage candidates"]
    lines += [f"  {name:22} {by_class[name]:4}" for name in class_order if by_class[name]]
    lines += [f"  WITHHELD {entry.class_name} -- {entry.reason}" for entry in snapshot.withheld]
    if snapshot.unparseable:
        lines.append(f"  UNPARSEABLE {len(snapshot.unparseable)} row(s) skipped")
    for item in selected:
        tier = item.tier or "-"
        lines.append(f"  {item.row.id} [{tier}] {', '.join(item.classes) or 'no evidence'}")
    return "\n".join(lines)
