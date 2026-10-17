"""The adherence eval's results file: one versioned JSON document per run.

``RunResults`` is built once and rewritten whole, atomically, after the
provisional write and after every session, so a crash keeps every paid session
(a temporary file in the same directory, then a rename). The declared settings
sit in it from the first write and cannot change afterwards: the type is frozen,
``declared_at`` must precede every session's start, and a rewrite of the same
run with other settings is refused.

Verdicts are never read back. The file carries them for its readers, but they are
recomputed from the stored sessions every time (:func:`role_verdicts`), so a
stored verdict cannot drift from the evidence beneath it.

Raw JSON becomes typed values once, in :func:`from_json`; everything after it
trusts its types. Reading and writing a file are the only effects here.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, assert_never

from praxion_evals.adherence import verdict
from praxion_evals.adherence.model import (
    ARMS,
    ROLES,
    Assessed,
    CheckDef,
    CheckKind,
    DeclaredSettings,
    Measured,
    Pair,
    RoleVerdict,
    RuleRef,
    SessionRecord,
    Underpowered,
    settings_from_json,
    settings_to_json,
    setup_from_json,
    setup_to_json,
    status_from_json,
    status_to_json,
    verdict_to_json,
)

SCHEMA_VERSION = "adherence/1"
RUN_ID_RANDOM_BYTES = 3
KERNEL_PREFIX_CHARS = 8  # the length of the kernel version a delivery marker carries
FlipLabel = Literal["clear", "not clear", "underpowered"]
FLIP_LABELS: tuple[str, ...] = ("clear", "not clear", "underpowered")
CHECK_KINDS: tuple[str, ...] = ("mechanical", "judged")
# The wire kind of a run's ending once closed on request; ``lineage`` writes it, and the listing
# (which cannot import ``lineage``) reads it.
CLOSED_ENDING_KIND = "closed"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _need(data: Mapping[str, Any], key: str, what: str) -> Any:
    if key not in data:
        raise ValueError(f"{what} lacks {key!r}")
    return data[key]


def instant(text: str, what: str) -> datetime:
    """An ISO-8601 timestamp that names its offset, so two of them always compare."""
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{what} is not an ISO-8601 timestamp: {text!r}") from error
    _require(moment.tzinfo is not None, f"{what} must carry a UTC offset: {text!r}")
    return moment


# ---------------------------------------------------------------------------
# The document's parts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EarlierRun:
    """A previous run of a role on the same checkout, and the flip verdict it reached."""

    run_id: str
    flip: FlipLabel

    def __post_init__(self) -> None:
        _require(bool(self.run_id.strip()), "an earlier run names its run identifier")
        _require(self.flip in FLIP_LABELS, f"an earlier run's flip is one of {FLIP_LABELS}")


@dataclass(frozen=True)
class Draw:
    """One draw of a role's flip verdict: the run or runs it took, in order, and what they reached."""

    run_ids: tuple[str, ...]
    flip: FlipLabel
    interim: bool = False

    def __post_init__(self) -> None:
        _require(bool(self.run_ids), "a draw names the run it took")
        _require(self.flip in FLIP_LABELS, f"a draw's flip is one of {FLIP_LABELS}")


@dataclass(frozen=True)
class EarlierRuns:
    """A role's earlier runs grouped by what they measured.

    ``draws`` measured the same role definition and kernel as the run that lists them, whatever
    their checkout commit; ``apart`` maps every other run to how its identity differs; a
    calibration run is never a draw and is listed in ``calibration``.
    """

    draws: tuple[Draw, ...]
    apart: Mapping[str, str]
    calibration: tuple[str, ...]


@dataclass(frozen=True)
class EarlierListing:
    """What the results directory held when a run began: every role's earlier runs, and the
    names of the JSON files in it that are not results files."""

    by_role: Mapping[str, EarlierRuns]
    skipped_files: tuple[str, ...]

    def for_older_readers(self) -> dict[str, tuple[EarlierRun, ...]]:
        """``run.earlier_runs`` as it was before runs were grouped: the draws' first ids."""
        return {
            role: tuple(EarlierRun(draw.run_ids[0], draw.flip) for draw in earlier.draws)
            for role, earlier in self.by_role.items()
        }


