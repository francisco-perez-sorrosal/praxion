"""Behavioral tests for Family 2 — Behavioral-contract adherence.

Tests cover the BC-section presence check, six BC tag scans, four LLM-judged
behavior checks (with FakeJudgeClient), the SKIP path when the section is
absent, and the AC-7 lint guard.

All production imports are deferred inside each test body so pytest collection
succeeds before the family module exists (RED-state handshake).

FakeJudgeClient is defined at module scope so it is available to all tests
without importing the real JudgeClient ABC during collection.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal VERIFICATION_REPORT fixtures
# ---------------------------------------------------------------------------

# A report that contains the Behavioral Contract section with PASS content.
# This mirrors the shape of the real head-milestone-verify VERIFICATION_REPORT.md
# so the fixture stays honest about what a real passing report looks like.
_REPORT_WITH_BC_SECTION = textwrap.dedent("""\
    # Verification Report — Test Pipeline

    **Mode**: Pipeline verification.

    ---

    ## Verdict: PASS WITH FINDINGS

    | Category | Result |
    |----------|--------|
    | Test suite | PASS |
    | Behavioral-contract compliance | PASS (no violations observed) |

    ---

    ## 1. Test Suite Health

    All tests passed.

    ---

    ## 3. Behavioral-Contract Compliance (Phase 5.5)

    ### Behavioral Contract Findings

    Behavioral-contract compliance: PASS (no violations observed)

    | Tag | Result |
    |-----|--------|
    | `[UNSURFACED-ASSUMPTION]` | none |
    | `[MISSING-OBJECTION]` | none |
    | `[NON-SURGICAL]` | none |
    | `[SCOPE-CREEP]` | none |
    | `[BLOAT]` | none |
    | `[DEAD-CODE-UNREMOVED]` | none |
""")

# A report that lacks the Behavioral Contract Findings section entirely.
_REPORT_WITHOUT_BC_SECTION = textwrap.dedent("""\
    # Verification Report — Early Pipeline

    **Mode**: Pipeline verification.

    ---

    ## Verdict: PASS

    | Category | Result |
    |----------|--------|
    | Test suite | PASS |

    ---

    ## 1. Test Suite Health

    All tests passed.

    No behavioral-contract section was written (verifier did not reach Phase 5.5).
""")

# A report with BC tags present (violations observed).
_REPORT_WITH_BC_VIOLATIONS = textwrap.dedent("""\
    # Verification Report — Violation Sample

    **Mode**: Pipeline verification.

    ---

    ## 3. Behavioral-Contract Compliance (Phase 5.5)

    ### Behavioral Contract Findings

    | Tag | Result |
    |-----|--------|
    | `[UNSURFACED-ASSUMPTION]` | 1 occurrence — the implementer assumed X without stating it |
    | `[MISSING-OBJECTION]` | none |
    | `[NON-SURGICAL]` | 1 occurrence — modified file Y outside declared scope |
    | `[SCOPE-CREEP]` | none |
    | `[BLOAT]` | none |
    | `[DEAD-CODE-UNREMOVED]` | none |

    `[UNSURFACED-ASSUMPTION]` The implementer assumed the database would be seeded without surfacing this.
    `[NON-SURGICAL]` Modified config.py outside the declared file set.
