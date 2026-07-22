"""Structural tests for the ci-autofix onboarding install sub-step.

`/onboard-project` is a slash command (Markdown body executed by a live Claude
Code session) — it cannot be invoked from pytest. These tests validate the
documented contract by parsing `commands/onboard-project.md` structurally,
matching the precedent set by `tests/commands/test_resume_rework.py`.

All tests exercising the new sub-step are expected to FAIL until the
implementer adds it to `commands/onboard-project.md`. The regression-guard
test on `commands/new-project.md` is expected to PASS from the start — it
pins the pre-existing baseline the plan depends on, not new behavior.
"""

from __future__ import annotations

import re
from pathlib import Path

ONBOARD_FILE = Path(__file__).parents[2] / "commands" / "onboard-project.md"
NEW_PROJECT_FILE = Path(__file__).parents[2] / "commands" / "new-project.md"

# The caller template's exact placeholder tokens (claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl)
HUB_SHA_PLACEHOLDER = "{{HUB_SHA}}"
HUB_OWNER_PLACEHOLDER = "{{PRAXION_HUB}}"


def _onboard_body() -> str:
    """Return the full onboard-project.md content (read lazily so collection succeeds)."""
    return ONBOARD_FILE.read_text(encoding="utf-8")


def _new_project_body() -> str:
    """Return the full new-project.md content (read lazily so collection succeeds)."""
    return NEW_PROJECT_FILE.read_text(encoding="utf-8")


def _sub_step_8e8_section() -> str:
    """Return the '### Sub-step 8e.8' section body, or '' if not yet documented.

    Mirrors the sibling sub-steps' heading shape (e.g. '### Sub-step 8e.7 —
    Dependency-scanning config'), extracting up to the next '##'-or-shallower
    heading so assertions stay scoped to this sub-step's own text and cannot
    pass vacuously against a neighboring sub-step's prose.
    """
    match = re.search(r"###\s+Sub-step 8e\.8.*?(?=\n##|\Z)", _onboard_body(), re.DOTALL)
    return match.group(0) if match else ""


def _manifest_artifacts_snippet() -> str:
    """Return the text following the '"artifacts"' key in the §Phase 9 manifest example.

    A fixed-size window (not brace-matching) is intentional: the manifest JSON
    example is illustrative Markdown, not parseable JSON (it may gain new keys
    at any indentation), so anchoring on a generous character window is more
    robust than depending on exact brace nesting.
    """
    body = _onboard_body()
    idx = body.find('"artifacts"')
    assert idx != -1, "commands/onboard-project.md must document an 'artifacts' manifest key"
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
    assert (
        "ci-autofix.yml.tmpl" in section
    ), "Sub-step 8e.8 must read the caller template 'ci-autofix.yml.tmpl'"
    assert (
        "autofix-policy.yml.tmpl" in section
    ), "Sub-step 8e.8 must read the policy template 'autofix-policy.yml.tmpl'"
    assert (
        ".github/workflows/ci-autofix.yml" in section
    ), "Sub-step 8e.8 must write the caller to .github/workflows/ci-autofix.yml"
    assert (
        ".github/autofix-policy.yml" in section
    ), "Sub-step 8e.8 must write the policy to .github/autofix-policy.yml"


def test_skips_without_overwriting_when_caller_or_policy_already_exists() -> None:
    section = _sub_step_8e8_section()
    assert section, "Sub-step 8e.8 not documented yet"
    predicate_match = re.search(r"\*\*Predicate\.?\*\*.*?(?=\n\*\*Action|\Z)", section, re.DOTALL)
    assert predicate_match, "Sub-step 8e.8 must document a Predicate (skip-if-exists guard)"
    predicate = predicate_match.group(0)
    assert (
        ".github/workflows/ci-autofix.yml" in predicate
    ), "Predicate must check for an existing .github/workflows/ci-autofix.yml"
    assert (
        ".github/autofix-policy.yml" in predicate
    ), "Predicate must check for an existing .github/autofix-policy.yml"
    assert re.search(
        r"skip", predicate, re.IGNORECASE
    ), "Predicate must document skipping (never overwriting) when either file exists"


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
    assert (
        HUB_SHA_PLACEHOLDER in section
    ), f"Sub-step 8e.8 must reference the '{HUB_SHA_PLACEHOLDER}' placeholder from the caller template"
    assert (
        HUB_OWNER_PLACEHOLDER in section
    ), f"Sub-step 8e.8 must reference the '{HUB_OWNER_PLACEHOLDER}' placeholder from the caller template"
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
    assert (
        "gh secret set CLAUDE_CODE_OAUTH_TOKEN" in section
    ), "Sub-step 8e.8 must document the exact 'gh secret set CLAUDE_CODE_OAUTH_TOKEN' command"
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
    assert re.search(
        r"allow.?list", section, re.IGNORECASE
    ), "Sub-step 8e.8 must name the org Actions-allowlist instruction explicitly"
    assert re.search(r"one.?time", section, re.IGNORECASE), (
        "Sub-step 8e.8 must frame the allowlist instruction as a one-time, "
        "deliberate operator step (never auto-injected)"
    )


def test_new_project_gains_no_duplicate_install_logic() -> None:
    """Regression guard for the scoping decision to keep installs single-path.

    `/new-project` defers all `claude/project-baseline/*` installs to a later
    `/onboard-project` run — it must not gain its own copy of the ci-autofix
    install logic. This pins the pre-existing baseline (currently zero
    'dependabot' mentions) so a future edit cannot silently duplicate the
    install path here instead of confirming the defer-only contract.
    """
    body = _new_project_body()
    assert body.lower().count("dependabot") == 0, (
        "commands/new-project.md must not gain its own copy of any "
        "project-baseline install logic (dependabot is the existing precedent "
        "asset) — installs stay deferred to /onboard-project, matching the "
        "established single-install-path convention"
    )
