"""Argparse orchestration for the managed-project -> Praxion feedback reporter.

Thin wiring over the pure `scripts/praxion_feedback/` modules: `capture`
sanitizes-at-capture, scope-filters, fingerprints, and appends a candidate;
`list` enumerates un-filed candidates; `render` projects the fixed §5.2 body;
`mark-filed` flips a candidate out of the pending set. No business logic lives
here -- every rule (fingerprint/dedup, sanitizer, scope filter, body schema)
belongs to its own module and is reused, not reimplemented.

Repo-root resolution is the load-bearing safety property: the script runs from
an installed-plugin cache, so it resolves the *consumer* project root via
`--repo-root` or `git rev-parse --show-toplevel` (both from `_repo_root`),
**never** from this file's own `__file__` location -- resolving via `__file__`
would silently write the git-committed ledger into the shared plugin cache.
Filing (`gh`) and the human gate deliberately live in the command layer, not
here, so this module stays pure, offline, and unit-testable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts._repo_root import git_toplevel_from_cwd, is_plugin_cache_path
from scripts.praxion_feedback.candidate_store import (
    append_candidate,
    list_pending,
    mark_filed,
)
from scripts.praxion_feedback.render import render_candidate
from scripts.praxion_feedback.sanitizer import is_shipped_artifact_path, sanitize_text

__all__ = ["main"]

# ---------------------------------------------------------------------------
# Constants -- paths, subcommand vocabulary, field ordering.
# ---------------------------------------------------------------------------

_AI_STATE_DIRNAME = ".ai-state"
_FEEDBACK_SUBDIR = "praxion_feedback"
_PENDING_BASENAME = "PENDING.md"
_UPSTREAM_BASENAME = "UPSTREAM_ISSUES.md"

_CATEGORY_CHOICES = ("hooks", "blocks", "agents", "scripts", "skills")
_SHORT_FINGERPRINT_LEN = 8

# The `capture` candidate fields, in the order the store expects. Each name is
# also the argparse `dest`, so `getattr(args, key)` reads the flag value
# directly (e.g. `--artifact` sets `dest="artifact_path"`).
_CAPTURE_FIELD_KEYS = (
    "category",
    "artifact_path",
    "error",
    "detected_by",
    "detection_point",
    "confidence",
    "expected",
    "observed",
    "reproduction_command",
    "environment",
    "regression_status",
)


class _RepoRootError(RuntimeError):
    """Raised when the consumer repo root cannot be safely resolved."""


# ---------------------------------------------------------------------------
# Repo-root resolution -- git / --repo-root, never __file__.
# ---------------------------------------------------------------------------


def _resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the consumer repo root: explicit `--repo-root` > git-root.

    Never falls back to this script's own location -- a plugin-cache install
    would otherwise write the git-committed ledger into shared plugin state.
    Refuses outright when git resolution fails (cwd is not a working tree) or
    when the resolved root looks like a plugin-cache path.
    """
    if cli_repo_root:
        root = Path(cli_repo_root).resolve()
    else:
        git_root = git_toplevel_from_cwd()
        if git_root is None:
            raise _RepoRootError(
                "cannot resolve the repo root: not inside a git working tree "
                "(run from within the target repository, or pass --repo-root)"
            )
        root = git_root.resolve()
    if is_plugin_cache_path(root):
        raise _RepoRootError(
            f"refusing to operate on a plugin-cache path ({root}); "
            "the repo root must be a consumer checkout"
        )
    return root


def _pending_path(repo_root: Path) -> Path:
    return repo_root / _AI_STATE_DIRNAME / _FEEDBACK_SUBDIR / _PENDING_BASENAME


def _upstream_path(repo_root: Path) -> Path:
    return repo_root / _AI_STATE_DIRNAME / _FEEDBACK_SUBDIR / _UPSTREAM_BASENAME


# ---------------------------------------------------------------------------
# Subcommand handlers.
# ---------------------------------------------------------------------------


def _cmd_capture(args: argparse.Namespace, pending: Path, upstream: Path) -> int:
    """Scope-filter, sanitize-at-capture, fingerprint, and append a candidate."""
    raw_fields = {key: getattr(args, key) for key in _CAPTURE_FIELD_KEYS}
    if not is_shipped_artifact_path(raw_fields["artifact_path"], raw_fields["category"]):
        print(
            f"error: artifact {raw_fields['artifact_path']!r} is not a shipped "
            f"{raw_fields['category']!r} artifact; only shipped Praxion "
            "artifacts enter the sidecar",
            file=sys.stderr,
        )
        return 1
    sanitized_fields = {key: sanitize_text(value) for key, value in raw_fields.items()}
    pending.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = append_candidate(pending, upstream, sanitized_fields)
    if fingerprint is None:
        print("candidate already captured; skipping (dedup no-op)", file=sys.stderr)
        return 0
    print(fingerprint)
    return 0


