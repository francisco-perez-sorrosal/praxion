#!/usr/bin/env python3
"""
Skill Validator -- validates SKILL.md structure and frontmatter.

Usage:
  python validate.py <skill-directory>   # validate a single skill
  python validate.py --all               # validate every skills/<name>/ under repo root

Errors (the skill is malformed):
  - YAML frontmatter exists (--- delimiters)
  - Required fields: name, description
  - name matches parent directory, 1-64 chars, lowercase/digits/hyphens
  - description is 1-1024 chars, no angle brackets
  - compatibility is at most 500 chars
  - No top-level field outside the accepted set (frontmatter_contract.py)

Warnings (the skill loads, but an authoring hazard will bite; see HAZARDS below).

Exit 0 when there is no error anywhere, exit 1 otherwise; a warning never changes it.
"""

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# The contract is a sibling module: put this script's own directory on the path so the import
# resolves however the validator is reached (run directly, or imported by package_skill.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from frontmatter_contract import (  # noqa: E402
    ACCEPTED_FIELDS,
    COMPATIBILITY_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    name_errors,
)

MAX_ENTRY_PAGE_LINES = 500

HELP_FLAGS = frozenset({"-h", "--help"})
HELP_TEXT = """\
Usage: validate.py <skill-directory> | --all

Validate SKILL.md structure and frontmatter.

Arguments:
  <skill-directory>  validate the one skill in that directory
  --all              validate every skills/<name>/ under the repository root
  -h, --help         print this text and exit 0

Exit status:
  0  no errors (warnings are printed but never change the exit status)
  1  (non-zero) at least one error, or the arguments could not be used
"""


@dataclass(frozen=True)
class RawField:
    """A frontmatter value as written: quoting intact, with the lines its key occupies."""

    value: str
    line_count: int


@dataclass(frozen=True)
class Report:
    """What the validator found. The exit status is a function of `errors` alone."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def extract_frontmatter(content: str) -> tuple[str | None, list[str]]:
    """Extract raw frontmatter string from SKILL.md content.

    Returns (frontmatter_text, errors).
    """
    if not content.startswith("---"):
        return None, ["Frontmatter missing: file must start with '---'"]

    close = content.find("\n---", 3)
    if close == -1:
        return None, ["Frontmatter missing closing '---' delimiter"]

    raw = content[4:close].strip()
    if not raw:
        return None, ["Frontmatter is empty"]

    return raw, []


def parse_frontmatter(raw: str) -> tuple[dict[str, RawField], list[str]]:
    """Parse simple YAML key-value pairs from frontmatter text.

    Handles single-line values, YAML folded scalars (>), literal scalars (|),
    and indented continuation lines. Values keep their source quoting; each
    field records how many lines its key and continuation lines span.
    """
    fields: dict[str, RawField] = {}
    errors: list[str] = []
    current_key: str | None = None
    current_value_lines: list[str] = []
    current_line_count = 0

    def flush():
        if current_key is not None:
            fields[current_key] = RawField(
                " ".join(current_value_lines).strip(), current_line_count
            )

    for line in raw.split("\n"):
        key_match = re.match(r"^([a-z][a-z0-9_-]*)\s*:\s*(.*)", line)
        if key_match:
            flush()
            current_key = key_match.group(1)
            current_line_count = 1
            value = key_match.group(2).strip()
            # Skip YAML block scalar indicators (> or |)
            if value in (">", "|", ">-", "|-"):
                current_value_lines = []
            else:
                current_value_lines = [value] if value else []
        elif current_key is not None and (line.startswith("  ") or line.startswith("\t")):
            # Continuation line for current key
            current_value_lines.append(line.strip())
            current_line_count += 1
        elif line.strip() == "":
            continue
        else:
            errors.append(f"Unexpected frontmatter line: {line!r}")

    flush()
    return fields, errors


def validate_name(name: str, expected_dir: str) -> list[str]:
    """Validate the name field value."""
    errors = list(name_errors(name))

    if name != expected_dir:
        errors.append(f"'name' ({name!r}) does not match directory name ({expected_dir!r})")

    return errors


def validate_description(desc: str) -> list[str]:
    """Validate the description field value."""
    errors: list[str] = []

    if not desc:
        errors.append("'description' is empty")
        return errors

    if len(desc) > DESCRIPTION_MAX_LENGTH:
        errors.append(f"'description' exceeds {DESCRIPTION_MAX_LENGTH} chars (got {len(desc)})")

    if re.search(r"[<>]", desc):
        errors.append("'description' must not contain angle brackets (< or >)")

    return errors


def validate_compatibility(value: str) -> list[str]:
    """Validate the optional compatibility field."""
    if len(value) > COMPATIBILITY_MAX_LENGTH:
        return [f"'compatibility' exceeds {COMPATIBILITY_MAX_LENGTH} chars (got {len(value)})"]
    return []


def field_errors(fields: dict[str, RawField], dir_name: str) -> list[str]:
    """Errors in the frontmatter fields, in the order a reader would fix them."""
    errors: list[str] = []

    unknown = set(fields) - ACCEPTED_FIELDS
    if unknown:
        errors.append(f"Unknown frontmatter fields: {', '.join(sorted(unknown))}")

    if "name" not in fields:
        errors.append("Missing 'name' in frontmatter (required)")
    else:
        errors.extend(validate_name(fields["name"].value, dir_name))

    if "description" not in fields:
        errors.append("Missing 'description' in frontmatter (required)")
    else:
        errors.extend(validate_description(fields["description"].value))

    if "compatibility" in fields:
        errors.extend(validate_compatibility(fields["compatibility"].value))

    return errors


# --- Hazards: a skill the harness loads without complaint that will still misbehave -------------


@dataclass(frozen=True)
class SkillText:
    """What a hazard may read: the parsed fields, the body, and the whole file's line count."""

    fields: dict[str, RawField]
    body: str
    total_lines: int


