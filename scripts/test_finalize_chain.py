"""Gate behavior for the finalize hook chain (`scripts/finalize_chain.sh`).

Cites: scripts/finalize_chain.sh — the bash library that decides which finalizers
fire on a given repo state. These tests pin the *decoupling* contract: ADR-draft
promotion is gated on drafts being present, but tech-debt ledger reconciliation
runs on any on-main commit (its byte-equivalent no-op contract makes that free).
Bundling the tech-debt finalizer behind the drafts gate previously stranded
tech-debt resolutions committed without a concurrent ADR draft.

The bash gate predicates have no other test coverage; these exercise the
state-driven entry point (shared by post-commit and post-checkout) by sourcing
the library and stubbing the script-runner plus the repo-state predicates.
"""

from __future__ import annotations

import dataclasses
import os
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

import _sidecar_mount

CHAIN_PATH = Path(__file__).parent / "finalize_chain.sh"


def _run_state_driven(
    *,
    on_main: bool,
    drafts_present: bool,
    repo_root: str = "/fake/repo",
) -> list[str]:
    """Source the chain, stub the predicates, and return finalizers that fired.

    Stubs ``_finalize_chain_run_script`` to echo each finalizer's label instead
    of invoking the real python scripts, so the test observes the gate decision
    without side effects.

    ``repo_root`` controls what ``_finalize_chain_repo_root`` returns, which in
    turn determines whether the doc-manifest existence gate fires.  The default
    ``/fake/repo`` has no manifest, so the gate keeps ``build_doc_manifest`` out
    of the existing four tests unchanged.
    """

    on_main_rc = 0 if on_main else 1
    drafts_rc = 0 if drafts_present else 1
    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        _finalize_chain_repo_root() {{ echo {repo_root!r}; }}
        _finalize_chain_on_main() {{ return {on_main_rc}; }}
        _finalize_chain_drafts_present() {{ return {drafts_rc}; }}
        _finalize_chain_state_driven
    """
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.split(":", 1)[1] for line in result.stdout.splitlines() if line.startswith("RAN:")]


def test_tech_debt_finalizer_runs_on_main_without_drafts() -> None:
    """The fix: a resolution committed to main with no ADR draft still finalizes."""
    fired = _run_state_driven(on_main=True, drafts_present=False)
    assert "finalize_tech_debt_ledger" in fired


def test_adr_finalizer_skipped_on_main_without_drafts() -> None:
    """ADR promotion keeps its genuine trigger — it does not fire without drafts."""
    fired = _run_state_driven(on_main=True, drafts_present=False)
    assert "finalize_adrs" not in fired


def test_both_finalizers_run_on_main_with_drafts() -> None:
    """With drafts present, both finalizers fire (ADR before ledger)."""
    fired = _run_state_driven(on_main=True, drafts_present=True)
    assert fired == ["finalize_adrs", "finalize_tech_debt_ledger"]


def test_nothing_runs_off_main_even_with_drafts() -> None:
    """Off main, the state-driven gate is a no-op regardless of drafts."""
    assert _run_state_driven(on_main=False, drafts_present=False) == []
    assert _run_state_driven(on_main=False, drafts_present=True) == []


def test_build_doc_manifest_fires_on_main_when_manifest_exists(tmp_path: Path) -> None:
    """build_doc_manifest fires on main and lands after finalize_tech_debt_ledger.

    The manifest must be present for the existence gate to open, and the step
    must come after the ledger finalizer so the committed index reflects the
    post-finalize dec-NNN renames and TECH_DEBT_RESOLVED migrations.
    """
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    (ai_state / "doc_manifest.yaml").write_text("generated_at: 2025-01-01\n")

    fired = _run_state_driven(on_main=True, drafts_present=False, repo_root=str(tmp_path))

    assert "build_doc_manifest" in fired
    assert fired.index("build_doc_manifest") > fired.index("finalize_tech_debt_ledger")


def test_build_doc_manifest_skipped_when_manifest_absent(tmp_path: Path) -> None:
    """Existence gate: build_doc_manifest is not invoked when doc_manifest.yaml is absent.

    Projects that never opted into the dashboard manifest must not gain a
    committed doc_manifest.yaml on the first on-main merge (pre-mortem #1).
    """
    # tmp_path has no .ai-state/doc_manifest.yaml — existence gate keeps it out
    fired = _run_state_driven(on_main=True, drafts_present=False, repo_root=str(tmp_path))

    assert "build_doc_manifest" not in fired


def test_all_three_finalizers_fire_on_main_with_drafts_and_manifest(tmp_path: Path) -> None:
    """With drafts + manifest present all three steps fire in order: ADR → ledger → manifest."""
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    (ai_state / "doc_manifest.yaml").write_text("generated_at: 2025-01-01\n")

    fired = _run_state_driven(on_main=True, drafts_present=True, repo_root=str(tmp_path))

    assert fired == ["finalize_adrs", "finalize_tech_debt_ledger", "build_doc_manifest"]


def _run_on_main_real(
    *,
    repo_root: Path,
    finalize_dir: Path,
    strict: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Source the chain and run `_finalize_chain_run_on_main` end-to-end.

    Overrides ``FINALIZE_CHAIN_DIR`` to point at a fake finalizer directory so
    the REAL (non-stubbed) `_finalize_chain_run_script` executes an actual
    python script — this proves exit-code propagation rather than assuming it
    from a stubbed return value.
    """
    strict_line = "export FINALIZE_CHAIN_STRICT=1" if strict else ""
    snippet = f"""
        source {CHAIN_PATH}
        FINALIZE_CHAIN_DIR={str(finalize_dir)!r}
        {strict_line}
        _finalize_chain_run_on_main {str(repo_root)!r}
    """
    return subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)


