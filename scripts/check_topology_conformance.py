#!/usr/bin/env python3
"""TT01/TT02/TT05/TT06: test-topology conformance checks.

Reads `.ai-state/TEST_TOPOLOGY.md` through the existing `_topology_yaml.py` parser
(`iter_yaml_blocks` + `parse_yaml_subset` -- reused, not re-parsed) and checks the
declared groups against three independent authorities:

* **TT01** (fail) -- every group's `subsystems` entry names a component that has a
  row in `.ai-state/DESIGN.md` **section 3a** (structural components) *and* whose
  `Status` column contains "Built". Section 3b capabilities are cross-cutting and
  are never valid test-group boundaries (`test-topology.md`'s own distinction).
* **TT02** (fail/warn) -- every group's `selectors[].strategy` value is a
  registered identifier in Registry 1 of `skills/testing-strategy/references/
  test-topology.md`. Unregistered -> fail. Registered but documented "Optional"
  in the registry's own description (today: `pytest-keywords`) -> warn, mirroring
  the leaf's own "prefer `pytest-markers` for declared groups" guidance.
* **TT05** (fail) -- for every group whose `selectors` includes a `pytest-markers`
  entry: (a) the kebab->snake_case form of the group id must be registered in the
  repo-root `pyproject.toml`'s `[tool.pytest.ini_options] markers` list; (b) that
  same form must not collide with the reserved-name set (`## Reserved Name Set` in
  the trunk, extended by `### Reserved Name Set` in every `*-testing.md` leaf under
  the same directory). A collision is reported instead of, not in addition to, a
  missing-registration finding -- renaming the group id is the only fix either way.
* **TT06** (info, never fail) -- runs whether or not `TEST_TOPOLOGY.md` exists.
  Skips (returns no finding) when the file is present. Otherwise measures the three
  Growth-Trigger Policy signals (`skills/testing-strategy/references/
  test-topology.md` §"Growth-Trigger Policy"): Built §3a component count, static
  test-function count under the declared pytest `testpaths`, and full-suite
  wall-clock runtime. **The runtime signal is not cheaply measurable** (computing it
  means running the suite, which this check must not do) -- no `.ai-state/`
  location records it today, so `_recorded_full_suite_runtime` always returns
  `None` and the term is reported `withheld`. If a future convention starts
  recording it, that one function is the seam to wire it through; until then the
  three-signal advisory can be exercised only via that seam (see the canary).
  Emits an INFO advisory only when all three signals are confirmed crossed. Never
  writes `.ai-state/TEST_TOPOLOGY.md` or a ledger row.

Skip conditions (DS-A, keyed): `.ai-state/TEST_TOPOLOGY.md` absent -> TT01, TT02,
TT05 skip (TT06 does not skip -- see above). `.ai-state/DESIGN.md` absent -> TT01
skips (TT06's component-count term withholds instead of skipping, since TT06 runs
regardless). The leaf file absent -> TT02, TT05 skip. `TEST_TOPOLOGY.md` present
but unparseable by the closed YAML subset -> TT01, TT02, TT05 skip with the parse
error recorded (structural validation of the file itself is `resolve_test_scope.py`
/ `--tests`-field consumers' job, not this check's).

Invocation:

    check_topology_conformance.py                  # human-readable summary
    check_topology_conformance.py --json           # machine-readable envelope
    check_topology_conformance.py --check          # exit 1 on any finding
    check_topology_conformance.py --repo-root DIR  # operate on another checkout
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging
from _topology_yaml import TopologyError, iter_yaml_blocks, parse_yaml_subset
from state_ledger_schema import split_row

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_NAME = "check_topology_conformance"

CHECK_IDS: tuple[str, ...] = ("TT01", "TT02", "TT05", "TT06")

_TOPOLOGY_REL = ".ai-state/TEST_TOPOLOGY.md"
_DESIGN_REL = ".ai-state/DESIGN.md"
_LEAF_REL = "skills/testing-strategy/references/test-topology.md"
_LEAF_DIR_REL = "skills/testing-strategy/references"

# Growth-Trigger Policy thresholds (test-topology.md §"Growth-Trigger Policy").
# Fixed numeric constants the trunk names in prose, not a table row -- kept here
# as named constants rather than re-parsed from running English.
_RUNTIME_THRESHOLD_SECONDS = 90
_COMPONENT_THRESHOLD = 4
_TEST_COUNT_THRESHOLD = 200

_SECTION_3A = re.compile(r"^###\s*3a\b")
_SECTION_NEXT = re.compile(r"^###?\s")
_STATUS_BUILT = re.compile(r"\bBuilt\b")
_REGISTRY_HEADING = re.compile(r"^##\s*Selector Strategy Registry\b")
_RESERVED_HEADING = re.compile(r"^#{2,3}\s*Reserved Name Set\b")
_BULLET_LINE = re.compile(r"^-\s")
_BACKTICK_IDENT = re.compile(r"`([a-zA-Z0-9_.-]+)`")
_TEST_FUNC = re.compile(r"^\s*def test_[a-zA-Z0-9_]*\(")
_MARKER_NAME = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:")

logger = logging.getLogger(SCRIPT_NAME)


# -- shared table parsing -----------------------------------------------------


def _markdown_table_rows(lines: list[str]) -> tuple[list[str], list[list[str]]] | None:
    """The first `| header | ... |` table found in `lines`, as (header, data rows).

    Lowercases the header for case-insensitive column lookup; drops the
    separator row (`|---|---|`); returns None when no table opens.
    """
    header: list[str] | None = None
    rows: list[list[str]] = []
    for line in lines:
        if not line.startswith("|"):
            if header is not None:
                break  # table has ended
            continue
        cells = split_row(line)  # honours `\|` escapes -- a literal pipe in prose
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        rows.append(cells)
    if header is None:
        return None
    return header, rows


# -- TT01: subsystems -> DESIGN.md §3a Status: Built --------------------------


def _parse_3a_status(design_text: str) -> dict[str, str]:
    """Component name -> Status text, for every row in DESIGN.md's §3a table."""
    lines = design_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _SECTION_3A.match(line))
    except StopIteration:
        return {}
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _SECTION_NEXT.match(line):
            break
        body.append(line)
    parsed = _markdown_table_rows(body)
    if parsed is None:
        return {}
    header, rows = parsed
    try:
        name_col = header.index("component")
        status_col = header.index("status")
    except ValueError:
        return {}
    return {
        row[name_col].strip("`").strip(): row[status_col]
        for row in rows
        if len(row) > max(name_col, status_col) and row[name_col].strip("`").strip()
    }


