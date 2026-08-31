"""Structural tests for the `permissions.allow` baseline in §Phase 5 of onboarding.

`/onboard-project` (now `skills/onboard-project/SKILL.md` + its phase-body
references) is executed by a live Claude Code session — it cannot be invoked
from pytest. These tests validate the documented contract by parsing
`skills/onboard-project/references/phases-core.md` structurally, matching the
precedent set by `tests/commands/test_onboard_praxion_feedback_install.py`.

The gap these guard against is invisible from inside Praxion: this repo's own
`.claude/settings.json` already pre-allows subagent writes to the ephemeral
pipeline tree, so its pipelines never hit the denial that a freshly-onboarded
project would hit on its very first run.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
_SKILL_ROOT = REPO_ROOT / "skills" / "onboard-project"
ONBOARD_FILE = _SKILL_ROOT / "references" / "phases-core.md"
SKILL_FILE = _SKILL_ROOT / "SKILL.md"

AI_WORK_WRITE_ENTRY = "Write(.ai-work/**)"


def _onboard_body() -> str:
    """Return the phases-core.md content that owns §Phase 5 (read lazily)."""
    return ONBOARD_FILE.read_text(encoding="utf-8")


def _skill_body() -> str:
    """Return SKILL.md's content, the sole owner of §Idempotency Predicates (read lazily)."""
    return SKILL_FILE.read_text(encoding="utf-8")


def _phase_5_section() -> str:
    """Return the '## §Phase 5' section body, up to the next '## ' heading.

    A fixed heading-to-heading window keeps assertions scoped to this phase and
    unable to pass vacuously against the Obsidian phase, which writes the
    sibling `permissions.deny` array.
    """
    match = re.search(r"##\s+§Phase 5 .*?(?=\n## §|\Z)", _onboard_body(), re.DOTALL)
    return match.group(0) if match else ""


def _allow_sub_step() -> str:
    """Return the `permissions.allow` sub-step body within §Phase 5."""
    section = _phase_5_section()
    match = re.search(r"###\s+Sub-step 5b.*?(?=\n### |\Z)", section, re.DOTALL)
    return match.group(0) if match else ""


def _granted_entries() -> list[str]:
    """Return every permission entry the sub-step grants, from its jq merge command."""
    body = _allow_sub_step()
    merge = re.search(r"\.permissions\.allow\s*=\s*\(\(.*?\|\s*unique\)", body, re.DOTALL)
    assert merge, "Sub-step must document a jq merge that appends to .permissions.allow"
    return re.findall(r'"([^"]+)"', merge.group(0))


def test_phase_5_installs_a_permissions_allow_baseline() -> None:
    section = _phase_5_section()
    assert section, "§Phase 5 section not found in commands/onboard-project.md"
    assert "permissions.allow" in section, (
        "§Phase 5 must install a permissions.allow baseline — onboarding previously "
        "only preserved an existing array and never created one, so managed projects "
        "started with no allow list at all"
    )
    assert _allow_sub_step(), "The permissions.allow baseline must be its own §Phase 5 sub-step"


def test_baseline_grants_subagent_writes_to_the_ephemeral_pipeline_tree() -> None:
    assert AI_WORK_WRITE_ENTRY in _granted_entries(), (
        f"The baseline must grant {AI_WORK_WRITE_ENTRY}. A spawned subagent cannot answer "
        "an interactive permission prompt, so without it the pipeline stalls mid-run on a "
        "denial the orchestrator never sees."
    )


def test_baseline_grants_no_bash_permissions() -> None:
    """A standing `Bash(...)` grant is never installed on a user's behalf."""
    bash_entries = [entry for entry in _granted_entries() if entry.startswith("Bash(")]
    assert not bash_entries, (
        f"The onboarding baseline must not grant Bash permissions, found: {bash_entries}"
    )


def test_baseline_grants_no_writes_to_committed_project_intelligence() -> None:
    """`.ai-state/` holds committed decisions and ledgers — those writes stay promptable."""
    state_entries = [entry for entry in _granted_entries() if ".ai-state" in entry]
    assert not state_entries, (
        f"The baseline must not pre-approve writes to .ai-state/, found: {state_entries}. "
        "Only the gitignored, cleanup-deleted .ai-work/ tree qualifies."
    )


def test_every_granted_entry_carries_a_written_justification() -> None:
    """Each entry is a standing grant the user is never asked about again."""
    body = _allow_sub_step()
    for entry in _granted_entries():
        assert body.count(entry) >= 2, (
            f"'{entry}' appears only in the merge command — every granted entry needs a "
            "one-line rationale in the sub-step's 'Why each entry' table"
        )


def test_predicate_is_a_subset_check_so_older_installs_gain_new_entries() -> None:
    body = _allow_sub_step()
    predicate = re.search(r"\*\*Predicate.*?\*\*.*?(?=\*\*Action|\Z)", body, re.DOTALL)
    assert predicate, "Sub-step must document a Predicate"
    text = predicate.group(0)
    assert "permissions.allow" in text, "Predicate must inspect .permissions.allow"
    assert re.search(r"length\s*==\s*0", text), (
        "Predicate must be a subset check (required-minus-present is empty), not a bare "
        "existence check — otherwise a project onboarded under a smaller entry set never "
        "gains the missing entries on re-run"
    )


def test_merge_preserves_the_sibling_deny_array_and_user_entries() -> None:
    body = _allow_sub_step()
    assert re.search(r"permissions\.deny", body), (
        "Sub-step must state that the sibling permissions.deny array is preserved — the "
        "Obsidian phase writes it, and the two must compose in either order"
    )
    assert re.search(r"unique", body), (
        "The jq merge must be `unique`-deduped so re-running is idempotent"
    )
    assert re.search(r"never remove|preserve", body, re.IGNORECASE), (
        "Sub-step must state that a user's own entries are preserved, never rewritten"
    )


def test_phase_5_predicate_is_evaluated_per_sub_step_not_phase_wide() -> None:
    """A phase-level skip would strand already-onboarded projects without the baseline."""
    predicates_section = re.search(
        r"##\s+§Idempotency Predicates.*?(?=\n## |\Z)", _skill_body(), re.DOTALL
    )
    assert predicates_section, "§Idempotency Predicates section not found"
    table_row = re.search(r"^\| 5 \| (.*)$", predicates_section.group(0), re.MULTILINE)
    assert table_row, "§Idempotency Predicates must carry a row for Phase 5"
    row = table_row.group(1)
    assert "permissions.allow" in row, (
        "The Phase 5 idempotency row must cover the permissions.allow sub-step; a row "
        "naming only the observability key implies a phase-wide skip that would strand "
        "every project onboarded by an earlier version"
    )
