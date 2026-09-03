"""Behavioral tests for `sidecar_autocommit.py` -- Stop hook autocommit.

Written test-first, concurrently with the implementation (RED handshake: the
module under test does not exist yet -- every test here fails with
`FileNotFoundError` until `hooks/sidecar_autocommit.py` lands). Tests
drive the hook exactly as Claude Code does: JSON payload on stdin, exit code
as the pass/fail signal -- never internal functions, which do not exist yet.

The fast-exit contract: the hook "fast-exits on one `lstat` when `.ai-state` is
not a symlink (zero subprocess calls)". Pinned assumption for the symlinked
(`SidecarOwned`) path: the hook reads dirtiness and policy from
`praxion-sidecar status --json`'s `sidecar.dirty_files` / `autocommit` fields
(the same public JSON contract `inject_sidecar_banner.py` consumes), rather
than shelling out to `git status --porcelain` in the mount directly -- see
`LEARNINGS_test-engineer.md` for the reasoning (keeps git plumbing behind the
CLI boundary, matching the whole design's "hooks are thin consumers" shape).
Stub-CLI mechanics and the `SidecarOwned` fixture recipe mirror
`test_inject_sidecar_banner.py` (duplicated here deliberately -- these are two
independent, self-contained spec files, and hooks/ carries no conftest.py to
extract a shared helper into).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "sidecar_autocommit.py"
DISABLE_FLAG = "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT"


# --- stub praxion-sidecar CLI -------------------------------------------------

_STUB_CLI_SOURCE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys, time

    calls_log = os.environ.get("STUB_CALLS_LOG")
    if calls_log:
        with open(calls_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(sys.argv[1:]) + "\\n")

    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    responses = json.loads(os.environ.get("STUB_RESPONSES", "{}"))
    resp = responses.get(verb, {})
    sleep_s = resp.get("sleep_seconds")
    if sleep_s:
        time.sleep(sleep_s)
    stdout = resp.get("stdout", "")
    stderr = resp.get("stderr", "")
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    sys.exit(resp.get("exit_code", 0))
    """
)


def _install_stub_cli(tmp_path: Path, responses: dict) -> tuple[dict[str, str], Path]:
    """Install a fake `praxion-sidecar` reachable via PATH AND via
    `${CLAUDE_PLUGIN_ROOT}/scripts/praxion-sidecar` (see the sibling banner
    test file for why both channels are covered)."""
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    plugin_root = tmp_path / "stub-plugin"
    (plugin_root / "scripts").mkdir(parents=True, exist_ok=True)
    calls_log = tmp_path / "calls.jsonl"

    for target in (bin_dir / "praxion-sidecar", plugin_root / "scripts" / "praxion-sidecar"):
        target.write_text(_STUB_CLI_SOURCE, encoding="utf-8")
        mode = target.stat().st_mode
        target.chmod(mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        "STUB_RESPONSES": json.dumps(responses),
        "STUB_CALLS_LOG": str(calls_log),
    }
    return env, calls_log


def _read_calls(calls_log: Path) -> list[list[str]]:
    if not calls_log.exists():
        return []
    return [json.loads(line) for line in calls_log.read_text().splitlines() if line.strip()]


# --- SidecarOwned project fixture --------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_sidecar_repo(sidecar_root: Path) -> None:
    sidecar_root.mkdir(parents=True, exist_ok=True)
    _git(sidecar_root, "init", "-q", "-b", "main")
    _git(sidecar_root, "config", "user.email", "sidecar@example.com")
    _git(sidecar_root, "config", "user.name", "Sidecar Test")
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("# design\n")
    _git(sidecar_root, "add", "-A")
    _git(sidecar_root, "commit", "-q", "-m", "seed sidecar state")
    _git(sidecar_root, "checkout", "-q", "--detach")


def _mount_sidecar(sidecar_root: Path, project_root: Path) -> Path:
    mount_dir = project_root / ".praxion"
    _git(sidecar_root, "worktree", "add", "-q", str(mount_dir), "main")
    return mount_dir


def _write_manifest(sidecar_root: Path, *, project_root: Path, autocommit: str) -> None:
    manifest_path = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest_path.write_text(
        "schema: 1\n"
        "project:\n"
        '  origin: "https://github.com/acme/billing"\n'
        '  id: "github.com--acme--billing"\n'
        f'  roots: ["{project_root.resolve()}"]\n'
        "paths: {}\n"
        "excludes: []\n"
        f"autocommit: {autocommit}\n"
        "remote: null\n"
    )


def _link_shadow(project_root: Path) -> None:
    (project_root / ".ai-state").symlink_to(
        Path(".praxion") / ".ai-state", target_is_directory=True
    )


