"""Tests for the shared repo-root resolver (`scripts/_repo_root.py`).

The finalize-chain scripts share this resolver so consumer git hooks (which
symlink into the plugin cache) resolve the consumer repo, never the plugin.
These tests pin the resolution precedence, the cwd-git fallback, the
script-relative last resort + its callback, and plugin-cache detection.
"""

from __future__ import annotations

from pathlib import Path

import _repo_root
import pytest


class TestResolveRepoRoot:
    def test_explicit_repo_root_wins(self, tmp_path: Path) -> None:
        assert (
            _repo_root.resolve_repo_root(str(tmp_path), script_dir=tmp_path / "scripts")
            == tmp_path.resolve()
        )

    def test_git_toplevel_used_when_no_explicit_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_repo_root, "git_toplevel_from_cwd", lambda: tmp_path)
        assert (
            _repo_root.resolve_repo_root(None, script_dir=Path("/whatever/scripts"))
            == tmp_path.resolve()
        )

    def test_script_relative_last_resort_and_callback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_repo_root, "git_toplevel_from_cwd", lambda: None)
        seen: list[Path] = []
        result = _repo_root.resolve_repo_root(
            None,
            script_dir=Path("/plugin/praxion/0.9.0/scripts"),
            on_fallback=seen.append,
        )
        assert result == Path("/plugin/praxion/0.9.0")
        assert seen == [Path("/plugin/praxion/0.9.0")]


class TestGitToplevelFromCwd:
    def test_returns_none_when_not_a_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Run from a non-repo directory; git rev-parse exits non-zero -> None.
        monkeypatch.chdir(tmp_path)
        assert _repo_root.git_toplevel_from_cwd() is None

    def test_returns_repo_root_when_cwd_is_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess as sp

        sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        monkeypatch.chdir(tmp_path)
        resolved = _repo_root.git_toplevel_from_cwd()
        assert resolved is not None
        # macOS /tmp symlinks to /private/tmp; compare resolved paths.
        assert resolved.resolve() == tmp_path.resolve()


class TestIsPluginCachePath:
    @pytest.mark.parametrize(
        "path",
        [
            "/Users/x/.claude/plugins/cache/bit-agora/praxion/0.9.0",
            "/home/u/.config/plugins/cache",
        ],
    )
    def test_detects_cache_paths(self, path: str) -> None:
        assert _repo_root.is_plugin_cache_path(Path(path)) is True

    @pytest.mark.parametrize(
        "path",
        ["/Users/x/dev/sandbook", "/tmp/consumer", "/srv/repos/myproj"],
    )
    def test_allows_normal_paths(self, path: str) -> None:
        assert _repo_root.is_plugin_cache_path(Path(path)) is False