def test_run_on_main_swallows_failing_finalizer_by_default(tmp_path: Path) -> None:
    """Characterization: non-strict on-main composition always exits 0, even when
    a finalizer fails. Pins the CURRENT hook semantics before the strict-mode
    refactor — a failing finalizer warns but never aborts the (already-completed)
    git operation.
    """
    finalize_dir = tmp_path / "scripts"
    finalize_dir.mkdir()
    (finalize_dir / "finalize_tech_debt_ledger.py").write_text("import sys\nsys.exit(1)\n")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = _run_on_main_real(repo_root=repo_root, finalize_dir=finalize_dir)

    assert result.returncode == 0
    assert "warned (non-blocking)" in result.stdout


def test_strict_mode_propagates_failing_finalizer_exit(tmp_path: Path) -> None:
    """New behavior: FINALIZE_CHAIN_STRICT=1 makes a failing finalizer abort loudly
    instead of warning-and-continuing — the server-side (CI) safety contract.
    """
    finalize_dir = tmp_path / "scripts"
    finalize_dir.mkdir()
    (finalize_dir / "finalize_tech_debt_ledger.py").write_text("import sys\nsys.exit(1)\n")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = _run_on_main_real(repo_root=repo_root, finalize_dir=finalize_dir, strict=True)

    assert result.returncode != 0


def test_finalize_chain_run_on_main_runs_full_composition_in_order(tmp_path: Path) -> None:
    """New public entry point: full composition fires in fixed order adr -> ledger -> manifest."""
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    (ai_state / "doc_manifest.yaml").write_text("generated_at: 2025-01-01\n")
    drafts_dir = ai_state / "decisions" / "drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "20260101-0000-fake.md").write_text(
        "---\nid: dec-draft-aaaaaaaa\n---\n"  # id-citation-discipline:ignore
    )

    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        finalize_chain_run_on_main {str(tmp_path)!r}
    """
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=True)
    fired = [
        line.split(":", 1)[1] for line in result.stdout.splitlines() if line.startswith("RAN:")
    ]

    assert fired == ["finalize_adrs", "finalize_tech_debt_ledger", "build_doc_manifest"]


def test_finalize_chain_run_on_main_resolves_repo_root_when_omitted(tmp_path: Path) -> None:
    """When called with no argument, repo_root is resolved via `_finalize_chain_repo_root`."""
    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        _finalize_chain_repo_root() {{ echo {str(tmp_path)!r}; }}
        finalize_chain_run_on_main
    """
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=True)
    fired = [
        line.split(":", 1)[1] for line in result.stdout.splitlines() if line.startswith("RAN:")
    ]

    assert fired == ["finalize_tech_debt_ledger"]


# ---------------------------------------------------------------------------
# Interpreter resolution
#
# A bare `python3` is not necessarily an interpreter holding the project's
# declared dependencies. When it is not, any chain script needing a third-party
# package fails, the chain degrades to a non-blocking warning, and the state
# that script maintains drifts silently.
# ---------------------------------------------------------------------------


