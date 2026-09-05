"""Behavioral tests for `_sidecar_commit.py` -- the per-mount commit lock
and the pathspec-scoped autocommit surface it serializes.

`_sidecar_commit.py` does not exist yet (concurrent BDD/TDD with its
implementation) -- this is the RED skeleton, confirmed to fail on
`ModuleNotFoundError` before the module lands. Every fixture below drives
*real* `git worktree` / `git commit` commands under `tmp_path`, built
directly with plain git plumbing rather than through `_sidecar_mount`
(concurrently in flight elsewhere) -- the one exception is the single
`converge()` integration test at the bottom, guarded by
`pytest.importorskip("_sidecar_mount")`.

Lock-contention tests hold the real per-mount lock in a background thread
(same-process, so the OS-level `fcntl.flock` genuinely contends -- `flock`
is scoped to the open file description, not the process, so two separate
`open()` calls on the same lock path block each other even from the same
process) and synchronize via `threading.Event`, never `time.sleep()`. The
one exception is the stale-holder test, which needs an actually-dead
process: it forks a child that acquires the lock and is SIGKILLed while
holding it, so no `finally` runs and the OS releases the flock on fd-close
while the pid/timestamp record `mount_lock` wrote while held survives on
disk -- exactly what a crashed committer leaves behind, with no lock-file
format hand-crafted by the test.
"""

from __future__ import annotations

import dataclasses
import multiprocessing
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import _sidecar_commit
import pytest


class _CountingLock:
    """Test double proving `converge()` acquires its lock exactly once per
    run, not once per merged branch. Never touches real `fcntl` state --
    `_sidecar_mount`'s own suite already covers real-lock behaviour via its
    `_NullLock`; this double isolates the *counting* claim from locking
    mechanics.
    """

    def __init__(self) -> None:
        self.enter_count = 0

    def __enter__(self) -> _CountingLock:
        self.enter_count += 1
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


# --- git plumbing ------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _configure_identity(repo: Path) -> None:
    _git_ok(repo, "config", "user.email", "test@example.com")
    _git_ok(repo, "config", "user.name", "Test")


def _commit_all(repo: Path, message: str) -> None:
    _git_ok(repo, "add", "-A")
    _git_ok(repo, "commit", "-q", "-m", message)


def _worktree_git_dir(checkout: Path) -> Path:
    """Resolve a worktree's real git-dir (`.git/worktrees/<name>`) from its
    `.git` pointer file -- the exact directory the per-mount lock hangs
    off of.
    """
    result = _git_ok(checkout, "rev-parse", "--git-dir")
    git_dir = Path(result.stdout.strip())
    return git_dir if git_dir.is_absolute() else (checkout / git_dir).resolve()


# --- fixture builders --------------------------------------------------------


def _init_sidecar(sidecar_root: Path) -> Path:
    """A minimal sidecar repo: seeded, committed on `main`, then detached --
    mirroring `praxion-sidecar init`'s sequence so `main` stays free for a
    mount to check out.
    """
    sidecar_root.mkdir(parents=True, exist_ok=True)
    _git_ok(sidecar_root, "init", "-q", "-b", "main")
    _configure_identity(sidecar_root)
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "seed.md").write_text("seed\n")
    _commit_all(sidecar_root, "seed sidecar state")
    _git_ok(sidecar_root, "checkout", "-q", "--detach")
    return sidecar_root


def _mount(
    sidecar_root: Path, checkout_dir: Path, branch: str, *, new: bool, base: str = "main"
) -> Path:
    """Attach a real `git worktree` at `<checkout_dir>/.praxion-state`, built
    directly with `git worktree add` -- no dependency on `_sidecar_mount`,
    which is concurrently in flight elsewhere. `new=False` checks out an
    existing branch (the main-checkout shape); `new=True` creates one from
    `base` (the linked-worktree shape) -- both are real sidecar worktrees,
    each with its own `.git/worktrees/<name>/` as the lock derivation expects.
    """
    mount_dir = checkout_dir / ".praxion-state"
    checkout_dir.mkdir(parents=True, exist_ok=True)
    if new:
        _git_ok(sidecar_root, "worktree", "add", "-q", str(mount_dir), "-b", branch, base)
    else:
        _git_ok(sidecar_root, "worktree", "add", "-q", str(mount_dir), branch)
    return mount_dir


