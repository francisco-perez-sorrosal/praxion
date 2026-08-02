"""Unit tests for scripts/sync_canonical_blocks.py engine.

Tests are designed from the sync script's behavioral contract, not from
reading the production implementation. Synthetic file fixtures use
pytest's tmp_path fixture — no coupling to real command files for
state-mutating tests.

Two test layers:

1. **Internal-function tests**: import the module, monkeypatch CANONICAL_DIR
   and COMMAND_FILES to point at tmp_path fixtures, and exercise the
   extract_block / check_file / write_file functions directly. This layer
   tests the block locator, drift detection, write mechanics, and all four
   slug mappings with synthetic command files.

2. **CLI black-box tests**: invoke the script via subprocess against the real
   repo (read-only operations only) to verify exit codes and message contracts
   for the clean-path (--check on an in-sync repo, --help output, --dry-run
   no-drift). Write-mode and drift tests use monkeypatched fixtures in layer 1.

Block-locator contract (derived from SYSTEMS_PLAN + actual implementation):
  The script anchors on a ``<!-- canonical-source: claude/canonical-blocks/<slug>.md``
  HTML comment, then finds the next ```markdown fence, extracts content until
  the matching ``` closer. Synthetic command files in tests use this same marker.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = SCRIPTS_DIR / "sync_canonical_blocks.py"
REPO_ROOT = SCRIPTS_DIR.parent

# The block slugs the script must resolve.
ALL_BLOCK_SLUGS = [
    "agent-pipeline",
    "compaction-guidance",
    "behavioral-contract",
    "praxion-process",
    "obsidian-integration",
]

# Canonical-source comment prefix (matches CANONICAL_SOURCE_PREFIX in script).
CANONICAL_SOURCE_PREFIX = "canonical-source: claude/canonical-blocks/"
CANONICAL_SOURCE_SUFFIX = ".md"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_module():
    """Import sync_canonical_blocks lazily (ensures fresh module each time)."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    import sync_canonical_blocks as mod

    return importlib.reload(mod)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _canonical_source_comment(slug: str) -> str:
    """Return the canonical-source HTML comment line for a slug."""
    return (
        f"<!-- {CANONICAL_SOURCE_PREFIX}{slug}{CANONICAL_SOURCE_SUFFIX}"
        f" — edit the canonical file, then run: python3 scripts/sync_canonical_blocks.py --write -->"
    )


def _make_canonical_file(canonical_dir: Path, slug: str, content: str) -> Path:
    """Write a canonical block file and return its path."""
    path = canonical_dir / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    return path


def _make_command_file_with_one_block(
    directory: Path,
    filename: str,
    slug: str,
    fenced_content: str,
    surrounding_prose: str = "",
) -> Path:
    """Create a minimal synthetic command file containing one embedded block.

    The file structure mirrors what the implementer wrote:
      - HTML canonical-source comment (the block locator anchor)
      - optional surrounding prose between comment and fence
      - a ```markdown fence wrapping fenced_content
    """
    comment = _canonical_source_comment(slug)
    path = directory / filename
    path.write_text(
        f"{comment}\n{surrounding_prose}```markdown\n{fenced_content}```\n",
        encoding="utf-8",
    )
    return path


def _make_minimal_repo(
    tmp_path: Path,
    slug: str,
    canonical_content: str,
    onboard_fenced: str | None = None,
    new_project_fenced: str | None = None,
) -> tuple[Path, Path, Path]:
    """Build a minimal tmp_path tree for a single slug.

    Returns (canonical_dir, onboard_path, new_project_path).
    """
    canonical_dir = tmp_path / "claude" / "canonical-blocks"
    commands_dir = tmp_path / "commands"
    canonical_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)

    _make_canonical_file(canonical_dir, slug, canonical_content)

    onboard_body = onboard_fenced if onboard_fenced is not None else canonical_content
    new_project_body = new_project_fenced if new_project_fenced is not None else canonical_content

    onboard_path = _make_command_file_with_one_block(
        commands_dir, "onboard-project.md", slug, onboard_body
    )
    new_project_path = _make_command_file_with_one_block(
        commands_dir, "new-project.md", slug, new_project_body
    )
    return canonical_dir, onboard_path, new_project_path


