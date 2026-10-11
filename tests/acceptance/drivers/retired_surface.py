"""Driver for searching the repository for the retired workflow directory and vocabulary.

Files are the tracked set as the index lists it (`git ls-files`, which needs no history). A
*live reference* to the retired directory is `commands/` as a path from the repository root:
bare, after `./` or `../`, after a root variable (`${CLAUDE_PLUGIN_ROOT}/`, `$PRAXION_ROOT/`),
in a link to this repository on GitHub, or a `"commands"` path segment joined in code. A
`commands/` that continues another path (`tests/commands/`, `.claude/commands/`,
`.cursor/commands/`) is some other directory and is not matched.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

LIVE_REFERENCE = re.compile(
    r"(?:(?<![\w.~$}/-])|(?<=\.\./)|(?<=\./)|(?<=\}/)|(?<=ROOT/)|(?<=Praxion/blob/main/)"
    r"|(?<=Praxion/tree/main/))commands/"
    r"|[/,(]\s*[\"']commands[\"']"
)

# Frozen history: records of the past, never rewritten.
FROZEN_HISTORY = re.compile(
    r"^(\.ai-state/(decisions|specs|sentinel_reports|metrics_reports|skill_genesis_reports"
    r"|praxion_eval_reports)/"
    r"|\.ai-state/(TECH_DEBT_LEDGER|TECH_DEBT_RESOLVED|calibration_log|DESIGN_CHANGELOG)\.md$"
    r"|CHANGELOG\.md$|docs/independent-analysis/|docs/context-prj-comparison-[^/]*/"
    r"|eval/.*(fixtures?|streams?)/)"
)

# Named exceptions: the frozen before-state and the tests asserting a retired surface stays
# absent (this outer loop), the installers' legacy cleanup and its tests, and the conversion
# recipe that names the legacy file shape as its input. Every other test module and the frozen
# fixture snapshots join them: once the directory is gone a test can only name it as a negative
# case (a stray file there is ignored, a replacement must not send readers there), and a
# fixture snapshot is a before-state.
NAMED_EXCEPTIONS = re.compile(
    r"^(tests/acceptance/|install_cursor\.sh$|install_codex\.sh$|scripts/test_install_(cursor|codex)[\w]*\.py$"
    r"|tests/test_legacy_\w+\.sh$|skills/skill-crafting/references/user-invoked-skills\.md$"
    r"|scripts/test_\w+\.py$|scripts/[\w/]+/tests/test_\w+\.py$|tests/(?:[\w-]+/)*test_\w+\.py$"
    r"|scripts/test_fixtures/|tests/fixtures/)"
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return [f for f in result.stdout.split("\0") if f]


def read_text(relative: str) -> str | None:
    path = REPO_ROOT / relative
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def lines_matching(pattern: re.Pattern, *, exempt: tuple[re.Pattern, ...] = ()) -> list[str]:
    """`path:line: text` for every tracked, non-exempt file line the pattern matches."""
    hits = []
    for relative in tracked_files():
        if any(e.search(relative) for e in exempt):
            continue
        text = read_text(relative)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{relative}:{number}: {line.strip()[:160]}")
    return hits


def always_loaded_files() -> list[str]:
    """The guidelines template, the project guide, every rule without a path scope."""
    import yaml

    files = ["claude/config/CLAUDE.md.tmpl", "CLAUDE.md"]
    for path in sorted((REPO_ROOT / "rules").rglob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        meta = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else None
        if not (isinstance(meta, dict) and meta.get("paths")):
            files.append(path.relative_to(REPO_ROOT).as_posix())
    return files


def agent_definitions() -> list[str]:
    return [
        p.relative_to(REPO_ROOT).as_posix()
        for p in sorted((REPO_ROOT / "agents").glob("*.md"))
        if p.name not in ("README.md", "CLAUDE.md")
    ]


def canonical_blocks() -> list[str]:
    return [
        p.relative_to(REPO_ROOT).as_posix()
        for p in sorted((REPO_ROOT / "claude/canonical-blocks").glob("*.md"))
    ]


def glob_matches(pattern: str, path: str) -> bool:
    """Path-scope glob semantics: `**` spans directories, `*` stays within one."""
    regex = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            regex += r"(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            regex += r".*"
            i += 2
        elif pattern[i] == "*":
            regex += r"[^/]*"
            i += 1
        else:
            regex += re.escape(pattern[i])
            i += 1
    return re.fullmatch(regex, path) is not None
