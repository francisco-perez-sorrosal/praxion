"""Count the process text a split recipient is spared, at no cost.

A split recipient receives the protocol and the intermediate-documents rule without the
spans only the main session acts on. This command plans both units the way the hook does,
whole and split, through `_rule_delivery` (labels included, the split through `spawn_units`
over the committed `claude/kernels/spawn_split.json`), and reports the characters each
audience receives and the difference, per unit and in total, with a token figure that names
its basis.

It makes no model request. By default it makes no network call either: the token figure is
`measure_token_budget`'s offline estimate (basis `estimate`). `--tokenizer` opts in to the
real tokenizer through that module's counter, which needs `ANTHROPIC_API_KEY` and the network
and fails loudly rather than falling back, so an `estimate` is never mistaken for a
`tokenizer` reading.

Usage: python3 scripts/count_spawn_shed.py [--repo-root DIR] [--json] [--tokenizer]
Exit: 0 counted; 2 an input error (an input absent or unusable, or the tokenizer unavailable).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

# hooks/ sits beside scripts/; the hook's pure module is the one definition of the delivery
# this command measures, so a figure here is the length of what the hook prints.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import _rule_delivery as rd  # noqa: E402  # pyright: ignore[reportMissingImports]
import measure_token_budget as mtb  # noqa: E402
from _project_scope import Managed  # noqa: E402  # pyright: ignore[reportMissingImports]

REPORT_SCHEMA = 1
EXIT_COUNTED = 0
EXIT_INPUT_ERROR = 2
API_KEY_VARIABLE = "ANTHROPIC_API_KEY"
BASIS_ESTIMATE = "estimate"
BASIS_TOKENIZER = "tokenizer"

TokenCounter = Callable[[str], int]


class InputError(Exception):
    """An input the count needs is absent or unusable; the message names it."""


@dataclass(frozen=True)
class Figures:
    """What one audience-pair receives of a unit (or of all units): characters and tokens."""

    whole_chars: int
    split_chars: int
    whole_tokens: int
    split_tokens: int

    @property
    def shed_chars(self) -> int:
        return self.whole_chars - self.split_chars

    @property
    def shed_tokens(self) -> int:
        return self.whole_tokens - self.split_tokens

    def __add__(self, other: Figures) -> Figures:
        return Figures(
            self.whole_chars + other.whole_chars,
            self.split_chars + other.split_chars,
            self.whole_tokens + other.whole_tokens,
            self.split_tokens + other.split_tokens,
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        split = _read_spawn_split(args.repo_root)
        wholes = _read_whole_bodies(args.repo_root, split)
        splits = _read_split_bodies(args.repo_root, split, wholes)
        counter, basis = _token_counter(args.tokenizer)
        figures = shed_figures(wholes, splits, counter)
    except InputError as error:
        print(f"count_spawn_shed: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    for unit_id in _units_arriving_whole(wholes, splits):
        print(
            f"[count_spawn_shed] WARNING: {unit_id} arrives whole; its split is stale",
            file=sys.stderr,
        )
    print(_render_json(figures, basis) if args.json else _render_lines(figures, basis))
    return EXIT_COUNTED


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Count the text a split recipient sheds.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="the plugin root to count over (default: this checkout)",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--tokenizer",
        action="store_true",
        help=f"count tokens with the real tokenizer (network; needs {API_KEY_VARIABLE})",
    )
    return parser.parse_args(argv)


# -- Pure: planning and counting ---------------------------------------------------------


def shed_figures(
    wholes: Mapping[str, str], splits: Mapping[str, str], count_tokens: TokenCounter
) -> dict[str, Figures]:
    """Per unit, what a whole recipient and a split recipient each receive of it.

    `wholes` and `splits` hold the same unit ids: a unit's body, and the text a split
    recipient is given for it. Both are planned the way the hook plans a managed spawn.
    """
    whole_strings = _delivered_strings(wholes, rd.AgentKind.WHOLE_RECIPIENT)
    split_strings = _delivered_strings(splits, rd.AgentKind.SPLIT_RECIPIENT)
    return {
        unit_id: _figures(whole_strings[unit_id], split_strings[unit_id], count_tokens)
        for unit_id in wholes
    }


def _delivered_strings(units: Mapping[str, str], kind: rd.AgentKind) -> dict[str, list[str]]:
    """The labelled strings each unit reaches a managed spawn of `kind` as, by unit id."""
    scope = Managed(Path("."), Path(".ai-state"))
    parts = rd.plan_delivery(units, set(units), scope, rd.Event.SUBAGENT, kind, (), ())
    strings: dict[str, list[str]] = {unit_id: [] for unit_id in units}
    for part in parts:
        strings[part.unit_id].append(part.text)
    return strings


def _figures(whole: list[str], split: list[str], count_tokens: TokenCounter) -> Figures:
    return Figures(
        whole_chars=sum(map(len, whole)),
        split_chars=sum(map(len, split)),
        whole_tokens=count_tokens("\n\n".join(whole)),
        split_tokens=count_tokens("\n\n".join(split)),
    )


def _units_arriving_whole(wholes: Mapping[str, str], splits: Mapping[str, str]) -> list[str]:
    """The units whose stored split the hook would not use: they arrive whole."""
    return [unit_id for unit_id in wholes if splits[unit_id] == wholes[unit_id]]


def estimate_tokens(text: str) -> int:
    """The offline figure of `measure_token_budget`: UTF-8 bytes over its fallback divisor."""
    return round(len(text.encode("utf-8")) / mtb._FALLBACK_DIVISOR)


def _total(figures: Mapping[str, Figures]) -> Figures:
    return sum(figures.values(), Figures(0, 0, 0, 0))


# -- Pure: rendering ----------------------------------------------------------------------


def _render_json(figures: Mapping[str, Figures], basis: str) -> str:
    total = _total(figures)
    report = {
        "schema": REPORT_SCHEMA,
        "units": {
            unit_id: {
                "whole_chars": unit.whole_chars,
                "split_chars": unit.split_chars,
                "shed_chars": unit.shed_chars,
                "tokens": {
                    "whole": unit.whole_tokens,
                    "split": unit.split_tokens,
                    "shed": unit.shed_tokens,
                },
            }
            for unit_id, unit in figures.items()
        },
        "total": {
            "whole_chars": total.whole_chars,
            "split_chars": total.split_chars,
            "shed_chars": total.shed_chars,
        },
        "tokens": {
            "whole": total.whole_tokens,
            "split": total.split_tokens,
            "shed": total.shed_tokens,
            "basis": basis,
        },
    }
    return json.dumps(report, indent=2)


def _render_lines(figures: Mapping[str, Figures], basis: str) -> str:
    lines = [_line(unit_id, unit, basis) for unit_id, unit in figures.items()]
    return "\n".join([*lines, _line("total", _total(figures), basis)])


def _line(name: str, unit: Figures, basis: str) -> str:
    return (
        f"{name}: whole {unit.whole_chars} chars, split {unit.split_chars} chars, "
        f"shed {unit.shed_chars} chars (~{unit.shed_tokens} tokens, {basis})"
    )


# -- Edge: reading the plugin root --------------------------------------------------------


def _read_whole_bodies(root: Path, split: rd.SpawnSplit) -> dict[str, str]:
    """The body of each core unit the spawn split lists, as the hook reads it."""
    return {
        unit.unit_id: rd.rule_body(_read_text(root, unit.path))
        for unit in rd.MANAGED_CORE_UNITS
        if unit.unit_id in split.units
    }


def _read_split_bodies(
    root: Path, split: rd.SpawnSplit, wholes: Mapping[str, str]
) -> dict[str, str]:
    """The text a split recipient gets for each unit, trusting the artifact as the hook does."""
    manifest = hashlib.sha256(_read_bytes(root, rd.AUDIENCE_MANIFEST_PATH))
    return dict(rd.spawn_units(wholes, split, manifest.hexdigest()))


def _read_spawn_split(root: Path) -> rd.SpawnSplit:
    split = rd.parse_spawn_split(_read_text(root, rd.SPAWN_SPLIT_PATH))
    if split is None:
        raise InputError(f"{rd.SPAWN_SPLIT_PATH} is not a spawn split of schema {rd.SPLIT_SCHEMA}")
    return split


def _read_bytes(root: Path, relative: str) -> bytes:
    """The file's raw bytes, as the hook digests them; its absence is an input error."""
    try:
        return (root / relative).read_bytes()
    except OSError as error:
        raise InputError(f"{relative} cannot be read under {root}: {error}") from error


def _read_text(root: Path, relative: str) -> str:
    try:
        return _read_bytes(root, relative).decode("utf-8")
    except UnicodeDecodeError as error:
        raise InputError(f"{relative} is not UTF-8: {error}") from error


def _token_counter(use_tokenizer: bool) -> tuple[TokenCounter, str]:
    if not use_tokenizer:
        return estimate_tokens, BASIS_ESTIMATE
    api_key = os.environ.get(API_KEY_VARIABLE)
    if not api_key:
        raise InputError(f"--tokenizer needs {API_KEY_VARIABLE} to be set")

    def count(text: str) -> int:
        tokens = mtb.count_tokens(text, api_key)
        if tokens is None:
            raise InputError("the tokenizer could not be reached; no figure was counted")
        return tokens

    return count, BASIS_TOKENIZER


if __name__ == "__main__":
    sys.exit(main())