def _resolve_python(*, repo_root: str, env: dict[str, str] | None = None) -> str:
    """Source the chain and return the interpreter it would use."""
    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_repo_root() {{ echo {repo_root!r}; }}
        _finalize_chain_python
    """
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **(env or {})},
    )
    return result.stdout.strip()


def _make_venv(root: Path) -> Path:
    """Create an executable stub at <root>/.venv/bin/python."""
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    return python


def test_project_venv_is_preferred_over_ambient_python(tmp_path: Path) -> None:
    """The regression: the ambient python3 lacked a declared dependency."""
    python = _make_venv(tmp_path)
    assert _resolve_python(repo_root=str(tmp_path)) == str(python)


def test_explicit_override_outranks_the_project_venv(tmp_path: Path) -> None:
    _make_venv(tmp_path)
    override = tmp_path / "override-python"
    override.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    override.chmod(0o755)
    resolved = _resolve_python(repo_root=str(tmp_path), env={"PRAXION_PYTHON": str(override)})
    assert resolved == str(override)


def test_falls_back_to_ambient_python_without_a_venv(tmp_path: Path) -> None:
    """Consumer projects have no venv; stdlib-only finalizers must still run."""
    resolved = _resolve_python(repo_root=str(tmp_path))
    assert resolved.endswith("python3")


def test_unusable_override_falls_through_rather_than_breaking(tmp_path: Path) -> None:
    """A stale PRAXION_PYTHON must not strand the chain."""
    python = _make_venv(tmp_path)
    resolved = _resolve_python(
        repo_root=str(tmp_path), env={"PRAXION_PYTHON": str(tmp_path / "gone")}
    )
    assert resolved == str(python)


# ---------------------------------------------------------------------------
# Block D self-repair backstop
# ---------------------------------------------------------------------------

# Minimal structurally-valid broken Block D: both grep markers the chain guard
# requires (check_aac_golden_rule + the data.items() literal unique to the
# pre-fix resolution) and the region shape reconcile_aac_surfaces.py locates
# (banner -> header -> outer STAGED_AAC if -> column-0 fi).
_BROKEN_BLOCK_D = """# ---------------------------------------------------------------------------
# Block D: AaC golden-rule gate
# ---------------------------------------------------------------------------

STAGED_AAC="$(git diff --cached --name-only | grep -E '^docs/' || true)"

if [ -n "$STAGED_AAC" ]; then
    PLUGIN_ROOT="$(python3 -c "
for _name, entry in data.items():
    path = entry if isinstance(entry, str) else entry.get('path', '')
" 2>/dev/null || true)"
    if [ -z "$PLUGIN_ROOT" ]; then
        echo "info: praxion plugin not found in installed_plugins.json — skipping Block D golden-rule gate"
    else
        python3 "$PLUGIN_ROOT/scripts/check_aac_golden_rule.py" --mode=gate
    fi
