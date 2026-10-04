#!/usr/bin/env python3
"""Regenerate the C4 renders of a LikeC4 workspace in one fixed visual vocabulary.

    ROOT      a diagram root holding `src/*.c4` and `rendered/`; default: every
              `<dir>/<name>/` under `docs/diagrams/` that has a `src/*.c4`
    --staged  pre-commit: only roots with a staged `src/*.c4`, then `git add <root>/rendered/`;
              failed checks print as non-blocking WARN lines
    --check   render into a temporary directory, byte-compare with the committed `rendered/`,
              run every review check; writes nothing in the checkout
    --json    findings as JSON Lines on stdout

Exit codes: 0 success (`--check`: no drift, no failed check); 1 a regeneration failure, or
under `--check` drift or a failed check; 2 a usage error (a refused `style.json` included);
3 (default, `--check`) `likec4` or `d2` absent from PATH or off its pinned version.

The model is read once, through `likec4 export json --skip-layout`, into a view projection;
each view is drawn as D2 text and rendered by `d2`. Every render guarantees:

- one category per element: its `metadata.category` when that is one string, else its
  kind's `notation`; without one it draws as "Uncategorised" and fails DRC-05, never the run;
- one drawing per (category, form): class `category_<snake_case>`, plus `_frame` for an
  element enclosing children in the view; in a vocabulary, marks differ without colour;
- plain, never markdown, element labels: name, `[Category]` or `[Category · technology]`,
  then the summary (else the description) wrapped at 28 characters, never truncated;
- one-way arrows labelled with the relationship title, or `<first title> +<k> more` over
  sorted titles; dynamic steps read `<n> · <title>`; kind `reads` is a dashed read-only line;
- a title block `<view title> — <C4 type> diagram` above the drawing, and below it a
  container labelled exactly `Legend` with one sample per drawing and line meaning used;
- no network address, clock or dark layer: an identical model and pinned toolchain give
  identical bytes; the only image is the Person glyph, embedded as a data URI.

`<diagram-root>/style.json` (`{"schema": 1, "categories": {"<Name>": {"box": {...},
"frame": {...}}}}`) adds categories; an entry missing a contrast floor or repeating a mark of
its form is a usage error naming it. Runs report a regeneration failure `{kind, target, what,
cause, fix}` (three stderr lines) and findings `{check, view, status, evidence, measured,
threshold}` (`<CHECK-ID> <VIEW> <STATUS> <EVIDENCE>`).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from _diagram_core import (
    Edge,
    Finding,
    LegendEntry,
    Node,
    Projection,
    RegenerationFailure,
    View,
    emit_d2,
    legend_entries,
    node_label_lines,
    project,
    resolve_category,
    wrap_text,
)
from _diagram_tokens import (
    DEFAULT_TOKENS,
    UNCATEGORISED,
    VOCABULARIES,
    Token,
    UsageError,
    load_style,
)

__all__ = [
    "DEFAULT_TOKENS",
    "Edge",
    "Finding",
    "LegendEntry",
    "Node",
    "Projection",
    "RegenerationFailure",
    "Token",
    "UNCATEGORISED",
    "UsageError",
    "VOCABULARIES",
    "View",
    "emit_d2",
    "legend_entries",
    "load_style",
    "node_label_lines",
    "project",
    "resolve_category",
    "wrap_text",
]

LIKEC4_VERSION = "1.59.4"
D2_VERSION = "0.7.1"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_TOOLCHAIN = 3

# --- command line ----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("roots", nargs="*", metavar="ROOT")
    for flag in ("--staged", "--check", "--json"):
        parser.add_argument(flag, action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print(
        "[diagram-regen] the render edge is not wired in yet; nothing regenerated", file=sys.stderr
    )
    return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
