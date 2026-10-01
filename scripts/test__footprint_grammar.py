"""Tests for `_footprint_grammar.py` -- the shared contract of the footprint check.

The failure mode this closes: a footprint criterion, a registry row or a
measurement row that breaks its grammar passing silently, so a bounded
footprint reaches the verifier unmeasured. Each grammar test holds golden good
rows and one golden bad row per malformed reason (`_footprint_testkit.py`); a
bad row is the canary that the parse-level check fires, and each case names the
exact rows that survive it, so a parser that drops more than the bad row is
caught too.

Later lanes cite the five pinning tests by node name; do not rename them.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _footprint_grammar as fg  # noqa: E402
from _footprint_testkit import (  # noqa: E402
    BUDGET_COMMAND,
    CRITERIA_HEADER,
    CRITERIA_ONLY,
    DECLARATION_HEADER,
    LOG_CASES,
    LOG_HEADER,
    LOG_STRAY_ROW,
    REGISTRY_CASES,
    REGISTRY_HEADER,
    SPEC_CASES,
    criterion_row,
    fenced,
    log_row,
    plan,
    plan_under,
    registry_row,
    table,
)

SCRIPTS = Path(__file__).resolve().parent
PRIVATE_SIBLINGS = ("_markdown_tables", "_footprint_grammar")
MODULES = tuple(SCRIPTS / f"{name}.py" for name in (*PRIVATE_SIBLINGS, "check_footprint_criteria"))
_IMPORT_PROGRAM = (
    "import importlib, sys; sys.path.insert(0, sys.argv[1]); importlib.import_module(sys.argv[2])"
)
CLI_TOKENS = ("--stage", "--paths", "--base-ref", "--repo-root", "--json", "schema")


def _sole_finding(findings: tuple[fg.Finding, ...], label: str) -> fg.Finding:
    assert len(findings) == 1, f"{label}: expected exactly one finding, got {findings}"
    return findings[0]


def _criteria_ids(parsed: fg.SpecTables) -> list[str]:
    return [c.id for c in parsed.criteria]


def _footprint_names(parsed: fg.RegistryParse) -> list[str]:
    return [f.name for f in parsed.registry.footprints]


def _measured_criteria(parsed: fg.LogParse) -> list[str]:
    return [m.criterion for m in parsed.measurements]


def _assert_each_case(parse, cases, expected: tuple[str, str, str], survivors) -> None:
    code, severity, kind = expected
    for case in cases:
        parsed = parse(case.text)
        finding = _sole_finding(parsed.findings, case.label)
        assert (finding.code, finding.severity, finding.reason) == (code, severity, case.reason), (
            case.label
        )
        assert survivors(parsed) == case.survivors, f"{kind} {case.label}"


# --- spec tables ----------------------------------------------------------------------------

GOLDEN_SPEC = plan(
    table(
        CRITERIA_HEADER,
        criterion_row(
            id="FC-01",
            footprint="always-loaded-tokens",
            metric="always-loaded token count",
            limit="16,726 tokens",
            against="baseline: 16,726 tokens, recorded before the first production change",
            command=BUDGET_COMMAND,
        ),
        criterion_row(
            id="FC-02",
            footprint="test-suite",
            comparator="exactly",
            limit="0",
            against="Reference: absolute zero",
            command="`pytest -q \\| tail -n 3`",
        ),
    ),
    table(
        DECLARATION_HEADER,
        "| spawn-count | the only spawn-count command counts a pipeline that has already run |",
    ),
)
GOLDEN_CRITERIA = (
    fg.Criterion(
        id="FC-01",
        footprint="always-loaded-tokens",
        metric="always-loaded token count",
        comparator="at or below",
        limit="16,726 tokens",
        against=fg.Baseline("16,726 tokens, recorded before the first production change"),
        command="python3 scripts/measure_token_budget.py --json",
    ),
    fg.Criterion(
        id="FC-02",
        footprint="test-suite",
        metric="lines in the longest prompt",
        comparator="exactly",
        limit="0",
        against=fg.Reference("absolute zero"),
        command="pytest -q | tail -n 3",
    ),
)
GOLDEN_DECLARATIONS = (
    fg.NotMeasured(
        "spawn-count", "the only spawn-count command counts a pipeline that has already run"
    ),
)


def test_parse_spec_tables_pins_golden_rows():
    parsed = fg.parse_spec_tables(GOLDEN_SPEC)

    assert parsed.findings == ()
    assert parsed.criteria == GOLDEN_CRITERIA
    assert parsed.not_measured == GOLDEN_DECLARATIONS
    # Neither table: today's spec shape, nothing parsed, nothing reported.
    assert fg.parse_spec_tables(plan()) == fg.SpecTables((), (), ())
    _assert_spec_examples_are_not_read()
    _assert_each_case(fg.parse_spec_tables, SPEC_CASES, ("FP02", "fail", "spec"), _criteria_ids)


def _assert_spec_examples_are_not_read() -> None:
    """A table or heading inside a code fence is an example: neither read nor reported."""
    example = fenced(table(CRITERIA_HEADER, criterion_row(id="FC-77", footprint="example")))
    ahead = fg.parse_spec_tables(plan(example + CRITERIA_ONLY))
    assert ahead.findings == ()
    assert _criteria_ids(ahead) == ["FC-09"]
    quoted = plan(rest="## Architecture\n\n### Footprint Criteria\n\n" + example)
    assert fg.parse_spec_tables(quoted) == fg.SpecTables((), (), ())
    example_heading = fenced("### Footprint Criteria\n\n" + CRITERIA_ONLY.replace("FC-09", "FC-77"))
    after_heading = "# Plan\n\n## Acceptance Criteria\n\n" + example_heading
    parsed = fg.parse_spec_tables(after_heading + "### Footprint Criteria\n\n" + CRITERIA_ONLY)
    assert parsed.findings == ()
    assert _criteria_ids(parsed) == ["FC-09"]


# --- code and generic tables are not misplaced criteria -------------------------------------

GENERIC_TABLE = table(DECLARATION_HEADER, "| risk | a rationale, not a footprint |")


def test_indented_and_nested_code_is_never_read_or_reported():
    indented = "    " + CRITERIA_ONLY.replace("\n", "\n    ").rstrip(" ")
    nested = "````\n```\n" + CRITERIA_ONLY + "```\n````\n"
    for label, quote in (("indented", indented), ("nested fence", nested)):
        parsed = fg.parse_spec_tables(plan(rest="## Architecture\n\n" + quote + "\n"))
        assert parsed == fg.SpecTables((), (), ()), label
    registry = fg.parse_registry(nested + table(REGISTRY_HEADER, registry_row()))
    assert registry.findings == ()
    assert _footprint_names(registry) == ["prompt-size"]


def test_generic_footprint_reason_table_outside_acceptance_is_not_a_misplaced_table():
    design = plan(rest="## Architecture\n\n" + GENERIC_TABLE)
    assert fg.parse_spec_tables(design) == fg.SpecTables((), (), ())
    # Inside `## Acceptance Criteria` the same shape is a renamed declarations heading.
    inside = fg.parse_spec_tables(plan_under("### Not measured", GENERIC_TABLE))
    assert [f.reason for f in inside.findings] == ["misplaced-table"]


def test_misplaced_table_message_gives_the_line_and_the_fence_remedy():
    text = plan_under("### Measured Footprints", CRITERIA_ONLY)
    line = text.splitlines().index(CRITERIA_ONLY.splitlines()[0]) + 1
    message = _sole_finding(fg.parse_spec_tables(text).findings, "misplaced").message
    assert f"line {line}:" in message
    assert "code fence" in message


# --- placeholders ---------------------------------------------------------------------------


def test_synonym_outside_the_placeholder_list_reads_as_a_real_reason():
    """The declared limit: the list is finite, so the verifier's judgment carries the rest."""
    for reason in ("TBD for now", "to be determined", "no instrument counts it", "none of them"):
        declared = table(DECLARATION_HEADER, f"| spawn-count | {reason} |")
        parsed = fg.parse_spec_tables(plan(CRITERIA_ONLY, declared))
        assert parsed.findings == (), reason
        assert [n.footprint for n in parsed.not_measured] == ["spawn-count"], reason


