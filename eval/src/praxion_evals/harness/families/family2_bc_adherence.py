"""Family 2 — Behavioral-contract adherence checks.

Mechanical checks scan VERIFICATION_REPORT.md files for the six BC violation tags:
    [UNSURFACED-ASSUMPTION], [MISSING-OBJECTION], [NON-SURGICAL],
    [SCOPE-CREEP], [BLOAT], [DEAD-CODE-UNREMOVED]

LLM-judged checks evaluate the four behavioral-contract behaviors via rubric:
    Surface Assumptions, Register Objection, Stay Surgical, Simplicity First

When the BC Findings section is absent (verifier did not reach Phase 5.5),
all checks emit SKIP with an explanatory prose note.

v1 corpus: VERIFICATION_REPORT.md only (LEARNINGS-distillation deferred).

This module never imports claude_agent_sdk or anthropic directly.
All LLM calls route through JudgeClient.
"""

from __future__ import annotations

from typing import Any

from praxion_evals.harness.families import FAMILY_REGISTRY, Family
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import CheckResult, Corpus

# ---------------------------------------------------------------------------
# BC violation tag definitions
# ---------------------------------------------------------------------------

_BC_TAGS: tuple[tuple[str, str], ...] = (
    ("unsurfaced_assumption", "[UNSURFACED-ASSUMPTION]"),
    ("missing_objection", "[MISSING-OBJECTION]"),
    ("non_surgical", "[NON-SURGICAL]"),
    ("scope_creep", "[SCOPE-CREEP]"),
    ("bloat", "[BLOAT]"),
    ("dead_code_unremoved", "[DEAD-CODE-UNREMOVED]"),
)

# Sentinel used to detect the BC findings section presence
_BC_SECTION_MARKER = "### Behavioral Contract Findings"

# Result cell content that means "no violation" (case-insensitive)
_NONE_VALUES = frozenset({"none", "—", "-", "0", ""})

# ---------------------------------------------------------------------------
# LLM rubrics and schemas for the four BC behaviors
# ---------------------------------------------------------------------------

_BC_BEHAVIORS: tuple[tuple[str, str], ...] = (
    (
        "bc_surface_assumptions",
        "Surface Assumptions",
    ),
    (
        "bc_register_objection",
        "Register Objection",
    ),
    (
        "bc_stay_surgical",
        "Stay Surgical",
    ),
    (
        "bc_simplicity_first",
        "Simplicity First",
    ),
)

_BC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["PASS", "WARN", "FAIL"],
            "description": "Overall verdict for this behavioral-contract behavior.",
        },
        "findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Prose observations about this behavior in the report.",
        },
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Confidence score 0-100.",
        },
    },
    "required": ["verdict", "findings", "score"],
}


