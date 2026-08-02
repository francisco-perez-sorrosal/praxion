#!/usr/bin/env python3
"""
Skill Packager -- creates a distributable .skill file from a skill directory.

A .skill file is a zip archive with the .skill extension, containing the full
skill directory structure. Validates the skill before packaging.

Usage: python package_skill.py <path/to/skill-folder> [output-directory]

Examples:
    python package_skill.py skills/pdf-processing
    python package_skill.py skills/pdf-processing ./dist
"""

import sys
import zipfile
from pathlib import Path

# Import validate_skill from sibling module
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
# noqa E402: this import MUST follow the sys.path.insert above — the sibling
# module is not importable until the script's own directory is on the path.
# Hoisting it to the top would make the script fail to start.
from validate import validate_skill  # noqa: E402


def package_skill(skill_path: Path, output_dir: Path | None = None) -> int:
    if not skill_path.is_dir():
        print(f"Error: not a directory: {skill_path}", file=sys.stderr)
        return 1

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"Error: SKILL.md not found in {skill_path}", file=sys.stderr)
        return 1

    # Validate first
    print(f"Validating {skill_path.name}...")
    errors = validate_skill(skill_path)
    if errors:
        print(f"\nValidation failed ({len(errors)} error(s)):")
        for err in errors:
            print(f"  - {err}")
        print("\nFix validation errors before packaging.")
        return 1
    print("Validation passed.\n")

    # Determine output location
    skill_name = skill_path.name
    dest = (output_dir or Path.cwd()).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    skill_file = dest / f"{skill_name}.skill"

    # Create .skill archive
    with zipfile.ZipFile(skill_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(skill_path.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(skill_path.parent)
            zf.write(file_path, arcname)
            print(f"  Added: {arcname}")

    print(f"\nPackaged: {skill_file}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: package_skill.py <path/to/skill-folder> [output-directory]")
        print()
        print("Examples:")
        print("  package_skill.py skills/pdf-processing")
        print("  package_skill.py skills/pdf-processing ./dist")
        return 1

    skill_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None

    return package_skill(skill_path, output_dir)


if __name__ == "__main__":
    sys.exit(main())
