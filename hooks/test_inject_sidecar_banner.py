"""Behavioral tests for `inject_sidecar_banner.py` -- SessionStart sidecar banner.

Written test-first, concurrently with the implementation (RED handshake: the
module under test does not exist yet -- every test here fails with
`FileNotFoundError` until `hooks/inject_sidecar_banner.py` lands). Tests drive
the hook exactly as Claude Code does: JSON payload on stdin, `additionalContext`
JSON on stdout, exit code as the pass/fail signal -- never the hook's internal
functions, which do not exist yet and whose shape is not this file's business.

The hook shells out to `praxion-sidecar status --json` and `praxion-sidecar
link --quiet`. Its actual resolution
mechanism for that executable (`shutil.which` via `PATH`, or a
`CLAUDE_PLUGIN_ROOT`-relative script path mirroring `heal_hook_chain.py`'s
`_resolve_plugin_root()`) is not yet decided -- this file does not depend on
either, and instead installs a stub `praxion-sidecar` reachable through BOTH
channels simultaneously (see `_install_stub_cli`). Pinned in
`LEARNINGS_test-engineer.md`.

Three further pinned assumptions, all grounded in already-shipped, already-
merged code rather than guessed:

- `status --json`'s `failed_checks` array is built by
  `scripts/_sidecar_inputs.py::_failed_check_ids` -- one entry PER OFFENDING
  ROW, bare `row.id` for most checks but `state-unmerged:<branch>` /
  `state-eligible:<branch>` for the two DS-11 convergence rows (F-3: the
  banner names branches, not just a count).
- `status --json`'s `counts` field is `scripts/_sidecar_checks.py::counts()`'s
  `{"pass": N, "warn": N, "fail": N}` tally, threaded through unchanged --
  the unhealthy line renders the real fail/warn split from it (F-4), never
  `len(failed_checks)`.
- Dirty-mount detection reads `status --json`'s `sidecar.dirty_files` field
  (`scripts/_sidecar_render.py`'s `SidecarFacts.dirty_files`), not a direct
  `git status --porcelain` call -- this is the autocommit hook's file, but the
  banner fixture-builder below is shared groundwork.
- Placement resolution (`InRepo` vs `SidecarOwned`) is subprocess-free per
  `scripts/_state_repo.py`'s own module docstring ("stdlib-only and
  subprocess-free on both happy paths") -- so the InRepo fixture below needs
  no git repository at all, matching `scripts/test_state_repo.py`'s own
  InRepo fixture exactly.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "inject_sidecar_banner.py"
DISABLE_FLAG = "PRAXION_DISABLE_SIDECAR_BANNER"
HEADING = "## Praxion sidecar (auto-injected)"


# --- stub praxion-sidecar CLI -------------------------------------------------

_STUB_CLI_SOURCE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, subprocess, sys, time

    calls_log = os.environ.get("STUB_CALLS_LOG")
    if calls_log:
        with open(calls_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(sys.argv[1:]) + "\\n")

    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    responses = json.loads(os.environ.get("STUB_RESPONSES", "{}"))
    resp = responses.get(verb, {})
    # `side_effect_argv` lets a verb actually change the filesystem -- the only
    # way to exercise a self-heal whose whole point is that the placement
    # differs before and after the call.
    side_effect_argv = resp.get("side_effect_argv")
    if side_effect_argv:
        subprocess.run(side_effect_argv, check=False)
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
    `${CLAUDE_PLUGIN_ROOT}/scripts/praxion-sidecar`. Returns (env, calls_log).

    `responses` maps verb name ("status", "link") to
    `{"stdout": str, "stderr": str, "exit_code": int, "sleep_seconds": float}`.
    """
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


def _write_manifest(sidecar_root: Path, *, project_root: Path) -> None:
    manifest_path = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest_path.write_text(
        "schema: 1\n"
        "project:\n"
        '  origin: "https://github.com/acme/billing"\n'
        '  id: "github.com--acme--billing"\n'
        f'  roots: ["{project_root.resolve()}"]\n'
        "paths: {}\n"
        "excludes: []\n"
        "autocommit: on-finalize-and-stop\n"
        "remote: null\n"
    )


def _link_shadow(project_root: Path) -> None:
    (project_root / ".ai-state").symlink_to(
        Path(".praxion") / ".ai-state", target_is_directory=True
    )


