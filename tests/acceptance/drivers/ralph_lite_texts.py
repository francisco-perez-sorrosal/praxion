"""Driver for the texts that describe Ralph-lite: its skill, its recipe, its launch policy.

Reads them as the ordinary text driver does (`tests/acceptance/drivers/shipped_texts.py`):
by file, by heading and by sentence, emphasis and code marks dropped. Adds the pieces this
mode's texts need: the skill's argument substitutions, the recipe's section, the tier
table's rows, and the list item or paragraph of a text that mentions a word.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers.shipped_texts import (
    COORDINATION_PROTOCOL,
    body,
    frontmatter,
    normalize,
    read,
    section,
)

RALPH_LITE_SKILL = "skills/ralph-lite/SKILL.md"
RALPH_LITE_COMMAND = "commands/ralph-lite.md"
TIER_TEMPLATES = "skills/software-planning/references/tier-templates.md"
EVAL_COMMAND = "commands/eval-praxion.md"
RALPH_LITE = r"ralph[- ]lite"
TIERS = ("Direct", "Lightweight", "Standard", "Full", "Spike")
NEGATION = r"\b(never|not|no|don't|do not|must not|mustn't|isn't)\b"

# The safety profile both the skill and the recipe state, each element as the patterns one
# sentence carries together.
SAFETY_PROFILE = {
    "a-scratch-worktree": (r"scratch", r"worktree"),
    "the-worker-under-dont-ask": (r"dontAsk",),
    "the-check-allow-listed": (r"allow", r"\bcheck\b"),
    "the-test-scope-resolver-allow-listed": (r"allow", r"resolve_test_scope|resolver"),
    "never-accept-edits-alone": (r"acceptEdits", NEGATION),
    "never-bypass-permissions-outside-a-container": (r"bypassPermissions", r"container"),
    "deny-rules-on-the-protected-paths": (r"\bdeny", r"protected"),
    "deny-rules-hold-in-every-permission-mode": (r"\bdeny", r"\b(every|any|all)\b", r"mode"),
    "a-turn-bound-per-iteration": (r"\bturn", r"iteration"),
    "a-dollar-fuse-per-iteration": (r"dollar|max-budget-usd|\bfuse\b", r"iteration"),
    "the-iterations-budget-bounds-the-loop": (r"\bIterations\b", r"budget"),
}


def skill_text() -> str:
    return read(RALPH_LITE_SKILL)


def recipe_section() -> str:
    """The Ralph-lite section of the tier-prompt scaffolds."""
    return section(read(TIER_TEMPLATES), RALPH_LITE)


def argument_substitutions_used(text: str) -> list[str]:
    """Which of `$ARGUMENTS`, `$0` and `$<declared name>` the skill's body uses."""
    declared = frontmatter(text).get("arguments") or []
    names = declared.split() if isinstance(declared, str) else [str(n) for n in declared]
    tokens = ["$ARGUMENTS", "$0", *(f"${name}" for name in names)]
    return [token for token in tokens if token in body(text)]


def tier_rows() -> list[str]:
    """The first cell of each row of the coordination protocol's tier table."""
    table = section(read(COORDINATION_PROTOCOL), r"process calibration")
    return re.findall(r"^\|\s*\*\*([^*]+)\*\*\s*\|", table, re.MULTILINE)


def tier_row(name: str) -> str:
    """The tier table's row for tier `name`, as one line."""
    table = section(read(COORDINATION_PROTOCOL), r"process calibration")
    rows = re.findall(rf"^\|\s*\*\*{re.escape(name)}\*\*\s*\|.*$", table, re.MULTILINE)
    if len(rows) != 1:
        raise AssertionError(f"the tier table has {len(rows)} rows for {name}: {rows}")
    return rows[0]


def blocks_mentioning(text: str, pattern: str) -> list[str]:
    """Paragraphs and list items of `text` that match `pattern`, normalized."""
    blocks = re.split(r"\n\s*\n|\n(?=\s*[-*] )", text)
    return [normalize(b) for b in blocks if re.search(pattern, b, re.IGNORECASE)]


def lines_with_goal_command(text: str) -> list[str]:
    """Lines naming the harness's `/goal` command (not a path or a namespaced skill)."""
    return [line for line in text.splitlines() if re.search(r"(?<![\w:/.-])/goal\b", line)]
