"""Hook-mode and walk-pruning tests for scripts/check_id_citation_discipline.py.

Background: registered as a blocking PreToolUse gate on ``git commit``, the
checker received the tool payload on stdin and — having no ``--files`` — ran a
full-repository scan. Two defects followed. The scan walked every vendored
tree before filtering it, so on a checkout with an installed dashboard it
exceeded the hook budget and failed open; a fresh worktree walked fast and
failed closed on every pre-existing violation in the tree, none of them in the
commit being gated. Hook mode scopes the scan to the files the commit records;
directory pruning bounds the full scan by the corpus, not the checkout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts" / "check_id_citation_discipline.py"

VIOLATING_LINE = "# see AC-14 for the acceptance criterion\n"  # id-citation-discipline:ignore
VIOLATING_JS_LINE = "// Step 4 wires this\n"  # id-citation-discipline:ignore
CLEAN_LINE = "# nothing ephemeral cited here\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")


def _write(repo: Path, rel: str, body: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _commit_all(repo: Path, message: str = "c") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _run_hook(repo: Path, command: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)}
    )
    return subprocess.run(
        [sys.executable, str(CHECKER)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(repo),
    )


def _run_full(repo: Path, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    kwargs: dict = {"capture_output": True, "text": True, "cwd": str(repo)}
    if stdin_text is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = stdin_text
    return subprocess.run([sys.executable, str(CHECKER), "--repo-root", str(repo)], **kwargs)


def test_hook_mode_scans_only_the_staged_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, "src/legacy.py", VIOLATING_LINE)
    _commit_all(tmp_path)
    _write(tmp_path, "src/clean.py", CLEAN_LINE)
    _git(tmp_path, "add", "src/clean.py")

    result = _run_hook(tmp_path, 'git commit -q -m "add clean"')

    assert result.returncode == 0, result.stdout + result.stderr
    assert "legacy.py" not in result.stdout


def test_hook_mode_blocks_a_staged_violation(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, "src/bad.py", VIOLATING_LINE)
    _git(tmp_path, "add", "src/bad.py")

    result = _run_hook(tmp_path, 'git commit -m "add bad"')

    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/bad.py" in result.stdout


def test_hook_mode_with_nothing_staged_passes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, "src/legacy.py", VIOLATING_LINE)
    _commit_all(tmp_path)

    result = _run_hook(tmp_path, "git commit --amend --no-edit")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no staged code files" in result.stdout


def test_hook_mode_commit_all_includes_unstaged_tracked_changes(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", CLEAN_LINE)
    _commit_all(tmp_path)
    _write(tmp_path, "src/mod.py", CLEAN_LINE + VIOLATING_LINE)

    without_all = _run_hook(tmp_path, 'git commit -m "x"')
    with_all = _run_hook(tmp_path, 'git commit -am "x"')

    assert without_all.returncode == 0, without_all.stdout
    assert with_all.returncode == 1, with_all.stdout
    assert "src/mod.py" in with_all.stdout


def test_hook_mode_ignores_staged_non_code_files(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path, "docs/notes.md", VIOLATING_LINE)
    _write(tmp_path, ".ai-state/ledger.md", VIOLATING_LINE)
    _git(tmp_path, "add", "-A")

    result = _run_hook(tmp_path, 'git commit -m "docs"')

    assert result.returncode == 0, result.stdout + result.stderr


def test_hook_payload_outside_a_repository_falls_back_to_full_scan(tmp_path: Path) -> None:
    _write(tmp_path, "src/bad.py", VIOLATING_LINE)

    result = _run_hook(tmp_path, 'git commit -m "x"')

    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/bad.py" in result.stdout


def test_non_payload_stdin_falls_back_to_full_scan(tmp_path: Path) -> None:
    _write(tmp_path, "src/bad.py", VIOLATING_LINE)

    result = _run_full(tmp_path, stdin_text="not a hook payload")

    assert result.returncode == 1, result.stdout + result.stderr


def test_open_but_silent_stdin_does_not_hang_the_full_scan(tmp_path: Path) -> None:
    _write(tmp_path, "src/ok.py", CLEAN_LINE)
    read_end, write_end = os.pipe()
    try:
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--repo-root", str(tmp_path)],
            stdin=read_end,
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=15,
        )
    finally:
        os.close(write_end)
        os.close(read_end)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "scanned 1 code file(s)" in result.stdout


def test_full_scan_prunes_vendored_trees_and_sibling_worktrees(tmp_path: Path) -> None:
    _write(tmp_path, "node_modules/pkg/index.js", VIOLATING_JS_LINE)
    _write(tmp_path, ".claude/worktrees/other/src/x.py", VIOLATING_LINE)
    _write(tmp_path, "dist/bundle.js", VIOLATING_LINE)
    _write(tmp_path, "src/ok.py", CLEAN_LINE)

    result = _run_full(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "scanned 1 code file(s)" in result.stdout


def test_full_scan_still_reports_violations_in_the_corpus(tmp_path: Path) -> None:
    _write(tmp_path, "src/ok.py", CLEAN_LINE)
    _write(tmp_path, "src/bad.py", VIOLATING_LINE)

    result = _run_full(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "src/bad.py" in result.stdout
    assert "scanned 2 code file(s)" in result.stdout