def _sidecar_owned_project(root: Path) -> tuple[Path, Path]:
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
    _write_manifest(sidecar_root, project_root=project_root)
    _link_shadow(project_root)
    return project_root, sidecar_root


@pytest.fixture
def in_repo_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".ai-state").mkdir()
    return root


@pytest.fixture
def sidecar_owned(tmp_path: Path) -> tuple[Path, Path]:
    return _sidecar_owned_project(tmp_path)


def _status_json_response(
    sidecar_root: Path,
    *,
    healthy: bool = True,
    failed_checks: list[str] | None = None,
    dirty_files: int = 0,
    counts: dict[str, int] | None = None,
) -> str:
    failed_checks = failed_checks or []
    # Default counts mirror the dogfooded scenario (F-4): an unhealthy
    # report whose rows are all WARN, never a phantom FAIL -- a caller that
    # needs a FAIL in the split passes `counts=` explicitly.
    if counts is None:
        counts = {"pass": 0, "warn": len(failed_checks) if not healthy else 0, "fail": 0}
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
        "autocommit": "on-finalize-and-stop",
        "paths": [],
        "healthy": healthy,
        "failed_checks": failed_checks,
        "counts": counts,
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


def _additional_context(result: subprocess.CompletedProcess) -> str:
    out = result.stdout.strip()
    assert out, "expected additionalContext JSON on stdout, got empty output"
    payload = json.loads(out)
    return payload["hookSpecificOutput"]["additionalContext"]


# --- tests ---------------------------------------------------------------------


class TestSilentInRepo:
    def test_in_repo_project_produces_no_output_and_invokes_no_subprocess(
        self, in_repo_project, tmp_path
    ):
        env, calls_log = _install_stub_cli(tmp_path, {"status": {"stdout": "{}"}})
        result = _run_hook({"cwd": str(in_repo_project)}, env)

        assert result.returncode == 0
        assert result.stdout.strip() == ""
        assert _read_calls(calls_log) == [], (
            "an InRepo project must never invoke praxion-sidecar -- placement "
            "resolution is subprocess-free per _state_repo.py's own contract"
        )


class TestHealthyBanner:
    def test_healthy_sidecar_owned_renders_expected_body_with_no_convergence_line(
        self, sidecar_owned, tmp_path, monkeypatch
    ):
        project_root, sidecar_root = sidecar_owned
        monkeypatch.setenv("HOME", str(tmp_path))
        response = _status_json_response(sidecar_root, healthy=True, failed_checks=[])
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        banner = _additional_context(result)
        assert HEADING in banner
        assert "lives **outside it**" in banner
        assert "excluded via `.git/info/exclude`" in banner
        assert "`git add` through the symlink fails loudly" in banner
        # tilde-abbreviated sidecar path (HOME pinned to tmp_path above)
        assert f"~/{sidecar_root.relative_to(tmp_path)}" in banner
        assert "doctor" not in banner.split("\n\n")[-1].lower() or "⚠️" not in banner
        assert "state branch" not in banner  # no convergence line at the fixed point
        assert "must target the mount path" in banner  # file-shadow write-target line


class TestUnhealthyBanner:
    def test_unhealthy_sidecar_replaces_final_sentence_with_doctor_warning(
        self, sidecar_owned, tmp_path
    ):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(
            sidecar_root, healthy=False, failed_checks=["shadow:CLAUDE.md", "hooks-path"]
        )
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        banner = _additional_context(result)
        assert HEADING in banner
        assert "⚠️ `praxion-sidecar doctor` reports 2 warnings" in banner
        assert "run it before writing state" in banner
        assert "failed" not in banner.split("reports")[1].split("—")[0], (
            "an all-WARN report must never claim a FAIL (F-4)"
        )


