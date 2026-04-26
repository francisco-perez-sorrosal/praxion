"""Behavioral tests for hackathon/run_review.py — Reviewer script.

ASSUMPTION CONTRACT (surfaced before implementer writes run_review.py):

  CLI interface:
    --skill PATH   Path to SKILL.md file (required)
    --rule  PATH   Path to coding-style rule file (required)
    --diff  PATH   Path to PR unified diff (required)
    --out   PATH   Path where findings.json is written (required)

  Outputs (written to the directory containing --out):
    findings.json  — serialized FindingsOutput schema (always written on success)
    report.md      — human-readable markdown summary of findings

  Exit codes:
    0   — success (even if findings list is empty)
    1   — error (missing/unreadable input file, API failure, etc.)

  Empty diff behavior (ASSUMPTION: exit 0 with findings=[], no LLM call):
    When --diff points to a file that is empty (zero bytes), the script exits 0
    and writes findings.json with {"findings": []}. No Anthropic API call is made.
    Rationale: an empty diff has nothing to review. If the implementer makes a
    different choice (e.g., always calls the LLM), update this test to match and
    add a comment explaining the design decision.

  Schema strictness:
    findings.json must conform to FindingsOutput exactly.
    FindingsOutput has model_config extra="forbid", so unknown fields in the
    JSON response would fail model_validate_json().

DESIGN NOTE — subprocess-based tests:
  Unit tests invoke run_review.py via `subprocess.run([sys.executable,
  "hackathon/run_review.py", ...])`. They do NOT import from run_review.py
  directly. This decouples test collection from the script's import chain,
  ensuring pytest can collect and enumerate tests even before run_review.py
  exists — the RED handshake protocol for concurrent BDD/TDD execution.

CONCURRENT-MODE RED STATE:
  On first run, every test in this file should FAIL because run_review.py does
  not exist. The subprocess invocations return a non-zero exit code with stderr
  like "No such file or directory" or "can't open file". This is expected and
  the correct RED state. Tests will turn GREEN once the implementer delivers
  hackathon/run_review.py (S3.1).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Root of the worktree — all subprocess calls use paths relative to this.
WORKTREE_ROOT = Path(
    __file__
).parent.parent.parent  # .../hackathon-self-improving-skill/

# Path to the reviewer script (does not exist yet in RED state)
RUN_REVIEW_PY = WORKTREE_ROOT / "hackathon" / "run_review.py"

# Fixture paths (produced by S2.1, already on disk)
FIXTURES_DIR = WORKTREE_ROOT / "hackathon" / "fixtures"
PR_A_PATCH = FIXTURES_DIR / "pr_A.patch"

# Real skill + rule files in the repo (always present)
SKILL_MD = WORKTREE_ROOT / "skills" / "code-review" / "SKILL.md"
RULE_MD = WORKTREE_ROOT / "rules" / "swe" / "coding-style.md"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _skip_when_api_key_absent() -> None:
    """Skip integration tests cleanly when ANTHROPIC_API_KEY is not set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set — skipping integration test")


@pytest.fixture()
def run_review_args(tmp_path: Path) -> dict:
    """Common argument dict for subprocess invocations.

    Points --skill and --rule at real repo files; --diff at PR-A fixture;
    --out at a tmp_path location so each test run is isolated.
    """
    return {
        "skill": str(SKILL_MD),
        "rule": str(RULE_MD),
        "diff": str(PR_A_PATCH),
        "out": str(tmp_path / "findings.json"),
    }


def _build_cmd(args: dict) -> list[str]:
    """Build the subprocess command list from a dict of CLI args."""
    return [
        sys.executable,
        str(RUN_REVIEW_PY),
        "--skill",
        args["skill"],
        "--rule",
        args["rule"],
        "--diff",
        args["diff"],
        "--out",
        args["out"],
    ]


# ---------------------------------------------------------------------------
# Unit tests — CLI argument parsing
# ---------------------------------------------------------------------------