def _build_bc_rubric(behavior_name: str) -> str:
    """Return a rubric for judging one behavioral-contract behavior."""
    rubric_text = {
        "Surface Assumptions": (
            "Evaluate whether the implementer 'Surfaced Assumptions' throughout "
            "this verification report.\n\n"
            "A good Surface Assumptions record:\n"
            "1. States the reviewer's interpretation upfront\n"
            "2. Explicitly names each gap-filling assumption as it was made\n"
            "3. Uses phrasing like 'Assumption:', 'Assumed that:', 'Surfaced assumption:'\n\n"
            "Emit:\n"
            "- PASS: Assumptions clearly surfaced in the report\n"
            "- WARN: Some evidence of surfacing but partial or implicit\n"
            "- FAIL: No assumptions surfaced, or verifier proceeded without stating them"
        ),
        "Register Objection": (
            "Evaluate whether the verifier 'Registered Objections' when scope, structure, "
            "or evidence conflicts were encountered.\n\n"
            "A good Register Objection record:\n"
            "1. States conflicts explicitly before complying or declining\n"
            "2. Gives a reason for the objection\n"
            "3. Does not silently agree when evidence or scope is violated\n\n"
            "Emit:\n"
            "- PASS: Objections clearly registered when warranted, or no conflicts arose\n"
            "- WARN: Conflicts acknowledged but no explicit objection framing\n"
            "- FAIL: Conflicts present but verifier did not register any objection"
        ),
        "Stay Surgical": (
            "Evaluate whether the verifier 'Stayed Surgical' — reviewed only what the "
            "change required and did not scope-creep beyond the declared files.\n\n"
            "A good Stay Surgical record:\n"
            "1. Reviews only the files declared in the step's scope\n"
            "2. Flags out-of-scope changes but does not block on them without reason\n"
            "3. Does not expand review scope silently\n\n"
            "Emit:\n"
            "- PASS: Review scope matches declared files; no unexplained scope expansion\n"
            "- WARN: Minor scope drift acknowledged and explained\n"
            "- FAIL: Significant unreported scope expansion, or refusal to note drift"
        ),
        "Simplicity First": (
            "Evaluate whether the verifier applied 'Simplicity First' — flagging "
            "unnecessary complexity, bloat, or over-engineering in the reviewed code.\n\n"
            "A good Simplicity First record:\n"
            "1. Notes when simpler solutions were available\n"
            "2. Flags added lines or files that did not earn their place\n"
            "3. Distinguishes necessary complexity from accidental complexity\n\n"
            "Emit:\n"
            "- PASS: Simplicity assessed; no bloat found, or bloat clearly flagged\n"
            "- WARN: Some complexity concerns but not fully analyzed\n"
            "- FAIL: Obvious bloat ignored, or no simplicity assessment made"
        ),
    }
    return rubric_text.get(behavior_name, f"Evaluate '{behavior_name}' behavioral compliance.")


# ---------------------------------------------------------------------------
# Tag violation detection helper
# ---------------------------------------------------------------------------


def _count_bc_tag_violations(content: str) -> dict[str, int]:
    """Return a map of tag → violation count parsed from the report content.

    Violation detection strategy:
    1. For each table row that contains a BC tag, parse the result cell.
       If the result cell is NOT a "none" value, count it as a violation.
    2. Additionally, count bare prose lines (non-table lines) that contain the tag.
       These are inline violation citations appended after the table.

    Table rows have this shape (from the BC Findings table):
        | `[TAG]` | <result text> |

    A result cell of "none", "—", "-", "0", or "" means no violation.
    Any other content (e.g. "1 occurrence — ...") is a violation.
    """
    violation_counts: dict[str, int] = {}
    all_tags = {tag for _, tag in _BC_TAGS}

    for line in content.splitlines():
        stripped = line.strip()
        # Identify which tag(s) appear on this line
        tags_on_line = [tag for tag in all_tags if tag in stripped]
        if not tags_on_line:
            continue

        for tag in tags_on_line:
            if stripped.startswith("|"):
                # Table row: parse the result cell (second cell after tag cell)
                cells = [c.strip() for c in stripped.split("|")]
                # cells[0] is empty (before first |), cells[1] is tag cell, cells[2] is result
                result_cell = cells[2].strip() if len(cells) > 2 else ""
                # Strip markdown formatting (backticks, bold markers)
                result_clean = result_cell.strip("`*").strip().lower()
                if result_clean not in _NONE_VALUES:
                    violation_counts[tag] = violation_counts.get(tag, 0) + 1
            else:
                # Prose line containing the tag — always a violation citation
                violation_counts[tag] = violation_counts.get(tag, 0) + 1

    return violation_counts


# ---------------------------------------------------------------------------
# Family 2 implementation
# ---------------------------------------------------------------------------


