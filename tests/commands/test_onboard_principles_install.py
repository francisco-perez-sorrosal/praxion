"""Structural tests for the principles.yaml §Phase 2 onboarding sub-step.

`/onboard-project` (now `skills/onboard-project/SKILL.md` + its phase-body
references) is executed by a live Claude Code session — it cannot be invoked
from pytest. These tests validate the documented contract by parsing
`skills/onboard-project/references/phases-core.md` structurally, matching the
precedent of `tests/commands/test_onboard_consult_ledgers_install.py`.

The gap these guard against is invisible from inside Praxion: Praxion's own
`.ai-state/principles.yaml` exists, so the planner's Phase 1b threading and the
verifier's Phase 4.5 gating fire here while staying silent in every managed
project. The mechanism's consumers ship with the plugin; this seed is what
activates them — without it, the beautiful-code dimensions are documentation,
not a gate, exactly where Praxion is supposed to apply them most.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
ONBOARD_FILE = REPO_ROOT / "skills" / "onboard-project" / "references" / "phases-core.md"
TEMPLATE_FILE = REPO_ROOT / "claude" / "project-baseline" / "principles.yaml.tmpl"

PRINCIPLES_PATH = ".ai-state/principles.yaml"

EXPECTED_DIMENSION_IDS = {
    "beauty-storytelling",
    "beauty-simplicity",
    "beauty-clarity-of-intent",
    "beauty-expressiveness",
    "beauty-purity",
    "beauty-sustainability",
    "beauty-durability",
    "beauty-creativity",
}


def _phase_2_section() -> str:
    """Return the '## §Phase 2' section body, up to the next '## ' heading."""
    body = ONBOARD_FILE.read_text(encoding="utf-8")
    match = re.search(r"##\s+§Phase 2 .*?(?=\n## |\Z)", body, re.DOTALL)
    return match.group(0) if match else ""


def _substep_block() -> str:
    """Return the principles sub-step text from its bullet to the next top-level item."""
    section = _phase_2_section()
    idx = section.find(f"`{PRINCIPLES_PATH}`")
    assert idx != -1, f"§Phase 2 must document seeding {PRINCIPLES_PATH}"
    return section[idx : idx + 3000]


def test_phase_2_documents_the_principles_seed() -> None:
    section = _phase_2_section()
    assert section, "§Phase 2 section not found in commands/onboard-project.md"
    assert PRINCIPLES_PATH in section, (
        f"§Phase 2 must seed {PRINCIPLES_PATH}: the planner Phase 1b / verifier "
        "Phase 4.5 consumers ship with the plugin, so a managed project without "
        "the seed has gating machinery that never fires."
    )


def test_substep_references_the_canonical_template_asset() -> None:
    block = _substep_block()
    assert "claude/project-baseline/principles.yaml.tmpl" in block, (
        "The sub-step must copy from the canonical single-sourced template, "
        "never inline a second copy of the eight principles."
    )
    assert TEMPLATE_FILE.exists(), (
        "The referenced template asset must exist — a documented copy source "
        "that is absent leaves onboarding unable to install the seed."
    )


def test_substep_skips_without_overwriting_when_file_exists() -> None:
    block = _substep_block()
    predicate = re.search(r"\*\*Predicate.*?\*\*.*?(?=\n\s*\*\*Action|\Z)", block, re.DOTALL)
    assert predicate, "The principles sub-step must document a Predicate (skip-if-exists guard)"
    assert re.search(r"skip|never overwrit", predicate.group(0), re.IGNORECASE), (
        "Predicate must document skipping — an existing principles.yaml holds the "
        "project's own edited statements, scopes, and severities."
    )


def test_template_parses_through_the_real_loader_with_eight_advisory_rows() -> None:
    """The seed must satisfy the loader contract its consumers actually use."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from principles_loader import load_principles

    principles = load_principles(TEMPLATE_FILE)
    ids = {p["id"] for p in principles}
    assert ids == EXPECTED_DIMENSION_IDS, (
        f"Template must carry exactly the eight beautiful-code dimensions; got {sorted(ids)}"
    )
    non_advisory = [p["id"] for p in principles if p["severity"] != "advisory"]
    assert not non_advisory, (
        f"Seed rows must all ship advisory (WARN, never FAIL) — promotion to blocking "
        f"is the project's decision, not the seed's: {non_advisory}"
    )


def test_completion_manifest_lists_the_principles_artifact() -> None:
    body = ONBOARD_FILE.read_text(encoding="utf-8")
    assert f'"principles": "{PRINCIPLES_PATH}"' in body, (
        "The completion manifest example must list the principles seed so the "
        "installed-artifact record stays complete."
    )


def test_template_cites_no_praxion_local_decision_records() -> None:
    """Shipped artifacts must not reference this repo's own .ai-state entries."""
    text = TEMPLATE_FILE.read_text(encoding="utf-8")
    assert not re.search(r"dec-\d{3}", text), (
        "principles.yaml.tmpl ships into managed projects, where a concrete "
        "dec-NNN reference dangles (shipped-artifact isolation)."
    )