@dataclass(frozen=True)
class RunInfo:
    """Who ran: identifier, model, Claude Code version, how it ended.

    ``extra`` carries the run keys beyond these (times, effort, checkout, seed,
    spend) untouched, so the schema stays additive within ``adherence/1``.
    """

    id: str
    model: str
    claude_code_version: str
    complete: bool
    refused_launches: tuple[str, ...]
    earlier_runs: Mapping[str, tuple[EarlierRun, ...]]
    extra: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("id", "model", "claude_code_version"):
            _require(bool(getattr(self, name).strip()), f"a run's {name} is not empty")


@dataclass(frozen=True)
class CatalogEntry:
    """One check as the run scored it: the rule it enforces and, if judged, its golden bad case."""

    name: str
    kind: CheckKind
    rule: RuleRef
    common: bool
    golden_bad_case: str | None

    def __post_init__(self) -> None:
        _require(bool(self.name.strip()), "a catalog entry's name is not empty")
        _require(self.kind in CHECK_KINDS, f"a catalog entry's kind is one of {CHECK_KINDS}")
        _require(
            self.kind == "mechanical" or bool((self.golden_bad_case or "").strip()),
            f"the judged check {self.name} records its golden bad case",
        )


@dataclass(frozen=True)
class KernelDelivery:
    """One kernel delivery marker a lean session's role transcript showed, as a flip cites it."""

    task_id: str
    session_id: str | None
    kernel_version: str  # the first KERNEL_PREFIX_CHARS of the kernel's version
    slot: int | None


@dataclass(frozen=True)
class RunResults:
    run: RunInfo
    settings: DeclaredSettings
    declared_at: str
    catalog: Mapping[str, tuple[CatalogEntry, ...]]
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]]
    sessions: tuple[SessionRecord, ...]
    golden_bad_case_verdicts: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        declared = instant(self.declared_at, "the settings' declared_at")
        for record in self.sessions:
            _require(
                declared < instant(record.started_at, "a session's started_at"),
                f"the settings were declared at {self.declared_at}, not before the session"
                f" {record.setup.task_id} started at {record.started_at}",
            )
            _require(
                record.setup.role in self.catalog,
                f"the session {record.setup.task_id} ran {record.setup.role}, which has no catalog",
            )
        for role, per_arm in self.arms.items():
            _require(role in ROLES, f"arms name an unknown role {role!r}")
            for arm, record in per_arm.items():
                _require(arm in ARMS, f"{role}'s arms name an unknown arm {arm!r}")
                _require(isinstance(record.get("built"), bool), f"{role}/{arm} lacks 'built'")
        error = (self.golden_bad_case_verdicts or {}).get("observed_error")
        _require(
            error is None or 0 <= error <= 1,
            "the judge's observed golden-case error is a rate between 0 and 1",
        )


# ---------------------------------------------------------------------------
# Identity, the start-of-run refusal, the atomic write, the load
# ---------------------------------------------------------------------------


def new_run_id(now: datetime) -> str:
    """UTC timestamp plus a short random suffix: sortable by time, unique across a second."""
    return f"{now.astimezone(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(RUN_ID_RANDOM_BYTES)}"