# --- registry -------------------------------------------------------------------------------


def test_parse_registry_pins_golden_rows():
    good = table(
        REGISTRY_HEADER,
        registry_row(),
        registry_row(
            "hook-latency", "hooks/*.py, hooks/hooks.json, !hooks/*test_*.py", "none", "—"
        ),
    )

    parsed = fg.parse_registry(good)

    assert parsed.findings == ()
    assert parsed.registry == fg.Registry(
        (
            fg.Footprint(
                name="prompt-size",
                include_globs=("agents/*.md",),
                exclude_globs=("agents/README.md",),
                command="python3 scripts/check_agent_prompt_size.py --json",
                reading="line counts",
            ),
            fg.Footprint(
                name="hook-latency",
                include_globs=("hooks/*.py", "hooks/hooks.json"),
                exclude_globs=("hooks/*test_*.py",),
                command=None,
                reading="—",
            ),
        )
    )
    # No registry file is a legal state, not a defect.
    assert fg.parse_registry(None) == fg.RegistryParse(fg.NoRegistry(), ())
    _assert_registry_edges(good)
    _assert_each_case(
        fg.parse_registry, REGISTRY_CASES, ("FP05", "warn", "registry"), _footprint_names
    )


def _assert_registry_edges(good: str) -> None:
    # Reading is optional, and `none` has one meaning whether or not it is backticked.
    no_reading = "| Footprint | Paths | Command |\n|---|---|---|\n| a-b | x/*.py | `none` |\n"
    parsed = fg.parse_registry(no_reading)
    assert parsed.findings == ()
    assert parsed.registry == fg.Registry((fg.Footprint("a-b", ("x/*.py",), (), None, ""),))
    # A fenced example ahead of the real table is not the table.
    parsed = fg.parse_registry(fenced(table(REGISTRY_HEADER, registry_row("example"))) + good)
    assert parsed.findings == ()
    assert _footprint_names(parsed) == ["prompt-size", "hook-latency"]


