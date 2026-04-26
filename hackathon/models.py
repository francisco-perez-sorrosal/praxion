"""Pydantic schemas shared across the hackathon pipeline.

These are dumb data containers — no business logic, no I/O, no env vars.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SkillRunEntry(BaseModel):
    """One Cognee record written after each review round."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    selected_skill_id: str
    task_text: str
    result_summary: str
    success_score: float  # 0.0, 0.5, or 1.0
    feedback: float  # -1.0, 0.0, or 1.0
    error_type: (
        str  # "missed_bug", "weak_evidence", "hallucinated_api", "agent_failed", ""
    )
    error_message: str


class Finding(BaseModel):
    """A single reviewer finding with location and evidence."""

    model_config = ConfigDict(extra="forbid")

    severity: str  # "FAIL", "WARN", or "PASS"
    file: str
    line: int
    rule: str
    evidence: str


class FindingsOutput(BaseModel):
    """Reviewer's structured output — list of zero or more findings."""

    model_config = ConfigDict(extra="forbid")

    findings: list[Finding]


class RewriteOutput(BaseModel):
    """Editor's structured output — one gotcha bullet for the skill."""

    model_config = ConfigDict(extra="forbid")

    gotcha_bullet: str


class FixOutput(BaseModel):
    """Fixer's structured output — a unified diff and a regression test."""

    model_config = ConfigDict(extra="forbid")

    patch_text: str
    test_text: str
