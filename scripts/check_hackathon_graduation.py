#!/usr/bin/env python3
"""HK01: hackathon-mode graduation nudge when a project outgrows PoC size.

Hackathon mode is a deliberately lightweight tier -- see `CLAUDE.md`'s hackathon-mode
block -- and this check is its only feedback signal that a project has kept growing
past the size that tier was designed for. It never fails and never blocks; it only
advises.

Conditional (env-gated, not filesystem-substrate-gated): this check runs only when
`PRAXION_HACKATHON_MODE` is `"1"` in the project's `.claude/settings.json` `env`
block -- the same detection Claude Code itself uses to activate hackathon-mode
sessions (`skills/onboard-project/references/detection.md`). Every non-hackathon
project (including Praxion's own checkout, which carries no such entry) skips with
`skipped.HK01 = {"reason": "hackathon-mode-off"}` and never counts anything.

When active, it counts two signals across the working tree: non-test source files
(`.py`/`.rs`/`.ts`/`.tsx`, excluding any path with a `.git/` component or a path
component beginning with `test` -- the same exclusion `find ... -not -path "*/test*"
-not -path "*/.git/*"` applies) and total commit count (`git rev-list --count HEAD`).
Crossing either threshold (>40 source files OR >150 commits) emits a single advisory
`findings[]` entry naming both counts; below both, the project is clean. A
`git rev-list` failure (no commits yet, not a git checkout) counts as 0 rather than
crashing the check -- it degrades to judging on source-file count alone.

Invocation:

    check_hackathon_graduation.py                  # human-readable summary
    check_hackathon_graduation.py --json           # machine-readable envelope
    check_hackathon_graduation.py --check          # exit 1 on any finding
    check_hackathon_graduation.py --repo-root DIR  # operate on another checkout

Exit code: 0 by default (advisory), 1 with --check when the advisory fires.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_hackathon_graduation"

CHECK_IDS: tuple[str, ...] = ("HK01",)

_SETTINGS_REL = ".claude/settings.json"
_SOURCE_EXTENSIONS = (".py", ".rs", ".ts", ".tsx")
_TEST_PATH_PREFIX = "test"
_GIT_DIR_NAME = ".git"

# Thresholds from the row's own recipe (`agents/sentinel.md` § Hackathon Mode
# Graduation) -- fixed constants the row names in prose, not derived from any file.
_SOURCE_FILE_THRESHOLD = 40
_COMMIT_THRESHOLD = 150

logger = logging.getLogger(SCRIPT_NAME)


def _hackathon_mode_enabled(repo_root: Path) -> bool:
    """`.claude/settings.json`'s `env.PRAXION_HACKATHON_MODE == "1"` -- the row's own gate.

    Mirrors the fallback branch of `skills/onboard-project/references/detection.md`'s
    row 2 rather than reading `os.environ`: the settings file is the durable record of
    whether a project *is* a hackathon-mode project, independent of whatever
    environment the check happens to run under.
    """
    settings_path = repo_root / _SETTINGS_REL
    if not settings_path.is_file():
        return False
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    env = data.get("env")
    if not isinstance(env, dict):
        return False
    return env.get("PRAXION_HACKATHON_MODE") == "1"


def _is_test_path(rel_parts: tuple[str, ...]) -> bool:
    """Mirrors `find -not -path "*/test*"`: any path component starting with 'test'."""
    return any(part.startswith(_TEST_PATH_PREFIX) for part in rel_parts)


def _count_source_files(repo_root: Path) -> int:
    """Non-test `.py`/`.rs`/`.ts`/`.tsx` files, excluding `.git/` -- the row's `find` recipe."""
    count = 0
    for ext in _SOURCE_EXTENSIONS:
        for path in repo_root.rglob(f"*{ext}"):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(repo_root).parts
            if _GIT_DIR_NAME in rel_parts or _is_test_path(rel_parts):
                continue
            count += 1
    return count


def _count_commits(repo_root: Path) -> int:
    """`git rev-list --count HEAD`; 0 when unresolvable (no HEAD, not a git repo)."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
    except FileNotFoundError:
        return 0
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _skipped_report() -> dict:
    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": {"HK01": {"reason": "hackathon-mode-off"}},
        "examined": {"HK01": None},
        "findings": [],
        "info": {},
        "withheld": [],
        "bound": {"HK01": "HK01 did not run; hackathon mode is off for this project."},
    }


def classify(repo_root: Path) -> dict:
    """Build the HK01 envelope: an advisory when a hackathon-mode project outgrows PoC size."""
    if not _hackathon_mode_enabled(repo_root):
        return _skipped_report()

    source_files = _count_source_files(repo_root)
    commits = _count_commits(repo_root)

    findings: list[dict] = []
    if source_files > _SOURCE_FILE_THRESHOLD or commits > _COMMIT_THRESHOLD:
        findings.append(
            {
                "check": "HK01",
                "severity": "info",
                "entity": str(repo_root),
                "message": (
                    "This project is in hackathon mode and has outgrown typical PoC size "
                    f"(source files: {source_files}, commits: {commits}). Consider "
                    "graduating to full 5-tier ceremony -- see the `### To exit hackathon "
                    "mode` section in `CLAUDE.md`."
                ),
            }
        )

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": {"HK01": None},
        "examined": {"HK01": {"source_files": source_files, "commits": commits}},
        "findings": findings,
        "info": {},
        "withheld": [],
        "bound": {
            "HK01": (
                "HK01 clean means source files <= "
                f"{_SOURCE_FILE_THRESHOLD} and commits <= {_COMMIT_THRESHOLD} "
                "(or hackathon mode is off)."
            )
        },
    }


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: nudge a hackathon-mode project that has outgrown PoC size toward "
            "graduating to the full 5-tier ceremony. Called by sentinel HK01."
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
        if report["skipped"]["HK01"] is not None:
            return f"{SCRIPT_NAME}: skipped ({report['skipped']['HK01']['reason']})."
        return f"{SCRIPT_NAME}: no graduation advisory."
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