class Family2BehavioralContractAdherence(Family):
    """Behavioral-contract adherence: mechanical tag scans + LLM rubric checks."""

    id = "family2-bc-adherence"
    name = "Family 2 — Behavioral-contract adherence"
    corpus_paths = (".ai-work/",)

    def run(self, corpus: Corpus, judge: JudgeClient) -> list[CheckResult]:
        """Execute all Family 2 checks against the corpus.

        For each VERIFICATION_REPORT.md in the corpus:
        1. Detect BC Findings section presence — SKIP all checks if absent
        2. Run 6 mechanical tag-scan checks
        3. Run 4 LLM-judged rubric checks (one per behavioral-contract behavior)

        Args:
            corpus: Resolved, immutable snapshot of the target's artifacts.
            judge: JudgeClient for LLM-judged checks.

        Returns:
            Ordered list of CheckResult objects.
        """
        if not corpus.verification_reports:
            return [
                CheckResult(
                    check_name="bc_corpus_presence",
                    check_kind="mechanical",
                    verdict="SKIP",
                    artifact_path="(no verification reports in corpus)",
                    findings=(
                        "No VERIFICATION_REPORT.md files found in corpus. "
                        "Family 2 requires at least one verification report.",
                    ),
                    score=-1,
                )
            ]

        results: list[CheckResult] = []
        for path, content in corpus.verification_reports:
            results.extend(self._check_report(path, content, judge))
        return results

    def _check_report(self, path: str, content: str, judge: JudgeClient) -> list[CheckResult]:
        """Run all checks for one VERIFICATION_REPORT.md."""
        results: list[CheckResult] = []

        has_bc_section = _BC_SECTION_MARKER in content
        if not has_bc_section:
            results.append(
                CheckResult(
                    check_name="bc_section_presence",
                    check_kind="skip",
                    verdict="SKIP",
                    artifact_path=path,
                    findings=(
                        "Behavioral Contract Findings section absent. "
                        "The verifier did not reach Phase 5.5 of the review protocol, "
                        "so BC compliance could not be assessed. "
                        "All Family 2 checks are skipped for this report.",
                    ),
                    score=-1,
                )
            )
            return results

        # Mechanical: 6 tag scans
        results.extend(self._check_bc_tags(path, content))

        # LLM: 4 rubric checks
        results.extend(self._check_bc_rubrics(path, content, judge))

        return results

    def _check_bc_tags(self, path: str, content: str) -> list[CheckResult]:
        """Scan for each BC violation tag via table-cell parse + prose fallback.

        A violation is detected when:
        - The tag's table row in the BC Findings section has a non-"none" result cell, OR
        - The tag appears on a non-table line (bare prose violation line)

        Tags that only appear in table rows with "none" are clean (PASS).
        """
        results: list[CheckResult] = []
        violation_counts = _count_bc_tag_violations(content)

        for check_slug, tag in _BC_TAGS:
            check_name = f"bc_tag_{check_slug}"
            count = violation_counts.get(tag, 0)
            if count == 0:
                results.append(
                    CheckResult(
                        check_name=check_name,
                        check_kind="mechanical",
                        verdict="PASS",
                        artifact_path=path,
                        findings=(f"Tag {tag!r} has no recorded violations in report.",),
                        score=-1,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check_name=check_name,
                        check_kind="mechanical",
                        verdict="WARN",
                        artifact_path=path,
                        findings=(
                            f"Tag {tag!r} has {count} recorded violation(s) in report. "
                            "This tag indicates a behavioral-contract violation was recorded "
                            "by the verifier. Review the report for details.",
                        ),
                        score=-1,
                    )
                )
        return results

    def _check_bc_rubrics(self, path: str, content: str, judge: JudgeClient) -> list[CheckResult]:
        """Run one LLM rubric check per behavioral-contract behavior."""
        family_id = getattr(self, "id", self.__class__.__name__)
        results: list[CheckResult] = []
        for check_slug, behavior_name in _BC_BEHAVIORS:
            print(f"[{family_id}] llm-check {check_slug} — {path}", flush=True)
            rubric = _build_bc_rubric(behavior_name)
            verdict_obj = judge.judge(
                rubric=rubric,
                artifact=content,
                schema=_BC_SCHEMA,
            )
            results.append(
                CheckResult(
                    check_name=check_slug,
                    check_kind="llm",
                    verdict=verdict_obj.verdict,
                    artifact_path=path,
                    findings=verdict_obj.findings,
                    score=verdict_obj.score,
                )
            )
        return results


# ---------------------------------------------------------------------------
# Register in the global family registry
# ---------------------------------------------------------------------------

FAMILY_REGISTRY.append(Family2BehavioralContractAdherence)
