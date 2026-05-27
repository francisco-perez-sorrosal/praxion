"""Family 1 — Pipeline-outcome fidelity checks.

Mechanical checks verify structural correctness of ADRs and SPECs:
- ADR frontmatter completeness (required fields present)
- ADR body section presence (Context / Decision / Considered Options / Consequences)
- Supersession reciprocity (supersedes ↔ superseded_by symmetry)
- Re-affirmation reciprocity (re_affirms ↔ re_affirmed_by symmetry)
- SPEC traceability matrix presence
- affected_reqs resolvability (WARN on unresolvable — 20% population rate is expected)
- DECISIONS_INDEX row count consistency (WARN on mismatch)

LLM-judged checks evaluate substantive quality:
- Option-depth substantiveness (Considered Options section depth)

All LLM calls are routed through JudgeClient — this module never imports
claude_agent_sdk or anthropic directly.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from praxion_evals.harness.families import FAMILY_REGISTRY, Family
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import CheckResult, Corpus

# ---------------------------------------------------------------------------
# Required ADR frontmatter fields (per adr-conventions.md)
# ---------------------------------------------------------------------------

_REQUIRED_FRONTMATTER_FIELDS = (
    "id",
    "title",
    "status",
    "category",
    "date",
    "summary",
    "tags",
    "made_by",
)

# ---------------------------------------------------------------------------
# Required ADR body sections
# ---------------------------------------------------------------------------

_REQUIRED_BODY_SECTIONS = (
    "## Context",
    "## Decision",
    "## Considered Options",
    "## Consequences",
)

# ---------------------------------------------------------------------------
# LLM judge schema for option-depth check
# ---------------------------------------------------------------------------

_OPTION_DEPTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["PASS", "WARN", "FAIL"],
            "description": "Overall verdict for the Considered Options section depth.",
        },
        "findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Prose observations about option substantiveness.",
        },
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Confidence score 0–100.",
        },
    },
    "required": ["verdict", "findings", "score"],
}

_OPTION_DEPTH_RUBRIC = """\
Evaluate the 'Considered Options' section of the ADR below.

A substantive Considered Options section should:
1. Name at least two distinct options (Option A, Option B, etc.)
2. List pros (+) or cons (-) for each option, or explain why each was considered
3. Provide enough detail that a reader understands why the chosen option was selected

Emit:
- PASS: Two or more options with meaningful pro/con analysis
- WARN: Options present but shallow (e.g., one-word bullets, no actual trade-off analysis)
- FAIL: Only one option, no options, or placeholder text only
"""

# ---------------------------------------------------------------------------
# Frontmatter parser (stdlib-only, covers ADR YAML frontmatter)
# ---------------------------------------------------------------------------


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter fields from ADR content.

    Uses yaml.safe_load to correctly parse all YAML constructs found in
    Praxion ADR frontmatter: scalars, quoted strings, inline lists,
    and multi-line block lists (the dominant form in the real corpus).

    Args:
        content: Raw ADR file content starting with '---'.

    Returns:
        Dict of frontmatter fields. Empty dict if no frontmatter present.
    """
    if not content.startswith("---"):
        return {}

    # Find the closing '---' (must be on its own line)
    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {}

    fm_text = content[4:end_idx]  # skip the opening '---\n'
    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    return parsed


def _extract_id(content: str) -> str:
    """Return the 'id' field from ADR frontmatter, or empty string."""
    fm = _parse_frontmatter(content)
    return str(fm.get("id", ""))


def _count_index_rows(index_content: str) -> int:
    """Count the number of data rows in a DECISIONS_INDEX.md table."""
    # Table rows start with '|' and are not the header or separator rows
    rows = 0
    in_table = False
    for line in index_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            # Skip separator rows (|---|---|)
            if re.match(r"^\|[-|: ]+\|$", stripped):
                continue
            # Skip header row (contains 'ID' or 'Title' etc. — heuristic: first table row)
            # We'll count rows that have actual content in the first cell
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if cells and cells[0].lower() not in ("id", "#"):
                rows += 1
        elif in_table and not stripped.startswith("|"):
            # Table ended
            in_table = False
    return rows


