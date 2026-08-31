"""Structural tests for the onboarding capability-ID vocabulary + defaults.

`skills/onboard-project/SKILL.md` is a Claude Code skill body — it cannot be
invoked from pytest. These tests validate the documented contract by parsing
the skill file structurally, matching the precedent set by
`tests/commands/test_onboard_ci_autofix_install.py`.

RED-first (BDD/TDD): as of this test's authoring, `SKILL.md` still speaks
only the internal phase-id vocabulary — there is no user-facing capability
table. Every test below is expected to FAIL until the paired implementer
step publishes the capability-ID -> phase-id mapping table and the
Mode x Phase Matrix per `INTERFACE_DESIGN.md §2.3` / `SYSTEMS_PLAN.md
§Capability IDs`. The module-level `pytestmark` records this as a
non-blocking xfail so the rest of the suite stays green for other agents
running concurrently; the implementer removes the marker when the tables
land.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.xfail(
    strict=False,
    reason="RED until the paired implementer step publishes SKILL.md's capability vocabulary",
)

SKILL_FILE = Path(__file__).parents[2] / "skills" / "onboard-project" / "SKILL.md"

# The eight capability ids, per SYSTEMS_PLAN.md §Capability IDs / INTERFACE_DESIGN.md §2.3.
CAPABILITY_IDS = ("core", "arch", "quality", "ci", "aac", "ml", "obsidian", "observability")

# Every phase id the Mode x Phase Matrix enumerates (SYSTEMS_PLAN.md §Mode x Phase Matrix).
MODE_PHASE_MATRIX_IDS = (
    "0",
    "0s",
    "0.5",
    "1",
    "2",
    "3",
    "4",
    "5",
    "5b",
    "5b.t",
    "6",
    "7",
    "8",
    "8b",
    "8c",
    "8d",
    "8e.1",
    "8e.2",
    "8e.3",
    "8e.4",
    "8e.5",
    "8e.6",
    "8e.7",
    "8e.8",
    "8e.9",
    "9",
)

# Two phase ids the vocabulary deliberately leaves unmapped -- they are
# mode-implied, not user-selectable (SYSTEMS_PLAN.md §Capability IDs note).
_NOT_USER_SELECTABLE = ("0", "0s", "5b", "5b.t")


def _skill_body() -> str:
    """Return the full SKILL.md content (read lazily so collection succeeds)."""
    return SKILL_FILE.read_text(encoding="utf-8")


def _capability_table_section() -> str:
    """Return the capability-ID mapping table section, or '' if absent."""
    match = re.search(
        r"^##\s*.*Capability.*$.*?(?=\n##\s|\Z)", _skill_body(), re.MULTILINE | re.DOTALL
    )
    return match.group(0) if match else ""


def test_capability_id_table_is_published_once_in_skill_md() -> None:
    section = _capability_table_section()
    assert section, (
        "SKILL.md must publish the capability-ID -> phase-id mapping table as "
        "the single join point between the user-facing and internal "
        "vocabularies (INTERFACE_DESIGN.md §2.3 / dec-draft-113cc050)"
    )
    for capability_id in CAPABILITY_IDS:
        assert re.search(rf"`{re.escape(capability_id)}`", section), (
            f"Capability table must list `{capability_id}` as a row"
        )


def test_obsidian_defaults_on_only_when_cli_and_marketplace_plugin_detected() -> None:
    section = _capability_table_section()
    assert section, "Capability table not documented yet"
    row_match = re.search(r"`obsidian`.*", section)
    assert row_match, "Capability table must have an `obsidian` row"
    row = row_match.group(0)
    assert re.search(r"claude.{0,20}cli", row, re.IGNORECASE), (
        "`obsidian`'s default derivation must require the `claude` CLI to be present"
    )
    assert re.search(r"obsidian-skills|marketplace", row, re.IGNORECASE), (
        "`obsidian`'s default derivation must require the "
        "obsidian@obsidian-skills marketplace plugin to be present"
    )


def test_ci_defaults_off_unless_profile_all() -> None:
    section = _capability_table_section()
    assert section, "Capability table not documented yet"
    row_match = re.search(r"`ci`.*", section)
    assert row_match, "Capability table must have a `ci` row"
    row = row_match.group(0)
    assert re.search(r"\boff\b", row, re.IGNORECASE), (
        "`ci` must default off -- it is the only capability with out-of-band "
        "prerequisites (two `gh secret set` calls)"
    )
    assert re.search(r"profile.{0,10}all", row, re.IGNORECASE), (
        "`ci` must document turning on only under `--profile all`"
    )


def test_ml_defaults_on_iff_ml_signals_detected() -> None:
    section = _capability_table_section()
    assert section, "Capability table not documented yet"
    row_match = re.search(r"`ml`.*", section)
    assert row_match, "Capability table must have an `ml` row"
    row = row_match.group(0)
    assert re.search(r"ml signals?", row, re.IGNORECASE), (
        "`ml`'s default derivation must be conditioned on detected ML signals"
    )


def test_capability_to_phase_mapping_is_a_total_function_over_the_matrix() -> None:
    """Every phase id in the Mode x Phase Matrix resolves to exactly one capability.

    A capability vocabulary that silently omits a phase id -- or double-maps
    one -- breaks the "single join point" invariant the plan requires
    (dec-draft-113cc050): the internal phase grammar and the user-facing
    surface must agree on a total, unambiguous mapping.
    """
    section = _capability_table_section()
    assert section, "Capability table not documented yet"

    # Build capability_id -> {phase ids it covers}, from each row's "Phases" cell.
    mapping: dict[str, set[str]] = {}
    for capability_id in CAPABILITY_IDS:
        row_match = re.search(rf"`{re.escape(capability_id)}`\s*\|([^\n]*)", section)
        assert row_match, f"Capability table must have a `{capability_id}` row"
        cell = row_match.group(1)
        ids_in_cell = {token.strip("` .") for token in re.split(r"[,\s]+", cell) if token.strip()}
        mapping[capability_id] = {i for i in ids_in_cell if re.fullmatch(r"[0-9][0-9a-z.]*", i)}

    covered: dict[str, list[str]] = {}
    for capability_id, phase_ids in mapping.items():
        for phase_id in phase_ids:
            covered.setdefault(phase_id, []).append(capability_id)

    selectable_ids = [pid for pid in MODE_PHASE_MATRIX_IDS if pid not in _NOT_USER_SELECTABLE]
    missing = [pid for pid in selectable_ids if pid not in covered]
    assert not missing, (
        f"Mode x Phase Matrix phase id(s) {missing} are not covered by any "
        "capability -- the capability->phase mapping must be a total function "
        "over every user-selectable phase id"
    )
    ambiguous = {pid: caps for pid, caps in covered.items() if len(caps) > 1}
    assert not ambiguous, (
        f"Phase id(s) mapped to more than one capability: {ambiguous} -- the "
        "mapping must be unambiguous (each phase belongs to exactly one capability)"
    )
