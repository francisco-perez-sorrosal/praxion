"""Tests for all four canonical CLAUDE.md blocks in onboard-project.md and new-project.md.

Behavioral coverage:
  - Each of the four §<Block> Block sections exists in commands/onboard-project.md
  - Each of the four §<Block> Block sections exists in commands/new-project.md
  - Each block's fenced content is byte-identical between both command files
  - Each block's injectable heading matches the heading the idempotency predicate checks
  - Each block's fenced content is byte-identical to the corresponding canonical file
  - Each block contains no .ai-state/ or .ai-work/ identifiers (shipped artifact isolation)
  - Each block stays under the ~250-token budget (bytes/3.6 conservative estimate)

Praxion Process block additionally tests:
  - Block contains tier-selector / pipeline principle reference
  - Block contains rule-inheritance corollary (subagent delegation)
  - Block contains trivial-vs-non-trivial threshold reference
  - Block contains orchestrator delegation obligation reference
  - Idempotency predicate prevents duplicate insertion on a second Phase 6 run

Canonical-file byte-identity tests:
  - These tests are expected to be RED until `claude/canonical-blocks/<slug>.md` files
    are created by the concurrent implementer. They transition to GREEN at the
    Group A integration checkpoint.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ONBOARD_PATH = REPO_ROOT / "commands" / "onboard-project.md"
NEW_PROJECT_PATH = REPO_ROOT / "commands" / "new-project.md"
CANONICAL_BLOCKS_DIR = REPO_ROOT / "claude" / "canonical-blocks"

# Token budget ceiling (conservative Praxion convention: bytes / 3.6)
TOKEN_BUDGET = 250

# ---------------------------------------------------------------------------
# Block registry
#
# Each entry maps a block slug to:
#   - section_heading:  the '## §...' heading anchoring the block in command files
#   - claude_md_heading: the injectable heading the idempotency predicate checks
#   - canonical_file:   filename under claude/canonical-blocks/
# ---------------------------------------------------------------------------

BLOCKS: dict[str, dict[str, str]] = {
    "agent-pipeline": {
        "section_heading": "## §Agent Pipeline Block",
        "claude_md_heading": "## Agent Pipeline",
        "canonical_file": "agent-pipeline.md",
    },
    "compaction-guidance": {
        "section_heading": "## §Compaction Guidance Block",
        "claude_md_heading": "## Compaction Guidance",
        "canonical_file": "compaction-guidance.md",
    },
    "behavioral-contract": {
        "section_heading": "## §Behavioral Contract Block",
        "claude_md_heading": "## Behavioral Contract",
        "canonical_file": "behavioral-contract.md",
    },
    "praxion-process": {
        "section_heading": "## §Praxion Process Block",
        "claude_md_heading": "## Praxion Process",
        "canonical_file": "praxion-process.md",
    },
}

# Forbidden patterns for shipped-artifact isolation.
#
# Per rules/swe/shipped-artifact-isolation.md: path *shapes* (e.g. `.ai-state/`,
# `.ai-work/<slug>/`) are fine and encouraged — they describe conventions that users
# need to understand. What is forbidden is embedding *specific entries* that dangle
# when the plugin lands in a different project. Only specific-entry patterns are listed.
FORBIDDEN_PATTERNS = [
    r"dec-\d{3,}",  # specific ADR entries like dec-001, dec-042
    r"SPEC_\w+_\d{4}-\d{2}-\d{2}",  # specific archived spec files
    r"SENTINEL_REPORT_\d{4}-\d{2}-\d{2}",  # specific sentinel report files
    r"IDEA_LEDGER_\d{4}-\d{2}-\d{2}",  # specific idea ledger files
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_command_file(path: Path) -> str:
    """Read a command file, asserting it exists."""
    assert path.exists(), f"Command file not found: {path}"
    return path.read_text(encoding="utf-8")


def _extract_block_section(content: str, section_heading: str) -> str:
    """Extract the content of a §<Block> Block section from a command file.

    The section starts at the given section_heading (e.g., '## §Agent Pipeline Block')
    and ends at the next '## §' heading (or end of file).

    Returns the extracted section text (including the heading line), rstripped.
    Raises AssertionError if the section is absent.
    """
    escaped = re.escape(section_heading)
    match = re.search(rf"^{escaped}\b.*$", content, re.MULTILINE)
    assert (
        match is not None
    ), f"Heading '{section_heading}' not found in content (first 200 chars: {content[:200]!r})"
    start = match.start()

    # Find where the next canonical-block section heading begins (or EOF).
    # Canonical-block sections all use the '## §' prefix; matching plain '## '
    # would falsely terminate at inner injectable headings like '## Agent Pipeline'.
    next_heading = re.search(r"^## §", content[match.end() :], re.MULTILINE)
    if next_heading is None:
        end = len(content)
    else:
        end = match.end() + next_heading.start()

    return content[start:end].rstrip()


def _extract_fenced_content(content: str, section_heading: str) -> str:
    """Extract the raw fenced-block content from a §<Block> Block section.

    Finds the first ```markdown fence after the section_heading and returns
    the content between the fence opener and its matching ``` closer —
    without the fence delimiters. Trailing whitespace is preserved; the result
    ends with a newline if the original does.

    Raises AssertionError if the fence is absent or the section is missing.
    """
    section = _extract_block_section(content, section_heading)

    fence_open = re.search(r"^```markdown\s*$", section, re.MULTILINE)
    assert fence_open is not None, (
        f"No ```markdown fence found inside '{section_heading}' section. "
        f"Section content:\n{section[:300]!r}"
    )
    content_start = fence_open.end()

    # Find the matching closing ``` (must be at line-start)
    fence_close = re.search(r"^```\s*$", section[content_start:], re.MULTILINE)
    assert (
        fence_close is not None
    ), f"No closing ``` fence found after ```markdown in '{section_heading}' section."
    content_end = content_start + fence_close.start()

    # Strip only the leading newline introduced by the fence opener line ending
    raw = section[content_start:content_end]
    if raw.startswith("\n"):
        raw = raw[1:]
    return raw


def _extract_inline_block(content: str, section_heading: str, claude_md_heading: str) -> str:
    """Extract the injectable prose that will be written into user CLAUDE.md.

    Starting from the claude_md_heading inside the section, returns from there
    to the next '## ' heading or end of the section. This is the block as a
    user would see it in their CLAUDE.md.
    """
    section = _extract_block_section(content, section_heading)
    escaped = re.escape(claude_md_heading)
    match = re.search(rf"^{escaped}\b.*$", section, re.MULTILINE)
    assert match is not None, f"'{claude_md_heading}' not found inside '{section_heading}' section"
    start = match.start()

    next_heading = re.search(r"^## ", section[match.end() :], re.MULTILINE)
    if next_heading is None:
        end = len(section)
    else:
        end = match.end() + next_heading.start()

    return section[start:end].rstrip()


# ---------------------------------------------------------------------------
# Parameterized block-presence tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_block_section_exists_in_onboard_project(slug: str, block_meta: dict) -> None:
    """Each canonical block section heading must exist in onboard-project.md."""
    content = _read_command_file(ONBOARD_PATH)
    heading = block_meta["section_heading"]
    assert (
        heading in content
    ), f"'{heading}' not found in {ONBOARD_PATH.name}. The {slug} block section is missing."


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_block_section_exists_in_new_project(slug: str, block_meta: dict) -> None:
    """Each canonical block section heading must exist in new-project.md."""
    content = _read_command_file(NEW_PROJECT_PATH)
    heading = block_meta["section_heading"]
    assert (
        heading in content
    ), f"'{heading}' not found in {NEW_PROJECT_PATH.name}. The {slug} block section is missing."


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_injectable_heading_present_in_onboard_project_block(slug: str, block_meta: dict) -> None:
    """Each §<Block> Block section in onboard-project.md must contain its injectable heading."""
    content = _read_command_file(ONBOARD_PATH)
    section = _extract_block_section(content, block_meta["section_heading"])
    assert block_meta["claude_md_heading"] in section, (
        f"'{block_meta['claude_md_heading']}' not found inside "
        f"'{block_meta['section_heading']}' section in {ONBOARD_PATH.name}."
    )


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_injectable_heading_present_in_new_project_block(slug: str, block_meta: dict) -> None:
    """Each §<Block> Block section in new-project.md must contain its injectable heading."""
    content = _read_command_file(NEW_PROJECT_PATH)
    section = _extract_block_section(content, block_meta["section_heading"])
    assert block_meta["claude_md_heading"] in section, (
        f"'{block_meta['claude_md_heading']}' not found inside "
        f"'{block_meta['section_heading']}' section in {NEW_PROJECT_PATH.name}."
    )


# ---------------------------------------------------------------------------
# Byte-identical mirror constraint (all four blocks)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_fenced_content_is_byte_identical_between_both_command_files(
    slug: str, block_meta: dict
) -> None:
    """Each block's fenced content must be byte-identical between both command files.

    Any drift means users onboarded via different paths receive different standing
    instructions in their CLAUDE.md.
    """
    onboard_content = _read_command_file(ONBOARD_PATH)
    new_project_content = _read_command_file(NEW_PROJECT_PATH)

    onboard_fenced = _extract_fenced_content(onboard_content, block_meta["section_heading"])
    new_project_fenced = _extract_fenced_content(new_project_content, block_meta["section_heading"])

    assert onboard_fenced == new_project_fenced, (
        f"'{block_meta['section_heading']}' fenced content is NOT byte-identical "
        f"between command files.\n"
        f"onboard-project.md ({len(onboard_fenced)} chars):\n{onboard_fenced[:300]!r}\n\n"
        f"new-project.md ({len(new_project_fenced)} chars):\n{new_project_fenced[:300]!r}"
    )


# ---------------------------------------------------------------------------
# Canonical-file byte-identity assertions
#
# These tests will be RED until `claude/canonical-blocks/<slug>.md` files are
# created by the implementer. They transition to GREEN once the canonical files
# exist and their content matches the embedded fenced blocks in the command files.
# This is the primary regression guarantee for the extraction refactor.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_fenced_content_matches_canonical_file_byte_for_byte(slug: str, block_meta: dict) -> None:
    """Each block's fenced content in onboard-project.md must equal its canonical file.

    This is the primary regression guarantee for the extraction refactor: a drift
    between the embedded block and `claude/canonical-blocks/<slug>.md` means users
    are onboarded with content that differs from the canonical source of truth.
    """
    canonical_path = CANONICAL_BLOCKS_DIR / block_meta["canonical_file"]
    assert canonical_path.exists(), (
        f"Canonical file not found: {canonical_path}. "
        f"Create `claude/canonical-blocks/{block_meta['canonical_file']}` with the "
        f"block content extracted from the command file's ```markdown fence."
    )

    canonical_content = canonical_path.read_text(encoding="utf-8")
    onboard_content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(onboard_content, block_meta["section_heading"])

    assert fenced == canonical_content, (
        f"Fenced content in onboard-project.md does NOT match "
        f"canonical file '{block_meta['canonical_file']}'.\n"
        f"Canonical ({len(canonical_content)} chars):\n{canonical_content[:300]!r}\n\n"
        f"Embedded fenced ({len(fenced)} chars):\n{fenced[:300]!r}\n\n"
        f"Run: python3 scripts/sync_canonical_blocks.py --write"
    )


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_new_project_fenced_content_matches_canonical_file_byte_for_byte(
    slug: str, block_meta: dict
) -> None:
    """Each block's fenced content in new-project.md must equal its canonical file.

    Complements the onboard-project test: both command files must be in sync with
    the canonical source. This catches the case where one file was synced but not the other.
    """
    canonical_path = CANONICAL_BLOCKS_DIR / block_meta["canonical_file"]
    assert canonical_path.exists(), (
        f"Canonical file not found: {canonical_path}. "
        f"Create `claude/canonical-blocks/{block_meta['canonical_file']}` with the "
        f"block content extracted from the command file's ```markdown fence."
    )

    canonical_content = canonical_path.read_text(encoding="utf-8")
    new_project_content = _read_command_file(NEW_PROJECT_PATH)
    fenced = _extract_fenced_content(new_project_content, block_meta["section_heading"])

    assert fenced == canonical_content, (
        f"Fenced content in new-project.md does NOT match "
        f"canonical file '{block_meta['canonical_file']}'.\n"
        f"Canonical ({len(canonical_content)} chars):\n{canonical_content[:300]!r}\n\n"
        f"Embedded fenced ({len(fenced)} chars):\n{fenced[:300]!r}\n\n"
        f"Run: python3 scripts/sync_canonical_blocks.py --write"
    )


# ---------------------------------------------------------------------------
# Shipped artifact isolation (all four blocks)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_block_contains_no_specific_ai_state_entries(slug: str, block_meta: dict) -> None:
    """Each block's fenced content must contain no specific .ai-state/ or .ai-work/ entries.

    Canonical blocks are injected into user CLAUDE.md files in external projects.
    Path shapes (`.ai-state/`, `.ai-work/<slug>/`) are permitted — they teach the
    convention. Specific entries (dec-NNN, SPEC_<name>_<date>, SENTINEL_REPORT_<date>)
    would dangle when the plugin lands in a different project.
    """
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, block_meta["section_heading"])

    for pattern in FORBIDDEN_PATTERNS:
        match = re.search(pattern, fenced)
        assert match is None, (
            f"'{slug}' block fenced content contains a forbidden shipped-artifact reference "
            f"matching '{pattern}': {match.group()!r}. "
            "Canonical blocks must not reference .ai-state/ or .ai-work/ entries."
        )


# ---------------------------------------------------------------------------
# Token budget (all four blocks)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_block_stays_within_token_budget(slug: str, block_meta: dict) -> None:
    """Each block's fenced content must be under ~250 tokens (bytes/3.6 estimate).

    Combined budget across all four blocks is ~8KB. Per-block ceiling is ~900 bytes.
    """
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, block_meta["section_heading"])
    block_bytes = len(fenced.encode("utf-8"))
    conservative_tokens = block_bytes / 3.6
    assert conservative_tokens < TOKEN_BUDGET, (
        f"'{slug}' block exceeds token budget. "
        f"Block is {block_bytes} bytes ({conservative_tokens:.1f} tokens by bytes/3.6). "
        f"Budget is {TOKEN_BUDGET} tokens. Trim the block prose before merging."
    )


# ---------------------------------------------------------------------------
# Idempotency predicate heading parity (all four blocks)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("slug", "block_meta"), BLOCKS.items())
def test_injectable_heading_is_idempotency_predicate_anchor(
    slug: str, block_meta: dict, tmp_path: Path
) -> None:
    """The injectable heading in each block must serve as the idempotency predicate anchor.

    Phase 6 of onboard-project.md checks for this heading in the user's CLAUDE.md to
    decide whether to skip re-injection. The heading in the block and the heading the
    predicate checks must be identical, or duplicate injection will occur.
    """
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, block_meta["section_heading"])
    claude_md_heading = block_meta["claude_md_heading"]

    # The fenced block must start with (or contain at start) the injectable heading
    assert fenced.startswith(claude_md_heading), (
        f"The '{slug}' block's fenced content does not start with '{claude_md_heading}'. "
        "The idempotency predicate checks for this heading in CLAUDE.md. "
        f"Block starts with: {fenced[:80]!r}"
    )

    # Simulate: write block to a temp CLAUDE.md and verify heading is detectable
    fixture_claude_md = tmp_path / "CLAUDE.md"
    fixture_claude_md.write_text(f"\n\n{fenced}\n", encoding="utf-8")
    assert claude_md_heading in fixture_claude_md.read_text(encoding="utf-8"), (
        f"After writing '{slug}' block to CLAUDE.md, the idempotency heading "
        f"'{claude_md_heading}' was not found. A second Phase 6 run would re-append the block."
    )


# ---------------------------------------------------------------------------
# Block ordering — §Praxion Process appears after §Behavioral Contract
# ---------------------------------------------------------------------------


def test_praxion_process_block_appears_after_behavioral_contract_in_onboard_project() -> None:
    """The §Praxion Process Block must appear after §Behavioral Contract Block in onboard-project.md."""
    content = _read_command_file(ONBOARD_PATH)

    behavioral_contract_pos = content.find("## §Behavioral Contract Block")
    praxion_process_pos = content.find("## §Praxion Process Block")

    assert (
        behavioral_contract_pos != -1
    ), "'## §Behavioral Contract Block' not found in onboard-project.md"
    assert praxion_process_pos != -1, "'## §Praxion Process Block' not found in onboard-project.md"
    assert praxion_process_pos > behavioral_contract_pos, (
        "'## §Praxion Process Block' must appear after '## §Behavioral Contract Block'. "
        f"Behavioral contract at pos {behavioral_contract_pos}, "
        f"Praxion Process at pos {praxion_process_pos}."
    )


# ---------------------------------------------------------------------------
# Phase 6 block references in command files
# ---------------------------------------------------------------------------


def test_phase_6_references_praxion_process_in_onboard_project() -> None:
    """Phase 6 gate message or action text must reference the Praxion Process block."""
    content = _read_command_file(ONBOARD_PATH)
    phase6_match = re.search(r"^## §Phase 6.*$", content, re.MULTILINE)
    assert phase6_match is not None, "§Phase 6 section not found in onboard-project.md"

    next_section = re.search(r"^## §Phase 7", content[phase6_match.end() :], re.MULTILINE)
    if next_section:
        phase6_text = content[phase6_match.start() : phase6_match.end() + next_section.start()]
    else:
        phase6_text = content[phase6_match.start() :]

    assert "Praxion Process" in phase6_text, (
        "Phase 6 section in onboard-project.md does not mention 'Praxion Process'. "
        "The phase description must reference four blocks."
    )


def test_phase_6_references_praxion_process_in_new_project() -> None:
    """The Praxion Process block must be referenced in new-project.md."""
    content = _read_command_file(NEW_PROJECT_PATH)
    assert "Praxion Process" in content, (
        "new-project.md does not mention 'Praxion Process' — "
        "the mirrored block reference is missing."
    )


# ---------------------------------------------------------------------------
# Praxion Process block — structural content requirements
# (specific to this block's governance role; other blocks have looser structure)
# ---------------------------------------------------------------------------


def test_praxion_process_block_contains_principle_language() -> None:
    """The Praxion Process block prose must reference the tier selector or pipeline principle."""
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, "## §Praxion Process Block")
    tier_or_pipeline = re.search(
        r"tier.{0,30}(selector|pipeline)|pipeline.{0,20}tier", fenced, re.IGNORECASE
    )
    assert tier_or_pipeline is not None, (
        "Praxion Process block does not reference the tier selector or pipeline principle. "
        f"Block content:\n{fenced}"
    )


def test_praxion_process_block_contains_rule_inheritance_corollary() -> None:
    """The Praxion Process block prose must reference rule-inheritance or subagent delegation."""
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, "## §Praxion Process Block")
    inheritance_ref = re.search(
        r"(subagent|delegation|host.native|inject|inherit|behavioral contract)",
        fenced,
        re.IGNORECASE,
    )
    assert inheritance_ref is not None, (
        "Praxion Process block does not reference the rule-inheritance corollary "
        "(subagent injection, delegation, or behavioral contract carry-forward). "
        f"Block content:\n{fenced}"
    )


def test_praxion_process_block_contains_threshold_reference() -> None:
    """The Praxion Process block prose must reference the trivial-vs-non-trivial threshold."""
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, "## §Praxion Process Block")
    threshold_ref = re.search(
        r"(trivial|non.trivial|threshold|simple|direct.tier|lightweight)",
        fenced,
        re.IGNORECASE,
    )
    assert threshold_ref is not None, (
        "Praxion Process block does not reference the trivial-vs-non-trivial threshold. "
        f"Block content:\n{fenced}"
    )


def test_praxion_process_block_contains_orchestrator_obligation() -> None:
    """The Praxion Process block prose must state the orchestrator's delegation obligation."""
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, "## §Praxion Process Block")
    obligation_ref = re.search(
        r"(orchestrat|delegation|delegation prompt|carry|include|pass)",
        fenced,
        re.IGNORECASE,
    )
    assert obligation_ref is not None, (
        "Praxion Process block does not state the orchestrator delegation obligation. "
        f"Block content:\n{fenced}"
    )