def _make_four_block_command_file(
    directory: Path,
    filename: str,
    contents: dict[str, str],
    drifted: dict[str, str] | None = None,
) -> Path:
    """Build a command file containing all four canonical-source blocks.

    Args:
        contents: mapping slug → canonical fenced content
        drifted: optional mapping slug → overridden fenced content
    """
    sections = []
    for slug in ALL_BLOCK_SLUGS:
        if slug not in contents:
            continue
        body = (drifted or {}).get(slug, contents[slug])
        comment = _canonical_source_comment(slug)
        sections.append(f"{comment}\n```markdown\n{body}```\n")

    path = directory / filename
    path.write_text("\n".join(sections), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI smoke tests (real repo, read-only)
# ---------------------------------------------------------------------------


def test_help_flag_exits_zero_and_prints_usage() -> None:
    """The sync script accepts --help and exits 0."""
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--help returned {result.returncode}.\nstderr: {result.stderr}"
    assert result.stdout, "--help produced no output"


def test_check_exits_zero_on_in_sync_real_repo() -> None:
    """--check exits 0 against the real repo when canonical blocks are in sync.

    This verifies the full CLI pipeline end-to-end. It is a read-only test
    (no file mutation) and relies on the sync script and the canonical block
    files both being present.
    """
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        "Real-repo --check should exit 0 when canonical blocks are in sync. "
        f"Exit {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_dry_run_exits_zero_on_in_sync_real_repo() -> None:
    """--dry-run exits 0 against the real repo when all blocks are in sync."""
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        "Real-repo --dry-run should exit 0 when no drift. "
        f"Exit {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Internal-function tests: check_file (drift detection)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ALL_BLOCK_SLUGS)
def test_check_file_returns_empty_when_block_matches_canonical(tmp_path: Path, slug: str) -> None:
    """check_file returns an empty drift list when the embedded block is
    byte-identical to the canonical file."""
    canonical = f"## {slug.replace('-', ' ').title()}\n\nBlock prose.\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(tmp_path, slug, canonical)

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    drifted = mod.check_file(onboard_path)
    assert drifted == [], (
        f"check_file should return [] for '{slug}' when block matches canonical. Got: {drifted}"
    )


@pytest.mark.parametrize("slug", ALL_BLOCK_SLUGS)
def test_check_file_returns_drift_entry_when_block_differs_from_canonical(
    tmp_path: Path, slug: str
) -> None:
    """check_file returns a non-empty list when the embedded block differs
    from the canonical file. Each entry is (slug, diff_lines)."""
    canonical = f"## {slug.replace('-', ' ').title()}\n\nCanonical content.\n"
    drifted_body = canonical + "EXTRA LINE THAT DRIFTED\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    drifted = mod.check_file(onboard_path)
    assert len(drifted) == 1, (
        f"check_file should return one drift entry for '{slug}'. Got: {drifted}"
    )
    found_slug, diff_lines = drifted[0]
    assert found_slug == slug
    assert diff_lines, "Drift entry must include non-empty diff lines"


def test_check_file_includes_remediation_hint_in_printed_output(tmp_path: Path, capsys) -> None:
    """When check_file detects drift, the overall --check run prints a
    remediation hint that names the --write command."""
    slug = "behavioral-contract"
    canonical = "## Behavioral Contract\n\nOriginal.\n"
    drifted_body = "## Behavioral Contract\n\nDrifted.\n"
    canonical_dir, onboard_path, new_project_path = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]
    # Point COMMAND_FILES at our synthetic files
    mod.COMMAND_FILES = (onboard_path, new_project_path)  # type: ignore[attr-defined]

    exit_code = mod.run_check()
    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert exit_code == 1, f"run_check should return 1 on drift. Got {exit_code}"
    assert "--write" in output, (
        f"run_check output on drift must reference --write as remediation hint. Got:\n{output}"
    )


# ---------------------------------------------------------------------------
# Internal-function tests: write_file (corrects drift)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ALL_BLOCK_SLUGS)
def test_write_file_corrects_drifted_block_to_canonical(tmp_path: Path, slug: str) -> None:
    """write_file rewrites the drifted embedded block so it matches the
    canonical file byte-for-byte."""
    canonical = f"## {slug.replace('-', ' ').title()}\n\nCanonical prose.\n"
    drifted_body = canonical + "DRIFT LINE\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    updated = mod.write_file(onboard_path, dry_run=False)
    assert slug in updated, f"write_file should return the updated slug. Got: {updated}"

    # Verify the embedded content now matches canonical
    drifted_after = mod.check_file(onboard_path)
    assert drifted_after == [], (
        f"After write_file, check_file should return [] for '{slug}'. Got: {drifted_after}"
    )


# ---------------------------------------------------------------------------
# write_file idempotency
# ---------------------------------------------------------------------------


def test_write_file_is_idempotent_on_second_run(tmp_path: Path) -> None:
    """write_file called twice on an already-synced file produces identical
    output both times — the second call is a no-op."""
    slug = "compaction-guidance"
    canonical = "## Compaction Guidance\n\nContent.\n"
    drifted_body = canonical + "DRIFT\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    # First write: corrects drift
    mod.write_file(onboard_path, dry_run=False)
    after_first = onboard_path.read_text(encoding="utf-8")

    # Second write: no-op
    mod.write_file(onboard_path, dry_run=False)
    after_second = onboard_path.read_text(encoding="utf-8")

    assert after_first == after_second, (
        "write_file changed the file on second run (not idempotent). "
        f"First ({len(after_first)} chars) vs second ({len(after_second)} chars)."
    )