def _sidecar_owned_project(
    root: Path, *, autocommit: str = "on-finalize-and-stop"
) -> tuple[Path, Path]:
    """Build a `SidecarOwned` project at `root`. Returns (project_root, sidecar_root)."""
    sidecar_root = root / "sidecar"
    project_root = root / "project"
    project_root.mkdir(parents=True)
    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "p@p.p")
    _git(project_root, "config", "user.name", "p")
    # `_require_identity_match` compares the manifest's recorded origin
    # against the project's OWN `remote.origin.url` when origin is set (the
    # manifest below always sets one) -- without this remote the mount
    # resolves to `Foreign`/`IDENTITY_MISMATCH`, never `SidecarOwned`.
    _git(project_root, "remote", "add", "origin", "https://github.com/acme/billing")
    _init_sidecar_repo(sidecar_root)
    _mount_sidecar(sidecar_root, project_root)
    _write_manifest(sidecar_root, project_root=project_root, autocommit=autocommit)
    _link_shadow(project_root)
    return project_root, sidecar_root


def _status_json_response(sidecar_root: Path, *, dirty_files: int, autocommit: str) -> str:
    payload = {
        "schema": 1,
        "placement": "sidecar",
        "project": {"root": "/fake/project", "origin": "https://github.com/acme/billing"},
        "checkout": {"root": "/fake/project", "kind": "main", "total_checkouts": 1},
        "sidecar": {
            "root": str(sidecar_root),
            "branch": "main",
            "dirty_files": dirty_files,
            "unpushed_commits": 0,
            "last_commit_at": None,
        },
        "remote": None,
        "autocommit": autocommit,
        "paths": [],
        "healthy": True,
        "failed_checks": [],
    }
    return json.dumps(payload)


def _run_hook(payload: dict, env: dict) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=15,
    )


# --- tests ---------------------------------------------------------------------


class TestFastExit:
    def test_real_directory_ai_state_makes_zero_subprocess_calls(self, tmp_path):
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / ".ai-state").mkdir()
        env, calls_log = _install_stub_cli(tmp_path, {"status": {"stdout": "{}"}, "commit": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        assert _read_calls(calls_log) == [], (
            "an InRepo project must never invoke praxion-sidecar -- the .ai-state "
            "lstat check alone must decide this, with zero subprocess calls"
        )


class TestDirtyMountInvokesCommit:
    def test_dirty_mount_with_on_finalize_and_stop_invokes_commit_quiet(self, tmp_path):
        project_root, sidecar_root = _sidecar_owned_project(
            tmp_path, autocommit="on-finalize-and-stop"
        )
        response = _status_json_response(
            sidecar_root, dirty_files=3, autocommit="on-finalize-and-stop"
        )
        env, calls_log = _install_stub_cli(
            tmp_path, {"status": {"stdout": response}, "commit": {"exit_code": 0}}
        )

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        verbs = [call[0] for call in _read_calls(calls_log) if call]
        assert "commit" in verbs


class TestPolicyGating:
    @pytest.mark.parametrize("policy", ["on-finalize", "manual"])
    def test_policy_other_than_on_finalize_and_stop_skips_commit(self, tmp_path, policy):
        project_root, sidecar_root = _sidecar_owned_project(tmp_path, autocommit=policy)
        response = _status_json_response(sidecar_root, dirty_files=3, autocommit=policy)
        env, calls_log = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "commit": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        verbs = [call[0] for call in _read_calls(calls_log) if call]
        assert "commit" not in verbs, f"policy {policy!r} must never trigger a commit"


class TestCleanMountSkipsCommit:
    def test_clean_mount_never_invokes_commit(self, tmp_path):
        project_root, sidecar_root = _sidecar_owned_project(
            tmp_path, autocommit="on-finalize-and-stop"
        )
        response = _status_json_response(
            sidecar_root, dirty_files=0, autocommit="on-finalize-and-stop"
        )
        env, calls_log = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "commit": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        verbs = [call[0] for call in _read_calls(calls_log) if call]
        assert "commit" not in verbs


class TestCommitFailureIsIgnored:
    def test_nonzero_commit_exit_code_still_exits_0(self, tmp_path):
        project_root, sidecar_root = _sidecar_owned_project(
            tmp_path, autocommit="on-finalize-and-stop"
        )
        response = _status_json_response(
            sidecar_root, dirty_files=1, autocommit="on-finalize-and-stop"
        )
        env, calls_log = _install_stub_cli(
            tmp_path,
            {"status": {"stdout": response}, "commit": {"exit_code": 3, "stderr": "refused"}},
        )

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0, "a Stop hook must never fail the session on commit refusal"
        verbs = [call[0] for call in _read_calls(calls_log) if call]
        assert "commit" in verbs


class TestDisableFlag:
    def test_disable_flag_skips_even_when_dirty(self, tmp_path):
        project_root, sidecar_root = _sidecar_owned_project(
            tmp_path, autocommit="on-finalize-and-stop"
        )
        response = _status_json_response(
            sidecar_root, dirty_files=5, autocommit="on-finalize-and-stop"
        )
        env, calls_log = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "commit": {}})
        env[DISABLE_FLAG] = "1"

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        assert _read_calls(calls_log) == []


class TestUnresolvableCli:
    def test_missing_cli_binary_exits_0_without_crashing(self, tmp_path):
        project_root, _sidecar_root = _sidecar_owned_project(
            tmp_path, autocommit="on-finalize-and-stop"
        )
        env = {
            "PATH": "/usr/bin:/bin",
            "CLAUDE_PLUGIN_ROOT": str(tmp_path / "nonexistent-plugin-root"),
        }

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
