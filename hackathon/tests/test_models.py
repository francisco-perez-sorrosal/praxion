"""Behavioral tests for hackathon/models.py Pydantic schemas.

ASSUMPTION CONTRACT (surfaced before implementer writes models.py):

  SkillRunEntry:
    - 8 fields: run_id, selected_skill_id, task_text, result_summary,
                success_score, feedback, error_type, error_message
    - model_config = {"extra": "forbid"} — unknown fields raise ValidationError
    - success_score is one of {0.0, 0.5, 1.0} (float)
    - feedback is one of {-1.0, 0.0, 1.0} (float), set by caller not auto-derived

  FindingsOutput:
    - field: findings: list[Finding]
    - model_config = {"extra": "forbid"}
    - empty findings list is valid

  Finding (nested inside FindingsOutput):
    - 5 fields: severity (str), file (str), line (int), rule (str), evidence (str)
    - model_config = {"extra": "forbid"}
    - severity is one of {"FAIL", "WARN", "PASS"}

  RewriteOutput:
    - 1 field: gotcha_bullet (str)
    - model_config = {"extra": "forbid"}

  FixOutput:
    - 2 fields: patch_text (str), test_text (str)
    - model_config = {"extra": "forbid"}

All imports are DEFERRED into each test body so pytest collection succeeds
even before models.py exists (BDD/TDD RED handshake protocol).
"""

from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_skill_run_entry_data() -> dict:
    """Minimal valid data for SkillRunEntry (Round 1 miss scenario)."""
    return {
        "run_id": "praxion:r1:code-review",
        "selected_skill_id": "code-review@v1",
        "task_text": "Review PR-A: adds append_event() with history=[] default",
        "result_summary": "Reported 1 WARN on naming, 0 FAILs. Did not flag mutable default.",
        "success_score": 0.0,
        "feedback": -1.0,
        "error_type": "missed_bug",
        "error_message": "ground truth: events.py:14 mutable default argument; no FAIL emitted",
    }


@pytest.fixture()
def valid_finding_data() -> dict:
    """Minimal valid data for a single Finding (FAIL severity, explicit line)."""
    return {
        "severity": "FAIL",
        "file": "events.py",
        "line": 14,
        "rule": "Immutability — mutable default argument",
        "evidence": "append_event(payload, history=[]) — history is shared across all calls",
    }


@pytest.fixture()
def valid_findings_output_data(valid_finding_data) -> dict:
    """FindingsOutput with one finding."""
    return {"findings": [valid_finding_data]}


# ---------------------------------------------------------------------------
# SkillRunEntry tests
# ---------------------------------------------------------------------------


