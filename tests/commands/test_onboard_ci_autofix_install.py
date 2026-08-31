"""Structural tests for the ci-autofix onboarding install sub-step.

`/onboard-project` (now `skills/onboard-project/SKILL.md` + its phase-body
references) is executed by a live Claude Code session — it cannot be invoked
from pytest. These tests validate the documented contract by parsing the
skill's phase files structurally, matching the precedent set by
`tests/commands/test_resume_rework.py`.

Sub-step 8e.8 (the ci-autofix caller+policy install) lives in
`references/phases-optional.md`; the §Phase 9 onboard-manifest example it
must extend lives in `references/phases-core.md` — the two files are read
independently below rather than joined, since each assertion targets exactly
one of them.
"""

from __future__ import annotations

import re
from pathlib import Path

_SKILL_ROOT = Path(__file__).parents[2] / "skills" / "onboard-project"
PHASES_CORE_FILE = _SKILL_ROOT / "references" / "phases-core.md"
PHASES_OPTIONAL_FILE = _SKILL_ROOT / "references" / "phases-optional.md"
POLICY_TEMPLATE_FILE = (
    Path(__file__).parents[2]
    / "claude"
    / "project-baseline"
    / "ci-autofix"
    / "autofix-policy.yml.tmpl"
)

# The caller template's exact placeholder tokens (claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl)
HUB_SHA_PLACEHOLDER = "{{HUB_SHA}}"
HUB_OWNER_PLACEHOLDER = "{{PRAXION_HUB}}"


def _onboard_body() -> str:
    """Return the phases-optional.md content that owns Sub-step 8e.8 (read lazily)."""
    return PHASES_OPTIONAL_FILE.read_text(encoding="utf-8")


def _phases_core_body() -> str:
    """Return the phases-core.md content that owns §Phase 9 (read lazily)."""
    return PHASES_CORE_FILE.read_text(encoding="utf-8")


def _policy_template_body() -> str:
    """Return the full autofix-policy.yml.tmpl content (read lazily so collection succeeds)."""
    return POLICY_TEMPLATE_FILE.read_text(encoding="utf-8")


def _hub_sha_shared_section() -> str:
    """Return the '§ Hub SHA resolution' section shared-procedures.md now owns.

    A dedup pass (planner Step 7) moved the hub-SHA resolution rules — including
    the "never a placeholder, never a mutable ref" requirement asserted below —
    out of the per-sub-step body and into one shared section cited by anchor.
    Behavior is unchanged; only its location moved.
    """
    text = (PHASES_CORE_FILE.parents[0] / "shared-procedures.md").read_text(encoding="utf-8")
    match = re.search(r"##\s+§ Hub SHA resolution.*?(?=\n## |\Z)", text, re.DOTALL)
    return match.group(0) if match else ""


def _sub_step_8e8_section() -> str:
    """Return the '### Sub-step 8e.8' section body, or '' if not yet documented.

    Mirrors the sibling sub-steps' heading shape (e.g. '### Sub-step 8e.7 —
    Dependency-scanning config'), extracting up to the next '##'-or-shallower
    heading so assertions stay scoped to this sub-step's own text and cannot
    pass vacuously against a neighboring sub-step's prose. Appends the shared
    hub-SHA resolution section it cites by anchor, so assertions written
    against the pre-dedup inline text still see the same behavioral content.
    """
    match = re.search(r"###\s+Sub-step 8e\.8.*?(?=\n##|\Z)", _onboard_body(), re.DOTALL)
    section = match.group(0) if match else ""
    if section and "shared-procedures.md#" in section:
        section += "\n\n" + _hub_sha_shared_section()
    return section


def _manifest_artifacts_snippet() -> str:
    """Return the text following the '"artifacts"' key in the §Phase 9 manifest example.

    A fixed-size window (not brace-matching) is intentional: the manifest JSON
    example is illustrative Markdown, not parseable JSON (it may gain new keys
    at any indentation), so anchoring on a generous character window is more
    robust than depending on exact brace nesting.
    """
    body = _phases_core_body()
    idx = body.find('"artifacts"')
    assert idx != -1, "phases-core.md's §Phase 9 must document an 'artifacts' manifest key"
    return body[idx : idx + 600]


def test_ci_autofix_install_substep_is_documented() -> None:
    section = _sub_step_8e8_section()
    assert section, (
        "commands/onboard-project.md must document a 'Sub-step 8e.8' for the "
        "ci-autofix caller+policy install — not found. The implementer must add it."
    )
    assert re.search(r"ci-?autofix", section, re.IGNORECASE), (
        "Sub-step 8e.8 must be about the ci-autofix caller install "
        "(heading/body should name 'ci-autofix')"
    )


