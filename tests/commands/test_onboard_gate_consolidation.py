"""Structural tests for the onboarding gate consolidation (25 fires -> 3 gates).

`skills/onboard-project/SKILL.md` is a Claude Code skill body (Markdown,
`disable-model-invocation` eventually true) — it cannot be invoked from
pytest. These tests validate the documented contract by parsing the skill
file structurally, matching the precedent set by
`tests/commands/test_onboard_ci_autofix_install.py`.

`SKILL.md` publishes the 3-gate policy (G1 mode-confirm / G2 build-intent /
G3 profile) per `INTERFACE_DESIGN.md §3.3`; the old 25-gate-fire surface
(one `AskUserQuestion` pause per phase plus the one-way `Run all rest`
escape hatch) is retired.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_FILE = Path(__file__).parents[2] / "skills" / "onboard-project" / "SKILL.md"
PHASES_FILES = (
    Path(__file__).parents[2] / "skills" / "onboard-project" / "references" / "phases-core.md",
    Path(__file__).parents[2] / "skills" / "onboard-project" / "references" / "phases-optional.md",
)

# The three surviving gates, per INTERFACE_DESIGN.md §3.3.
_GATE_NAMES = ("mode confirm", "build intent", "profile")

# Interaction machinery that belongs only to the driver (SKILL.md) and
# detection.md -- a phase body that fires its own AskUserQuestion, checks a
# no-more-gates flag, or offers "Run all rest" contradicts the 3-gate policy
# even when SKILL.md itself is correct (the two-textual-sites anti-pattern).
_INTERACTION_MACHINERY = ("AskUserQuestion", "no-more-gates", "Run all rest")


def _skill_body() -> str:
    """Return the full SKILL.md content (read lazily so collection succeeds)."""
    return SKILL_FILE.read_text(encoding="utf-8")


def _gates_section() -> str:
    """Return the gate-policy section body (whatever heading the skill gives it).

    Anchored loosely on 'Gate' so this survives the implementer choosing
    '## §Gates' vs '## §Phase Gates' vs a renamed heading — the behavioral
    contract under test is the gate *count* and *names*, not the heading text.
    """
    # Two-step extraction rather than one combined regex: MULTILINE's `^`/`$`
    # anchors and DOTALL's newline-matching `.` are mutually defeating in a
    # single pattern -- a DOTALL `.*` before "Gate" greedily walks past the
    # first heading match and re-anchors on whichever heading contains the
    # *last* "Gate" occurrence in the whole document, not the first one.
    body = _skill_body()
    heading = re.search(r"^##\s*.*Gate.*$", body, re.MULTILINE)
    if not heading:
        return ""
    rest = body[heading.start() :]
    next_heading = re.search(r"\n##\s", rest)
    return rest[: next_heading.start()] if next_heading else rest


def test_gate_table_collapses_to_exactly_three_gates() -> None:
    section = _gates_section()
    assert section, "SKILL.md must carry a gate-policy section"
    gate_ids = set(re.findall(r"\bG[123]\b", section))
    assert gate_ids == {"G1", "G2", "G3"}, (
        f"Expected exactly the three surviving gates G1/G2/G3, found {gate_ids or 'none'} "
        "-- the old per-phase gate table (Gates 0.5, 1-8e) must be retired"
    )
    for name in _GATE_NAMES:
        assert re.search(name, section, re.IGNORECASE), (
            f"Gate policy section must name the '{name}' gate (INTERFACE_DESIGN.md §3.3)"
        )


def test_run_all_rest_escape_hatch_is_retired() -> None:
    section = _gates_section()
    assert section, "SKILL.md must carry a gate-policy section"
    assert not re.search(r"run all rest", section, re.IGNORECASE), (
        "The one-way 'Run all rest' escape hatch must be retired -- with three "
        "gates there is nothing left to escape (INTERFACE_DESIGN.md §3.3)"
    )


def test_per_phase_gates_no_longer_pause_between_every_phase() -> None:
    """Regression guard: the old per-phase-1-through-8e AskUserQuestion table."""
    section = _gates_section()
    assert section, "SKILL.md must carry a gate-policy section"
    old_per_phase_headline_count = len(re.findall(r"Phase\s+\d+(?:\.\d+)?[a-z]?\s+of\s+9", section))
    assert old_per_phase_headline_count == 0, (
        "Gate section must not retain the old 'Phase N of 9' per-phase gate "
        f"headlines ({old_per_phase_headline_count} found) -- 25 fires collapse to 3"
    )


def test_g1_mode_confirm_fires_only_on_ambiguous_or_hackathon_detection() -> None:
    section = _gates_section()
    assert section, "SKILL.md must carry a gate-policy section"
    g1_match = re.search(r"\bG1\b.*?(?=\bG2\b|\Z)", section, re.DOTALL)
    assert g1_match, "Gate policy section must document G1"
    g1 = g1_match.group(0)
    assert re.search(r"ambiguous", g1, re.IGNORECASE), (
        "G1 (Mode confirm) must fire only when detection is ambiguous (INTERFACE_DESIGN.md §3.3)"
    )
    assert re.search(r"hackathon", g1, re.IGNORECASE), (
        "G1 (Mode confirm) must also fire when a hackathon/promote state is "
        "detected with no mode flag"
    )


def test_g2_build_intent_fires_only_in_new_mode() -> None:
    section = _gates_section()
    assert section, "SKILL.md must carry a gate-policy section"
    g2_match = re.search(r"\bG2\b.*?(?=\bG3\b|\Z)", section, re.DOTALL)
    assert g2_match, "Gate policy section must document G2"
    g2 = g2_match.group(0)
    assert re.search(r"\bnew\b", g2, re.IGNORECASE), (
        "G2 (Build intent) must be scoped to `new` mode only"
    )
    assert re.search(r"brief|--yes", g2, re.IGNORECASE), (
        "G2 (Build intent) must document its bypass via --brief or --yes"
    )


def test_phase_bodies_carry_no_interaction_machinery_of_their_own() -> None:
    """Regression guard: gate consolidation must not stop at the driver.

    `SKILL.md` can correctly declare a 3-gate policy while the phase bodies
    in phases-core.md/phases-optional.md still fire their own
    `AskUserQuestion`, check a `no-more-gates` flag, or offer a `Run all
    rest` escape hatch -- contradicting the driver from underneath it (two
    textual sites disagreeing about who owns interaction). The driver +
    detection.md are the only interaction sites; a phase body declares only
    its selection binding (a capability row or a mode/flag) and keeps its
    write-set semantics.
    """
    for phases_file in PHASES_FILES:
        body = phases_file.read_text(encoding="utf-8")
        for marker in _INTERACTION_MACHINERY:
            assert marker not in body, (
                f"{phases_file.name} must not contain {marker!r} -- phase bodies "
                "declare a selection binding only; all interaction is owned by "
                "SKILL.md's 3-gate policy (and detection.md's guards)"
            )


def test_g3_profile_fires_once_before_any_write() -> None:
    section = _gates_section()
    assert section, "SKILL.md must carry a gate-policy section"
    g3_match = re.search(r"\bG3\b.*", section, re.DOTALL)
    assert g3_match, "Gate policy section must document G3"
    g3 = g3_match.group(0)
    assert re.search(r"multi.?select", g3, re.IGNORECASE), (
        "G3 (Profile) must be a multiSelect AskUserQuestion, pre-checked from detection"
    )
    assert re.search(r"before any write|before.{0,20}write", g3, re.IGNORECASE), (
        "G3 (Profile) must fire once, before any write"
    )