class TestConvergenceLine:
    def test_zero_state_rows_render_no_convergence_line(self, sidecar_owned, tmp_path):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(
            sidecar_root, healthy=False, failed_checks=["shadow:CLAUDE.md"]
        )
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        banner = _additional_context(result)
        assert "awaiting merge-back" not in banner

    def test_three_state_rows_render_exactly_one_counted_convergence_line(
        self, sidecar_owned, tmp_path
    ):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(
            sidecar_root,
            healthy=False,
            failed_checks=["state-unmerged:wt/a", "state-unmerged:wt/b", "state-eligible:wt/c"],
        )
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        banner = _additional_context(result)
        occurrences = banner.count("State branch(es) awaiting merge-back")
        assert occurrences == 1, f"expected exactly one convergence line, banner was:\n{banner}"
        assert (
            "State branch(es) awaiting merge-back: wt/a, wt/b, wt/c — run: praxion-sidecar doctor"
            in banner
        ), f"expected all three branches named, banner was:\n{banner}"

    def test_named_branch_matches_the_dogfooded_example(self, sidecar_owned, tmp_path):
        """F-3 repro: a single unmerged branch must be NAMED, not just counted."""
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(
            sidecar_root, healthy=False, failed_checks=["state-unmerged:wt/wt6"]
        )
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        banner = _additional_context(result)
        assert (
            "State branch(es) awaiting merge-back: wt/wt6 — run: praxion-sidecar doctor" in banner
        )

    def test_more_than_three_branches_shows_first_three_and_a_remainder_count(
        self, sidecar_owned, tmp_path
    ):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(
            sidecar_root,
            healthy=False,
            failed_checks=[
                "state-unmerged:wt/a",
                "state-unmerged:wt/b",
                "state-eligible:wt/c",
                "state-unmerged:wt/d",
                "state-eligible:wt/e",
            ],
        )
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        banner = _additional_context(result)
        assert "wt/a, wt/b, wt/c, and 2 more" in banner, banner
        assert "wt/d" not in banner
        assert "wt/e" not in banner


class TestDoctorSummarySplit:
    """F-4 repro: doctor's own summary is `0 failed · 2 warnings`, the banner
    must render the real split rather than treating every failed_checks entry
    as a FAIL."""

    def test_fail_and_warn_both_named(self, sidecar_owned, tmp_path):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(
            sidecar_root,
            healthy=False,
            failed_checks=["mount-conflict", "shadow:CLAUDE.md", "hooks-path"],
            counts={"pass": 0, "warn": 2, "fail": 1},
        )
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        banner = _additional_context(result)
        assert "⚠️ `praxion-sidecar doctor` reports 1 failed, 2 warnings" in banner

    def test_warnings_only_omits_the_word_failed(self, sidecar_owned, tmp_path):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(
            sidecar_root,
            healthy=False,
            failed_checks=["shadow:CLAUDE.md", "hooks-path"],
            counts={"pass": 0, "warn": 2, "fail": 0},
        )
        env, _ = _install_stub_cli(tmp_path, {"status": {"stdout": response}, "link": {}})

        result = _run_hook({"cwd": str(project_root)}, env)

        banner = _additional_context(result)
        assert "⚠️ `praxion-sidecar doctor` reports 2 warnings" in banner
        assert "failed" not in banner.split("reports")[1].split("—")[0]


class TestLinkInvokedBeforeStatus:
    def test_link_quiet_runs_before_status_json(self, sidecar_owned, tmp_path):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(sidecar_root, healthy=True, failed_checks=[])
        env, calls_log = _install_stub_cli(
            tmp_path, {"status": {"stdout": response}, "link": {"exit_code": 0}}
        )

        _run_hook({"cwd": str(project_root)}, env)

        calls = _read_calls(calls_log)
        verbs = [call[0] for call in calls if call]
        assert "link" in verbs
        assert "status" in verbs
        assert verbs.index("link") < verbs.index("status"), (
            f"expected self-heal link before status read, got order: {verbs}"
        )


class TestNeverFailsTheSession:
    def test_link_conflict_still_exits_0_and_surfaces_in_banner_and_stderr(
        self, sidecar_owned, tmp_path
    ):
        project_root, sidecar_root = sidecar_owned
        conflict_line = "aborted wt/x: conflict — run praxion-sidecar merge-back --from wt/x"
        response = _status_json_response(sidecar_root, healthy=True, failed_checks=[])
        env, calls_log = _install_stub_cli(
            tmp_path,
            {
                "link": {"exit_code": 1, "stderr": conflict_line},
                "status": {"stdout": response},
            },
        )

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0, (
            "link's embedded converge() aborting a conflict must never fail the session"
        )
        assert _read_calls(calls_log), "link must still have been invoked"
        banner = _additional_context(result)
        assert "wt/x" in banner, f"conflict branch name must be surfaced, got:\n{banner}"
        assert "conflict" in banner.lower(), f"conflict must be surfaced, got:\n{banner}"
        assert result.stderr.strip() != "", "conflict must also be logged to the hook's stderr"


