"""ReportWriter — per-run report file + append-only log.

Writes PRAXION_EVAL_REPORT_<ISO-timestamp>.md under the configured output
directory and appends a frozen-column row to PRAXION_EVAL_LOG.md.

Log column contract (must not change without a new ADR):
    Timestamp | Target | Auth route | Families | Pass | Warn | Fail | Cost (USD) | Report
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from praxion_evals.harness.schemas import Report

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPORT_PREFIX = "PRAXION_EVAL_REPORT"
_LOG_FILENAME = "PRAXION_EVAL_LOG.md"

_LOG_HEADER = (
    "| Timestamp | Target | Auth route | Families | Pass | Warn | Fail | Cost (USD) | Report |\n"
    "|-----------|--------|------------|----------|------|------|------|------------|--------|\n"
)

_CALIBRATION_NOTES = """\
## Calibration Notes

**Family 1 — affected_reqs population gap (20%):** Many ADRs legitimately omit
`affected_reqs` (Praxion population rate ~20%). Unresolvable entries emit WARN,
not FAIL, to avoid drowning the signal in expected gaps. A high WARN count on
`affected_reqs_resolvability` is expected and should not be treated as breakage.

**Family 2 — PASS-only corpus (v1):** The behavioral-contract adherence family
is calibrated on VERIFICATION_REPORT.md files from a corpus where all known
reports show PASS findings. False-negative detection (cases where the LLM
judge misses a real violation) is not tested at v1. Interpret PASS verdicts
from Family 2 with appropriate caution; adversarial fixtures are deferred to v2.
"""


# ---------------------------------------------------------------------------
# ReportWriter
# ---------------------------------------------------------------------------


class ReportWriter:
    """Writes per-run eval reports and appends rows to the persistent log.

    Args:
        output_dir: Directory under which the report file and log are written.
                    Created on first use if it does not exist.
    """

    def __init__(self, output_dir: Path | str) -> None:
        self._output_dir = Path(output_dir)

    def write(self, report: Report) -> str:
        """Render and write the report file. Return its absolute path as a string.

        Args:
            report: The aggregated Report from an eval run.

        Returns:
            Absolute path to the written report file.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _iso_timestamp()
        filename = f"{_REPORT_PREFIX}_{timestamp}.md"
        path = self._output_dir / filename
        content = _render_report(report, timestamp)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def append_log(self, report: Report, report_path: str) -> None:
        """Append a frozen-column row to PRAXION_EVAL_LOG.md.

        Creates the log file with a header if it does not exist.

        Args:
            report: The aggregated Report from an eval run.
            report_path: Absolute path to the report file (returned by write()).
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._output_dir / _LOG_FILENAME
        row = _build_log_row(report, report_path)
        if not log_path.exists():
            log_path.write_text(_LOG_HEADER + row + "\n", encoding="utf-8")
        else:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(row + "\n")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _iso_timestamp() -> str:
    """Return a filesystem-safe ISO-8601 timestamp (no colons)."""
    now = datetime.now(tz=UTC)
    return now.strftime("%Y-%m-%dT%H-%M-%SZ")


def _detect_auth_route() -> str:
    """Return the auth route label based on current env vars."""
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return "agent-sdk"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "messages-api"
    return "unknown"


def _render_report(report: Report, timestamp: str) -> str:
    """Render the full markdown report content."""
    corpus = report.corpus
    lines: list[str] = []

    # Header
    lines.append(f"# Praxion Eval Report — {timestamp}\n")
    lines.append(f"**Target**: `{corpus.target_label}` (kind: {corpus.target_kind})")
    lines.append(
        f"**Summary**: {report.pass_count} PASS / "
        f"{report.warn_count} WARN / "
        f"{report.fail_count} FAIL / "
        f"{report.skip_count} SKIP"
    )
    lines.append(f"**Estimated cost**: ${report.cost_usd_estimate:.4f} USD")
    lines.append("")

    # Check results table
    lines.append("## Check Results\n")
    lines.append("| Check | Kind | Verdict | Artifact | Score | Findings |")
    lines.append("|-------|------|---------|----------|-------|----------|")
    for r in report.check_results:
        score_str = str(r.score) if r.score >= 0 else "N/A"
        findings_str = "; ".join(r.findings) if r.findings else "—"
        lines.append(
            f"| {r.check_name} | {r.check_kind} | {r.verdict} "
            f"| {r.artifact_path} | {score_str} | {findings_str} |"
        )
    lines.append("")

    # Calibration Notes (required by AC-6)
    lines.append(_CALIBRATION_NOTES)

    return "\n".join(lines)


def _build_log_row(report: Report, report_path: str) -> str:
    """Build the frozen-column Markdown table row for the log."""
    corpus = report.corpus
    timestamp = _iso_timestamp()
    auth_route = _detect_auth_route()

    # Derive families label from check names present in the report (best-effort heuristic).
    # The Report schema does not carry an explicit families field; we infer from check names.
    family_ids: list[str] = []

    # Simple heuristic: detect family1 and/or family2 from check_name membership
    adr_checks = {
        "adr_frontmatter_completeness",
        "adr_body_sections",
        "supersession_reciprocity",
        "re_affirmation_reciprocity",
        "spec_traceability_presence",
        "affected_reqs_resolvability",
        "decisions_index_consistency",
    }
    bc_checks = {"bc_section_presence", "bc_tag_scan", "bc_rubric"}
    check_names = {r.check_name for r in report.check_results}

    if check_names & adr_checks:
        family_ids.append("family1")
    if check_names & bc_checks or any("bc_" in n for n in check_names):
        family_ids.append("family2")
    if not family_ids:
        family_ids = ["(none)"]

    families_str = "+".join(family_ids)
    report_name = Path(report_path).name if report_path else "—"

    return (
        f"| {timestamp} | {corpus.target_label} | {auth_route} | {families_str} "
        f"| {report.pass_count} | {report.warn_count} | {report.fail_count} "
        f"| ${report.cost_usd_estimate:.4f} | {report_name} |"
    )