# A hazard returns its "<hazard> — <fix>" warning when the skill has it, and None otherwise.
Hazard = Callable[[SkillText], str | None]

_EMPTY_HINTS = ("", '""', "''")


def _long_entry_page(skill: SkillText) -> str | None:
    if skill.total_lines > MAX_ENTRY_PAGE_LINES:
        return (
            f"SKILL.md is {skill.total_lines} lines, over {MAX_ENTRY_PAGE_LINES} — "
            "move depth into references/"
        )
    return None


def _empty_argument_hint(skill: SkillText) -> str | None:
    hint = skill.fields.get("argument-hint")
    if hint is not None and hint.value in _EMPTY_HINTS:
        return "empty argument-hint — omit the key or give a quoted value"
    return None


def _unquoted_argument_hint(skill: SkillText) -> str | None:
    # YAML reads an unquoted `[path]` as a list, not as the hint text.
    hint = skill.fields.get("argument-hint")
    if (
        hint is not None
        and hint.value not in _EMPTY_HINTS
        and not hint.value.startswith(("'", '"'))
    ):
        return "unquoted argument-hint — quote the value"
    return None


def _multiline_user_only_description(skill: SkillText) -> str | None:
    user_only = skill.fields.get("disable-model-invocation")
    description = skill.fields.get("description")
    if (
        user_only is not None
        and user_only.value.lower() == "true"
        and description is not None
        and description.line_count > 1
    ):
        return (
            f"user-only skill's description spans {description.line_count} lines — "
            "write it on one line"
        )
    return None


def _arguments_without_placeholder(skill: SkillText) -> str | None:
    declared = skill.fields.get("arguments")
    if declared is None:
        return None
    names = re.findall(r"\w[\w-]*", declared.value)
    placeholders = ("ARGUMENTS", r"\d+", *map(re.escape, names))
    if re.search(rf"\$(?:{'|'.join(placeholders)})(?!\w)", skill.body):
        return None
    return "arguments declared but the body has no placeholder — add $ARGUMENTS or $<name>"