class TestStatusTimeout:
    def test_hanging_status_call_returns_within_the_3s_budget(self, sidecar_owned, tmp_path):
        project_root, sidecar_root = sidecar_owned
        env, _ = _install_stub_cli(
            tmp_path,
            {"link": {}, "status": {"sleep_seconds": 10, "stdout": "{}"}},
        )

        started = time.monotonic()
        result = _run_hook({"cwd": str(project_root)}, env)
        elapsed = time.monotonic() - started

        assert result.returncode == 0
        assert elapsed < 6, f"hook took {elapsed:.1f}s -- status --json must be bounded at ~3s"


class TestUnresolvableCli:
    def test_missing_cli_binary_exits_0_silently(self, sidecar_owned, tmp_path):
        project_root, _sidecar_root = sidecar_owned
        # Deliberately do NOT install a stub: PATH has nothing named
        # praxion-sidecar and CLAUDE_PLUGIN_ROOT points nowhere useful.
        env = {
            "PATH": "/usr/bin:/bin",
            "CLAUDE_PLUGIN_ROOT": str(tmp_path / "nonexistent-plugin-root"),
        }
        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_malformed_status_json_exits_0_silently(self, sidecar_owned, tmp_path):
        project_root, _sidecar_root = sidecar_owned
        env, _ = _install_stub_cli(tmp_path, {"link": {}, "status": {"stdout": "not-json{{{"}})

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestDisableFlag:
    def test_disable_flag_skips_even_with_a_resolvable_cli(self, sidecar_owned, tmp_path):
        project_root, sidecar_root = sidecar_owned
        response = _status_json_response(sidecar_root, healthy=True, failed_checks=[])
        env, calls_log = _install_stub_cli(tmp_path, {"link": {}, "status": {"stdout": response}})
        env[DISABLE_FLAG] = "1"

        result = _run_hook({"cwd": str(project_root)}, env)

        assert result.returncode == 0
        assert result.stdout.strip() == ""
        assert _read_calls(calls_log) == []


class TestLinkedWorktreeComposition:
    def test_sidecar_owned_linked_worktree_checkout_still_renders_the_banner(self, tmp_path):
        """The hook must not gate on being the *main* checkout -- a project
        worktree with its own mount (ARCH_WT_RULING.md's per-checkout shadow
        model) is `SidecarOwned` too, and both SessionStart banners compose
        (INTERFACE_DESIGN.md sec. 6)."""
        worktree_root = tmp_path / "main" / ".claude" / "worktrees" / "auth-flow"
        worktree_root.mkdir(parents=True)
        # Reuse the project-fixture recipe rooted at the worktree path directly --
        # what matters is that _state_repo.resolve_placement(cwd) sees SidecarOwned
        # at a path shaped like a linked worktree, not real `git worktree` plumbing
        # for the *project* repo.
        sidecar_root = worktree_root.parent / "sidecar-for-auth-flow"
        _init_sidecar_repo(sidecar_root)
        _git(worktree_root, "init", "-q")
        _git(worktree_root, "config", "user.email", "p@p.p")
        _git(worktree_root, "config", "user.name", "p")
        # See the sibling `_sidecar_owned_project` comment: origin is set in
        # the manifest below, so the project side needs a matching remote.
        _git(worktree_root, "remote", "add", "origin", "https://github.com/acme/billing")
        _mount_sidecar(sidecar_root, worktree_root)
        _write_manifest(sidecar_root, project_root=worktree_root)
        _link_shadow(worktree_root)

        response = _status_json_response(sidecar_root, healthy=True, failed_checks=[])
        env, _ = _install_stub_cli(tmp_path, {"link": {}, "status": {"stdout": response}})

        result = _run_hook({"cwd": str(worktree_root)}, env)

        assert result.returncode == 0
        banner = _additional_context(result)
        assert HEADING in banner


