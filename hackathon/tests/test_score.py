"""Behavioral tests for hackathon/score.py — deterministic scorer.

ASSUMPTION CONTRACT (surfaced before implementer writes score.py):

  score(findings: list[dict], ground_truth: dict) -> tuple[float, float, str, str]
    Returns: (success_score, feedback, error_type, error_message)

  ground_truth schema:
    {"file": str, "line_range": [int, int], "defect_class": str}
    defect_class is a comma-separated list of keywords
    e.g., "mutable default,shared state"

  A finding "overlaps" when finding["line"] is within
    ground_truth["line_range"][0] .. ground_truth["line_range"][1] INCLUSIVE.

  Defect-class keyword match: case-insensitive substring search of each
  comma-split keyword against evidence + " " + rule (concatenated).

  Score-to-feedback mapping:  {1.0: 1.0, 0.5: 0.0, 0.0: -1.0}
  Error-type mapping:         {1.0: "",  0.5: "weak_evidence", 0.0: "missed_bug"}

  1.0 path: finding overlaps AND defect_class keyword matches in evidence/rule
  0.5 path: line overlaps BUT defect_class keyword is absent OR severity is WARN
             (The plan says "WARN instead of FAIL" for 0.5; we test both sub-cases.)
  0.0 path: no finding overlaps ground-truth line range

  Multiple findings: if ANY finding scores 1.0, the whole result is 1.0
  (the matching finding wins — we pick the best outcome across all findings).

All imports are DEFERRED into each test body so pytest collection succeeds
even before score.py exists (BDD/TDD RED handshake protocol).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers / shared test data
# ---------------------------------------------------------------------------

# Ground truth for the events.py mutable-default scenario
GROUND_TRUTH_EVENTS = {
    "file": "events.py",
    "line_range": [10, 20],
    "defect_class": "mutable default,shared state",
}

# Ground truth for the cache.py scenario (Round 2)
GROUND_TRUTH_CACHE = {
    "file": "cache.py",
    "line_range": [18, 28],
    "defect_class": "mutable default,shared state",
}


def _finding(
    *,
    severity: str = "FAIL",
    file: str = "events.py",
    line: int = 14,
    rule: str = "Immutability — mutable default argument",
    evidence: str = "append_event uses mutable default history=[]",
) -> dict:
    """Build a finding dict matching the Finding model's expected field names."""
    return {
        "severity": severity,
        "file": file,
        "line": line,
        "rule": rule,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# 1.0 path — finding overlaps AND defect_class keyword matches
# ---------------------------------------------------------------------------


class TestScoreReturnsFullCreditOnExactMatch:
    def test_single_fail_finding_at_ground_truth_line_returns_1_0(self):
        from hackathon.score import score

        findings = [_finding(line=14, severity="FAIL")]
        success_score, feedback, error_type, error_message = score(
            findings, GROUND_TRUTH_EVENTS
        )

        assert success_score == 1.0
        assert feedback == 1.0
        assert error_type == ""

    def test_finding_at_range_start_returns_1_0(self):
        # line == range start (10) is inclusive — must still score 1.0
        from hackathon.score import score

        findings = [_finding(line=10, severity="FAIL")]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 1.0
        assert feedback == 1.0
        assert error_type == ""

    def test_finding_at_range_end_returns_1_0(self):
        # line == range end (20) is inclusive — must still score 1.0
        from hackathon.score import score

        findings = [_finding(line=20, severity="FAIL")]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 1.0
        assert feedback == 1.0
        assert error_type == ""

    def test_defect_class_keyword_match_is_case_insensitive(self):
        # "MUTABLE DEFAULT" in evidence should still match "mutable default" in ground truth
        from hackathon.score import score

        findings = [
            _finding(
                line=14,
                severity="FAIL",
                evidence="MUTABLE DEFAULT ARGUMENT — shared state detected",
                rule="Immutability",
            )
        ]
        success_score, _, _, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 1.0

    def test_keyword_match_on_second_comma_separated_keyword_returns_1_0(self):
        # "shared state" is the second keyword in "mutable default,shared state"
        from hackathon.score import score

        findings = [
            _finding(
                line=14,
                severity="FAIL",
                evidence="This is a shared state mutation problem",
                rule="Immutability",
            )
        ]
        success_score, _, _, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 1.0

    def test_round_2_cache_finding_returns_1_0(self):
        # Mirrors AC4: one FAIL at cache.py:22 with matching keyword
        from hackathon.score import score

        findings = [
            _finding(
                file="cache.py",
                line=22,
                severity="FAIL",
                evidence="cache_lookup uses mutable default seen=set() — shared state",
                rule="Immutability — mutable default",
            )
        ]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_CACHE)

        assert success_score == 1.0
        assert feedback == 1.0
        assert error_type == ""


