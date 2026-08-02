#!/usr/bin/env python3
"""Assert the ruff a commit is formatted BY matches the ruff a developer runs.

Two independently-versioned ruffs formatting the same files never converge.
The pre-commit hook rewrites a file on commit; the developer's own ruff rewrites
it back; `git add` never captures a stable state and the commit loop does not
settle -- because each side is correct by its own configuration. Worse, while
that loop spins, pre-commit stashes and restores unstaged changes on every
attempt, and a restore landing on top of a hook's rewrite has silently reverted
completed work in this repository.

The defect is not a stale pin. A stale pin drifts once. The defect is an
UNPINNED local side: with no declared version, the hook fights a different
opponent on every machine, and the disagreement is invisible until a commit
refuses to settle.

This check makes the two sides one decision. It compares, and requires equality
between:

  1. the `rev:` pinned on the `ruff-pre-commit` repo in `.pre-commit-config.yaml`
     -- the ruff that formats a commit, and
  2. the `ruff==<version>` declared in `pyproject.toml`'s dependency group
     -- the ruff a developer's environment installs.

The installed ruff is compared too, resolved project-environment-first
(`.venv/bin/ruff`) and only then from PATH -- see `resolve_local_ruff`. That
order matters: in a uv-managed project the ruff a developer runs is the one the
project provides, and comparing against an unrelated global binary would fail
someone doing everything right.

Absent inputs are never drift. A repository with no ruff hook, or one that has
not adopted the dependency pin, is out of scope rather than broken -- this
ships to managed projects whose stacks differ.

Exit codes: 0 equal (or nothing to compare), 1 drift, 2 script error.

Usage:
    python3 scripts/check_ruff_pin_drift.py
    python3 scripts/check_ruff_pin_drift.py --repo-root PATH
    python3 scripts/check_ruff_pin_drift.py --skip-path-check   # config-only
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

PRECOMMIT_CONFIG = ".pre-commit-config.yaml"
PYPROJECT = "pyproject.toml"

# `- repo: https://github.com/astral-sh/ruff-pre-commit` followed, within the
# same block, by `rev: vX.Y.Z`. Matched textually rather than via a YAML parse so
# the check stays stdlib-only and runs in a bare pre-commit environment.
_RUFF_REPO_REV_RE = re.compile(
    r"-\s*repo:\s*\S*ruff-pre-commit\s*\n(?:\s*#.*\n)*\s*rev:\s*v?(?P<version>[0-9][^\s#]*)",
    re.MULTILINE,
)
_RUFF_DEP_RE = re.compile(r"""["']ruff==(?P<version>[0-9][^"']*)["']""")
_RUFF_VERSION_OUT_RE = re.compile(r"ruff\s+(?P<version>[0-9][^\s]*)")


def pinned_hook_version(config_text: str) -> str | None:
    """The ruff version `.pre-commit-config.yaml` pins, or None if ruff is absent."""
    match = _RUFF_REPO_REV_RE.search(config_text)
    return match.group("version") if match else None


def declared_dep_version(pyproject_text: str) -> str | None:
    """The exact ruff version pyproject declares, or None if it declares none.

    Only an `==` pin counts. A floating constraint (`>=`, `~=`, bare `ruff`) is
    deliberately read as "no pin", because it cannot guarantee the equality this
    check exists to enforce -- reporting it as a match would be a false clear.
    """
    match = _RUFF_DEP_RE.search(pyproject_text)
    return match.group("version") if match else None


def _version_of(executable: str) -> str | None:
    """Run `<executable> --version` and parse it; None if unusable."""
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, check=False, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    match = _RUFF_VERSION_OUT_RE.search(result.stdout.strip())
    return match.group("version") if match else None


def resolve_local_ruff(root: Path) -> tuple[str, str] | None:
    """The ruff this project actually runs, as `(version, source)`.

    Resolution order is deliberate: a project-managed interpreter FIRST, PATH
    only as a fallback.

    In a uv- or venv-managed project the ruff a developer invokes is the one in
    the project environment (`uv run ruff`), not whatever global binary happens
    to sit on PATH. Comparing against PATH first would fail a developer who is
    doing everything correctly and merely has an unrelated global ruff
    installed. A gate that punishes correct behaviour is worse than no gate --
    it teaches people to bypass it, and a bypassed gate protects nothing.

    PATH still matters when the project manages no ruff of its own: then the
    global binary IS the one that will fight the hook.
    """
    for relative in (".venv/bin/ruff", ".venv/Scripts/ruff.exe"):
        candidate = root / relative
        if candidate.is_file():
            version = _version_of(str(candidate))
            if version is not None:
                return version, relative
    on_path = shutil.which("ruff")
    if on_path is None:
        return None
    version = _version_of(on_path)
    return (version, "PATH") if version is not None else None


def find_drift(config_text: str, pyproject_text: str, local: tuple[str, str] | None) -> list[str]:
    """Return one message per disagreement; empty when the pins agree.

    Absent inputs are NOT drift. A project with no ruff hook, or one that has not
    adopted the dependency pin, is out of scope rather than broken -- this ships
    to managed projects whose stacks differ, and a check that fails on a
    non-Python repository would be noise, not a gate.
    """
    hook = pinned_hook_version(config_text)
    declared = declared_dep_version(pyproject_text)
    if hook is None:
        return []

    findings: list[str] = []
    if declared is not None and declared != hook:
        findings.append(
            f"{PRECOMMIT_CONFIG} pins ruff v{hook} but {PYPROJECT} declares "
            f"ruff=={declared}. The hook and the environment would format "
            f"differently and never converge."
        )
    if local is not None and local[0] != hook:
        local_version, source = local
        findings.append(
            f"{PRECOMMIT_CONFIG} pins ruff v{hook} but the ruff this project "
            f"runs ({source}) is {local_version}. A file formatted by hand "
            f"would be reformatted on commit, and back again."
        )
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--skip-path-check",
        action="store_true",
        help="Compare only the declared pins; ignore the installed ruff.",
    )
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()

    config_path = root / PRECOMMIT_CONFIG
    pyproject_path = root / PYPROJECT
    if not config_path.is_file():
        print(f"check_ruff_pin_drift: no {PRECOMMIT_CONFIG} — nothing to compare.")
        return 0

    try:
        config_text = config_path.read_text(encoding="utf-8")
        pyproject_text = (
            pyproject_path.read_text(encoding="utf-8") if pyproject_path.is_file() else ""
        )
    except OSError as exc:
        print(f"error: cannot read pin sources: {exc}", file=sys.stderr)
        return 2

    local = None if args.skip_path_check else resolve_local_ruff(root)
    findings = find_drift(config_text, pyproject_text, local)

    if not findings:
        hook = pinned_hook_version(config_text)
        print(f"check_ruff_pin_drift: ruff pins agree{f' (v{hook})' if hook else ''}.")
        return 0

    print("ruff pin drift — formatting will not converge:\n")
    for finding in findings:
        print(f"  - {finding}")
    print("")
    print("Fix: align every pin to ONE version, then reinstall.")
    print(f"  {PYPROJECT}          ruff==<version>   (exact, not >=)")
    print(f"  {PRECOMMIT_CONFIG}   rev: v<version>")
    print("  then: uv sync   (or pip install 'ruff==<version>')")
    print("")
    print("Why this blocks: a formatter disagreement does not surface as a lint")
    print("error. It surfaces as a commit that will not settle, and pre-commit's")
    print("stash/restore around each failed attempt can silently revert work.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