def test_write_file_returns_empty_on_already_synced_file(tmp_path: Path) -> None:
    """write_file on an already-synced file returns an empty updated-slug list."""
    slug = "praxion-process"
    canonical = "## Praxion Process\n\nAlready synced content.\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(tmp_path, slug, canonical)

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    updated = mod.write_file(onboard_path, dry_run=False)
    assert updated == [], f"write_file on already-synced file should return []. Got: {updated}"


# ---------------------------------------------------------------------------
# dry_run: no file mutations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ALL_BLOCK_SLUGS)
def test_write_file_dry_run_makes_no_file_changes(tmp_path: Path, slug: str) -> None:
    """write_file(dry_run=True) on a drifted file does not modify the file."""
    canonical = f"## {slug.replace('-', ' ').title()}\n\nCanonical.\n"
    drifted_body = canonical + "DRIFT\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )

    before = onboard_path.read_text(encoding="utf-8")

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]
    mod.write_file(onboard_path, dry_run=True)

    assert onboard_path.read_text(encoding="utf-8") == before, (
        "write_file(dry_run=True) must not modify the file."
    )


def test_write_file_dry_run_returns_drifted_slugs_without_writing(
    tmp_path: Path,
) -> None:
    """write_file(dry_run=True) returns the slugs that would be updated,
    but the file content remains unchanged."""
    slug = "agent-pipeline"
    canonical = "## Agent Pipeline\n\nCanonical.\n"
    drifted_body = canonical + "DRIFT\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )
    before = onboard_path.read_text(encoding="utf-8")

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]
    would_update = mod.write_file(onboard_path, dry_run=True)

    assert slug in would_update, f"dry_run should return drifted slug '{slug}'. Got: {would_update}"
    assert onboard_path.read_text(encoding="utf-8") == before, (
        "File must be unchanged after dry_run."
    )


# ---------------------------------------------------------------------------
# Script error path (exit 2 via SystemExit)
# ---------------------------------------------------------------------------


def test_check_file_exits_with_error_when_canonical_file_missing(
    tmp_path: Path,
) -> None:
    """check_file calls sys.exit(2) when the canonical file for a slug does
    not exist, distinguishing setup errors from drift."""
    slug = "praxion-process"
    # Build command file with the canonical-source comment but NO canonical file
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True)
    empty_canonical_dir = tmp_path / "claude" / "canonical-blocks"
    empty_canonical_dir.mkdir(parents=True)
    # Do NOT write any canonical file

    onboard_path = _make_command_file_with_one_block(
        commands_dir, "onboard-project.md", slug, "## Praxion Process\n\nContent.\n"
    )

    mod = _load_module()
    mod.CANONICAL_DIR = empty_canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    with pytest.raises(SystemExit) as exc_info:
        mod.check_file(onboard_path)
    assert exc_info.value.code == 2, (
        f"Missing canonical file should cause SystemExit(2). Got: {exc_info.value.code}"
    )


def test_write_file_exits_with_error_when_canonical_file_missing(
    tmp_path: Path,
) -> None:
    """write_file calls sys.exit(2) when the canonical file for a slug
    does not exist."""
    slug = "behavioral-contract"
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True)
    empty_canonical_dir = tmp_path / "claude" / "canonical-blocks"
    empty_canonical_dir.mkdir(parents=True)

    onboard_path = _make_command_file_with_one_block(
        commands_dir,
        "onboard-project.md",
        slug,
        "## Behavioral Contract\n\nStale content.\n",
    )

    mod = _load_module()
    mod.CANONICAL_DIR = empty_canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    with pytest.raises(SystemExit) as exc_info:
        mod.write_file(onboard_path, dry_run=False)
    assert exc_info.value.code == 2, (
        f"Missing canonical file should cause SystemExit(2). Got: {exc_info.value.code}"
    )


# ---------------------------------------------------------------------------
# Round-trip fidelity
# ---------------------------------------------------------------------------


def test_write_then_check_always_exits_clean(tmp_path: Path) -> None:
    """The round-trip guarantee: write_file followed by check_file returns []
    (no drift) for the same command file.

    This is the mechanically verifiable contract that the pre-commit hook
    relies on: run --write before staging, then --check passes.
    """
    slug = "compaction-guidance"
    canonical = "## Compaction Guidance\n\nFresh content.\n"
    drifted_body = "## Compaction Guidance\n\nSTALE CONTENT\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    mod.write_file(onboard_path, dry_run=False)
    drifted = mod.check_file(onboard_path)
    assert drifted == [], (
        f"Round-trip failure: check_file returned drift after write_file. Drift: {drifted}"
    )


