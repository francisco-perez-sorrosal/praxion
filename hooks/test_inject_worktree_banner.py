"""Tests for inject_worktree_banner.py -- SessionStart worktree-orientation banner."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "inject_worktree_banner.py"


def _load_banner_module():
    """Load inject_worktree_banner.py by path (hooks/ is not a package)."""
    sys.path.insert(0, str(MODULE_PATH.parent))  # so `import _hook_utils` resolves
    spec = importlib.util.spec_from_file_location("inject_worktree_banner_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


banner = _load_banner_module()


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    """A real git repo serving as the 'main' worktree."""
    repo = tmp_path / "main"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


@pytest.fixture
def linked_worktree(main_repo: Path, tmp_path: Path) -> Path:
    """A linked worktree created from the main repo."""
    wt = tmp_path / "linked"
    subprocess.run(
        [
            "git",
            "-C",
            str(main_repo),
            "worktree",
            "add",
            "-q",
            str(wt),
            "-b",
            "feature",
        ],
        check=True,
    )
    return wt


def _run_hook(
    payload: dict, cwd: Path, extra_env: dict | None = None
) -> subprocess.CompletedProcess:
    """Invoke the hook as a subprocess with a JSON payload on stdin."""
    env = {**os.environ, **(extra_env or {})}
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )


def _injected_context(result: subprocess.CompletedProcess) -> str:
    """Extract the additionalContext string from a hook's stdout JSON."""
    parsed = json.loads(result.stdout)
    return parsed["hookSpecificOutput"]["additionalContext"]


class TestBannerEmitted:
    """When the session is inside a linked worktree, the banner must appear."""

    def test_emits_banner_in_linked_worktree(self, linked_worktree: Path) -> None:
        result = _run_hook({"cwd": str(linked_worktree)}, linked_worktree)
        assert result.returncode == 0
        context = _injected_context(result)
        assert "Worktree session" in context
        assert str(linked_worktree.resolve()) in context

    def test_banner_names_main_checkout(self, linked_worktree: Path, main_repo: Path) -> None:
        result = _run_hook({"cwd": str(linked_worktree)}, linked_worktree)
        assert str(main_repo.resolve()) in _injected_context(result)

    def test_banner_references_lifecycle_doc(self, linked_worktree: Path) -> None:
        context = _injected_context(_run_hook({"cwd": str(linked_worktree)}, linked_worktree))
        assert "pipeline-worktree-lifecycle" in context

    def test_falls_back_to_cwd_when_payload_lacks_cwd(self, linked_worktree: Path) -> None:
        # No "cwd" key -- the hook should fall back to the process working dir.
        result = _run_hook({}, linked_worktree)
        assert result.returncode == 0
        assert "Worktree session" in _injected_context(result)


class TestBannerSuppressed:
    """Cases where no banner must be emitted."""

    def test_silent_in_main_worktree(self, main_repo: Path) -> None:
        result = _run_hook({"cwd": str(main_repo)}, main_repo)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_silent_outside_any_git_tree(self, tmp_path: Path) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()
        result = _run_hook({"cwd": str(non_git)}, non_git)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_disable_flag_suppresses_banner(self, linked_worktree: Path) -> None:
        result = _run_hook(
            {"cwd": str(linked_worktree)},
            linked_worktree,
            extra_env={banner.DISABLE_FLAG: "1"},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestFailsOpen:
    """Internal errors must never wedge session creation."""

    def test_malformed_payload_exits_zero(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="not-json",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0

    def test_empty_payload_exits_zero(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="{}",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode == 0


class TestBannerRendering:
    """Unit-level checks on the banner text builder."""

    def test_includes_both_roots_when_main_known(self) -> None:
        text = banner._build_banner(Path("/wt/feature"), Path("/repo/main"))
        assert "/wt/feature" in text
        assert "/repo/main" in text
        assert "do not create or edit files outside this worktree" in text

    def test_degrades_when_main_root_unknown(self) -> None:
        text = banner._build_banner(Path("/wt/feature"), None)
        assert "/wt/feature" in text
        assert "git worktree list" in text


class TestReworkAffordance:
    """Banner must append a rework note iff VERIFIER_FINDINGS.md is present."""

    def test_appends_rework_paragraph_when_findings_present(self, tmp_path: Path) -> None:
        # Arrange: a worktree root with a VERIFIER_FINDINGS.md under .ai-work/<slug>/
        findings = tmp_path / ".ai-work" / "fix-auth" / "VERIFIER_FINDINGS.md"
        findings.parent.mkdir(parents=True)
        findings.write_text("# Rework\n", encoding="utf-8")

        # Act: build the banner for this worktree
        text = banner._build_banner(tmp_path, Path("/repo/main"))

        # Assert: the rework note is present with expected content
        assert "VERIFIER_FINDINGS.md" in text, "Banner must name the findings file"
        assert "/resume-rework" in text, "Banner must name the /resume-rework command"

    def test_no_change_when_findings_absent(self, tmp_path: Path) -> None:
        # Arrange: a worktree root with NO VERIFIER_FINDINGS.md anywhere
        (tmp_path / ".ai-work").mkdir()

        # Act
        text = banner._build_banner(tmp_path, Path("/repo/main"))

        # Assert: neither the findings file name nor the resume command appear
        assert "VERIFIER_FINDINGS.md" not in text
        assert "/resume-rework" not in text

    def test_fail_open_on_glob_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange: make Path.glob raise unconditionally
        original_glob = Path.glob

        def _raising_glob(self: Path, pattern: str):  # noqa: ANN001
            if pattern == ".ai-work/*/VERIFIER_FINDINGS.md":
                raise OSError("simulated glob failure")
            return original_glob(self, pattern)

        monkeypatch.setattr(Path, "glob", _raising_glob)

        # Act: _build_banner must not propagate the exception
        text = banner._build_banner(tmp_path, Path("/repo/main"))

        # Assert: returns a banner (fail-open) without the rework note
        assert text, "Banner must be returned even when glob raises"
        assert "/resume-rework" not in text

    def test_opt_out_still_suppresses_all(self, linked_worktree: Path) -> None:
        # Arrange: a real linked worktree WITH a VERIFIER_FINDINGS.md
        findings = linked_worktree / ".ai-work" / "fix-auth" / "VERIFIER_FINDINGS.md"
        findings.parent.mkdir(parents=True)
        findings.write_text("# Rework\n", encoding="utf-8")

        # Act: run the hook with the opt-out flag set
        result = _run_hook(
            {"cwd": str(linked_worktree)},
            linked_worktree,
            extra_env={banner.DISABLE_FLAG: "1"},
        )

        # Assert: no output at all — rework note is included in the suppression
        assert result.returncode == 0
        assert result.stdout.strip() == "", (
            "Opt-out must suppress the entire banner including the rework note"
        )
