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

Selection: candidates only, unless `--all` (every active row, candidates
first) or `--ids td-NNN[,td-NNN]`; `--class <name>` keeps rows carrying that
evidence class. The envelope's `anchor` is the sha a judge stamps with -- HEAD,
which is the merge-base when the probe runs on the default branch.

Advisory by construction: reads the ledger pair, the ADR corpus and git history,
writes nothing, and exits 0 whatever it finds. Exit 2 only on a script error --
an unreadable ledger file or a plugin-cache repo root -- with the cause on stderr.
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

from _repo_root import is_plugin_cache_path, resolve_repo_root
from ledger_delta import (
    ActiveRow,
    AdrGoal,
    CitationDecay,
    CitedByCommit,
    CitedDecisionChanged,
    DraftGoal,
    DuplicatePeer,
    FirstSeenWindow,
    GoalLinkUnresolved,
    GoalRef,
    Judged,
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
    Unjudged,
    Withheld,
)
from ledger_snapshot import StateSnapshot, gather, row_delta, signal_class_name

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
}
_TIER_ORDER: Mapping[Tier, int] = {"strong": 0, "medium": 1}

DIGEST_SCHEMA = "ledger-triage-digest/1"
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
            f"error: could not read the tech-debt ledger under {repo_root}: {exc}", file=sys.stderr
        )
        return 2

    assessments = assess(snapshot)
    ids = tuple(part.strip() for part in (args.ids or "").split(",") if part.strip())
    unknown = sorted(set(ids) - {item.row.id for item in assessments})
    if unknown:
        print(f"note: not an active row: {', '.join(unknown)}", file=sys.stderr)
    selected = select(assessments, ids=ids, every_row=args.all, only_class=args.only)

    if args.digest:
        print(json.dumps(render_digest(snapshot, assessments, selected, _utc_now()), indent=2))
    else:
        print(render_summary(snapshot, assessments, selected))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tech-debt ledger triage probe (advisory).")
    parser.add_argument("--digest", action="store_true", help="emit the judge digest as JSON")
    parser.add_argument("--all", action="store_true", help="every active row, candidates first")
    parser.add_argument("--ids", help="comma-separated td-NNN ids to report")
    parser.add_argument(
        "--class", dest="only", choices=sorted(CLASS_POLICY), help="keep rows with this class"
    )
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    return parser.parse_args(argv)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# -- Policy --------------------------------------------------------------------------


def assess(snapshot: StateSnapshot) -> list[Assessment]:
    """Every active row with its verdict, candidates first, strongest first."""
    assessments = []
    for row in snapshot.active_rows:
        delta = row_delta(snapshot, row)
        classes = tuple(dict.fromkeys(signal_class_name(signal) for signal in delta.signals))
        tiers = [CLASS_POLICY[name] for name in classes]
        tier = min(tiers, key=_TIER_ORDER.__getitem__) if tiers else None
        assessments.append(Assessment(row, delta, classes, tier))
    return sorted(assessments, key=_rank_key)


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


# -- Digest ----------------------------------------------------------------------------


def render_digest(
    snapshot: StateSnapshot,
    assessments: list[Assessment],
    selected: list[Assessment],
    generated_at: str,
) -> dict:
    """The `ledger-triage-digest/1` envelope: additive-only within the version."""
    return {
        "schema": DIGEST_SCHEMA,
        "head": snapshot.head,
        "anchor": snapshot.head,
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
        "rows": [_row_digest(item) for item in selected],
    }


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
            return (basis, f"{peer_id} ({status}) has the same base dedup key", None)
        case SelfAmended(segments=segments):
            return ("notes-segment", _clip(" // ".join(segments)), None)
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
