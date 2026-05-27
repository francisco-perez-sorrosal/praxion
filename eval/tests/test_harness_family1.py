"""Behavioral tests for Family 1 — Pipeline-outcome fidelity.

Tests cover every mechanical check and one mocked-LLM check. All production
imports are deferred inside each test body so pytest collection succeeds before
the family module exists (RED-state handshake).

FakeJudgeClient is defined at module scope so it is available to all tests
without importing the real JudgeClient ABC during collection.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal ADR and SPEC templates used to build synthetic test corpora
# ---------------------------------------------------------------------------

_FRONTMATTER_FULL = textwrap.dedent("""\
    ---
    id: dec-099
    title: Test ADR with all required fields
    status: accepted
    category: architectural
    date: "2026-01-01"
    summary: A complete ADR used as a positive fixture
    tags: [test]
    made_by: agent
    ---
""")

_FRONTMATTER_MISSING_TITLE = textwrap.dedent("""\
    ---
    id: dec-099
    status: accepted
    category: architectural
    date: "2026-01-01"
    summary: Missing title field
    tags: [test]
    made_by: agent
    ---
""")

_FRONTMATTER_MISSING_MADE_BY = textwrap.dedent("""\
    ---
    id: dec-099
    title: Test ADR missing made_by
    status: accepted
    category: architectural
    date: "2026-01-01"
    summary: Missing made_by field
    tags: [test]
    ---
""")

_BODY_ALL_SECTIONS = textwrap.dedent("""\
    ## Context

    Background information about the decision.

    ## Decision

    The decision was made.

    ## Considered Options

    ### Option A

    - (+) Pro

    ### Option B

    - (-) Con

    ## Consequences

    Positive: works well.
""")

_BODY_MISSING_CONSIDERED_OPTIONS = textwrap.dedent("""\
    ## Context

    Background.

    ## Decision

    Made.

    ## Consequences

    Good outcome.
""")

_ADR_COMPLETE = _FRONTMATTER_FULL + "\n" + _BODY_ALL_SECTIONS

_SPEC_WITH_MATRIX = textwrap.dedent("""\
    # SPEC: Feature

    ## Acceptance Criteria

    - AC-1: The system does something.

    ## Traceability Matrix

    | AC | Implementing artifact | Verification |
    |----|----------------------|--------------|
    | AC-1 | module/file.py | pytest |
""")

_SPEC_WITHOUT_MATRIX = textwrap.dedent("""\
    # SPEC: Another Feature

    ## Acceptance Criteria

    - AC-1: The system does something else.

    No traceability section here.
""")

_DECISIONS_INDEX_CONSISTENT = textwrap.dedent("""\
    # Decisions Index

    | ID | Title | Status | Category | Date | Tags | Summary |
    |----|-------|--------|----------|------|------|---------|
    | dec-001 | First decision | accepted | architectural | 2026-01-01 | test | Summary one |
    | dec-002 | Second decision | accepted | architectural | 2026-02-01 | test | Summary two |
""")


# ---------------------------------------------------------------------------
# FakeJudgeClient — returns scripted verdicts; no SDK calls
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
# Helpers to build minimal Corpus objects
# ---------------------------------------------------------------------------


def _make_corpus(
    decisions: list[tuple[str, str]] | None = None,
    specs: list[tuple[str, str]] | None = None,
    verification_reports: list[tuple[str, str]] | None = None,
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
# ADR frontmatter completeness checks
# ---------------------------------------------------------------------------


def test_frontmatter_all_required_fields_passes():
    """An ADR with all required frontmatter fields produces a PASS CheckResult."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/099-test.md", _ADR_COMPLETE)])
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    frontmatter_results = [r for r in results if r.check_name == "adr_frontmatter_completeness"]
    assert any(r.verdict == "PASS" for r in frontmatter_results), (
        "ADR with all required fields must produce at least one PASS for frontmatter check"
    )


def test_frontmatter_missing_title_fails():
    """An ADR missing the 'title' field produces a FAIL CheckResult."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    adr_content = _FRONTMATTER_MISSING_TITLE + "\n" + _BODY_ALL_SECTIONS
    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/099-test.md", adr_content)])
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    frontmatter_results = [r for r in results if r.check_name == "adr_frontmatter_completeness"]
    assert any(r.verdict == "FAIL" for r in frontmatter_results), (
        "ADR missing 'title' must produce a FAIL for frontmatter completeness"
    )


def test_frontmatter_missing_made_by_fails():
    """An ADR missing the 'made_by' field produces a FAIL CheckResult."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    adr_content = _FRONTMATTER_MISSING_MADE_BY + "\n" + _BODY_ALL_SECTIONS
    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/099-test.md", adr_content)])
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    frontmatter_results = [r for r in results if r.check_name == "adr_frontmatter_completeness"]
    assert any(r.verdict == "FAIL" for r in frontmatter_results), (
        "ADR missing 'made_by' must produce a FAIL for frontmatter completeness"
    )


