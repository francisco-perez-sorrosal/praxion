"""CLI entry point for eval-praxion — Python module layer.

Wires the CorpusReader's 4-case arg resolver as the primary entry surface:
    1. No argument        → resolve to 'main' HEAD via git rev-parse
    2. Existing FS path   → path mode
    3. Known worktree name → expand to .claude/worktrees/<name>/
    4. Valid git ref      → ref mode

Auth route is resolved via select_judge_client() (env-detect):
    CLAUDE_CODE_OAUTH_TOKEN set → agent-sdk route
    ANTHROPIC_API_KEY set       → messages-api route
    Neither                     → RuntimeError naming both vars

The slash-command registration (entry point script, commands/eval-praxion.md)
is Step 8 scope — this module is the Python-level CLI only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Public re-export: run_eval (the orchestrator-backed implementation lives in
# harness/__init__.py; CLI consumers use it as cli.run_eval)
# ---------------------------------------------------------------------------
from praxion_evals.harness import run_eval  # noqa: F401

# ---------------------------------------------------------------------------
# Arg resolver: 4-case resolution
# ---------------------------------------------------------------------------

_WORKTREES_RELATIVE = Path(".claude") / "worktrees"


def resolve_target(target: str | None, repo_root: Path | None = None) -> Any:
    """Resolve a CLI target argument to a CorpusReader-compatible form.

    Resolution order (first match wins):
    1. None → resolve to 'main' HEAD SHA via git rev-parse
    2. Existing filesystem path → return the Path object (path mode)
    3. Known worktree name under <repo_root>/.claude/worktrees/ → return Path
    4. Valid git ref (git rev-parse succeeds) → return the resolved SHA string
    5. None of the above → raise ValueError with a three-part error message

    Args:
        target: The raw CLI argument, or None when no argument was given.
        repo_root: Repository root for git commands and worktree expansion.
                   Defaults to the current working directory.

    Returns:
        Resolved target: a Path (filesystem modes) or str (ref mode).

    Raises:
        ValueError: When the target matches none of the four cases.
    """
    cwd = repo_root or Path.cwd()

    # Case 1: no argument → resolve to main HEAD
    if target is None:
        return _resolve_git_ref("main", cwd)

    # Case 2: existing filesystem path
    candidate_path = Path(target)
    if candidate_path.exists():
        return candidate_path

    # Case 3: known worktree name
    worktrees_dir = cwd / _WORKTREES_RELATIVE
    if worktrees_dir.is_dir():
        worktree_candidate = worktrees_dir / target
        if worktree_candidate.is_dir():
            return worktree_candidate

    # Case 4: valid git ref
    try:
        return _resolve_git_ref(target, cwd)
    except ValueError:
        pass

    # Case 5: invalid target
    raise ValueError(
        f"Cannot resolve target {target!r}. "
        f"Tried: filesystem path, worktree under {worktrees_dir}, git ref. "
        "Pass an existing path, a known worktree name, a valid git ref, "
        "or omit the argument to eval the main branch HEAD."
    )


def _resolve_git_ref(ref: str, cwd: Path) -> str:
    """Resolve a git ref to its full SHA. Raises ValueError if not resolvable."""
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"git ref {ref!r} is not resolvable: {result.stderr.strip()}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Argparse-backed CLI entry point for eval-praxion.

    Usage:
        python -m praxion_evals.harness.cli [TARGET] [--output-dir DIR]

    TARGET is resolved via the 4-case resolver (resolve_target).
    """
    parser = argparse.ArgumentParser(
        prog="eval-praxion",
        description=(
            "Praxion eval harness — run quality checks against a pipeline corpus.\n\n"
            "TARGET can be: an existing filesystem path, a known worktree name, "
            "a git ref, or omitted (defaults to main HEAD)."
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help=("Eval target: filesystem path, worktree name, git ref, or omit for main HEAD."),
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for the eval report and log file (default: current directory).",
    )

    args = parser.parse_args(argv)

    try:
        resolved = resolve_target(args.target)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    # Run eval — fully wired composition: CorpusReader → JudgeClient → families → Report.
    try:
        report = run_eval(
            target=str(resolved),
            output_dir=args.output_dir,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Eval complete: {report.pass_count} PASS / "
        f"{report.warn_count} WARN / "
        f"{report.fail_count} FAIL"
    )
    if report.report_path:
        print(f"Report: {report.report_path}")


if __name__ == "__main__":
    main()
