#!/usr/bin/env python3
"""Self-healing-loop metrics collector (brief §7 auditability, §8 P6).

Queries the GitHub Actions run history of the self-healing loop's watched
workflows (`ci-autofix.yml`, `cross-model-review.yml`, `issue-autofix.yml`) plus
the `autofix:declined` label and fix-PR branch prefixes, then emits a timestamped
report triple to `.ai-state/metrics_reports/`:

    SELF_HEALING_REPORT_<ts>.json   canonical machine-readable payload
    SELF_HEALING_REPORT_<ts>.md     human-readable rendering
    SELF_HEALING_LOG.md             append-only one-row-per-run summary log

The prefix is deliberately distinct from the code-health `METRICS_REPORT_*` /
`METRICS_LOG.md` triple written by `scripts.project_metrics` into the same dir:
the two share a directory but NOT a schema (different columns) or a prune policy.
Reusing those names would corrupt the code-health log — see the P6 metric-taxonomy
ADR.

This is the P6 *baseline*: it stands the infrastructure up so the 60–90d ADR-seed
recalibration can accrue. On a days-old loop the first snapshot is sparse by
design — several fields are `null` with a documented reason (credit burn is
Cursor-side / operator-supplied; gate-verdict classification and override rate are
deferred to the recalibration pass once real gate comments exist to pattern-match).
The value is the ready-to-accrue collector, not the first numbers.

I/O (the `gh` calls) is isolated in `fetch_raw`; `compute_metrics` is a pure
function over the fetched payload so the metric math is unit-tested against
fixtures with no live network. Read-only: never mutates the repo or the PRs.

Run: `python3 scripts/self_healing_metrics.py [--window-days N] [--repo-root DIR]`
(script mode, so the sibling `_repo_root` import resolves; usually via the
`/loop-metrics` command).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _repo_root import git_toplevel_from_cwd

SCRIPT_DIR = Path(__file__).resolve().parent

SCHEMA_VERSION = "1.0.0"
TS_FORMAT = "%Y-%m-%d_%H-%M-%S"

# The loop surfaces we measure. Keys are workflow filenames as `gh` expects them.
AUTOFIX_WORKFLOW = "ci-autofix.yml"
GATE_WORKFLOW = "cross-model-review.yml"
ISSUE_AUTOFIX_WORKFLOW = "issue-autofix.yml"

DECLINED_LABEL = "autofix:declined"
# Branch prefixes the loop's fixers push to (never main; see dec-286 seam).
FIX_BRANCH_PREFIXES = ("ci-autofix/", "issue-autofix/")

RUN_JSON_FIELDS = "databaseId,status,conclusion,event,headBranch,createdAt,updatedAt,displayTitle"
PR_JSON_FIELDS = "number,headRefName,state,createdAt,updatedAt,mergedAt,closedAt,labels"
# Issues carry the decline record for the default-branch surface, which has no
# PR to label. Narrower than PR_JSON_FIELDS -- there is no head branch or merge
# state to read.
ISSUE_JSON_FIELDS = "number,title,state,createdAt,updatedAt,closedAt,labels"


# --------------------------------------------------------------------------- #
# gh I/O (the only impure layer)
# --------------------------------------------------------------------------- #
def _run_gh(args: list[str], errors: list[str]) -> Any:
    """Run a `gh` command returning parsed JSON; append a message to `errors` and
    return `None` on any failure (missing gh, auth, non-zero exit, bad JSON).

    A failed source degrades to empty data + a recorded error rather than aborting
    the whole snapshot — mirrors project_metrics' tool-availability philosophy.
    """
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        errors.append("gh CLI not found on PATH")
        return None
    if result.returncode != 0:
        errors.append(
            f"gh {' '.join(args[:3])}… exited {result.returncode}: {result.stderr.strip()[:200]}"
        )
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"gh {' '.join(args[:3])}… returned unparseable JSON: {exc}")
        return None


def _runs_for(workflow: str, errors: list[str], limit: int = 200) -> list[dict]:
    data = _run_gh(
        ["run", "list", "--workflow", workflow, "--limit", str(limit), "--json", RUN_JSON_FIELDS],
        errors,
    )
    return data if isinstance(data, list) else []


def fetch_raw(errors: list[str], *, limit: int = 200) -> dict[str, Any]:
    """Fetch every raw source the metrics derive from. Impure (network + auth).

    `gh` auto-detects the repository from the process CWD, so this must run with
    the CWD at the target repo root.
    """
    declined = _run_gh(
        [
            "pr",
            "list",
            "--label",
            DECLINED_LABEL,
            "--state",
            "all",
            "--limit",
            str(limit),
            "--json",
            PR_JSON_FIELDS,
        ],
        errors,
    )
    # The default-branch autofix surface has no PR to label -- it reacts to a
    # workflow_run failure -- so it records a decline as a labelled ISSUE.
    # Counting only `declined_prs` would leave that surface's declines
    # invisible, and would understate declines exactly as the surface's
    # `continue-on-error` (added alongside this query) removes them from
    # `autofix_failures`. The two changes have to land together or the
    # failure-rate series silently improves while the fixer degrades.
    declined_issues = _run_gh(
        [
            "issue",
            "list",
            "--label",
            DECLINED_LABEL,
            "--state",
            "all",
            "--limit",
            str(limit),
            "--json",
            ISSUE_JSON_FIELDS,
        ],
        errors,
    )
    all_prs = _run_gh(
        ["pr", "list", "--state", "all", "--limit", str(limit), "--json", PR_JSON_FIELDS],
        errors,
    )
    return {
        "autofix_runs": _runs_for(AUTOFIX_WORKFLOW, errors, limit),
        "gate_runs": _runs_for(GATE_WORKFLOW, errors, limit),
        "issue_autofix_runs": _runs_for(ISSUE_AUTOFIX_WORKFLOW, errors, limit),
        "declined_prs": declined if isinstance(declined, list) else [],
        "declined_issues": declined_issues if isinstance(declined_issues, list) else [],
        "all_prs": all_prs if isinstance(all_prs, list) else [],
    }


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _in_window(created: str | None, since: datetime) -> bool:
    ts = parse_ts(created)
    return ts is not None and ts >= since


def _tally_conclusions(runs: list[dict]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for r in runs:
        key = (r.get("conclusion") or r.get("status") or "unknown") or "unknown"
        tally[key] = tally.get(key, 0) + 1
    return tally


def _fix_prs(all_prs: list[dict], since: datetime) -> list[dict]:
    """PRs on a loop fixer branch prefix within the window."""
    out = []
    for pr in all_prs:
        head = pr.get("headRefName", "")
        if head.startswith(FIX_BRANCH_PREFIXES) and _in_window(pr.get("createdAt"), since):
            out.append(pr)
    return out


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


# Conclusions that mean the autofix never actually engaged the fixer agent:
# `skipped` (gate no-op — e.g. main-push with nothing to fix), `cancelled`
# (superseded by a newer run), or not-yet-concluded (`None`). Every main push
# fires a workflow_run → autofix → skip, so skips dominate the raw run count and
# would drown any real signal; "attempts" strips them.
_NON_ATTEMPT_CONCLUSIONS = frozenset({"skipped", "cancelled", None})


def _attempts(runs: list[dict]) -> list[dict]:
    """Runs where the fixer actually engaged (non-skipped, non-cancelled, concluded)."""
    return [r for r in runs if r.get("conclusion") not in _NON_ATTEMPT_CONCLUSIONS]


def _count_failures(runs: list[dict]) -> int:
    return sum(1 for r in runs if r.get("conclusion") == "failure")


# --------------------------------------------------------------------------- #
# metric computation (pure — unit-tested against fixtures)
# --------------------------------------------------------------------------- #
def compute_metrics(raw: dict[str, Any], *, window_days: int, now: datetime) -> dict[str, Any]:
    """Derive the brief §7 auditability metric families from fetched raw data.

    Pure: identical `raw` + `now` + `window_days` always yield identical output.
    Deferred fields carry an explicit `null` value plus a `_note` sibling naming
    why — never a fabricated zero.
    """
    since = now - timedelta(days=window_days)

    autofix_runs = [r for r in raw["autofix_runs"] if _in_window(r.get("createdAt"), since)]
    gate_runs = [r for r in raw["gate_runs"] if _in_window(r.get("createdAt"), since)]
    issue_runs = [r for r in raw["issue_autofix_runs"] if _in_window(r.get("createdAt"), since)]
    declined = [p for p in raw["declined_prs"] if _in_window(p.get("createdAt"), since)]
    declined_issues = [
        i for i in raw.get("declined_issues", []) if _in_window(i.get("createdAt"), since)
    ]
    fix_prs = _fix_prs(raw["all_prs"], since)

    autofix_attempts = _attempts(autofix_runs)
    issue_attempts = _attempts(issue_runs)

    merged_fix_prs = [p for p in fix_prs if p.get("mergedAt")]

    # time-to-green proxy: mergedAt − createdAt (hours) for merged fix PRs.
    ttg_hours: list[float] = []
    for p in merged_fix_prs:
        created, merged = parse_ts(p.get("createdAt")), parse_ts(p.get("mergedAt"))
        if created and merged:
            ttg_hours.append((merged - created).total_seconds() / 3600.0)

    fix_prs_opened = len(fix_prs)
    fix_prs_merged = len(merged_fix_prs)
    fix_success_rate = (fix_prs_merged / fix_prs_opened) if fix_prs_opened else None

    return {
        # 1. Gate catch-rate vs noise
        "gate": {
            "runs_total": len(gate_runs),
            "runs_by_conclusion": _tally_conclusions(gate_runs),
            "verdicts_classified": None,
            "_note": (
                "Verdict (request-changes vs approve vs unavailable) lives in the "
                "PR review comment, not the run conclusion; classification wiring is "
                "deferred to the recalibration pass once real gate comments exist to "
                "pattern-match. Baseline reports run counts only."
            ),
        },
        # 2. Credit burn — not GitHub-queryable
        "credit_burn": {
            "cursor_credits": None,
            "_note": "Cursor's credit pool is not GitHub-queryable; operator-supplied (brief §7 [U]).",
        },
        # 3. Fix success. `fix_prs_*` count NEW-BRANCH fixes only (ci-autofix/ +
        # issue-autofix/). The P3a pr_checks/dependabot surface pushes an in-place
        # fix commit onto the *existing* PR branch (stamped with an `Autofix-Attempt:`
        # trailer), so those fixes are NOT counted here — detecting them needs a
        # `git log --grep='Autofix-Attempt:'` scan of each PR head, deferred to the
        # recalibration pass. Baseline scope is explicit to avoid silent undercount.
        "fix_success": {
            "autofix_runs_total": len(autofix_runs),
            "autofix_attempts": len(autofix_attempts),
            "autofix_failures": _count_failures(autofix_attempts),
            "autofix_runs_by_conclusion": _tally_conclusions(autofix_runs),
            "issue_autofix_runs_total": len(issue_runs),
            "issue_autofix_attempts": len(issue_attempts),
            "issue_autofix_runs_by_conclusion": _tally_conclusions(issue_runs),
            # Split by surface, then summed. The PR-labelled series is the
            # PR/dependabot surfaces; the issue-labelled series is the
            # default-branch surface, whose fixer crash now exits green and
            # so no longer lands in `autofix_failures`. Reading the total
            # alone would hide a shift between the two.
            "declines_prs": len(declined),
            "declines_issues": len(declined_issues),
            "declines_total": len(declined) + len(declined_issues),
            "fix_prs_opened": fix_prs_opened,
            "fix_prs_merged": fix_prs_merged,
            "fix_success_rate": fix_success_rate,
            "_scope_note": (
                "fix_prs_* = new-branch fixes (ci-autofix/, issue-autofix/) only; "
                "in-place P3a fixes (Autofix-Attempt trailer on the PR branch) are "
                "uncounted pending trailer-scan wiring."
            ),
        },
        # 4. Time-to-green
        "time_to_green": {
            "sample_size": len(ttg_hours),
            "median_hours": _median(ttg_hours),
            "_note": "Proxy = mergedAt − createdAt of merged fix PRs; refine to first-failing-run → merge in the recalibration pass.",
        },
        # 5. Override rate — depends on gate-verdict classification (deferred)
        "override_rate": {
            "value": None,
            "_note": "Requires correlating gate request-changes verdicts with human merges; deferred with gate-verdict classification.",
        },
        # 6. Cost-per-fix — derived from credit burn (operator-supplied)
        "cost_per_fix": {
            "value": None,
            "_note": "credit_burn / fix_prs_merged; null until credit burn is operator-supplied.",
        },
    }


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _provenance(
    raw: dict[str, Any],
    errors: list[str],
    *,
    window_days: int,
    now: datetime,
    commit_sha: str,
    limit: int,
) -> dict[str, Any]:
    source_counts = {k: len(v) for k, v in raw.items()}
    # A source at the fetch limit is saturated — its count is a floor, not exact.
    saturated = [k for k, n in source_counts.items() if n >= limit]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "window_days": window_days,
        "since": (now - timedelta(days=window_days)).isoformat(),
        "commit_sha": commit_sha,
        "fetch_limit": limit,
        "source_counts": source_counts,
        "saturated_sources": saturated,
        "gh_errors": errors,
    }


def render_json(metrics: dict, provenance: dict) -> str:
    # Trailing newline: satisfies the "all files end with a newline" convention
    # (end-of-file-fixer) so a committed snapshot is not rewritten by the gate.
    return (
        json.dumps({"provenance": provenance, "metrics": metrics}, indent=2, sort_keys=False) + "\n"
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "_n/a_"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_md(metrics: dict, provenance: dict) -> str:
    g, fs = metrics["gate"], metrics["fix_success"]
    ttg = metrics["time_to_green"]
    lines = [
        "# Self-Healing Loop Metrics",
        "",
        f"- **Generated:** {provenance['generated_at']}",
        f"- **Window:** last {provenance['window_days']} days (since {provenance['since']})",
        f"- **Commit:** `{provenance['commit_sha']}`",
        f"- **Schema:** {provenance['schema_version']}",
        "",
        "## Fix success",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| CI autofix attempts (non-skipped) | {_fmt(fs['autofix_attempts'])} |",
        f"| — of which failed | {_fmt(fs['autofix_failures'])} |",
        f"| CI autofix runs (total, incl. skips) | {_fmt(fs['autofix_runs_total'])} |",
        f"| Issue autofix attempts (non-skipped) | {_fmt(fs['issue_autofix_attempts'])} |",
        f"| Declines (`autofix:declined`) | {_fmt(fs['declines_total'])} |",
        f"| — on PRs (PR + dependabot surfaces) | {_fmt(fs['declines_prs'])} |",
        f"| — as issues (default-branch surface) | {_fmt(fs['declines_issues'])} |",
        f"| Fix PRs opened (new-branch) | {_fmt(fs['fix_prs_opened'])} |",
        f"| Fix PRs merged (new-branch) | {_fmt(fs['fix_prs_merged'])} |",
        f"| Fix success rate (new-branch) | {_fmt(fs['fix_success_rate'])} |",
        "",
        f"- CI autofix by conclusion: {fs['autofix_runs_by_conclusion'] or '_none_'}",
        f"- _{fs['_scope_note']}_",
        "",
        "## Cross-model gate",
        "",
        f"- Runs (total): **{_fmt(g['runs_total'])}** — by conclusion: {g['runs_by_conclusion'] or '_none_'}",
        f"- Verdict classification: {_fmt(g['verdicts_classified'])} — {g['_note']}",
        "",
        "## Time-to-green",
        "",
        f"- Sample size: {_fmt(ttg['sample_size'])}; median: {_fmt(ttg['median_hours'])} h",
        f"- {ttg['_note']}",
        "",
        "## Deferred / operator-supplied",
        "",
        f"- **Credit burn:** {metrics['credit_burn']['_note']}",
        f"- **Override rate:** {metrics['override_rate']['_note']}",
        f"- **Cost per fix:** {metrics['cost_per_fix']['_note']}",
        "",
    ]
    warnings = list(provenance["gh_errors"])
    if provenance.get("saturated_sources"):
        warnings.append(
            f"Sources at the fetch limit ({provenance['fetch_limit']}) — counts are a floor, "
            f"not exact: {', '.join(provenance['saturated_sources'])}."
        )
    if warnings:
        lines += ["## Collection warnings", ""]
        lines += [f"- {w}" for w in warnings]
        lines += [""]
    return "\n".join(lines)


LOG_COLUMNS = [
    "schema_version",
    "generated_at",
    "commit_sha",
    "window_days",
    "autofix_attempts",
    "autofix_failures",
    "gate_runs",
    "declines",
    "fix_prs_opened",
    "fix_prs_merged",
    "issue_autofix_attempts",
    "report_file",
]
LOG_HEADER = "| " + " | ".join(LOG_COLUMNS) + " |"
LOG_SEP = "| " + " | ".join(["---"] * len(LOG_COLUMNS)) + " |"


def log_row(metrics: dict, provenance: dict, report_md_name: str) -> str:
    fs = metrics["fix_success"]
    return (
        f"| {provenance['schema_version']} | {provenance['generated_at']} | "
        f"{provenance['commit_sha']} | {provenance['window_days']} | "
        f"{fs['autofix_attempts']} | {fs['autofix_failures']} | {metrics['gate']['runs_total']} | "
        f"{fs['declines_total']} | {fs['fix_prs_opened']} | {fs['fix_prs_merged']} | "
        f"{fs['issue_autofix_attempts']} | [{report_md_name}]({report_md_name}) |"
    )


def append_log(log_path: Path, row: str) -> None:
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8").rstrip("\n")
        log_path.write_text(existing + "\n" + row + "\n", encoding="utf-8")
    else:
        log_path.write_text(LOG_HEADER + "\n" + LOG_SEP + "\n" + row + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def _commit_sha(repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return r.stdout.strip() or "unknown" if r.returncode == 0 else "unknown"
    except FileNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Self-healing-loop metrics collector (P6 baseline)."
    )
    parser.add_argument(
        "--window-days", type=int, default=90, help="Look-back window in days (default 90)."
    )
    parser.add_argument(
        "--repo-root", default=None, help="Repo root; defaults to git toplevel of CWD."
    )
    parser.add_argument(
        "--limit", type=int, default=200, help="Max rows per gh query (default 200)."
    )
    args = parser.parse_args(argv)

    if args.window_days <= 0:
        parser.error("--window-days must be a positive integer")

    repo_root = Path(args.repo_root).resolve() if args.repo_root else git_toplevel_from_cwd()
    if repo_root is None:
        print("error: not inside a git worktree and no --repo-root given", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    errors: list[str] = []
    raw = fetch_raw(errors, limit=args.limit)
    metrics = compute_metrics(raw, window_days=args.window_days, now=now)
    provenance = _provenance(
        raw,
        errors,
        window_days=args.window_days,
        now=now,
        commit_sha=_commit_sha(repo_root),
        limit=args.limit,
    )

    reports_dir = repo_root / ".ai-state" / "metrics_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = now.strftime(TS_FORMAT)
    json_path = reports_dir / f"SELF_HEALING_REPORT_{ts}.json"
    md_path = reports_dir / f"SELF_HEALING_REPORT_{ts}.md"
    log_path = reports_dir / "SELF_HEALING_LOG.md"

    json_path.write_text(render_json(metrics, provenance), encoding="utf-8")
    md_path.write_text(render_md(metrics, provenance), encoding="utf-8")
    append_log(log_path, log_row(metrics, provenance, md_path.name))

    for p in (json_path, md_path, log_path):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