# ---------------------------------------------------------------------------
# 0.5 path — overlap but defect class mismatch OR severity is WARN
# ---------------------------------------------------------------------------


class TestScoreReturnsPartialCreditOnWeakEvidence:
    def test_overlapping_finding_with_wrong_defect_class_returns_0_5(self):
        # File and line match, but evidence/rule don't name the defect class keywords
        from hackathon.score import score

        findings = [
            _finding(
                line=14,
                severity="FAIL",
                evidence="Function is too long",
                rule="Function size — over 30 lines",
            )
        ]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 0.5
        assert feedback == 0.0
        assert error_type == "weak_evidence"

    def test_overlapping_finding_with_warn_severity_returns_0_5(self):
        # Line overlaps and keyword matches, but severity is WARN not FAIL
        from hackathon.score import score

        findings = [
            _finding(
                line=14,
                severity="WARN",
                evidence="mutable default argument detected",
                rule="Immutability",
            )
        ]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 0.5
        assert feedback == 0.0
        assert error_type == "weak_evidence"

    def test_wrong_file_but_matching_line_and_keyword_returns_0_0(self):
        # File does not match — no overlap, so 0.0 not 0.5
        from hackathon.score import score

        findings = [
            _finding(
                file="other.py",
                line=14,
                severity="FAIL",
                evidence="mutable default argument",
                rule="Immutability",
            )
        ]
        success_score, _, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        # No file match means no overlap — even with correct keyword, result is 0.0
        assert success_score == 0.0
        assert error_type == "missed_bug"


# ---------------------------------------------------------------------------
# 0.0 path — no finding overlaps ground-truth location
# ---------------------------------------------------------------------------


class TestScoreReturnsZeroOnMiss:
    def test_empty_findings_list_returns_0_0(self):
        from hackathon.score import score

        success_score, feedback, error_type, error_message = score(
            [], GROUND_TRUTH_EVENTS
        )

        assert success_score == 0.0
        assert feedback == -1.0
        assert error_type == "missed_bug"
        assert isinstance(error_message, str)

    def test_finding_at_line_before_range_returns_0_0(self):
        # line 9 is just outside range [10, 20] — no overlap
        from hackathon.score import score

        findings = [_finding(line=9, severity="FAIL")]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 0.0
        assert feedback == -1.0
        assert error_type == "missed_bug"

    def test_finding_at_line_after_range_returns_0_0(self):
        # line 21 is just outside range [10, 20] — no overlap
        from hackathon.score import score

        findings = [_finding(line=21, severity="FAIL")]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 0.0
        assert feedback == -1.0
        assert error_type == "missed_bug"

    def test_finding_in_wrong_file_returns_0_0(self):
        from hackathon.score import score

        findings = [_finding(file="unrelated.py", line=14)]
        success_score, _, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 0.0
        assert error_type == "missed_bug"


# ---------------------------------------------------------------------------
# Boundary cases for line range (inclusive at both ends)
# ---------------------------------------------------------------------------


