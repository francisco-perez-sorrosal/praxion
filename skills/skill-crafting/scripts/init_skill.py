#!/usr/bin/env python3
"""
Skill Initializer -- creates a new skill directory from template.

Usage: python init_skill.py <skill-name> --path <output-directory>

Examples:
    python init_skill.py pdf-processing --path skills/
    python init_skill.py my-api-helper --path ~/.claude/skills
"""

import re
import sys
from pathlib import Path

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

EXAMPLE_SCRIPT = '''\
#!/usr/bin/env python3
"""
Example helper script for {skill_name}.

Replace with actual implementation or delete if not needed.

Example real scripts from other skills:
- pdf/scripts/fill_fillable_fields.py - Fills PDF form fields
- pdf/scripts/convert_pdf_to_images.py - Converts PDF pages to images

Appropriate for: Python scripts, shell scripts, or any executable code that
performs automation, data processing, or specific operations. For example:
form field extraction, PDF manipulation, file conversion, data validation.

Scripts may be executed without loading into context, but can still be read
by the agent for patching or environment-specific adjustments.
"""


def main():
    print("Example script for {skill_name}")
    # TODO: Add actual script logic here


if __name__ == "__main__":
    main()
'''

EXAMPLE_REFERENCE = """\
# Reference Documentation for {skill_title}

Replace with actual reference content or delete if not needed.

Example real reference docs from other skills:
- product-management/references/communication.md - Comprehensive guide for status updates
- product-management/references/context_building.md - Deep-dive on gathering context
- bigquery/references/ - API references and query examples

Appropriate for: in-depth documentation, API references, database schemas,
comprehensive workflow guides, company policies, or any detailed information
that the agent should reference while working. For example: communication
guidelines, context-building procedures, query examples, schema documentation.

## Structure Suggestions

### API Reference
- Overview
- Authentication
- Endpoints with examples
- Error codes
- Rate limits

### Workflow Guide
- Prerequisites
- Step-by-step instructions
- Common patterns
- Troubleshooting
- Best practices
"""

EXAMPLE_ASSET = """\
# Example Asset

Replace with actual asset files (templates, images, fonts, etc.) or delete
if not needed.

Asset files are NOT loaded into context -- they are used in the output the
agent produces.

Example asset files from other skills:
- Brand guidelines: logo.png, slides_template.pptx
- Frontend builder: hello-world/ directory with HTML/React boilerplate
- Typography: custom-font.ttf, font-family.woff2
- Data: sample_data.csv, test_dataset.json

Appropriate for: templates (.pptx, .docx), images (.png, .jpg, .svg),
fonts (.ttf, .woff2), boilerplate project directories, starter files,
icons (.ico, .svg), or data files (.csv, .json, .yaml).

Note: This is a text placeholder. Actual assets can be any file type.
"""