fi
"""


def _make_repo_with_hook(tmp_path: Path, hook_body: str) -> Path:
    repo = tmp_path / "proj"
    (repo / ".git" / "hooks").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/usr/bin/env bash\n" + hook_body)
    hook.chmod(0o755)
    return repo


def _run_post_commit_for_real(repo: Path) -> subprocess.CompletedProcess:
    """Source the chain unstubbed and fire the post-commit entry from inside
    the fixture repo -- the real backstop path, real python, real reconciler."""
    snippet = f"""
        cd {str(repo)!r}
        source {str(CHAIN_PATH)!r}
        finalize_chain_post_commit
    """
    return subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)


def test_backstop_repairs_broken_block_d_end_to_end(tmp_path: Path) -> None:
    repo = _make_repo_with_hook(tmp_path, _BROKEN_BLOCK_D)
    hook = repo / ".git" / "hooks" / "pre-commit"

    result = _run_post_commit_for_real(repo)

    assert result.returncode == 0, result.stderr
    assert "repairing from the shipped template" in result.stdout
    text = hook.read_text()
    assert "data.items()" not in text
    assert ".plugins[$k][0].installPath" in text


def test_backstop_is_a_noop_on_a_healthy_hook(tmp_path: Path) -> None:
    repo = _make_repo_with_hook(tmp_path, "echo healthy-hook\n")
    hook = repo / ".git" / "hooks" / "pre-commit"
    before = hook.read_text()

    result = _run_post_commit_for_real(repo)

    assert result.returncode == 0, result.stderr
    assert "repairing" not in result.stdout
    assert hook.read_text() == before


def test_backstop_fires_even_off_main(tmp_path: Path) -> None:
    """Hook repair is branch-independent: it must run before the on-main gate
    that keeps the finalizers themselves quiet off main."""
    repo = _make_repo_with_hook(tmp_path, _BROKEN_BLOCK_D)
    snippet = f"""
        source {str(CHAIN_PATH)!r}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        _finalize_chain_repo_root() {{ echo {str(repo)!r}; }}
        _finalize_chain_on_main() {{ return 1; }}
        _finalize_chain_state_driven
    """
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "RAN:block-d repair" in result.stdout
    assert "RAN:finalize_adrs" not in result.stdout
    assert "RAN:finalize_tech_debt_ledger" not in result.stdout


def test_backstop_repair_is_idempotent(tmp_path: Path) -> None:
    repo = _make_repo_with_hook(tmp_path, _BROKEN_BLOCK_D)

    first = _run_post_commit_for_real(repo)
    second = _run_post_commit_for_real(repo)

    assert "repairing from the shipped template" in first.stdout
    assert "repairing" not in second.stdout


# ---------------------------------------------------------------------------
# SidecarOwned routing
#
# Under sidecar placement `.ai-state/` is a relative symlink into a state
# mount (a real `git worktree` of a separate sidecar repository) -- the
# project repository no longer owns the directory the chain's finalizers
# read and write. These tests pin the routing contract: the two project-side
# reconcilers report why they no-op instead of silently doing nothing, the
# on-main composition mutates the MOUNT and gets exactly one commit, a
# linked worktree materializes its own mount with no manual step, and
# (channel 1) automatic merge-back convergence runs before draft promotion
# so a plain `git merge` or a GitHub-squash-merge promotes a worktree's
# drafts in the same finalize run.
#
# `_state_repo.py` exposes only a library API today (no CLI), and
# `praxion-sidecar merge-back` does not exist yet -- these tests drive the
# CHAIN's observable behaviour against a real, on-disk SidecarOwned fixture
# (real git worktrees, a real manifest, a real shadow symlink) rather than
# any particular resolution mechanism, so they stay valid however placement
# detection gets wired. Expected RED today; GREEN once this file's paired
# implementer step and the `merge-back --auto` verb both land.
# ---------------------------------------------------------------------------

_REPO_SCRIPTS_DIR = Path(__file__).resolve().parent
_ORIGIN_URL = "https://example.invalid/acme/project.git"
_CORRECTED_REASON_MARKERS = ("does not own", ".ai-state", "merge-back")
_SUPERSEDED_REASON_MARKER = "shared live tree"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _configure_identity_sc(repo: Path) -> None:
    _git_ok(repo, "config", "user.email", "test@example.com")
    _git_ok(repo, "config", "user.name", "Test")


def _commit_all(repo: Path, message: str) -> None:
    _git_ok(repo, "add", "-A")
    _git_ok(
        repo,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-q",
        "-m",
        message,
    )


def _init_sidecar_repo(sidecar_root: Path) -> None:
    """A sidecar repo seeded with the ADR-drafts skeleton, committed on
    `main`, then detached -- mirrors `praxion-sidecar init`'s own sequence
    (`main` must stay free for the project's own mount to check out)."""
    sidecar_root.mkdir(parents=True)
    _git_ok(sidecar_root, "init", "-q", "-b", "main")
    _configure_identity_sc(sidecar_root)
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("seed\n")
    _sidecar_mount.seed_skeleton(sidecar_root, ("decisions/drafts",))
    _commit_all(sidecar_root, "seed sidecar state")
    _git_ok(sidecar_root, "checkout", "-q", "--detach")


def _init_project_repo(project_root: Path) -> None:
    """A minimal project repo, with the mount/worktree exclude block a real
    managed project carries and a `remote.origin.url` the manifest's
    `origin:` is written to match."""
    project_root.mkdir(parents=True)
    _git_ok(project_root, "init", "-q", "-b", "main")
    _configure_identity_sc(project_root)
    exclude = project_root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(
        f"/{_sidecar_mount.MOUNT_DIRNAME}/\n/wts/\n/.claude/worktrees/\n"
        "/.ai-state\nCLAUDE.local.md\n/.claude/settings.local.json\n"
    )
    _git_ok(project_root, "remote", "add", "origin", _ORIGIN_URL)
    (project_root / "app.py").write_text("code\n")
    _commit_all(project_root, "init")


def _write_manifest(sidecar_root: Path, *, project_root: Path) -> None:
    """Schema-1 manifest, complete per DS-2's smart constructor: `paths:`
    declares the three shadow slots `link` actually creates (an incomplete
    `paths:` refuses at `autocommit`/slot lookup, per
    `_sidecar_manifest.load_manifest`'s closed-enum validation)."""
    manifest = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest.write_text(
        "schema: 1\n"
        "project:\n"
        f'  origin: "{_ORIGIN_URL}"\n'
        '  id: "local--finalizechain"\n'
        f'  roots: ["{project_root.resolve()}"]\n'
        "paths:\n"
        "  .ai-state:\n"
        "    intent: shadow\n"
        "    kind: dir\n"
        "  CLAUDE.local.md:\n"
        "    intent: shadow\n"
        "    kind: file\n"
        "  .claude/settings.local.json:\n"
        "    intent: shadow\n"
        "    kind: file\n"
        "excludes: []\n"
        "autocommit: on-finalize-and-stop\n"
        "remote: null\n"
    )


def _link_shadow(project_root: Path, mount_dir: Path) -> None:
    link = project_root / ".ai-state"
    link.symlink_to(Path(mount_dir.name) / ".ai-state", target_is_directory=True)


@dataclasses.dataclass(frozen=True)
class _SidecarOwnedProject:
    sidecar_root: Path
    project_root: Path
    mount_dir: Path


def _build_sidecar_owned_project(tmp_path: Path, *, name: str = "proj") -> _SidecarOwnedProject:
    """Sidecar + project + main mount + manifest + shadow -- a fully wired
    `SidecarOwned` fixture, built entirely from raw git (mirrors
    `scripts/test_sidecar_mount.py`; never depends on `praxion-sidecar init`,
    so this suite's RED/GREEN is independent of that verb's own landing)."""
    sidecar_root = tmp_path / f"{name}-sidecar"
    project_root = tmp_path / f"{name}-project"
    _init_sidecar_repo(sidecar_root)
    _init_project_repo(project_root)
    _sidecar_mount.create_mount(sidecar_root, project_root, "main", project_branch="main")
    mount_dir = project_root / _sidecar_mount.MOUNT_DIRNAME
    _write_manifest(sidecar_root, project_root=project_root)
    _link_shadow(project_root, mount_dir)
    return _SidecarOwnedProject(
        sidecar_root=sidecar_root, project_root=project_root, mount_dir=mount_dir
    )


def _add_project_worktree(project_root: Path, name: str, project_branch: str) -> Path:
    checkout = project_root / "wts" / name
    _git_ok(project_root, "worktree", "add", "-q", str(checkout), "-b", project_branch, "main")
    # Real divergence on the PROJECT side: without a commit of its own the
    # branch is trivially an ancestor of `main` and every eligibility /
    # conflict assertion below passes or fails vacuously.
    (checkout / f"{name}.py").write_text(f"{name} feature\n")
    _commit_all(checkout, f"{name} feature work")
    return checkout


def _mount_worktree(
    sidecar_root: Path, checkout: Path, sidecar_branch: str, *, project_branch: str
) -> Path:
    _sidecar_mount.create_mount(
        sidecar_root, checkout, sidecar_branch, project_branch=project_branch, base_branch="main"
    )
    return checkout / _sidecar_mount.MOUNT_DIRNAME


def _write_draft(mount_dir: Path, *, slug: str = "test-decision") -> Path:
    drafts_dir = mount_dir / ".ai-state" / "decisions" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path = drafts_dir / f"20260101-0000-tester-main-{slug}.md"
    path.write_text(
        "---\n"
        "id: dec-draft-abc12345\n"  # id-citation-discipline:ignore
        "title: Test Draft\n"
        "status: proposed\n"
        "category: implementation\n"
        "date: 2026-01-01\n"
        "summary: Test draft for finalize-chain sidecar routing.\n"
        "tags: [test]\n"
        "made_by: agent\n"
        "branch: main\n"
        "---\n\n## Context\n\nTest.\n"
    )
    _commit_all(mount_dir, "add draft")
    return path


def _make_fake_plugin(plugin_dir: Path, *, sidecar_call_log: Path | None = None) -> Path:
    """A fake plugin root: `scripts/` holds real symlinks to every sibling
    script the finalize chain and its composed finalizers call or import,
    mirroring the symlinked-plugin-cache layout the real hooks run under.

    `sidecar_call_log`, when given, replaces the `praxion-sidecar` symlink
    with a recording shim that appends its argv to the log file and exits 0
    -- used to observe invocations (a commit call; the absence of any call)
    without depending on verbs not yet landed (`merge-back`). Returns the
    fake plugin's `scripts/` directory.
    """
    scripts_dir = plugin_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    for path in _REPO_SCRIPTS_DIR.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        (scripts_dir / path.name).symlink_to(path)
    sidecar_path = scripts_dir / "praxion-sidecar"
    if sidecar_call_log is not None:
        sidecar_path.write_text(
            f'#!/usr/bin/env bash\necho "CALL:$*" >> {shlex.quote(str(sidecar_call_log))}\nexit 0\n'
        )
        sidecar_path.chmod(0o755)
    else:
        sidecar_path.symlink_to(_REPO_SCRIPTS_DIR / "praxion-sidecar")
    return scripts_dir


def _run_chain(
    *, cwd: Path, finalize_dir: Path, entry: str, args: Sequence[str] = ()
) -> subprocess.CompletedProcess[str]:
    """Source the real, unmodified `finalize_chain.sh`, override
    `FINALIZE_CHAIN_DIR` to the fake plugin's `scripts/` dir, `cd` into
    `cwd`, and call the given public entry point -- the same override
    pattern `_run_on_main_real` above already uses to prove real (non-stubbed)
    script execution."""
    quoted_args = " ".join(shlex.quote(a) for a in args)
    snippet = f"""
        cd {shlex.quote(str(cwd))}
        source {shlex.quote(str(CHAIN_PATH))}
        FINALIZE_CHAIN_DIR={shlex.quote(str(finalize_dir))}
        {entry} {quoted_args}
    """
    return subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)


