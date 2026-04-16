#!/usr/bin/env python3
"""
Skill Validator -- validates SKILL.md structure and frontmatter.

Usage:
  python validate.py <skill-directory>   # validate a single skill
  python validate.py --all               # validate every skills/<name>/ under repo root

Validates:
  - YAML frontmatter exists (--- delimiters)
  - Required fields: name, description
  - name matches parent directory, 1-64 chars, lowercase/digits/hyphens
  - description is 1-1024 chars, no angle brackets
  - Optional fields: allowed-tools, license, metadata, compatibility,
    staleness_sensitive_sections, staleness_threshold_days
  - No unknown top-level fields

Exit 0 on success, exit 1 on failure.
"""

import re
import sys
from pathlib import Path

REQUIRED_FIELDS = {"name", "description"}
OPTIONAL_FIELDS = {
    "allowed-tools",
    "license",
    "metadata",
    "compatibility",
    "staleness_sensitive_sections",  # per rules/swe/staleness-policy.md
    "staleness_threshold_days",  # per rules/swe/staleness-policy.md
}
ALL_KNOWN_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
NAME_MAX_LENGTH = 64
DESCRIPTION_MAX_LENGTH = 1024
COMPATIBILITY_MAX_LENGTH = 500


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


def parse_frontmatter(raw: str) -> tuple[dict[str, str], list[str]]:
    """Parse simple YAML key-value pairs from frontmatter text.

    Handles single-line values, YAML folded scalars (>), literal scalars (|),
    and indented continuation lines.
    """
    fields: dict[str, str] = {}
    errors: list[str] = []
    current_key: str | None = None
    current_value_lines: list[str] = []

    def flush():
        if current_key is not None:
            fields[current_key] = " ".join(current_value_lines).strip()

    for line in raw.split("\n"):
        key_match = re.match(r"^([a-z][a-z0-9_-]*)\s*:\s*(.*)", line)
        if key_match:
            flush()
            current_key = key_match.group(1)
            value = key_match.group(2).strip()
            # Skip YAML block scalar indicators (> or |)
            if value in (">", "|", ">-", "|-"):
                current_value_lines = []
            else:
                current_value_lines = [value] if value else []
        elif current_key is not None and (
            line.startswith("  ") or line.startswith("\t")
        ):
            # Continuation line for current key
            current_value_lines.append(line.strip())
        elif line.strip() == "":
            continue
        else:
            errors.append(f"Unexpected frontmatter line: {line!r}")

    flush()
    return fields, errors


def validate_name(name: str, expected_dir: str) -> list[str]:
    """Validate the name field value."""
    errors: list[str] = []

    if len(name) > NAME_MAX_LENGTH:
        errors.append(f"'name' exceeds {NAME_MAX_LENGTH} chars (got {len(name)})")

    if not NAME_PATTERN.match(name):
        errors.append(
            f"'name' must be lowercase letters/digits/hyphens, no consecutive "
            f"hyphens, no leading/trailing hyphens (got {name!r})"
        )

    if name != expected_dir:
        errors.append(
            f"'name' ({name!r}) does not match directory name ({expected_dir!r})"
        )

    return errors


def validate_description(desc: str) -> list[str]:
    """Validate the description field value."""
    errors: list[str] = []

    if not desc:
        errors.append("'description' is empty")
        return errors

    if len(desc) > DESCRIPTION_MAX_LENGTH:
        errors.append(
            f"'description' exceeds {DESCRIPTION_MAX_LENGTH} chars (got {len(desc)})"
        )

    if re.search(r"[<>]", desc):
        errors.append("'description' must not contain angle brackets (< or >)")

    return errors


def validate_compatibility(value: str) -> list[str]:
    """Validate the optional compatibility field."""
    if len(value) > COMPATIBILITY_MAX_LENGTH:
        return [
            f"'compatibility' exceeds {COMPATIBILITY_MAX_LENGTH} chars (got {len(value)})"
        ]
    return []


def validate_skill(skill_dir: Path) -> list[str]:
    """Run all validations on a skill directory. Returns list of errors."""
    errors: list[str] = []

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"SKILL.md not found in {skill_dir}"]

    content = skill_md.read_text(encoding="utf-8")
    dir_name = skill_dir.name

    # Extract frontmatter
    raw, extract_errors = extract_frontmatter(content)
    if extract_errors:
        return extract_errors

    assert raw is not None
    fields, parse_errors = parse_frontmatter(raw)
    errors.extend(parse_errors)

    # Check for unknown fields
    unknown = set(fields.keys()) - ALL_KNOWN_FIELDS
    if unknown:
        errors.append(f"Unknown frontmatter fields: {', '.join(sorted(unknown))}")

    # Required: name
    if "name" not in fields:
        errors.append("Missing 'name' in frontmatter (required)")
    else:
        errors.extend(validate_name(fields["name"], dir_name))

    # Required: description
    if "description" not in fields:
        errors.append("Missing 'description' in frontmatter (required)")
    else:
        errors.extend(validate_description(fields["description"]))

    # Optional: compatibility
    if "compatibility" in fields:
        errors.extend(validate_compatibility(fields["compatibility"]))

    return errors


def _repo_root_from_script() -> Path:
    # Script lives at <repo>/skills/skill-crafting/scripts/validate.py
    return Path(__file__).resolve().parents[3]


def _validate_all(repo_root: Path) -> int:
    skills_root = repo_root / "skills"
    if not skills_root.is_dir():
        print(f"Error: {skills_root} is not a directory", file=sys.stderr)
        return 1
    failed: list[tuple[str, list[str]]] = []
    count = 0
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        if not (skill_dir / "SKILL.md").is_file():
            continue
        count += 1
        errors = validate_skill(skill_dir)
        if errors:
            failed.append((skill_dir.name, errors))
    if failed:
        print(f"\nFAILED -- {len(failed)}/{count} skills have errors:")
        for name, errs in failed:
            print(f"\n{name}:")
            for err in errs:
                print(f"  - {err}")
        return 1
    print(f"\nPASSED -- all {count} skills validated")
    return 0


def main() -> int:
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

    errors = validate_skill(skill_dir)

    if errors:
        print(f"\nFAILED -- {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("\nPASSED -- all validations succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