SKILL_TEMPLATE = """\
---
name: {skill_name}
description: >
  TODO: What the skill does and when to use it. This is the PRIMARY triggering
  mechanism -- the agent reads this to decide whether to activate the skill.
  Include specific trigger terms and key use cases. Write in third person.
  Example: "Extract text from PDF files, fill forms, merge documents. Use when
  working with PDF files or when the user mentions PDFs, forms, or document
  extraction."
---

# {skill_title}

[TODO: 1-2 sentences explaining what this skill enables.]

## Structuring This Skill

Choose the structure that best fits this skill's purpose:

**1. Workflow-Based** (best for sequential processes)
- Clear step-by-step procedures with validation between steps
- Example: DOCX skill with "Workflow Decision Tree" -> "Reading" -> "Creating" -> "Editing"
- Structure: ## Overview -> ## Decision Tree -> ## Step 1 -> ## Step 2...

**2. Task-Based** (best for tool collections)
- Different operations or capabilities the skill offers
- Example: PDF skill with "Quick Start" -> "Merge PDFs" -> "Split PDFs" -> "Extract Text"
- Structure: ## Overview -> ## Quick Start -> ## Task 1 -> ## Task 2...

**3. Reference/Guidelines** (best for standards or specifications)
- Standards, brand guidelines, coding conventions, or requirements
- Example: Brand styling with "Brand Guidelines" -> "Colors" -> "Typography"
- Structure: ## Overview -> ## Guidelines -> ## Specifications -> ## Usage...

**4. Capabilities-Based** (best for integrated systems)
- Multiple interrelated features that work together
- Example: Product Management with "Core Capabilities" -> numbered feature list
- Structure: ## Overview -> ## Core Capabilities -> ### 1. Feature -> ### 2. Feature...

Patterns can be mixed. Most skills combine patterns (e.g., task-based with workflow
for complex operations). Delete this entire "Structuring This Skill" section when done.

## [TODO: Replace with first main section based on chosen structure]

[TODO: Add content. Only include information the agent does not already have.]
Challenge each piece: "Does the agent really need this?"

Useful content types:
- Code samples for technical skills
- Decision trees for complex workflows
- Concrete examples with realistic user requests
- References to scripts/templates/references as needed]

## Bundled Resources

This skill includes resource directories for organizing different types of files.
Delete any unneeded directories -- not every skill needs all three.

### scripts/

Executable code (Python/Bash/etc.) for tasks requiring deterministic reliability
or that would otherwise be rewritten repeatedly.

- Scripts are executed (via Bash), not loaded into context -- keeping token cost low
- Handle errors explicitly -- solve, do not punt to the agent
- May still be read by the agent for patching or environment adjustments

**Examples from other skills:**
- PDF skill: `fill_fillable_fields.py`, `extract_form_field_info.py` - pdf manipulation scripts
- DOCX skill: `document.py`, `utilities.py` - docx processing scripts

### references/

Documentation loaded on-demand to inform the agent's process and thinking.

- Keep SKILL.md lean -- prefer references for detailed material
- Information should live in EITHER SKILL.md or references, not both
- For files over 100 lines, include a table of contents at the top
- Keep one level deep from SKILL.md -- avoid nested reference chains

**Examples from other skills:**
- Product management: `communication.md`, `context_building.md`
- BigQuery: API reference documentation and query
- Finance: Schema documentation, company policies

### assets/

Files used in the output the agent produces, NOT loaded into context.

- Templates, images, boilerplate code, fonts, sample documents
- Copied or modified for the final output

**Examples from other skills:**
- Brand styling: PowerPoint templates (.pptx), logo files
- Frontend builder: HTML/React boilerplate project directories
- Typography: custom-font.ttf, font-family.woff2

## Common Skill Types

Three common patterns for `allowed-tools`:

- **Read-only reference**: `allowed-tools: [Read, Grep, Glob]` -- documentation and code analysis
- **Script-based**: `allowed-tools: [Read, Bash, Write]` -- executable utilities
- **Template-based**: `allowed-tools: [Read, Write, Edit]` -- templates in `assets/`
"""


def title_case(name: str) -> str:
    """Convert kebab-case to Title Case."""
    return " ".join(word.capitalize() for word in name.split("-"))


def init_skill(skill_name: str, output_path: Path) -> int:
    skill_dir = output_path / skill_name

    if skill_dir.exists():
        print(f"Error: directory already exists: {skill_dir}", file=sys.stderr)
        return 1

    # Validate name
    if not NAME_PATTERN.match(skill_name):
        print(
            f"Error: name must be lowercase letters/digits/hyphens, "
            f"no consecutive hyphens (got {skill_name!r})",
            file=sys.stderr,
        )
        return 1

    if len(skill_name) > 64:
        print("Error: name exceeds 64 characters", file=sys.stderr)
        return 1

    # Create directory and SKILL.md
    skill_title = title_case(skill_name)
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(SKILL_TEMPLATE.format(skill_name=skill_name, skill_title=skill_title))

    # Create resource directories with example files
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    example_script = scripts_dir / "example.py"
    example_script.write_text(EXAMPLE_SCRIPT.format(skill_name=skill_name))
    example_script.chmod(0o755)

    references_dir = skill_dir / "references"
    references_dir.mkdir()
    (references_dir / "api_reference.md").write_text(
        EXAMPLE_REFERENCE.format(skill_title=skill_title)
    )

    assets_dir = skill_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "example_asset.txt").write_text(EXAMPLE_ASSET)

    print(f"Created {skill_dir}/")
    print("  SKILL.md              (edit frontmatter and body)")
    print("  scripts/example.py    (replace or delete)")
    print("  references/api_reference.md  (replace or delete)")
    print("  assets/example_asset.txt     (replace or delete)")
    print()
    print("Next steps:")
    print("  1. Complete the TODO items in SKILL.md")
    print("  2. Replace or delete example files in scripts/, references/, assets/")
    print("  3. Run validate.py when ready to check structure")

    return 0


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[2] != "--path":
        print("Usage: init_skill.py <skill-name> --path <output-directory>")
        print()
        print("Examples:")
        print("  init_skill.py pdf-processing --path skills/")
        print("  init_skill.py my-api-helper --path ~/.claude/skills")
        return 1

    skill_name = sys.argv[1]
    output_path = Path(sys.argv[3]).resolve()

    return init_skill(skill_name, output_path)


if __name__ == "__main__":
    sys.exit(main())
