#!/usr/bin/env python3
"""Measure how large the derived test selection is over recent history.

The method behind `skills/testing-strategy/references/test-selection.md`
§ Selection-Size Baseline, as code so every re-measurement is comparable:
take the change sets of the last N non-merge commits before a ref, hand each
to `resolve_test_scope.py --json --changed`, and report, for one pocket:

- how many change sets widened that pocket to its full suite;
- median and p90 selection size for the narrow runs, in test files and as a
  share of the pocket's test-file corpus;
- the same with widened runs counted as the whole corpus;
- the edge attribution (`via`) across the narrow selections.

Every run is over the current working tree: the graph is today's, not the
graph as it stood at each commit. `--compare-ref REF` also runs the resolver
exactly as it was at REF of this script's own repository (the resolver ships
with the script, not with the measured project) over the same tree and change
sets, so a change to the resolver itself can be measured before and after. `via` names only the
first source connecting a test, so the attribution is an upper bound on what
removing one source would drop.

Functional core: `summarize` is pure over parsed resolver output. The git and
subprocess calls live in the shell below it. Stdlib-only (it runs under a bare
`python3`). Exit 0 measured, 2 input error (no commits, unknown pocket,
resolver failure).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _repo_root import is_plugin_cache_path, resolve_repo_root  # noqa: E402
from _test_inventory import discover_pockets, is_test_file, project_files  # noqa: E402

# The resolver and the private siblings it imports; exported together for --compare-ref.
RESOLVER_MODULES = (
    "resolve_test_scope.py",
    "_declared_deps.py",
    "_test_inventory.py",
    "_python_selection.py",
    "_native_selection.py",
    "_repo_root.py",
)
DEFAULT_COMMITS = 50


class MeasureError(Exception):
    """An input the measurement cannot be trusted on; exit 2."""


# --- Pure core ---------------------------------------------------------------------


@dataclass(frozen=True)
class PocketRun:
    """One change set's outcome for the measured pocket."""

    widened: bool
    tests: tuple[tuple[str, str], ...]  # (test path, via), one entry per test file


@dataclass(frozen=True)
class Summary:
    corpus: int
    runs: int
    widened: int
    narrow_median: float
    narrow_p90: float
    all_median: float
    all_p90: float
    via_share: dict[str, float]

    def as_dict(self) -> dict:
        def pct(value: float) -> float:
            return round(100 * value / self.corpus, 1) if self.corpus else 0.0

        return {
            "corpus": self.corpus,
            "runs": self.runs,
            "widened": self.widened,
            "narrow": {
                "median": self.narrow_median,
                "p90": self.narrow_p90,
                "median_pct": pct(self.narrow_median),
                "p90_pct": pct(self.narrow_p90),
            },
            "all": {
                "median": self.all_median,
                "p90": self.all_p90,
                "median_pct": pct(self.all_median),
                "p90_pct": pct(self.all_p90),
            },
            "via_pct": {via: round(100 * share, 1) for via, share in self.via_share.items()},
        }


def pocket_run(output: dict, pocket_root: str) -> PocketRun:
    """The measured pocket's outcome in one resolver `--json` output."""
    for pocket in output.get("pockets", []):
        if pocket.get("root") != pocket_root:
            continue
        if pocket.get("selection") == "full":
            return PocketRun(widened=True, tests=())
        best: dict[str, str] = {}
        for test in pocket.get("tests", []):
            best.setdefault(test["path"], test["via"])
        return PocketRun(widened=False, tests=tuple(sorted(best.items())))
    return PocketRun(widened=False, tests=())  # the change set never touched this pocket


def _p90(values: Sequence[float]) -> float:
    # The default (exclusive) method, as the published baseline used; keep it so re-measurements compare.
    if len(values) == 1:
        return float(values[0])
    return statistics.quantiles(values, n=10)[8]


def summarize(runs: Sequence[PocketRun], corpus: int) -> Summary:
    if not runs:
        raise MeasureError("no change sets to measure")
    narrow = [len(run.tests) for run in runs if not run.widened]
    every = [corpus if run.widened else len(run.tests) for run in runs]
    vias = Counter(via for run in runs if not run.widened for _, via in run.tests)
    total = sum(vias.values())
    return Summary(
        corpus=corpus,
        runs=len(runs),
        widened=sum(run.widened for run in runs),
        narrow_median=float(statistics.median(narrow)) if narrow else 0.0,
        narrow_p90=_p90(narrow) if narrow else 0.0,
        all_median=float(statistics.median(every)),
        all_p90=_p90(every),
        via_share={via: count / total for via, count in vias.most_common()} if total else {},
    )


