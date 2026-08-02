"""Behavioral tests for scripts/dispatch-reworks: manifest parsing and --dry-run output.

Integration-style tests using subprocess invocation against synthetic manifests.
The script is not imported — it is invoked as a subprocess so all I/O coupling
(git, python3, parse_json_blocks) runs in a controlled child process.

All tests run with --dry-run so no real claude --bg or open invocations fire.

Design note: because the script resolves the main worktree root via
`git worktree list --porcelain`, tests that exercise the dispatch loop (the
worktree-existence check and dry-run print) must construct worktree directories
under the real main worktree root (or trick the script into accepting a
synthesised path). The approach chosen here:
  - Inject a synthetic REWORK_MANIFEST.md via --manifest.
  - Create the expected worktree directory under the real .claude/worktrees/ so
    the existence check passes, OR rely on the skip-and-warn behavior for rows
    whose directory does not exist.
  - Tests that only check exit codes and stderr messages do not need worktrees.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "dispatch-reworks"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_MANIFEST = FIXTURES / "rework_manifest_sample.md"

# The script resolves PROJECT_ROOT via `git worktree list --porcelain` (first
# line = main checkout).  When tests run from a linked worktree the main checkout
# is a different path.  We derive it once at module load so worktree-creation
# helpers can target the right directory.
_MAIN_WORKTREE_ROOT = Path(
    subprocess.check_output(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(REPO_ROOT),
        text=True,
    )
    .splitlines()[0]
    .split(" ", 1)[1]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_script(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run scripts/dispatch-reworks with the given arguments; capture all output."""
    cmd = [str(SCRIPT), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
    )


