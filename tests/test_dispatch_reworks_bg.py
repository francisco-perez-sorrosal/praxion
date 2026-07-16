"""Behavioral tests for scripts/dispatch-reworks: real --bg dispatch path.

Tests the dispatch_bg() function's observable behaviors via a stub `claude`
binary injected at the front of PATH.  No real claude --bg sessions are spawned.

Stub strategy
-------------
Each test that exercises the live-dispatch path creates a temp directory,
writes an executable `claude` shell script there, and passes it via the
`env=` dict of subprocess.run.  The stub emits the same "backgrounded · <id>"
output shape Claude Code produces on a real `claude --bg` invocation.

The stub generates a distinct 8-hex-character session ID per invocation from
its own PID — distinct per process by construction, POSIX-sh portable (a
$RANDOM-based version emitted a constant '00000000' under dash on CI); IDs are
not cryptographically significant here.  Passing a magic `--fail-me` flag causes
the stub to exit non-zero with an error on stderr — used for failure-path tests.

All tests reuse the helpers and worktree-root detection established in the
sibling test_dispatch_reworks_manifest.py so the patterns are consistent.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "dispatch-reworks"

# The script resolves PROJECT_ROOT via `git worktree list --porcelain` (first
# line = main checkout).  When tests run from a linked worktree the main
# checkout path differs from the linked worktree.  Derive once at module load.
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
# Helpers shared with the sibling test module
# ---------------------------------------------------------------------------


def run_script(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run scripts/dispatch-reworks with the given arguments; capture all output."""
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env or os.environ.copy(),
    )


def make_manifest(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a synthetic REWORK_MANIFEST.md in tmp_path with the given rows."""
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
            **row,
        }
        blocks.append(f"### Row {i} — {full_row.get('worktree_name', f'row-{i}')}\n")
        blocks.append("```json")
        blocks.append(json.dumps(full_row, indent=2))
        blocks.append("```")
    header = textwrap.dedent("""\
        # Rework Manifest — synthetic-test

        Generated: 2026-05-15T00:00:00Z.

    """)
    manifest = tmp_path / "REWORK_MANIFEST.md"
    manifest.write_text(header + "\n".join(blocks) + "\n", encoding="utf-8")
    return manifest


def make_worktree_dir(name: str) -> Path:
    """Create (or confirm) the expected worktree directory under the main checkout."""
    wt_dir = _MAIN_WORKTREE_ROOT / ".claude" / "worktrees" / name
    wt_dir.mkdir(parents=True, exist_ok=True)
    return wt_dir


# ---------------------------------------------------------------------------
# Stub claude binary factory
# ---------------------------------------------------------------------------

# The stub emits the same shape Claude Code produces on `claude --bg ...`:
#
#   Starting background service…
#   backgrounded · <8-hex-id>
#     claude agents             list sessions
#     claude attach <id>        open in this terminal
#     claude logs <id>          show recent output
#     claude stop <id>          stop this session
#
# The ID is derived from the stub's own PID ($$) so that multiple calls
# within one test receive distinct IDs. POSIX-portable on purpose: $RANDOM
# is a bash-ism that expands empty under dash (Ubuntu's /bin/sh), which
# made every CI invocation emit the same '00000000'. Passing `--fail-me`
# causes the stub to exit non-zero — used for failure-path tests.

_STUB_CLAUDE_TEMPLATE = textwrap.dedent("""\
    #!/bin/sh
    # Stub claude binary for dispatch-reworks tests.
    # Emits the same "backgrounded · <id>" shape as the real claude --bg.
    for arg in "$@"; do
        case "$arg" in
            --fail-me)
                printf "claude: simulated dispatch error\\n" >&2
                exit 1
                ;;
        esac
    done
    # 8-hex-char ID from the stub's PID: distinct per invocation, POSIX sh.
    ID=$(printf "%08x" $$)
    printf "Starting background service\\xe2\\x80\\xa6\\n"
    printf "backgrounded \\xc2\\xb7 %s\\n" "$ID"
    printf "  claude agents             list sessions\\n"
    printf "  claude attach %s    open in this terminal\\n" "$ID"
    printf "  claude logs %s      show recent output\\n" "$ID"
    printf "  claude stop %s      stop this session\\n" "$ID"
