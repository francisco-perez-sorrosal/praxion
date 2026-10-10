#!/usr/bin/env python3
"""Regenerate the C4 renders of a LikeC4 workspace in one fixed visual vocabulary.

    ROOT      a diagram root holding `src/*.c4` and `rendered/`; default: every
              `<dir>/<name>/` under `docs/diagrams/` that has a `src/*.c4`
    --staged  pre-commit: only roots with a staged `src/*.c4`, then `git add <root>/rendered/`;
              failed checks print as non-blocking WARN lines; a tool absent or off its pin
              writes and stages nothing, warns naming the pins and exits 0
    --check   render into a temporary directory, byte-compare with the committed `rendered/`
              (DRC-10), run every review check; writes nothing in the checkout, and ends with
              `<n> renders · <f> failed checks · <d> drifted` on stderr
    --json    findings as JSON Lines on stdout
    --diagrams-dir DIR
              where roots are discovered when none is named; default `docs/diagrams`

Exit codes: 0 success (`--check`: no failed check); 1 a regeneration failure, or under
`--check` a failed check; 2 a usage error (a refused `style.json` included); 3 (default,
`--check`) `likec4` or `d2` absent from PATH or off its pinned version. `--staged` exits 0 in
that case after a warning, regenerating and staging nothing: the commit proceeds and the CI
drift gate still judges the renders.

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
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from _diagram_checks import regeneration_finding, run_checks
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
from _diagram_edge import (
    RENDER_DIR,
    RegenerationError,
    Toolchain,
    ToolProblem,
    build_root,
    discover_roots,
    has_model,
    publish,
    read_style,
    stage,
    staged_roots,
    toolchain_problems,
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
DEFAULT_DIAGRAMS_DIR = "docs/diagrams"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_TOOLCHAIN = 3

LOG = "[diagram-regen]"
SEPARATOR = "·"
SKIPPING = "skipping diagram regeneration"
DRIFT_CHECK = "DRC-10"
INSTALL = {
    "likec4": f"npm install --global likec4@{LIKEC4_VERSION}",
    "d2": f"install the d2 v{D2_VERSION} release tarball for your platform, checksum-verified"
    " (docs/architecture-diagrams.md, section D2)",
}

# --- command line ----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("roots", nargs="*", metavar="ROOT")
    for flag in ("--staged", "--check", "--json"):
        parser.add_argument(flag, action="store_true")
    parser.add_argument("--diagrams-dir", default=DEFAULT_DIAGRAMS_DIR, metavar="DIR")
    return parser


def main(argv: Sequence[str] | None = None, *, tool_path: str | None = None) -> int:
    """Run the command; `tool_path` is the PATH `likec4` and `d2` are found on (default: ours)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.staged and args.check:
        parser.error("--staged and --check cannot be combined")
    path = os.environ.get("PATH", "") if tool_path is None else tool_path
    try:
        return run(args, Toolchain(LIKEC4_VERSION, D2_VERSION, path))
    except UsageError as error:
        print(f"{LOG} usage error: {error}", file=sys.stderr)
        return EXIT_USAGE
    except RegenerationError as stopped:
        print(format_failure(stopped.failure), file=sys.stderr)
        return EXIT_FAILURE


# --- the modes -------------------------------------------------------------------------------


def run(args: argparse.Namespace, toolchain: Toolchain) -> int:
    roots = select_roots(args)
    if not roots:
        log("no diagram root to regenerate")
        return EXIT_OK
    refusal = toolchain_gate(toolchain, staged=args.staged)
    if refusal is not None:
        return refusal
    results = [regenerate(root, args, toolchain) for root in roots]
    if not args.check:
        return EXIT_OK
    findings = [finding for _, found in results for finding in found]
    renders = sum(count for count, _ in results)
    failed = [finding for finding in findings if finding.status == "FAIL"]
    drifted = sum(1 for finding in failed if finding.check == DRIFT_CHECK)
    log(f"{renders} renders {SEPARATOR} {len(failed)} failed checks {SEPARATOR} {drifted} drifted")
    return EXIT_FAILURE if failed else EXIT_OK