def refuse_existing(path: Path, overwrite: bool) -> None:
    """The start-of-run check: an existing file is replaced only on request."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")


def write_atomic(path: Path, results: RunResults) -> None:
    """Replace ``path`` with ``results`` whole: a crash leaves the previous file or the new one."""
    _refuse_changed_settings(path, results)
    text = json.dumps(to_json(results), indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _refuse_changed_settings(path: Path, results: RunResults) -> None:
    if not path.exists():
        return
    try:
        previous = load(path)
    except ValueError:
        return  # not a results file: replacing it is the overwrite flag's decision, taken at start
    if previous.run.id == results.run.id and (previous.settings, previous.declared_at) != (
        results.settings,
        results.declared_at,
    ):
        raise ValueError(
            f"the declared settings of run {results.run.id} cannot change once written"
        )


def load(path: Path) -> RunResults:
    """Read a results file; rejects an unknown schema and settings declared after a session began."""
    return from_json(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Verdicts and earlier runs: derived from the sessions, never read back
# ---------------------------------------------------------------------------


def pairs_of(results: RunResults, role: str) -> list[Pair]:
    """The role's tasks that ran in both arms; a later record of a task and arm replaces an earlier."""
    latest: dict[tuple[str, str], dict[str, SessionRecord]] = {}
    for record in results.sessions:
        if record.setup.role == role:
            task = (record.setup.task_id, record.setup.template_id)
            latest.setdefault(task, {})[record.setup.arm] = record
    return [
        Pair(task_id, template_id, arms["full"].status, arms["lean"].status)
        for (task_id, template_id), arms in latest.items()
        if set(arms) == set(ARMS)
    ]


def role_verdicts(results: RunResults) -> dict[str, RoleVerdict]:
    return {
        role: verdict.role_verdict(
            checks_by_kind(entries),
            pairs_of(results, role),
            results.settings,
            role,
        )
        for role, entries in results.catalog.items()
    }


def kernel_deliveries(results: RunResults, role: str) -> tuple[KernelDelivery, ...]:
    """The marker records of the lean sessions ``role``'s verdict relies on: its complete pairs.

    An adherence sandbox writes no observation row, so the marker in the role's transcript
    is the only record a flip can cite that the lean arm received its kernel.
    """
    return tuple(
        KernelDelivery(
            task_id=pair.task_id,
            session_id=row.get("session_id"),
            kernel_version=row["kernel_version"][:KERNEL_PREFIX_CHARS],
            slot=row.get("slot"),
        )
        for pair in pairs_of(results, role)
        if pair.complete and isinstance(pair.lean, Measured)
        for row in pair.lean.kernel_rows
    )


def checks_by_kind(entries: Sequence[CatalogEntry]) -> dict[str, CheckKind]:
    return {entry.name: entry.kind for entry in entries}


def flip_label(role_verdict: RoleVerdict) -> FlipLabel:
    match role_verdict:
        case Assessed():
            return role_verdict.flip
        case Underpowered():
            return "underpowered"
        case _:
            assert_never(role_verdict)


# How an earlier run's identity for a role differs from the listing run's, one line each; empty
# when it measured the same definition and kernel. The caller supplies it because reading an
# identity needs the checkout, which this module does not know.
Differences = Callable[["RunResults", str], tuple[str, ...]]


def earlier_runs(
    directory: Path, roles: Sequence[str], differences: Differences, replaced: str | None = None
) -> EarlierListing:
    """Every results file in ``directory``, oldest first, listed by what it measured for each role.

    A ``.json`` file that is not an ``adherence/1`` results file is not a run: it is passed over
    and its name returned. ``replaced`` is the id of a run the listing run overwrites, which is
    no longer evidence.
    """
    runs, skipped = _read_directory(directory)
    runs = [earlier for earlier in runs if earlier.run.id != replaced]
    return EarlierListing(
        {role: _earlier_for(role, runs, differences) for role in roles}, tuple(skipped)
    )


def _read_directory(directory: Path) -> tuple[list[RunResults], list[str]]:
    runs: list[RunResults] = []
    skipped: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            runs.append(load(path))
        except (OSError, ValueError, KeyError, TypeError):  # whatever its shape, it is named
            skipped.append(path.name)
    return runs, skipped