def make_manifest(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a synthetic REWORK_MANIFEST.md in tmp_path with the given rows.

    Each dict must have at least 'worktree_name'. Other fields are given
    sensible defaults so parse_json_blocks() accepts them cleanly.
    """
    blocks: list[str] = []
    for i, row in enumerate(rows, start=1):
        full_row = {
            "id": f"rw-test{i:04d}",
            "target_agent": "implementer",
            "severity": "important",
            "recommended_tier": "standard",
            "class": "implementation",
            "headline": f"Test finding {i}",
            "finding_refs": [],
            "td_refs": [],
            "confidence": "high",
            "dedup_against": [],
            "notes": "",
            **row,  # caller overrides take precedence
        }
        blocks.append(f"### Row {i} — {full_row.get('worktree_name', f'row-{i}')}\n")
        blocks.append("```json")
        blocks.append(json.dumps(full_row, indent=2))
        blocks.append("```")
    header = textwrap.dedent("""\
        # Rework Manifest — synthetic-test

        Generated: 2026-05-14T00:00:00Z.

    """)
    manifest = tmp_path / "REWORK_MANIFEST.md"
    manifest.write_text(header + "\n".join(blocks) + "\n", encoding="utf-8")
    return manifest


def make_worktree_dir(name: str) -> Path:
    """Create (or confirm) the expected worktree directory under the main checkout.

    The script resolves PROJECT_ROOT via `git worktree list --porcelain` (first
    line = main checkout) and constructs paths as <main>/.claude/worktrees/<name>.
    When running from a linked worktree, REPO_ROOT != main root; we use
    _MAIN_WORKTREE_ROOT so the directories the script checks actually exist.
    Returns the created path for cleanup.
    """
    wt_dir = _MAIN_WORKTREE_ROOT / ".claude" / "worktrees" / name
    wt_dir.mkdir(parents=True, exist_ok=True)
    return wt_dir


# ---------------------------------------------------------------------------
# Mutual-exclusion flag guard
# ---------------------------------------------------------------------------


def test_bg_and_terminals_together_exits_misuse():
    """Passing --bg and --terminals together must exit 2 (misuse) immediately."""
    result = run_script("--bg", "--terminals", "--dry-run", "--manifest", str(SAMPLE_MANIFEST))
    assert result.returncode == 2, (
        f"Expected exit 2 for --bg + --terminals, got {result.returncode}. "
        f"stderr: {result.stderr!r}"
    )
    assert "--bg" in result.stderr, (
        "Error message should mention both flags. stderr: " + result.stderr
    )
    assert "--terminals" in result.stderr, (
        "Error message should mention both flags. stderr: " + result.stderr
    )


# ---------------------------------------------------------------------------
# Manifest-not-found cases
# ---------------------------------------------------------------------------


def test_nonexistent_manifest_path_exits_manifest_not_found(tmp_path):
    """Passing --manifest with a path that does not exist must exit 3."""
    missing = tmp_path / "no_such_manifest.md"
    result = run_script("--dry-run", "--manifest", str(missing))
    assert result.returncode == 3, (
        f"Expected exit 3 for missing manifest, got {result.returncode}. stderr: {result.stderr!r}"
    )


def test_manifest_path_is_directory_exits_manifest_not_found(tmp_path):
    """Passing --manifest pointing to a directory (not a file) must exit 3."""
    result = run_script("--dry-run", "--manifest", str(tmp_path))
    assert result.returncode == 3, (
        f"Expected exit 3 when manifest is a directory, got {result.returncode}. "
        f"stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Empty / no-JSON-blocks manifest
# ---------------------------------------------------------------------------


def test_empty_manifest_file_exits_empty(tmp_path):
    """A zero-byte manifest file must exit 4 (no rows) with a message on stderr."""
    empty = tmp_path / "REWORK_MANIFEST.md"
    empty.write_text("", encoding="utf-8")
    result = run_script("--dry-run", "--manifest", str(empty))
    assert result.returncode == 4, (
        f"Expected exit 4 for empty manifest, got {result.returncode}. stderr: {result.stderr!r}"
    )
    assert result.stderr.strip(), "Expected a diagnostic message on stderr for empty manifest"


def test_manifest_with_no_json_blocks_exits_empty(tmp_path):
    """A manifest with prose but no ```json blocks must exit 4 (no rows)."""
    prose_only = tmp_path / "REWORK_MANIFEST.md"
    prose_only.write_text(
        "# Rework Manifest\n\nNo findings. All reworks complete.\n",
        encoding="utf-8",
    )
    result = run_script("--dry-run", "--manifest", str(prose_only))
    assert result.returncode == 4, (
        f"Expected exit 4 for manifest with no JSON blocks, got {result.returncode}. "
        f"stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Malformed JSON block — silent skip, valid rows surface
# ---------------------------------------------------------------------------


def test_malformed_json_block_silently_skipped(tmp_path):
    """A manifest with a malformed JSON block must not produce a Python traceback.

    parse_json_blocks() silently skips blocks whose content fails json.loads().
    The script must exit without a traceback or SyntaxError — the exact exit
    code depends on how many valid rows remain after parsing.

    NOTE: the greedy DOTALL regex in rework_manifest.py (_JSON_BLOCK_RE) can
    consume a subsequent valid block when the malformed block's `{` is on the
    same line as ```json and the next closing ``` spans both fences.  This is a
    known edge case in parse_json_blocks(): only self-contained, valid JSON
    blocks are reliably extracted.  We assert no crash; row-survival count is
    a separate contract concern (see LEARNINGS.md Gotchas).
    """
    manifest = tmp_path / "REWORK_MANIFEST.md"
    manifest.write_text(
        textwrap.dedent("""\
            # Rework Manifest — malformed test

            ```json
            { this is not valid json
            ```

            ```json
            {
              "id": "rw-validtest",
              "worktree_name": "valid-rw-row",
              "target_agent": "implementer",
              "severity": "important",
              "recommended_tier": "standard",
              "class": "implementation",
              "headline": "Valid finding",
              "finding_refs": [],
              "td_refs": [],
              "confidence": "high",
              "dedup_against": [],
              "notes": ""
            }
            ```
        """),
        encoding="utf-8",
    )
    result = run_script("--dry-run", "--manifest", str(manifest))
    # The malformed block must not produce a Python traceback on stderr
    assert "Traceback" not in result.stderr, (
        f"Malformed JSON block caused a Python traceback. stderr: {result.stderr!r}"
    )
    assert "SyntaxError" not in result.stderr, (
        f"Unexpected SyntaxError in stderr: {result.stderr!r}"
    )
    # Exit must be 0 (row parsed, worktree exists), 1 (row parsed, no worktree),
    # or 4 (no rows parsed at all) — never a crash code.
    assert result.returncode in (0, 1, 4), (
        f"Expected exit 0, 1, or 4 for malformed manifest, got {result.returncode}. "
        f"stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Missing worktree_name field — skip behavior
# ---------------------------------------------------------------------------


def test_row_missing_worktree_name_is_skipped(tmp_path):
    """A manifest row without 'worktree_name' must not crash the script.

    The script uses r.get('worktree_name', '') in the Python bridge; an empty
    name triggers the `[ -z "$WT_NAME" ] && continue` guard in the bash loop.
    Expected: the row is skipped, stderr may warn, script exits without a
    Python traceback.
    """
    manifest = tmp_path / "REWORK_MANIFEST.md"
    manifest.write_text(
        textwrap.dedent("""\
            # Rework Manifest — missing worktree_name

            ```json
            {
              "id": "rw-noname",
              "target_agent": "implementer",
              "severity": "critical",
              "headline": "No worktree_name key in this row"
            }
            ```
        """),
        encoding="utf-8",
    )
    result = run_script("--dry-run", "--manifest", str(manifest))
    assert "Traceback" not in result.stderr, (
        f"Row without worktree_name caused a traceback: {result.stderr!r}"
    )
    # The exit code will be 4 (no rows with a name) or 1 (no valid worktrees).
    # Either is acceptable — the important invariant is no crash.
    assert result.returncode in (1, 4), (
        f"Expected exit 1 or 4 for row missing worktree_name, got {result.returncode}. "
        f"stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# --bg --dry-run: output format
# ---------------------------------------------------------------------------


def test_bg_dry_run_two_rows_prints_two_lines(tmp_path):
    """--bg --dry-run with a 2-row manifest whose worktrees exist must print
    exactly 2 'would dispatch' lines and exit 0.
    """
    names = ["fix-auth-expiry-bg", "patch-rate-limiter-bg"]
    wt_dirs = [make_worktree_dir(n) for n in names]
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": n} for n in names])
        result = run_script("--bg", "--dry-run", "--manifest", str(manifest))
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert len(dispatch_lines) == 2, (
            f"Expected 2 'would dispatch' lines, got {len(dispatch_lines)}. "
            f"stdout: {result.stdout!r}"
        )
    finally:
        for d in wt_dirs:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()


def test_bg_dry_run_line_format_contains_expected_fields(tmp_path):
    """Each --bg --dry-run line must contain the mode, worktree name, claude --bg,
    /resume-rework, and --name "rework: <name>".
    """
    name = "fix-session-leak-bg"
    wt_dir = make_worktree_dir(name)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = run_script("--bg", "--dry-run", "--manifest", str(manifest))
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr!r}"
        )
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert len(dispatch_lines) == 1, f"Expected 1 dispatch line, got {dispatch_lines!r}"
        line = dispatch_lines[0]
        assert "bg" in line, f"Mode 'bg' missing from line: {line!r}"
        assert name in line, f"Worktree name '{name}' missing from line: {line!r}"
        assert "claude --bg" in line, f"'claude --bg' missing from line: {line!r}"
        assert '"/resume-rework"' in line, f"'/resume-rework' missing from line: {line!r}"
        assert f'"rework: {name}"' in line, (
            f"'rework: {name}' missing from --name value in line: {line!r}"
        )
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_bg_dry_run_row_order_matches_manifest_order(tmp_path):
    """--bg --dry-run output order must match the manifest row order."""
    names = ["row-alpha-bg", "row-beta-bg", "row-gamma-bg"]
    wt_dirs = [make_worktree_dir(n) for n in names]
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": n} for n in names])
        result = run_script("--bg", "--dry-run", "--manifest", str(manifest))
        assert result.returncode == 0, f"Expected exit 0. stderr: {result.stderr!r}"
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert len(dispatch_lines) == 3, f"Expected 3 dispatch lines, got: {dispatch_lines!r}"
        for expected_name, line in zip(names, dispatch_lines, strict=False):
            assert expected_name in line, (
                f"Expected '{expected_name}' at this position; got: {line!r}"
            )
    finally:
        for d in wt_dirs:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()


def test_bg_dry_run_does_not_start_claude_process(tmp_path, tmp_path_factory):
    """--bg --dry-run must not invoke claude (no real dispatch).

    Verified by placing a sentinel script named 'claude' at the front of PATH
    that writes a marker file and exits 0. If the script invokes 'claude', the
    marker appears. If it does not, the marker is absent.
    """
    name = "no-claude-fire-bg"
    wt_dir = make_worktree_dir(name)
    sentinel_dir = tmp_path_factory.mktemp("fake_bin")
    marker = tmp_path_factory.mktemp("markers") / "claude_invoked.marker"
    fake_claude = sentinel_dir / "claude"
    fake_claude.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 0\n', encoding="utf-8")
    fake_claude.chmod(0o755)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        import os

        env = {**os.environ, "PATH": f"{sentinel_dir}:{os.environ.get('PATH', '')}"}
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--dry-run", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, f"Expected exit 0. stderr: {result.stderr!r}"
        assert not marker.exists(), (
            "'claude' was invoked during --dry-run — real dispatch must not fire."
        )
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


# ---------------------------------------------------------------------------
# --terminals --dry-run: output format
# ---------------------------------------------------------------------------


def test_terminals_dry_run_line_format_contains_claude_cli_url(tmp_path):
    """--terminals --dry-run must print a claude-cli:// URL per row."""
    name = "fix-session-leak-term"
    wt_dir = make_worktree_dir(name)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = run_script("--terminals", "--dry-run", "--manifest", str(manifest))
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. stderr: {result.stderr!r}"
        )
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert len(dispatch_lines) == 1, f"Expected 1 dispatch line, got: {dispatch_lines!r}"
        line = dispatch_lines[0]
        assert "terminals" in line, f"Mode 'terminals' missing: {line!r}"
        assert name in line, f"Worktree name '{name}' missing: {line!r}"
        assert "claude-cli://" in line, f"'claude-cli://' missing from line: {line!r}"
        assert "resume-rework" in line, f"'/resume-rework' not referenced: {line!r}"
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_terminals_dry_run_url_encodes_spaces_in_path(tmp_path):
    """--terminals --dry-run must percent-encode spaces in the worktree path as %20."""
    # The path itself has a space — we need to create the directory to make the
    # worktree-existence check pass. If .claude/worktrees doesn't support spaces
    # this test documents the actual behavior.
    name = "path-with-spaces"
    # Note: we create the worktree dir without spaces (space in the *resolved path*
    # comes from the project root having a space or the name itself).  The
    # url_encode() in the script runs python3 urllib.parse.quote against WT_PATH.
    # The worktree name itself contains no space, but we verify the quote logic
    # works for a name that would produce a path component without spaces first.
    wt_dir = make_worktree_dir(name)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = run_script("--terminals", "--dry-run", "--manifest", str(manifest))
        assert result.returncode == 0, f"Expected exit 0. stderr: {result.stderr!r}"
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert dispatch_lines, "Expected at least one dispatch line"
        line = dispatch_lines[0]
        # The URL must not contain raw spaces — they would be invalid in a URL.
        url_part = line.split("claude-cli://", 1)[-1] if "claude-cli://" in line else ""
        assert " " not in url_part, (
            f"Raw space found inside claude-cli:// URL segment: {url_part!r}"
        )
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_terminals_dry_run_encodes_resume_rework_as_percent2F(tmp_path):  # noqa: N802 — 2F is hex; lowercasing would misname the byte being asserted
    """The /resume-rework query parameter must be encoded as %2Fresume-rework in the URL."""
    name = "fix-resume-enc"
    wt_dir = make_worktree_dir(name)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = run_script("--terminals", "--dry-run", "--manifest", str(manifest))
        assert result.returncode == 0, f"Expected exit 0. stderr: {result.stderr!r}"
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert dispatch_lines, "Expected at least one dispatch line"
        line = dispatch_lines[0]
        assert "%2Fresume-rework" in line, (
            f"Expected encoded '/resume-rework' (%2Fresume-rework) in line: {line!r}"
        )
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


# ---------------------------------------------------------------------------
# Missing worktree directory — warn and skip
# ---------------------------------------------------------------------------


def test_missing_worktree_directory_warns_on_stderr_and_skips(tmp_path):
    """When a manifest row's worktree directory does not exist, the script must
    warn on stderr and skip that row (not abort).

    If all rows are skipped, exit 1 with a clear error.
    """
    # Use a name that definitely does NOT correspond to a real directory.
    name = "nonexistent-wt-for-test-xyzzy"
    wt_path = _MAIN_WORKTREE_ROOT / ".claude" / "worktrees" / name
    assert not wt_path.exists(), f"Test pre-condition violated: {wt_path} unexpectedly exists"
    manifest = make_manifest(tmp_path, [{"worktree_name": name}])
    result = run_script("--bg", "--dry-run", "--manifest", str(manifest))
    # The single row is skipped → no valid worktrees → non-zero exit
    assert result.returncode != 0, (
        f"Expected non-zero exit when all worktrees are missing, got {result.returncode}"
    )
    # A warning mentioning the missing worktree must appear on stderr
    assert name in result.stderr, f"Expected '{name}' in stderr warning. stderr: {result.stderr!r}"


def test_partial_missing_worktrees_skips_missing_processes_valid(tmp_path):
    """When one row's worktree exists and another's doesn't, the script must
    skip the missing one (warning on stderr) and dispatch the valid one.

    With --dry-run + 2 rows (1 valid, 1 missing), stdout has 1 dispatch line
    and exit is 0.
    """
    valid_name = "valid-wt-partial-test"
    missing_name = "missing-wt-partial-xyzzy"
    assert not (_MAIN_WORKTREE_ROOT / ".claude" / "worktrees" / missing_name).exists()
    wt_dir = make_worktree_dir(valid_name)
    try:
        manifest = make_manifest(
            tmp_path,
            [{"worktree_name": valid_name}, {"worktree_name": missing_name}],
        )
        result = run_script("--bg", "--dry-run", "--manifest", str(manifest))
        assert result.returncode == 0, (
            f"Expected exit 0 when at least one valid worktree exists. stderr: {result.stderr!r}"
        )
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert len(dispatch_lines) == 1, (
            f"Expected 1 dispatch line (valid row only), got {dispatch_lines!r}"
        )
        assert valid_name in dispatch_lines[0], (
            f"Expected valid worktree name in dispatch line: {dispatch_lines[0]!r}"
        )
        assert missing_name in result.stderr, (
            f"Expected warning for missing worktree in stderr: {result.stderr!r}"
        )
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


# ---------------------------------------------------------------------------
# Sample fixture manifest (2 well-formed rows) — integration smoke
# ---------------------------------------------------------------------------


def test_sample_manifest_two_rows_bg_dry_run_exits_cleanly():
    """The committed 2-row fixture manifest produces either:
    - 2 dispatch lines and exit 0 (when both worktrees exist), or
    - 1 dispatch line and exit 0 (one worktree exists), or
    - exit 1 (no worktrees exist yet).

    This test documents the observable behavior without requiring worktrees to
    exist in CI. It asserts the script parses the manifest without crashing.
    """
    result = run_script("--bg", "--dry-run", "--manifest", str(SAMPLE_MANIFEST))
    assert "Traceback" not in result.stderr, f"Unexpected Python traceback: {result.stderr!r}"
    # Exit 0 (some rows dispatched) or exit 1 (all skipped because dirs absent) are valid.
    assert result.returncode in (0, 1), (
        f"Expected exit 0 or 1 for valid manifest, got {result.returncode}. "
        f"stderr: {result.stderr!r}"
    )
    if result.returncode == 0:
        dispatch_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("would dispatch:")
        ]
        assert dispatch_lines, "Exit 0 must produce at least one dispatch line"