class TestSkillRunEntry:
    def test_valid_construction_with_all_fields(self, valid_skill_run_entry_data):
        from hackathon.models import SkillRunEntry

        entry = SkillRunEntry(**valid_skill_run_entry_data)

        assert entry.run_id == "praxion:r1:code-review"
        assert entry.selected_skill_id == "code-review@v1"
        assert entry.success_score == 0.0
        assert entry.feedback == -1.0
        assert entry.error_type == "missed_bug"

    def test_model_dump_json_produces_parseable_json(self, valid_skill_run_entry_data):
        from hackathon.models import SkillRunEntry

        entry = SkillRunEntry(**valid_skill_run_entry_data)
        json_str = entry.model_dump_json()

        parsed = json.loads(json_str)
        assert parsed["run_id"] == "praxion:r1:code-review"
        assert parsed["success_score"] == 0.0
        assert parsed["feedback"] == -1.0

    def test_round_trip_via_model_validate_json_is_lossless(
        self, valid_skill_run_entry_data
    ):
        from hackathon.models import SkillRunEntry

        original = SkillRunEntry(**valid_skill_run_entry_data)
        json_str = original.model_dump_json()
        restored = SkillRunEntry.model_validate_json(json_str)

        assert restored.run_id == original.run_id
        assert restored.selected_skill_id == original.selected_skill_id
        assert restored.task_text == original.task_text
        assert restored.result_summary == original.result_summary
        assert restored.success_score == original.success_score
        assert restored.feedback == original.feedback
        assert restored.error_type == original.error_type
        assert restored.error_message == original.error_message

    def test_unknown_field_raises_validation_error(self, valid_skill_run_entry_data):
        from pydantic import ValidationError

        from hackathon.models import SkillRunEntry

        data = {**valid_skill_run_entry_data, "unexpected_field": "should fail"}
        with pytest.raises(ValidationError):
            SkillRunEntry(**data)

    def test_success_score_zero_is_valid(self, valid_skill_run_entry_data):
        from hackathon.models import SkillRunEntry

        data = {**valid_skill_run_entry_data, "success_score": 0.0, "feedback": -1.0}
        entry = SkillRunEntry(**data)
        assert entry.success_score == 0.0

    def test_success_score_half_is_valid(self, valid_skill_run_entry_data):
        from hackathon.models import SkillRunEntry

        data = {
            **valid_skill_run_entry_data,
            "success_score": 0.5,
            "feedback": 0.0,
            "error_type": "weak_evidence",
            "error_message": "",
        }
        entry = SkillRunEntry(**data)
        assert entry.success_score == 0.5

    def test_success_score_one_is_valid(self, valid_skill_run_entry_data):
        from hackathon.models import SkillRunEntry

        data = {
            **valid_skill_run_entry_data,
            "success_score": 1.0,
            "feedback": 1.0,
            "error_type": "",
            "error_message": "",
        }
        entry = SkillRunEntry(**data)
        assert entry.success_score == 1.0

    def test_feedback_negative_one_accepted(self, valid_skill_run_entry_data):
        from hackathon.models import SkillRunEntry

        data = {**valid_skill_run_entry_data, "feedback": -1.0}
        entry = SkillRunEntry(**data)
        assert entry.feedback == -1.0

    def test_round_2_success_entry_construction(self):
        from hackathon.models import SkillRunEntry

        entry = SkillRunEntry(
            run_id="praxion:r2:code-review",
            selected_skill_id="code-review@v2",
            task_text="Review PR-B: adds cache_lookup() with seen=set() default",
            result_summary="Reported 1 FAIL at cache.py:22: mutable default set().",
            success_score=1.0,
            feedback=1.0,
            error_type="",
            error_message="",
        )
        assert entry.success_score == 1.0
        assert entry.error_type == ""


# ---------------------------------------------------------------------------
# FindingsOutput tests
# ---------------------------------------------------------------------------


class TestFindingsOutput:
    def test_valid_construction_with_one_finding(self, valid_findings_output_data):
        from hackathon.models import FindingsOutput

        output = FindingsOutput(**valid_findings_output_data)
        assert len(output.findings) == 1
        assert output.findings[0].severity == "FAIL"
        assert output.findings[0].file == "events.py"
        assert output.findings[0].line == 14

    def test_empty_findings_list_is_valid(self):
        from hackathon.models import FindingsOutput

        output = FindingsOutput(findings=[])
        assert output.findings == []

    def test_finding_severity_fail_accepted(self, valid_finding_data):
        from hackathon.models import FindingsOutput

        output = FindingsOutput(findings=[{**valid_finding_data, "severity": "FAIL"}])
        assert output.findings[0].severity == "FAIL"

    def test_finding_severity_warn_accepted(self, valid_finding_data):
        from hackathon.models import FindingsOutput

        output = FindingsOutput(findings=[{**valid_finding_data, "severity": "WARN"}])
        assert output.findings[0].severity == "WARN"

    def test_finding_severity_pass_accepted(self, valid_finding_data):
        from hackathon.models import FindingsOutput

        output = FindingsOutput(findings=[{**valid_finding_data, "severity": "PASS"}])
        assert output.findings[0].severity == "PASS"

    def test_finding_line_is_int(self, valid_finding_data):
        from hackathon.models import FindingsOutput

        output = FindingsOutput(findings=[valid_finding_data])
        assert isinstance(output.findings[0].line, int)

    def test_findings_output_unknown_field_raises_validation_error(
        self, valid_findings_output_data
    ):
        from pydantic import ValidationError

        from hackathon.models import FindingsOutput

        data = {**valid_findings_output_data, "surprise": "field"}
        with pytest.raises(ValidationError):
            FindingsOutput(**data)

    def test_multiple_findings_preserved_in_order(self, valid_finding_data):
        from hackathon.models import FindingsOutput

        finding_warn = {**valid_finding_data, "severity": "WARN", "line": 5}
        finding_fail = {**valid_finding_data, "severity": "FAIL", "line": 14}
        output = FindingsOutput(findings=[finding_warn, finding_fail])
        assert len(output.findings) == 2
        assert output.findings[0].severity == "WARN"
        assert output.findings[1].severity == "FAIL"

    def test_round_trip_json_preserves_findings(self, valid_findings_output_data):
        from hackathon.models import FindingsOutput

        original = FindingsOutput(**valid_findings_output_data)
        json_str = original.model_dump_json()
        restored = FindingsOutput.model_validate_json(json_str)
        assert len(restored.findings) == 1
        assert restored.findings[0].file == original.findings[0].file
        assert restored.findings[0].line == original.findings[0].line