class TestNotYetLinkedSelfHeal:
    """A session opened in a worktree created moments ago.

    `git worktree add` copies no `.ai-state`, so the checkout resolves to
    `NotYetLinked` -- the state the heal exists to leave. Gating the hook on
    `SidecarOwned` alone made it silent in exactly that case.
    """

    @staticmethod
    def _fresh_worktree(tmp_path: Path) -> tuple[Path, Path, Path]:
        """(project_root, sidecar_root, worktree) -- a real `git worktree add`
        checkout of a SidecarOwned project, with no shadow of its own."""
        project_root, sidecar_root = _sidecar_owned_project(tmp_path)
        _git(project_root, "commit", "-q", "--allow-empty", "-m", "seed project")
        worktree = project_root / "wts" / "wt1"
        _git(project_root, "worktree", "add", "-q", str(worktree), "-b", "feat/wt1")
        return project_root, sidecar_root, worktree

    @staticmethod
    def _link_side_effect(tmp_path: Path, sidecar_root: Path, worktree: Path) -> list[str]:
        """A script standing in for what `praxion-sidecar link` does here:
        materialize the worktree's own mount and its `.ai-state` shadow."""
        script = tmp_path / "stub-link.sh"
        script.write_text(
            f"set -e\n"
            f'git -C "{sidecar_root}" worktree add -q -b wt/feat-wt1 '
            f'"{worktree}/.praxion" main\n'
            f'ln -s .praxion/.ai-state "{worktree}/.ai-state"\n'
        )
        return ["/bin/sh", str(script)]

    def test_fresh_worktree_runs_link_and_renders_the_banner_once_it_takes(self, tmp_path):
        _project_root, sidecar_root, worktree = self._fresh_worktree(tmp_path)
        response = _status_json_response(sidecar_root, healthy=True, failed_checks=[])
        env, calls_log = _install_stub_cli(
            tmp_path,
            {
                "link": {
                    "side_effect_argv": self._link_side_effect(tmp_path, sidecar_root, worktree)
                },
                "status": {"stdout": response},
            },
        )

        result = _run_hook({"cwd": str(worktree)}, env)

        assert result.returncode == 0
        assert ["link", "--quiet"] in _read_calls(calls_log)
        assert HEADING in _additional_context(result)

    def test_fresh_worktree_whose_link_does_not_take_stays_silent(self, tmp_path):
        """The heal is attempted, but the banner describes a mount -- so with
        no mount to describe, the hook reports nothing rather than a fiction."""
        _project_root, sidecar_root, worktree = self._fresh_worktree(tmp_path)
        response = _status_json_response(sidecar_root, healthy=True, failed_checks=[])
        env, calls_log = _install_stub_cli(
            tmp_path, {"link": {"exit_code": 1}, "status": {"stdout": response}}
        )

        result = _run_hook({"cwd": str(worktree)}, env)

        assert result.returncode == 0
        assert ["link", "--quiet"] in _read_calls(calls_log)
        assert result.stdout.strip() == ""
        assert ["status", "--json"] not in _read_calls(calls_log)


class TestHooksRegistration:
    """`hooks/hooks.json` registration for both sidecar hooks (not their
    own runtime behavior -- a static wiring check)."""

    def _load_hooks_json(self) -> dict:
        hooks_json_path = Path(__file__).parent / "hooks.json"
        return json.loads(hooks_json_path.read_text())

    def _commands(self, event: str) -> list[str]:
        data = self._load_hooks_json()["hooks"].get(event) or []
        commands: list[str] = []
        for matcher_group in data:
            for entry in matcher_group.get("hooks", []):
                commands.append(entry.get("command", ""))
        return commands

    def test_inject_sidecar_banner_registered_after_heal_hook_chain_in_session_start(self):
        commands = self._commands("SessionStart")
        heal_idx = next((i for i, cmd in enumerate(commands) if "heal_hook_chain.py" in cmd), None)
        banner_idx = next(
            (i for i, cmd in enumerate(commands) if "inject_sidecar_banner.py" in cmd), None
        )
        assert heal_idx is not None, "heal_hook_chain.py must already be registered (Step P0)"
        assert banner_idx is not None, "inject_sidecar_banner.py must be registered in SessionStart"
        assert banner_idx > heal_idx, "inject_sidecar_banner.py must run after heal_hook_chain.py"

    def test_sidecar_autocommit_registered_in_stop(self):
        commands = self._commands("Stop")
        assert any("sidecar_autocommit.py" in cmd for cmd in commands), (
            "sidecar_autocommit.py must be registered in the Stop event"
        )
