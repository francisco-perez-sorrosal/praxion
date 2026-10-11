"""The SKILL.md frontmatter contract: which keys a skill may carry, and what a valid name is.

One source for every Praxion check that judges skill frontmatter. The validator and the
scaffold import it as a sibling module; the sentinel's frontmatter-key check loads it by file
path from the plugin's own tree. The schema reference (`references/schema.md`) lists the same
fields, and a parity test fails when the two disagree, so a field Claude Code adds is one line
here plus one row there.

Data and one pure function only: stdlib imports, no I/O, nothing runs on import.
"""

from __future__ import annotations

import re

# The portable Agent Skills core (agentskills.io); every compatible host reads these.
OPEN_STANDARD_FIELDS = frozenset(
    {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
    }
)

# Fields Claude Code reads on top of the portable core.
CLAUDE_CODE_FIELDS = frozenset(
    {
        "when_to_use",
        "disable-model-invocation",
        "user-invocable",
        "paths",
        "context",
        "agent",
        "background",
        "model",
        "effort",
        "argument-hint",
        "arguments",
        "hooks",
        "shell",
        "disallowed-tools",
    }
)

# Praxion's own staleness tracking (rules/swe/staleness-policy.md).
PRAXION_FIELDS = frozenset(
    {
        "staleness_sensitive_sections",
        "staleness_threshold_days",
    }
)

REQUIRED_FIELDS = frozenset({"name", "description"})
ACCEPTED_FIELDS = OPEN_STANDARD_FIELDS | CLAUDE_CODE_FIELDS | PRAXION_FIELDS

NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")
NAME_MAX_LENGTH = 64
DESCRIPTION_MAX_LENGTH = 1024
COMPATIBILITY_MAX_LENGTH = 500

_HYPHEN_RUN = re.compile(r"-{2,}")


def name_errors(name: str) -> tuple[str, ...]:
    """One message per rule `name` breaks, in a fixed order: length, hyphen runs, pattern.

    Empty means the name is valid. A run of hyphens has its own message, so the pattern is
    matched with each run collapsed to one hyphen: `a--b` draws only the hyphen message, while
    `A--b` draws both, because its capital letter breaks the pattern on its own.
    """
    errors: list[str] = []
    if len(name) > NAME_MAX_LENGTH:
        errors.append(f"'name' exceeds {NAME_MAX_LENGTH} chars (got {len(name)})")
    if _HYPHEN_RUN.search(name):
        errors.append(f"'name' must not contain consecutive hyphens (got {name!r})")
    if not NAME_PATTERN.fullmatch(_HYPHEN_RUN.sub("-", name)):
        errors.append(
            f"'name' must be lowercase letters/digits/hyphens, no consecutive "
            f"hyphens, no leading/trailing hyphens (got {name!r})"
        )
    return tuple(errors)
