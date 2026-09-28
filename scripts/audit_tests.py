#!/usr/bin/env python3
"""Suite-failure auditor: junit in, "would selection have caught it?" records out.

    python3 scripts/audit_tests.py --junit FILE [--rerun FILE]
                                   [--changed PATH… | --changed-from REF]
                                   [--slow N] [--json]

Closes the loop the derived resolver (`resolve_test_scope.py`) opens: every
failure from a full-suite run is classified `real`/`flaky`/`unclassified`, and
every `real`/`unclassified` failure is checked against what the resolver would
have selected for the same change set -- `selected` (the narrow run would have
caught it), `widened` (the resolver would have run the full suite for that
pocket anyway), `missed` (the narrow run would have missed it -- a resolver
gap), or `unattributable` (no change set was given, or the failing test's own
file is untracked).

A `missed` failure's `suggested_edge` names every changed path as the entry to
add to `tests/declared-deps.toml`: selection is a union of sources, so if the
full changed set didn't connect to the test, no single path in it did either --
the whole set is exactly what the graph failed to connect.

Persistence is deliberately not a new `.ai-state` file: a record lands in the
integration checkpoint's `TEST_RESULTS.md` `Audit:` line, the scheduled
workflow's job summary, or a human's terminal. The closing commit -- the added
edge -- is the durable record.

`test`/`file` are read from junit's own `file`/`classname` attributes (pytest's
`xunit2` junit family emits both); a class-scoped test's reconstructed nodeid
(`file::name`, dropping the class segment) is an approximation this codebase's
dominant function-level test style rarely exercises.

Exit codes: `0` no `missed`/`flaky` failures; `1` at least one; `2` usage or a
junit file that will not parse.

Stdlib-only: it runs under a bare `python3` (gate-liveness GL05).
Tests and canaries: `scripts/test_audit_tests.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _repo_root import resolve_repo_root  # noqa: E402
from _test_inventory import pocket_of  # noqa: E402
from resolve_test_scope import (  # noqa: E402
    Full,
    Native,
    Resolution,
    Tests,
    changed_paths,
    repo_files,
    resolve,
)

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_VERSION = 1

CLASSIFICATION_REAL = "real"
CLASSIFICATION_FLAKY = "flaky"
CLASSIFICATION_UNCLASSIFIED = "unclassified"

SELECTION_SELECTED = "selected"
SELECTION_WIDENED = "widened"
SELECTION_MISSED = "missed"
SELECTION_UNATTRIBUTABLE = "unattributable"
SELECTION_NA = "n/a"

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class AuditError(RuntimeError):
    """A junit file this tool cannot read; the caller treats it as usage error."""


# --- Values ------------------------------------------------------------------


@dataclass(frozen=True)
class JunitCase:
    test: str
    file: str
    seconds: float


@dataclass(frozen=True)
class SuggestedEdge:
    paths: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass(frozen=True)
class AuditedFailure:
    test: str
    file: str
    classification: str
    selection: str
    suggested_edge: SuggestedEdge | None


# --- JUnit parsing -------------------------------------------------------------


def _split_classname(classname: str, known_files: frozenset[str] | None) -> tuple[str, list[str]]:
    """(file, classes) for a junit `classname` such as `scripts.test_x.TestFoo`.

    pytest writes the module path and any enclosing test classes as one dotted
    name, so the file is the longest dotted prefix that names a real `.py` file.
    Without a file list, the whole name is taken as the module (no classes).
    """
    parts = classname.split(".")
    if known_files is not None:
        for cut in range(len(parts), 0, -1):
            candidate = "/".join(parts[:cut]) + ".py"
            if candidate in known_files:
                return candidate, parts[cut:]
    return "/".join(parts) + ".py", []


def _nodeid(
    testcase: ElementTree.Element, known_files: frozenset[str] | None = None
) -> tuple[str, str]:
    """(nodeid, file) for one `<testcase>`, from its `file`/`classname`/`name`."""
    name = testcase.get("name", "")
    file = testcase.get("file") or ""
    classes: list[str] = []
    classname = testcase.get("classname", "")
    if classname:
        module_file, classes = _split_classname(classname, known_files)
        file = file or module_file
    if not file:
        return name, file
    return "::".join([file, *classes, name]), file


def parse_junit(path: Path, known_files: frozenset[str] | None = None) -> dict[str, JunitCase]:
    """Every test case in a junit XML file, keyed by nodeid, with its duration."""
    try:
        tree = ElementTree.parse(path)
    except (OSError, ElementTree.ParseError) as exc:
        raise AuditError(f"cannot parse {path}: {exc}") from exc
    cases: dict[str, JunitCase] = {}
    for testcase in tree.getroot().iter("testcase"):
        nodeid, file = _nodeid(testcase, known_files)
        cases[nodeid] = JunitCase(nodeid, file, float(testcase.get("time", 0.0)))
    return cases


def failing_cases(path: Path, known_files: frozenset[str] | None = None) -> dict[str, JunitCase]:
    """Nodeids with a `<failure>` or `<error>` child -- the run's red cases."""
    try:
        tree = ElementTree.parse(path)
    except (OSError, ElementTree.ParseError) as exc:
        raise AuditError(f"cannot parse {path}: {exc}") from exc
    failed: dict[str, JunitCase] = {}
    for testcase in tree.getroot().iter("testcase"):
        if testcase.find("failure") is None and testcase.find("error") is None:
            continue
        nodeid, file = _nodeid(testcase, known_files)
        failed[nodeid] = JunitCase(nodeid, file, float(testcase.get("time", 0.0)))
    return failed


