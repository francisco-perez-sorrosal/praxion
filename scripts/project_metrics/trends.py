"""Trend computation against the most-recent-prior report and schema-mismatch policy.

Discovers prior `METRICS_REPORT_*.json` artifacts in the caller-supplied
`.ai-state/` directory, selects the most-recent-strictly-prior by embedded
`aggregate.timestamp`, and returns a discriminated `TrendBlock` per the
storage-schema ADR's four-outcome contract:

* ``first_run`` — no usable prior on disk.
* ``schema_mismatch`` — prior's major/minor schema differs from current.
* ``computed`` — prior schema is compatible; per-aggregate-column deltas emitted.
* ``no_prior_readable`` — prior file present but unparseable or missing keys.

Patch-level schema differences (e.g. ``1.0.0`` vs ``1.0.1``) are **not** a
mismatch — they preserve the frozen aggregate-column contract and flow through
to the `computed` branch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.project_metrics.schema import AGGREGATE_COLUMNS, Report, TrendBlock

__all__ = ["compute_trends"]


_METRICS_REPORT_GLOB = "METRICS_REPORT_*.json"


def compute_trends(current: Report, ai_state_dir: Path) -> TrendBlock:
    """Return a `TrendBlock` describing the delta between `current` and the
    most-recent-strictly-prior report found under `ai_state_dir`.

    The selection predicate excludes any candidate whose embedded
    ``aggregate.timestamp`` is greater than or equal to
    ``current.aggregate.timestamp`` — this single rule covers both the
    current run's own already-on-disk file and clock-skew anomalies.
    """

    current_timestamp = current.aggregate.timestamp
    current_schema = current.aggregate.schema_version

    prior_path, prior_payload, load_error = _load_most_recent_prior(
        ai_state_dir, current_timestamp
    )

    if prior_path is None:
        return TrendBlock(status="first_run")

    if load_error is not None:
        return _unreadable(prior_path, load_error)

    # A parsed payload without the required structure is also unreadable —
    # surface it with the same discriminator rather than silently degrading
    # to `first_run`.
    assert prior_payload is not None  # narrowing for type checkers
    prior_aggregate = prior_payload.get("aggregate")
    if not isinstance(prior_aggregate, dict):
        return _unreadable(
            prior_path, "prior report is missing required 'aggregate' block"
        )

    prior_schema = prior_aggregate.get("schema_version")
    if not isinstance(prior_schema, str):
        return _unreadable(
            prior_path, "prior report is missing 'aggregate.schema_version'"
        )

    if _parse_major_minor(prior_schema) != _parse_major_minor(current_schema):
        return TrendBlock(
            status="schema_mismatch",
            prior_report=prior_path.name,
            prior_schema=prior_schema,
            current_schema=current_schema,
        )

    deltas = _compute_deltas(current.aggregate, prior_aggregate)
    return TrendBlock(
        status="computed",
        prior_report=prior_path.name,
        prior_schema=prior_schema,
        current_schema=current_schema,
        deltas=deltas,
    )


def _unreadable(prior_path: Path, error: str) -> TrendBlock:
    """Build a `no_prior_readable` TrendBlock for the given file + error."""

    return TrendBlock(
        status="no_prior_readable", prior_report=prior_path.name, error=error
    )


def _load_most_recent_prior(
    ai_state_dir: Path, current_timestamp: str
) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    """Return (path, payload, error) for the most-recent-strictly-prior file.

    * Returns ``(None, None, None)`` when no eligible file is found.
    * Returns ``(path, payload, None)`` when the prior parsed successfully.
    * Returns ``(path, None, error_str)`` when the prior exists but cannot
      be loaded (JSON parse failure, IO error).

    Candidate ordering: files whose embedded ``aggregate.timestamp`` is
    strictly less than ``current_timestamp``, sorted descending by that
    timestamp. Files whose timestamp cannot be extracted (IO or parse
    failures while gathering candidates) are set aside and consulted only
    if no timestamp-eligible candidate exists — so one corrupted stranger
    cannot mask a perfectly good prior.
    """

    if not ai_state_dir.is_dir():
        return (None, None, None)

    eligible: list[tuple[str, Path, dict[str, Any]]] = []
    unreadable: list[tuple[Path, str]] = []

    for candidate in ai_state_dir.glob(_METRICS_REPORT_GLOB):
        if candidate.suffix != ".json" or not candidate.is_file():
            # Glob is already `*.json`; the extra suffix check defends
            # against a directory ending in `.json` sneaking through.
            continue

        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            unreadable.append((candidate, _format_load_error(exc)))
            continue

        timestamp = _extract_timestamp(payload)
        if timestamp is None:
            unreadable.append(
                (candidate, "prior report is missing 'aggregate.timestamp'")
            )
            continue

        if timestamp >= current_timestamp:
            # The current run's own file (if already persisted) or a
            # future/skewed run — never a valid prior.
            continue

        eligible.append((timestamp, candidate, payload))

    if eligible:
        eligible.sort(key=lambda entry: entry[0], reverse=True)
        _, path, payload = eligible[0]
        return (path, payload, None)

    if unreadable:
        # Surface the most-recent-by-filename unreadable file so the UI
        # can point at something specific. Filename sort is deterministic
        # and has no dependency on the unparseable payload.
        unreadable.sort(key=lambda entry: entry[0].name, reverse=True)
        path, error = unreadable[0]
        return (path, None, error)

    return (None, None, None)


def _extract_timestamp(payload: Any) -> str | None:
    """Return ``aggregate.timestamp`` from a parsed payload when it exists
    as a string, else ``None``."""

    if not isinstance(payload, dict):
        return None
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        return None
    timestamp = aggregate.get("timestamp")
    if isinstance(timestamp, str):
        return timestamp
    return None


def _format_load_error(exc: BaseException) -> str:
    """Return a compact error string for UI surfacing."""

    return f"{type(exc).__name__}: {exc}"


def _parse_major_minor(version: str) -> tuple[int, int]:
    """Return the (major, minor) tuple for a SemVer-style version string.

    Patch-level and any further qualifiers are intentionally discarded:
    the frozen-aggregate-column contract is scoped to major/minor, and
    patch bumps are reserved for non-structural fixes that preserve the
    aggregate shape.
    """

    parts = version.split(".", 2)
    return (int(parts[0]), int(parts[1]))


def _compute_deltas(
    current_aggregate: Any, prior_aggregate: dict[str, Any]
) -> dict[str, Any]:
    """Return per-column deltas for every numeric aggregate column.

    Policy:

    * Both sides numeric → ``{"delta": current - prior, "delta_pct": pct}``
      where ``delta_pct`` is ``delta / prior`` when ``prior != 0``, else
      ``None``.
    * Either side ``None`` → ``{"delta": None, "reason": "null_input"}``.
    * Both sides non-numeric (e.g. the three string metadata columns
      ``schema_version`` / ``timestamp`` / ``commit_sha``) → omitted.
    """

    deltas: dict[str, Any] = {}
    for column in AGGREGATE_COLUMNS:
        current_value = getattr(current_aggregate, column)
        prior_value = prior_aggregate.get(column)

        if _is_numeric(current_value) and _is_numeric(prior_value):
            delta = current_value - prior_value
            delta_pct = (delta / prior_value) if prior_value != 0 else None
            deltas[column] = {"delta": delta, "delta_pct": delta_pct}
            continue

        # Nulls on either side of a numeric-typed column propagate as an
        # explicit sentinel — distinguishable from "0 delta" at the UI.
        if _is_nullable_numeric_slot(current_value, prior_value):
            deltas[column] = {"delta": None, "reason": "null_input"}

        # Otherwise (both non-numeric, non-null) the column is metadata
        # and is not a delta candidate — omit silently.

    return deltas


def _is_numeric(value: Any) -> bool:
    """Return True if `value` is an ``int`` or ``float`` (excluding bool).

    ``bool`` is an ``int`` subclass in Python; excluding it guards against
    a collector ever accidentally emitting booleans into a numeric column.
    """

    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_nullable_numeric_slot(current_value: Any, prior_value: Any) -> bool:
    """Return True if the column is a numeric slot with a null on at least
    one side. A column qualifies when each side is either numeric or
    ``None``, and at least one side is ``None``."""

    sides_are_numeric_or_null = all(
        value is None or _is_numeric(value) for value in (current_value, prior_value)
    )
    has_a_null = current_value is None or prior_value is None
    return sides_are_numeric_or_null and has_a_null