def test_round_trip_preserves_fenced_content_byte_for_byte(tmp_path: Path) -> None:
    """write_file rewrites the fenced content; extracting it back yields
    byte-identical content to the canonical file."""
    slug = "behavioral-contract"
    canonical = "## Behavioral Contract\n\nContent with special chars: --write, ```.\n"
    drifted_body = "## Behavioral Contract\n\nOLD CONTENT\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(
        tmp_path, slug, canonical, onboard_fenced=drifted_body
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]
    mod.write_file(onboard_path, dry_run=False)

    # Extract the block body from the written file using the module's own extractor
    lines = onboard_path.read_text(encoding="utf-8").splitlines(keepends=True)
    loc = mod.extract_block(lines, slug, onboard_path)
    assert loc.body == canonical, (
        "Round-trip: extracted fenced content does not match canonical file. "
        f"Expected ({len(canonical)} chars):\n{canonical!r}\n\n"
        f"Got ({len(loc.body)} chars):\n{loc.body!r}"
    )


# ---------------------------------------------------------------------------
# Fence edge cases (robustness of the block locator)
# ---------------------------------------------------------------------------


def test_extract_block_handles_canonical_with_trailing_newline(
    tmp_path: Path,
) -> None:
    """extract_block correctly handles canonical content ending with a
    trailing newline — the most common case for well-formed Markdown files."""
    slug = "praxion-process"
    canonical = "## Praxion Process\n\nContent.\n"  # trailing newline
    assert canonical.endswith("\n"), "Test fixture must have trailing newline"
    canonical_dir, onboard_path, _ = _make_minimal_repo(tmp_path, slug, canonical)

    # extract_block does not use CANONICAL_DIR — no need to patch SLUGS
    mod = _load_module()
    lines = onboard_path.read_text(encoding="utf-8").splitlines(keepends=True)
    loc = mod.extract_block(lines, slug, onboard_path)
    assert loc.body == canonical, (
        "extract_block must preserve trailing newline. "
        f"Expected:\n{canonical!r}\nGot:\n{loc.body!r}"
    )


def test_extract_block_handles_canonical_with_blank_lines_inside(
    tmp_path: Path,
) -> None:
    """extract_block correctly handles canonical content containing blank
    lines — the locator must not stop at an interior blank line."""
    slug = "agent-pipeline"
    canonical = "## Agent Pipeline\n\nFirst paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(tmp_path, slug, canonical)

    # extract_block does not use CANONICAL_DIR — no need to patch SLUGS
    mod = _load_module()
    lines = onboard_path.read_text(encoding="utf-8").splitlines(keepends=True)
    loc = mod.extract_block(lines, slug, onboard_path)
    assert loc.body == canonical, (
        "extract_block must preserve all blank lines inside the fence. "
        f"Expected:\n{canonical!r}\nGot:\n{loc.body!r}"
    )


def test_write_file_preserves_surrounding_prose_between_comment_and_fence(
    tmp_path: Path,
) -> None:
    """write_file rewrites only the fenced content; prose between the
    canonical-source comment and the fence opener is left intact."""
    slug = "compaction-guidance"
    canonical = "## Compaction Guidance\n\nCanonical content.\n"
    surrounding_prose = "\nSome prose between the comment and the fence.\n\n"

    canonical_dir = tmp_path / "claude" / "canonical-blocks"
    commands_dir = tmp_path / "commands"
    canonical_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)
    _make_canonical_file(canonical_dir, slug, canonical)

    comment = _canonical_source_comment(slug)
    onboard_path = commands_dir / "onboard-project.md"
    onboard_path.write_text(
        f"{comment}\n{surrounding_prose}```markdown\nOLD CONTENT\n```\n",
        encoding="utf-8",
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]
    mod.write_file(onboard_path, dry_run=False)

    result = onboard_path.read_text(encoding="utf-8")
    assert surrounding_prose in result, (
        "write_file removed prose between the canonical-source comment and fence. "
        f"Expected to find:\n{surrounding_prose!r}\n\nGot:\n{result!r}"
    )


# ---------------------------------------------------------------------------
# All four slugs resolve via the canonical-source comment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ALL_BLOCK_SLUGS)
def test_all_block_slugs_locate_their_canonical_source_comment(tmp_path: Path, slug: str) -> None:
    """All four slugs are correctly identified via the canonical-source
    HTML comment. A missing or misspelled comment would cause SystemExit(2)."""
    canonical = f"## {slug.replace('-', ' ').title()}\n\nContent.\n"
    canonical_dir, onboard_path, _ = _make_minimal_repo(tmp_path, slug, canonical)

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.SLUGS = (slug,)  # type: ignore[attr-defined]

    # Should not raise — all four slugs have canonical-source comments in fixture
    drifted = mod.check_file(onboard_path)
    assert isinstance(drifted, list), (
        f"slug '{slug}': check_file should return a list, not raise. Got: {drifted}"
    )


