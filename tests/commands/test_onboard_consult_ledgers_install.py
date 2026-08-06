"""Structural tests for the consult-ledger §Phase 2 onboarding sub-step.

`/onboard-project` is a slash command (Markdown body executed by a live Claude
Code session) — it cannot be invoked from pytest. These tests validate the
documented contract by parsing `commands/onboard-project.md` structurally,
matching the precedent set by `tests/commands/test_onboard_praxion_feedback_install.py`.

The gap these guard against is invisible from inside Praxion: Praxion's own
`.ai-state/` already holds the three consult ledgers, so a consult convened here
succeeds while the same consult in a freshly-onboarded project would be told to
append to files that do not exist. The consult mechanism's producer (the
`discipline-consultant` agent and `/consult`) ships with the plugin; these
skeletons are its consumer.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
ONBOARD_FILE = REPO_ROOT / "commands" / "onboard-project.md"
NEW_PROJECT_FILE = REPO_ROOT / "commands" / "new-project.md"

LEDGER_PATHS = (
    ".ai-state/CONSULT_LEDGER.md",
    ".ai-state/CONSULT_COSTS.md",
    ".ai-state/CONSULT_PRIORS.md",
)

# Table-row counts per skeleton: a header row plus its separator, per table.
# CONSULT_PRIORS carries two tables (Sealed Priors, Challenge Classification).
EXPECTED_TABLE_LINES = {
    ".ai-state/CONSULT_LEDGER.md": 2,
    ".ai-state/CONSULT_COSTS.md": 2,
    ".ai-state/CONSULT_PRIORS.md": 4,
}


def _onboard_body() -> str:
    """Return the full onboard-project.md content (read lazily so collection succeeds)."""
    return ONBOARD_FILE.read_text(encoding="utf-8")


def _phase_2_section() -> str:
    """Return the '## §Phase 2' section body, up to the next '## ' heading.

    A fixed heading-to-heading window keeps assertions scoped to this phase's
    own text and unable to pass vacuously against a neighboring phase.
    """
    match = re.search(r"##\s+§Phase 2 .*?(?=\n## |\Z)", _onboard_body(), re.DOTALL)
    return match.group(0) if match else ""


def _skeleton_block(path: str) -> str:
    """Return the fenced Markdown skeleton that follows the given ledger path.

    Locating the fence by the path that introduces it — rather than by ordinal
    position — keeps the helper stable if the bullets are ever reordered.
    """
    section = _phase_2_section()
    idx = section.find(f"`{path}`:")
    assert idx != -1, f"§Phase 2 must introduce a skeleton for {path}"
    fence = re.search(r"```markdown\n(.*?)```", section[idx:], re.DOTALL)
    assert fence, f"The {path} bullet must be followed by a fenced markdown skeleton"
    return fence.group(1)


def test_phase_2_documents_all_three_consult_ledger_skeletons() -> None:
    section = _phase_2_section()
    assert section, "§Phase 2 section not found in commands/onboard-project.md"
    missing = [path for path in LEDGER_PATHS if path not in section]
    assert not missing, (
        f"§Phase 2 must document creating these consult ledgers as skeletons: {missing}. "
        "The consult producer ships globally, so a managed project without them has a "
        "convener instructed to append to files that do not exist."
    )


def test_skips_without_overwriting_when_a_ledger_already_exists() -> None:
    section = _phase_2_section()
    idx = section.find(LEDGER_PATHS[0])
    assert idx != -1, "consult-ledger sub-step not documented yet"
    following = section[idx : idx + 2000]
    predicate = re.search(r"\*\*Predicate.*?\*\*.*?(?=\n\s*\*\*Action|\Z)", following, re.DOTALL)
    assert predicate, "The consult-ledger sub-step must document a Predicate (skip-if-exists guard)"
    body = predicate.group(0)
    assert re.search(r"skip|never overwrit", body, re.IGNORECASE), (
        "Predicate must document skipping — an existing ledger already holds committed, "
        "append-only rows and must never be overwritten"
    )


def test_skeletons_are_header_only_with_no_seeded_data_row() -> None:
    """A fabricated row is indistinguishable from a real observation.

    These ledgers are read as data series, so any seeded example row permanently
    contaminates every count computed over them. Each table must ship with its
    header and separator only.
    """
    for path, expected in EXPECTED_TABLE_LINES.items():
        block = _skeleton_block(path)
        table_lines = [line for line in block.splitlines() if line.strip().startswith("|")]
        assert len(table_lines) == expected, (
            f"{path} skeleton must contain exactly {expected} table line(s) "
            f"(header + separator per table), found {len(table_lines)}: {table_lines}"
        )
        separators = [line for line in table_lines if set(line.strip()) <= set("|- ")]
        assert len(separators) * 2 == expected, (
            f"{path} skeleton's table lines must pair one separator per header row — "
            "any extra row is a seeded observation"
        )


def test_each_skeleton_carries_its_own_column_definitions() -> None:
    """The convening instructions cite `<file> § Column Definitions` as the schema.

    Each ledger is therefore its own schema anchor; a skeleton that omits the
    section leaves that pointer dangling in every managed project.
    """
    for path in LEDGER_PATHS:
        block = _skeleton_block(path)
        assert "## Column Definitions" in block, (
            f"{path} skeleton must ship a '## Column Definitions' section — the consult "
            "convener is instructed to read it as the schema"
        )


def test_skeletons_cite_no_praxion_local_decision_records() -> None:
    """Shipped artifacts must not reference this repo's own `.ai-state/` entries.

    A `dec-NNN` embedded in a scaffolded file dangles the moment it lands in
    someone else's project. Rationale belongs inline, in words.
    """
    for path in LEDGER_PATHS:
        block = _skeleton_block(path)
        assert not re.search(r"\bdec-\d{2,}\b", block), (
            f"{path} skeleton cites a concrete decision-record id; state the rationale "
            "inline instead — the id does not resolve in a managed project"
        )


def test_new_project_gains_no_duplicate_install_logic() -> None:
    """`/new-project` defers every `.ai-state/` skeleton install to `/onboard-project`.

    Mirrors the same guard already pinned for the praxion_feedback ledger, so the
    consult skeletons cannot silently acquire a second install path.
    """
    body = NEW_PROJECT_FILE.read_text(encoding="utf-8")
    assert body.count("CONSULT_") == 0, (
        "commands/new-project.md must not gain its own copy of the consult-ledger "
        "install logic — installs stay deferred to /onboard-project, matching the "
        "established single-install-path convention"
    )
