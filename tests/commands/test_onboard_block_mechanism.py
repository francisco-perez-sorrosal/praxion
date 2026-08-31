"""Successor to hooks/test_onboard_praxion_block.py after the onboarding unification.

That file parsed commands/onboard-project.md and commands/new-project.md — both
retired by the atomic cut — and mostly asserted byte-identity of canonical blocks
across the two commands, a duplication the unification removed (the blocks now
have one embedding site, checked against claude/canonical-blocks/ by
scripts/sync_canonical_blocks.py --check). Two guards remain meaningful and live
here: Phase 6 must delegate refreshable-block idempotency to the 4-state
classifier, and no other phase body may grow a second block-append mechanism.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PHASES_CORE = REPO_ROOT / "skills" / "onboard-project" / "references" / "phases-core.md"
SEED_PIPELINE = REPO_ROOT / "skills" / "onboard-project" / "references" / "seed-pipeline.md"
PHASES_OPTIONAL = REPO_ROOT / "skills" / "onboard-project" / "references" / "phases-optional.md"

REFRESHABLE_BLOCK_NAMES = (
    "Agent Pipeline",
    "Compaction Guidance",
    "Behavioral Contract",
    "Praxion Process",
)


def _phase_6_section() -> str:
    text = PHASES_CORE.read_text(encoding="utf-8")
    start = text.index("## §Phase 6")
    tail = text[start + 1 :]
    end = tail.find("\n## §Phase ")
    return text[start : start + 1 + end] if end != -1 else text[start:]


def test_phase_6_delegates_refreshable_blocks_to_the_4_state_classifier():
    section = _phase_6_section()
    assert "refresh_claude_blocks.py" in section, (
        "Phase 6 must delegate the four refreshable blocks to the 4-state "
        "classifier — the sole idempotency mechanism after the D2 dedup."
    )


def test_phase_6_names_every_refreshable_block():
    section = _phase_6_section()
    missing = [n for n in REFRESHABLE_BLOCK_NAMES if n not in section]
    assert not missing, f"Phase 6 no longer names refreshable blocks: {missing}"


def test_seed_pipeline_only_cites_phase_6_for_the_refresh_mechanism():
    """seed-pipeline.md may reference refresh_claude_blocks.py only while
    citing Phase 6 as its owner — a mention outside a Phase 6 citation is a
    second block-append mechanism growing back (the D2 regression)."""
    lines = SEED_PIPELINE.read_text(encoding="utf-8").splitlines()
    offenders = [
        line for line in lines if "refresh_claude_blocks.py" in line and "Phase 6" not in line
    ]
    assert not offenders, (
        "seed-pipeline.md runs the refresh mechanism instead of citing "
        f"Phase 6 as its owner: {offenders}"
    )


def test_no_flat_grep_block_predicate_outside_phase_6():
    """The retired /new-project mechanism probed refreshable blocks with flat
    heading-greps; only Phase 6 may state block-presence predicates for the
    four refreshable headings."""
    for path in (SEED_PIPELINE, PHASES_OPTIONAL):
        text = path.read_text(encoding="utf-8")
        offenders = [n for n in REFRESHABLE_BLOCK_NAMES if f"grep -q '^## {n}$'" in text]
        assert not offenders, (
            f"{path.name} carries a flat-grep predicate for {offenders} — "
            "that mechanism was deleted with the D2 dedup."
        )