def _check_tt01(groups: list[dict[str, Any]], built_status: dict[str, str]) -> list[dict]:
    findings: list[dict] = []
    for group in groups:
        group_id = group.get("id")
        subsystems = group.get("subsystems")
        if not isinstance(subsystems, list):
            continue
        for entry in subsystems:
            if not isinstance(entry, str):
                continue
            status = built_status.get(entry)
            if status is None:
                findings.append(
                    {
                        "check": "TT01",
                        "severity": "fail",
                        "entity": f"{group_id}:{entry}",
                        "message": (
                            f"group '{group_id}': subsystems entry '{entry}' has no row "
                            "in DESIGN.md §3a"
                        ),
                    }
                )
            elif not _STATUS_BUILT.search(status):
                findings.append(
                    {
                        "check": "TT01",
                        "severity": "fail",
                        "entity": f"{group_id}:{entry}",
                        "message": (
                            f"group '{group_id}': subsystems entry '{entry}' is not "
                            f"Status: Built (found '{status}')"
                        ),
                    }
                )
    return findings


# -- TT02: selector strategy registration -------------------------------------


def _parse_registry1(leaf_text: str) -> dict[str, bool]:
    """Registered `strategy` identifier -> whether the leaf documents it "Optional"."""
    lines = leaf_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _REGISTRY_HEADING.match(line))
    except StopIteration:
        return {}
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#") and body:
            break
        body.append(line)
    parsed = _markdown_table_rows(body)
    if parsed is None:
        return {}
    _header, rows = parsed
    identifiers: dict[str, bool] = {}
    for row in rows:
        if not row:
            continue
        match = _BACKTICK_IDENT.search(row[0])
        if not match:
            continue
        identifiers[match.group(1)] = "Optional" in row[-1]
    return identifiers


