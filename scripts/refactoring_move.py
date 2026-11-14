"""Move the refactoring skill between its two ways of reaching the implementer and test-engineer.

In the `preloaded` state both definitions list the skill in their `skills:` frontmatter, so the
harness injects it into every spawn. In the `delivered` state they do not, and a delegation that
carries the phase marker is served the skill by the spawn hook instead. The move is the table
`SITES`: each row is one text of one definition, written once per state. Only the table knows
what changes; the rest of this module finds the state a definition holds and swaps the texts.

    refactoring_move.py --to {preloaded,delivered} [--root DIR] [--check]

`--root` is the tree whose `agents/` is moved (default: the git toplevel of the working directory).
Moving is idempotent and runs in either direction. All sites are checked before any file is
written, so a drifted definition is never left half moved.

Exit codes: 0 the state was applied or already held; 1 a site has drifted (neither of its texts
is found exactly once) or, under `--check`, the state differs; 2 a usage error, including a root
with no definitions. This tool lives in the Praxion checkout only and is not shipped as a command.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

State = Literal["preloaded", "delivered"]
STATES: tuple[State, ...] = ("preloaded", "delivered")

IMPLEMENTER = "agents/implementer.md"
TEST_ENGINEER = "agents/test-engineer.md"


@dataclass(frozen=True)
class Site:
    """One text of one definition, in the words each state needs."""

    definition: str
    name: str
    preloaded: str
    delivered: str

    def text(self, state: State) -> str:
        return self.preloaded if state == "preloaded" else self.delivered

    def __str__(self) -> str:
        return f"{self.definition} ({self.name})"


# The passage is read by every host, so it states a condition rather than a state: where the
# skill is already in context it is inert. The Codex export carries it because no spawn-time
# delivery reaches a Codex agent.
_CODEX_PASSAGE = (
    "<!-- codex-wrapper:begin -->\n"
    "A step whose delegation carries `[Phase: Refactoring]` is verified against "
    "`skills/refactoring/SKILL.md`. Where that skill's text is not already in your context "
    "(a host with no spawn-time delivery, or a delivery that failed), read it before starting "
    "the step.\n"
    "<!-- codex-wrapper:end -->"
)


def _with_codex_passage(name: str, definition: str, anchor: str) -> Site:
    """The passage is inserted after `anchor`, the last sentence of the paragraph it follows."""
    return Site(definition, name, anchor, f"{anchor}\n\n{_CODEX_PASSAGE}")


SITES: tuple[Site, ...] = tuple(
    site
    for definition in (IMPLEMENTER, TEST_ENGINEER)
    for site in (
        Site(
            definition,
            "skills list",
            "skills: [software-planning, code-review, refactoring]",
            "skills: [software-planning, code-review]",
        ),
        Site(
            definition,
            "always-available sentence",
            "The three statically-injected skills (`software-planning`, `code-review`, "
            "`refactoring`) are always available.",
            "The skills listed in your `skills:` frontmatter are always available.",
        ),
    )
) + (
    Site(
        IMPLEMENTER,
        "phase-tag sentence",
        "The `[Phase: Refactoring]` step tag pulls the always-loaded "
        "`skills/refactoring/SKILL.md` and signals that",
        "A delegation that carries the `[Phase: Refactoring]` step tag has "
        "`skills/refactoring/SKILL.md` in your context from your first turn (preloaded by your "
        "frontmatter or delivered with the delegation), and the tag signals that",
    ),
    _with_codex_passage(
        "Codex passage",
        IMPLEMENTER,
        "names the behaviors the paired characterization tests must lock down.",
    ),
    _with_codex_passage(
        "Codex passage",
        TEST_ENGINEER,
        "Tests written here become the regression detector that every subsequent restructuring "
        "step in the mini-pipeline must pass.",
    ),
)


def held_state(text: str, site: Site) -> State | None:
    """The state `text` holds at `site`; None when that is not decided by one occurrence.

    The delivered text is tried first because an inserted passage's delivered text contains its
    preloaded anchor.
    """
    for state in reversed(STATES):
        if text.count(site.text(state)) == 1:
            return state
    return None


def move(
    texts: Mapping[str, str], to: State, sites: tuple[Site, ...] = SITES
) -> tuple[dict[str, str], list[Site]]:
    """The definitions' texts moved to `to`, and the sites whose texts were not found."""
    moved = dict(texts)
    drifted = []
    for site in sites:
        held = held_state(moved[site.definition], site)
        if held is None:
            drifted.append(site)
        elif held != to:
            moved[site.definition] = moved[site.definition].replace(
                site.text(held), site.text(to), 1
            )
    return moved, drifted


def _read_definitions(root: Path) -> dict[str, str]:
    """Bytes in, bytes out: a definition's line endings are never normalized by the move."""
    definitions = sorted({site.definition for site in SITES})
    return {d: (root / d).read_bytes().decode("utf-8") for d in definitions}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move the refactoring skill between preloaded and delivered."
    )
    parser.add_argument("--to", required=True, choices=STATES)
    parser.add_argument("--root", help="tree whose agents/ is moved (default: git toplevel)")
    parser.add_argument(
        "--check", action="store_true", help="verify only; exit 1 when the state differs"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = resolve_repo_root(args.root, script_dir=SCRIPT_DIR)
    try:
        texts = _read_definitions(root)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"refactoring-move: ERROR -- {exc}", file=sys.stderr)
        return 2

    moved, drifted = move(texts, args.to)
    for site in drifted:
        print(
            f"refactoring-move: DRIFT -- {site}: neither the preloaded nor the delivered text "
            "is found exactly once",
            file=sys.stderr,
        )
    if drifted:
        return 1

    differing = [d for d in texts if moved[d] != texts[d]]
    if args.check:
        for definition in differing:
            print(f"refactoring-move: {definition} does not hold the {args.to} state")
        return 1 if differing else 0

    for definition in differing:
        (root / definition).write_bytes(moved[definition].encode("utf-8"))
        print(f"refactoring-move: moved {definition} to {args.to}")
    if not differing:
        print(f"refactoring-move: already {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