# The closed set of hazards; one warning per hazard present, none for a skill without any.
HAZARDS: tuple[Hazard, ...] = (
    _long_entry_page,
    _empty_argument_hint,
    _unquoted_argument_hint,
    _multiline_user_only_description,
    _arguments_without_placeholder,
)


def _body_after_frontmatter(content: str) -> str:
    """The text past the closing delimiter; call only once `extract_frontmatter` succeeded."""
    return content[content.find("\n---", 3) + len("\n---") :]


def check_skill(skill_dir: Path) -> Report:
    """Run all validations on a skill directory. Returns its errors and warnings."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return Report(errors=(f"SKILL.md not found in {skill_dir}",))

    content = skill_md.read_text(encoding="utf-8")

    raw, extract_errors = extract_frontmatter(content)
    if raw is None:
        return Report(errors=tuple(extract_errors))

    fields, parse_errors = parse_frontmatter(raw)
    errors = (*parse_errors, *field_errors(fields, skill_dir.name))

    skill = SkillText(fields, _body_after_frontmatter(content), len(content.splitlines()))
    warnings = tuple(message for hazard in HAZARDS if (message := hazard(skill)) is not None)

    return Report(errors, warnings)


def validate_skill(skill_dir: Path) -> list[str]:
    """The errors alone, as the packager consumes them: warnings never block packaging."""
    return list(check_skill(skill_dir).errors)


def _repo_root_from_script() -> Path:
    # Script lives at <repo>/skills/skill-crafting/scripts/validate.py
    return Path(__file__).resolve().parents[3]


def _print_items(header: str, messages: tuple[str, ...]) -> None:
    print(f"\n{header}")
    for message in messages:
        print(f"  - {message}")


def _print_skill_groups(header: str, groups: list[tuple[str, tuple[str, ...]]]) -> None:
    print(f"\n{header}")
    for name, messages in groups:
        print(f"\n{name}:")
        for message in messages:
            print(f"  - {message}")


def _validate_all(repo_root: Path) -> int:
    skills_root = repo_root / "skills"
    if not skills_root.is_dir():
        print(f"Error: {skills_root} is not a directory", file=sys.stderr)
        return 1
    reports = [
        (skill_dir.name, check_skill(skill_dir))
        for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir())
        if (skill_dir / "SKILL.md").is_file()
    ]
    count = len(reports)
    failed = [(name, report.errors) for name, report in reports if report.errors]
    warned = [(name, report.warnings) for name, report in reports if report.warnings]
    if failed:
        _print_skill_groups(f"FAILED -- {len(failed)}/{count} skills have errors:", failed)
    if warned:
        _print_skill_groups(f"WARNINGS -- {len(warned)}/{count} skills have warnings:", warned)
    if failed:
        return 1
    print(f"\nPASSED -- all {count} skills validated")
    return 0


def main() -> int:
    if HELP_FLAGS.intersection(sys.argv[1:]):
        print(HELP_TEXT, end="")
        return 0

    if len(sys.argv) != 2:
        print(
            f"Usage: {sys.argv[0]} <skill-directory> | --all",
            file=sys.stderr,
        )
        return 1

    arg = sys.argv[1]
    if arg == "--all":
        return _validate_all(_repo_root_from_script())

    skill_dir = Path(arg).resolve()
    if not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a directory", file=sys.stderr)
        return 1

    print(f"Validating skill: {skill_dir.name}")

    report = check_skill(skill_dir)

    if report.errors:
        _print_items(f"FAILED -- {len(report.errors)} error(s):", report.errors)
    if report.warnings:
        _print_items(f"WARNINGS -- {len(report.warnings)} warning(s):", report.warnings)
    if report.errors:
        return 1

    suffix = f" ({len(report.warnings)} warning(s))" if report.warnings else ""
    print(f"\nPASSED -- all validations succeeded{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
