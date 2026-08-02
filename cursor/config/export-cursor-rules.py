#!/usr/bin/env python3
"""Export rules/*.md to Cursor .cursor/rules/ with minimal frontmatter (description, alwaysApply). Repo files unchanged."""

import sys
from pathlib import Path


def path_to_description(rel_path: str) -> str:
    """One-line description from path; keep short."""
    stem = rel_path.replace(".md", "").replace("/", " ").replace("-", " ").replace("_", " ")
    return " ".join(w.capitalize() for w in stem.split() if w).strip() or stem


def export_rules(repo_root: Path, out_dir: Path) -> None:
    rules_dir = repo_root / "rules"
    if not rules_dir.is_dir():
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(rules_dir.rglob("*.md")):
        rel = path.relative_to(rules_dir)
        if rel.name == "README.md" or "references" in rel.parts:
            continue
        text = path.read_text(encoding="utf-8")
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