# ---------------------------------------------------------------------------
# run_check / run_write / run_dry_run integration (monkeypatched paths)
# ---------------------------------------------------------------------------


def test_run_check_returns_zero_when_all_blocks_in_sync(tmp_path: Path, capsys) -> None:
    """run_check returns 0 when all blocks in both command files match canonical."""
    contents = {
        slug: f"## {slug.replace('-', ' ').title()}\n\nContent for {slug}.\n"
        for slug in ALL_BLOCK_SLUGS
    }
    canonical_dir = tmp_path / "claude" / "canonical-blocks"
    commands_dir = tmp_path / "commands"
    canonical_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)

    for slug, content in contents.items():
        _make_canonical_file(canonical_dir, slug, content)

    onboard = _make_four_block_command_file(commands_dir, "onboard-project.md", contents)
    new_proj = _make_four_block_command_file(commands_dir, "new-project.md", contents)

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.COMMAND_FILES = (onboard, new_proj)  # type: ignore[attr-defined]
    mod.SLUGS = tuple(ALL_BLOCK_SLUGS)  # type: ignore[attr-defined]

    exit_code = mod.run_check()
    assert exit_code == 0, (
        f"run_check should return 0 when all blocks in sync. Got {exit_code}.\n"
        f"{capsys.readouterr().out}"
    )


def test_run_check_returns_one_when_any_block_drifted(tmp_path: Path, capsys) -> None:
    """run_check returns 1 when at least one embedded block differs from its
    canonical file."""
    contents = {
        slug: f"## {slug.replace('-', ' ').title()}\n\nContent.\n" for slug in ALL_BLOCK_SLUGS
    }
    canonical_dir = tmp_path / "claude" / "canonical-blocks"
    commands_dir = tmp_path / "commands"
    canonical_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)

    for slug, content in contents.items():
        _make_canonical_file(canonical_dir, slug, content)

    drifted_overrides = {"praxion-process": "## Praxion Process\n\nDRIFTED\n"}
    onboard = _make_four_block_command_file(
        commands_dir, "onboard-project.md", contents, drifted=drifted_overrides
    )
    new_proj = _make_four_block_command_file(commands_dir, "new-project.md", contents)

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.COMMAND_FILES = (onboard, new_proj)  # type: ignore[attr-defined]
    mod.SLUGS = tuple(ALL_BLOCK_SLUGS)  # type: ignore[attr-defined]

    exit_code = mod.run_check()
    assert exit_code == 1, f"run_check should return 1 when drift detected. Got {exit_code}."


def test_run_write_corrects_drift_and_check_passes(tmp_path: Path, capsys) -> None:
    """run_write followed by run_check returns 0 — the round-trip guarantee
    at the mode-function level."""
    contents = {
        slug: f"## {slug.replace('-', ' ').title()}\n\nContent.\n" for slug in ALL_BLOCK_SLUGS
    }
    canonical_dir = tmp_path / "claude" / "canonical-blocks"
    commands_dir = tmp_path / "commands"
    canonical_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)

    for slug, content in contents.items():
        _make_canonical_file(canonical_dir, slug, content)

    drifted_overrides = {
        "agent-pipeline": "## Agent Pipeline\n\nSTALE\n",
        "compaction-guidance": "## Compaction Guidance\n\nSTALE\n",
    }
    onboard = _make_four_block_command_file(
        commands_dir, "onboard-project.md", contents, drifted=drifted_overrides
    )
    new_proj = _make_four_block_command_file(
        commands_dir, "new-project.md", contents, drifted=drifted_overrides
    )

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.COMMAND_FILES = (onboard, new_proj)  # type: ignore[attr-defined]
    mod.SLUGS = tuple(ALL_BLOCK_SLUGS)  # type: ignore[attr-defined]

    write_code = mod.run_write()
    assert write_code == 0, f"run_write should return 0 on success. Got {write_code}."

    # Reload to pick up any module-level state changes (CANONICAL_DIR etc.)
    mod2 = _load_module()
    mod2.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod2.COMMAND_FILES = (onboard, new_proj)  # type: ignore[attr-defined]
    mod2.SLUGS = tuple(ALL_BLOCK_SLUGS)  # type: ignore[attr-defined]

    check_code = mod2.run_check()
    assert check_code == 0, (
        f"Round-trip failure: run_check returned non-zero after run_write. Got {check_code}."
    )