def _check_tt02(groups: list[dict[str, Any]], registry: dict[str, bool]) -> list[dict]:
    findings: list[dict] = []
    for group in groups:
        group_id = group.get("id")
        selectors = group.get("selectors")
        if not isinstance(selectors, list):
            continue
        for selector in selectors:
            if not isinstance(selector, dict):
                continue
            strategy = selector.get("strategy")
            if not isinstance(strategy, str):
                continue
            if strategy not in registry:
                findings.append(
                    {
                        "check": "TT02",
                        "severity": "fail",
                        "entity": f"{group_id}:{strategy}",
                        "message": (
                            f"group '{group_id}': selector strategy '{strategy}' is not "
                            "registered in Registry 1"
                        ),
                    }
                )
            elif registry[strategy]:
                findings.append(
                    {
                        "check": "TT02",
                        "severity": "warn",
                        "entity": f"{group_id}:{strategy}",
                        "message": (
                            f"group '{group_id}': selector strategy '{strategy}' is "
                            "documented as optional in the leaf -- prefer a non-optional "
                            "strategy for a declared group"
                        ),
                    }
                )
    return findings


# -- TT05: marker-name consistency and reserved-name compliance --------------


def _leaf_reserved_names(text: str) -> set[str]:
    lines = text.splitlines()
    names: set[str] = set()
    in_section = False
    for line in lines:
        if _RESERVED_HEADING.match(line):
            in_section = True
            continue
        if in_section and line.startswith("#"):
            break
        if in_section and _BULLET_LINE.match(line):
            names.update(_BACKTICK_IDENT.findall(line))
    return names


def _reserved_name_set(repo_root: Path) -> set[str]:
    """Trunk `## Reserved Name Set` union every `*-testing.md` leaf's own section."""
    testing_dir = repo_root / _LEAF_DIR_REL
    names: set[str] = set()
    trunk = repo_root / _LEAF_REL
    if trunk.is_file():
        names |= _leaf_reserved_names(trunk.read_text(encoding="utf-8"))
    if testing_dir.is_dir():
        for leaf in sorted(testing_dir.glob("*-testing.md")):
            names |= _leaf_reserved_names(leaf.read_text(encoding="utf-8"))
    return names


def _registered_pytest_markers(repo_root: Path) -> set[str] | None:
    """Marker names declared in the repo-root `pyproject.toml`, or None if unreadable.

    Single-pocket scope, deliberately: the live corpus's `TEST_TOPOLOGY.md` has no
    `pytest-markers` group today (all thirteen groups use `pytest-globs`), so there
    is no multi-pocket instance to design against yet. A project that needs
    per-pocket resolution extends this, not the trunk schema.
    """
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - exercised only under < 3.11
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    markers = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    names: set[str] = set()
    if isinstance(markers, list):
        for entry in markers:
            if isinstance(entry, str):
                match = _MARKER_NAME.match(entry)
                if match:
                    names.add(match.group(1))
    return names