def _head(repo: Path) -> str:
    return _git_ok(repo, "rev-parse", "HEAD").stdout.strip()


# --- InRepo unchanged ---------------------------------------------------------


def test_in_repo_project_never_invokes_praxion_sidecar(tmp_path: Path) -> None:
    """An `InRepo` project (a real `.ai-state/` directory, no sidecar) is
    byte-for-byte unchanged: SidecarOwned routing never fires, so the chain
    never shells out to `praxion-sidecar` at all."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _git_ok(repo_root, "init", "-q", "-b", "main")
    _configure_identity_sc(repo_root)
    (repo_root / "app.py").write_text("code\n")
    _commit_all(repo_root, "init")

    call_log = tmp_path / "calls.log"
    scripts_dir = _make_fake_plugin(tmp_path / "plugin", sidecar_call_log=call_log)

    result = _run_chain(cwd=repo_root, finalize_dir=scripts_dir, entry="finalize_chain_post_commit")

    assert result.returncode == 0, result.stderr
    assert not call_log.exists() or call_log.read_text() == ""


def test_dangling_placement_skips_state_finalization_without_crashing(tmp_path: Path) -> None:
    """A project whose `.ai-state/` symlink is dangling (e.g. an
    unmaterialized mount) must not crash the chain, must never call
    `praxion-sidecar`, and must skip every state-mutating finalizer entirely
    -- fail closed for writers, non-blocking for the chain."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_ok(project_root, "init", "-q", "-b", "main")
    _configure_identity_sc(project_root)
    (project_root / ".ai-state").symlink_to(
        Path(".praxion") / ".ai-state"
    )  # .praxion never created
    (project_root / "app.py").write_text("code\n")
    _commit_all(project_root, "init")

    call_log = tmp_path / "calls.log"
    scripts_dir = _make_fake_plugin(tmp_path / "plugin", sidecar_call_log=call_log)

    result = _run_chain(
        cwd=project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_commit"
    )

    assert result.returncode == 0, result.stderr
    assert "dangling" in result.stdout
    assert not call_log.exists() or call_log.read_text() == ""