def test_installs_caller_and_policy_templates_into_dot_github() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert "ci-autofix.yml.tmpl" in section, (
        "Sub-step 8e.8 must read the caller template 'ci-autofix.yml.tmpl'"
    )
    assert "autofix-policy.yml.tmpl" in section, (
        "Sub-step 8e.8 must read the policy template 'autofix-policy.yml.tmpl'"
    )
    assert ".github/workflows/ci-autofix.yml" in section, (
        "Sub-step 8e.8 must write the caller to .github/workflows/ci-autofix.yml"
    )
    assert ".github/autofix-policy.yml" in section, (
        "Sub-step 8e.8 must write the policy to .github/autofix-policy.yml"
    )


def test_skips_without_overwriting_when_caller_or_policy_already_exists() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    predicate_match = re.search(r"\*\*Predicate\.?\*\*.*?(?=\n\*\*Action|\Z)", section, re.DOTALL)
    assert predicate_match, "Sub-step 8e.8 must document a Predicate (skip-if-exists guard)"
    predicate = predicate_match.group(0)
    assert ".github/workflows/ci-autofix.yml" in predicate, (
        "Predicate must check for an existing .github/workflows/ci-autofix.yml"
    )
    assert ".github/autofix-policy.yml" in predicate, (
        "Predicate must check for an existing .github/autofix-policy.yml"
    )
    assert re.search(r"skip", predicate, re.IGNORECASE), (
        "Predicate must document skipping (never overwriting) when either file exists"
    )


def test_records_install_in_onboard_manifest() -> None:
    snippet = _manifest_artifacts_snippet()
    assert re.search(r'"[a-z_]*autofix[a-z_]*"\s*:', snippet, re.IGNORECASE), (
        "The §Phase 9 onboard-manifest 'artifacts' example must gain a new key "
        "recording the installed ci-autofix caller+policy (e.g. 'ci_autofix') — "
        "not found near the 'artifacts' block."
    )


def test_hub_sha_and_hub_owner_placeholders_resolved_to_real_values() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert HUB_SHA_PLACEHOLDER in section, (
        f"Sub-step 8e.8 must reference the '{HUB_SHA_PLACEHOLDER}' placeholder from the caller template"
    )
    assert HUB_OWNER_PLACEHOLDER in section, (
        f"Sub-step 8e.8 must reference the '{HUB_OWNER_PLACEHOLDER}' placeholder from the caller template"
    )
    # FM-1: the sub-step must document resolving HUB_SHA to a REAL commit SHA —
    # never leaving it as an unresolved placeholder or a mutable ref/tag/branch.
    assert re.search(r"real|actual|resolved|current", section, re.IGNORECASE), (
        "Sub-step 8e.8 must document resolving {{HUB_SHA}} to a real, current "
        "commit SHA at install time (FM-1: an unresolved placeholder or mutable "
        "ref must never survive in the installed caller)"
    )
    assert re.search(r"never.{0,40}(placeholder|mutable|tag|branch)", section, re.IGNORECASE), (
        "Sub-step 8e.8 must explicitly rule out shipping an unresolved "
        "placeholder or a mutable tag/branch for {{HUB_SHA}} (FM-1)"
    )


def test_prints_secret_setup_command_without_auto_running_it() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert "gh secret set CLAUDE_CODE_OAUTH_TOKEN" in section, (
        "Sub-step 8e.8 must document the exact 'gh secret set CLAUDE_CODE_OAUTH_TOKEN' command"
    )
    assert re.search(r"\bprint\b", section, re.IGNORECASE), (
        "Sub-step 8e.8 must PRINT the secret-setup command, matching the "
        "print-not-inject convention used by sibling sub-steps (8e.3/8e.4)"
    )
    assert not re.search(r"\brun\s+gh secret set", section, re.IGNORECASE), (
        "Sub-step 8e.8 must never auto-run 'gh secret set' on the operator's "
        "behalf — only print it as a one-time manual step"
    )


def test_prints_org_actions_allowlist_instruction() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert "OWNER/REPOSITORY/PATH/FILENAME" in section, (
        "Sub-step 8e.8 must print the org Actions-allowlist instruction using "
        "the OWNER/REPOSITORY/PATH/FILENAME@<ref> syntax (RESEARCH_FINDINGS.md Q4b)"
    )
    assert re.search(r"allow.?list", section, re.IGNORECASE), (
        "Sub-step 8e.8 must name the org Actions-allowlist instruction explicitly"
    )
    assert re.search(r"one.?time", section, re.IGNORECASE), (
        "Sub-step 8e.8 must frame the allowlist instruction as a one-time, "
        "deliberate operator step (never auto-injected)"
    )