# ---------------------------------------------------------------------------
# Family 1 implementation
# ---------------------------------------------------------------------------


class Family1PipelineOutcomeFidelity(Family):
    """Pipeline-outcome fidelity: structural + substantive ADR/SPEC quality."""

    id = "family1-pipeline-fidelity"
    name = "Family 1 — Pipeline-outcome fidelity"
    corpus_paths = (
        ".ai-state/decisions/",
        ".ai-state/specs/",
    )

    def run(self, corpus: Corpus, judge: JudgeClient) -> list[CheckResult]:
        """Execute all Family 1 checks against the corpus.

        Mechanical checks run first; LLM checks run last (cost-sensitive).

        Args:
            corpus: Resolved, immutable snapshot of the target's artifacts.
            judge: JudgeClient for LLM-judged checks.

        Returns:
            Ordered list of CheckResult objects.
        """
        results: list[CheckResult] = []

        # Separate DECISIONS_INDEX from real ADR files
        adr_entries = [
            (path, content)
            for path, content in corpus.decisions
            if not path.endswith("DECISIONS_INDEX.md")
        ]
        index_entries = [
            (path, content)
            for path, content in corpus.decisions
            if path.endswith("DECISIONS_INDEX.md")
        ]

        # --- Mechanical checks ---
        results.extend(self._check_frontmatter(adr_entries))
        results.extend(self._check_body_sections(adr_entries))
        results.extend(self._check_supersession_reciprocity(adr_entries))
        results.extend(self._check_re_affirmation_reciprocity(adr_entries))
        results.extend(self._check_spec_traceability(corpus.specs))
        results.extend(self._check_affected_reqs(adr_entries, corpus.specs))
        results.extend(self._check_decisions_index(adr_entries, index_entries))

        # --- LLM-judged checks ---
        results.extend(self._check_option_depth(adr_entries, judge))

        return results

    # ------------------------------------------------------------------
    # Mechanical: frontmatter completeness
    # ------------------------------------------------------------------

    def _check_frontmatter(self, adr_entries: list[tuple[str, str]]) -> list[CheckResult]:
        """Verify all required frontmatter fields are present in each ADR."""
        results: list[CheckResult] = []

        if not adr_entries:
            results.append(
                CheckResult(
                    check_name="adr_frontmatter_completeness",
                    check_kind="mechanical",
                    verdict="SKIP",
                    artifact_path="(no ADRs in corpus)",
                    findings=("No ADR files found in corpus.",),
                    score=-1,
                )
            )
            return results

        for path, content in adr_entries:
            fm = _parse_frontmatter(content)
            missing = [f for f in _REQUIRED_FRONTMATTER_FIELDS if f not in fm]
            if missing:
                results.append(
                    CheckResult(
                        check_name="adr_frontmatter_completeness",
                        check_kind="mechanical",
                        verdict="FAIL",
                        artifact_path=path,
                        findings=(
                            f"Missing required frontmatter fields: {missing}. "
                            f"All required fields: {list(_REQUIRED_FRONTMATTER_FIELDS)}.",
                        ),
                        score=-1,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check_name="adr_frontmatter_completeness",
                        check_kind="mechanical",
                        verdict="PASS",
                        artifact_path=path,
                        findings=("All required frontmatter fields present.",),
                        score=-1,
                    )
                )

        return results

    # ------------------------------------------------------------------
    # Mechanical: body section presence
    # ------------------------------------------------------------------

    def _check_body_sections(self, adr_entries: list[tuple[str, str]]) -> list[CheckResult]:
        """Verify required body sections are present in each ADR."""
        results: list[CheckResult] = []

        if not adr_entries:
            results.append(
                CheckResult(
                    check_name="adr_body_sections",
                    check_kind="mechanical",
                    verdict="SKIP",
                    artifact_path="(no ADRs in corpus)",
                    findings=("No ADR files found in corpus.",),
                    score=-1,
                )
            )
            return results

        for path, content in adr_entries:
            missing = [s for s in _REQUIRED_BODY_SECTIONS if s not in content]
            if missing:
                results.append(
                    CheckResult(
                        check_name="adr_body_sections",
                        check_kind="mechanical",
                        verdict="FAIL",
                        artifact_path=path,
                        findings=(
                            f"Missing required body sections: {missing}. "
                            f"Required: {list(_REQUIRED_BODY_SECTIONS)}.",
                        ),
                        score=-1,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check_name="adr_body_sections",
                        check_kind="mechanical",
                        verdict="PASS",
                        artifact_path=path,
                        findings=("All required body sections present.",),
                        score=-1,
                    )
                )

        return results

    # ------------------------------------------------------------------
    # Mechanical: supersession reciprocity
    # ------------------------------------------------------------------

    def _check_supersession_reciprocity(
        self, adr_entries: list[tuple[str, str]]
    ) -> list[CheckResult]:
        """Verify that supersedes/superseded_by links are symmetric."""
        results: list[CheckResult] = []

        # Build id → frontmatter map
        id_to_fm: dict[str, dict[str, Any]] = {}
        for _path, content in adr_entries:
            fm = _parse_frontmatter(content)
            adr_id = str(fm.get("id", ""))
            if adr_id:
                id_to_fm[adr_id] = fm

        violations: list[str] = []

        for adr_id, fm in id_to_fm.items():
            supersedes = str(fm.get("supersedes", "")).strip()
            if not supersedes:
                continue

            target_fm = id_to_fm.get(supersedes)
            if target_fm is None:
                # Target not in corpus — cannot verify; skip with WARN
                violations.append(
                    f"{adr_id} supersedes {supersedes!r} but target ADR not found in corpus."
                )
                continue

            back_link = str(target_fm.get("superseded_by", "")).strip()
            if back_link != adr_id:
                violations.append(
                    f"{adr_id} supersedes {supersedes!r} but "
                    f"{supersedes!r}.superseded_by={back_link!r} (expected {adr_id!r})."
                )

        if not violations and id_to_fm:
            # Check whether any supersedes links exist; if none, PASS trivially
            has_supersession = any("supersedes" in fm for fm in id_to_fm.values())
            verdict_note = (
                "All supersedes/superseded_by links are symmetric."
                if has_supersession
                else "No supersession links found in corpus (trivially consistent)."
            )
            results.append(
                CheckResult(
                    check_name="supersession_reciprocity",
                    check_kind="mechanical",
                    verdict="PASS",
                    artifact_path="(corpus-wide)",
                    findings=(verdict_note,),
                    score=-1,
                )
            )
        elif violations:
            results.append(
                CheckResult(
                    check_name="supersession_reciprocity",
                    check_kind="mechanical",
                    verdict="FAIL",
                    artifact_path="(corpus-wide)",
                    findings=tuple(violations),
                    score=-1,
                )
            )
        else:
            # Empty corpus
            results.append(
                CheckResult(
                    check_name="supersession_reciprocity",
                    check_kind="mechanical",
                    verdict="SKIP",
                    artifact_path="(no ADRs in corpus)",
                    findings=("No ADR files found in corpus.",),
                    score=-1,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Mechanical: re-affirmation reciprocity
    # ------------------------------------------------------------------

    def _check_re_affirmation_reciprocity(
        self, adr_entries: list[tuple[str, str]]
    ) -> list[CheckResult]:
        """Verify that re_affirms/re_affirmed_by links are symmetric."""
        results: list[CheckResult] = []

        id_to_fm: dict[str, dict[str, Any]] = {}
        for _path, content in adr_entries:
            fm = _parse_frontmatter(content)
            adr_id = str(fm.get("id", "")).strip()
            if adr_id:
                id_to_fm[adr_id] = fm

        violations: list[str] = []

        for adr_id, fm in id_to_fm.items():
            re_affirms = str(fm.get("re_affirms", "")).strip()
            if not re_affirms:
                continue

            target_fm = id_to_fm.get(re_affirms)
            if target_fm is None:
                violations.append(
                    f"{adr_id} re_affirms {re_affirms!r} but target ADR not found in corpus."
                )
                continue

            # re_affirmed_by is a list field
            back_links_raw = target_fm.get("re_affirmed_by", [])
            if isinstance(back_links_raw, list):
                back_links = [str(x).strip() for x in back_links_raw]
            else:
                back_links = [str(back_links_raw).strip()]

            if adr_id not in back_links:
                violations.append(
                    f"{adr_id} re_affirms {re_affirms!r} but "
                    f"{re_affirms!r}.re_affirmed_by={back_links!r} does not include {adr_id!r}."
                )

        if not violations and id_to_fm:
            has_reaffirmation = any("re_affirms" in fm for fm in id_to_fm.values())
            verdict_note = (
                "All re_affirms/re_affirmed_by links are symmetric."
                if has_reaffirmation
                else "No re-affirmation links found in corpus (trivially consistent)."
            )
            results.append(
                CheckResult(
                    check_name="re_affirmation_reciprocity",
                    check_kind="mechanical",
                    verdict="PASS",
                    artifact_path="(corpus-wide)",
                    findings=(verdict_note,),
                    score=-1,
                )
            )
        elif violations:
            results.append(
                CheckResult(
                    check_name="re_affirmation_reciprocity",
                    check_kind="mechanical",
                    verdict="FAIL",
                    artifact_path="(corpus-wide)",
                    findings=tuple(violations),
                    score=-1,
                )
            )
        else:
            results.append(
                CheckResult(
                    check_name="re_affirmation_reciprocity",
                    check_kind="mechanical",
                    verdict="SKIP",
                    artifact_path="(no ADRs in corpus)",
                    findings=("No ADR files found in corpus.",),
                    score=-1,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Mechanical: SPEC traceability matrix presence
    # ------------------------------------------------------------------

    def _check_spec_traceability(self, spec_entries: list[tuple[str, str]]) -> list[CheckResult]:
        """Verify each SPEC contains a Traceability Matrix section."""
        results: list[CheckResult] = []

        if not spec_entries:
            results.append(
                CheckResult(
                    check_name="spec_traceability_presence",
                    check_kind="mechanical",
                    verdict="SKIP",
                    artifact_path="(no SPECs in corpus)",
                    findings=("No SPEC files found in corpus.",),
                    score=-1,
                )
            )
            return results

        for path, content in spec_entries:
            has_matrix = "## Traceability Matrix" in content or "## Traceability" in content
            if has_matrix:
                results.append(
                    CheckResult(
                        check_name="spec_traceability_presence",
                        check_kind="mechanical",
                        verdict="PASS",
                        artifact_path=path,
                        findings=("Traceability Matrix section present.",),
                        score=-1,
                    )
                )
            else:
                results.append(
                    CheckResult(
                        check_name="spec_traceability_presence",
                        check_kind="mechanical",
                        verdict="FAIL",
                        artifact_path=path,
                        findings=(
                            "SPEC is missing the '## Traceability Matrix' section. "
                            "Archived SPECs must include a traceability matrix per "
                            "the spec-driven-development skill.",
                        ),
                        score=-1,
                    )
                )

        return results

    # ------------------------------------------------------------------
    # Mechanical: affected_reqs resolvability (WARN, not FAIL)
    # ------------------------------------------------------------------

    def _check_affected_reqs(
        self,
        adr_entries: list[tuple[str, str]],
        spec_entries: list[tuple[str, str]],
    ) -> list[CheckResult]:
        """Check that affected_reqs entries can be found in at least one SPEC.

        Emits WARN (not FAIL) when a REQ ID is not found — the 20% population
        rate means many ADRs legitimately have no affected_reqs.
        """
        results: list[CheckResult] = []

        # Build a set of all REQ-like identifiers mentioned across all SPECs
        all_spec_content = "\n".join(content for _, content in spec_entries)

        for path, content in adr_entries:
            fm = _parse_frontmatter(content)
            affected_reqs_raw = fm.get("affected_reqs", [])
            if not affected_reqs_raw:
                # No affected_reqs — skip this ADR for resolvability check
                continue

            if isinstance(affected_reqs_raw, list):
                req_ids = [str(r).strip().strip('"').strip("'") for r in affected_reqs_raw]
            else:
                req_ids = [str(affected_reqs_raw).strip()]

            for req_id in req_ids:
                if not req_id:
                    continue
                if req_id in all_spec_content:
                    results.append(
                        CheckResult(
                            check_name="affected_reqs_resolvability",
                            check_kind="mechanical",
                            verdict="PASS",
                            artifact_path=path,
                            findings=(f"REQ ID {req_id!r} found in at least one archived SPEC.",),
                            score=-1,
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            check_name="affected_reqs_resolvability",
                            check_kind="mechanical",
                            verdict="WARN",
                            artifact_path=path,
                            findings=(
                                f"REQ ID {req_id!r} not found in any archived SPEC. "
                                "This is expected for the ~80% of ADRs that predate "
                                "the spec archival practice or belong to direct-tier work.",
                            ),
                            score=-1,
                        )
                    )

        return results

    # ------------------------------------------------------------------
    # Mechanical: DECISIONS_INDEX row count consistency
    # ------------------------------------------------------------------

    def _check_decisions_index(
        self,
        adr_entries: list[tuple[str, str]],
        index_entries: list[tuple[str, str]],
    ) -> list[CheckResult]:
        """Compare DECISIONS_INDEX row count against number of ADR files.

        Emits WARN on mismatch — the index may lag by a few rows during
        active development (the finalize script regenerates it at merge).
        """
        if not index_entries:
            return [
                CheckResult(
                    check_name="decisions_index_consistency",
                    check_kind="mechanical",
                    verdict="SKIP",
                    artifact_path="(no DECISIONS_INDEX.md in corpus)",
                    findings=("DECISIONS_INDEX.md not found in corpus; skipping.",),
                    score=-1,
                )
            ]

        _index_path, index_content = index_entries[0]
        row_count = _count_index_rows(index_content)
        adr_count = len(adr_entries)

        if row_count == adr_count:
            return [
                CheckResult(
                    check_name="decisions_index_consistency",
                    check_kind="mechanical",
                    verdict="PASS",
                    artifact_path=_index_path,
                    findings=(
                        f"DECISIONS_INDEX row count ({row_count}) matches "
                        f"ADR file count ({adr_count}).",
                    ),
                    score=-1,
                )
            ]
        else:
            return [
                CheckResult(
                    check_name="decisions_index_consistency",
                    check_kind="mechanical",
                    verdict="WARN",
                    artifact_path=_index_path,
                    findings=(
                        f"DECISIONS_INDEX row count ({row_count}) does not match "
                        f"ADR file count ({adr_count}). "
                        "The index may be stale — run 'scripts/finalize_adrs.py' to regenerate.",
                    ),
                    score=-1,
                )
            ]

    # ------------------------------------------------------------------
    # LLM-judged: option-depth substantiveness
    # ------------------------------------------------------------------

    def _check_option_depth(
        self,
        adr_entries: list[tuple[str, str]],
        judge: JudgeClient,
    ) -> list[CheckResult]:
        """Evaluate the substantiveness of each ADR's Considered Options section.

        Uses the JudgeClient to call an LLM (Haiku tier, cost-sensitive).
        Returns one CheckResult per ADR.
        """
        results: list[CheckResult] = []

        if not adr_entries:
            return results

        for path, content in adr_entries:
            verdict_obj = judge.judge(
                rubric=_OPTION_DEPTH_RUBRIC,
                artifact=content,
                schema=_OPTION_DEPTH_SCHEMA,
            )
            results.append(
                CheckResult(
                    check_name="adr_option_depth",
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

FAMILY_REGISTRY.append(Family1PipelineOutcomeFidelity)