""")


# ---------------------------------------------------------------------------
# FakeJudgeClient — scripted verdicts; no SDK calls
# ---------------------------------------------------------------------------


class FakeJudgeClient:
    """A test double for JudgeClient.

    Returns a pre-scripted JudgeVerdict for every judge() call. The verdict
    dict is converted to a real JudgeVerdict instance after the harness schemas
    module is available (importable at test runtime).
    """

    def __init__(
        self, verdict: str = "PASS", findings: tuple[str, ...] = ("looks good",), score: int = 90
    ) -> None:
        self._verdict = verdict
        self._findings = findings
        self._score = score

    def judge(self, rubric: str, artifact: str, schema: Any) -> Any:
        from praxion_evals.harness.schemas import JudgeVerdict

        return JudgeVerdict(
            verdict=self._verdict,  # type: ignore[arg-type]
            findings=self._findings,
            score=self._score,
            raw={"verdict": self._verdict, "findings": list(self._findings), "score": self._score},
        )


# ---------------------------------------------------------------------------
# Helper: build minimal Corpus objects
# ---------------------------------------------------------------------------


def _make_corpus(
    verification_reports: list[tuple[str, str]] | None = None,
    decisions: list[tuple[str, str]] | None = None,
    specs: list[tuple[str, str]] | None = None,
) -> Any:
    """Build a minimal Corpus using the harness Corpus dataclass."""
    from praxion_evals.harness.schemas import Corpus

    return Corpus(
        target_kind="path",
        target_label="synthetic-fixture",
        decisions=tuple(decisions or []),
        specs=tuple(specs or []),
        verification_reports=tuple(verification_reports or []),
    )


# ---------------------------------------------------------------------------
# BC section presence: present → no SKIP emitted; 4 LLM checks queued
# ---------------------------------------------------------------------------


def test_bc_section_present_no_skip_emitted():
    """When the Behavioral Contract section is present, no SKIP result is emitted."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    skip_results = [r for r in results if r.verdict == "SKIP"]
    assert len(skip_results) == 0, (
        "No SKIP results should be emitted when the BC Findings section is present; "
        f"got {len(skip_results)} SKIP: {[r.findings for r in skip_results]!r}"
    )


def test_bc_section_present_four_llm_checks_produced():
    """When the BC section is present, exactly 4 LLM-judged checks are emitted
    (one per behavioral-contract behavior)."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    llm_results = [r for r in results if r.check_kind == "llm"]
    assert len(llm_results) == 4, (
        f"Family 2 must produce exactly 4 LLM-judged checks (one per behavior); "
        f"got {len(llm_results)}: {[r.check_name for r in llm_results]!r}"
    )


def test_bc_section_present_all_four_behavior_names_covered():
    """The four LLM checks cover the four behavioral-contract behaviors."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    llm_check_names = {r.check_name for r in results if r.check_kind == "llm"}
    # The four behaviors must each have a check — use substring matching so
    # implementers have flexibility in naming (e.g. "bc_surface_assumptions" or
    # "surface_assumptions") without breaking the test on style choices.
    expected_keywords = {"surface", "objection", "surgical", "simplicity"}
    covered = {kw for kw in expected_keywords if any(kw in name for name in llm_check_names)}
    assert covered == expected_keywords, (
        f"LLM checks must cover all 4 BC behaviors; missing: {expected_keywords - covered!r}. "
        f"Found check names: {llm_check_names!r}"
    )


# ---------------------------------------------------------------------------
# BC section absent → SKIP emitted with explanatory prose
# ---------------------------------------------------------------------------


def test_bc_section_absent_skip_emitted():
    """When the Behavioral Contract section is absent, a SKIP result is emitted."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/old-verify/VERIFICATION_REPORT.md", _REPORT_WITHOUT_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    skip_results = [r for r in results if r.verdict == "SKIP"]
    assert len(skip_results) >= 1, (
        "At least one SKIP result must be emitted when the BC Findings section is absent"
    )


def test_bc_section_absent_skip_has_phase_explanation():
    """The SKIP result for an absent BC section includes prose mentioning Phase 5.5."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/old-verify/VERIFICATION_REPORT.md", _REPORT_WITHOUT_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    skip_results = [r for r in results if r.verdict == "SKIP"]
    assert skip_results, "Expected at least one SKIP result"
    skip_findings_text = " ".join(" ".join(r.findings) for r in skip_results)
    # The prose should mention Phase 5.5 to explain why BC checks were skipped.
    assert "5.5" in skip_findings_text or "phase" in skip_findings_text.lower(), (
        "SKIP findings must explain why the section was absent (mention Phase 5.5 or 'phase'); "
        f"got: {skip_findings_text!r}"
    )


# ---------------------------------------------------------------------------
# BC tag scans — mechanical checks
# ---------------------------------------------------------------------------