def _earlier_for(role: str, runs: Sequence[RunResults], differences: Differences) -> EarlierRuns:
    draws: list[Draw] = []
    apart: dict[str, str] = {}
    calibration: list[str] = []
    for earlier in runs:
        if not any(record.setup.role == role for record in earlier.sessions):
            continue
        if earlier.run.extra.get("calibration"):
            calibration.append(earlier.run.id)
        elif differing := differences(earlier, role):
            apart[earlier.run.id] = "; ".join(differing)
        else:
            draws.append(_draw_of(earlier, role))
    return EarlierRuns(tuple(draws), apart, tuple(calibration))


def _draw_of(earlier: RunResults, role: str) -> Draw:
    """A run closed on request gave up before its plan ran out: it reached no flip verdict, so it
    is a not-clear draw however its sessions would read, and what it had reached is interim."""
    if (earlier.run.extra.get("ending") or {}).get("kind") == CLOSED_ENDING_KIND:
        return Draw((earlier.run.id,), "not clear", interim=True)
    return Draw((earlier.run.id,), flip_label(role_verdicts(earlier)[role]))


def earlier_to_json(listing: EarlierListing) -> dict[str, Any]:
    """The run keys a listing adds to ``run`` (pin ``earlier`` and ``skipped_files``)."""
    return {
        "earlier": {
            role: {
                "draws": [
                    {"run_ids": list(d.run_ids), "flip": d.flip, "interim": d.interim}
                    for d in earlier.draws
                ],
                "apart": dict(earlier.apart),
                "calibration": list(earlier.calibration),
            }
            for role, earlier in listing.by_role.items()
        },
        "skipped_files": list(listing.skipped_files),
    }


def earlier_listed(run: RunInfo, role: str) -> EarlierRuns | None:
    """The listing a run recorded for ``role``; ``None`` for a file written before listings."""
    recorded = run.extra.get("earlier")
    if recorded is None:
        return None
    entry = recorded.get(role, {})
    return EarlierRuns(
        draws=tuple(
            Draw(tuple(d["run_ids"]), d["flip"], bool(d.get("interim", False)))
            for d in entry.get("draws", ())
        ),
        apart=dict(entry.get("apart", {})),
        calibration=tuple(entry.get("calibration", ())),
    )


def skipped_files(run: RunInfo) -> tuple[str, ...]:
    """The JSON files beside this run's that were not results files, as the run named them."""
    return tuple(run.extra.get("skipped_files") or ())


def catalog_entry(check: CheckDef) -> CatalogEntry:
    return CatalogEntry(
        name=check.name,
        kind=check.kind,
        rule=check.rule,
        common=check.common,
        golden_bad_case=check.golden_bad_case if check.kind == "judged" else None,
    )


def measured_sessions(results: RunResults, role: str, arm: str) -> list[Measured]:
    return [
        record.status
        for record in results.sessions
        if record.setup.role == role
        and record.setup.arm == arm
        and isinstance(record.status, Measured)
    ]


# ---------------------------------------------------------------------------
# JSON: the one place raw values become typed ones
# ---------------------------------------------------------------------------


def to_json(results: RunResults) -> dict[str, Any]:
    run = results.run
    return {
        "schema_version": SCHEMA_VERSION,
        "run": {
            **run.extra,
            "id": run.id,
            "model": run.model,
            "claude_code_version": run.claude_code_version,
            "complete": run.complete,
            "refused_launches": list(run.refused_launches),
            "earlier_runs": {
                role: [{"run_id": e.run_id, "flip": e.flip} for e in earlier]
                for role, earlier in run.earlier_runs.items()
            },
        },
        "settings": {**settings_to_json(results.settings), "declared_at": results.declared_at},
        "arms": {
            role: {arm: dict(record) for arm, record in a.items()}
            for role, a in results.arms.items()
        },
        "catalog": {
            role: [_entry_to_json(entry) for entry in entries]
            for role, entries in results.catalog.items()
        },
        "sessions": [_session_to_json(record) for record in results.sessions],
        "verdicts": {role: verdict_to_json(v) for role, v in role_verdicts(results).items()},
        "kernel_delivery": _kernel_delivery_to_json(results),
        "golden_bad_case_verdicts": (
            None
            if results.golden_bad_case_verdicts is None
            else dict(results.golden_bad_case_verdicts)
        ),
    }