def test_installs_cross_model_caller_when_policy_gate_is_not_off() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert "cross-model-review.yml.tmpl" in section, (
        "Sub-step 8e.8 must read the cross-model review caller template "
        "'cross-model-review.yml.tmpl'"
    )
    assert ".github/workflows/cross-model-review.yml" in section, (
        "Sub-step 8e.8 must write the rendered caller to "
        ".github/workflows/cross-model-review.yml — not found (8e.8 still "
        "defers this install)"
    )
    assert re.search(r"cross_model_gate\s*!=\s*.{0,3}off", section, re.IGNORECASE), (
        "Sub-step 8e.8 must gate the cross-model install on the policy's "
        "'cross_model_gate != off' predicate"
    )


def test_skips_cross_model_install_when_policy_gate_is_off() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert re.search(r"cross_model_gate.{0,60}\boff\b", section, re.IGNORECASE | re.DOTALL), (
        "Sub-step 8e.8 must reference the policy's 'cross_model_gate' value "
        "'off' as the explicit opt-out"
    )
    assert re.search(
        r"\boff\b.{0,120}(skip|not install|never install|does not install|no.{0,10}install)"
        r"|(skip|not install|never install|does not install|no.{0,10}install).{0,120}\boff\b",
        section,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Sub-step 8e.8 must explicitly document that a project with "
        "'cross_model_gate: off' does NOT get the cross-model caller "
        "installed — an opted-out project must not be forced a second "
        "vendor's secret requirement"
    )


def test_skips_without_overwriting_when_cross_model_caller_already_exists() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert ".github/workflows/cross-model-review.yml" in section, (
        "Sub-step 8e.8 must reference the cross-model caller's install path "
        ".github/workflows/cross-model-review.yml"
    )
    assert re.search(
        r"cross-model-review\.yml.{0,120}(already exist|absent|present)"
        r"|(already exist|absent|present).{0,120}cross-model-review\.yml",
        section,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Sub-step 8e.8 must guard the cross-model caller install on its own "
        "file-existence check — never overwrite an existing "
        ".github/workflows/cross-model-review.yml, mirroring the ci-autofix "
        "file-existence idempotency guard"
    )


def test_prints_cursor_api_key_when_cross_model_caller_is_installed() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    assert "gh secret set CURSOR_API_KEY" in section, (
        "Sub-step 8e.8 must document the exact 'gh secret set CURSOR_API_KEY' command"
    )
    assert not re.search(r"P2.{0,40}print only if", section, re.IGNORECASE | re.DOTALL), (
        "The CURSOR_API_KEY print must no longer be framed as a deferred "
        "'P2, print only if' aside — the cross-model caller is now actually "
        "installed, so the print is a real, unconditional one-time operator "
        "step whenever the caller is installed"
    )
    assert re.search(
        r"(installed|install).{0,120}CURSOR_API_KEY|CURSOR_API_KEY.{0,120}(installed|install)",
        section,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Sub-step 8e.8 must tie the CURSOR_API_KEY print explicitly to the "
        "cross-model caller being installed"
    )


def test_onboard_asset_lists_reference_cross_model_review_template() -> None:
    body = _onboard_body()
    asset_resolution_match = re.search(r"\*\*Asset resolution\.\*\*.*", body)
    assert asset_resolution_match, "Phase 8e must document an 'Asset resolution.' line"
    assert "cross-model-review.yml.tmpl" in asset_resolution_match.group(0), (
        "The Phase 8e asset-resolution line (~L975) must list "
        "'cross-model-review.yml.tmpl' alongside the ci-autofix templates it "
        "already names"
    )
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    action_match = re.search(
        r"\*\*Action\.\*\*\s+Read `claude/project-baseline/ci-autofix/.*", section
    )
    assert action_match, "Sub-step 8e.8's 'Action.' template-read line (~L1033) not found"
    assert "cross-model-review.yml.tmpl" in action_match.group(0), (
        "Sub-step 8e.8's Action line (~L1033) must read 'cross-model-review.yml.tmpl' "
        "alongside the ci-autofix templates it already reads"
    )


def test_autofix_policy_template_documents_pr_checks_dependabot_fork_prs_as_live_surfaces() -> None:
    body = _policy_template_body()
    assert "reserved, not yet read by the hub" not in body, (
        "autofix-policy.yml.tmpl's pr_checks/dependabot/fork_prs comments must "
        "no longer claim they are 'reserved, not yet read by the hub' — P3a "
        "made these surfaces live"
    )
    for surface in ("pr_checks", "dependabot", "fork_prs"):
        line_match = re.search(rf"^\s*{surface}:.*$", body, re.MULTILINE)
        assert line_match, f"autofix-policy.yml.tmpl must document a '{surface}:' surface line"
        assert re.search(r"live", line_match.group(0), re.IGNORECASE), (
            f"autofix-policy.yml.tmpl's '{surface}:' comment must describe it "
            "as a LIVE surface read by the hub (P3a made these live, no "
            "longer reserved)"
        )
