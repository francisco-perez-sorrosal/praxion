"""Tests for decision_tracker.schema — validates REQ-08 (schema structure)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from decision_tracker.schema import (
    Decision,
    ExtractedDecision,
    HookOutput,
    PendingDecisions,
    generate_id,
)


class TestGenerateId:
    def test_format(self):
        id_ = generate_id()
        assert id_.startswith("dec-")
        assert len(id_) == 16  # "dec-" + 12 hex chars

    def test_unique(self):
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100


class TestDecision:
    def test_minimal_required_fields(self):
        d = Decision(
            status="documented",
            category="implementation",
            decision="Use dict lookup",
            made_by="agent",
            source="agent",
        )
        assert d.id.startswith("dec-")
        assert d.version == 1
        assert d.timestamp  # auto-generated
        assert d.status == "documented"
        assert d.decision == "Use dict lookup"

    def test_all_fields(self):
        d = Decision(
            id="dec-test12345678",
            version=1,
            timestamp="2026-03-19T14:00:00+00:00",
            status="approved",
            category="architectural",
            question="What cache to use?",
            decision="Use Redis with 5-min TTL",
            rationale="Low latency + existing infra",
            alternatives=["Memcached", "In-process"],
            made_by="user",
            agent_type="systems-architect",
            confidence=0.87,
            source="hook",
            affected_files=["src/cache.py"],
            affected_reqs=["REQ-03"],
            commit_sha="abc1234",
            branch="feat/caching",
            session_id="sess-123",
            pipeline_tier="standard",
            supersedes="dec-oldone12345",
            rejection_reason=None,
            user_note="Good call",
        )
        assert d.question == "What cache to use?"
        assert d.alternatives == ["Memcached", "In-process"]
        assert d.pipeline_tier == "standard"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Decision(
                status="documented",
                category="implementation",
                # missing: decision, made_by, source
            )

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            Decision(
                status="invalid",
                category="implementation",
                decision="Test",
                made_by="agent",
                source="agent",
            )

    def test_pending_status_valid(self):
        d = Decision(
            status="pending",
            category="architectural",
            decision="Use Redis",
            made_by="agent",
            source="hook",
        )
        assert d.status == "pending"

    def test_invalid_category_raises(self):
        with pytest.raises(ValidationError):
            Decision(
                status="documented",
                category="unknown",
                decision="Test",
                made_by="agent",
                source="agent",
            )

    def test_invalid_source_raises(self):
        with pytest.raises(ValidationError):
            Decision(
                status="documented",
                category="implementation",
                decision="Test",
                made_by="agent",
                source="manual",
            )

    def test_invalid_made_by_raises(self):
        with pytest.raises(ValidationError):
            Decision(
                status="documented",
                category="implementation",
                decision="Test",
                made_by="bot",
                source="agent",
            )

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            Decision(
                status="documented",
                category="implementation",
                decision="Test",
                made_by="agent",
                source="agent",
                unknown_field="bad",
            )

    def test_json_roundtrip(self):
        d = Decision(
            status="documented",
            category="implementation",
            decision="Use dict lookup",
            made_by="agent",
            source="agent",
        )
        json_str = d.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["decision"] == "Use dict lookup"
        assert parsed["version"] == 1
        assert parsed["source"] == "agent"
        # Roundtrip back to model
        d2 = Decision.model_validate(parsed)
        assert d2.decision == d.decision

    def test_model_dump_excludes_none_optional(self):
        d = Decision(
            status="documented",
            category="implementation",
            decision="Test",
            made_by="agent",
            source="agent",
        )
        dumped = d.model_dump(mode="json", exclude_none=True)
        assert "question" not in dumped
        assert "rationale" not in dumped
        assert "alternatives" not in dumped
        assert "decision" in dumped

    def test_valid_tiers(self):
        for tier in ("direct", "lightweight", "standard", "full", "spike"):
            d = Decision(
                status="documented",
                category="implementation",
                decision="Test",
                made_by="agent",
                source="agent",
                pipeline_tier=tier,
            )
            assert d.pipeline_tier == tier

    def test_invalid_tier_raises(self):
        with pytest.raises(ValidationError):
            Decision(
                status="documented",
                category="implementation",
                decision="Test",
                made_by="agent",
                source="agent",
                pipeline_tier="mega",
            )


class TestExtractedDecision:
    def test_minimal(self):
        ed = ExtractedDecision(
            decision="Use Redis",
            category="architectural",
            made_by="agent",
            confidence=0.85,
        )
        assert ed.spec_relevant is True
        assert ed.question is None

    def test_full(self):
        ed = ExtractedDecision(
            question="What cache?",
            decision="Use Redis",
            rationale="Fast",
            alternatives=["Memcached"],
            category="architectural",
            made_by="user",
            confidence=0.92,
            affected_files=["src/cache.py"],
            spec_relevant=False,
        )
        assert ed.alternatives == ["Memcached"]
        assert ed.spec_relevant is False


class TestPendingDecisions:
    def test_wraps_decisions(self):
        d = Decision(
            status="approved",
            category="implementation",
            decision="Test",
            made_by="agent",
            source="hook",
        )
        pd = PendingDecisions(tier="standard", decisions=[d])
        assert len(pd.decisions) == 1
        assert pd.tier == "standard"


class TestHookOutput:
    def test_review_required(self):
        ho = HookOutput(
            status="review_required",
            count=2,
            tier="standard",
            decisions=[{"id": "dec-123", "decision": "Use Redis"}],
            message="2 decisions extracted. Review required.",
        )
        assert ho.count == 2
        assert ho.status == "review_required"

    def test_no_decisions(self):
        ho = HookOutput(status="no_decisions", message="No novel decisions found.")
        assert ho.count == 0

    def test_error(self):
        ho = HookOutput(status="error", message="API key missing.")
        assert ho.status == "error"
