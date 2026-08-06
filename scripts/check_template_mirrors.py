#!/usr/bin/env python3
"""Keep a shipped template byte-identical to the in-repo file it mirrors.

Some files under ``claude/aac-templates/`` are copied *verbatim* into a managed
project by ``/onboard-project``, and Praxion carries its own copy of the same
file as the dogfooding instance of that install.  The two are a **mirror pair**:
the in-repo copy is the one this repo actually exercises, the template is the
one every managed project receives, and nothing but a gate keeps them equal.

This is the same defect class ``sync_canonical_blocks.py`` guards for canonical
blocks, on a different surface -- so the two are deliberate siblings: same
``--check`` / ``--write`` shape, same exit codes, same message style.  Hardening
one and silently not hardening the other is exactly how a shipped block drifted
into three variants across four sites, undetected, because no check covered it.

Not every template is a mirror.  ``fitness-README.md.tmpl``,
``fitness-import-linter.cfg.tmpl``, ``fitness-test-starter.py.tmpl`` and
``fitness-test-meta-citation.py.tmpl`` are *starters* -- a project is expected to
grow past them, and this repo's copies already have.  Asserting those identical
would be false, and would make the gate fire on correct work.  ``MIRRORS`` is
therefore an explicit registry, not a directory scan: membership is a contract
about which pairs must not diverge, and the burden of proof is on adding a row.

**Direction is asymmetric and deliberate.**  ``--write`` copies *source ->
template*, never the reverse.  The source is the copy this repo imports and runs
(pytest loads ``fitness/tests/conftest.py`` on every fitness run); the template
is inert text nothing here executes.  Propagating the exercised copy outward
publishes something proven; propagating the template inward would overwrite a
live fixture the fitness suite depends on with text no test has ever run.  When
the intended change really is to the shipped side, make it in the source and
re-run ``--write``.

There is no ``--dry-run``: unlike the canonical-block sibling -- which rewrites
fenced regions *inside* larger files, where previewing the touched set is
genuinely informative -- ``--write`` here copies whole files, so ``--check``
already prints strictly more than a dry run could (the full diff, per pair).

Two invocation modes:

    check_template_mirrors.py            # --check (default)
    check_template_mirrors.py --check    # exit 0 if in sync, else 1
    check_template_mirrors.py --write    # rewrite each template from its source

Exit codes:
    0  -- every mirror pair is identical (--check), or all rewrites succeeded (--write)
    1  -- drift detected (--check)
    2  -- script error (a registered mirror file is missing or unreadable)

Usage:
    python3 scripts/check_template_mirrors.py [--check | --write] [--repo-root PATH]
"""

from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

# The pre-commit hook whose `files:` pattern must cover every path below.
# Named here so the wiring test can find the hook it is asserting about without
# a second hardcoded string in the test file.
HOOK_ID = "template-mirror-sync"


@dataclass(frozen=True)
class Mirror:
    """A shipped template and the in-repo file it must stay byte-identical to.

    Paths are repo-root-relative so the registry survives being pointed at a
    fixture tree via ``--repo-root``.
    """

    source: str  # the copy this repo exercises -- the authority
    template: str  # the copy shipped into managed projects -- the derivative
    installed_by: str  # which onboarding step copies it, for the drift message


# Mirror registry. Add a row only when a template is installed *verbatim* (no
# placeholder substitution) AND this repo carries the installed counterpart --
# both halves matter: `architecture.yml.tmpl` fails the first, the fitness
# starters fail the second.
MIRRORS: tuple[Mirror, ...] = (
    Mirror(
        source="fitness/tests/conftest.py",
        template="claude/aac-templates/fitness-conftest.py.tmpl",
        installed_by="/onboard-project Phase 8b.2",
    ),
)


class MirrorDrift(NamedTuple):
    """One diverged pair, with the diff that shows how."""

    mirror: Mirror
    diff: list[str]


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------


