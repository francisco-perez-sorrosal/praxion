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
is found exactly once, or a passage it inserted has been reworded) or, under `--check`, the state
differs; 2 a usage error, including a root with no definitions, no root to default to (the working
directory is not in a git repository), an installed-plugin cache as root, and a definition that
cannot be read or written. This tool lives in the Praxion checkout only and is not shipped as a command.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from _repo_root import git_toplevel_from_cwd, is_plugin_cache_path

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
    # Text that only an inserted passage leaves behind: where it is found without the exact
    # delivered text, the passage was reworded, and the site is not the preloaded state.
    inserted_trace: str | None = None

    def text(self, state: State) -> str:
        return self.preloaded if state == "preloaded" else self.delivered

    def holds(self, text: str, state: State) -> bool:
        """True when `text` is in `state` here: its words found once, and no stray insertion."""
        stray = (
            state == "preloaded" and self.inserted_trace is not None and self.inserted_trace in text
        )
        return text.count(self.text(state)) == 1 and not stray

    def __str__(self) -> str:
        return f"{self.definition} ({self.name})"


# The passage is read by every host, so it states a condition rather than a state: where the
# skill is already in context it is inert. The Codex export carries it because no spawn-time
# delivery reaches a Codex agent.
_PASSAGE_BEGIN = "<!-- codex-wrapper:begin -->"
_CODEX_PASSAGE = (
    f"{_PASSAGE_BEGIN}\n"
    "A step whose delegation carries `[Phase: Refactoring]` is verified against "
    "`skills/refactoring/SKILL.md`. Where that skill's text is not already in your context "
    "(a host with no spawn-time delivery, or a delivery that failed), read it before starting "
    "the step.\n"
    "<!-- codex-wrapper:end -->"
)


def _with_codex_passage(definition: str, anchor: str) -> Site:
    """The passage is inserted after `anchor`, the last sentence of the paragraph it follows."""
    return Site(
        definition,
        "Codex passage",
        anchor,
        f"{anchor}\n\n{_CODEX_PASSAGE}",
        inserted_trace=f"{anchor}\n\n{_PASSAGE_BEGIN}",
    )


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
        IMPLEMENTER,
        "names the behaviors the paired characterization tests must lock down.",
    ),
    _with_codex_passage(
        TEST_ENGINEER,
        "Tests written here become the regression detector that every subsequent restructuring "
        "step in the mini-pipeline must pass.",
    ),
)


def held_state(text: str, site: Site) -> State | None:
    """The state `text` holds at `site`; None when it holds neither, or is ambiguous."""
    held = [state for state in STATES if site.holds(text, state)]
    return held[0] if len(held) == 1 else None


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


class UsageError(Exception):
    """The command cannot say which tree to move."""


def _target_root(explicit: str | None) -> Path:
    """The tree to move. Never a silent fallback: without a root the live checkout is not guessed."""
    root = Path(explicit).resolve() if explicit else git_toplevel_from_cwd()
    if root is None:
        raise UsageError("no --root given and the working directory is not in a git repository")
    if is_plugin_cache_path(root):
        raise UsageError(f"{root} is an installed-plugin cache, which is never moved")
    return root


def _read_definitions(root: Path) -> dict[str, str]:
    """Bytes in, bytes out: a definition's line endings are never normalized by the move."""
    definitions = sorted({site.definition for site in SITES})
    return {d: (root / d).read_bytes().decode("utf-8") for d in definitions}


def _write_definitions(root: Path, texts: Mapping[str, str], to: State) -> int:
    for definition, text in texts.items():
        try:
            (root / definition).write_bytes(text.encode("utf-8"))
        except OSError as exc:
            return _fail(f"cannot write {definition}: {exc}")
        print(f"refactoring-move: moved {definition} to {to}")
    return 0


def _fail(reason: object) -> int:
    print(f"refactoring-move: ERROR -- {reason}", file=sys.stderr)
    return 2


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
    try:
        root = _target_root(args.root)
        texts = _read_definitions(root)
    except (UsageError, OSError, UnicodeDecodeError) as exc:
        return _fail(exc)

    moved, drifted = move(texts, args.to)
    for site in drifted:
        print(
            f"refactoring-move: DRIFT -- {site}: neither the preloaded nor the delivered text "
            "is found exactly once",
            file=sys.stderr,
        )
    if drifted:
        return 1

    differing = {d: moved[d] for d in texts if moved[d] != texts[d]}
    if args.check:
        for definition in differing:
            print(f"refactoring-move: {definition} does not hold the {args.to} state")
        return 1 if differing else 0

    if not differing:
        print(f"refactoring-move: already {args.to}")
        return 0
    return _write_definitions(root, differing, args.to)


if __name__ == "__main__":
    sys.exit(main())