def test_bc_tag_scans_zero_occurrences_produce_pass():
    """When no BC tags appear in the content, all 6 tag-scan checks return PASS."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    tag_scan_results = [r for r in results if r.check_kind == "mechanical"]
    assert len(tag_scan_results) >= 6, (
        f"Family 2 must run at least 6 mechanical tag-scan checks; got {len(tag_scan_results)}"
    )
    # All mechanical checks should PASS when no BC tags appear in clean content
    for r in tag_scan_results:
        assert r.verdict == "PASS", (
            f"Mechanical check {r.check_name!r} should PASS with zero tag occurrences; "
            f"got {r.verdict!r} with findings: {r.findings!r}"
        )


def test_unsurfaced_assumption_tag_present_produces_warn():
    """A report containing [UNSURFACED-ASSUMPTION] tag produces a WARN for that check."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/violation-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_VIOLATIONS)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    # Find the UNSURFACED-ASSUMPTION mechanical check
    tag_results = [
        r for r in results if r.check_kind == "mechanical" and "unsurfaced" in r.check_name.lower()
    ]
    assert tag_results, "A mechanical check for [UNSURFACED-ASSUMPTION] tag must be emitted"
    assert any(r.verdict == "WARN" for r in tag_results), (
        "When [UNSURFACED-ASSUMPTION] appears in the content, the check must produce WARN; "
        f"got verdicts: {[r.verdict for r in tag_results]!r}"
    )


def test_non_surgical_tag_present_produces_warn():
    """A report containing [NON-SURGICAL] tag produces a WARN for that check."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/violation-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_VIOLATIONS)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    tag_results = [
        r for r in results if r.check_kind == "mechanical" and "surgical" in r.check_name.lower()
    ]
    assert tag_results, "A mechanical check for [NON-SURGICAL] tag must be emitted"
    assert any(r.verdict == "WARN" for r in tag_results), (
        "When [NON-SURGICAL] appears in the content, the check must produce WARN; "
        f"got verdicts: {[r.verdict for r in tag_results]!r}"
    )


def test_all_six_bc_tags_have_mechanical_checks():
    """Family 2 produces a mechanical check for each of the 6 BC violation tags."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    tag_check_names = {r.check_name for r in results if r.check_kind == "mechanical"}
    # Each of the 6 BC tags must have a corresponding mechanical check.
    # Use keywords because naming conventions vary (e.g. "tag_unsurfaced" vs "unsurfaced_assumption").
    expected_tag_keywords = {
        "unsurfaced",
        "objection",
        "surgical",
        "scope",
        "bloat",
        "dead_code",
    }
    covered = {kw for kw in expected_tag_keywords if any(kw in name for name in tag_check_names)}
    assert covered == expected_tag_keywords, (
        f"Mechanical checks must cover all 6 BC tags; missing: {expected_tag_keywords - covered!r}. "
        f"Found check names: {tag_check_names!r}"
    )


# ---------------------------------------------------------------------------
# LLM-judged checks: FakeJudgeClient returning PASS for all 4 behaviors
# ---------------------------------------------------------------------------


def test_fake_judge_pass_produces_four_pass_llm_results():
    """A FakeJudgeClient returning PASS yields 4 CheckResults all with verdict=PASS."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient(verdict="PASS", findings=("no violations",), score=95)

    results = family.run(corpus, fake_judge)

    llm_results = [r for r in results if r.check_kind == "llm"]
    assert len(llm_results) == 4, f"Expected 4 LLM results; got {len(llm_results)}"
    for r in llm_results:
        assert r.verdict == "PASS", (
            f"LLM check {r.check_name!r} must be PASS when FakeJudgeClient is PASS; "
            f"got {r.verdict!r}"
        )
        assert r.check_kind == "llm", (
            f"BC-rubric checks must have check_kind='llm'; got {r.check_kind!r}"
        )


def test_fake_judge_fail_produces_fail_llm_results():
    """A FakeJudgeClient returning FAIL propagates FAIL to all 4 LLM check results."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient(verdict="FAIL", findings=("violation detected",), score=20)

    results = family.run(corpus, fake_judge)

    llm_results = [r for r in results if r.check_kind == "llm"]
    assert len(llm_results) == 4, f"Expected 4 LLM results; got {len(llm_results)}"
    for r in llm_results:
        assert r.verdict == "FAIL", (
            f"LLM check {r.check_name!r} must be FAIL when FakeJudgeClient is FAIL; "
            f"got {r.verdict!r}"
        )


