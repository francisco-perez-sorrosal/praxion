#!/usr/bin/env python3
r"""Strip stale routing-rule citations from agent frontmatter `model:` lines.

`rules/swe/agent-model-routing.md` is hook-delivered to the orchestrator's
spawn decision, not something a subagent frontmatter comment usefully cites
(the subagent never reads its own frontmatter at runtime). Several agent
files nonetheless carry a trailing comment on the `model:` line pointing at
that rule, in one of a few hand-written wordings, e.g.:

    model: sonnet  # capability floor per rules/swe/agent-model-routing.md
    model: opus  # capability floor; orchestrator may route up via
                 # per-spawn override, never below. See rules/swe/agent-model-routing.md.

This script deletes any such trailing comment -- matched by the presence of
`agent-model-routing.md` after a `#` on a `model:` line -- leaving a bare
`model: <alias>`. It never touches a `model:` line whose comment does not
cite that rule (e.g. `doc-engineer.md`'s pinned-ID rationale).

Idempotent: a second run over already-stripped files is a no-op.

Two invocation modes:

    strip_routing_frontmatter_comments.py            # --write (default)
    strip_routing_frontmatter_comments.py --check    # exit 1 if any citation remains

Exit codes:
    0 -- no citations remain (--check), or all citations stripped (--write)
    1 -- --check found at least one remaining citation
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"

# Matches a `model:` line whose trailing comment cites the routing rule,
# regardless of the comment's exact wording. Captures the line up to (but
# not including) the comment, so the replacement is a bare `model: <value>`.
MODEL_LINE_CITATION = re.compile(
    r"^(model:\s*\S+)[ \t]+#.*agent-model-routing\.md.*$",
    re.MULTILINE,
)


def strip_citation(text: str) -> str:
    """Return `text` with any routing-rule citation removed from its `model:` line."""
    return MODEL_LINE_CITATION.sub(r"\1", text)


def find_agent_files() -> list[Path]:
    return sorted(AGENTS_DIR.glob("*.md"))


def run_write() -> int:
    changed = []
    for path in find_agent_files():
        original = path.read_text()
        stripped = strip_citation(original)
        if stripped != original:
            path.write_text(stripped)
            changed.append(path.relative_to(REPO_ROOT))
    for path in changed:
        print(f"stripped: {path}")
    print(f"{len(changed)} file(s) stripped.")
    return 0


def run_check() -> int:
    remaining = [
        path.relative_to(REPO_ROOT)
        for path in find_agent_files()
        if MODEL_LINE_CITATION.search(path.read_text())
    ]
    if remaining:
        for path in remaining:
            print(f"citation remains: {path}")
        return 1
    print("no routing-rule citations remain in agents/*.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Check for remaining citations and exit 1 if any found, without writing.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.check:
        return run_check()
    return run_write()


if __name__ == "__main__":
    sys.exit(main())