# --- SidecarOwned: project-side reconcilers report why they no-op ------------


def test_sidecar_owned_post_merge_never_reports_the_superseded_shared_tree_reason(
    tmp_path: Path,
) -> None:
    """Whatever wording the chain settles on, it is never the first-draft's
    now-superseded 'shared live tree' reason."""
    fixture = _build_sidecar_owned_project(tmp_path)
    _write_draft(fixture.mount_dir)
    _git_ok(fixture.project_root, "commit", "--allow-empty", "-q", "-m", "trigger merge")

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert _SUPERSEDED_REASON_MARKER not in result.stdout


def test_sidecar_owned_post_merge_reports_squash_safety_skipped_project_side(
    tmp_path: Path,
) -> None:
    """`check_squash_safety.py` runs unconditionally in post-merge; under
    `SidecarOwned` it must report the corrected reason (state lives in the
    mount, diagnosed at merge-back) rather than running its diagnostic
    against the project's own tree, where there is nothing to diagnose."""
    fixture = _build_sidecar_owned_project(tmp_path)
    scripts_dir = _make_fake_plugin(tmp_path / "plugin")

    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert all(marker in result.stdout for marker in _CORRECTED_REASON_MARKERS), result.stdout


# --- SidecarOwned: the mount gets exactly one commit --------------------------


def test_sidecar_owned_post_merge_commits_the_mount_exactly_once(tmp_path: Path) -> None:
    """After the on-main composition mutates the mount, the chain calls
    `praxion-sidecar commit` exactly once -- the only commit anywhere in the
    chain -- and the project's own HEAD never moves."""
    fixture = _build_sidecar_owned_project(tmp_path)
    _write_draft(fixture.mount_dir)
    project_head_before = _head(fixture.project_root)

    call_log = tmp_path / "calls.log"
    scripts_dir = _make_fake_plugin(tmp_path / "plugin", sidecar_call_log=call_log)
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text().splitlines() if call_log.exists() else []
    sidecar_calls = [line for line in calls if line.startswith("CALL:")]
    assert len(sidecar_calls) == 1, sidecar_calls
    assert sidecar_calls[0].split(":", 1)[1].split()[0] == "commit"
    assert _head(fixture.project_root) == project_head_before


def test_sidecar_owned_post_commit_also_commits_the_mount_exactly_once(tmp_path: Path) -> None:
    """`finalize_chain_post_commit` shares the state-driven composition body
    with post-merge -- the single-mount-commit contract holds there too."""
    fixture = _build_sidecar_owned_project(tmp_path)
    _write_draft(fixture.mount_dir)

    call_log = tmp_path / "calls.log"
    scripts_dir = _make_fake_plugin(tmp_path / "plugin", sidecar_call_log=call_log)
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_commit"
    )

    assert result.returncode == 0, result.stderr
    calls = [
        line
        for line in (call_log.read_text().splitlines() if call_log.exists() else [])
        if line.startswith("CALL:")
    ]
    assert len(calls) == 1, calls
    assert calls[0].split(":", 1)[1].split()[0] == "commit"


# --- SidecarOwned: draft promotion targets the mount, not the project --------


def test_sidecar_owned_draft_promotes_into_the_mount_with_a_new_commit(tmp_path: Path) -> None:
    """The finalized ADR lands in the mount's `.ai-state/decisions/` (not
    the project's -- which has no real `.ai-state/` to land in), and the
    mount gains a real commit recording it. The project repository gains no
    commit of its own."""
    fixture = _build_sidecar_owned_project(tmp_path)
    _write_draft(fixture.mount_dir, slug="promote-me")
    mount_head_before = _head(fixture.mount_dir)
    project_head_before = _head(fixture.project_root)

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert result.returncode == 0, result.stderr
    finalized = list((fixture.mount_dir / ".ai-state" / "decisions").glob("[0-9]*-promote-me.md"))
    assert len(finalized) == 1, result.stdout
    assert _head(fixture.mount_dir) != mount_head_before
    assert _head(fixture.project_root) == project_head_before