class TestCliArgParsing:
    def test_help_flag_exits_zero_and_lists_expected_flags(self) -> None:
        """--help should exit 0 and mention all required flags in its output."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(RUN_REVIEW_PY), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"--help exited {result.returncode}; stderr={result.stderr!r}"
        )
        help_text = result.stdout + result.stderr
        for flag in ("--skill", "--rule", "--diff", "--out"):
            assert flag in help_text, (
                f"Expected '{flag}' in --help output but did not find it.\n"
                f"help output was:\n{help_text}"
            )


# ---------------------------------------------------------------------------
# Unit tests — output schema parseability (no subprocess, no API)
# ---------------------------------------------------------------------------


class TestOutputSchemaParseability:
    def test_fabricated_findings_json_round_trips_through_findings_output(self) -> None:
        """A hand-crafted findings.json that matches the schema must round-trip
        through FindingsOutput.model_validate_json() without error."""
        from hackathon.models import FindingsOutput

        fabricated = {
            "findings": [
                {
                    "severity": "FAIL",
                    "file": "events.py",
                    "line": 24,
                    "rule": "Immutability — mutable default argument",
                    "evidence": "append_event(payload, history=[]) shares history across calls",
                }
            ]
        }
        json_str = json.dumps(fabricated)
        output = FindingsOutput.model_validate_json(json_str)
        assert len(output.findings) == 1
        assert output.findings[0].severity == "FAIL"
        assert output.findings[0].line == 24

    def test_empty_findings_list_is_valid_schema(self) -> None:
        """findings.json with an empty list is a valid FindingsOutput."""
        from hackathon.models import FindingsOutput

        json_str = json.dumps({"findings": []})
        output = FindingsOutput.model_validate_json(json_str)
        assert output.findings == []

    def test_findings_output_rejects_extra_fields(self) -> None:
        """FindingsOutput.model_config extra=forbid must reject unknown keys."""
        from pydantic import ValidationError

        from hackathon.models import FindingsOutput

        json_str = json.dumps({"findings": [], "surprise": "boom"})
        with pytest.raises(ValidationError):
            FindingsOutput.model_validate_json(json_str)

    def test_finding_rejects_extra_fields(self) -> None:
        """A Finding nested inside FindingsOutput must also reject extra fields."""
        from pydantic import ValidationError

        from hackathon.models import FindingsOutput

        json_str = json.dumps(
            {
                "findings": [
                    {
                        "severity": "FAIL",
                        "file": "events.py",
                        "line": 24,
                        "rule": "Immutability",
                        "evidence": "history=[]",
                        "unexpected": "should fail",
                    }
                ]
            }
        )
        with pytest.raises(ValidationError):
            FindingsOutput.model_validate_json(json_str)


# ---------------------------------------------------------------------------
# Unit tests — missing-file handling (subprocess, no API call)
# ---------------------------------------------------------------------------


class TestMissingFileHandling:
    def test_missing_skill_file_exits_nonzero(self, tmp_path: Path) -> None:
        """When --skill points to a nonexistent file the script must exit non-zero."""
        import subprocess

        cmd = _build_cmd(
            {
                "skill": "/nonexistent/skill.md",
                "rule": str(RULE_MD),
                "diff": str(PR_A_PATCH),
                "out": str(tmp_path / "findings.json"),
            }
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode != 0, (
            "Expected non-zero exit when --skill file is missing, "
            f"but got returncode={result.returncode}"
        )

    def test_missing_rule_file_exits_nonzero(self, tmp_path: Path) -> None:
        """When --rule points to a nonexistent file the script must exit non-zero."""
        import subprocess

        cmd = _build_cmd(
            {
                "skill": str(SKILL_MD),
                "rule": "/nonexistent/rule.md",
                "diff": str(PR_A_PATCH),
                "out": str(tmp_path / "findings.json"),
            }
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode != 0, (
            "Expected non-zero exit when --rule file is missing, "
            f"but got returncode={result.returncode}"
        )

    def test_missing_diff_file_exits_nonzero(self, tmp_path: Path) -> None:
        """When --diff points to a nonexistent file the script must exit non-zero."""
        import subprocess

        cmd = _build_cmd(
            {
                "skill": str(SKILL_MD),
                "rule": str(RULE_MD),
                "diff": "/nonexistent/pr.patch",
                "out": str(tmp_path / "findings.json"),
            }
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode != 0, (
            "Expected non-zero exit when --diff file is missing, "
            f"but got returncode={result.returncode}"
        )

    def test_missing_file_error_message_is_nonempty(self, tmp_path: Path) -> None:
        """When a required file is missing the script must print a clear error (stderr)."""
        import subprocess

        cmd = _build_cmd(
            {
                "skill": "/nonexistent/skill.md",
                "rule": str(RULE_MD),
                "diff": str(PR_A_PATCH),
                "out": str(tmp_path / "findings.json"),
            }
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        error_output = result.stderr + result.stdout
        assert error_output.strip(), (
            "Expected a non-empty error message when --skill file is missing, "
            "but got no output on stdout/stderr"
        )


# ---------------------------------------------------------------------------
# Unit tests — empty diff behavior (subprocess, no API call)
# ---------------------------------------------------------------------------


class TestEmptyDiffBehavior:
    def test_empty_diff_exits_zero_with_empty_findings(self, tmp_path: Path) -> None:
        """An empty diff should exit 0 and produce findings.json with findings=[].

        ASSUMPTION: the script treats an empty diff as 'nothing to review'
        and short-circuits before making any Anthropic API call. If the
        implementer chooses a different contract (e.g., always call the LLM),
        this test should be updated to match with a comment explaining why.

        This test does NOT set ANTHROPIC_API_KEY; if an LLM call were made
        it would fail with an auth error — thus a clean exit-0 confirms the
        short-circuit behavior.
        """
        import subprocess

        empty_diff = tmp_path / "empty.patch"
        empty_diff.write_text("")  # zero bytes

        cmd = _build_cmd(
            {
                "skill": str(SKILL_MD),
                "rule": str(RULE_MD),
                "diff": str(empty_diff),
                "out": str(tmp_path / "findings.json"),
            }
        )
        # Run WITHOUT ANTHROPIC_API_KEY in environment to confirm no LLM call
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        assert result.returncode == 0, (
            f"Expected exit 0 for empty diff, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )
        findings_path = tmp_path / "findings.json"
        assert findings_path.exists(), "findings.json was not written for empty diff"
        findings_data = json.loads(findings_path.read_text())
        assert findings_data.get("findings") == [], (
            f"Expected empty findings list for empty diff, got: {findings_data}"
        )


# ---------------------------------------------------------------------------
# Integration smoke tests — require ANTHROPIC_API_KEY and run_review.py
# ---------------------------------------------------------------------------


class TestPrARoundTrip:
    @pytest.mark.integration
    def test_exits_zero_against_pr_a_fixture(
        self,
        run_review_args: dict,
        _skip_when_api_key_absent: None,
    ) -> None:
        """run_review.py exits 0 when given real inputs and a valid API key."""
        import subprocess

        result = subprocess.run(
            _build_cmd(run_review_args),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Expected exit 0 but got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    @pytest.mark.integration
    def test_findings_json_exists_after_successful_run(
        self,
        run_review_args: dict,
        _skip_when_api_key_absent: None,
    ) -> None:
        """findings.json is written at the --out path on success."""
        import subprocess

        subprocess.run(_build_cmd(run_review_args), capture_output=True, text=True)
        findings_path = Path(run_review_args["out"])
        assert findings_path.exists(), (
            f"findings.json was not written to {findings_path}"
        )

    @pytest.mark.integration
    def test_findings_json_parses_as_findings_output(
        self,
        run_review_args: dict,
        _skip_when_api_key_absent: None,
    ) -> None:
        """findings.json content is parseable as a FindingsOutput model."""
        import subprocess

        from hackathon.models import FindingsOutput

        subprocess.run(_build_cmd(run_review_args), capture_output=True, text=True)
        findings_path = Path(run_review_args["out"])
        assert findings_path.exists(), (
            "findings.json not found — script may have failed"
        )
        findings_text = findings_path.read_text()
        output = FindingsOutput.model_validate_json(findings_text)
        # Structural assertion only — content is non-deterministic
        assert isinstance(output.findings, list)

    @pytest.mark.integration
    def test_report_md_exists_after_successful_run(
        self,
        run_review_args: dict,
        _skip_when_api_key_absent: None,
    ) -> None:
        """report.md is written alongside findings.json on success."""
        import subprocess

        subprocess.run(_build_cmd(run_review_args), capture_output=True, text=True)
        out_dir = Path(run_review_args["out"]).parent
        report_path = out_dir / "report.md"
        assert report_path.exists(), (
            f"report.md was not written to {report_path}. "
            "The spec requires a human-readable report alongside findings.json."
        )

    @pytest.mark.integration
    def test_findings_json_has_no_extra_fields(
        self,
        run_review_args: dict,
        _skip_when_api_key_absent: None,
    ) -> None:
        """findings.json schema strictness: no extra fields beyond FindingsOutput.

        FindingsOutput uses ConfigDict(extra='forbid'). If the LLM response
        sneaks in extra fields and the script does not strip them, this test
        surfaces the violation via model_validate_json().
        """
        import subprocess

        from hackathon.models import FindingsOutput

        subprocess.run(_build_cmd(run_review_args), capture_output=True, text=True)
        findings_path = Path(run_review_args["out"])
        if not findings_path.exists():
            pytest.skip("findings.json not written — earlier test may have failed")
        findings_text = findings_path.read_text()
        # model_validate_json raises ValidationError if extra fields are present
        # because FindingsOutput.model_config = ConfigDict(extra="forbid")
        output = FindingsOutput.model_validate_json(findings_text)
        assert output is not None  # parse succeeded
