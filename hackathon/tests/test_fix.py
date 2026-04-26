"""Tests for hackathon/fix.py — Fixer script.

Mix of unit tests (no API, no subprocess beyond import checks) and one
integration smoke test that requires ANTHROPIC_API_KEY.

Unit tests verify:
  - FixOutput schema round-trips correctly
  - FixOutput rejects unknown fields
  - propose_fix([]) with empty findings returns ("", "") — no LLM call, no output files
  - Findings with only WARN severity return ("", "") — Fixer only fixes FAIL-equivalent
  - Missing --findings file exits non-zero with stderr error message
  - Missing --diff file exits non-zero with stderr error message

Integration smoke (pytest.mark.integration):
  - propose_fix() with a stub FAIL finding against PR-B diff returns non-empty strings
  - main() CLI end-to-end: both artifact files are written to --out-dir
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WORKTREE_ROOT = Path(__file__).parent.parent.parent
FIX_PY = WORKTREE_ROOT / "hackathon" / "fix.py"

FIXTURES_DIR = WORKTREE_ROOT / "hackathon" / "fixtures"
PR_B_PATCH = FIXTURES_DIR / "pr_B.patch"

RULE_MD = WORKTREE_ROOT / "rules" / "swe" / "coding-style.md"


# ---------------------------------------------------------------------------
# Stub findings data — a single FAIL finding for PR-B's mutable-default defect.
# ---------------------------------------------------------------------------

_FAIL_FINDING = {
    "severity": "FAIL",
    "file": "cache.py",
    "line": 26,
    "rule": "Immutability — mutable default argument",
    "evidence": "cache_lookup(key, seen=set()) shares seen across all calls",
}

_WARN_FINDING = {
    "severity": "WARN",
    "file": "cache.py",
    "line": 26,
    "rule": "Immutability",
    "evidence": "seen=set() is a mutable default",
}

_STUB_FINDINGS_JSON = json.dumps({"findings": [_FAIL_FINDING]})

_WARN_ONLY_JSON = json.dumps({"findings": [_WARN_FINDING]})

_EMPTY_FINDINGS_JSON = json.dumps({"findings": []})


# ---------------------------------------------------------------------------
# Unit: FixOutput schema round-trips
# ---------------------------------------------------------------------------


class TestFixOutputSchema:
    def test_fix_output_round_trips_model_validate_json(self) -> None:
        """A FixOutput with both fields round-trips through model_validate_json()."""
        from hackathon.models import FixOutput

        original = FixOutput(
            patch_text="--- a/cache.py\n+++ b/cache.py\n@@ -26 +26 @@\n-def f(seen=set()):\n+def f(seen=None):\n",
            test_text="def test_not_shared():\n    assert f() == f()\n",
        )
        serialised = original.model_dump_json()
        recovered = FixOutput.model_validate_json(serialised)
        assert recovered.patch_text == original.patch_text
        assert recovered.test_text == original.test_text

    def test_fix_output_rejects_extra_fields(self) -> None:
        """FixOutput has extra='forbid' so unknown fields must raise ValidationError."""
        from pydantic import ValidationError

        from hackathon.models import FixOutput

        bad_json = json.dumps(
            {"patch_text": "diff", "test_text": "def test(): pass", "surprise": "boom"}
        )
        with pytest.raises(ValidationError):
            FixOutput.model_validate_json(bad_json)

    def test_fix_output_requires_both_fields(self) -> None:
        """FixOutput must have both patch_text and test_text — missing one raises."""
        from pydantic import ValidationError

        from hackathon.models import FixOutput

        with pytest.raises(ValidationError):
            FixOutput.model_validate_json(json.dumps({"patch_text": "diff"}))


# ---------------------------------------------------------------------------
# Unit: propose_fix() with empty or WARN-only findings — no LLM call.
# ---------------------------------------------------------------------------


class TestProposeFix:
    def test_empty_findings_returns_empty_strings(self) -> None:
        """propose_fix([]) must return ('', '') without making any LLM call.

        This is verified by running WITHOUT ANTHROPIC_API_KEY — if an LLM call
        were made it would raise an auth error, not return empty strings.
        """
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os, sys\n"
                    "sys.path.insert(0, '.')\n"
                    "from hackathon.fix import propose_fix\n"
                    "result = propose_fix([], 'diff text', 'rule text')\n"
                    "assert result == ('', ''), f'expected empty strings, got {result}'\n"
                    "print('ok')\n"
                ),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(WORKTREE_ROOT),
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for empty findings, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "ok" in result.stdout

    def test_warn_only_findings_returns_empty_strings(self) -> None:
        """propose_fix() with only WARN-severity findings returns ('', '').

        Fixer is only invoked after a successful FAIL catch. WARN findings are
        not severe enough to warrant a fix.
        """
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        warn_dict = json.dumps(_WARN_FINDING)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys, json\n"
                    "sys.path.insert(0, '.')\n"
                    f"warn = {warn_dict!r}\n"
                    "from hackathon.fix import propose_fix\n"
                    "result = propose_fix([json.loads(warn)], 'diff', 'rule')\n"
                    "assert result == ('', ''), f'expected empty strings, got {{result}}'\n"
                    "print('ok')\n"
                ),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(WORKTREE_ROOT),
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for WARN-only findings, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "ok" in result.stdout


# ---------------------------------------------------------------------------
# Unit: missing-file handling via CLI subprocess (no API call).
# ---------------------------------------------------------------------------


class TestMissingFileHandling:
    def test_missing_findings_file_exits_nonzero(self, tmp_path: Path) -> None:
        """--findings pointing to a nonexistent file must exit non-zero with stderr."""
        result = subprocess.run(
            [
                sys.executable,
                str(FIX_PY),
                "--findings",
                "/nonexistent/findings.json",
                "--diff",
                str(PR_B_PATCH),
                "--rule",
                str(RULE_MD),
                "--out-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_ROOT),
        )
        assert result.returncode != 0, (
            "Expected non-zero exit when --findings file is missing, "
            f"got returncode={result.returncode}"
        )
        error_output = result.stderr + result.stdout
        assert error_output.strip(), (
            "Expected a non-empty error message when --findings is missing"
        )

    def test_missing_diff_file_exits_nonzero_after_fail_finding(
        self, tmp_path: Path
    ) -> None:
        """--diff pointing to a nonexistent file exits non-zero (after a FAIL finding)."""
        findings_path = tmp_path / "findings.json"
        findings_path.write_text(_STUB_FINDINGS_JSON, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(FIX_PY),
                "--findings",
                str(findings_path),
                "--diff",
                "/nonexistent/pr.patch",
                "--rule",
                str(RULE_MD),
                "--out-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_ROOT),
        )
        assert result.returncode != 0, (
            "Expected non-zero exit when --diff file is missing, "
            f"got returncode={result.returncode}"
        )

    def test_empty_findings_exits_zero_without_api_call(self, tmp_path: Path) -> None:
        """Empty findings.json exits 0 printing 'No fix proposed', no LLM call."""
        findings_path = tmp_path / "findings.json"
        findings_path.write_text(_EMPTY_FINDINGS_JSON, encoding="utf-8")

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        result = subprocess.run(
            [
                sys.executable,
                str(FIX_PY),
                "--findings",
                str(findings_path),
                "--diff",
                str(PR_B_PATCH),
                "--rule",
                str(RULE_MD),
                "--out-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(WORKTREE_ROOT),
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for empty findings, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "No fix proposed" in result.stdout, (
            f"Expected 'No fix proposed' in stdout, got: {result.stdout!r}"
        )
        assert not (tmp_path / "proposed_fix.patch").exists(), (
            "proposed_fix.patch should not be written when there are no FAIL findings"
        )

    def test_warn_only_findings_exits_zero_without_api_call(
        self, tmp_path: Path
    ) -> None:
        """WARN-only findings.json exits 0 without making an LLM call."""
        findings_path = tmp_path / "findings.json"
        findings_path.write_text(_WARN_ONLY_JSON, encoding="utf-8")

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        result = subprocess.run(
            [
                sys.executable,
                str(FIX_PY),
                "--findings",
                str(findings_path),
                "--diff",
                str(PR_B_PATCH),
                "--rule",
                str(RULE_MD),
                "--out-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(WORKTREE_ROOT),
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for WARN-only findings, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        assert "No fix proposed" in result.stdout


# ---------------------------------------------------------------------------
# Integration smoke — requires ANTHROPIC_API_KEY.
# ---------------------------------------------------------------------------


class TestIntegrationSmoke:
    @pytest.mark.integration
    def test_propose_fix_returns_nonempty_strings_for_fail_finding(
        self, tmp_path: Path
    ) -> None:
        """propose_fix() with a FAIL finding against PR-B returns non-empty patch+test."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set — skipping integration test")

        from hackathon.fix import propose_fix

        diff_text = PR_B_PATCH.read_text(encoding="utf-8")
        rule_text = RULE_MD.read_text(encoding="utf-8")

        patch_text, test_text = propose_fix([_FAIL_FINDING], diff_text, rule_text)

        assert patch_text, "patch_text must be non-empty for a FAIL finding"
        assert test_text, "test_text must be non-empty for a FAIL finding"

    @pytest.mark.integration
    def test_cli_writes_both_artifacts_for_fail_finding(self, tmp_path: Path) -> None:
        """End-to-end CLI: both proposed_fix.patch and missing_test.py are written."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set — skipping integration test")

        findings_path = tmp_path / "findings.json"
        findings_path.write_text(_STUB_FINDINGS_JSON, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(FIX_PY),
                "--findings",
                str(findings_path),
                "--diff",
                str(PR_B_PATCH),
                "--rule",
                str(RULE_MD),
                "--out-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(WORKTREE_ROOT),
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        patch_path = tmp_path / "proposed_fix.patch"
        test_path = tmp_path / "missing_test.py"

        assert patch_path.exists(), "proposed_fix.patch was not written"
        assert test_path.exists(), "missing_test.py was not written"
        assert patch_path.stat().st_size > 0, "proposed_fix.patch is empty"
        assert test_path.stat().st_size > 0, "missing_test.py is empty"

        test_content = test_path.read_text(encoding="utf-8")
        assert "def test_" in test_content, (
            f"missing_test.py does not contain a pytest function.\n"
            f"Content: {test_content!r}"
        )

        patch_content = patch_path.read_text(encoding="utf-8")
        # A unified diff must have at least one hunk marker or header.
        # We check for the presence of diff-like content without being too strict
        # about the exact format since the LLM generates it.
        has_diff_content = any(
            line.startswith(("---", "+++", "@@", "+", "-"))
            for line in patch_content.splitlines()
        )
        assert has_diff_content, (
            f"proposed_fix.patch does not look like a unified diff.\n"
            f"Content: {patch_content!r}"
        )