def _cmd_list(pending: Path) -> int:
    """Print each still-pending candidate's short fingerprint and location."""
    candidates = list_pending(pending)
    if not candidates:
        print("No pending candidates.", file=sys.stderr)
        return 0
    for candidate in candidates:
        short = candidate.get("fingerprint", "")[:_SHORT_FINGERPRINT_LEN]
        category = candidate.get("category", "")
        artifact = candidate.get("artifact_path", "")
        print(f"{short}  [{category}] {artifact}")
    return 0


def _cmd_render(args: argparse.Namespace, pending: Path) -> int:
    """Project a pending candidate into the fixed §5.2 markdown body."""
    candidate = _find_pending_candidate(pending, args.fingerprint)
    if candidate is None:
        print(
            f"error: no pending candidate with fingerprint {args.fingerprint!r}",
            file=sys.stderr,
        )
        return 1
    body = render_candidate(candidate)
    if args.body_file:
        body_path = Path(args.body_file)
        body_path.write_text(body)
        print(str(body_path))
        return 0
    print(body)
    return 0


def _cmd_mark_filed(args: argparse.Namespace, pending: Path) -> int:
    """Flip a candidate to `filed` and record its issue URL."""
    mark_filed(pending, args.fingerprint, args.issue_url)
    return 0


def _find_pending_candidate(pending: Path, fingerprint: str) -> dict | None:
    for candidate in list_pending(pending):
        if candidate.get("fingerprint") == fingerprint:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Argument parsing.
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Construct the reporter's argument parser with its four subcommands."""
    parser = argparse.ArgumentParser(
        prog="report-praxion-issue",
        description=(
            "Capture, list, render, and mark-filed managed-project defect "
            "candidates in a shipped Praxion artifact. Pure and offline -- "
            "filing (gh) and the human gate live in /report-praxion-issue."
        ),
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--repo-root",
        dest="repo_root",
        default=None,
        help="Consumer repo root; defaults to `git rev-parse --show-toplevel` from cwd.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_capture_parser(subparsers, common)
    subparsers.add_parser("list", parents=[common], help="List still-pending candidates.")
    _add_render_parser(subparsers, common)
    _add_mark_filed_parser(subparsers, common)
    return parser


def _add_capture_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    capture = subparsers.add_parser(
        "capture",
        parents=[common],
        help="Sanitize, fingerprint, and append a candidate to PENDING.md.",
    )
    capture.add_argument("--category", choices=_CATEGORY_CHOICES, required=True)
    capture.add_argument("--artifact", dest="artifact_path", required=True)
    capture.add_argument("--error", required=True)
    capture.add_argument("--detected-by", dest="detected_by", required=True)
    capture.add_argument("--detection-point", dest="detection_point", required=True)
    capture.add_argument("--confidence", required=True)
    capture.add_argument("--expected", required=True)
    capture.add_argument("--observed", required=True)
    capture.add_argument("--reproduction-command", dest="reproduction_command", required=True)
    capture.add_argument("--environment", required=True)
    capture.add_argument("--regression-status", dest="regression_status", required=True)


def _add_render_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    render = subparsers.add_parser(
        "render",
        parents=[common],
        help="Render a candidate's §5.2 markdown body to stdout or --body-file.",
    )
    render.add_argument("--fingerprint", required=True)
    render.add_argument("--body-file", dest="body_file", default=None)


def _add_mark_filed_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
) -> None:
    filed = subparsers.add_parser(
        "mark-filed",
        parents=[common],
        help="Flip a candidate to `filed` with its issue URL.",
    )
    filed.add_argument("--fingerprint", required=True)
    filed.add_argument("--issue-url", dest="issue_url", required=True)


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse `argv`, resolve the repo root, and dispatch to a subcommand."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        repo_root = _resolve_repo_root(args.repo_root)
    except _RepoRootError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    pending = _pending_path(repo_root)
    upstream = _upstream_path(repo_root)

    if args.command == "capture":
        return _cmd_capture(args, pending, upstream)
    if args.command == "list":
        return _cmd_list(pending)
    if args.command == "render":
        return _cmd_render(args, pending)
    if args.command == "mark-filed":
        return _cmd_mark_filed(args, pending)
    # Unreachable: argparse `required=True` subparsers reject an unknown command.
    parser.error(f"unknown command: {args.command}")  # pragma: no cover
    return 2
