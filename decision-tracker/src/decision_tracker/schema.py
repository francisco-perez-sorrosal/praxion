"""Decision tracking schema — shared between agent writes and hook extraction."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusType = Literal["pending", "approved", "auto-approved", "documented", "rejected"]
CategoryType = Literal[
    "architectural", "behavioral", "implementation", "configuration", "calibration"
]
SourceType = Literal["agent", "hook"]
MadeByType = Literal["user", "agent"]
TierType = Literal["direct", "lightweight", "standard", "full", "spike"]


def generate_id() -> str:
    return f"dec-{uuid.uuid4().hex[:12]}"


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


class Decision(BaseModel):
    """A single decision entry in decisions.jsonl."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=generate_id)
    version: int = 1
    timestamp: str = Field(default_factory=now_utc)
    status: StatusType
    category: CategoryType
    question: str | None = None
    decision: str
    rationale: str | None = None
    alternatives: list[str] | None = None
    made_by: MadeByType
    agent_type: str | None = None
    confidence: float | None = None
    source: SourceType
    affected_files: list[str] | None = None
    affected_reqs: list[str] | None = None
    commit_sha: str | None = None
    branch: str | None = None
    session_id: str | None = None
    pipeline_tier: TierType | None = None
    supersedes: str | None = None
    rejection_reason: str | None = None
    user_note: str | None = None


class ExtractedDecision(BaseModel):
    """Decision candidate from Haiku extraction (hook path)."""

    model_config = ConfigDict(extra="forbid")

    question: str | None = None
    decision: str
    rationale: str | None = None
    alternatives: list[str] | None = None
    category: CategoryType
    made_by: MadeByType
    confidence: float
    affected_files: list[str] | None = None
    spec_relevant: bool = True


class PendingDecisions(BaseModel):
    """Wrapper for .pending_decisions.json — decisions awaiting user review."""

    model_config = ConfigDict(extra="forbid")

    tier: TierType
    session_id: str | None = None
    decisions: list[Decision]


class HookOutput(BaseModel):
    """Structured stderr output from the hook to the agent."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["review_required", "auto_logged", "no_decisions", "error", "skipped"]
    count: int = 0
    tier: TierType | None = None
    decisions: list[dict] | None = None
    message: str