# --- SidecarOwned: post-checkout materializes the mount with no manual step --


def test_post_checkout_materializes_a_new_worktrees_mount_with_no_manual_step(
    tmp_path: Path,
) -> None:
    """`git worktree add` on a SidecarOwned project fires `post-checkout`;
    the chain's unconditional `praxion-sidecar link --quiet` call must
    materialize that worktree's own mount and all three shadows with no
    operator action."""
    fixture = _build_sidecar_owned_project(tmp_path)
    wt_checkout = fixture.project_root / ".claude" / "worktrees" / "wt1"
    _git_ok(
        fixture.project_root, "worktree", "add", "-q", str(wt_checkout), "-b", "feat/wt1", "main"
    )

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=wt_checkout,
        finalize_dir=scripts_dir,
        entry="finalize_chain_post_checkout",
        args=("main", "feat/wt1", "1"),
    )

    assert result.returncode == 0, result.stderr
    mount = wt_checkout / _sidecar_mount.MOUNT_DIRNAME
    assert mount.is_dir(), result.stdout
    assert (wt_checkout / ".ai-state").is_symlink()
    assert (wt_checkout / "CLAUDE.local.md").is_symlink()
    assert (wt_checkout / ".claude" / "settings.local.json").is_symlink()


def test_post_checkout_ignores_a_file_checkout(tmp_path: Path) -> None:
    """`branch-flag=0` (a file checkout, not a branch switch) must never
    materialize a mount -- git fires post-checkout on every `git checkout
    <path>` too, and that path cannot legitimately land a worktree."""
    fixture = _build_sidecar_owned_project(tmp_path)
    wt_checkout = fixture.project_root / ".claude" / "worktrees" / "wt2"
    _git_ok(
        fixture.project_root, "worktree", "add", "-q", str(wt_checkout), "-b", "feat/wt2", "main"
    )
    (wt_checkout / _sidecar_mount.MOUNT_DIRNAME).exists()  # sanity: not yet materialized

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=wt_checkout,
        finalize_dir=scripts_dir,
        entry="finalize_chain_post_checkout",
        args=("main", "feat/wt2", "0"),
    )

    assert result.returncode == 0, result.stderr
    assert not (wt_checkout / _sidecar_mount.MOUNT_DIRNAME).exists()


# --- Convergence-ordering settling tests (channel 1) --------------------------
#
# `praxion-sidecar merge-back --auto` does not exist yet, so every test below
# is RED today by construction: the chain either never calls the verb, or
# calls it and gets a non-blocking "unrecognized verb" warning, and the
# `converged`/`skipped`/`aborted` line never appears. The git fixtures are
# built to be genuinely correct convergence scenarios so these tests mean
# something the moment the verb lands -- not placeholders that would pass on
# any output.


def test_manual_merge_promotes_the_draft_in_the_same_finalize_run(tmp_path: Path) -> None:
    """A worktree's draft is committed on `wt/x`; the operator merges its
    project branch with a plain `git merge` (no `/merge-worktree` step).
    `finalize_chain_post_merge` in the main checkout must both log
    `converged wt/x` and promote the draft in that same run."""
    fixture = _build_sidecar_owned_project(tmp_path)
    checkout = _add_project_worktree(fixture.project_root, "x", "feat/x")
    wt_mount = _mount_worktree(fixture.sidecar_root, checkout, "wt/x", project_branch="feat/x")
    _write_draft(wt_mount, slug="from-wt-x")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", "feat/x")

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert "converged wt/x" in result.stdout
    finalized = list((fixture.mount_dir / ".ai-state" / "decisions").glob("[0-9]*-from-wt-x.md"))
    assert len(finalized) == 1, result.stdout


def test_squash_merge_shape_also_converges_and_promotes(tmp_path: Path) -> None:
    """The squash-merge variant of the same scenario: the project lands the
    squashed tree by hand (as a GitHub squash-merge would), with no explicit
    merge-back -- `converged wt/x` still fires and the draft still promotes."""
    fixture = _build_sidecar_owned_project(tmp_path)
    checkout = _add_project_worktree(fixture.project_root, "x", "feat/x")
    wt_mount = _mount_worktree(fixture.sidecar_root, checkout, "wt/x", project_branch="feat/x")
    _write_draft(wt_mount, slug="from-wt-x")
    _git_ok(fixture.project_root, "merge", "-q", "--squash", "feat/x")
    _commit_all(fixture.project_root, "squash-merge feat/x")

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert "converged wt/x" in result.stdout
    finalized = list((fixture.mount_dir / ".ai-state" / "decisions").glob("[0-9]*-from-wt-x.md"))
    assert len(finalized) == 1, result.stdout


