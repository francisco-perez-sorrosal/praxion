#!/usr/bin/env python3
"""Retain-last-N pruning for timestamped report families in ``.ai-state/``.

Bounds the unbounded growth of per-run report directories (``metrics_reports``,
``sentinel_reports``). Keeps the N most-recent report *runs* per family and
removes older ones. The append-only ``*_LOG.md`` index and any ``.lock`` files
are never touched — they do not carry a ``_REPORT_`` token, so they are not
reports. A run is grouped by its ``YYYY-MM-DD_HH-MM-SS`` timestamp, so a metrics
run's ``.md`` + ``.json`` pair is always kept or pruned together.

Deletes from the working tree only — pruned reports remain in git history (the
prior audit's ``historical-retained`` rationale, now served by history rather
than a growing live directory). Default keeps N=10 per family; ``--dry-run``
previews without deleting.

Invocation::

    prune_reports.py                 # prune all families, keep 10, print summary
    prune_reports.py --keep 20       # keep 20 runs per family
    prune_reports.py --dry-run       # preview; delete nothing
    prune_reports.py --json          # machine-readable output
    prune_reports.py --repo-root DIR # operate on another checkout (tests)

Exit code: 0 — this is maintenance, advisory, never a gate. (Always 0 even when
a family directory is absent: nothing to prune is not an error.)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_KEEP = 10

# Report families pruned by this script, as (directory, filename prefix) pairs
# relative to repo root. Each family is a timestamped per-run report series plus
# an append-only *_LOG.md index.
#
# A family is (directory, prefix) rather than a directory alone because one
# directory legitimately hosts two independent series: `.ai-state/metrics_reports/`
# carries both the code-health `METRICS_REPORT_*` triple and the self-healing
# `SELF_HEALING_REPORT_*` triple, namespaces `self_healing_metrics.py` and
# `scripts/CLAUDE.md` both declare "deliberately distinct to avoid schema
# collision". Matching on a bare `_REPORT_` token collapsed them into one
# retention pool, so every self-healing run silently evicted a metrics run and
# vice versa, interleaved by timestamp. That is not hypothetical: it deleted
# `METRICS_REPORT_2026-06-11_08-38-15.{json,md}` twice, once on 2026-08-05 and
# again on 2026-08-06, while reporting `kept 10` — a count correct for the mixed
# pool and wrong for either real series.
_REPORT_FAMILIES = (
    (".ai-state/metrics_reports", "METRICS"),
    (".ai-state/metrics_reports", "SELF_HEALING"),
    (".ai-state/sentinel_reports", "SENTINEL"),
)

# A report file carries `<PREFIX>_REPORT_` and a sortable timestamp; the LOG
# index and lock files carry neither, so they are structurally exempt.
_REPORT_MARKER = "_REPORT_"
_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")

logger = logging.getLogger("prune_reports")


# -- Grouping -----------------------------------------------------------------


def _timestamp_of(name: str) -> str | None:
    """Return the ``YYYY-MM-DD_HH-MM-SS`` run token in a filename, or None."""
    match = _TIMESTAMP_RE.search(name)
    return match.group(0) if match else None


def _report_runs(family_dir: Path, prefix: str) -> dict[str, list[Path]]:
    """Map each run timestamp to its report files (e.g. a `.md` + `.json` pair).

    Only files whose name starts with ``<prefix>_REPORT_`` and carries a
    timestamp count; the ``*_LOG.md`` index and ``.lock`` files are excluded by
    construction, and a *sibling series* in the same directory is excluded by
    the prefix — which is the whole point of carrying one.
    """
    marker = f"{prefix}{_REPORT_MARKER}"
    runs: dict[str, list[Path]] = {}
    for path in family_dir.iterdir():
        if not path.is_file() or not path.name.startswith(marker):
            continue
        ts = _timestamp_of(path.name)
        if ts is None:
            continue
        runs.setdefault(ts, []).append(path)
    return runs


# -- Pruning ------------------------------------------------------------------


def prune_family(family_dir: Path, prefix: str, keep: int, dry_run: bool) -> dict[str, object]:
    """Keep the ``keep`` newest ``<prefix>_REPORT_`` runs; prune older run files.

    ``family`` is labelled ``<dir>:<prefix>`` because two families can share a
    directory, and a bare directory name would report them as one.
    """
    label = f"{family_dir.name}:{prefix}"
    if not family_dir.is_dir():
        return {"family": label, "present": False, "kept": 0, "pruned": []}

    runs = _report_runs(family_dir, prefix)
    # Newest-first by timestamp string (the fixed-width format sorts lexically).
    ordered = sorted(runs, reverse=True)
    prune_timestamps = ordered[keep:]

    pruned: list[str] = []
    for ts in prune_timestamps:
        for path in sorted(runs[ts]):
            pruned.append(str(path.relative_to(family_dir.parent.parent)))
            if not dry_run:
                path.unlink()

    return {
        "family": label,
        "present": True,
        "kept": min(len(ordered), keep),
        "pruned": sorted(pruned),
    }


def prune_all(repo_root: Path, keep: int, dry_run: bool) -> dict[str, object]:
    """Prune every configured report family under ``repo_root``."""
    families = [
        prune_family(repo_root / rel, prefix, keep, dry_run) for rel, prefix in _REPORT_FAMILIES
    ]
    total_pruned = sum(len(f["pruned"]) for f in families)  # type: ignore[arg-type]
    return {
        "keep": keep,
        "dry_run": dry_run,
        "total_pruned": total_pruned,
        "families": families,
    }


# -- Reporting ----------------------------------------------------------------


def _format_human(result: dict[str, object]) -> str:
    verb = "would prune" if result["dry_run"] else "pruned"
    lines = [
        f"prune_reports: {verb} {result['total_pruned']} report file(s), keep={result['keep']}"
    ]
    for fam in result["families"]:  # type: ignore[union-attr]
        if not fam["present"]:
            lines.append(f"  {fam['family']}: absent (skipped)")
        else:
            lines.append(f"  {fam['family']}: kept {fam['kept']}, {verb} {len(fam['pruned'])}")
    return "\n".join(lines)


# -- Orchestration ------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="prune_reports",
        description="Retain the N newest report runs per family in .ai-state/; prune older ones.",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=DEFAULT_KEEP,
        metavar="N",
        help=f"Number of newest runs to keep per family (default: {DEFAULT_KEEP}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview prunes without deleting.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    args = parser.parse_args(argv)
    if args.keep < 0:
        parser.error("--keep must be >= 0")
    return args


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2
    result = prune_all(repo_root, args.keep, args.dry_run)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_human(result))
    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("prune_reports: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