def _check_tt05(
    groups: list[dict[str, Any]], repo_root: Path, reserved: set[str]
) -> tuple[list[dict], dict[str, Any]]:
    marker_groups = [
        group
        for group in groups
        if isinstance(group.get("selectors"), list)
        and any(
            isinstance(selector, dict) and selector.get("strategy") == "pytest-markers"
            for selector in group["selectors"]
        )
    ]
    info: dict[str, Any] = {"marker_groups": len(marker_groups)}
    if not marker_groups:
        return [], info

    registered = _registered_pytest_markers(repo_root)
    info["markers_registration_readable"] = registered is not None
    findings: list[dict] = []
    for group in marker_groups:
        group_id = group.get("id")
        if not isinstance(group_id, str):
            continue
        snake = group_id.replace("-", "_")
        if snake in reserved:
            findings.append(
                {
                    "check": "TT05",
                    "severity": "fail",
                    "entity": group_id,
                    "message": (
                        f"group '{group_id}': marker form '{snake}' collides with the "
                        "reserved-name set"
                    ),
                }
            )
            continue  # renaming the group id is the only fix either way
        if registered is not None and snake not in registered:
            findings.append(
                {
                    "check": "TT05",
                    "severity": "fail",
                    "entity": group_id,
                    "message": (
                        f"group '{group_id}': marker form '{snake}' is not registered in "
                        "pyproject.toml's pytest markers"
                    ),
                }
            )
    return findings, info


# -- TT06: topology-less growth-trigger advisory -------------------------------


def _pytest_testpaths(repo_root: Path) -> list[str]:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - exercised only under < 3.11
        return []
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    paths = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("testpaths", [])
    return [p for p in paths if isinstance(p, str)]


def _count_tests(repo_root: Path) -> int:
    """Static `def test_*(` count under the declared pytest `testpaths`.

    Deliberately not `pytest --collect-only`: TT06's own row says full-suite
    *runtime* is not cheaply measurable, and invoking the runner to only count
    tests pays most of that cost for a number a grep answers in milliseconds. A
    def-count over/under-counts at the margins (parametrization, generated
    tests), acceptable for the coarse >=200 growth signal this feeds.
    """
    testpaths = _pytest_testpaths(repo_root) or ["tests"]
    count = 0
    for rel in testpaths:
        base = repo_root / rel
        if not base.exists():
            continue
        files = (
            [base]
            if base.is_file()
            else sorted(set(base.rglob("test_*.py")) | set(base.rglob("*_test.py")))
        )
        for file in files:
            if not file.is_file():
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except OSError:
                continue
            count += sum(1 for line in text.splitlines() if _TEST_FUNC.match(line))
    return count


def _recorded_full_suite_runtime(repo_root: Path) -> float | None:
    """A previously-recorded full-suite wall-clock figure, or None.

    No `.ai-state/` location records this today (confirmed: no schema, no
    producer). Running the suite here to measure it would violate TT06's own
    "not cheaply measurable" premise, so this always withholds. This function is
    the seam a future recording convention wires through -- see the module
    docstring and this check's canary, which exercises the crossed-all-three path
    by monkeypatching this one function rather than by inventing a file format.
    """
    del repo_root  # unused until a recording convention exists
    return None


def _check_tt06(repo_root: Path) -> tuple[list[dict], dict[str, Any]]:
    topology_present = (repo_root / _TOPOLOGY_REL).is_file()
    if topology_present:
        return [], {"reason": "topology-present"}

    design_path = repo_root / _DESIGN_REL
    component_count: int | None = None
    if design_path.is_file():
        built_status = _parse_3a_status(design_path.read_text(encoding="utf-8"))
        component_count = sum(1 for status in built_status.values() if _STATUS_BUILT.search(status))

    test_count = _count_tests(repo_root)
    runtime_seconds = _recorded_full_suite_runtime(repo_root)

    crossed: list[str] = []
    withheld_terms: list[str] = []

    if runtime_seconds is None:
        withheld_terms.append("full-suite wall-clock runtime")
    elif runtime_seconds >= _RUNTIME_THRESHOLD_SECONDS:
        crossed.append(f"full-suite wall-clock runtime ({runtime_seconds:.0f}s)")

    if component_count is None:
        withheld_terms.append("Built structural components (DESIGN.md absent)")
    elif component_count >= _COMPONENT_THRESHOLD:
        crossed.append(f"Built structural components ({component_count})")

    if test_count >= _TEST_COUNT_THRESHOLD:
        crossed.append(f"test count ({test_count})")

    info: dict[str, Any] = {
        "component_count": component_count,
        "test_count": test_count,
        "runtime_seconds": runtime_seconds,
        "crossed": crossed,
        "withheld_terms": withheld_terms,
    }

    findings: list[dict] = []
    if len(crossed) == 3:
        findings.append(
            {
                "check": "TT06",
                "severity": "info",
                "entity": _TOPOLOGY_REL,
                "message": (
                    "adoption thresholds crossed: "
                    + "; ".join(crossed)
                    + " -- run `/refresh-topology --init`"
                ),
            }
        )
    return findings, info