# ---------------------------------------------------------------------------
# RewriteOutput tests
# ---------------------------------------------------------------------------


class TestRewriteOutput:
    def test_valid_construction_with_gotcha_bullet(self):
        from hackathon.models import RewriteOutput

        bullet = "- **Mutable default arguments**: In Python, `def f(x=[])` shares state across calls."
        output = RewriteOutput(gotcha_bullet=bullet)
        assert output.gotcha_bullet == bullet

    def test_empty_string_bullet_is_valid(self):
        from hackathon.models import RewriteOutput

        output = RewriteOutput(gotcha_bullet="")
        assert output.gotcha_bullet == ""

    def test_unknown_field_raises_validation_error(self):
        from pydantic import ValidationError

        from hackathon.models import RewriteOutput

        with pytest.raises(ValidationError):
            RewriteOutput(gotcha_bullet="valid", unexpected="field")

    def test_round_trip_json_preserves_gotcha_bullet(self):
        from hackathon.models import RewriteOutput

        bullet = "- **Test**: A bullet with `code` and newline\n  continuation."
        original = RewriteOutput(gotcha_bullet=bullet)
        restored = RewriteOutput.model_validate_json(original.model_dump_json())
        assert restored.gotcha_bullet == bullet


# ---------------------------------------------------------------------------
# FixOutput tests
# ---------------------------------------------------------------------------


class TestFixOutput:
    def test_valid_construction_with_patch_and_test(self):
        from hackathon.models import FixOutput

        output = FixOutput(
            patch_text="--- a/cache.py\n+++ b/cache.py\n@@ -22 +22 @@\n-def cache_lookup(key, seen=set()):\n+def cache_lookup(key, seen=None):\n+    if seen is None: seen = set()",
            test_text="import pytest\n\ndef test_cache_lookup_does_not_share_state():\n    from cache import cache_lookup\n    r1 = cache_lookup('a')\n    r2 = cache_lookup('b')\n    assert r1 is not r2\n",
        )
        assert "cache_lookup" in output.patch_text
        assert "def test_" in output.test_text

    def test_unknown_field_raises_validation_error(self):
        from pydantic import ValidationError

        from hackathon.models import FixOutput

        with pytest.raises(ValidationError):
            FixOutput(patch_text="diff", test_text="pytest", bogus="field")

    def test_round_trip_json_is_lossless(self):
        from hackathon.models import FixOutput

        original = FixOutput(
            patch_text="--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n",
            test_text="def test_x(): pass\n",
        )
        restored = FixOutput.model_validate_json(original.model_dump_json())
        assert restored.patch_text == original.patch_text
        assert restored.test_text == original.test_text

    def test_empty_strings_are_valid(self):
        from hackathon.models import FixOutput

        output = FixOutput(patch_text="", test_text="")
        assert output.patch_text == ""
        assert output.test_text == ""
