"""Driver that finds every documentation embed of an architecture render.

Documentation is Praxion's own documentation about itself: every Markdown file git
tracks or would track under `docs/`, at the repository root (changelogs aside), and
`.ai-state/DESIGN.md`. Teaching material and templates for managed projects (rules,
skills, onboarding templates) show example paths, not Praxion's renders. An
embed is a Markdown image (`![alt](target)`) or an HTML `<img>` whose target points
into the architecture diagram set (`diagrams/architecture/`). The catalog is
`docs/diagrams/README.md`, read with shell brace forms (`{a,b}`) expanded.
"""

from __future__ import annotations

import html
import itertools
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG = REPO_ROOT / "docs" / "diagrams" / "README.md"
_TARGET = "diagrams/architecture/"
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)


@dataclass(frozen=True)
class Embed:
    document: Path
    alt: str
    target: str

    @property
    def resolved(self) -> Path:
        clean = self.target.split("#", 1)[0].split("?", 1)[0]
        base = REPO_ROOT if clean.startswith("/") else self.document.parent
        return (base / clean.lstrip("/")).resolve()


def documentation_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    keep = []
    for rel in filter(None, listed):
        parts = Path(rel).parts
        is_doc = parts[0] == "docs" or rel == ".ai-state/DESIGN.md" or len(parts) == 1
        if (
            is_doc
            and not Path(rel).name.upper().startswith("CHANGELOG")
            and (REPO_ROOT / rel).is_file()
        ):
            keep.append(REPO_ROOT / rel)
    return keep


def architecture_embeds() -> list[Embed]:
    embeds = []
    for doc in documentation_files():
        text = doc.read_text(encoding="utf-8", errors="replace")
        for alt, target in _MD_IMAGE.findall(text):
            if _TARGET in target:
                embeds.append(Embed(doc, html.unescape(alt), target))
        for tag in _IMG_TAG.findall(text):
            src = re.search(r"\bsrc\s*=\s*[\"']([^\"']+)", tag, re.I)
            alt = re.search(r"\balt\s*=\s*[\"']([^\"']*)", tag, re.I)
            if src and _TARGET in src.group(1):
                embeds.append(Embed(doc, html.unescape(alt.group(1)) if alt else "", src.group(1)))
    return embeds


def catalog_text() -> str:
    return expand_braces(CATALOG.read_text(encoding="utf-8"))


def expand_braces(text: str) -> str:
    def expand(token: str) -> list[str]:
        match = re.search(r"\{([^{}]*,[^{}]*)\}", token)
        if not match:
            return [token]
        head, tail = token[: match.start()], token[match.end() :]
        return list(
            itertools.chain.from_iterable(
                expand(f"{head}{opt}{tail}") for opt in match.group(1).split(",")
            )
        )

    return " ".join(" ".join(expand(token)) for token in re.split(r"[\s`|()]+", text))