# -- Envelope (DS-A, keyed) -------------------------------------------------------


def classify(repo_root: Path) -> dict:
    findings: list[dict] = []
    skipped: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)
    examined: dict[str, dict | None] = dict.fromkeys(CHECK_IDS)

    topology_path = repo_root / _TOPOLOGY_REL
    if not topology_path.is_file():
        reason = {"reason": "substrate-absent", "path": str(topology_path)}
        skipped["TT01"] = reason
        skipped["TT02"] = reason
        skipped["TT05"] = reason
    else:
        text = topology_path.read_text(encoding="utf-8")
        groups: list[dict[str, Any]] | None
        try:
            groups = [
                block
                for body, lineno in iter_yaml_blocks(text, str(topology_path))
                if isinstance(
                    (block := parse_yaml_subset(body, str(topology_path), lineno)).get("id"), str
                )
            ]
        except TopologyError as exc:
            reason = {"reason": "topology-unparseable", "detail": str(exc)}
            skipped["TT01"] = reason
            skipped["TT02"] = reason
            skipped["TT05"] = reason
            groups = None

        if groups is not None:
            examined["TT01"] = {"groups": len(groups)}
            examined["TT02"] = {"groups": len(groups)}
            examined["TT05"] = {"groups": len(groups)}

            design_path = repo_root / _DESIGN_REL
            if design_path.is_file():
                built_status = _parse_3a_status(design_path.read_text(encoding="utf-8"))
                findings.extend(_check_tt01(groups, built_status))
            else:
                skipped["TT01"] = {"reason": "substrate-absent", "path": str(design_path)}

            leaf_path = repo_root / _LEAF_REL
            if leaf_path.is_file():
                registry = _parse_registry1(leaf_path.read_text(encoding="utf-8"))
                findings.extend(_check_tt02(groups, registry))
                reserved = _reserved_name_set(repo_root)
                tt05_findings, tt05_info = _check_tt05(groups, repo_root, reserved)
                findings.extend(tt05_findings)
                examined["TT05"] = {**examined["TT05"], **tt05_info}
            else:
                reason = {"reason": "substrate-absent", "path": str(leaf_path)}
                skipped["TT02"] = reason
                skipped["TT05"] = reason

    tt06_findings, tt06_info = _check_tt06(repo_root)
    findings.extend(tt06_findings)
    examined["TT06"] = tt06_info

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "skipped": skipped,
        "examined": examined,
        "findings": findings,
        "info": {},
        "withheld": [],
        "bound": {
            "TT01": "TT01 clean means every group's subsystems resolve to a Built §3a component.",
            "TT02": "TT02 clean means every selector strategy is registered (or flagged optional).",
            "TT05": "TT05 clean means every marker-selector group id is registered and collision-free.",
            "TT06": "TT06 never fails -- it advises adoption when all three growth signals are confirmed crossed.",
        },
    }


# -- CLI ----------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Advisory: test-topology conformance checks. Called by sentinel TT01/TT02/TT05/TT06."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(report: dict) -> str:
    findings = report["findings"]
    if not findings:
        return f"{SCRIPT_NAME}: no findings across {', '.join(CHECK_IDS)}."
    lines = [f"{SCRIPT_NAME}: {len(findings)} finding(s):"]
    lines.extend(f"  - [{f['check']}/{f['severity']}] {f['message']}" for f in findings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = _format_human(report)
        print(text, file=sys.stderr if report["findings"] else sys.stdout)

    return 1 if (args.check and report["findings"]) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("%s: %s", SCRIPT_NAME, exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
