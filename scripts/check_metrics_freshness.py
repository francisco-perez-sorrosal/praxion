#!/usr/bin/env python3
"""Is the latest metrics report still describing current ``HEAD``?

A `/project-metrics` report is a photograph of the repository at one commit.
Consumers act on it later — the sentinel's TD dimension reads the newest report
and writes `td-NNN` rows into a ledger five agents consume. Between the shutter
and the reading, the subject moves.

The failure this guards against is specific and has happened: a report ranked
a file as the #1 hotspot; a commit decomposed that file the next day; the
sentinel read the report a week afterwards and came within one judgement call
of filing debt that was already paid.

**Days are the wrong unit.** The consuming policy asked whether the report was
older than 14 days. It was 7 — comfortably fresh — while roughly thirty commits
had landed, one of which resolved the finding. A hotspot is invalidated by a
*commit*, not by the passage of time, so this check measures commit distance
and, more precisely, asks the only question that admits an exact answer:

    has *this* hotspot's file been touched since the report was taken?

That is a per-path yes/no requiring no threshold. `commits_since` and
`age_days` are reported as context, never as the gate — inventing a commit
threshold would reproduce the original defect in a new unit.

**Withholding.** Reports written before provenance existed carry no `commit`,
and no filename encodes one. For those, commit distance is *unanswerable*, and
this check says so rather than defaulting to "fresh" — an unanswerable question
reported as a clean answer is how the original gap stayed invisible. A withheld
verdict is a signal to regenerate, not a pass.

Stdlib-only, deliberately: the sentinel invokes this through the ambient
interpreter, so a third-party import would make it a finding of
`check_gate_liveness.py`'s own `ambient-import` check.

Exit codes: ``0`` fresh / not applicable, ``1`` stale findings, ``2`` script error.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root

__all__ = ["evaluate_freshness", "main"]

_LOG = logging.getLogger("check_metrics_freshness")

_REPORTS_SUBDIR = Path(".ai-state") / "metrics_reports"
_REPORT_GLOB = "METRICS_REPORT_*.json"
_FILENAME_TIMESTAMP = re.compile(r"METRICS_REPORT_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.json$")
_FILENAME_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
_GIT_TIMEOUT_SECONDS = 30.0


# ---------------------------------------------------------------------------
# git helpers — every one returns None rather than raising, so an unavailable
# oracle becomes a withheld field instead of a crash or a wrong answer.
# ---------------------------------------------------------------------------


def _git(repo_root: Path, *argv: str) -> str | None:
    """Run ``git`` and return stdout, or ``None`` when it cannot answer."""

    try:
        completed = subprocess.run(
            ["git", *argv],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _commit_exists(repo_root: Path, sha: str) -> bool:
    """True when ``sha`` resolves to a commit in this repository."""

    return _git(repo_root, "cat-file", "-e", f"{sha}^{{commit}}") is not None


def _count_commits_between(repo_root: Path, sha: str) -> int | None:
    """Number of commits reachable from ``HEAD`` but not from ``sha``."""

    out = _git(repo_root, "rev-list", "--count", f"{sha}..HEAD")
    if out is None:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


def _paths_touched_since(repo_root: Path, sha: str, paths: list[str]) -> dict[str, int]:
    """Map each path to the number of commits touching it since ``sha``.

    One `git log` per path. The top-N is small (10 by default) and bounded by
    the report itself, so this stays a handful of subprocesses rather than the
    per-file sweep that would make it unusable on a large corpus.
    """

    touched: dict[str, int] = {}
    for path in paths:
        out = _git(repo_root, "rev-list", "--count", f"{sha}..HEAD", "--", path)
        if out is None:
            continue
        try:
            count = int(out.strip())
        except ValueError:
            continue
        if count > 0:
            touched[path] = count
    return touched


# ---------------------------------------------------------------------------
# Report discovery.
# ---------------------------------------------------------------------------


def _latest_report(reports_dir: Path) -> Path | None:
    """Newest report by filename timestamp, which sorts lexicographically."""

    candidates = sorted(reports_dir.glob(_REPORT_GLOB))
    return candidates[-1] if candidates else None


def _age_days(report_path: Path, now: datetime) -> int | None:
    """Days between the report's filename timestamp and ``now``.

    The filename is used rather than the embedded `generated_at` so this still
    works for pre-provenance reports. It is the weaker source — a copied or
    renamed file would lie — but it is the same basis `METRICS_LOG.md` and the
    trend block already use, so it introduces no new trust assumption.
    """

    match = _FILENAME_TIMESTAMP.search(report_path.name)
    if match is None:
        return None
    try:
        stamped = datetime.strptime(match.group(1), _FILENAME_TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return (now - stamped.replace(tzinfo=timezone.utc)).days


# ---------------------------------------------------------------------------
# Core evaluation — pure given (repo_root, reports_dir, now).
# ---------------------------------------------------------------------------


def evaluate_freshness(
    repo_root: Path,
    *,
    reports_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Return the freshness verdict for the newest metrics report.

    ``status`` is one of:

    * ``absent``  — no report exists; nothing to judge (not a failure).
    * ``withheld`` — a report exists but commit distance is unanswerable.
    * ``stale``   — at least one ranked hotspot's file moved since the report.
    * ``fresh``   — a report exists, its commit is known, and no ranked
      hotspot has been touched since.
    """

    now = now or datetime.now(timezone.utc)
    reports_dir = reports_dir or (repo_root / _REPORTS_SUBDIR)

    result: dict[str, object] = {
        "status": "absent",
        "report": None,
        "commit": None,
        "age_days": None,
        "commits_since": None,
        "dirty": None,
        "hotspots_touched": [],
        "withheld": [],
        "findings": [],
    }

    if not reports_dir.is_dir():
        result["note"] = f"{reports_dir} does not exist; /project-metrics has never run"
        return result

    report_path = _latest_report(reports_dir)
    if report_path is None:
        result["note"] = f"no {_REPORT_GLOB} in {reports_dir}"
        return result

    result["report"] = report_path.name
    result["age_days"] = _age_days(report_path, now)

    try:
        payload = json.loads(report_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        result["status"] = "withheld"
        result["withheld"] = [{"field": "all", "reason": f"report unreadable: {exc}"}]
        return result

    run_metadata = payload.get("run_metadata") or {}
    commit = run_metadata.get("commit")
    result["commit"] = commit
    result["dirty"] = run_metadata.get("dirty")

    if not commit:
        # Pre-provenance report. Commit distance is not merely unknown, it is
        # unrecoverable — no filename or log entry records the analysed SHA.
        result["status"] = "withheld"
        result["withheld"] = [
            {
                "field": "commits_since",
                "reason": (
                    "report carries no run_metadata.commit (written before provenance "
                    "was recorded); commit distance is unrecoverable — regenerate with "
                    "/project-metrics to restore the freshness signal"
                ),
            },
            {"field": "hotspots_touched", "reason": "requires run_metadata.commit"},
        ]
        return result

    if not _commit_exists(repo_root, str(commit)):
        result["status"] = "withheld"
        result["withheld"] = [
            {
                "field": "commits_since",
                "reason": (
                    f"run_metadata.commit {commit} is not present in this repository "
                    "(rebased, or the report came from another clone)"
                ),
            },
            {"field": "hotspots_touched", "reason": "requires a resolvable commit"},
        ]
        return result

    result["commits_since"] = _count_commits_between(repo_root, str(commit))

    hotspots = payload.get("hotspots") or {}
    top_n = hotspots.get("top_n") if isinstance(hotspots, dict) else None
    ranked = [e for e in (top_n or []) if isinstance(e, dict) and e.get("path")]
    paths = [str(e["path"]) for e in ranked]
    touched = _paths_touched_since(repo_root, str(commit), paths)

    entries = [
        {
            "path": str(e["path"]),
            "rank": e.get("rank"),
            "commits_since_report": touched[str(e["path"])],
        }
        for e in ranked
        if str(e["path"]) in touched
    ]
    result["hotspots_touched"] = entries

    if entries:
        result["status"] = "stale"
        result["findings"] = [
            {
                "kind": "hotspot-moved-since-report",
                "path": e["path"],
                "rank": e["rank"],
                "detail": (
                    f"ranked #{e['rank']} in {report_path.name} but modified by "
                    f"{e['commits_since_report']} commit(s) since that report's commit — "
                    "re-verify against current source before filing debt"
                ),
            }
            for e in entries
        ]
    else:
        result["status"] = "fresh"

    return result


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _render_human(result: dict[str, object]) -> str:
    status = result["status"]
    lines = [f"metrics freshness: {status}"]
    if result.get("report"):
        lines.append(f"  report:        {result['report']}")
    if result.get("age_days") is not None:
        lines.append(f"  age:           {result['age_days']} day(s)")
    if result.get("commits_since") is not None:
        lines.append(f"  commits since: {result['commits_since']}")
    if result.get("dirty"):
        lines.append("  tree:          dirty at capture (describes no single commit)")
    for entry in result.get("withheld") or []:
        lines.append(f"  WITHHELD {entry['field']}: {entry['reason']}")
    for finding in result.get("findings") or []:
        lines.append(f"  STALE #{finding['rank']} {finding['path']}")
        lines.append(f"    {finding['detail']}")
    if status == "fresh":
        lines.append("  no ranked hotspot has moved since the report's commit")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--repo-root", default=None, help="repository root (defaults to git root)")
    parser.add_argument(
        "--reports-dir", default=None, help="override the metrics_reports directory (tests)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    try:
        repo_root = resolve_repo_root(args.repo_root, script_dir=Path(__file__).resolve().parent)
    except Exception as exc:  # pragma: no cover - defensive
        _LOG.error("could not resolve repo root: %s", exc)
        return 2

    if is_plugin_cache_path(repo_root):
        _LOG.error("refusing to run against a plugin-cache path: %s", repo_root)
        return 2

    reports_dir = Path(args.reports_dir) if args.reports_dir else None
    try:
        result = evaluate_freshness(repo_root, reports_dir=reports_dir)
    except Exception as exc:  # pragma: no cover - defensive
        _LOG.error("freshness evaluation failed: %s", exc)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_render_human(result))

    return 1 if result["status"] == "stale" else 0


if __name__ == "__main__":
    sys.exit(main())
