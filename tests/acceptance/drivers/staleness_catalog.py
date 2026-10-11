"""Driver for the staleness catalog: a skill's cataloged titles, their headings, their markers.

The checker runs as `check_staleness_markers.py --json --repo-root <root>`. The contract assumed
of its JSON output: a `findings` list whose entries carry `check` (`F07`, `F08`, `F09`) and an
`entity` that opens with `<skill>::<title>`; and a `withheld` list of strings, each opening with
`<skill>::<title>`, for cataloged titles that match no heading.

A cataloged title resolves the way the checker's documentation states: an h2 or h3 heading with
exactly that text, looked for on the entry page, then the skill's reference pages, then its
context pages (each directory alphabetically); the marker is the HTML comment
`<!-- last-verified: <value> -->` on the line directly below the heading.

Nothing here imports the system under test.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "check_staleness_markers.py"
_MARKER = re.compile(r"^\s*<!--\s*last-verified:\s*(?P<value>\S+)\s*-->\s*$")


def run_checker(root: Path = REPO_ROOT) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_"))}
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--json", "--repo-root", str(root)],
        cwd=root, env=env, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    if result.returncode != 0:
        raise AssertionError(
            f"the staleness checker exited {result.returncode}: {result.stderr[-1500:]}"
        )
    return json.loads(result.stdout)


def findings_for(envelope: dict, skill: str) -> list[dict]:
    return [
        f for f in envelope.get("findings", []) if str(f.get("entity", "")).startswith(f"{skill}::")
    ]


def withheld_for(envelope: dict, skill: str) -> list[str]:
    return [w for w in envelope.get("withheld", []) if str(w).startswith(f"{skill}::")]


def catalog(skill_dir: Path) -> list[str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
    return list((meta or {}).get("staleness_sensitive_sections") or [])


def _candidate_pages(skill_dir: Path) -> list[Path]:
    pages = [skill_dir / "SKILL.md"]
    for sub in ("references", "contexts"):
        pages += sorted((skill_dir / sub).glob("*.md")) if (skill_dir / sub).is_dir() else []
    return pages


def resolve(skill_dir: Path, title: str) -> tuple[Path, int] | None:
    """The page and line index of the heading a cataloged title names, or None."""
    heading = re.compile(rf"^#{{2,3}}\s+{re.escape(title)}\s*$")
    for page in _candidate_pages(skill_dir):
        for index, line in enumerate(page.read_text(encoding="utf-8").splitlines()):
            if heading.match(line):
                return page, index
    return None


def marker_below(page: Path, index: int) -> str | None:
    lines = page.read_text(encoding="utf-8").splitlines()
    if index + 1 >= len(lines):
        return None
    match = _MARKER.match(lines[index + 1])
    return match.group("value") if match else None