def _error(message: str) -> None:
    """Print a script-error message and exit 2."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def _read(path: Path, role: str) -> str:
    """Read a registered mirror file, or exit 2 naming which half is missing.

    A missing file is a script error rather than drift: the registry is a
    contract asserting both halves exist, so an absent one means the contract
    broke (a template was un-shipped, a source moved) -- a louder problem than
    two files disagreeing, and one `--write` must not paper over.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _error(f"{role} not found: {path}")
    except OSError as exc:
        _error(f"cannot read {role} {path}: {exc}")
    return ""  # unreachable: _error exits


# ---------------------------------------------------------------------------
# Check / write
# ---------------------------------------------------------------------------


def check_mirrors(repo_root: Path = REPO_ROOT) -> list[MirrorDrift]:
    """Return one MirrorDrift per diverged pair; empty list means all in sync."""
    drifted: list[MirrorDrift] = []

    for mirror in MIRRORS:
        source_body = _read(repo_root / mirror.source, "mirror source")
        template_body = _read(repo_root / mirror.template, "mirror template")
        if source_body == template_body:
            continue

        diff = list(
            difflib.unified_diff(
                source_body.splitlines(keepends=True),
                template_body.splitlines(keepends=True),
                fromfile=mirror.source,
                tofile=mirror.template,
            )
        )
        drifted.append(MirrorDrift(mirror=mirror, diff=diff))

    return drifted


def write_mirrors(repo_root: Path = REPO_ROOT) -> list[Mirror]:
    """Rewrite each drifted template from its source. Returns the pairs updated."""
    updated: list[Mirror] = []

    for mirror in MIRRORS:
        source_path = repo_root / mirror.source
        template_path = repo_root / mirror.template
        source_body = _read(source_path, "mirror source")
        # Read the template too, so an absent one is the same loud error in
        # --write as it is in --check rather than being silently recreated.
        if _read(template_path, "mirror template") == source_body:
            continue

        try:
            template_path.write_text(source_body, encoding="utf-8")
        except OSError as exc:
            _error(f"cannot write mirror template {template_path}: {exc}")
        updated.append(mirror)

    return updated


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def _remediation_hint() -> str:
    """Build a remediation hint listing every template the fix would rewrite."""
    templates = " ".join(mirror.template for mirror in MIRRORS)
    return (
        "  Fix:  python3 scripts/check_template_mirrors.py --write\n"
        f"        git add {templates}\n"
        "  (--write copies source -> template; put the intended change in the "
        "source, not the template.)"
    )


def run_check(repo_root: Path) -> int:
    """--check mode: report drift and exit 1 if any found."""
    drifted = check_mirrors(repo_root)

    for mirror, diff_lines in drifted:
        print(f"\ndrift detected in {mirror.template}:")
        print(f"  mirror of {mirror.source} (installed by {mirror.installed_by}):")
        for diff_line in diff_lines:
            print("    " + diff_line, end="")
    if drifted:
        print()
        print("template-mirror sync check failed.")
        print(_remediation_hint())
        return 1

    print(f"checked {len(MIRRORS)} mirror pair(s); all in sync.")
    return 0


def run_write(repo_root: Path) -> int:
    """--write mode: rewrite drifted templates from their sources."""
    updated = write_mirrors(repo_root)

    for mirror in updated:
        print(f"updated {mirror.template} from {mirror.source}")
    if not updated:
        print("all mirror pairs already in sync; no changes written.")

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Check for drift and exit 1 if any found (default mode).",
    )
    mode_group.add_argument(
        "--write",
        action="store_true",
        default=False,
        help="Rewrite each shipped template from its in-repo source.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to resolve mirror paths against (default: this script's repo).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    repo_root = args.repo_root.resolve()
    if args.write:
        return run_write(repo_root)
    # Default to --check
    return run_check(repo_root)


if __name__ == "__main__":
    sys.exit(main())
