"""Structural tests for the label-taxonomy-manifest onboarding install sub-step.

`/onboard-project` is a slash command (Markdown body executed by a live Claude
Code session) — it cannot be invoked from pytest. These tests validate the
documented contract by parsing `commands/onboard-project.md` structurally,
matching the precedent set by `tests/commands/test_onboard_ci_autofix_install.py`.

All tests below are expected to FAIL until the implementer adds a new
"Sub-step 8e.9" section to `commands/onboard-project.md` — the label taxonomy
manifest + reconciler caller install, positioned immediately after the
existing sub-step 8e.8 (whose Predicate/Action/placeholder-resolution shape
this new sub-step must mirror).
"""

from __future__ import annotations

import re
from pathlib import Path

ONBOARD_FILE = Path(__file__).parents[2] / "commands" / "onboard-project.md"

# The caller template's exact placeholder tokens, matching sub-step 8e.8's own
# resolution convention (claude/project-baseline/ci-autofix/ci-autofix.yml.tmpl).
HUB_SHA_PLACEHOLDER = "{{HUB_SHA}}"
HUB_OWNER_PLACEHOLDER = "{{PRAXION_HUB}}"


def _onboard_body() -> str:
    """Return the full onboard-project.md content (read lazily so collection succeeds)."""
    return ONBOARD_FILE.read_text(encoding="utf-8")


def _sub_step_8e9_section() -> str:
    """Return the '### Sub-step 8e.9' section body, or '' if not yet documented.

    Mirrors the sibling sub-steps' heading shape (e.g. '### Sub-step 8e.8 —
    CI autofix caller + policy + cross-model review gate'), extracting up to
    the next '##'-or-shallower heading so assertions stay scoped to this
    sub-step's own text and cannot pass vacuously against 8e.8's prose.
    """
    match = re.search(r"###\s+Sub-step 8e\.9.*?(?=\n##|\Z)", _onboard_body(), re.DOTALL)
    return match.group(0) if match else ""


def test_label_taxonomy_install_substep_is_documented() -> None:
    section = _sub_step_8e9_section()
    assert section, (
        "commands/onboard-project.md must document a 'Sub-step 8e.9' for the "
        "label taxonomy manifest + reconciler caller install — not found. "
        "The implementer must add it immediately after sub-step 8e.8."
    )
    assert re.search(r"label", section, re.IGNORECASE), (
        "Sub-step 8e.9 must be about the label taxonomy manifest install "
        "(heading/body should name 'label')"
    )


def test_skips_without_overwriting_when_manifest_or_caller_already_exists() -> None:
    section = _sub_step_8e9_section()
    assert section, "Sub-step 8e.9 not documented yet"
    predicate_match = re.search(r"\*\*Predicate\.?\*\*.*?(?=\n\*\*Action|\Z)", section, re.DOTALL)
    assert predicate_match, "Sub-step 8e.9 must document a Predicate (skip-if-exists guard)"
    predicate = predicate_match.group(0)
    assert ".github/labels.yml" in predicate, (
        "Predicate must check for an existing .github/labels.yml"
    )
    assert re.search(r"labels-reconcile\.yml", predicate), (
        "Predicate must also check for an existing reconciler caller "
        "(.github/workflows/labels-reconcile.yml)"
    )
    assert re.search(r"skip", predicate, re.IGNORECASE), (
        "Predicate must document skipping when either file already exists"
    )
    assert re.search(r"never overwrit", section, re.IGNORECASE), (
        "Sub-step 8e.9 must explicitly state it never overwrites an existing "
        "manifest or caller installation, mirroring sub-step 8e.8's own "
        "file-existence idempotency guard"
    )


def test_installs_manifest_and_caller_templates_into_dot_github() -> None:
    section = _sub_step_8e9_section()
    assert section, "Sub-step 8e.9 not documented yet"
    action_match = re.search(r"\*\*Action\.?\*\*.*", section, re.DOTALL)
    assert action_match, "Sub-step 8e.9 must document an Action"
    action = action_match.group(0)
    assert "claude/project-baseline/labels/labels.yml.tmpl" in action, (
        "Sub-step 8e.9's Action must read the manifest template "
        "'claude/project-baseline/labels/labels.yml.tmpl'"
    )
    assert "claude/project-baseline/labels/labels-reconcile.yml.tmpl" in action, (
        "Sub-step 8e.9's Action must read the caller template "
        "'claude/project-baseline/labels/labels-reconcile.yml.tmpl'"
    )
    assert ".github/labels.yml" in action, (
        "Sub-step 8e.9's Action must write the rendered manifest to .github/labels.yml"
    )
    assert ".github/workflows/labels-reconcile.yml" in action, (
        "Sub-step 8e.9's Action must write the rendered caller to "
        ".github/workflows/labels-reconcile.yml"
    )


def test_resolves_hub_sha_and_hub_owner_placeholders_same_as_sub_step_8e8() -> None:
    section = _sub_step_8e9_section()
    assert section, "Sub-step 8e.9 not documented yet"
    assert HUB_SHA_PLACEHOLDER in section, (
        f"Sub-step 8e.9 must reference the '{HUB_SHA_PLACEHOLDER}' placeholder "
        "from the caller template, matching sub-step 8e.8's own resolution "
        "convention for this token"
    )
    assert HUB_OWNER_PLACEHOLDER in section, (
        f"Sub-step 8e.9 must reference the '{HUB_OWNER_PLACEHOLDER}' "
        "placeholder from the caller template, matching sub-step 8e.8's own "
        "resolution convention for this token"
    )
    assert re.search(r"real|actual|resolved|current", section, re.IGNORECASE), (
        "Sub-step 8e.9 must document resolving {{HUB_SHA}} to a real, current "
        "commit SHA at install time — an unresolved placeholder or mutable "
        "ref must never survive in the installed caller (same discipline as "
        "sub-step 8e.8)"
    )
    assert re.search(r"never.{0,60}(placeholder|mutable|tag|branch)", section, re.IGNORECASE), (
        "Sub-step 8e.9 must explicitly rule out shipping an unresolved "
        "placeholder or a mutable tag/branch for {{HUB_SHA}}, mirroring "
        "sub-step 8e.8's resolution discipline verbatim"
    )
