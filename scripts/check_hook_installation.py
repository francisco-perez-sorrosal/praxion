#!/usr/bin/env python3
"""F10: git hook source matches installed copy(ies), resolved by content.

`scripts/git-<name>-hook.sh` files are the source of truth for Praxion's git
hooks; `install_claude.sh` symlinks (or copies) them into `.git/hooks/<hook>`.
A source script can be **multiplexed** -- one script installed under several
hook names at once (`git-finalize-hook.sh` under `post-merge`, `post-commit`
*and* `post-checkout`) -- so **filename derivation is unsound**: a naive
`git-<name>-hook.sh` -> `.git/hooks/<name>` mapping has no single target for
a multiplexed source and reports false MISSINGs for every correctly-installed
copy.

This check resolves installed counterparts **by content instead**: every
`.git/hooks/*` entry (symlink-aware -- read through the link, so a dangling
symlink is simply unreadable, not a crash) is byte-compared against every
`scripts/git-*-hook.sh` source. A source is "installed" the moment *any*
hook file matches its bytes exactly, under however many names.

Two WARN shapes, in order of preference:

* a hook file exists at the source's **naively-derived** single-name location
  (`git-<name>-hook.sh` -> `<name>`) but its content differs from the source
  -- the installer needs to re-run to pick up a source edit;
* otherwise, no installed hook matches the source's content at all, and the
  source is executable -- it looks like it was never installed.

A non-executable source with no naive-name hook present raises nothing: it is
not meant to be installed standalone (e.g. a helper sourced by another hook).

Conditional: skip (all findings withheld) when `.git/hooks` cannot be
resolved (`git rev-parse --git-path hooks` fails, or the reported path is not
a directory) -- covers a non-git checkout and the plugin-cache path alike.
Zero `scripts/git-*-hook.sh` sources is not a skip: the walk simply examines
zero sources and reports no findings, the same way `check_staleness_markers`
reports an empty walk over a `skills/` dir with no cataloged sections.

Invocation:

    check_hook_installation.py                  # human-readable summary
    check_hook_installation.py --json           # machine-readable envelope
    check_hook_installation.py --check          # exit 1 on any finding
    check_hook_installation.py --repo-root DIR  # operate on another checkout

Exit code: 0 by default (advisory), 1 with --check when findings exist.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_hook_installation"

CHECK_IDS: tuple[str, ...] = ("F10",)

_SOURCE_PREFIX = "git-"
_SOURCE_SUFFIX = "-hook"

logger = logging.getLogger(SCRIPT_NAME)


def _resolve_hooks_dir(repo_root: Path) -> Path | None:
    """Return the git common hooks dir, or None if it cannot be resolved.

    Uses `git rev-parse --git-path hooks` run with `cwd=repo_root` -- `hooks`
    is one of the paths git always resolves against the *common* git dir, so
    this returns the shared hooks directory even when `repo_root` is itself a
    worktree (whose own `.git` is a file, not a directory).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    hooks_dir = Path(result.stdout.strip())
    if not hooks_dir.is_absolute():
        hooks_dir = repo_root / hooks_dir
    return hooks_dir if hooks_dir.is_dir() else None


def _read_bytes_or_none(path: Path) -> bytes | None:
    """Read `path`'s bytes, resolving a symlink; None if unreadable (e.g. dangling)."""
    try:
        return path.read_bytes()
    except OSError:
        return None


def _installed_hooks(hooks_dir: Path) -> dict[str, bytes]:
    """Map hook name -> content for every readable, non-`.sample` hooks/ entry."""
    installed: dict[str, bytes] = {}
    for entry in sorted(hooks_dir.iterdir()):
        if entry.name.endswith(".sample") or not entry.is_file():
            continue
        content = _read_bytes_or_none(entry)
        if content is not None:
            installed[entry.name] = content
    return installed


def _derived_hook_name(source_name: str) -> str | None:
    """Naive `git-<name>-hook.sh` -> `<name>` derivation; None if the shape doesn't match."""
    stem = source_name[: -len(".sh")] if source_name.endswith(".sh") else source_name
    if not (stem.startswith(_SOURCE_PREFIX) and stem.endswith(_SOURCE_SUFFIX)):
        return None
    return stem[len(_SOURCE_PREFIX) : -len(_SOURCE_SUFFIX)]


def classify(repo_root: Path) -> dict:
    """Build the F10 envelope: every `git-*-hook.sh` source vs. installed hooks by content."""
    hooks_dir = _resolve_hooks_dir(repo_root)
    if hooks_dir is None:
        return _skipped_report("substrate-absent", str(repo_root / ".git" / "hooks"))

    installed = _installed_hooks(hooks_dir)
    sources = sorted((repo_root / "scripts").glob(f"{_SOURCE_PREFIX}*-hook.sh"))

    findings: list[dict] = []
    for source in sources:
        source_bytes = _read_bytes_or_none(source)
        if source_bytes is None:
            continue  # unreadable source -- nothing to compare
        matched_names = [name for name, content in installed.items() if content == source_bytes]
        if matched_names:
            continue  # installed under >=1 name (possibly multiplexed) -- PASS

        derived = _derived_hook_name(source.name)
        if derived is not None and derived in installed:
            findings.append(
                {
                    "check": "F10",
                    "severity": "warn",
                    "entity": f"scripts/{source.name}",
                    "message": (
                        f"scripts/{source.name}: installed hook '.git/hooks/{derived}' "
                        "differs from source -- run install_claude.sh (or --hooks-only) "
                        "to refresh it"
                    ),
                }
            )
        elif os.access(source, os.X_OK):
            findings.append(
                {
                    "check": "F10",
                    "severity": "warn",
                    "entity": f"scripts/{source.name}",
                    "message": (
                        f"scripts/{source.name}: matches no installed hook and is "
                        "executable -- run install_claude.sh (or --hooks-only) to install it"
                    ),
                }
            )

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": {"F10": None},
        "examined": {"F10": {"sources": len(sources)}},
        "findings": findings,
        "info": {},
        "withheld": [],
        "bound": {"F10": "F10 clean means every git hook source is installed under >=1 name."},
    }


def _skipped_report(reason: str, path: str) -> dict:
    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": {"F10": {"reason": reason, "path": path}},
        "examined": {"F10": None},
        "findings": [],
        "info": {},
        "withheld": [],
        "bound": {"F10": "F10 did not run; no hook-installation conclusion can be drawn."},
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: flag a git hook source whose installed counterpart is missing "
            "or stale, resolved by content (not filename). Called by sentinel F10."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(report: dict) -> str:
    findings = report["findings"]
    if not findings:
        sources = report["examined"]["F10"]["sources"] if report["examined"]["F10"] else 0
        return f"{SCRIPT_NAME}: no hook-installation violations across {sources} source(s)."
    lines = [f"{SCRIPT_NAME}: {len(findings)} finding(s):"]
    lines.extend(f"  - [{f['check']}/{f['severity']}] {f['message']}" for f in findings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = _format_human(report)
        print(text, file=sys.stderr if report["findings"] else sys.stdout)

    return 1 if (args.check and report["findings"]) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("%s: %s", SCRIPT_NAME, exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