def test_run_dry_run_does_not_modify_files(tmp_path: Path, capsys) -> None:
    """run_dry_run on drifted files exits non-zero but does not modify any file."""
    contents = {
        slug: f"## {slug.replace('-', ' ').title()}\n\nContent.\n" for slug in ALL_BLOCK_SLUGS
    }
    canonical_dir = tmp_path / "claude" / "canonical-blocks"
    commands_dir = tmp_path / "commands"
    canonical_dir.mkdir(parents=True)
    commands_dir.mkdir(parents=True)

    for slug, content in contents.items():
        _make_canonical_file(canonical_dir, slug, content)

    drifted_overrides = {"behavioral-contract": "## Behavioral Contract\n\nSTALE\n"}
    onboard = _make_four_block_command_file(
        commands_dir, "onboard-project.md", contents, drifted=drifted_overrides
    )
    new_proj = _make_four_block_command_file(commands_dir, "new-project.md", contents)

    before_onboard = onboard.read_text(encoding="utf-8")
    before_new_proj = new_proj.read_text(encoding="utf-8")

    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.COMMAND_FILES = (onboard, new_proj)  # type: ignore[attr-defined]
    mod.SLUGS = tuple(ALL_BLOCK_SLUGS)  # type: ignore[attr-defined]

    exit_code = mod.run_dry_run()
    assert exit_code != 0, f"run_dry_run should exit non-zero on drift. Got {exit_code}."
    assert onboard.read_text(encoding="utf-8") == before_onboard, (
        "run_dry_run must not modify onboard-project.md"
    )
    assert new_proj.read_text(encoding="utf-8") == before_new_proj, (
        "run_dry_run must not modify new-project.md"
    )


# ---------------------------------------------------------------------------
# History-manifest generator: --write-history / --check-history (new mode)
# ---------------------------------------------------------------------------
#
# The history-manifest generator enumerates each refresh-eligible canonical
# file's git history, normalizes+hashes each historical body via the shared
# canonical_block_identity module, dedupes, and writes/verifies a JSON
# manifest at <CANONICAL_DIR>/block-history.json. Tests build a real,
# throwaway git repository per fixture (git init/add/commit via subprocess,
# mirroring test_check_aac_golden_rule.py's micro-repo convention) so the
# git-log-derived dedup and drift-detection behavior is exercised for real,
# not mocked.
#
# Interface contract these tests pin (the history-manifest generator must satisfy):
#   - CANONICAL_DIR / REPO_ROOT stay overridable module attributes (mirrors
#     the existing SLUGS/CANONICAL_DIR override convention above).
#   - REFRESHABLE_SLUGS (imported from canonical_block_identity) is a plain
#     module-level binding on sync_canonical_blocks, overridable the same
#     way SLUGS already is, so tests can scope a fixture to one slug.
#   - The manifest's "current" hash must be computed from the canonical
#     file's LIVE on-disk content, not solely from the last git-log commit.
#     This is load-bearing for the gate-liveness canary below: a pre-commit
#     hook fires on staged/working-tree state *before* a commit exists, so
#     if "current" only reflected git log, an uncommitted edit would never
#     be caught -- defeating the "caught at commit time" guarantee the
#     manifest's producer-liveness gate exists for.

sys.path.insert(0, str(SCRIPTS_DIR))  # ensure canonical_block_identity is importable
from canonical_block_identity import REFRESHABLE_SLUGS, hash_block_body  # noqa: E402


def _git_history_repo(tmp_path: Path) -> Path:
    """Init a throwaway git repo at tmp_path with a claude/canonical-blocks/ dir.

    Returns the canonical-blocks directory path. Mirrors the micro-repo
    convention in test_check_aac_golden_rule.py: real git init/add/commit via
    subprocess, so the generator's actual git-log-derived history enumeration
    is exercised rather than a mocked stub.
    """
    canonical_dir = tmp_path / "claude" / "canonical-blocks"
    canonical_dir.mkdir(parents=True)
    subprocess.run(["git", "init"], check=True, capture_output=True, cwd=str(tmp_path))
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    return canonical_dir


def _commit_canonical_body(canonical_dir: Path, slug: str, body: str, msg: str) -> None:
    """Write+commit one revision of a canonical file's body."""
    repo_root = canonical_dir.parent.parent
    path = canonical_dir / f"{slug}.md"
    path.write_text(body, encoding="utf-8")
    relpath = str(path.relative_to(repo_root))
    subprocess.run(["git", "add", relpath], check=True, capture_output=True, cwd=str(repo_root))
    subprocess.run(
        ["git", "commit", "-m", msg], check=True, capture_output=True, cwd=str(repo_root)
    )


def _mutate_canonical_body_uncommitted(canonical_dir: Path, slug: str, body: str) -> None:
    """Overwrite a canonical file's live content WITHOUT committing -- simulates
    an edit the manifest has not yet been regenerated for."""
    (canonical_dir / f"{slug}.md").write_text(body, encoding="utf-8")