# ---------------------------------------------------------------------------
# Schema enforcement: all CheckResults are well-formed
# ---------------------------------------------------------------------------


def test_all_check_results_have_valid_verdicts():
    """Every CheckResult from Family 2 has a verdict in the allowed set."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    assert len(results) > 0, "Family 2 must produce at least one CheckResult"
    for r in results:
        assert r.verdict in ("PASS", "WARN", "FAIL", "SKIP"), (
            f"CheckResult verdict must be one of PASS/WARN/FAIL/SKIP; got {r.verdict!r}"
        )
        assert r.check_kind in ("mechanical", "llm", "skip"), (
            f"CheckResult check_kind must be mechanical/llm/skip; got {r.check_kind!r}"
        )
        assert r.check_name, "CheckResult must have a non-empty check_name"


def test_mechanical_check_results_have_negative_one_score():
    """Mechanical tag-scan checks produce CheckResult with score=-1 (score N/A)."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    mechanical_results = [r for r in results if r.check_kind == "mechanical"]
    assert len(mechanical_results) > 0, "Family 2 must produce at least one mechanical CheckResult"
    for r in mechanical_results:
        assert r.score == -1, (
            f"Mechanical CheckResult score must be -1 (not applicable); got {r.score} "
            f"for check {r.check_name!r}"
        )


# ---------------------------------------------------------------------------
# Calibration notes: report includes the PASS-only-corpus gap note
# ---------------------------------------------------------------------------


def test_report_writer_includes_family2_calibration_note(tmp_path: Path):
    """The report written by ReportWriter contains the Family 2 PASS-only-corpus calibration note."""
    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import Report

    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[
            (".ai-work/head-verify/VERIFICATION_REPORT.md", _REPORT_WITH_BC_SECTION)
        ]
    )
    fake_judge = FakeJudgeClient()
    check_results = tuple(family.run(corpus, fake_judge))

    report = Report(corpus=corpus, check_results=check_results, cost_usd_estimate=0.0)
    writer = ReportWriter(output_dir=tmp_path)
    written_path = writer.write(report)

    content = Path(written_path).read_text(encoding="utf-8")
    # The Calibration Notes section must mention the PASS-only corpus gap for Family 2.
    assert "## Calibration Notes" in content, "Report must contain a '## Calibration Notes' section"
    # The note should acknowledge the adversarial fixture gap — use soft matching
    # so wording can evolve without breaking the test.
    calibration_section = content.split("## Calibration Notes", 1)[-1]
    keywords_present = (
        "adversarial" in calibration_section.lower()
        or "pass-only" in calibration_section.lower()
        or "calibration gap" in calibration_section.lower()
        or "false-negative" in calibration_section.lower()
    )
    assert keywords_present, (
        "The Calibration Notes section must acknowledge the Family 2 PASS-only-corpus gap "
        "(adversarial fixtures, false-negative detection unvalidated); "
        f"calibration text: {calibration_section[:300]!r}"
    )


# ---------------------------------------------------------------------------
# AC-7 lint guard: family2 module must not import SDKs directly
# ---------------------------------------------------------------------------