def render(label: str, summary: Summary) -> str:
    d = summary.as_dict()
    vias = ", ".join(f"{via} {pct}%" for via, pct in d["via_pct"].items()) or "none"
    return "\n".join(
        [
            f"{label}: corpus {d['corpus']} test files; widened {d['widened']} of {d['runs']}",
            f"  narrow median {d['narrow']['median']:g} ({d['narrow']['median_pct']}%), "
            f"p90 {d['narrow']['p90']:g} ({d['narrow']['p90_pct']}%)",
            f"  all    median {d['all']['median']:g} ({d['all']['median_pct']}%), "
            f"p90 {d['all']['p90']:g} ({d['all']['p90_pct']}%)",
            f"  via    {vias}",
        ]
    )


# --- I/O shell ---------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        raise MeasureError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def change_sets(root: Path, ref: str, count: int) -> list[list[str]]:
    commits = _git(root, "log", "--no-merges", f"-{count}", "--format=%H", ref).split()
    if not commits:
        raise MeasureError(f"no non-merge commits reachable from {ref}")
    sets = []
    for commit in commits:
        paths = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit)
        changed = [p for p in paths.splitlines() if p]
        if changed:
            sets.append(changed)
    return sets


def corpus_size(root: Path, pocket_root: str) -> int:
    files = project_files(root)
    pockets = {pocket.root: pocket for pocket in discover_pockets(root, files)}
    if pocket_root not in pockets:
        raise MeasureError(f"no pocket rooted at {pocket_root!r}; known: {sorted(pockets)}")
    pocket = pockets[pocket_root]
    return sum(
        1 for f in files if pocket.collection.covers(f) and is_test_file(f, pocket.ecosystem)
    )


def resolve(resolver: Path, root: Path, changed: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, str(resolver), "--repo-root", str(root), "--json", "--changed", *changed],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MeasureError(f"resolver exited {result.returncode}: {result.stderr.strip()[:300]}")
    return json.loads(result.stdout)


def measure(
    resolver: Path, root: Path, sets: list[list[str]], pocket_root: str, corpus: int
) -> Summary:
    return summarize([pocket_run(resolve(resolver, root, s), pocket_root) for s in sets], corpus)


def export_resolver(ref: str, into: Path) -> Path:
    """The resolver as it was at `ref` of the checkout this script lives in.

    The resolver ships with this script, not with the measured project, so `ref` names a
    commit of this script's own repository; a plugin-cache copy has no history to export.
    """
    home = Path(_git(SCRIPT_DIR, "rev-parse", "--show-toplevel").strip())
    for module in RESOLVER_MODULES:
        (into / module).write_text(_git(home, "show", f"{ref}:scripts/{module}"))
    return into / "resolve_test_scope.py"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ref", default="HEAD", help="last commit of the window (default HEAD)")
    parser.add_argument(
        "--commits",
        type=int,
        default=DEFAULT_COMMITS,
        help=f"non-merge commits in the window (default {DEFAULT_COMMITS})",
    )
    parser.add_argument("--pocket", default=".", help="pocket root to measure (default '.')")
    parser.add_argument("--compare-ref", help="also run the resolver as it was at this ref")
    parser.add_argument("--repo-root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    try:
        if is_plugin_cache_path(root):
            raise MeasureError(f"refusing a plugin-cache root: {root}")
        if args.commits < 1:
            raise MeasureError("--commits must be at least 1")
        sets = change_sets(root, args.ref, args.commits)
        corpus = corpus_size(root, args.pocket)
        results = {
            "current": measure(
                SCRIPT_DIR / "resolve_test_scope.py", root, sets, args.pocket, corpus
            )
        }
        if args.compare_ref:
            with tempfile.TemporaryDirectory() as tmp:
                base = export_resolver(args.compare_ref, Path(tmp))
                results = {
                    args.compare_ref: measure(base, root, sets, args.pocket, corpus),
                    **results,
                }
    except MeasureError as exc:
        print(f"measure_selection_size: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "ref": args.ref,
                    "pocket": args.pocket,
                    "results": {k: v.as_dict() for k, v in results.items()},
                },
                indent=2,
            )
        )
    else:
        print("\n".join(render(label, summary) for label, summary in results.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