def _load_module_for_synthetic_history(canonical_dir: Path, slugs: frozenset[str] | None = None):
    """Load sync_canonical_blocks scoped to a throwaway git-history fixture.

    Patches CANONICAL_DIR and REPO_ROOT to the fixture's tmp git repo so the
    generator's git-log enumeration resolves within it regardless of whether
    the implementation anchors git commands via cwd=CANONICAL_DIR or an
    explicit REPO_ROOT path (both resolve correctly here, since REPO_ROOT is
    the tmp repo's root and CANONICAL_DIR is one of its subdirectories). When
    `slugs` is given, also restricts REFRESHABLE_SLUGS to that set -- mirrors
    the file's existing SLUGS-override convention used to scope fixtures to
    a minimal, focused subset.
    """
    mod = _load_module()
    mod.CANONICAL_DIR = canonical_dir  # type: ignore[attr-defined]
    mod.REPO_ROOT = canonical_dir.parent.parent  # type: ignore[attr-defined]
    if slugs is not None:
        mod.REFRESHABLE_SLUGS = slugs  # type: ignore[attr-defined]
    return mod


def _history_manifest_path(canonical_dir: Path) -> Path:
    """The manifest's expected on-disk location, per the shipped schema path
    (claude/canonical-blocks/block-history.json)."""
    return canonical_dir / "block-history.json"


