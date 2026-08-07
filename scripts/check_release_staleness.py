#!/usr/bin/env python3
"""Report plugin artifacts present at HEAD but absent from the last release.

Praxion ships as a Claude Code plugin via an external marketplace manifest.
Claude Code serves only *published releases* (the marketplace `version` field is
a cache key tied to a git tag), so any agent / skill / command added after the
last `v*` tag is invisible to every installed copy until a new release is cut.
This is a silent failure: the source repo looks correct, `plugin.json` lists the
artifact, yet `claude plugin install` users never see it.

This diagnostic compares the artifact set registered at the last release tag
against the set at a target ref (default HEAD) and lists what is unreleased,
prompting the maintainer to cut a release. It does NOT change versions --
`cz bump` is the only mechanism that does that (see release.yml). It is a
release-staleness signal, not a per-commit version gate; firing on every feat
commit between releases would contradict the pinned-stable version model.

Artifact sources (mirroring `.claude-plugin/plugin.json`):
  - agents:   the explicit `agents` array in plugin.json
  - skills:   `skills/<name>/SKILL.md`
  - commands: `commands/<name>.md` (excluding README.md)

## Named consumer

This advisory is correct and deliberately non-blocking (see the rationale above) --
but a correct-and-advisory gate is only useful if something reads its output before
a human claim is made that the gate could contradict. The named reader is the
release cut (`commands/release.md`): before that process declares a release
complete, it runs this check for the tag being cut and records the verdict.

Nothing else is a substitute for that read. The failure mode this exists to catch:
a committed document asserting an artifact "MERGED ... NOT YET RELEASED" for an
artifact this check would report as *present* at the named tag -- i.e. the
document's claim is stale and this check's own output already contradicts it.
That is not hypothetical; it is the exact defect this diagnostic was written to
surface, once, before a named reader existed to keep it from recurring.

Invocation:

    check_release_staleness.py                 # compare HEAD vs latest v* tag
    check_release_staleness.py --base-ref v0.2.0
    check_release_staleness.py --head-ref <sha>
    check_release_staleness.py --json          # machine-readable
    check_release_staleness.py --check         # exit 1 when stale (opt-in CI)
    check_release_staleness.py --repo-root DIR # operate on another checkout (tests)

Exit code: 0 by default (advisory). With --check, 1 when unreleased artifacts
exist. Always 0 when no release tag exists or git is unavailable.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from _git_runner import git_output
from _script_cli import configure_logging

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"
RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+")
SKILL_PATH_RE = re.compile(r"^skills/([^/]+)/SKILL\.md$")
COMMAND_PATH_RE = re.compile(r"^commands/([^/]+)\.md$")
COMMAND_EXCLUDE = {"README"}

logger = logging.getLogger("check_release_staleness")


# -- Git helpers --------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str | None:
    """Run `git <args>` in repo_root; return stripped stdout, None on failure."""
    return git_output(repo_root, *args, logger=logger)


def latest_release_tag(repo_root: Path, ref: str = "HEAD") -> str | None:
    """Return the nearest `v*` release tag reachable from `ref`, or None.

    Uses `git describe` (topological nearest), not date sorting: tag creation
    dates collide for same-second commits, and "the last release on this
    history line" is what matters for staleness -- not the globally newest tag.
    """
    tag = _git(repo_root, "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", ref)
    if tag is not None and RELEASE_TAG_RE.match(tag):
        return tag
    return None


# -- Artifact extraction ------------------------------------------------------


def _file_at(repo_root: Path, ref: str, path: str) -> str | None:
    return _git(repo_root, "show", f"{ref}:{path}")


def agents_at(repo_root: Path, ref: str) -> set[str]:
    """Registered agent names (file stems) from plugin.json `agents` at ref."""
    blob = _file_at(repo_root, ref, PLUGIN_MANIFEST)
    if blob is None:
        return set()
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        logger.debug("plugin.json at %s did not parse", ref)
        return set()
    return {Path(entry).stem for entry in data.get("agents", [])}


def _tree_names(repo_root: Path, ref: str, prefix: str, pattern: re.Pattern[str]) -> set[str]:
    """Names captured by `pattern` over files under `prefix` at `ref`."""
    output = _git(repo_root, "ls-tree", "-r", "--name-only", ref, "--", prefix)
    if output is None:
        return set()
    names: set[str] = set()
    for line in output.splitlines():
        match = pattern.match(line.strip())
        if match:
            names.add(match.group(1))
    return names


def skills_at(repo_root: Path, ref: str) -> set[str]:
    return _tree_names(repo_root, ref, "skills/", SKILL_PATH_RE)


def commands_at(repo_root: Path, ref: str) -> set[str]:
    return _tree_names(repo_root, ref, "commands/", COMMAND_PATH_RE) - COMMAND_EXCLUDE


# -- Staleness computation ----------------------------------------------------


@dataclass
class Staleness:
    base_ref: str
    head_ref: str
    new_agents: list[str] = field(default_factory=list)
    new_skills: list[str] = field(default_factory=list)
    new_commands: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.new_agents) + len(self.new_skills) + len(self.new_commands)

    @property
    def is_stale(self) -> bool:
        return self.total > 0


def compute_staleness(repo_root: Path, base_ref: str, head_ref: str = "HEAD") -> Staleness:
    """Artifacts registered at head_ref but absent at base_ref."""
    return Staleness(
        base_ref=base_ref,
        head_ref=head_ref,
        new_agents=sorted(agents_at(repo_root, head_ref) - agents_at(repo_root, base_ref)),
        new_skills=sorted(skills_at(repo_root, head_ref) - skills_at(repo_root, base_ref)),
        new_commands=sorted(commands_at(repo_root, head_ref) - commands_at(repo_root, base_ref)),
    )


# -- Reporting ----------------------------------------------------------------


def _format_report(s: Staleness) -> str:
    if not s.is_stale:
        return (
            f"check_release_staleness: in sync -- no agents/skills/commands added "
            f"since {s.base_ref}."
        )
    lines = [
        "",
        "=" * 72,
        f"RELEASE STALENESS: {s.total} artifact(s) added since {s.base_ref} are unreleased.",
        "=" * 72,
        "Marketplace installs only see published releases, so these are invisible",
        f"to `claude plugin install` users until a new release is cut ({s.head_ref} state):",
        "",
    ]
    for label, items in (
        ("agents", s.new_agents),
        ("skills", s.new_skills),
        ("commands", s.new_commands),
    ):
        if items:
            lines.append(f"  {label} (+{len(items)}):")
            lines.extend(f"    - {name}" for name in items)
    lines.extend(
        [
            "",
            "Fix: cut a release (cz bump is the only version mechanism) --",
            "  gh workflow run release.yml --ref main",
            "then advertise the same version in the external marketplace manifest.",
            "See skills/versioning/SKILL.md.",
            "=" * 72,
            "",
        ]
    )
    return "\n".join(lines)


# -- Orchestration ------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_release_staleness",
        description=(
            "Advisory: list plugin artifacts added since the last release tag, "
            "invisible to marketplace installs until a release is cut."
        ),
        epilog=(
            "Named consumer: commands/release.md runs this check for the tag "
            "being cut and records its verdict before declaring a release "
            "complete -- see the module docstring's '## Named consumer' section."
        ),
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        metavar="REF",
        help="Release baseline (default: newest v* tag).",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        metavar="REF",
        help="Ref to inspect (default: HEAD).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: this checkout).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when unreleased artifacts exist (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _run(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    base_ref = args.base_ref or latest_release_tag(repo_root, args.head_ref)
    if base_ref is None:
        logger.info("check_release_staleness: no v* release tag found; nothing to compare")
        return 0

    staleness = compute_staleness(repo_root, base_ref, args.head_ref)

    if args.json:
        print(
            json.dumps(
                {
                    **asdict(staleness),
                    "total": staleness.total,
                    "is_stale": staleness.is_stale,
                },
                indent=2,
            )
        )
    else:
        report = _format_report(staleness)
        print(report, file=sys.stderr if staleness.is_stale else sys.stdout)

    return 1 if (args.check and staleness.is_stale) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_release_staleness: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
