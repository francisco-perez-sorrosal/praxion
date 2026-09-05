"""Regression tests for the placement axis across the onboarding phase matrix.

RED-first (BDD/TDD): as of this test's authoring, none of the
prose it checks for exists yet — `phases-core.md`, `phases-optional.md`,
`detection.md`, and `claude-md-blocks.md` carry no sidecar/placement
language, and no placement canonical-block variant is registered. Every test
below is expected to fail until the implementer's paired step lands the
placement axis described in §"Capability availability
under sidecar placement" and the `CLAUDE.md` placement-cases table.

**The phase-heading grammar itself must NOT change.** Placement is a
parameter of existing phases (`SYSTEMS_PLAN.md` § Risk Assessment) — it is
never expressed as a new phase id or a renumbering of an existing one. The
first two tests snapshot today's phase-id sets so any accidental
add/renumber/split fails loudly, independent of whichever placement prose
change accompanies it.

Prose assertions here are deliberately keyword/substring based (matching the
existing `test_onboard_block_mechanism.py` convention) — the implementer is
free to word sentences differently as long as the underlying invariant is
stated. This suite proves the phase matrix *says* the right thing; it does
not execute onboarding (that is `tests/consumer_layout/`'s job for the
mechanical predicates, and `scripts/test_onboard_project_placement.py`'s job
for the CLI subprocess surface).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PHASES_CORE = REPO_ROOT / "skills" / "onboard-project" / "references" / "phases-core.md"
PHASES_OPTIONAL = REPO_ROOT / "skills" / "onboard-project" / "references" / "phases-optional.md"
DETECTION = REPO_ROOT / "skills" / "onboard-project" / "references" / "detection.md"
CLAUDE_MD_BLOCKS = REPO_ROOT / "skills" / "onboard-project" / "references" / "claude-md-blocks.md"
CANONICAL_BLOCKS_DIR = REPO_ROOT / "claude" / "canonical-blocks"
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync_canonical_blocks.py"

_PHASE_ID = r"[0-9]+(?:\.5)?[a-z]?"

# Snapshot of today's phase-id sets (pre-Step-16). A renumbering, split, or a
# new phase id introduced to express placement — rather than placement
# landing as a parameter/subsection of an existing phase — must fail this
# test even though it says nothing about placement content itself.
CORE_PHASE_IDS_SNAPSHOT = ("0.5", "1", "2", "3", "4", "5", "5b", "6", "7", "9")
OPTIONAL_PHASE_IDS_SNAPSHOT = ("8", "8b", "8c", "8d", "8e")


def _phase_ids(text: str) -> tuple[str, ...]:
    return tuple(re.findall(rf"^## §Phase ({_PHASE_ID}) ", text, re.MULTILINE))


def _phase_section(text: str, phase_id: str) -> str:
    """One `## §Phase <id> ...` section body, heading to the next `## §Phase` or EOF."""
    match = re.search(
        rf"^## §Phase {re.escape(phase_id)} .*?(?=\n## §Phase |\Z)", text, re.DOTALL | re.MULTILINE
    )
    assert match, f"§Phase {phase_id} section not found"
    return match.group(0)


@pytest.fixture(scope="module")
def core_text() -> str:
    return PHASES_CORE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def optional_text() -> str:
    return PHASES_OPTIONAL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def detection_text() -> str:
    return DETECTION.read_text(encoding="utf-8")


# -- Phase-heading grammar is unchanged by the placement axis ---------------


def test_phases_core_phase_id_set_is_unchanged_by_the_placement_axis(core_text: str) -> None:
    assert _phase_ids(core_text) == CORE_PHASE_IDS_SNAPSHOT, (
        "phases-core.md's phase-id set moved — placement must land as a "
        "parameter of an existing phase, never as a new/renumbered phase id."
    )


def test_phases_optional_phase_id_set_is_unchanged_by_the_placement_axis(
    optional_text: str,
) -> None:
    assert _phase_ids(optional_text) == OPTIONAL_PHASE_IDS_SNAPSHOT, (
        "phases-optional.md's phase-id set moved — placement must land as a "
        "parameter of an existing phase, never as a new/renumbered phase id."
    )


# -- Phase 1: `.git/info/exclude` gains `/.praxion-state/` + shadow paths ---------


def test_phase_1_names_the_mount_exclude_entry_ahead_of_the_shadow_paths(
    core_text: str,
) -> None:
    section = _phase_section(core_text, "1")
    assert "/.praxion-state/" in section, (
        "Phase 1 must name the state-mount exclude entry `/.praxion-state/` "
        "(the exclude block and the state mount) — it heads the "
        ".git/info/exclude block under sidecar placement."
    )
    mount_index = section.index("/.praxion-state/")
    other_shadow_markers = ("/.ai-state", "/CLAUDE.local.md", "settings.local.json")
    later_markers = [
        m for m in other_shadow_markers if m in section and section.index(m) > mount_index
    ]
    assert later_markers, (
        "Phase 1 names /.praxion-state/ but not a single shadow path following it — "
        "the exclude block states /.praxion-state/ heads the block with the shadow entries after it."
    )


def test_phase_1_states_gitignore_stays_untouched_under_sidecar_placement(
    core_text: str,
) -> None:
    section = _phase_section(core_text, "1")
    assert "sidecar" in section.lower(), (
        "Phase 1 has no sidecar-placement clause at all — expected `.git/info/"
        "exclude` (not `.gitignore`) to be named as the sidecar target."
    )
    assert ".gitignore" in section, "Phase 1 must still name `.gitignore` explicitly."
    assert "untouched" in section.lower(), (
        "Phase 1 must state that `.gitignore` is left untouched under sidecar "
        "placement (info/exclude is per-clone; .gitignore is teammate-visible)."
    )


# -- Phase 2: `.ai-state/` skeleton gains `.gitkeep` seeding -----------------


def test_phase_2_names_gitkeep_seeding_for_the_sidecar_mount(core_text: str) -> None:
    # Phase 2 already mentions ".gitkeep" once, pre-Step-16 -- in the negative
    # ("no .gitkeep") ADR-drafts sub-step -- and already contains the word
    # "sidecar" once, pre-Step-16, in an unrelated feature (the healing
    # sidecar / `/report-praxion-issue` feedback ledger). Neither substring
    # alone can distinguish the placement-mount seeding this test targets
    # from that pre-existing content, so this test requires a SECOND
    # `.gitkeep` mention plus the unambiguous "mount" keyword (the state
    # mount's own vocabulary), which nothing pre-existing in this section uses.
    section = _phase_section(core_text, "2")
    gitkeep_mentions = section.count(".gitkeep")
    assert gitkeep_mentions >= 2, (
        "Phase 2 must additionally name `.gitkeep` seeding for the sidecar "
        "mount, beyond the pre-existing 'no .gitkeep' ADR-drafts mention — a "
        "`git worktree` materialises only tracked content, so every expected "
        ".ai-state/ subdirectory needs a real seeded file or a fresh mount is "
        "silently missing it (ARCH_WT_RULING.md §5's Seeding obligation)."
    )
    assert "mount" in section.lower(), (
        "Phase 2 must name the state 'mount' explicitly as the "
        "target the skeleton is seeded into under sidecar placement."
    )


def test_phase_2_names_the_mount_and_link_step_under_sidecar_placement(
    core_text: str,
) -> None:
    section = _phase_section(core_text, "2")
    assert "symlink" in section.lower() or "link" in section.lower(), (
        "Phase 2 must name the link/symlink step that projects the sidecar-"
        "created skeleton back into the checkout under sidecar placement."
    )


# -- Phase 3: merge-driver registration targets the sidecar's own config ----


def test_phase_3_registers_the_merge_driver_in_the_sidecars_own_config(
    core_text: str,
) -> None:
    section = _phase_section(core_text, "3")
    assert "sidecar" in section.lower(), (
        "Phase 3 has no sidecar-placement clause — the merge-driver "
        "registration (`git config`) must target the sidecar's own config "
        "under sidecar placement, not the project repository's."
    )


# -- Phase 6: the three-case `CLAUDE.md` placement table --------------------


def test_phase_6_carries_the_ds8_three_case_claude_md_placement_table(
    core_text: str,
) -> None:
    section = _phase_section(core_text, "6")
    assert "CLAUDE.local.md" in section, (
        "Phase 6 must name `CLAUDE.local.md` as the shadowed Praxion-block "
        "target when the project has a tracked CLAUDE.md (the `untouched` "
        "case)."
    )
    assert "--share" in section or "share" in section.lower(), (
        "Phase 6 must name the `--share CLAUDE.md` opt-in (the `share` case)."
    )
    assert "untouched" in section.lower(), (
        "Phase 6 must name the `untouched` case by name — a tracked "
        "CLAUDE.md that already exists is never written to."
    )


def test_phase_6_states_no_writer_targets_an_untouched_claude_md(core_text: str) -> None:
    # Phase 6 already uses "untouched" and "never" today, pre-Step-16, in two
    # unrelated contexts: the 4-state refreshable-block classifier's
    # `modified` case ("leaves the file untouched") and the block-class
    # predicate note ("never two for the same heading"). A bare
    # substring-anywhere-in-the-section check would pass on that pre-existing
    # prose alone, so this test anchors on `CLAUDE.local.md` (the placement-
    # cases vocabulary, absent from today's Phase 6) and requires the invariant
    # wording to appear in the same neighbourhood as that anchor.
    section = _phase_section(core_text, "6")
    assert "CLAUDE.local.md" in section, (
        "Phase 6 must name `CLAUDE.local.md` before this invariant can be "
        "meaningfully checked (see the placement three-case test above)."
    )
    anchor = section.index("CLAUDE.local.md")
    window = section[max(0, anchor - 500) : anchor + 500].lower()
    assert "untouched" in window, (
        "Phase 6 must state the `untouched` case near its CLAUDE.local.md "
        "mention, not only elsewhere in the phase (where 'untouched' already "
        "appears for the unrelated refreshable-block `modified` case)."
    )
    assert "never" in window, (
        "Phase 6 must state the invariant that no Praxion write path ever "
        "targets a CLAUDE.md whose intent is `untouched`, near its "
        "CLAUDE.local.md mention."
    )


# -- Phase 9: staging split + corrected verification next-steps -------------


def test_phase_9_states_the_staging_split_across_project_and_sidecar(core_text: str) -> None:
    section = _phase_section(core_text, "9")
    assert "sidecar" in section.lower(), (
        "Phase 9 has no sidecar-placement clause — staging must split "
        "project-side files (project repo) from sidecar-side files (sidecar "
        "repo)."
    )


def test_phase_9_corrects_the_git_status_verification_expectation(core_text: str) -> None:
    section = _phase_section(core_text, "9")
    lowered = section.lower()
    assert "git status" in lowered, "Phase 9 must still name `git status` in its next-steps."
    assert "no praxion" in lowered or "empty" in lowered, (
        "Phase 9's verification next-steps must state the corrected "
        "expectation under sidecar placement: `git status` shows NO Praxion "
        "files (that is the point) — an operator seeing a clean status must "
        "not conclude onboarding failed."
    )


# -- phases-optional.md: capability × placement table -----------------------

EXPECTED_LOCAL_CAPABILITIES = ("core", "observability", "arch", "ml")
EXPECTED_SHARE_GATED_CAPABILITIES = ("quality", "obsidian")
EXPECTED_UNAVAILABLE_CAPABILITIES = ("ci",)
EXPECTED_SHADOWED_CAPABILITIES = ("aac",)


def test_phases_optional_names_every_local_capability_under_sidecar_placement(
    optional_text: str,
) -> None:
    lowered = optional_text.lower()
    missing = [c for c in EXPECTED_LOCAL_CAPABILITIES if c not in lowered]
    assert not missing, (
        f"phases-optional.md's capability x placement table is missing local "
        f"capabilities: {missing}"
    )


def test_phases_optional_marks_ci_unavailable_with_a_one_line_reason(
    optional_text: str,
) -> None:
    lowered = optional_text.lower()
    assert "unavailable" in lowered, (
        "phases-optional.md must state that the `ci` capability is "
        "unavailable under sidecar placement — .github/workflows "
        "is GitHub-visible by construction, with no invisible variant."
    )


def test_phases_optional_marks_aac_shadowed_with_the_workflow_subsurface_dropped(
    optional_text: str,
) -> None:
    lowered = optional_text.lower()
    assert "shadow" in lowered, (
        "phases-optional.md must state that the `aac` capability is offered "
        "shadowed under sidecar placement — the Block D gate "
        "installs into the local hook chain only."
    )


def test_phases_optional_names_the_share_gated_file_lists_for_quality_and_obsidian(
    optional_text: str,
) -> None:
    # `quality` and `obsidian` are pre-existing phase names (8e, 8d) — a bare
    # substring check on those two words alone would already pass today. The
    # class name itself needs the unambiguous hyphenated term "share-gated"
    # (the SYSTEMS_PLAN.md capability table's own vocabulary; "share" alone
    # would false-positive on the pre-existing "shared-procedures.md" links).
    lowered = optional_text.lower()
    missing = [c for c in EXPECTED_SHARE_GATED_CAPABILITIES if c not in lowered]
    assert not missing, (
        f"phases-optional.md's capability x placement table is missing "
        f"share-gated capabilities: {missing}"
    )
    assert "share-gated" in lowered, (
        "phases-optional.md must name the share-gated class explicitly for "
        "`quality` and `obsidian` — offered with the exact tracked-file list "
        "named, confirmed or declined, never written silently."
    )


def test_phases_optional_states_the_no_silent_tracked_write_invariant(
    optional_text: str,
) -> None:
    # "confirm"/"confirmed" already appear today in two unrelated contexts
    # (the architect Phase 8 hand-off, the CI workflow-name resolution) — the
    # noun "confirmation" does not, so it is the unambiguous anchor here.
    lowered = optional_text.lower()
    assert "sidecar" in lowered, "phases-optional.md has no sidecar-placement clause at all."
    assert "confirmation" in lowered, (
        "phases-optional.md must state the invariant that no capability "
        "writes a tracked file under sidecar placement without a share "
        "intent or an explicit per-capability confirmation naming the files."
    )


# -- detection.md: state-4 predicate consults CLAUDE.local.md too -----------


def test_detection_partially_managed_predicate_names_claude_local_md(
    detection_text: str,
) -> None:
    """A sidecar-placed project's Praxion blocks live in
    `CLAUDE.local.md`, not `CLAUDE.md` — the state-4 predicate must consult
    both or a sidecar-placed project misclassifies as unmanaged."""
    match = re.search(r"^\|\s*4\s*\|\s*`partially-managed`\s*\|(.*)$", detection_text, re.MULTILINE)
    assert match, "detection.md's state-4 (`partially-managed`) predicate row not found"
    row = match.group(1)
    assert "CLAUDE.local.md" in row, (
        "detection.md's partially-managed predicate greps only CLAUDE.md — "
        "must also consult CLAUDE.local.md so a sidecar-placed, "
        "team-owned project is not misclassified as unmanaged."
    )
    assert "CLAUDE.md" in row, (
        "the predicate must still consult CLAUDE.md as before (unchanged clause)."
    )


# -- Canonical block: a new placement/sidecar variant is registered ---------


def _canonical_block_slugs() -> dict[str, object]:
    """Load `scripts/sync_canonical_blocks.py`'s `BLOCKS` registry.

    `scripts/` is placed on `sys.path` first — the module does a sibling
    `from canonical_block_identity import ...` that only resolves when its
    own directory is importable, exactly as it would be when the script runs
    normally as `python3 scripts/sync_canonical_blocks.py`. Using
    `importlib.import_module` (rather than `spec_from_file_location` +
    `exec_module` without registering in `sys.modules`) matters beyond
    caching: the module's dataclasses resolve `ClassVar` string annotations
    via `sys.modules[cls.__module__]`, which raises `AttributeError` on an
    unregistered module.
    """
    import importlib
    import sys

    scripts_dir = str(SYNC_SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    module = importlib.import_module("sync_canonical_blocks")
    return dict(module.BLOCKS)


# The 8 blocks registered before the placement axis lands. A 9th key
# matching the placement/sidecar naming pattern is that change's job to add.
KNOWN_PRE_STEP_16_SLUGS = frozenset(
    {
        "agent-pipeline",
        "compaction-guidance",
        "behavioral-contract",
        "praxion-process",
        "hackathon-mode",
        "project-essentials",
        "obsidian-integration",
        "commit-process",
    }
)


def test_a_placement_or_sidecar_canonical_block_variant_is_registered() -> None:
    blocks = _canonical_block_slugs()
    new_slugs = set(blocks) - KNOWN_PRE_STEP_16_SLUGS
    matching = [s for s in new_slugs if re.search(r"sidecar|placement", s)]
    assert matching, (
        "scripts/sync_canonical_blocks.py's BLOCKS registry carries no new "
        f"slug matching /sidecar|placement/ (new slugs seen: {sorted(new_slugs)}). "
        "the placement axis must register a canonical-block variant naming the mount and "
        "sidecar location."
    )


def test_the_new_canonical_block_file_exists_on_disk() -> None:
    blocks = _canonical_block_slugs()
    new_slugs = [
        s for s in set(blocks) - KNOWN_PRE_STEP_16_SLUGS if re.search(r"sidecar|placement", s)
    ]
    assert new_slugs, "no placement/sidecar canonical-block slug registered yet (see prior test)."
    missing = [s for s in new_slugs if not (CANONICAL_BLOCKS_DIR / f"{s}.md").exists()]
    assert not missing, f"registered slug(s) with no file on disk: {missing}"


def test_claude_md_blocks_embeds_the_new_placement_block(core_text: str) -> None:
    # core_text unused directly, but keeps this test module-scoped-fixture
    # consistent with its siblings; the embedding site is claude-md-blocks.md.
    del core_text
    blocks = _canonical_block_slugs()
    new_slugs = [
        s for s in set(blocks) - KNOWN_PRE_STEP_16_SLUGS if re.search(r"sidecar|placement", s)
    ]
    assert new_slugs, "no placement/sidecar canonical-block slug registered yet."
    text = CLAUDE_MD_BLOCKS.read_text(encoding="utf-8")
    headings = re.findall(r"^## §(.+?) Block\b", text, re.MULTILINE)
    normalized = {h.lower().replace(" ", "-") for h in headings}
    matches = [s for s in new_slugs if s in normalized]
    assert matches, (
        f"claude-md-blocks.md has no `## §... Block` heading matching the "
        f"registered slug(s) {new_slugs} — headings found: {headings}"
    )


def test_sync_canonical_blocks_check_passes() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"sync_canonical_blocks.py --check failed (drift between claude/"
        f"canonical-blocks/ and its embedding sites):\n{result.stdout}\n{result.stderr}"
    )


# -- Shipped-surface isolation: no ephemeral-artifact citations -------------
#
# Scoped to the placement-related prose the placement axis actually owns,
# not whole files. `phases-core.md`'s Phase 4 (git hooks — explicitly
# "unaffected" by the placement axis, per IMPLEMENTATION_PLAN.md) already
# carries a pre-existing draft-ADR citation from the earlier hook-chaining
# work; that is a real, separately-tracked violation of `rules/swe/
# shipped-artifact-isolation.md` (see LEARNINGS_test-engineer.md), but it is
# not something the placement axis's own Done-when criteria can close, and
# folding it into this regression suite would pin an unrelated pre-existing
# defect to the placement axis forever. The placement Phases (1, 2, 3, 6, 9)
# are scanned individually instead of the whole file.
PLACEMENT_PHASE_IDS_TO_SCAN = ("1", "2", "3", "6", "9")


def _new_canonical_block_files() -> list[Path]:
    try:
        blocks = _canonical_block_slugs()
    except Exception:
        return []
    new_slugs = [
        s for s in set(blocks) - KNOWN_PRE_STEP_16_SLUGS if re.search(r"sidecar|placement", s)
    ]
    return [
        CANONICAL_BLOCKS_DIR / f"{s}.md"
        for s in new_slugs
        if (CANONICAL_BLOCKS_DIR / f"{s}.md").exists()
    ]


def _isolation_targets() -> list[tuple[str, str]]:
    """(label, text) pairs to scan: placement phases (not whole files) from
    `phases-core.md`, plus the wholly-in-scope files and the new block."""
    targets: list[tuple[str, str]] = []
    if PHASES_CORE.exists():
        text = PHASES_CORE.read_text(encoding="utf-8")
        for phase_id in PLACEMENT_PHASE_IDS_TO_SCAN:
            match = re.search(
                rf"^## §Phase {re.escape(phase_id)} .*?(?=\n## §Phase |\Z)",
                text,
                re.DOTALL | re.MULTILINE,
            )
            if match:
                targets.append((f"phases-core.md §Phase {phase_id}", match.group(0)))
    for path in (PHASES_OPTIONAL, DETECTION, CLAUDE_MD_BLOCKS, *_new_canonical_block_files()):
        if path.exists():
            targets.append((path.name, path.read_text(encoding="utf-8")))
    return targets


@pytest.mark.parametrize(
    ("label", "text"),
    _isolation_targets(),
    ids=[label for label, _ in _isolation_targets()],
)
def test_placement_prose_cites_no_ephemeral_pipeline_identifiers(label: str, text: str) -> None:
    """Skills and canonical blocks are shipped into every managed project —
    the placement prose must not cite this pipeline's ephemeral
    `.ai-work/`/`.ai-state/` entries (a `dec-draft-` fragment id, a concrete
    `dec-NNN`, or the `ARCH_WT_RULING.md` filename), per `rules/swe/
    shipped-artifact-isolation.md`. Such a citation dangles the moment the
    plugin lands in another project."""
    assert "dec-draft-" not in text, f"{label} cites an unfinalized dec-draft- id"
    assert not re.search(r"\bdec-[0-9]{3}\b", text), f"{label} cites a concrete dec-NNN id"
    assert "ARCH_WT_RULING" not in text, (
        f"{label} cites the ephemeral ARCH_WT_RULING.md pipeline doc"
    )