def test_write_history_manifest_maps_slug_to_current_and_deduped_ordered_history(
    tmp_path: Path,
) -> None:
    """--write-history maps a refresh-eligible slug to its current hash and a
    deduped, oldest-to-newest history list, with current == history[-1]."""
    slug = "agent-pipeline"
    canonical_dir = _git_history_repo(tmp_path)

    body_a = "## Agent Pipeline\n\nFirst revision.\n"
    body_b = "## Agent Pipeline\n\nSecond revision.\n"
    body_b_whitespace_variant = body_b + "\n"  # normalizes to the same hash as body_b

    _commit_canonical_body(canonical_dir, slug, body_a, "rev 1")
    _commit_canonical_body(canonical_dir, slug, body_b, "rev 2")
    _commit_canonical_body(
        canonical_dir, slug, body_b_whitespace_variant, "rev 3 (whitespace-only)"
    )

    mod = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    exit_code = mod.run_write_history()
    assert exit_code == 0, f"run_write_history should return 0. Got {exit_code}."

    manifest = json.loads(_history_manifest_path(canonical_dir).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert set(manifest["blocks"].keys()) == {slug}, (
        "manifest must map exactly the scoped refresh-eligible slugs, nothing "
        f"more/less. Got keys: {sorted(manifest['blocks'].keys())}"
    )

    block_entry = manifest["blocks"][slug]
    expected_history = [hash_block_body(body_a), hash_block_body(body_b)]
    assert block_entry["history"] == expected_history, (
        "history must be oldest-to-newest and deduped by normalized body -- the "
        "whitespace-only third revision must collapse into the second entry, "
        f"not add a third. Got: {block_entry['history']}"
    )
    assert block_entry["current"] == block_entry["history"][-1], (
        "current must equal the last (newest) history entry"
    )


def test_write_history_manifest_excludes_slugs_outside_refreshable_set(
    tmp_path: Path,
) -> None:
    """A canonical file for a non-eligible slug (e.g. a template-filled or
    conditional block) present alongside the refresh-eligible files is never
    included in the manifest -- REFRESHABLE_SLUGS is a hard membership
    boundary, not a filter applied downstream of a naive directory scan."""
    canonical_dir = _git_history_repo(tmp_path)
    for slug in REFRESHABLE_SLUGS:
        _commit_canonical_body(
            canonical_dir,
            slug,
            f"## {slug.replace('-', ' ').title()}\n\nContent.\n",
            f"init {slug}",
        )
    excluded_slug = "project-essentials"
    _commit_canonical_body(
        canonical_dir,
        excluded_slug,
        "## Working in this project\n\nTemplate.\n",
        "init excluded",
    )

    mod = _load_module_for_synthetic_history(canonical_dir)  # real REFRESHABLE_SLUGS
    exit_code = mod.run_write_history()
    assert exit_code == 0, f"run_write_history should return 0. Got {exit_code}."

    manifest = json.loads(_history_manifest_path(canonical_dir).read_text(encoding="utf-8"))
    assert set(manifest["blocks"].keys()) == set(REFRESHABLE_SLUGS), (
        f"manifest must map exactly REFRESHABLE_SLUGS, excluding "
        f"'{excluded_slug}'. Got keys: {sorted(manifest['blocks'].keys())}"
    )


def test_check_history_exits_zero_when_manifest_matches_fresh_generation(
    tmp_path: Path,
) -> None:
    """--check-history exits 0 immediately after --write-history with no
    intervening edits (the non-vacuity control for the drift canary below --
    proves the gate does not simply always fail)."""
    slug = "compaction-guidance"
    canonical_dir = _git_history_repo(tmp_path)
    _commit_canonical_body(canonical_dir, slug, "## Compaction Guidance\n\nOriginal.\n", "init")

    mod = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    mod.run_write_history()

    mod2 = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    exit_code = mod2.run_check_history()
    assert exit_code == 0, (
        "--check-history should exit 0 when the manifest matches a fresh "
        f"generation. Got {exit_code}."
    )


def test_check_history_exits_nonzero_and_reports_drift_when_canonical_file_edited_without_regenerating(
    tmp_path: Path, capsys
) -> None:
    """The manifest's own producer-liveness gate: editing a canonical file's
    live content without re-running --write-history is caught by
    --check-history -- exits non-zero and names the drifted slug.

    This is the load-bearing gate-liveness canary: it proves the gate BITES,
    not just that it passes on an untouched repo. The edit is deliberately
    left uncommitted (not a new git commit) -- the "caught at commit time"
    guarantee only makes sense if the fresh regeneration reads the live
    file, since a pre-commit hook fires before the commit exists.
    """
    slug = "praxion-process"
    canonical_dir = _git_history_repo(tmp_path)
    _commit_canonical_body(canonical_dir, slug, "## Praxion Process\n\nOriginal.\n", "init")

    mod = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    mod.run_write_history()

    _mutate_canonical_body_uncommitted(
        canonical_dir, slug, "## Praxion Process\n\nEdited but not regenerated.\n"
    )

    mod2 = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    exit_code = mod2.run_check_history()
    output = capsys.readouterr().out

    assert exit_code != 0, (
        "--check-history must exit non-zero when a canonical file's live "
        "content diverges from the committed manifest's regeneration."
    )
    assert slug in output, (
        f"--check-history drift report must name the drifted slug '{slug}'. Got:\n{output}"
    )


def test_write_history_produces_byte_identical_manifest_across_consecutive_runs(
    tmp_path: Path,
) -> None:
    """Two consecutive --write-history runs over the same git history produce
    byte-identical manifest content -- deterministic: no timestamps, stable
    key ordering."""
    slug = "behavioral-contract"
    canonical_dir = _git_history_repo(tmp_path)
    _commit_canonical_body(canonical_dir, slug, "## Behavioral Contract\n\nRev 1.\n", "rev 1")
    _commit_canonical_body(canonical_dir, slug, "## Behavioral Contract\n\nRev 2.\n", "rev 2")

    mod = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    mod.run_write_history()
    first_bytes = _history_manifest_path(canonical_dir).read_bytes()

    mod2 = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    mod2.run_write_history()
    second_bytes = _history_manifest_path(canonical_dir).read_bytes()

    assert first_bytes == second_bytes, (
        "Two consecutive --write-history runs over unchanged history must "
        "produce byte-identical manifest content."
    )


def test_help_flag_lists_write_history_and_check_history_flags() -> None:
    """--help documents the new history-manifest generator flags."""
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert "--write-history" in result.stdout, (
        f"--help output must document --write-history.\n{result.stdout}"
    )
    assert "--check-history" in result.stdout, (
        f"--help output must document --check-history.\n{result.stdout}"
    )


def test_main_write_history_flag_invokes_generator_and_produces_manifest(
    tmp_path: Path,
) -> None:
    """`main(["--write-history"])` (the CLI entry point) wires the flag to the
    history generator and produces the manifest file -- not just the
    lower-level function existing in isolation."""
    slug = "compaction-guidance"
    canonical_dir = _git_history_repo(tmp_path)
    _commit_canonical_body(canonical_dir, slug, "## Compaction Guidance\n\nContent.\n", "init")

    mod = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    exit_code = mod.main(["--write-history"])

    assert exit_code == 0, f"main(['--write-history']) should return 0. Got {exit_code}."
    assert _history_manifest_path(canonical_dir).exists(), (
        "main(['--write-history']) must produce the manifest file."
    )


def test_main_check_history_flag_returns_zero_when_manifest_up_to_date(
    tmp_path: Path,
) -> None:
    """`main(["--check-history"])` wires the flag to the check mode and
    returns 0 when the committed manifest matches a fresh generation."""
    slug = "behavioral-contract"
    canonical_dir = _git_history_repo(tmp_path)
    _commit_canonical_body(canonical_dir, slug, "## Behavioral Contract\n\nContent.\n", "init")

    mod = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    mod.main(["--write-history"])

    mod2 = _load_module_for_synthetic_history(canonical_dir, frozenset({slug}))
    exit_code = mod2.main(["--check-history"])

    assert exit_code == 0, f"main(['--check-history']) should return 0. Got {exit_code}."
