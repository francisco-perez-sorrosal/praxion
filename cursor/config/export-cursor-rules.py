#!/usr/bin/env python3
"""Export rules/*.md to Cursor .cursor/rules/ with minimal frontmatter (description, alwaysApply). Repo files unchanged."""

import re
import sys
from pathlib import Path

# A resident file declares, as a top-level frontmatter key, the rule it is a projection of. The
# exporter checks that key itself so it runs from any copy that carries cursor/config/ alone (the
# move instrument's narrowed checkouts do); tests/test_export_cursor_rules_resident.py holds this
# check equal to scripts/_resident_of.py, the reader the kernel tooling uses.
_RESIDENT_OF = re.compile(r"""^["']?resident_of["']?\s*:\s*(.*?)\s*$""")


def path_to_description(rel_path: str) -> str:
    """One-line description from path; keep short."""
    stem = rel_path.replace(".md", "").replace("/", " ").replace("-", " ").replace("_", " ")
    return " ".join(w.capitalize() for w in stem.split() if w).strip() or stem


def is_resident(text: str) -> bool:
    """Whether a rule file's frontmatter names, in `resident_of`, the rule it stands for."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return False
    closing = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if closing is None:  # never closed: not frontmatter
        return False
    for line in lines[1:closing]:
        match = _RESIDENT_OF.match(line)
        if match:
            return bool(match.group(1).strip("\"'"))
    return False


def export_rules(repo_root: Path, out_dir: Path) -> None:
    rules_dir = repo_root / "rules"
    if not rules_dir.is_dir():
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(rules_dir.rglob("*.md")):
        rel = path.relative_to(rules_dir)
        # Directory guides (README.md, CLAUDE.md) are not rules.
        if rel.name in {"README.md", "CLAUDE.md"} or "references" in rel.parts:
            continue
        text = path.read_text(encoding="utf-8")
        # A resident file is a projection of a rule the export already carries.
        if is_resident(text):
            continue
        # Strip existing frontmatter so we don't double it
        if text.strip().startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2].lstrip("\n")
        description = path_to_description(str(rel))
        out_path = out_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            f'---\ndescription: "{description}"\nalwaysApply: false\n---\n\n{text}',
            encoding="utf-8",
        )
        print(f"  {rel} -> {out_path}")


def main() -> None:
    repo_root = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent.parent
    )
    out_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else repo_root / ".cursor" / "rules"
    export_rules(repo_root, out_dir)


if __name__ == "__main__":
    main()