# ---------------------------------------------------------------------------
# Body section presence checks
# ---------------------------------------------------------------------------


def test_body_all_four_sections_passes():
    """An ADR with all 4 required body sections produces a PASS CheckResult."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/099-test.md", _ADR_COMPLETE)])
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    section_results = [r for r in results if r.check_name == "adr_body_sections"]
    assert any(r.verdict == "PASS" for r in section_results), (
        "ADR with Context/Decision/Considered Options/Consequences must PASS body sections check"
    )


def test_body_missing_considered_options_fails():
    """An ADR without '## Considered Options' produces a FAIL CheckResult."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    adr_content = _FRONTMATTER_FULL + "\n" + _BODY_MISSING_CONSIDERED_OPTIONS
    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/099-test.md", adr_content)])
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    section_results = [r for r in results if r.check_name == "adr_body_sections"]
    assert any(r.verdict == "FAIL" for r in section_results), (
        "ADR missing '## Considered Options' must FAIL the body sections check"
    )


# ---------------------------------------------------------------------------
# Supersession reciprocity checks
# ---------------------------------------------------------------------------


def test_supersession_symmetric_links_passes():
    """Mutually linked supersedes/superseded_by ADRs produce a PASS."""
    adr_a = textwrap.dedent("""\
        ---
        id: dec-010
        title: Old decision
        status: superseded
        category: architectural
        date: "2026-01-01"
        summary: Was superseded
        tags: [test]
        made_by: agent
        superseded_by: dec-011
        ---

        ## Context

        Old context.

        ## Decision

        Old decision.

        ## Considered Options

        ### Option A

        Done.

        ## Consequences

        Superseded.
    """)
    adr_b = textwrap.dedent("""\
        ---
        id: dec-011
        title: New decision
        status: accepted
        category: architectural
        date: "2026-02-01"
        summary: Supersedes dec-010
        tags: [test]
        made_by: agent
        supersedes: dec-010
        ---

        ## Context

        New context.

        ## Decision

        New decision.

        ## Considered Options

        ### Option A

        Better.

        ## Consequences

        Improved.

        ## Prior Decision

        dec-010 was superseded because of new evidence.
    """)
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[
            (".ai-state/decisions/010-old.md", adr_a),
            (".ai-state/decisions/011-new.md", adr_b),
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    reciprocity_results = [r for r in results if r.check_name == "supersession_reciprocity"]
    assert any(r.verdict == "PASS" for r in reciprocity_results), (
        "Symmetric supersedes/superseded_by pair must produce PASS for supersession reciprocity"
    )


def test_supersession_missing_superseded_by_fails():
    """An ADR declaring 'supersedes' but the target lacking 'superseded_by' produces FAIL."""
    adr_a_incomplete = textwrap.dedent("""\
        ---
        id: dec-010
        title: Old decision without back-link
        status: accepted
        category: architectural
        date: "2026-01-01"
        summary: Missing superseded_by back-reference
        tags: [test]
        made_by: agent
        ---

        ## Context

        Missing the superseded_by field.

        ## Decision

        Decided.

        ## Considered Options

        ### Option A

        One option.

        ## Consequences

        Some outcome.
    """)
    adr_b = textwrap.dedent("""\
        ---
        id: dec-011
        title: Decision that claims to supersede dec-010
        status: accepted
        category: architectural
        date: "2026-02-01"
        summary: Supersedes dec-010 but dec-010 has no back-link
        tags: [test]
        made_by: agent
        supersedes: dec-010
        ---

        ## Context

        Claims to supersede.

        ## Decision

        Supersedes.

        ## Considered Options

        ### Option A

        Better.

        ## Consequences

        Updated.

        ## Prior Decision

        dec-010 replaced.
    """)
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[
            (".ai-state/decisions/010-old.md", adr_a_incomplete),
            (".ai-state/decisions/011-new.md", adr_b),
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    reciprocity_results = [r for r in results if r.check_name == "supersession_reciprocity"]
    assert any(r.verdict == "FAIL" for r in reciprocity_results), (
        "A supersedes link without the matching superseded_by must FAIL reciprocity check"
    )


# ---------------------------------------------------------------------------
# Re-affirmation reciprocity checks
# ---------------------------------------------------------------------------


def test_re_affirmation_symmetric_links_passes():
    """Mutually linked re_affirms/re_affirmed_by ADRs produce a PASS."""
    adr_original = textwrap.dedent("""\
        ---
        id: dec-022
        title: Original decision that was re-affirmed
        status: accepted
        category: architectural
        date: "2026-01-01"
        summary: Original decision
        tags: [test]
        made_by: agent
        re_affirmed_by: [dec-049]
        ---

        ## Context

        Original context.

        ## Decision

        Original.

        ## Considered Options

        ### Option A

        The one.

        ## Consequences

        Good.
    """)
    adr_reaffirm = textwrap.dedent("""\
        ---
        id: dec-049
        title: Re-affirmation of dec-022
        status: re-affirmation
        category: architectural
        date: "2026-02-01"
        summary: Re-affirms dec-022
        tags: [test]
        made_by: agent
        re_affirms: dec-022
        ---

        ## Context

        Re-examined and confirmed.

        ## Decision

        Re-affirmed.

        ## Considered Options

        ### Reconsider Option A

        Still the best.

        ## Consequences

        Confirmed.

        ## Prior Decision

        dec-022 still holds.
    """)
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[
            (".ai-state/decisions/022-original.md", adr_original),
            (".ai-state/decisions/049-reaffirm.md", adr_reaffirm),
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    reciprocity_results = [r for r in results if r.check_name == "re_affirmation_reciprocity"]
    assert any(r.verdict == "PASS" for r in reciprocity_results), (
        "Symmetric re_affirms/re_affirmed_by pair must produce PASS for re-affirmation reciprocity"
    )


def test_re_affirmation_missing_back_link_fails():
    """A re_affirms link without the matching re_affirmed_by entry produces FAIL."""
    adr_original_no_backlink = textwrap.dedent("""\
        ---
        id: dec-022
        title: Original decision without back-link
        status: accepted
        category: architectural
        date: "2026-01-01"
        summary: Original decision; missing re_affirmed_by
        tags: [test]
        made_by: agent
        ---

        ## Context

        No re_affirmed_by set.

        ## Decision

        Original.

        ## Considered Options

        ### Option A

        One option.

        ## Consequences

        Good outcome.
    """)
    adr_reaffirm = textwrap.dedent("""\
        ---
        id: dec-049
        title: Re-affirmation without back-link on target
        status: re-affirmation
        category: architectural
        date: "2026-02-01"
        summary: Claims to re-affirm dec-022 but dec-022 lacks re_affirmed_by
        tags: [test]
        made_by: agent
        re_affirms: dec-022
        ---

        ## Context

        Re-examined.

        ## Decision

        Re-affirmed.

        ## Considered Options

        ### Option A

        Still good.

        ## Consequences

        Confirmed.

        ## Prior Decision

        dec-022 still stands.
    """)
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[
            (".ai-state/decisions/022-original.md", adr_original_no_backlink),
            (".ai-state/decisions/049-reaffirm.md", adr_reaffirm),
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    reciprocity_results = [r for r in results if r.check_name == "re_affirmation_reciprocity"]
    assert any(r.verdict == "FAIL" for r in reciprocity_results), (
        "A re_affirms link without the matching re_affirmed_by must FAIL reciprocity check"
    )


# ---------------------------------------------------------------------------
# SPEC traceability matrix presence checks
# ---------------------------------------------------------------------------


def test_spec_with_traceability_matrix_passes():
    """A SPEC containing a traceability matrix produces a PASS CheckResult."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(specs=[(".ai-state/specs/SPEC_feature_2026-01-01.md", _SPEC_WITH_MATRIX)])
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    traceability_results = [r for r in results if r.check_name == "spec_traceability_presence"]
    assert any(r.verdict == "PASS" for r in traceability_results), (
        "SPEC with a Traceability Matrix section must PASS the traceability presence check"
    )


def test_spec_without_traceability_matrix_fails():
    """A SPEC lacking a traceability matrix produces a FAIL CheckResult."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        specs=[(".ai-state/specs/SPEC_feature_2026-01-01.md", _SPEC_WITHOUT_MATRIX)]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    traceability_results = [r for r in results if r.check_name == "spec_traceability_presence"]
    assert any(r.verdict == "FAIL" for r in traceability_results), (
        "SPEC without a Traceability Matrix section must FAIL the traceability presence check"
    )


# ---------------------------------------------------------------------------
# affected_reqs resolvability checks
# ---------------------------------------------------------------------------


def test_affected_reqs_found_in_spec_passes():
    """An ADR's affected_reqs entry that appears in a SPEC produces a PASS result."""
    adr_with_reqs = textwrap.dedent("""\
        ---
        id: dec-002
        title: ADR with populated affected_reqs
        status: accepted
        category: architectural
        date: "2026-01-01"
        summary: Has REQ-10 in affected_reqs
        tags: [test]
        made_by: agent
        affected_reqs: ["REQ-10"]
        ---

        ## Context

        Context.

        ## Decision

        Decided.

        ## Considered Options

        ### Option A

        Good.

        ## Consequences

        Good outcome.
    """)
    spec_with_req = textwrap.dedent("""\
        # SPEC: Observability

        ## Acceptance Criteria

        - REQ-10: The system emits telemetry.

        ## Traceability Matrix

        | AC | Implementing artifact | Verification |
        |----|----------------------|--------------|
        | REQ-10 | hooks/telemetry.py | manual |
    """)
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[(".ai-state/decisions/002-test.md", adr_with_reqs)],
        specs=[(".ai-state/specs/SPEC_obs_2026-01-01.md", spec_with_req)],
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    reqs_results = [r for r in results if r.check_name == "affected_reqs_resolvability"]
    assert any(r.verdict in ("PASS", "WARN") for r in reqs_results), (
        "ADR with affected_reqs populated must produce a verdict for resolvability check"
    )
    assert any(r.verdict == "PASS" for r in reqs_results), (
        "When the REQ ID appears in a SPEC, the resolvability check must PASS"
    )


def test_affected_reqs_not_in_any_spec_warns():
    """An ADR's affected_reqs entry absent from all SPECs produces a WARN (not FAIL)."""
    adr_with_missing_req = textwrap.dedent("""\
        ---
        id: dec-002
        title: ADR with unresolvable affected_reqs
        status: accepted
        category: architectural
        date: "2026-01-01"
        summary: Has REQ-999 which appears in no SPEC
        tags: [test]
        made_by: agent
        affected_reqs: ["REQ-999"]
        ---

        ## Context

        Context.

        ## Decision

        Decided.

        ## Considered Options

        ### Option A

        Good.

        ## Consequences

        Good outcome.
    """)
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[(".ai-state/decisions/002-test.md", adr_with_missing_req)],
        specs=[(".ai-state/specs/SPEC_feature_2026-01-01.md", _SPEC_WITH_MATRIX)],
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    reqs_results = [r for r in results if r.check_name == "affected_reqs_resolvability"]
    assert any(r.verdict == "WARN" for r in reqs_results), (
        "An affected_reqs entry not found in any SPEC must produce WARN (not FAIL) per spec"
    )
    # The spec says WARN, not FAIL — verify no FAIL is emitted for an unresolvable link
    assert not any(r.verdict == "FAIL" for r in reqs_results), (
        "An unresolvable affected_reqs entry must not produce FAIL — WARN is the correct signal"
    )


# ---------------------------------------------------------------------------
# DECISIONS_INDEX consistency check
# ---------------------------------------------------------------------------


def test_decisions_index_row_count_matches_adr_count_passes():
    """When index row count equals number of ADR files, the consistency check passes."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    # Build a corpus with exactly 2 ADRs and an index with 2 rows (consistent)
    adr_001 = (
        _FRONTMATTER_FULL.replace("dec-099", "dec-001").replace(
            "Test ADR with all required fields", "First ADR"
        )
        + "\n"
        + _BODY_ALL_SECTIONS
    )
    adr_002 = (
        _FRONTMATTER_FULL.replace("dec-099", "dec-002").replace(
            "Test ADR with all required fields", "Second ADR"
        )
        + "\n"
        + _BODY_ALL_SECTIONS
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[
            (".ai-state/decisions/001-first.md", adr_001),
            (".ai-state/decisions/002-second.md", adr_002),
            (".ai-state/decisions/DECISIONS_INDEX.md", _DECISIONS_INDEX_CONSISTENT),
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    index_results = [r for r in results if r.check_name == "decisions_index_consistency"]
    assert any(r.verdict in ("PASS", "WARN") for r in index_results), (
        "DECISIONS_INDEX consistency check must produce a verdict"
    )
    assert any(r.verdict == "PASS" for r in index_results), (
        "Index row count matching ADR file count must PASS the consistency check"
    )


def test_decisions_index_row_count_mismatch_warns():
    """When index row count differs from ADR file count, the consistency check emits WARN."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    # 3 ADR files but only 2 rows in the index → mismatch
    adr_001 = _FRONTMATTER_FULL.replace("dec-099", "dec-001") + "\n" + _BODY_ALL_SECTIONS
    adr_002 = _FRONTMATTER_FULL.replace("dec-099", "dec-002") + "\n" + _BODY_ALL_SECTIONS
    adr_003 = _FRONTMATTER_FULL.replace("dec-099", "dec-003") + "\n" + _BODY_ALL_SECTIONS

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[
            (".ai-state/decisions/001-first.md", adr_001),
            (".ai-state/decisions/002-second.md", adr_002),
            (".ai-state/decisions/003-third.md", adr_003),
            # Index only has 2 rows (inconsistent with 3 ADR files)
            (".ai-state/decisions/DECISIONS_INDEX.md", _DECISIONS_INDEX_CONSISTENT),
        ]
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    index_results = [r for r in results if r.check_name == "decisions_index_consistency"]
    assert any(r.verdict == "WARN" for r in index_results), (
        "Index row count mismatch with ADR file count must produce WARN"
    )


# ---------------------------------------------------------------------------
# LLM-judged option-depth check (via FakeJudgeClient)
# ---------------------------------------------------------------------------


def test_option_depth_check_uses_judge_and_returns_llm_kind():
    """The option-depth check calls the judge and returns a CheckResult with check_kind='llm'."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    fake_judge = FakeJudgeClient(
        verdict="PASS", findings=("substantive options present",), score=85
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/001-test.md", _ADR_COMPLETE)])

    results = family.run(corpus, fake_judge)

    llm_results = [r for r in results if r.check_kind == "llm"]
    assert len(llm_results) >= 1, "Family 1 must produce at least one LLM-judged CheckResult"

    option_depth = [
        r
        for r in llm_results
        if "option" in r.check_name.lower()
        or "depth" in r.check_name.lower()
        or "proportionality" in r.check_name.lower()
    ]
    assert len(option_depth) >= 1, (
        "At least one LLM check must relate to option substantiveness or proportionality"
    )

    for r in option_depth:
        assert r.verdict in ("PASS", "WARN", "FAIL"), (
            f"LLM CheckResult verdict must be PASS/WARN/FAIL; got {r.verdict!r}"
        )
        assert r.check_kind == "llm", (
            f"Option-depth check must have check_kind='llm'; got {r.check_kind!r}"
        )


def test_fake_judge_pass_verdict_propagates_to_check_result():
    """A FakeJudgeClient returning PASS produces CheckResult with verdict='PASS'."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    fake_judge = FakeJudgeClient(verdict="PASS", findings=("all good",), score=95)

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/001-test.md", _ADR_COMPLETE)])

    results = family.run(corpus, fake_judge)

    llm_results = [r for r in results if r.check_kind == "llm"]
    assert all(r.verdict == "PASS" for r in llm_results), (
        "All LLM checks must return PASS when FakeJudgeClient is scripted with PASS"
    )


# ---------------------------------------------------------------------------
# CheckResult schema enforcement
# ---------------------------------------------------------------------------


def test_all_check_results_have_valid_verdicts():
    """Every CheckResult from Family 1 has a verdict in the allowed set."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(
        decisions=[(".ai-state/decisions/001-test.md", _ADR_COMPLETE)],
        specs=[(".ai-state/specs/SPEC_feat_2026-01-01.md", _SPEC_WITH_MATRIX)],
    )
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    assert len(results) > 0, "Family 1 must produce at least one CheckResult"
    for result in results:
        assert result.verdict in ("PASS", "WARN", "FAIL", "SKIP"), (
            f"CheckResult verdict must be one of PASS/WARN/FAIL/SKIP; got {result.verdict!r}"
        )
        assert result.check_kind in ("mechanical", "llm", "skip"), (
            f"CheckResult check_kind must be mechanical/llm/skip; got {result.check_kind!r}"
        )
        assert result.check_name, "CheckResult must have a non-empty check_name"


def test_mechanical_check_results_have_negative_one_score():
    """Mechanical checks produce CheckResult with score=-1 (score N/A for non-LLM checks)."""
    from praxion_evals.harness.families.family1_pipeline_fidelity import (
        Family1PipelineOutcomeFidelity,
    )

    family = Family1PipelineOutcomeFidelity()
    corpus = _make_corpus(decisions=[(".ai-state/decisions/001-test.md", _ADR_COMPLETE)])
    fake_judge = FakeJudgeClient()

    results = family.run(corpus, fake_judge)

    mechanical_results = [r for r in results if r.check_kind == "mechanical"]
    assert len(mechanical_results) > 0, "Family 1 must produce at least one mechanical CheckResult"
    for r in mechanical_results:
        assert r.score == -1, (
            f"Mechanical CheckResult score must be -1 (not applicable); got {r.score}"
        )


# ---------------------------------------------------------------------------
# ReportWriter: produces file with ## Calibration Notes section
# ---------------------------------------------------------------------------


def test_report_writer_creates_file_at_expected_path(tmp_path: Path):
    """ReportWriter.write() creates a report file under the given output directory."""
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import CheckResult, Report

    corpus = _make_corpus()
    check_results = (
        CheckResult(
            check_name="adr_frontmatter_completeness",
            check_kind="mechanical",
            verdict="PASS",
            artifact_path=".ai-state/decisions/001-test.md",
            findings=("All required fields present",),
            score=-1,
        ),
    )
    report = Report(corpus=corpus, check_results=check_results, cost_usd_estimate=0.0)

    writer = ReportWriter(output_dir=tmp_path)
    written_path = writer.write(report)

    assert written_path, "ReportWriter.write() must return a non-empty path"
    assert Path(written_path).exists(), (
        f"Report file must exist at the returned path; {written_path!r} not found"
    )
    assert "PRAXION_EVAL_REPORT" in Path(written_path).name, (
        "Report filename must contain 'PRAXION_EVAL_REPORT'"
    )


def test_report_writer_output_contains_calibration_notes_section(tmp_path: Path):
    """The written report file contains a '## Calibration Notes' section."""
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import CheckResult, Report

    corpus = _make_corpus()
    check_results = (
        CheckResult(
            check_name="adr_frontmatter_completeness",
            check_kind="mechanical",
            verdict="PASS",
            artifact_path=".ai-state/decisions/001-test.md",
            findings=("All required fields present",),
            score=-1,
        ),
    )
    report = Report(corpus=corpus, check_results=check_results, cost_usd_estimate=0.0)

    writer = ReportWriter(output_dir=tmp_path)
    written_path = writer.write(report)

    content = Path(written_path).read_text(encoding="utf-8")
    assert "## Calibration Notes" in content, (
        "Report must contain a '## Calibration Notes' section per AC-6"
    )


def test_report_writer_log_appends_row_to_log_file(tmp_path: Path):
    """ReportWriter.append_log() creates or appends a row to PRAXION_EVAL_LOG.md."""
    from praxion_evals.harness.report_writer import ReportWriter
    from praxion_evals.harness.schemas import CheckResult, Report

    corpus = _make_corpus()
    check_results = (
        CheckResult(
            check_name="adr_frontmatter_completeness",
            check_kind="mechanical",
            verdict="PASS",
            artifact_path=".ai-state/decisions/001.md",
            findings=(),
            score=-1,
        ),
    )
    report = Report(corpus=corpus, check_results=check_results, cost_usd_estimate=0.0)

    writer = ReportWriter(output_dir=tmp_path)
    written_path = writer.write(report)
    writer.append_log(report, report_path=written_path)

    log_file = tmp_path / "PRAXION_EVAL_LOG.md"
    assert log_file.exists(), "ReportWriter.append_log() must create PRAXION_EVAL_LOG.md"
    log_content = log_file.read_text(encoding="utf-8")
    assert "|" in log_content, (
        "PRAXION_EVAL_LOG.md must contain a Markdown table row after append_log()"
    )


# ---------------------------------------------------------------------------
# AC-7 lint guard: family1 module must not import SDKs
# ---------------------------------------------------------------------------


def test_family1_module_source_contains_no_direct_sdk_imports():
    """Family1 source file must not contain direct claude_agent_sdk or anthropic imports.

    This is the behavioral encoding of AC-7: family code calls JudgeClient.judge()
    only; SDK imports belong exclusively in harness/judge_client.py.
    """
    import importlib
    import importlib.util

    spec = importlib.util.find_spec("praxion_evals.harness.families.family1_pipeline_fidelity")
    assert spec is not None, (
        "family1_pipeline_fidelity module must be importable after implementation"
    )
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
            f"Family1 source must not contain {pattern!r} — SDK imports belong in judge_client.py"
        )
