"""Structural tests for Sub-step 5b.t (hackathon teardown) + stamp `mode` persistence.

`skills/onboard-project/references/phases-core.md` is a Claude Code skill
reference body — it cannot be invoked from pytest. These tests validate the
documented contract by parsing the file structurally, matching the precedent
set by `tests/commands/test_onboard_ci_autofix_install.py`.

`phases-core.md` documents Sub-step 5b.t (hackathon teardown) and Phase 9's
additive-only stamp `mode` field.
"""

from __future__ import annotations

import re
from pathlib import Path

PHASES_CORE_FILE = (
    Path(__file__).parents[2] / "skills" / "onboard-project" / "references" / "phases-core.md"
)

# The six hackathon artifacts, per §Phase 5b's own
# install-side enumeration (phases-core.md §Phase 5b).
SIX_HACKATHON_ARTIFACTS = (
    "PRAXION_HACKATHON_MODE",
    "Hackathon Mode",  # CLAUDE.md block
    "praxion-rules.yaml",  # rules preset
    "scripts/praxion-hackathon",
    ".claude/hackathon-directive.md",
    ".claude/hackathon-settings.json",
)


def _phases_core_body() -> str:
    """Return the full phases-core.md content (read lazily so collection succeeds)."""
    return PHASES_CORE_FILE.read_text(encoding="utf-8")


def _sub_step_5bt_section() -> str:
    """Return the '### Sub-step 5b.t' section body, or '' if not yet documented."""
    match = re.search(r"###\s+Sub-step 5b\.t.*?(?=\n##|\Z)", _phases_core_body(), re.DOTALL)
    return match.group(0) if match else ""


def test_5bt_is_documented() -> None:
    section = _sub_step_5bt_section()
    assert section, (
        "phases-core.md must document 'Sub-step 5b.t' (hackathon teardown) -- "
        "not found. The implementer must add it."
    )
    assert re.search(r"teardown", section, re.IGNORECASE), (
        "Sub-step 5b.t must be framed as a teardown (inverse of §Phase 5b's install)"
    )


def test_5bt_enumerates_all_six_hackathon_artifacts_explicitly() -> None:
    section = _sub_step_5bt_section()
    assert section, "Sub-step 5b.t not documented yet"
    for artifact in SIX_HACKATHON_ARTIFACTS:
        assert artifact in section, (
            f"Sub-step 5b.t must explicitly enumerate the hackathon artifact "
            f"'{artifact}' -- an enumerate-before-remove teardown that silently "
            f"drops one of the six install-side artifacts is a data-loss bug"
        )


def test_5bt_fires_only_when_mode_is_promote() -> None:
    section = _sub_step_5bt_section()
    assert section, "Sub-step 5b.t not documented yet"
    assert re.search(r"\bpromote\b", section, re.IGNORECASE), (
        "Sub-step 5b.t must document firing only when mode=promote "
        "(SYSTEMS_PLAN.md §Mode x Phase Matrix)"
    )


def test_5bt_compares_each_artifact_against_its_template_before_removing() -> None:
    section = _sub_step_5bt_section()
    assert section, "Sub-step 5b.t not documented yet"
    assert re.search(r"template", section, re.IGNORECASE), (
        "Sub-step 5b.t must compare each artifact against its installed "
        "template before removal (diverged-artifact skip path)"
    )
    assert re.search(r"diverg", section, re.IGNORECASE), (
        "Sub-step 5b.t must name the diverged-from-template case explicitly"
    )


def test_5bt_skips_with_warning_on_a_diverged_artifact_never_rm_rf() -> None:
    section = _sub_step_5bt_section()
    assert section, "Sub-step 5b.t not documented yet"
    assert re.search(r"skip", section, re.IGNORECASE), (
        "A diverged (hand-edited) artifact must be skipped, not force-removed"
    )
    assert re.search(r"warn", section, re.IGNORECASE), (
        "Sub-step 5b.t must warn the user when it skips a diverged artifact"
    )
    assert not re.search(r"rm\s+-rf", section), (
        "Sub-step 5b.t must never use 'rm -rf' -- it is a one-way door "
        "(deletes files in a user's repo) and must remove named artifacts "
        "individually, never recursively"
    )


def test_phase_9_stamp_schema_gains_an_additive_mode_field() -> None:
    body = _phases_core_body()
    # Anchored on the bolded action phrase, not the bare "onboard manifest"
    # substring -- that phrase also appears earlier, in Phase 3/4's
    # cross-version-cleanup prose describing a *read* of a prior run's
    # manifest, which is not the Phase 9 stamp-write section under test.
    manifest_match = re.search(
        r"\*\*Write the onboard manifest\*\*.*?(?=\n##\s*§Phase|\Z)", body, re.DOTALL
    )
    assert manifest_match, "phases-core.md §Phase 9 must document the onboard-manifest write"
    manifest_section = manifest_match.group(0)
    assert re.search(r'"mode"\s*:', manifest_section), (
        'Phase 9\'s stamp write must add a "mode" field to .ai-state/.praxion-onboard.json'
    )
    assert re.search(r'"full"', manifest_section), 'Phase 9 must document the stamp value "full"'
    assert re.search(r'"hackathon"', manifest_section), (
        'Phase 9 must document the stamp value "hackathon"'
    )


def test_absent_mode_key_reads_as_full_for_back_compat() -> None:
    body = _phases_core_body()
    assert re.search(
        r"absent.{0,60}\bfull\b|\bfull\b.{0,60}absent", body, re.IGNORECASE | re.DOTALL
    ), (
        "phases-core.md must document that an absent 'mode' key in "
        '.ai-state/.praxion-onboard.json reads as "full" -- projects onboarded '
        "before this field existed must not silently read as hackathon-managed"
    )