def test_family2_module_source_contains_no_direct_sdk_imports():
    """Family2 source file must not contain direct claude_agent_sdk or anthropic imports.

    This is the behavioral encoding of the import-isolation requirement: family code
    calls JudgeClient.judge() only; SDK imports belong exclusively in judge_client.py.
    """
    import importlib.util

    spec = importlib.util.find_spec("praxion_evals.harness.families.family2_bc_adherence")
    assert spec is not None, "family2_bc_adherence module must be importable after implementation"
    assert spec.origin is not None, "Module origin (source file path) must be non-None"

    source = Path(spec.origin).read_text(encoding="utf-8")
    forbidden_patterns = [
        "import claude_agent_sdk",
        "from claude_agent_sdk",
        "import anthropic",
        "from anthropic",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source, (
            f"Family2 source must not contain {pattern!r} — SDK imports belong in judge_client.py"
        )


# ---------------------------------------------------------------------------
# Corpus-shape integration test: real VERIFICATION_REPORT.md
# ---------------------------------------------------------------------------

# Resolve the real VERIFICATION_REPORT.md from the canonical checkout's .ai-work/
# This follows the same discipline as test_harness_family1_corpus_integration.py:
# use real artifacts, not synthetic ones, to catch parser failures.
_CANONICAL_REPO = Path(__file__).parent.parent.parent
_REAL_REPORT_PATH = (
    _CANONICAL_REPO / ".ai-work" / "head-milestone-verify" / "VERIFICATION_REPORT.md"
)


def test_real_verification_report_bc_section_detected():
    """The real VERIFICATION_REPORT.md from head-milestone-verify has a BC section
    that Family 2 detects correctly (no SKIP emitted)."""
    # Register objection trigger: if this file doesn't exist, the corpus contract
    # is broken (no real PASS-case fixture) and the test must fail with a clear message.
    assert _REAL_REPORT_PATH.exists(), (
        f"Real VERIFICATION_REPORT.md not found at {_REAL_REPORT_PATH}. "
        "This is a corpus-contract violation: Family 2 integration tests require a real "
        "VERIFICATION_REPORT.md, not a synthetic fixture. "
        "Locate the report or document why none is reachable."
    )

    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    report_content = _REAL_REPORT_PATH.read_text(encoding="utf-8")
    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[(str(_REAL_REPORT_PATH.relative_to(_CANONICAL_REPO)), report_content)]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    assert len(results) > 0, "Family 2 must produce at least one result against the real report"
    skip_results = [r for r in results if r.verdict == "SKIP"]
    assert len(skip_results) == 0, (
        "The real head-milestone-verify VERIFICATION_REPORT.md has a '### Behavioral Contract "
        "Findings' section — no SKIP should be emitted. "
        f"Got {len(skip_results)} SKIP: {[r.findings for r in skip_results]!r}"
    )


def test_real_verification_report_all_tags_clean():
    """The real VERIFICATION_REPORT.md contains no BC violation tags (PASS-only corpus)."""
    assert _REAL_REPORT_PATH.exists(), (
        f"Real VERIFICATION_REPORT.md not found at {_REAL_REPORT_PATH}."
    )

    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    report_content = _REAL_REPORT_PATH.read_text(encoding="utf-8")
    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[(str(_REAL_REPORT_PATH.relative_to(_CANONICAL_REPO)), report_content)]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    mechanical_results = [r for r in results if r.check_kind == "mechanical"]
    warn_or_fail = [r for r in mechanical_results if r.verdict in ("WARN", "FAIL")]
    assert len(warn_or_fail) == 0, (
        "The real PASS-case VERIFICATION_REPORT.md must produce no WARN/FAIL on tag scans; "
        f"violations: {[(r.check_name, r.verdict, r.findings) for r in warn_or_fail]!r}"
    )


def test_real_verification_report_produces_four_llm_slots():
    """The real VERIFICATION_REPORT.md causes Family 2 to queue 4 LLM judgment slots
    (FakeJudgeClient intercepts; no real API calls)."""
    assert _REAL_REPORT_PATH.exists(), (
        f"Real VERIFICATION_REPORT.md not found at {_REAL_REPORT_PATH}."
    )

    from praxion_evals.harness.families.family2_bc_adherence import (
        Family2BehavioralContractAdherence,
    )

    report_content = _REAL_REPORT_PATH.read_text(encoding="utf-8")
    family = Family2BehavioralContractAdherence()
    corpus = _make_corpus(
        verification_reports=[(str(_REAL_REPORT_PATH.relative_to(_CANONICAL_REPO)), report_content)]
    )
    fake_judge = FakeJudgeClient(verdict="PASS", findings=("no violations",), score=98)

    results = family.run(corpus, fake_judge)

    llm_results = [r for r in results if r.check_kind == "llm"]
    assert len(llm_results) == 4, (
        f"Family 2 must produce exactly 4 LLM checks for the real report; "
        f"got {len(llm_results)}: {[r.check_name for r in llm_results]!r}"
    )
    # The real report is a PASS-case; all 4 LLM checks should return PASS
    for r in llm_results:
        assert r.verdict == "PASS", (
            f"LLM check {r.check_name!r} must be PASS for the real PASS-case report; "
            f"got {r.verdict!r}"
        )