class TestScoreLineRangeBoundaries:
    def test_line_at_lower_boundary_is_inclusive(self):
        # line == range[0] must overlap
        from hackathon.score import score

        ground_truth = {
            "file": "x.py",
            "line_range": [12, 14],
            "defect_class": "mutable default",
        }
        findings = [
            _finding(
                file="x.py",
                line=12,
                severity="FAIL",
                evidence="mutable default found here",
                rule="Immutability",
            )
        ]
        success_score, _, _, _ = score(findings, ground_truth)
        assert success_score == 1.0

    def test_line_at_upper_boundary_is_inclusive(self):
        # line == range[1] must overlap
        from hackathon.score import score

        ground_truth = {
            "file": "x.py",
            "line_range": [12, 14],
            "defect_class": "mutable default",
        }
        findings = [
            _finding(
                file="x.py",
                line=14,
                severity="FAIL",
                evidence="mutable default found here",
                rule="Immutability",
            )
        ]
        success_score, _, _, _ = score(findings, ground_truth)
        assert success_score == 1.0

    def test_line_one_below_lower_boundary_does_not_overlap(self):
        # line == range[0] - 1 must NOT overlap
        from hackathon.score import score

        ground_truth = {
            "file": "x.py",
            "line_range": [12, 14],
            "defect_class": "mutable default",
        }
        findings = [
            _finding(
                file="x.py",
                line=11,
                severity="FAIL",
                evidence="mutable default",
                rule="Immutability",
            )
        ]
        success_score, _, _, _ = score(findings, ground_truth)
        assert success_score != 1.0

    def test_line_one_above_upper_boundary_does_not_overlap(self):
        # line == range[1] + 1 must NOT overlap
        from hackathon.score import score

        ground_truth = {
            "file": "x.py",
            "line_range": [12, 14],
            "defect_class": "mutable default",
        }
        findings = [
            _finding(
                file="x.py",
                line=15,
                severity="FAIL",
                evidence="mutable default",
                rule="Immutability",
            )
        ]
        success_score, _, _, _ = score(findings, ground_truth)
        assert success_score != 1.0

    def test_overlap_at_shared_boundary_line_12_to_14_vs_14_to_16(self):
        # Ground truth [12, 14], finding at line 14 — shares endpoint — overlaps
        from hackathon.score import score

        ground_truth = {
            "file": "x.py",
            "line_range": [12, 14],
            "defect_class": "mutable default",
        }
        findings = [
            _finding(
                file="x.py",
                line=14,
                severity="FAIL",
                evidence="mutable default",
                rule="Immutability",
            )
        ]
        success_score, _, _, _ = score(findings, ground_truth)
        assert success_score == 1.0


# ---------------------------------------------------------------------------
# Multiple findings: best result wins
# ---------------------------------------------------------------------------


class TestScoreMultipleFindings:
    def test_multiple_findings_one_matches_returns_1_0(self):
        # One finding misses, one hits — score should be 1.0 (the matching one wins)
        from hackathon.score import score

        findings = [
            _finding(
                line=5,
                severity="FAIL",
                evidence="wrong location",
                rule="Naming convention",
            ),
            _finding(
                line=14,
                severity="FAIL",
                evidence="mutable default argument — shared state",
                rule="Immutability",
            ),
        ]
        success_score, feedback, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 1.0
        assert feedback == 1.0
        assert error_type == ""

    def test_multiple_findings_none_match_returns_0_0(self):
        from hackathon.score import score

        findings = [
            _finding(line=1, severity="WARN", evidence="style issue", rule="Naming"),
            _finding(
                line=50, severity="FAIL", evidence="function too long", rule="Size"
            ),
        ]
        success_score, _, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 0.0
        assert error_type == "missed_bug"

    def test_multiple_findings_weak_and_miss_returns_0_5(self):
        # One finding at the right location but wrong keyword, one misses entirely
        from hackathon.score import score

        findings = [
            # right line, wrong defect class
            _finding(
                line=14, severity="FAIL", evidence="complexity", rule="Function size"
            ),
            # wrong line
            _finding(
                line=50,
                severity="FAIL",
                evidence="mutable default but wrong location",
                rule="Immutability",
            ),
        ]
        success_score, _, error_type, _ = score(findings, GROUND_TRUTH_EVENTS)

        assert success_score == 0.5
        assert error_type == "weak_evidence"


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------


class TestScoreReturnTypeContract:
    def test_score_returns_4_tuple(self):
        from hackathon.score import score

        result = score([], GROUND_TRUTH_EVENTS)
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_score_returns_float_for_success_score(self):
        from hackathon.score import score

        success_score, _, _, _ = score([], GROUND_TRUTH_EVENTS)
        assert isinstance(success_score, float)

    def test_score_returns_float_for_feedback(self):
        from hackathon.score import score

        _, feedback, _, _ = score([], GROUND_TRUTH_EVENTS)
        assert isinstance(feedback, float)

    def test_score_returns_str_for_error_type(self):
        from hackathon.score import score

        _, _, error_type, _ = score([], GROUND_TRUTH_EVENTS)
        assert isinstance(error_type, str)

    def test_score_returns_str_for_error_message(self):
        from hackathon.score import score

        _, _, _, error_message = score([], GROUND_TRUTH_EVENTS)
        assert isinstance(error_message, str)

    def test_score_has_no_side_effects_on_findings_list(self):
        # score() is a pure function — must not mutate the findings list
        from hackathon.score import score

        findings = [_finding(line=14)]
        original_length = len(findings)
        score(findings, GROUND_TRUTH_EVENTS)
        assert len(findings) == original_length