def _kernel_delivery_to_json(results: RunResults) -> dict[str, list[dict[str, Any]]]:
    """Derived like the verdicts, never read back; a role with no marker has no entry."""
    by_role = {role: kernel_deliveries(results, role) for role in results.catalog}
    return {
        role: [
            {
                "task_id": d.task_id,
                "session_id": d.session_id,
                "kernel_version": d.kernel_version,
                "slot": d.slot,
            }
            for d in deliveries
        ]
        for role, deliveries in by_role.items()
        if deliveries
    }


def _entry_to_json(entry: CatalogEntry) -> dict[str, Any]:
    return {
        "name": entry.name,
        "kind": entry.kind,
        "rule": {"file": entry.rule.file, "section": entry.rule.section},
        "common": entry.common,
        "golden_bad_case": entry.golden_bad_case,
    }


def _session_to_json(record: SessionRecord) -> dict[str, Any]:
    return {
        "setup": setup_to_json(record.setup),
        "status": status_to_json(record.status),
        "cost_usd": record.cost_usd,
        "duration_ms": record.duration_ms,
        "started_at": record.started_at,
    }


def from_json(data: Mapping[str, Any]) -> RunResults:
    _require(isinstance(data, Mapping), "a results file is a JSON object")
    version = data.get("schema_version")
    _require(
        version == SCHEMA_VERSION,
        f"unknown results schema {version!r}, expected {SCHEMA_VERSION!r}",
    )
    settings = _need(data, "settings", "a results file")
    return RunResults(
        run=_run_from_json(_need(data, "run", "a results file")),
        settings=settings_from_json(settings),
        declared_at=_need(settings, "declared_at", "the declared settings"),
        catalog={
            role: tuple(_entry_from_json(entry) for entry in entries)
            for role, entries in _need(data, "catalog", "a results file").items()
        },
        arms=_need(data, "arms", "a results file"),
        sessions=tuple(_session_from_json(r) for r in _need(data, "sessions", "a results file")),
        golden_bad_case_verdicts=data.get("golden_bad_case_verdicts"),
    )


def _run_from_json(run: Mapping[str, Any]) -> RunInfo:
    known = ("id", "model", "claude_code_version", "complete", "refused_launches", "earlier_runs")
    return RunInfo(
        id=_need(run, "id", "the run"),
        model=_need(run, "model", "the run"),
        claude_code_version=_need(run, "claude_code_version", "the run"),
        complete=bool(_need(run, "complete", "the run")),
        refused_launches=tuple(_need(run, "refused_launches", "the run")),
        earlier_runs={
            role: tuple(EarlierRun(e["run_id"], e["flip"]) for e in earlier)
            for role, earlier in (run.get("earlier_runs") or {}).items()
        },
        extra={key: value for key, value in run.items() if key not in known},
    )


def _entry_from_json(entry: Mapping[str, Any]) -> CatalogEntry:
    rule = _need(entry, "rule", "a catalog entry")
    return CatalogEntry(
        name=_need(entry, "name", "a catalog entry"),
        kind=_need(entry, "kind", "a catalog entry"),
        rule=RuleRef(
            _need(rule, "file", "a rule reference"), _need(rule, "section", "a rule reference")
        ),
        common=bool(_need(entry, "common", "a catalog entry")),
        golden_bad_case=entry.get("golden_bad_case"),
    )


def _session_from_json(record: Mapping[str, Any]) -> SessionRecord:
    return SessionRecord(
        setup=setup_from_json(_need(record, "setup", "a session")),
        status=status_from_json(_need(record, "status", "a session")),
        cost_usd=float(_need(record, "cost_usd", "a session")),
        duration_ms=int(_need(record, "duration_ms", "a session")),
        started_at=_need(record, "started_at", "a session"),
    )
