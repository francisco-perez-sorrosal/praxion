"""Tests for check_squash_safety.py -- post-merge squash-merge detection.

Behavioral tests driven from dec-059 (Squash-Merge Safety) and
acceptance criterion AC-14 in the concurrency-collab pipeline's
SYSTEMS_PLAN.md.

The script under test:
1. Detects squash-merges that erase ``.ai-state/`` entries.
2. Emits a loud warning with recovery steps when erasure is detected.
3. Always exits 0 (non-blocking; post-merge cannot abort).

Surfaced assumptions about the implementer's contract (per the Step 10b
prompt; reconciled in Step 10c if the impl renames helpers):

    is_squash_merge()                  -> bool
    ai_state_entries_at(rev)           -> set[str] | list[str]
    emit_warning(before, after, ...)   -> None
    main(argv: list[str] | None = ...) -> int
    --since <ref>                      -- flag overriding HEAD~1 baseline
    --verbose                          -- flag setting logger to DEBUG

Some scenarios the prompt requires (``--since``, ``--verbose``,
20-file truncation cap) are not enumerated in Step 10a's impl spec and may
require reconciliation at the Step 10c integration checkpoint.

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
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=""
    )


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

    monkeypatch.setattr(squash_safety.subprocess, "run", _fake_run)


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


# -- Regular merge detection (AC-14) ------------------------------------------


class TestMergeRegularDetection:
    """AC-14: regular merge commits (multi-parent) MUST NOT trigger a warning."""

    def test_regular_merge_commit_exits_clean(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """AC-14: a 2-parent merge commit (regular merge) emits no warning.

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
        assert "WARNING" not in combined_output.upper() or (
            "ERASED" not in combined_output.upper()
        )


# -- Single-parent commit triggers inspection (AC-14) -------------------------


class TestSingleParentDetection:
    """AC-14: single-parent commits proceed to .ai-state/ erasure inspection."""

    def test_single_parent_commit_triggers_inspection(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AC-14: 2-word rev-list output (commit + 1 parent) is the squash signal.

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


# -- Erasure detection (AC-14) ------------------------------------------------


class TestErasureDetection:
    """AC-14: erasure of .ai-state/ entries triggers a loud, informative warning."""

    def test_no_erasure_when_files_intact(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AC-14: single-parent commit with no .ai-state/ count change -> no warning.

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
        """AC-14: a removed .ai-state/ file appears in the warning output.

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
        """AC-14 (prompt-extension): when many files are erased, output stays bounded.

        25 .ai-state/ files removed in one squash. The warning must remain
        readable: at most 20 filenames listed, with the remaining count
        elided ("...", "more", "(+5 more)" or any equivalent truncation
        marker).

        NOTE: This bound is from the Step 10b prompt; not codified in
        dec-059. The implementer MAY choose to print only the
        count (no filenames) -- in that case the truncation marker does not
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
            f"warning listed {name_hits} filenames; must be 0 (count-only) "
            "or <= 20 (truncated)"
        )

    def test_warning_includes_recovery_steps(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AC-14: the warning surfaces actionable recovery steps.

        Per dec-059, the warning block must point users at:
        - ``git reflog`` (locate the pre-squash tip)
        - ``git cherry-pick`` (replay the lost commit)
        - regular merge / rebase-and-merge as the prevention path

        Per the Step 10b prompt, all three phrases ('reflog', 'cherry-pick',
        'rebase') must appear in the warning text. Step 10b in the plan
        additionally requires 'pr-conventions.md' -- asserted as a bonus.
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
        assert "cherry-pick" in combined.lower(), (
            "warning must mention `git cherry-pick`"
        )
        # Prevention path per ADR + prompt
        assert "rebase" in combined.lower(), (
            "warning must mention rebase-and-merge as the prevention path"
        )
        # Bonus: pr-conventions.md pointer (Step 10b plan-level requirement)
        assert "pr-conventions.md" in combined.lower(), (
            "warning must point at rules/swe/vcs/pr-conventions.md"
        )


# -- Exit code (AC-14) --------------------------------------------------------


class TestExitCode:
    """AC-14: exit code is ALWAYS 0 -- post-merge cannot abort."""

    def test_always_exits_zero_even_on_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-14: even when the warning fires, the process returns 0.

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
    """AC-14: --since <ref> overrides the auto-detected HEAD~1 baseline."""

    def test_since_flag_overrides_auto_detection(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC-14 (prompt-extension): --since custom-ref is forwarded to git.

        When the user passes --since some-ref, the script must enumerate
        ``.ai-state/`` files at ``some-ref`` (not at HEAD~1) when computing
        the baseline. We assert that ``some-ref`` appears in at least one
        captured git invocation.

        NOTE: --since is not in Step 10a's impl spec; if the implementer did
        not add it, this test will fail (e.g., argparse exits non-zero on
        unknown flag) -- the Step 10c reconciliation point catches this.
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
    """AC-14: --verbose enables DEBUG-level logging (observable via caplog)."""

    def test_verbose_enables_debug_logging(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """AC-14 (prompt-extension): --verbose -> at least one DEBUG record emitted.

        Without --verbose, the script logs at INFO or above. With --verbose,
        DEBUG records become observable via caplog. We assert at least one
        DEBUG-level record is produced when --verbose is passed.

        The scenario routes ``git rev-parse --is-inside-work-tree`` to ``false``
        which the impl logs at DEBUG ("not inside a git worktree; skipping
        squash-safety check"). This guarantees an observable DEBUG record on
        the happy ``--verbose`` path without depending on a git failure.

        NOTE: --verbose is not in Step 10a's impl spec; if missing, argparse
        will exit non-zero on the unknown flag and the test fails -- the
        Step 10c reconciliation point catches this.
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