def _hold_lock(mount: Path, acquired: threading.Event, release: threading.Event) -> None:
    """Background-thread body: acquire the real per-mount lock, signal
    acquisition, then block until told to release -- the synchronization
    primitive every contention test below uses instead of `sleep()`.
    """
    with _sidecar_commit.mount_lock(mount, timeout_seconds=10):
        acquired.set()
        release.wait(timeout=10)


def _acquire_and_freeze(mount: Path, acquired) -> None:
    """Child-process body for the stale-lock scenario: acquire the real
    lock, signal acquisition, then wait to be killed. SIGKILL bypasses the
    `with` block's `finally`, so the flock releases at the OS level (fd
    close) while the pid/timestamp record written on acquisition survives.
    """
    with _sidecar_commit.mount_lock(mount, timeout_seconds=10):
        acquired.set()
        signal.pause()


# --- lock-path derivation ---------------------------------------------


def test_lock_path_lands_under_each_mounts_own_worktree_git_dir(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    main_mount = _mount(sidecar_root, tmp_path / "main-checkout", "main", new=False)
    wt_mount = _mount(sidecar_root, tmp_path / "wt-checkout", "wt/x", new=True)

    main_lock = _sidecar_commit.lock_path_for(main_mount)
    wt_lock = _sidecar_commit.lock_path_for(wt_mount)

    assert main_lock == _worktree_git_dir(main_mount) / "praxion-sidecar-commit.lock"
    assert wt_lock == _worktree_git_dir(wt_mount) / "praxion-sidecar-commit.lock"
    assert main_lock != wt_lock, "two distinct mounts must not share one lock path"


# --- read_lock_state (SidecarCommit) -----------------------------------------


def test_read_lock_state_reports_idle_when_never_locked(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/idle", new=True)

    assert _sidecar_commit.read_lock_state(mount) == _sidecar_commit.Idle()


def test_read_lock_state_returns_idle_after_a_clean_release_not_a_stale_ghost(
    tmp_path: Path,
) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/idle-after", new=True)

    with _sidecar_commit.mount_lock(mount, timeout_seconds=5):
        pass

    assert _sidecar_commit.read_lock_state(mount) == _sidecar_commit.Idle()


def test_read_lock_state_reports_committing_with_the_live_holder_pid(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/committing", new=True)
    acquired = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_lock, args=(mount, acquired, release))
    holder.start()
    assert acquired.wait(timeout=5), "holder thread never acquired the lock"

    state = _sidecar_commit.read_lock_state(mount)

    release.set()
    holder.join(timeout=5)

    assert isinstance(state, _sidecar_commit.Committing)
    assert state.holder_pid == os.getpid()


def test_read_lock_state_reports_a_dead_holder_as_stale_not_committing(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/stale", new=True)
    ctx = multiprocessing.get_context("fork")
    acquired = ctx.Event()
    child = ctx.Process(target=_acquire_and_freeze, args=(mount, acquired))
    child.start()
    assert acquired.wait(timeout=5), "child never acquired the lock"
    child.kill()  # SIGKILL -- no cleanup runs; simulates a crashed committer
    child.join(timeout=5)

    state = _sidecar_commit.read_lock_state(mount)

    assert isinstance(state, _sidecar_commit.StaleLock)
    assert state.holder_pid == child.pid


def test_committing_state_is_frozen_against_mutation() -> None:
    state = _sidecar_commit.Committing(holder_pid=1234, since="2026-01-01T00:00:00Z")

    with pytest.raises(dataclasses.FrozenInstanceError):
        state.holder_pid = 9999  # type: ignore[misc]


# --- mount_lock primitive -----------------------------------------------------


def test_mount_lock_releases_on_exception_inside_the_context(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/exc", new=True)

    with pytest.raises(RuntimeError, match="boom"):
        with _sidecar_commit.mount_lock(mount, timeout_seconds=5):
            raise RuntimeError("boom")

    # A second acquire on a short timeout only succeeds if the first
    # release actually happened -- proving `finally`-based release, not
    # release-on-success-only.
    with _sidecar_commit.mount_lock(mount, timeout_seconds=0.5):
        pass


def test_mount_lock_raises_lock_timeout_when_contended_past_the_bound(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/timeout", new=True)
    acquired = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_lock, args=(mount, acquired, release))
    holder.start()
    assert acquired.wait(timeout=5), "holder thread never acquired the lock"

    with pytest.raises(_sidecar_commit.LockTimeout):
        with _sidecar_commit.mount_lock(mount, timeout_seconds=0.2):
            pass

    release.set()
    holder.join(timeout=5)


# --- per-mount contention (the shrunk-race claim) -----------------------------


def test_commits_against_different_mounts_never_contend(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount_a = _mount(sidecar_root, tmp_path / "checkout-a", "wt/a", new=True)
    mount_b = _mount(sidecar_root, tmp_path / "checkout-b", "wt/b", new=True)
    acquired = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_lock, args=(mount_a, acquired, release))
    holder.start()
    assert acquired.wait(timeout=5), "holder thread never acquired mount A's lock"

    (mount_b / "b.txt").write_text("b\n")
    started = time.monotonic()
    result = _sidecar_commit.commit_paths(mount_b, ["b.txt"], "commit b")
    elapsed = time.monotonic() - started

    release.set()
    holder.join(timeout=5)

    assert result.committed is True
    assert elapsed < 2.0, "commit against an unlocked mount waited as if contended"


def test_committing_in_the_main_checkout_mount_succeeds_while_a_worktree_mount_is_locked(
    tmp_path: Path,
) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    main_mount = _mount(sidecar_root, tmp_path / "main-checkout", "main", new=False)
    wt_mount = _mount(sidecar_root, tmp_path / "wt-checkout", "wt/y", new=True)
    acquired = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_lock, args=(wt_mount, acquired, release))
    holder.start()
    assert acquired.wait(timeout=5), "holder thread never acquired the worktree mount's lock"

    (main_mount / ".ai-state" / "seed.md").write_text("main-change\n")
    result = _sidecar_commit.commit_paths(main_mount, [".ai-state/seed.md"], "commit in main")

    release.set()
    holder.join(timeout=5)

    assert result.committed is True


def test_commits_against_the_same_mount_serialize(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/same", new=True)
    acquired = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_lock, args=(mount, acquired, release))
    holder.start()
    assert acquired.wait(timeout=5), "holder thread never acquired the lock"

    (mount / "c.txt").write_text("c\n")
    deferred = _sidecar_commit.commit_paths(
        mount, ["c.txt"], "commit c", lock=_sidecar_commit.mount_lock(mount, timeout_seconds=0.3)
    )

    release.set()
    holder.join(timeout=5)

    assert isinstance(deferred, _sidecar_commit.CommitDeferred)
    committed = _sidecar_commit.commit_paths(mount, ["c.txt"], "commit c retry")
    assert committed.committed is True


# --- pathspec-scoped staging ---------------------------------------------------


def test_commit_paths_stages_only_the_given_pathspec(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/scoped", new=True)
    (mount / "a.txt").write_text("a\n")
    (mount / "b.txt").write_text("b\n")

    result = _sidecar_commit.commit_paths(mount, ["a.txt"], "commit only a")

    assert result.committed is True
    assert result.staged == ["a.txt"]
    status = _git_ok(mount, "status", "--porcelain").stdout
    assert "a.txt" not in status
    assert "?? b.txt" in status


def test_module_never_stages_with_add_dash_a() -> None:
    source = (Path(__file__).resolve().parent / "_sidecar_commit.py").read_text()

    assert "-A" not in source, "pathspec-scoped staging must never fall back to `git add -A`"


def test_commit_paths_refuses_an_empty_paths_list(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/empty", new=True)

    with pytest.raises(ValueError, match="paths"):
        _sidecar_commit.commit_paths(mount, [], "no paths")


def test_commit_paths_is_a_clean_noop_when_nothing_changed(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/noop", new=True)
    log_before = _git_ok(mount, "log", "--oneline").stdout

    result = _sidecar_commit.commit_paths(mount, [".ai-state/seed.md"], "no changes here")

    assert result.committed is False
    assert result.sha is None
    assert _git_ok(mount, "log", "--oneline").stdout == log_before


def test_residue_paths_lists_every_dirty_path_from_git_status(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/residue", new=True)
    (mount / "new.txt").write_text("new\n")
    (mount / ".ai-state" / "seed.md").write_text("changed\n")

    paths = _sidecar_commit.residue_paths(mount)

    assert set(paths) == {"new.txt", ".ai-state/seed.md"}


def test_residue_paths_takes_the_new_path_of_a_staged_rename(tmp_path: Path) -> None:
    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    mount = _mount(sidecar_root, tmp_path / "checkout", "wt/rename", new=True)
    _git_ok(mount, "mv", ".ai-state/seed.md", ".ai-state/renamed.md")

    assert _sidecar_commit.residue_paths(mount) == [".ai-state/renamed.md"]


def test_residue_paths_unquotes_a_path_git_had_to_quote() -> None:
    assert _sidecar_commit._porcelain_path('?? "my file.txt"') == "my file.txt"


def test_residue_paths_refuses_to_report_a_failed_status_as_clean(tmp_path: Path) -> None:
    """A mount whose `git status` fails must not read back as "nothing dirty" --
    the Stop-hook sweep would log a successful no-op over a mount it never read.
    """
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    with pytest.raises(_sidecar_commit.GitCommandError, match="status"):
        _sidecar_commit.residue_paths(not_a_repo)


# --- converge() integration (guarded, cross-module) ---------------------------


def test_converge_acquires_the_target_lock_exactly_once_for_three_merges(tmp_path: Path) -> None:
    """`_sidecar_convergence.converge()` may merge several eligible branches in
    one run; `ARCH_WT_RULING.md` sec. 13.4 requires it take the target
    mount's commit lock exactly once for the whole run, never once per
    branch. Only `_sidecar_commit` supplies the real lock class this test
    proves against -- the sole integration point between the two modules in
    this suite.
    """
    sidecar_mount = pytest.importorskip("_sidecar_mount")
    sidecar_convergence = pytest.importorskip("_sidecar_convergence")

    sidecar_root = _init_sidecar(tmp_path / "sidecar")
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_ok(project_root, "init", "-q", "-b", "main")
    _configure_identity(project_root)
    exclude = project_root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(f"/{sidecar_mount.MOUNT_DIRNAME}/\n/wts/\n")
    (project_root / "app.py").write_text("code\n")
    _commit_all(project_root, "init")
    sidecar_mount.create_mount(sidecar_root, project_root, "main", project_branch="main")

    for name in ("p", "q", "r"):
        project_branch = f"feat/{name}"
        sidecar_branch = f"wt/{name}"
        checkout = project_root / "wts" / name
        _git_ok(project_root, "worktree", "add", "-q", str(checkout), "-b", project_branch, "main")
        (checkout / f"{name}.py").write_text(f"{name} feature\n")
        _commit_all(checkout, f"{name} feature work")
        mount = checkout / sidecar_mount.MOUNT_DIRNAME
        sidecar_mount.create_mount(
            sidecar_root,
            checkout,
            sidecar_branch,
            project_branch=project_branch,
            base_branch="main",
        )
        # One state file per branch: three branches rewriting the same
        # `seed.md` from a common base is a genuine content conflict, which
        # an automatic converge run correctly aborts -- leaving only the
        # first branch merged and this test measuring conflict handling
        # rather than the once-per-run lock claim it is about.
        (mount / ".ai-state" / f"{name}.md").write_text(f"{name}-change\n")
        _commit_all(mount, f"{name} state")
        _git_ok(project_root, "merge", "-q", "--no-ff", "--no-edit", project_branch)

    counting_lock = _CountingLock()
    result = sidecar_convergence.converge(
        sidecar_root, project_root, project_root, lock=counting_lock
    )

    assert {"wt/p", "wt/q", "wt/r"} <= set(result.merged)
    assert counting_lock.enter_count == 1