def test_one_ineligible_branch_never_blocks_another_branchs_convergence(tmp_path: Path) -> None:
    """`wt/y`'s project branch never merged (ineligible forever); `wt/x`'s
    did. One run must log `skipped wt/y: project branch not merged` AND
    still promote `wt/x`'s draft -- one branch's ineligibility never blocks
    another's convergence."""
    fixture = _build_sidecar_owned_project(tmp_path)

    x_checkout = _add_project_worktree(fixture.project_root, "x", "feat/x")
    x_mount = _mount_worktree(fixture.sidecar_root, x_checkout, "wt/x", project_branch="feat/x")
    _write_draft(x_mount, slug="from-wt-x")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", "feat/x")

    y_checkout = _add_project_worktree(fixture.project_root, "y", "feat/y")
    y_mount = _mount_worktree(fixture.sidecar_root, y_checkout, "wt/y", project_branch="feat/y")
    # A real state commit on wt/y's own branch, exactly like wt/x's above --
    # without one, wt/y has no divergence from `main` at all and classifies
    # as the trivially-contained `MergedLive` (a healthy no-op branch), not
    # `UnmergedIneligible`. feat/y is intentionally never merged into the
    # project's main.
    (y_mount / ".ai-state" / "DESIGN.md").write_text("y-change\n")
    _commit_all(y_mount, "y state")

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert "skipped wt/y: project branch not merged" in result.stdout
    assert "converged wt/x" in result.stdout
    finalized = list((fixture.mount_dir / ".ai-state" / "decisions").glob("[0-9]*-from-wt-x.md"))
    assert len(finalized) == 1, result.stdout


def test_a_conflicting_branch_aborts_without_blocking_the_chain_or_dirtying_the_mount(
    tmp_path: Path,
) -> None:
    """`wt/z`'s project branch merged, but its sidecar branch genuinely
    conflicts with the main mount's own state edit. The chain must log
    `aborted wt/z: conflict — run praxion-sidecar merge-back --from wt/z`,
    leave the main mount clean (no stray `MERGE_HEAD`), and still promote
    whatever other eligible branch's draft exists -- the non-blocking
    contract `_finalize_chain_run_script` already applies to every other
    step in the chain."""
    fixture = _build_sidecar_owned_project(tmp_path)

    z_checkout = _add_project_worktree(fixture.project_root, "z", "feat/z")
    z_mount = _mount_worktree(fixture.sidecar_root, z_checkout, "wt/z", project_branch="feat/z")
    (z_mount / ".ai-state" / "DESIGN.md").write_text("z-change\n")
    _commit_all(z_mount, "z state")
    # Independent, conflicting edit on the MAIN sidecar branch itself.
    (fixture.mount_dir / ".ai-state" / "DESIGN.md").write_text("main-change\n")
    _commit_all(fixture.mount_dir, "main state, diverging")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", "feat/z")

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    result = _run_chain(
        cwd=fixture.project_root, finalize_dir=scripts_dir, entry="finalize_chain_post_merge"
    )

    assert "aborted wt/z: conflict — run praxion-sidecar merge-back --from wt/z" in result.stdout
    git_dir = fixture.mount_dir / ".git"
    assert not git_dir.is_file() or "MERGE_HEAD" not in git_dir.read_text()
    assert _git_ok(fixture.mount_dir, "status", "--porcelain").stdout == ""


def test_strict_mode_does_not_turn_an_aborted_convergence_into_a_failing_chain(
    tmp_path: Path,
) -> None:
    """`FINALIZE_CHAIN_STRICT=1` makes a *finalizer* failure propagate (see
    the interpreter-resolution tests above), but an aborted convergence is a
    reported, expected outcome for one branch -- not a finalizer crash -- so
    it must not flip the chain's exit code even under strict mode."""
    fixture = _build_sidecar_owned_project(tmp_path)
    z_checkout = _add_project_worktree(fixture.project_root, "z", "feat/z")
    z_mount = _mount_worktree(fixture.sidecar_root, z_checkout, "wt/z", project_branch="feat/z")
    (z_mount / ".ai-state" / "DESIGN.md").write_text("z-change\n")
    _commit_all(z_mount, "z state")
    (fixture.mount_dir / ".ai-state" / "DESIGN.md").write_text("main-change\n")
    _commit_all(fixture.mount_dir, "main state, diverging")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", "feat/z")

    scripts_dir = _make_fake_plugin(tmp_path / "plugin")
    snippet = f"""
        cd {shlex.quote(str(fixture.project_root))}
        source {shlex.quote(str(CHAIN_PATH))}
        FINALIZE_CHAIN_DIR={shlex.quote(str(scripts_dir))}
        export FINALIZE_CHAIN_STRICT=1
        finalize_chain_post_merge
    """
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