# ---------------------------------------------------------------------------
# Idempotency simulation — Praxion Process block (two-run scenario)
# ---------------------------------------------------------------------------


def test_second_phase6_run_produces_no_duplicate_when_block_already_present(
    tmp_path: Path,
) -> None:
    """Simulates two Phase 6 runs: the second run must not re-append the block.

    This tests the predicate logic: heading-present → skip.
    """
    content = _read_command_file(ONBOARD_PATH)
    fenced = _extract_fenced_content(content, "## §Praxion Process Block")
    claude_md_heading = BLOCKS["praxion-process"]["claude_md_heading"]

    # First run: CLAUDE.md has no Praxion Process block
    fixture_claude_md = tmp_path / "CLAUDE.md"
    fixture_claude_md.write_text(
        "# Project\n\n## Behavioral Contract\n\nContract text.\n", encoding="utf-8"
    )

    # Simulate Phase 6 first run (append if heading absent)
    claude_content = fixture_claude_md.read_text(encoding="utf-8")
    if claude_md_heading not in claude_content:
        fixture_claude_md.write_text(claude_content + f"\n{fenced}\n", encoding="utf-8")

    after_first_run = fixture_claude_md.read_text(encoding="utf-8")
    first_run_count = after_first_run.count(claude_md_heading)
    assert first_run_count == 1, (
        f"After first Phase 6 run, expected 1 occurrence of '{claude_md_heading}', "
        f"got {first_run_count}."
    )

    # Simulate Phase 6 second run (should be a no-op because heading is present)
    claude_content = fixture_claude_md.read_text(encoding="utf-8")
    if claude_md_heading not in claude_content:
        fixture_claude_md.write_text(claude_content + f"\n{fenced}\n", encoding="utf-8")

    after_second_run = fixture_claude_md.read_text(encoding="utf-8")
    second_run_count = after_second_run.count(claude_md_heading)
    assert second_run_count == 1, (
        f"After second Phase 6 run, '{claude_md_heading}' appears {second_run_count} times "
        f"(expected 1 — idempotency predicate should have suppressed the second append)."
    )

    assert (
        after_first_run == after_second_run
    ), "CLAUDE.md changed between first and second Phase 6 run — idempotency violated."
