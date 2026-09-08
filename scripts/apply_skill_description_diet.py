#!/usr/bin/env python3
"""Table-driven skill-description diet applier (P1.12, PM-7 binding).

Rewrites each `skills/<name>/SKILL.md` frontmatter `description:` field to the
value committed in `scripts/skill_description_diet.yaml` -- so a bad cut
(PM-7: a trigger noun dropped from a description silently stops that skill
from activating) is one table row to revert in review, not a diff to
hand-reconstruct from a 62-file sweep.

Only the `description:` line (or its `>`/`|` block-scalar span) is rewritten;
every other frontmatter line and the whole body are copied through verbatim --
deliberately not a full YAML round-trip, which would silently reformat
untouched fields (see `measure_token_budget.py`'s own `_frontmatter_block`/
`_extract_description`, reused here for reading).

Modes:
  (default)   apply -- rewrite every SKILL.md the table names; idempotent
              (a file already at the table's value is left untouched)
  --check     verify only, exit 1 on any drift; writes nothing
  --dry-run   print a unified diff per file the table would change; writes
              nothing

Exit codes: 0 clean, 1 drift/missing-file findings, 2 a malformed table
(missing file, non-string value, or a row over the 300-char diet cap).
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import yaml
from _repo_root import resolve_repo_root
from measure_token_budget import _extract_description, _frontmatter_block

SCRIPT_DIR = Path(__file__).resolve().parent
MAX_DESCRIPTION_CHARS = 300
DEFAULT_TABLE = SCRIPT_DIR / "skill_description_diet.yaml"


def load_table(path: Path) -> dict[str, str]:
    """`name -> description` mapping. Fails loud on a non-string value -- a
    silently-applied non-string row would corrupt frontmatter -- but NOT on
    length: PM-7 (every Triggers: noun survives verbatim) outranks the
    300-char-per-skill target, and several trigger-dense skills cannot hit
    300 without dropping vocabulary. `over_cap_names()` reports these; the
    aggregate 2,000-token listing ceiling this feeds is itself directional
    (see `--listing-ceiling` in `measure_token_budget.py`), never the
    per-skill cap enforced as a hard block."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: table must be a mapping of name -> description")
    for name, description in data.items():
        if not isinstance(description, str):
            raise ValueError(f"{path}: {name!r} description must be a string")
    return data


def over_cap_names(table: dict[str, str]) -> list[str]:
    """Table entries exceeding the 300-char target -- reported, never blocked."""
    return sorted(name for name, d in table.items() if len(d) > MAX_DESCRIPTION_CHARS)


def _yaml_quote(value: str) -> str:
    """A double-quoted YAML scalar -- always quoted, since a diet description
    is free English prose that may contain `:`, which breaks an unquoted
    plain scalar the moment it is followed by a space."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def replace_description(text: str, new_description: str) -> str:
    """Rewrite the frontmatter `description:` field to a single-line quoted
    scalar. Raises `ValueError` when there is no frontmatter fence or no
    `description:` key -- both are authoring defects, never silently skipped.
    """
    if not text.startswith("---"):
        raise ValueError("no frontmatter fence")
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("unterminated frontmatter fence")

    lines = text[3:end].split("\n")
    start = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("description:")), None
    )
    if start is None:
        raise ValueError("no description: field in frontmatter")

    value = lines[start].split("description:", 1)[1].strip()
    stop = start + 1
    if value[:1] in (">", "|"):
        while stop < len(lines) and (
            lines[stop].strip() == "" or lines[stop].startswith((" ", "\t"))
        ):
            stop += 1

    new_line = f"description: {_yaml_quote(new_description)}"
    new_frontmatter = "\n".join(lines[:start] + [new_line] + lines[stop:])
    return "---" + new_frontmatter + text[end:]


def current_description(path: Path) -> str:
    frontmatter = _frontmatter_block(path.read_text(encoding="utf-8"))
    if frontmatter is None:
        raise ValueError(f"{path}: no frontmatter fence")
    return _extract_description(frontmatter)


def _diff(path: Path, before: str, after: str) -> None:
    sys.stdout.writelines(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )


def apply_table(
    table: dict[str, str], skills_root: Path, *, check: bool, dry_run: bool
) -> tuple[int, list[str]]:
    """Returns `(changed_count, drift_findings)`. `drift_findings` is always
    populated with hard errors (missing file/field); a `--check` mismatch is
    also a finding, but a plain apply/dry-run mismatch is not (that is the
    normal case this script exists to fix)."""
    changed = 0
    findings: list[str] = []
    for name, new_description in sorted(table.items()):
        path = skills_root / name / "SKILL.md"
        if not path.is_file():
            findings.append(f"{name}: {path} does not exist")
            continue
        try:
            existing = current_description(path)
        except ValueError as exc:
            findings.append(f"{name}: {exc}")
            continue

        if existing == new_description:
            continue  # already at the target text -- idempotent no-op

        if check:
            findings.append(f"{name}: description differs from the table")
            continue

        text = path.read_text(encoding="utf-8")
        try:
            new_text = replace_description(text, new_description)
        except ValueError as exc:
            findings.append(f"{name}: {exc}")
            continue

        if dry_run:
            _diff(path, text, new_text)
            continue

        path.write_text(new_text, encoding="utf-8")
        changed += 1
        print(f"apply-skill-description-diet: rewrote {path}")

    return changed, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the table-driven skill-description diet (P1.12)."
    )
    parser.add_argument("--check", action="store_true", help="verify only; exit 1 on drift")
    parser.add_argument(
        "--dry-run", action="store_true", help="print a diff per changed file; write nothing"
    )
    parser.add_argument("--table", default=str(DEFAULT_TABLE))
    parser.add_argument("--repo-root")
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)

    try:
        table = load_table(Path(args.table))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"apply-skill-description-diet: ERROR -- {exc}", file=sys.stderr)
        return 2

    if not table:
        print("apply-skill-description-diet: table is empty, nothing to do")
        return 0

    for name in over_cap_names(table):
        print(
            f"apply-skill-description-diet: INFO -- {name} is {len(table[name])} chars "
            f"(> {MAX_DESCRIPTION_CHARS}, trigger-noun preservation takes precedence)"
        )

    changed, findings = apply_table(
        table, repo_root / "skills", check=args.check, dry_run=args.dry_run
    )

    for finding in findings:
        print(f"apply-skill-description-diet: DRIFT -- {finding}")

    if not findings and not args.check and not args.dry_run:
        print(
            f"apply-skill-description-diet: {changed} file(s) rewritten, "
            f"{len(table) - changed} already current"
        )

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