# --- measurement log ------------------------------------------------------------------------

GOLDEN_LOG = table(
    LOG_HEADER,
    log_row(),
    log_row(criterion="FC-02", phase="baseline", value="81.28 s", reading="estimate"),
    log_row(criterion="FC-01", phase="final", value="16800 tokens", head="0badf00d"),
    log_row(criterion="FC-03", phase="final", value="-", reading="none: tokenizer withheld"),
    log_row(criterion="FC-01", phase="final", value="16790 tokens", taken="2026-10-01T11:02Z"),
)
GOLDEN_KEYS = [
    ("FC-01", "baseline"),
    ("FC-02", "baseline"),
    ("FC-01", "final"),
    ("FC-03", "final"),
    ("FC-01", "final"),
]


def test_parse_measurements_pins_golden_rows():
    parsed = fg.parse_measurements(GOLDEN_LOG)

    assert parsed.findings == ()
    assert [(m.criterion, m.phase) for m in parsed.measurements] == GOLDEN_KEYS
    assert parsed.measurements[0] == fg.Measurement(
        criterion="FC-01",
        phase="baseline",
        value="16726 tokens",
        reading=fg.Measured(),
        head="f4d953a6",
        taken="2026-10-01T09:16Z",
        command="python3 scripts/measure_token_budget.py --json",
    )
    assert parsed.measurements[1].reading == fg.Estimate()
    assert parsed.measurements[3].reading == fg.NoReading("tokenizer withheld")
    _assert_latest_row_wins(parsed)
    _assert_log_edges(parsed)
    _assert_each_case(fg.parse_measurements, LOG_CASES, ("FP02", "fail", "log"), _measured_criteria)


