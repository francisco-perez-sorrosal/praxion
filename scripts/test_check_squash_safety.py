"""Tests for check_squash_safety.py -- post-merge squash-merge detection.

Behavioral tests of the Squash-Merge Safety check (see dec-059):

1. Detects squash-merges that erase ``.ai-state/`` entries.
2. Emits a loud warning with recovery steps when erasure is detected.
3. Always exits 0 (non-blocking; post-merge cannot abort).

Expected public surface of the script under test:

    is_squash_merge()                  -> bool
    ai_state_entries_at(rev)           -> set[str] | list[str]
    emit_warning(before, after, ...)   -> None
    main(argv: list[str] | None = ...) -> int
    --since <ref>                      -- flag overriding HEAD~1 baseline
    --verbose                          -- flag setting logger to DEBUG

Some scenarios (``--since``, ``--verbose``, 20-file truncation cap) are
extensions beyond the minimal script contract; if absent, argparse will
exit non-zero on the unknown flag and those specific tests fail -- that
failure signal is expected and surfaces the gap.

Import strategy mirrors scripts/test_finalize_adrs.py: load via
``importlib.util`` so the script does not need to be on sys.path.

No real git calls: ``subprocess.run`` is monkeypatched throughout.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_squash_safety.py"


def _load_module() -> Any:
    """Load check_squash_safety.py without requiring it on sys.path."""
    spec = importlib.util.spec_from_file_location("check_squash_safety", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


squash_safety = _load_module()


# -- Test helpers -------------------------------------------------------------


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    """Build a fake CompletedProcess for monkeypatched subprocess.run."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def mock_git_router(
    monkeypatch: pytest.MonkeyPatch,
    router: Callable[[list[str]], str],
    captured: list[list[str]] | None = None,
) -> None:
    """Replace ``subprocess.run`` with a router that dispatches on git args.

    ``router`` receives the full subprocess args list (e.g.
    ``['git', 'rev-parse', '--is-inside-work-tree']``) and returns the stdout
    string that call should produce. If ``captured`` is provided, every
    invocation's args list is appended for later assertion.

    A router is more robust than an order-based generator because the script
    may take different code paths (early-exit for non-worktree, multi-parent
    short-circuit, etc.) that produce different git-call sequences. The
    router only needs to specify the mapping from query shape to response.
    """

    def _fake_run(args: Any, *_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        args_list = list(args) if not isinstance(args, str) else args.split()
        if captured is not None:
            captured.append(args_list)
        stdout = router(args_list)
        return _completed(stdout)

    # Patch `subprocess.run` on the stdlib module itself, not through the
    # script's own binding: the script now issues its git calls through the
    # shared `_git_runner` sibling, so reaching for `squash_safety.subprocess`
    # would target a name the script no longer imports.
    monkeypatch.setattr(subprocess, "run", _fake_run)


def _invoke_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    """Invoke main() regardless of its exact signature; normalize the exit code."""
    try:
        sig = inspect.signature(squash_safety.main)
    except (ValueError, TypeError):
        sig = None

    try:
        if sig is not None and len(sig.parameters) >= 1:
            rc = squash_safety.main(argv)
        else:
            monkeypatch.setattr(sys, "argv", ["check_squash_safety.py", *argv])
            rc = squash_safety.main()
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1

    if rc is None:
        return 0
    return int(rc)


def _scenario(
    monkeypatch: pytest.MonkeyPatch,
    *,
    parents: int,
    erased: list[str] | None = None,
    captured: list[list[str]] | None = None,
) -> None:
    """Wire up a router-based subprocess.run mock for a typical scenario.

    Routes the git calls the script actually issues:
      - ``git rev-parse --is-inside-work-tree`` -> always "true" (we are a repo)
      - ``git rev-list --parents -n 1 HEAD``    -> "head_sha p1 [p2 ...]"
      - ``git rev-parse <ref>``                 -> "<ref>_sha" (echo)
      - ``git diff --diff-filter=D --name-only <parent> HEAD -- .ai-state/``
                                                -> newline-joined erased paths

    ``parents`` controls multi- vs single-parent (regular vs squash signal).
    ``erased`` is the list of .ai-state/ paths reported as deleted between
    parent and HEAD. Empty/None means no erasure.

    Any unrecognized git query returns empty stdout (safe default). This is
    deliberately tolerant: if the impl issues additional probes (e.g.,
    ``git ls-tree``) the test still works as long as the observable
    behavior (warning emitted / not, exit code, output content) is right.
    """
    erased_paths = erased or []
    parent_line = "head_sha " + " ".join(f"parent{i}" for i in range(parents))
    erasure_output = "\n".join(erased_paths)

    def _router(args: list[str]) -> str:
        # All routes are git invocations; first arg is "git".
        if len(args) < 2 or args[0] != "git":
            return ""
        sub = args[1]
        if sub == "rev-parse":
            # `git rev-parse --is-inside-work-tree` -> "true"
            if "--is-inside-work-tree" in args:
                return "true"
            # `git rev-parse <ref>` -> echo a synthetic sha
            ref = args[-1]
            return f"{ref}_sha"
        if sub == "rev-list" and "--parents" in args:
            return parent_line
        if sub == "diff" and "--diff-filter=D" in args:
            return erasure_output
        return ""

    mock_git_router(monkeypatch, _router, captured=captured)


# -- Regular merge detection ------------------------------------------


class TestMergeRegularDetection:
    """Regular merge commits (multi-parent) MUST NOT trigger a warning."""

    def test_regular_merge_commit_exits_clean(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A 2-parent merge commit (regular merge) emits no warning.

        ``git rev-list --parents -n 1 HEAD`` returns 3 whitespace-separated
        SHAs (commit + 2 parents) for a regular merge. The script must short-
        circuit and exit 0 without printing the warning block.
        """
        _scenario(
            monkeypatch,
            parents=2,
            erased=[],
        )

        with caplog.at_level(logging.DEBUG):
            exit_code = _invoke_main(monkeypatch, [])

        assert exit_code == 0
        captured = capsys.readouterr()
        combined_output = captured.out + captured.err
        # No warning block emitted -- detect by the WARNING marker the impl uses
        assert "WARNING" not in combined_output.upper() or ("ERASED" not in combined_output.upper())


# -- Single-parent commit triggers inspection -------------------------


class TestSingleParentDetection:
    """Single-parent commits proceed to .ai-state/ erasure inspection."""

    def test_single_parent_commit_triggers_inspection(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """2-word rev-list output (commit + 1 parent) is the squash signal.

        With a strict decrease in ``.ai-state/`` count between HEAD~1 and HEAD,
        the warning MUST be emitted.
        """
        _scenario(
            monkeypatch,
            parents=1,
            erased=[
                ".ai-state/decisions/051-b.md",
                ".ai-state/decisions/052-c.md",
            ],
        )

        exit_code = _invoke_main(monkeypatch, [])

        assert exit_code == 0
        captured = capsys.readouterr()
        # Single-parent + strict decrease -> warning MUST appear somewhere
        combined = captured.out + captured.err
        assert "WARNING" in combined.upper()


# -- Erasure detection ------------------------------------------------


class TestErasureDetection:
    """Erasure of .ai-state/ entries triggers a loud, informative warning."""

    def test_no_erasure_when_files_intact(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Single-parent commit with no .ai-state/ count change -> no warning.

        A non-merge commit (e.g., a fast-forward or a regular commit) that does
        not erase anything in .ai-state/ MUST exit 0 silently.
        """
        _scenario(
            monkeypatch,
            parents=1,
            erased=[],
        )

        exit_code = _invoke_main(monkeypatch, [])

        assert exit_code == 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # Either no output, or output that does not flag erasure
        assert "ERASED" not in combined.upper()

    def test_erasure_flagged_when_ai_state_paths_removed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A removed .ai-state/ file appears in the warning output.

        Per dec-059, the warning block surfaces information about
        erased files. The implementer may print a count, list filenames,
        or both. This test asserts BOTH that the warning fires AND that the
        specific erased filename appears verbatim in the output.
        """
        erased_path = ".ai-state/decisions/059-example.md"
        _scenario(
            monkeypatch,
            parents=1,
            erased=[erased_path],
        )

        exit_code = _invoke_main(monkeypatch, [])

        assert exit_code == 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # The warning block must appear and reflect the erasure
        assert "WARNING" in combined.upper()
        # The specific erased filename MUST be observable in the output so
        # users can see exactly what was lost.
        assert "059-example.md" in combined, (
            f"erased filename must appear in warning; output was: {combined!r}"
        )

    def test_warning_caps_at_20_files(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """(prompt-extension): when many files are erased, output stays bounded.

        25 .ai-state/ files removed in one squash. The warning must remain
        readable: at most 20 filenames listed, with the remaining count
        elided ("...", "more", "(+5 more)" or any equivalent truncation
        marker).

        NOTE: The 20-file cap is a display-bound heuristic, not codified
        in dec-059. The implementer MAY choose to print only the count
        (no filenames) -- in that case the truncation marker does not
        apply. The assertion below is permissive: it accepts EITHER a
        truncation marker OR a count-only output (no filenames at all).
        """
        erased_files = [f".ai-state/decisions/{n:03d}-x.md" for n in range(25)]
        _scenario(
            monkeypatch,
            parents=1,
            erased=erased_files,
        )

        exit_code = _invoke_main(monkeypatch, [])

        assert exit_code == 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err

        # Count how many of the 25 filenames appear in the output
        name_hits = sum(1 for n in range(25) if f"{n:03d}-x.md" in combined)
        # Either none of them (count-only output) OR at most 20 (truncated list)
        assert name_hits == 0 or name_hits <= 20, (
            f"warning listed {name_hits} filenames; must be 0 (count-only) or <= 20 (truncated)"
        )

    def test_warning_includes_recovery_steps(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The warning surfaces actionable recovery steps.

        Per dec-059, the warning block must point users at:
        - ``git reflog`` (locate the pre-squash tip)
        - ``git cherry-pick`` (replay the lost commit)
        - regular merge / rebase-and-merge as the prevention path

        The test asserts that all three phrases ('reflog', 'cherry-pick',
        'rebase') appear in the warning text, plus a pointer to
        'pr-conventions.md' as a prevention-path hint.
        """
        _scenario(
            monkeypatch,
            parents=1,
            erased=[".ai-state/decisions/051-b.md"],
        )

        exit_code = _invoke_main(monkeypatch, [])
        assert exit_code == 0

        captured = capsys.readouterr()
        combined = captured.out + captured.err

        # Recovery commands per ADR + prompt
        assert "reflog" in combined.lower(), "warning must mention `git reflog`"
        assert "cherry-pick" in combined.lower(), "warning must mention `git cherry-pick`"
        # Prevention path per ADR + prompt
        assert "rebase" in combined.lower(), (
            "warning must mention rebase-and-merge as the prevention path"
        )
        # Bonus: pr-conventions.md pointer (prevention-path hint)
        assert "pr-conventions.md" in combined.lower(), (
            "warning must point at rules/swe/vcs/pr-conventions.md"
        )


# -- Exit code --------------------------------------------------------


class TestExitCode:
    """Exit code is ALWAYS 0 -- post-merge cannot abort."""

    def test_always_exits_zero_even_on_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Even when the warning fires, the process returns 0.

        The hook is non-blocking; a non-zero exit would surface as a
        post-merge failure which is the wrong UX (the merge already
        succeeded by the time the hook runs).
        """
        _scenario(
            monkeypatch,
            parents=1,
            erased=[
                ".ai-state/decisions/050-a.md",
                ".ai-state/decisions/051-b.md",
                ".ai-state/decisions/052-c.md",
            ],
        )

        exit_code = _invoke_main(monkeypatch, [])
        assert exit_code == 0


# -- --since flag -------------------------------------------------------------


class TestSinceFlag:
    """--since <ref> overrides the auto-detected HEAD~1 baseline."""

    def test_since_flag_overrides_auto_detection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """(prompt-extension): --since custom-ref is forwarded to git.

        When the user passes --since some-ref, the script must enumerate
        ``.ai-state/`` files at ``some-ref`` (not at HEAD~1) when computing
        the baseline. We assert that ``some-ref`` appears in at least one
        captured git invocation.

        NOTE: --since is an extension beyond the minimal script contract.
        If the implementer omits it, argparse exits non-zero on the
        unknown flag and this test fails -- that failure signal is
        expected and surfaces the gap.
        """
        captured: list[list[str]] = []
        _scenario(
            monkeypatch,
            parents=1,
            erased=[],
            captured=captured,
        )

        exit_code = _invoke_main(monkeypatch, ["--since", "custom-ref"])
        assert exit_code == 0

        # custom-ref must appear in at least one git call's args
        flat = [arg for call in captured for arg in call]
        assert any("custom-ref" in str(arg) for arg in flat), (
            f"--since custom-ref must be forwarded to git; observed git args: {flat!r}"
        )


# -- --verbose flag -----------------------------------------------------------


class TestVerboseFlag:
    """--verbose enables DEBUG-level logging (observable via caplog)."""

    def test_verbose_enables_debug_logging(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """(prompt-extension): --verbose -> at least one DEBUG record emitted.

        Without --verbose, the script logs at INFO or above. With --verbose,
        DEBUG records become observable via caplog. We assert at least one
        DEBUG-level record is produced when --verbose is passed.

        The scenario routes ``git rev-parse --is-inside-work-tree`` to ``false``
        which the impl logs at DEBUG ("not inside a git worktree; skipping
        squash-safety check"). This guarantees an observable DEBUG record on
        the happy ``--verbose`` path without depending on a git failure.

        NOTE: --verbose is an extension beyond the minimal script
        contract. If missing, argparse exits non-zero on the unknown
        flag and the test fails -- that failure signal is expected and
        surfaces the gap.
        """

        def _router(args: list[str]) -> str:
            # Force the "not inside a git worktree" branch which logs at DEBUG.
            if (
                len(args) >= 3
                and args[0] == "git"
                and args[1] == "rev-parse"
                and "--is-inside-work-tree" in args
            ):
                return "false"
            return ""

        mock_git_router(monkeypatch, _router)

        # Capture at the lowest level so DEBUG records survive filtering
        with caplog.at_level(logging.DEBUG):
            exit_code = _invoke_main(monkeypatch, ["--verbose"])

        assert exit_code == 0

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_records) >= 1, (
            "--verbose must emit at least one DEBUG record; "
            f"captured levels: {[r.levelname for r in caplog.records]}"
        )


# -- --target-mount: reinstated at merge-back (ARCH_WT_RULING.md § 8) -------
#
# Everything below drives *real* `git worktree` / `git merge --squash` via
# subprocess -- deliberately departing from this file's own
# monkeypatched-`subprocess.run` convention above, because the behaviour
# under test is a genuine squash-shaped commit's parent count and tree diff,
# which a router fake cannot produce. `--target-mount` does not exist yet
# (concurrent BDD/TDD with the paired implementation work): confirmed
# empirically before writing these tests that passing it today is an *argparse* error
# (`unrecognized arguments: --target-mount ...`, exit 2) -- so every test
# below is RED today for a different, simpler reason than the reconciler's:
# the flag itself does not parse.

_TM_IDENTITY_ARGS = ("-c", "user.email=test@example.com", "-c", "user.name=Test")


def _tm_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _tm_git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _tm_git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _tm_configure_identity(repo: Path) -> None:
    _tm_git_ok(repo, "config", "user.email", "test@example.com")
    _tm_git_ok(repo, "config", "user.name", "Test")


def _tm_commit_all(repo: Path, message: str) -> None:
    _tm_git_ok(repo, "add", "-A")
    _tm_git_ok(repo, *_TM_IDENTITY_ARGS, "commit", "-q", "-m", message)


def _tm_adr_body(num: int, slug: str) -> str:
    return (
        f"---\nid: dec-{num:03d}\ntitle: {slug}\nstatus: accepted\n"
        "category: architectural\ndate: 2026-01-01\n"
        f"summary: {slug}\ntags: [test]\nmade_by: agent\n---\n\n## Context\n\nTest.\n"
    )


def _tm_init_sidecar(sidecar_root: Path) -> None:
    """Seed a sidecar repo with two finalized ADRs, then detach `main` so it
    is free for the mounts below (mirrors `praxion-sidecar init`'s own
    sequence, `ARCH_WT_RULING.md` § 5)."""
    _tm_git_ok(sidecar_root, "init", "-q", "-b", "main")
    _tm_configure_identity(sidecar_root)
    decisions = sidecar_root / ".ai-state" / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "001-first.md").write_text(_tm_adr_body(1, "first"))
    (decisions / "002-other.md").write_text(_tm_adr_body(2, "other"))
    _tm_commit_all(sidecar_root, "seed sidecar state")
    _tm_git_ok(sidecar_root, "checkout", "-q", "--detach")


def _tm_init_project(project_root: Path) -> None:
    _tm_git_ok(project_root, "init", "-q", "-b", "main")
    _tm_configure_identity(project_root)
    (project_root / "app.py").write_text("code\n")
    _tm_commit_all(project_root, "init")


def _tm_mount(sidecar_root: Path, dest: Path, branch: str, *, base: str | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["worktree", "add", "-q"]
    args += [str(dest), branch] if base is None else ["-b", branch, str(dest), base]
    _tm_git_ok(sidecar_root, *args)
    _tm_configure_identity(dest)
    return dest


def _tm_safe_cwd(tmp_path: Path) -> Path:
    """A throwaway, unrelated git repo used only as subprocess `cwd` -- see
    the module-level note above for why this matters even though this
    file's `--target-mount` tests fail on an argparse error today rather
    than a git-root fallback."""
    anchor = tmp_path / "cwd_anchor"
    anchor.mkdir()
    _tm_git_ok(anchor, "init", "-q", "-b", "main")
    _tm_configure_identity(anchor)
    return anchor


def _tm_write_manifest(
    sidecar_root: Path, project_root: Path, *, project_id: str = "local--abc123"
) -> None:
    manifest_path = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest_path.write_text(
        "schema: 1\n"
        "project:\n"
        "  origin: null\n"
        f'  id: "{project_id}"\n'
        f'  roots: ["{project_root.resolve()}"]\n'
    )


def _tm_run(safe_cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        cwd=safe_cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _tm_build_squash_erasure_fixture(tmp_path: Path) -> Path:
    """`main` mount with two ADRs; `wt/x` adds a third; `main` squash-merges
    `wt/x` and the squash commit *also* drops one of the original two ADRs
    -- the exact single-parent-plus-`.ai-state/`-deletion signature this
    script exists to detect. Returns the main mount path."""
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    sidecar_root.mkdir()
    project_root.mkdir()
    _tm_init_sidecar(sidecar_root)
    _tm_init_project(project_root)
    main_mount = _tm_mount(sidecar_root, project_root / ".praxion-state", "main")
    wt_mount = _tm_mount(
        sidecar_root,
        project_root / ".claude" / "worktrees" / "x" / ".praxion-state",
        "wt/x",
        base="main",
    )

    (wt_mount / ".ai-state" / "decisions" / "003-new.md").write_text(_tm_adr_body(3, "new"))
    _tm_commit_all(wt_mount, "wt: add 003")

    _tm_git_ok(main_mount, "merge", "-q", "--squash", "wt/x")
    _tm_git_ok(main_mount, "rm", "-q", ".ai-state/decisions/002-other.md")
    _tm_commit_all(main_mount, "squash wt/x (drops 002)")

    return main_mount


def _tm_build_sidecar_owned_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """A minimal, fully-wired `SidecarOwned` project -- mount, manifest,
    shadow symlink. Returns `(project_root, main_mount)`."""
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    sidecar_root.mkdir()
    project_root.mkdir()
    _tm_init_sidecar(sidecar_root)
    _tm_init_project(project_root)
    main_mount = _tm_mount(sidecar_root, project_root / ".praxion-state", "main")
    _tm_write_manifest(sidecar_root, project_root)
    (project_root / ".ai-state").symlink_to(
        Path(".praxion-state") / ".ai-state", target_is_directory=True
    )
    return project_root, main_mount


class TestTargetMountSquashErasureDiagnostic:
    """`check_squash_safety.py --target-mount <mount>` diagnoses a
    squash-shaped merge that erased a `.ai-state/` entry -- at the mount,
    where the sidecar's own history now lives (`ARCH_WT_RULING.md` § 8)."""

    def test_reports_the_erased_entry_and_stays_non_blocking(self, tmp_path: Path):
        main_mount = _tm_build_squash_erasure_fixture(tmp_path)
        safe_cwd = _tm_safe_cwd(tmp_path)

        result = _tm_run(safe_cwd, "--target-mount", str(main_mount))

        assert result.returncode == 0, result.stderr
        combined = result.stdout + result.stderr
        assert "WARNING" in combined.upper()
        assert "002-other.md" in combined


class TestTargetMountRefusesInvalidPaths:
    """`--target-mount` validates its argument the same way
    `reconcile_ai_state.py` does -- it must name a real state mount, never a
    path that merely resolves into (or through) one. The exact wording is
    an implementation choice; this test pins only the observable contract:
    refuse loudly (non-zero exit), never diagnose a directory as if it were
    the mount."""

    def test_refuses_a_directory_that_is_not_a_sidecar_worktree(self, tmp_path: Path):
        safe_cwd = _tm_safe_cwd(tmp_path)
        not_a_mount = tmp_path / "plain_dir"
        not_a_mount.mkdir()

        result = _tm_run(safe_cwd, "--target-mount", str(not_a_mount))

        assert result.returncode != 0
        combined = (result.stdout + result.stderr).lower()
        assert "mount" in combined


class TestProjectSideSkipsUnderSidecarOwnership:
    """`check_squash_safety.py --repo-root <project>` (no `--target-mount`)
    on a `SidecarOwned` project is a no-op: the project repository does not
    own `.ai-state/` -- the diagnostic runs at merge-back, against the
    mount, not here (`ARCH_WT_RULING.md` § 8).

    Today there is no such skip: the script inspects the *project's own*
    single-commit history (unrelated to the mount's), which happens to be
    harmless here only because a freshly-initialized project has no parent
    commit to compare against -- `is_single_parent_commit` never finds a
    signature to report. The corrected-reason message is absent either way,
    which is what `test_skips_with_the_corrected_reason` pins as RED.
    """

    def test_skips_with_the_corrected_reason(self, tmp_path: Path):
        project_root, _main_mount = _tm_build_sidecar_owned_fixture(tmp_path)

        result = _tm_run(_tm_safe_cwd(tmp_path), "--repo-root", str(project_root))

        assert result.returncode == 0, result.stderr
        combined = (result.stdout + result.stderr).lower()
        assert "does not own" in combined
        assert ".ai-state" in combined