def select_roots(args: argparse.Namespace) -> list[Path]:
    """The roots named, else every one discovered; under `--staged`, those with a staged source."""
    roots = [Path(named) for named in args.roots]
    for root in roots:
        if not has_model(root):
            raise UsageError(f"{root} has no src/*.c4 model source")
    roots = roots or discover_roots(Path(args.diagrams_dir))
    return staged_roots(roots) if args.staged and roots else roots


def toolchain_gate(toolchain: Toolchain, staged: bool) -> int | None:
    """The exit code that refuses the run on the toolchain's state, or None to go on."""
    problems = toolchain_problems(toolchain)
    for problem in problems:
        for line in describe(problem, staged):
            print(line, file=sys.stderr)
    if not problems:
        return None
    if not staged:
        return EXIT_TOOLCHAIN
    print(skip_summary(toolchain, problems), file=sys.stderr)
    return EXIT_OK


def regenerate(
    root: Path, args: argparse.Namespace, toolchain: Toolchain
) -> tuple[int, Sequence[Finding]]:
    """Render one root: how many renders, and its findings. Publishing comes before the checks,
    so under `--check` alone DRC-10 compares the committed renders with the fresh ones."""
    tokens = read_style(root)
    with tempfile.TemporaryDirectory(prefix="diagram-regen-") as work:
        built = Path(work)
        try:
            projection = build_root(toolchain, root, tokens, built)
        except RegenerationError as stopped:
            report([regeneration_finding(stopped.failure)], args)
            raise
        if not args.check:
            publish(built, root / RENDER_DIR)
        findings = run_checks(projection, built, root)
    if args.staged:
        stage(root / RENDER_DIR)
    report(findings, args)
    log(f"{root}: {len(projection.views)} renders {'checked' if args.check else 'written'}")
    return len(projection.views), findings


# --- what the command says -------------------------------------------------------------------


def report(findings: Sequence[Finding], args: argparse.Namespace) -> None:
    """Findings go to stdout (`--check`: all of them; otherwise the failed ones), or under
    `--staged` to stderr as non-blocking warnings."""
    for finding in findings:
        failed = finding.status == "FAIL"
        if args.staged:
            if failed:
                line = f"{finding.check} {finding.view} {finding.evidence}"
                print(f"{LOG} WARN {line}", file=sys.stderr)
        elif failed or args.check:
            print(format_finding(finding, as_json=args.json))


def format_finding(finding: Finding, as_json: bool) -> str:
    if as_json:
        return json.dumps(asdict(finding), ensure_ascii=False)
    return f"{finding.check} {finding.view} {finding.status} {finding.evidence}"


def format_failure(failure: RegenerationFailure) -> str:
    """PC-1's three lines; a multi-line cause (a command, then its stderr) is indented."""
    cause = failure.cause.splitlines() or [""]
    return "\n".join(
        [
            f"{LOG} FAIL {failure.kind} {failure.target}: {failure.what}",
            f"{LOG}   cause: {cause[0]}",
            *[f"{LOG}     {line}" for line in cause[1:]],
            f"{LOG}   fix: {failure.fix}",
        ]
    )


def describe(problem: ToolProblem, staged: bool) -> list[str]:
    """The lines saying why a tool cannot be used, as warnings under `--staged`."""
    tool, pin = problem.tool, problem.required
    lead = f"{LOG} WARN" if staged else LOG
    fix = f"{LOG}   fix: {INSTALL[tool]}"
    if problem.found is None:
        action = SKIPPING if staged else f"{pin} is required"
        return [f"{lead} {tool} is not installed (not on PATH); {action}", fix]
    action = SKIPPING if staged else "refusing to regenerate with another version"
    return [f"{lead} {tool} {problem.found} found but {pin} is pinned; {action}", fix]


def skip_summary(toolchain: Toolchain, problems: Sequence[ToolProblem]) -> str:
    """The `--staged` skip line: every pin beside what was found, and that nothing was written."""
    found = {problem.tool: problem.found or "not on PATH" for problem in problems}
    pins = toolchain.required.items()
    pinned = " and ".join(f"{tool} {pin}" for tool, pin in pins)
    seen = " and ".join(f"{tool} {found.get(tool, pin)}" for tool, pin in pins)
    return (
        f"{LOG} WARN pinned {pinned}; found {seen}; nothing regenerated or staged,"
        " the CI drift gate still checks the renders"
    )


def log(message: str) -> None:
    print(f"{LOG} {message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