def _assert_latest_row_wins(parsed: fg.LogParse) -> None:
    latest = fg.latest(parsed.measurements)
    assert set(latest) == set(GOLDEN_KEYS)
    assert latest[("FC-01", "final")].value == "16790 tokens"  # the later row in document order


def _assert_log_edges(parsed: fg.LogParse) -> None:
    # No log, a log with no rows yet, and a log that opens with a heading or a BOM are not defects.
    assert fg.parse_measurements("") == fg.LogParse((), ())
    assert fg.parse_measurements("# Measurements\n\n" + table(LOG_HEADER)) == fg.LogParse((), ())
    assert fg.parse_measurements("# Measurements\n") == fg.LogParse((), ())
    assert fg.parse_measurements("﻿" + GOLDEN_LOG).measurements == parsed.measurements
    # A fenced example ahead of the real table is not the table.
    example = fenced(table(LOG_HEADER, log_row(criterion="FC-77")))
    assert fg.parse_measurements(example + GOLDEN_LOG) == parsed
    assert fg.parse_measurements(LOG_STRAY_ROW).measurements == ()


# --- finding table and docstring ------------------------------------------------------------

STAGE_SET = ("spec", "plan", "verify")
EXPECTED_FINDING_TABLE = (
    fg.FindingSpec("FP01", "unbounded", "warn", ("plan", "verify"), ("unbounded",)),
    fg.FindingSpec(
        "FP02",
        "malformed",
        "fail",
        STAGE_SET,
        (
            *("bad-header", "empty-table", "missing-cell", "bad-id", "duplicate-id"),
            *("bad-against", "command-span", "reasonless", "bounded-and-declared"),
            *("unknown-criterion", "bad-phase", "bad-reading", "bad-head", "bad-taken"),
            *("misplaced-table", "stray-row", "extra-cell"),
        ),
    ),
    fg.FindingSpec(
        "FP03",
        "unmeasured",
        "fail",
        ("verify",),
        (
            *("missing-final", "missing-baseline", "no-reading", "stale-final"),
            *("late-baseline", "incomparable", "wrong-command"),
        ),
    ),
    fg.FindingSpec("FP04", "unregistered", "info", STAGE_SET, ("unregistered",)),
    fg.FindingSpec("FP05", "registry", "warn", STAGE_SET, ("malformed", "duplicate", "dead-glob")),
)


def test_finding_table_is_pinned():
    assert fg.FINDING_TABLE == EXPECTED_FINDING_TABLE
    assert fg.STAGES == STAGE_SET

    # The docstring is the one normative text: its table, parsed, is the finding table row by row.
    expected = {
        spec.code: [spec.name, spec.severity, ", ".join(spec.stages), ", ".join(spec.reasons)]
        for spec in fg.FINDING_TABLE
    }
    assert _docstring_finding_rows(fg.__doc__) == expected
    command_doc = ast.get_docstring(
        ast.parse((SCRIPTS / "check_footprint_criteria.py").read_text())
    )
    for token in CLI_TOKENS:
        assert token in command_doc, f"the command's docstring does not specify {token!r}"
    for placeholder in fg.PLACEHOLDER_REASONS:
        assert placeholder in fg.__doc__, f"module docstring omits the placeholder {placeholder!r}"
    _assert_make_finding_follows_the_table()


def _assert_make_finding_follows_the_table() -> None:
    """A finding takes its severity from the table, and an unknown reason is a programming error."""
    finding = fg.make_finding(
        "FP03", "stale-final", "the final row predates a change", criterion="FC-01"
    )
    assert (finding.severity, finding.criterion, finding.footprint) == ("fail", "FC-01", None)
    for code, reason in (("FP03", "typo"), ("FP09", "unbounded")):
        try:
            fg.make_finding(code, reason, "x")
        except ValueError:
            continue
        raise AssertionError(f"make_finding accepted {code}/{reason}")