""")


def make_stub_claude(
    stub_dir: Path,
    *,
    fail_name: str | None = None,
    home: Path | None = None,
) -> dict:
    """Write the stub `claude` script into stub_dir and return an env dict.

    Args:
        stub_dir: Directory to place the stub executable.
        fail_name: If given, the stub exits non-zero when invoked with a
            ``--name`` value containing this substring.  Used for per-row
            failure tests.
        home: If given, override ``HOME`` in the returned env dict so the
            dispatcher's marker-file writes land in this isolated path
            (under ``<home>/.claude/rework_sessions/``) rather than the
            real user home.

    Returns:
        A copy of os.environ with stub_dir prepended to PATH and (if ``home``
        is provided) ``HOME`` overridden.
    """
    script_body = _STUB_CLAUDE_TEMPLATE
    if fail_name is not None:
        # Inject a name-based failure gate before the success path.
        fail_block = textwrap.dedent(f"""\
            for arg in "$@"; do
                case "$arg" in
                    *{fail_name}*)
                        printf "claude: name-based failure for %s\\n" "$arg" >&2
                        exit 1
                        ;;
                esac
            done
        """)
        # Insert after the shebang and comment line.
        lines = script_body.splitlines(keepends=True)
        script_body = "".join(lines[:2]) + fail_block + "".join(lines[2:])

    stub = stub_dir / "claude"
    stub.write_text(script_body, encoding="utf-8")
    stub.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{stub_dir}:{env.get('PATH', '')}"
    if home is not None:
        env["HOME"] = str(home)
    return env


# ---------------------------------------------------------------------------
# Happy-path dispatch: row counts
# ---------------------------------------------------------------------------


def test_one_row_manifest_dispatches_one_session(tmp_path, tmp_path_factory):
    """A 1-row manifest must produce exactly 1 session dispatch and report it."""
    name = "bg-single-row-test"
    wt_dir = make_worktree_dir(name)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert (
            "Dispatched 1 rework session(s):" in result.stdout
        ), f"Expected 'Dispatched 1 rework session(s):' in stdout: {result.stdout!r}"
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_two_row_manifest_dispatches_two_sessions(tmp_path, tmp_path_factory):
    """A 2-row manifest must produce 2 session IDs in the output."""
    names = ["bg-two-row-a", "bg-two-row-b"]
    wt_dirs = [make_worktree_dir(n) for n in names]
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": n} for n in names])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert (
            "Dispatched 2 rework session(s):" in result.stdout
        ), f"Expected 'Dispatched 2 rework session(s):' in stdout: {result.stdout!r}"
        # Both worktree names should appear in the summary block.
        for name in names:
            assert (
                name in result.stdout
            ), f"Expected worktree name '{name}' in stdout: {result.stdout!r}"
    finally:
        for d in wt_dirs:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()


def test_three_row_manifest_preserves_row_order(tmp_path, tmp_path_factory):
    """A 3-row manifest must print summary lines in manifest row order."""
    names = ["bg-order-alpha", "bg-order-beta", "bg-order-gamma"]
    wt_dirs = [make_worktree_dir(n) for n in names]
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": n} for n in names])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert (
            result.returncode == 0
        ), f"Expected exit 0, got {result.returncode}. stderr: {result.stderr!r}"
        assert (
            "Dispatched 3 rework session(s):" in result.stdout
        ), f"Expected 'Dispatched 3 rework session(s):' in stdout: {result.stdout!r}"
        # Verify row order: alpha must appear before beta, beta before gamma.
        alpha_pos = result.stdout.find("bg-order-alpha")
        beta_pos = result.stdout.find("bg-order-beta")
        gamma_pos = result.stdout.find("bg-order-gamma")
        assert alpha_pos < beta_pos < gamma_pos, (
            f"Row order not preserved in stdout. "
            f"alpha={alpha_pos}, beta={beta_pos}, gamma={gamma_pos}"
        )
    finally:
        for d in wt_dirs:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()


def test_two_rows_produce_distinct_session_ids(tmp_path, tmp_path_factory):
    """Two rows dispatched via the stub must receive distinct session IDs.

    The stub derives its ID from its own PID per invocation.  This test
    asserts two invocations produce two different values so that the
    per-session hints in the output are not aliased.
    """
    names = ["bg-distinct-id-x", "bg-distinct-id-y"]
    wt_dirs = [make_worktree_dir(n) for n in names]
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": n} for n in names])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert (
            result.returncode == 0
        ), f"Expected exit 0, got {result.returncode}. stderr: {result.stderr!r}"
        # Extract session IDs from the "peek: claude logs <id>" lines.
        import re

        ids = re.findall(r"peek:\s+claude logs ([0-9a-f]+)", result.stdout)
        assert (
            len(ids) == 2
        ), f"Expected 2 peek lines in stdout, found: {ids!r}. stdout: {result.stdout!r}"
        assert ids[0] != ids[1], (
            f"Both rows received the same session ID '{ids[0]}'; "
            "stub must generate distinct IDs per invocation."
        )
    finally:
        for d in wt_dirs:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()


# ---------------------------------------------------------------------------
# Session-ID extraction regression (middle-dot UTF-8 bug)
# ---------------------------------------------------------------------------


def test_session_id_not_extracted_from_word_backgrounded(tmp_path, tmp_path_factory):
    """The script must not extract partial hex from the word 'backgrounded' itself.

    The original bug: `grep -oE 'backgrounded · [0-9a-f]+'` failed on the
    UTF-8 middle-dot (U+00B7) and fell back to the first hex run inside the
    word 'backgrounded' (e.g., 'bac', 'acd').  The fix uses
    `grep 'backgrounded' | awk '{print $NF}'`.

    Regression anchor: verify the extracted ID is NOT one of the hex substrings
    of the word "backgrounded" — specifically "bac" and "acd" which are the
    false-positives the original grep produced.
    """
    # Use a stub that emits a known session ID that differs from 'bac'/'acd'.
    known_id = "cafebabe"
    stub_body = textwrap.dedent(f"""\
        #!/bin/sh
        printf "Starting background service\\xe2\\x80\\xa6\\n"
        printf "backgrounded \\xc2\\xb7 {known_id}\\n"
        printf "  claude agents             list sessions\\n"
        printf "  claude attach {known_id}    open in this terminal\\n"
        printf "  claude logs {known_id}      show recent output\\n"
        printf "  claude stop {known_id}      stop this session\\n"
    """)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    stub = stub_dir / "claude"
    stub.write_text(stub_body, encoding="utf-8")
    stub.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub_dir}:{env.get('PATH', '')}"
    env["HOME"] = str(tmp_path)

    name = "bg-middledot-regression"
    wt_dir = make_worktree_dir(name)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        # The correct session ID must appear in the output.
        assert (
            known_id in result.stdout
        ), f"Expected session ID '{known_id}' in stdout but got: {result.stdout!r}"
        # False-positive substrings of 'backgrounded' must NOT appear as IDs.
        assert (
            "peek:   claude logs bac" not in result.stdout
        ), "Script extracted 'bac' (hex from 'backgrounded') — middle-dot bug still present."
        assert (
            "peek:   claude logs acd" not in result.stdout
        ), "Script extracted 'acd' (hex from 'backgrounded') — middle-dot bug still present."
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_session_id_containing_bac_extracted_correctly(tmp_path, tmp_path_factory):
    """A session ID that starts with 'bac' must be extracted in full.

    This was the original false-positive prefix from the word 'backgrounded'.
    The fix (awk $NF) must extract the full ID regardless of whether it begins
    with substrings found in the literal word 'backgrounded'.
    """
    # Craft a session ID that starts with 'bac' — the old bug's false match.
    tricky_id = "bac1234f"
    stub_body = textwrap.dedent(f"""\
        #!/bin/sh
        printf "Starting background service\\xe2\\x80\\xa6\\n"
        printf "backgrounded \\xc2\\xb7 {tricky_id}\\n"
        printf "  claude agents             list sessions\\n"
        printf "  claude attach {tricky_id}    open in this terminal\\n"
        printf "  claude logs {tricky_id}      show recent output\\n"
        printf "  claude stop {tricky_id}      stop this session\\n"
    """)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    stub = stub_dir / "claude"
    stub.write_text(stub_body, encoding="utf-8")
    stub.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub_dir}:{env.get('PATH', '')}"
    env["HOME"] = str(tmp_path)

    name = "bg-bac-id-regression"
    wt_dir = make_worktree_dir(name)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert (
            result.returncode == 0
        ), f"Expected exit 0, got {result.returncode}. stderr: {result.stderr!r}"
        # Full tricky ID must appear; partial match (just "bac") must not be the only one.
        assert (
            f"peek:   claude logs {tricky_id}" in result.stdout
        ), f"Expected full ID '{tricky_id}' in peek line. stdout: {result.stdout!r}"
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


# ---------------------------------------------------------------------------
# Closing summary format
# ---------------------------------------------------------------------------


def test_closing_summary_contains_claude_agents_line(tmp_path, tmp_path_factory):
    """Output must contain the exact 'claude agents' monitoring line."""
    name = "bg-summary-agents"
    wt_dir = make_worktree_dir(name)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, f"Expected exit 0. stderr: {result.stderr!r}"
        expected_line = (
            "To monitor all sessions in one view: open a fresh Cursor terminal pane "
            "and run `claude agents`."
        )
        assert (
            expected_line in result.stdout
        ), f"Closing 'claude agents' line not found. stdout: {result.stdout!r}"
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_closing_summary_contains_osascript_hook_note(tmp_path, tmp_path_factory):
    """Output must contain the macOS notifications reference line."""
    name = "bg-summary-osascript"
    wt_dir = make_worktree_dir(name)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, f"Expected exit 0. stderr: {result.stderr!r}"
        expected_line = (
            "macOS notifications will fire when each session completes "
            "(via the osascript Stop hook)."
        )
        assert (
            expected_line in result.stdout
        ), f"osascript notification line not found. stdout: {result.stdout!r}"
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_per_session_hints_use_exact_format(tmp_path, tmp_path_factory):
    """Per-session hints must use the exact 'peek:' and 'cancel:' prefix format."""
    name = "bg-hints-format"
    wt_dir = make_worktree_dir(name)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, f"Expected exit 0. stderr: {result.stderr!r}"
        # Extract the session ID to verify the exact hint lines.
        import re

        ids = re.findall(r"peek:\s+claude logs ([0-9a-f]+)", result.stdout)
        assert ids, f"No 'peek: claude logs <id>' line found in stdout: {result.stdout!r}"
        session_id = ids[0]
        assert (
            f"peek:   claude logs {session_id}" in result.stdout
        ), f"'peek:   claude logs <id>' format wrong. stdout: {result.stdout!r}"
        assert (
            f"cancel: claude stop {session_id}" in result.stdout
        ), f"'cancel: claude stop <id>' format wrong. stdout: {result.stdout!r}"
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_stub_failure_for_one_row_continues_remaining(tmp_path, tmp_path_factory):
    """When one row's dispatch fails, the script continues to the next row.

    The stub is configured to fail when the --name flag contains 'fail-target'.
    The other row succeeds.  Expected: exit 0 (at least one dispatched),
    'Dispatched 1 rework session(s):', and a warning on stderr for the failed row.
    """
    fail_name_slug = "fail-target"
    succeed_name = "bg-fail-one-succeed"
    wt_dirs = [make_worktree_dir(n) for n in [fail_name_slug, succeed_name]]
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, fail_name=fail_name_slug, home=tmp_path)
    try:
        manifest = make_manifest(
            tmp_path,
            [
                {"worktree_name": fail_name_slug},
                {"worktree_name": succeed_name},
            ],
        )
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        # At least one row succeeded → exit 0.
        assert result.returncode == 0, (
            f"Expected exit 0 when one row succeeds. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert (
            "Dispatched 1 rework session(s):" in result.stdout
        ), f"Expected 1 dispatched in stdout: {result.stdout!r}"
        # A warning for the failed row must appear on stderr.
        assert (
            fail_name_slug in result.stderr
        ), f"Expected warning for '{fail_name_slug}' in stderr: {result.stderr!r}"
    finally:
        for d in wt_dirs:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()


def test_all_rows_fail_exits_non_zero(tmp_path, tmp_path_factory):
    """When every row's dispatch fails, the script exits non-zero."""
    name = "bg-all-fail-row"
    wt_dir = make_worktree_dir(name)
    # Use the generic --fail-me stub (not the name-based one) by writing a
    # stub that always fails.
    always_fail_body = textwrap.dedent("""\
        #!/bin/sh
        printf "claude: always-fail stub\\n" >&2
        exit 1
    """)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    stub = stub_dir / "claude"
    stub.write_text(always_fail_body, encoding="utf-8")
    stub.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{stub_dir}:{env.get('PATH', '')}"
    env["HOME"] = str(tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode != 0, (
            f"Expected non-zero exit when all dispatches fail, got {result.returncode}. "
            f"stdout={result.stdout!r}"
        )
        # A clear error must appear — either on stderr or stdout.
        combined = result.stdout + result.stderr
        assert (
            "failed" in combined.lower()
        ), f"Expected failure message in output: stdout={result.stdout!r} stderr={result.stderr!r}"
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_claude_not_on_path_exits_non_zero(tmp_path):
    """When the `claude` binary is not on PATH, the script exits non-zero."""
    name = "bg-no-claude-on-path"
    wt_dir = make_worktree_dir(name)
    # Use a PATH that contains only system directories with no `claude`.
    minimal_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=minimal_env,
        )
        assert result.returncode != 0, (
            f"Expected non-zero exit when claude is not on PATH, got {result.returncode}. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_zero_valid_rows_after_parse_exits_empty(tmp_path):
    """A manifest with no worktree_name values (all skip) must exit non-zero cleanly."""
    manifest = tmp_path / "REWORK_MANIFEST.md"
    manifest.write_text(
        textwrap.dedent("""\
            # Rework Manifest — no-name rows

            ```json
            {
              "id": "rw-noname",
              "target_agent": "implementer",
              "severity": "important",
              "headline": "Row with no worktree_name field"
            }
            ```
        """),
        encoding="utf-8",
    )
    result = run_script("--bg", "--manifest", str(manifest))
    # The script exits 1 (general) or 4 (empty) when no valid rows are found.
    assert result.returncode in (1, 4), (
        f"Expected non-zero exit for zero-valid-row manifest, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Traceback" not in result.stderr, f"Unexpected Python traceback: {result.stderr!r}"


# ---------------------------------------------------------------------------
# Marker-file write (notification correlation)
# ---------------------------------------------------------------------------


def test_dispatch_writes_marker_file_with_worktree_name(tmp_path, tmp_path_factory):
    """Each dispatched session writes a marker at HOME/.claude/rework_sessions/<id>.

    The marker filename is the 8-hex short session ID extracted from the
    ``claude --bg`` output; its content is the worktree slug so the Stop hook
    can recover the rework label for the macOS notification.
    """
    name = "bg-marker-write"
    wt_dir = make_worktree_dir(name)
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": name}])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert (
            result.returncode == 0
        ), f"Expected exit 0, got {result.returncode}. stderr={result.stderr!r}"

        markers_dir = tmp_path / ".claude" / "rework_sessions"
        assert markers_dir.is_dir(), (
            f"Marker directory must be created at {markers_dir}, "
            f"got: {sorted(p.name for p in tmp_path.iterdir())}"
        )

        markers = list(markers_dir.iterdir())
        assert len(markers) == 1, (
            f"Expected exactly 1 marker file for 1-row dispatch, got {len(markers)}: "
            f"{[m.name for m in markers]}"
        )

        marker = markers[0]
        # Filename is the 8-hex short ID, matching the dispatch summary's
        # "peek: claude logs <id>" line.
        assert (
            len(marker.name) == 8
        ), f"Marker filename must be 8-char short ID, got {marker.name!r}"
        assert all(
            c in "0123456789abcdef" for c in marker.name
        ), f"Marker filename must be hex, got {marker.name!r}"

        # Content is the worktree slug (no trailing newline guaranteed by the
        # dispatcher, but tolerate whitespace).
        assert marker.read_text(encoding="utf-8").strip() == name, (
            f"Marker content must be the worktree slug '{name}', "
            f"got: {marker.read_text(encoding='utf-8')!r}"
        )
    finally:
        if wt_dir.exists() and not any(wt_dir.iterdir()):
            wt_dir.rmdir()


def test_dispatch_writes_one_marker_per_row(tmp_path, tmp_path_factory):
    """A 2-row dispatch writes exactly 2 distinct markers, each with its slug."""
    names = ["bg-marker-row-a", "bg-marker-row-b"]
    wt_dirs = [make_worktree_dir(n) for n in names]
    stub_dir = tmp_path_factory.mktemp("stub_bin")
    env = make_stub_claude(stub_dir, home=tmp_path)
    try:
        manifest = make_manifest(tmp_path, [{"worktree_name": n} for n in names])
        result = subprocess.run(
            [str(SCRIPT), "--bg", "--manifest", str(manifest)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, f"Expected exit 0. stderr={result.stderr!r}"

        markers_dir = tmp_path / ".claude" / "rework_sessions"
        markers = list(markers_dir.iterdir())
        assert len(markers) == 2, (
            f"Expected 2 markers for 2-row dispatch, got {len(markers)}: "
            f"{[m.name for m in markers]}"
        )

        slugs = {m.read_text(encoding="utf-8").strip() for m in markers}
        assert slugs == set(
            names
        ), f"Marker contents must equal worktree slugs {set(names)}, got {slugs}"
    finally:
        for d in wt_dirs:
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
