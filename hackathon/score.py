"""Deterministic scorer for hackathon code-review skill evaluation.

Compares a list of findings against a single ground-truth dict per PR and
returns a 4-tuple: (success_score, feedback, error_type, error_message).

Scoring rules:
  1.0 — finding overlaps the ground-truth line range, its evidence/rule text
        contains at least one ground-truth defect-class keyword (case-insensitive),
        AND severity is "FAIL".
  0.5 — finding overlaps the line range BUT defect-class keyword is absent
        OR severity is "WARN" (weak evidence).
  0.0 — no finding overlaps the ground-truth file + line range at all.

Multi-finding: iterate all findings and return the best (highest) score.
"""

from __future__ import annotations

SCORE_TO_FEEDBACK: dict[float, float] = {1.0: 1.0, 0.5: 0.0, 0.0: -1.0}
SCORE_TO_ERROR_TYPE: dict[float, str] = {
    1.0: "",
    0.5: "weak_evidence",
    0.0: "missed_bug",
}


def _keyword_matches(finding: dict, defect_class: str) -> bool:
    """Return True if any comma-separated keyword in defect_class appears
    (case-insensitive) in the concatenation of finding evidence and rule."""
    haystack = (finding.get("evidence", "") + " " + finding.get("rule", "")).lower()
    keywords = [kw.strip().lower() for kw in defect_class.split(",")]
    return any(kw in haystack for kw in keywords if kw)


def _line_overlaps(finding_line: int, line_range: list[int]) -> bool:
    """Return True when finding_line falls within [line_range[0], line_range[1]]
    inclusive on both ends."""
    return line_range[0] <= finding_line <= line_range[1]


def _score_single_finding(finding: dict, ground_truth: dict) -> float:
    """Return the score (1.0, 0.5, or 0.0) for a single finding."""
    if finding.get("file") != ground_truth["file"]:
        return 0.0

    finding_line = finding.get("line", -1)
    if not _line_overlaps(finding_line, ground_truth["line_range"]):
        return 0.0

    # File matches and line overlaps — check for full credit
    keyword_match = _keyword_matches(finding, ground_truth["defect_class"])
    severity_is_fail = finding.get("severity", "").upper() == "FAIL"

    if keyword_match and severity_is_fail:
        return 1.0
    return 0.5


def _build_error_message(success_score: float, ground_truth: dict) -> str:
    """Return a descriptive error message for the given score and ground truth."""
    expected_location = (
        f"{ground_truth['file']}:"
        f"{ground_truth['line_range'][0]}-{ground_truth['line_range'][1]}"
    )
    expected_class = ground_truth["defect_class"]

    if success_score == 1.0:
        return ""
    if success_score == 0.5:
        return (
            f"Weak evidence at {expected_location}: finding overlaps the line range "
            f"but did not satisfy both defect-class keyword match and FAIL severity. "
            f"Expected defect class: '{expected_class}'."
        )
    return (
        f"Missed bug: no finding overlaps {expected_location}. "
        f"Expected defect class: '{expected_class}'."
    )


def score(
    findings: list[dict],
    ground_truth: dict,
) -> tuple[float, float, str, str]:
    """Score a list of findings against a ground-truth defect descriptor.

    Parameters
    ----------
    findings:
        List of finding dicts, each containing at minimum:
        ``file``, ``line``, ``severity``, ``rule``, ``evidence``.
    ground_truth:
        Dict with keys ``file`` (str), ``line_range`` ([int, int]),
        and ``defect_class`` (comma-separated keyword string).

    Returns
    -------
    tuple of (success_score, feedback, error_type, error_message)
    """
    best_score: float = 0.0
    for finding in findings:
        candidate = _score_single_finding(finding, ground_truth)
        if candidate > best_score:
            best_score = candidate
        if best_score == 1.0:
            break  # cannot improve further

    feedback = SCORE_TO_FEEDBACK[best_score]
    error_type = SCORE_TO_ERROR_TYPE[best_score]
    error_message = _build_error_message(best_score, ground_truth)

    return best_score, feedback, error_type, error_message