def _docstring_finding_rows(doc: str) -> dict[str, list[str]]:
    """The docstring's finding table as {code: [name, severity, stages, reasons]}.

    Columns are separated by two or more spaces; a row's reasons may continue on
    the lines below it, which carry no code.
    """
    rows: dict[str, list[str]] = {}
    code = ""
    in_table = False
    for line in doc.splitlines():
        text = line.strip()
        if text.startswith("code  name"):
            in_table = True
        elif in_table and not text and rows:
            break
        elif in_table and text:
            parts = re.split(r"\s{2,}", text)
            if re.fullmatch(r"FP\d\d", parts[0]):
                code = parts[0]
                rows[code] = parts[1:]
            else:
                rows[code][-1] += " " + text
    return rows


# --- the modules themselves -----------------------------------------------------------------


def test_script_is_stdlib_only_and_python39_parseable():
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 9))
        assert not _foreign_imports(tree), f"{path.name}: non-stdlib imports"
        _assert_no_runtime_310_constructs(tree, path.name)

    # Each must import under a bare interpreter: isolated mode, no PYTHONPATH, only the scripts
    # directory on the path -- what a PATH-installed symlink to the command gives its siblings.
    for interpreter in (sys.executable, *_python39_interpreters()):
        for path in MODULES:
            result = subprocess.run(
                [interpreter, "-I", "-c", _IMPORT_PROGRAM, str(SCRIPTS), path.stem],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, f"{interpreter} {path.name}: {result.stderr}"


def test_stdlib_scan_flags_a_third_party_import_a_relative_one_and_an_unknown_sibling():
    for source in ("import yaml", "from yaml import safe_load", "from . import x", "import _other"):
        assert _foreign_imports(ast.parse(source)), source
    assert not _foreign_imports(ast.parse("import re\nfrom _markdown_tables import cells"))


def _foreign_imports(tree: ast.AST) -> set[str]:
    """Imports that are neither stdlib nor one of the footprint check's private siblings."""
    allowed = sys.stdlib_module_names | {*PRIVATE_SIBLINGS, "check_footprint_criteria"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." if node.level else (node.module or "").split(".")[0])
    return {name for name in found if name not in allowed}


def _assert_no_runtime_310_constructs(tree: ast.AST, name: str) -> None:
    """`feature_version` parses only syntax. What breaks a 3.9 import at run time is checked here:
    annotations must stay lazy, and no union operator, slotted or keyword-only dataclass, or
    `strict=` may be evaluated."""
    assert "annotations" in _future_imports(tree), f"{name}: annotations must be lazy for 3.9"
    in_annotation = _annotation_node_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            assert id(node) in in_annotation, f"{name}:{node.lineno}: a runtime `X | Y` needs 3.10"
        if isinstance(node, ast.keyword):
            assert node.arg not in {"slots", "kw_only", "strict"}, (
                f"{name}:{node.value.lineno}: `{node.arg}=` needs Python 3.10"
            )


def _future_imports(tree: ast.AST) -> set[str]:
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "__future__"
        for alias in node.names
    }


def _annotation_node_ids(tree: ast.AST) -> set[int]:
    """Ids of every node inside an annotation, which `from __future__ import annotations` keeps lazy."""
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg | ast.AnnAssign) and node.annotation is not None:
            roots.append(node.annotation)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.returns:
            roots.append(node.returns)
    return {id(inner) for root in roots for inner in ast.walk(root)}


def _python39_interpreters() -> list[str]:
    """Any Python 3.9 on this machine; the real proof, since the suite itself runs on 3.11+."""
    found = []
    for candidate in ("python3.9", "/usr/bin/python3"):
        path = shutil.which(candidate)
        if path is None:
            continue
        version = subprocess.run(
            [path, "--version"], capture_output=True, text=True, check=False
        ).stdout
        if version.startswith("Python 3.9"):
            found.append(path)
    return found