# --- Classification and selection ---------------------------------------------


def _classify(nodeid: str, rerun_failed: set[str] | None) -> str:
    if rerun_failed is None:
        return CLASSIFICATION_UNCLASSIFIED
    return CLASSIFICATION_REAL if nodeid in rerun_failed else CLASSIFICATION_FLAKY


def _selection(
    file: str, resolution: Resolution | None, tracked: frozenset[str]
) -> tuple[str, SuggestedEdge | None]:
    if resolution is None or file not in tracked:
        return SELECTION_UNATTRIBUTABLE, None
    pockets = tuple(entry.pocket for entry in resolution.pockets)
    owning = pocket_of(file, pockets)
    result = next((entry for entry in resolution.pockets if entry.pocket == owning), None)
    if result is not None:
        if isinstance(result.selection, Full):
            return SELECTION_WIDENED, None
        if isinstance(result.selection, Native):
            return SELECTION_SELECTED, None
        if isinstance(result.selection, Tests) and any(
            t.path == file for t in result.selection.tests
        ):
            return SELECTION_SELECTED, None
    return SELECTION_MISSED, SuggestedEdge(resolution.changed.paths, (file,))


def audit(
    failed: dict[str, JunitCase],
    rerun_failed: dict[str, JunitCase] | None,
    resolution: Resolution | None,
    tracked: frozenset[str],
) -> list[AuditedFailure]:
    """One record per failing test: how it was classified, and how it would have fared."""
    rerun_ids = set(rerun_failed) if rerun_failed is not None else None
    audited: list[AuditedFailure] = []
    for nodeid, case in sorted(failed.items()):
        classification = _classify(nodeid, rerun_ids)
        if classification == CLASSIFICATION_FLAKY:
            selection, edge = SELECTION_NA, None
        else:
            selection, edge = _selection(case.file, resolution, tracked)
        audited.append(AuditedFailure(nodeid, case.file, classification, selection, edge))
    return audited


def slow_tests(cases: dict[str, JunitCase], count: int) -> list[dict[str, object]]:
    """The `count` slowest cases in the original run, passing or not."""
    ranked = sorted(cases.values(), key=lambda case: case.seconds, reverse=True)[:count]
    return [{"test": case.test, "seconds": round(case.seconds, 3)} for case in ranked]


# --- Output --------------------------------------------------------------------


def to_payload(
    junit: str,
    rerun: str | None,
    change: str | None,
    audited: Sequence[AuditedFailure],
    slow: Sequence[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema": SCHEMA_VERSION,
        "inputs": {"junit": junit, "rerun": rerun, "change": change},
        "failures": [_failure_payload(a) for a in audited],
        "slow": list(slow),
        "summary": {
            "failures": len(audited),
            "real": sum(1 for a in audited if a.classification == CLASSIFICATION_REAL),
            "flaky": sum(1 for a in audited if a.classification == CLASSIFICATION_FLAKY),
            "missed": sum(1 for a in audited if a.selection == SELECTION_MISSED),
        },
    }


def _failure_payload(failure: AuditedFailure) -> dict[str, object]:
    edge = failure.suggested_edge
    return {
        "test": failure.test,
        "file": failure.file,
        "classification": failure.classification,
        "selection": failure.selection,
        "suggested_edge": (
            {"paths": list(edge.paths), "tests": list(edge.tests)} if edge is not None else None
        ),
    }


def print_human(payload: dict[str, object]) -> None:
    summary = payload["summary"]
    print(f"# {summary['failures']} failure(s): {summary['real']} real, {summary['flaky']} flaky")
    for failure in payload["failures"]:
        print(f"  [{failure['classification']}/{failure['selection']}] {failure['test']}")
        edge = failure["suggested_edge"]
        if edge is not None:
            print(f"    suggested_edge: paths={edge['paths']} tests={edge['tests']}")
    for entry in payload["slow"]:
        print(f"# slow: {entry['seconds']:.3f}s {entry['test']}")
    print(f"# missed={summary['missed']}")


# --- CLI -------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a junit run against derived selection.")
    parser.add_argument("--junit", required=True, metavar="FILE", help="the run under audit")
    parser.add_argument("--rerun", metavar="FILE", help="a rerun of the failures, for flaky")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--changed", nargs="+", action="extend", metavar="PATH")
    mode.add_argument("--changed-from", metavar="REF")
    parser.add_argument("--slow", type=int, default=0, metavar="N", help="top-N slowest cases")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo-root")
    return parser


def _resolve_change(
    args: argparse.Namespace, repo_root: Path
) -> tuple[Resolution | None, list[str]]:
    files = repo_files(repo_root)
    if not (args.changed or args.changed_from):
        return None, files
    namespace = argparse.Namespace(changed=args.changed, changed_from=args.changed_from, full=False)
    changed = changed_paths(namespace, repo_root)
    return resolve(repo_root, changed, files), files


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    known = frozenset(repo_files(repo_root))
    try:
        cases = failing_cases(Path(args.junit), known)
        rerun_cases = failing_cases(Path(args.rerun), known) if args.rerun else None
    except AuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    resolution, files = _resolve_change(args, repo_root)
    audited = audit(cases, rerun_cases, resolution, frozenset(files))
    slow = slow_tests(parse_junit(Path(args.junit), known), args.slow) if args.slow else []
    change_desc = resolution.changed.source if resolution is not None else None
    payload = to_payload(args.junit, args.rerun, change_desc, audited, slow)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print_human(payload)
    return EXIT_FINDINGS if payload["summary"]["missed"] or payload["summary"]["flaky"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
