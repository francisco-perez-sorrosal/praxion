"""Structural tests for the ``/report-praxion-issue`` command definition.

``commands/report-praxion-issue.md`` is a Markdown prompt, not executable code
-- its "tests" are grep-style assertions over frontmatter and body structure
(the convention used by any command test in this repo), verifying: the HITL
filing gate (no autonomous ``gh issue create``), the label-set invariant
(never the reserved ``ecosystem-feedback`` maintainer label), the preserved
security/responsible-disclosure path, the fingerprint-based dedup step run
before filing, and the hardcoded Praxion target (never a templated
``owner/repo`` argument).

Frontmatter parsing is reused from the Codex command exporter's own parser
(dynamic import, mirroring ``test_export_codex_command_skills.py``'s
convention) rather than reimplemented here.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMAND_PATH = REPO_ROOT / "commands" / "report-praxion-issue.md"
EXPORTER_PATH = REPO_ROOT / "codex" / "config" / "export-codex-command-skills.py"

PRAXION_REPO_SLUG = "francisco-perez-sorrosal/praxion"
ALLOWED_LABELS = "bug,auto-filed,category:<slug>,from-managed-project"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_codex_command_skills", EXPORTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frontmatter_and_body() -> tuple[dict[str, str], str]:
    exporter = _load_exporter()
    return exporter.parse_frontmatter_command(COMMAND_PATH)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def test_model_cannot_auto_invoke_the_command():
    metadata, _ = _frontmatter_and_body()
    assert metadata["disable-model-invocation"] == "true"


def test_allowed_tools_cover_gh_and_the_reporter_cli():
    metadata, _ = _frontmatter_and_body()
    allowed = metadata["allowed-tools"]
    for tool in ("Bash(gh:*)", "Bash(python3:*)", "Read", "Grep", "Glob", "AskUserQuestion"):
        assert tool in allowed


def test_argument_hint_accepts_only_a_fingerprint_not_a_bug_description():
    metadata, _ = _frontmatter_and_body()
    hint = metadata["argument-hint"]
    assert "fingerprint" in hint
    assert "owner/repo" not in hint
    assert "description" not in hint


# ---------------------------------------------------------------------------
# Hardcoded target (AC10 / REQ boundary: shape references only, never __file__
# -- this test covers the command-layer half: the target repo is a constant,
# never an interpolated argument).
# ---------------------------------------------------------------------------


def test_target_repo_is_hardcoded_not_a_template_argument():
    _, body = _frontmatter_and_body()
    assert PRAXION_REPO_SLUG in body
    assert "{owner/repo}" not in body


# ---------------------------------------------------------------------------
# Step ordering
# ---------------------------------------------------------------------------


def test_process_steps_appear_in_the_documented_order():
    _, body = _frontmatter_and_body()
    headings = (
        "### 1. Validate",
        "### 2. Dedup",
        "### 3. Draft",
        "### 4. Sanitize",
        "### 5. Security Gate",
        "### 6. HITL File",
        "### 7. Track",
    )
    indices = [body.index(heading) for heading in headings]
    assert indices == sorted(indices)


# ---------------------------------------------------------------------------
# Dedup before filing (fingerprint + tracker search)
# ---------------------------------------------------------------------------


def test_dedup_runs_before_drafting_and_searches_by_fingerprint():
    _, body = _frontmatter_and_body()
    dedup_index = body.index("### 2. Dedup")
    draft_index = body.index("### 3. Draft")
    dedup_section = body[dedup_index:draft_index]
    assert "fingerprint" in dedup_section
    assert "gh search issues" in dedup_section
    assert "UPSTREAM_ISSUES.md" in dedup_section


# ---------------------------------------------------------------------------
# HITL filing gate -- no autonomous `gh issue create`
# ---------------------------------------------------------------------------


def test_never_files_without_an_explicit_human_confirmation():
    _, body = _frontmatter_and_body()
    confirm_index = body.index("Shall I file this issue?")
    file_calls = [match.start() for match in re.finditer(r"gh issue create", body)]
    assert len(file_calls) == 1, (
        "gh issue create must appear exactly once (only after confirmation)"
    )
    assert confirm_index < file_calls[0]


# ---------------------------------------------------------------------------
# Label-set invariant -- exactly the four allowed labels, never the reserved
# maintainer arming-gate label.
# ---------------------------------------------------------------------------


def test_label_set_is_exactly_the_four_allowed_labels():
    _, body = _frontmatter_and_body()
    match = re.search(r'--label "([^"]+)"', body)
    assert match is not None, "gh issue create must pass an explicit --label value"
    assert match.group(1) == ALLOWED_LABELS


def test_never_emits_the_reserved_maintainer_label():
    _, body = _frontmatter_and_body()
    match = re.search(r'--label "([^"]+)"', body)
    assert "ecosystem-feedback" not in match.group(1)
    # The exclusion boundary is stated explicitly in prose, not silently omitted.
    assert "ecosystem-feedback" in body
    assert "maintainer" in body.lower()


# ---------------------------------------------------------------------------
# Security / responsible-disclosure path -- unconditional, precedes filing.
# ---------------------------------------------------------------------------


def test_security_gate_is_unconditional_and_precedes_filing():
    _, body = _frontmatter_and_body()
    gate_index = body.index("### 5. Security Gate")
    file_index = body.index("### 6. HITL File")
    gate_section = body[gate_index:file_index]
    assert "security-sensitive" in gate_section
    assert "public issue" in gate_section
    assert "stop" in gate_section.lower()


def test_preserves_the_responsible_disclosure_path():
    _, body = _frontmatter_and_body()
    assert "responsible-disclosure" in body
    assert "private vulnerability reporting" in body


# ---------------------------------------------------------------------------
# Reporter CLI invocation -- render / list / mark-filed, never a fresh capture.
# ---------------------------------------------------------------------------


def test_invokes_the_reporter_cli_for_list_render_and_mark_filed():
    _, body = _frontmatter_and_body()
    for subcommand in ("list", "render", "mark-filed"):
        assert f"report_praxion_issue.py {subcommand}" in body


def test_never_invokes_the_capture_subcommand():
    # Candidates are already captured by a Praxion capture point; this command
    # only files an existing PENDING.md candidate, never a fresh description.
    _, body = _frontmatter_and_body()
    assert "report_praxion_issue.py capture" not in body


def test_tracks_a_successful_filing_in_upstream_issues_and_marks_filed():
    _, body = _frontmatter_and_body()
    track_section = body[body.index("### 7. Track") :]
    assert "mark-filed" in track_section
    assert "UPSTREAM_ISSUES.md" in track_section
