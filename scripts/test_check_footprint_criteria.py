"""Tests for `check_footprint_criteria.py` -- the shared contract of the footprint check.

The failure mode this closes: a footprint criterion, a registry row or a
measurement row that breaks its grammar passing silently, so a bounded
footprint reaches the verifier unmeasured. Each grammar test holds golden good
rows and one golden bad row per malformed reason; a bad row is the canary that
the parse-level check fires. Expected values come from the grammar in the
module docstring, not from running the implementation.

Later lanes cite the five pinning tests by node name; do not rename them.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_footprint_criteria as fc  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "check_footprint_criteria.py"

CRITERIA_HEADER = "| Id | Footprint | Metric | Comparator | Limit | Against | Command |"
DECLARATION_HEADER = "| Footprint | Reason |"
REGISTRY_HEADER = "| Footprint | Paths | Command | Reading |"
LOG_HEADER = "| Criterion | Phase | Value | Reading | Head | Taken | Command |"


# --- builders -------------------------------------------------------------------------------


def _table(header: str, *rows: str) -> str:
    separator = "|" + "---|" * (header.count("|") - 1)
    return "\n".join([header, separator, *rows]) + "\n"


def _criterion_row(**cells: str) -> str:
    row = {
        "id": "FC-01",
        "footprint": "prompt-size",
        "metric": "lines in the longest prompt",
        "comparator": "at or below",
        "limit": "400 lines",
        "against": "baseline: 398 lines",
        "command": "`python3 scripts/check_agent_prompt_size.py --json`",
        **cells,
    }
    return "| " + " | ".join(row.values()) + " |"


def _plan(criteria: str | None = None, declared: str | None = None, *, rest: str = "") -> str:
    parts = ["# Plan", "", "## Acceptance Criteria", "", "- [ ] The change behaves", ""]
    if criteria is not None:
        parts += ["### Footprint Criteria", "", criteria]
    if declared is not None:
        parts += ["### Footprints Not Measured", "", declared]
    return "\n".join(parts) + "\n" + rest


def _registry_row(
    name: str = "prompt-size",
    paths: str = "agents/*.md, !agents/README.md",
    command: str = "`python3 scripts/check_agent_prompt_size.py --json`",
    reading: str = "line counts",
) -> str:
    return f"| {name} | {paths} | {command} | {reading} |"


def _log_row(**cells: str) -> str:
    row = {
        "criterion": "FC-01",
        "phase": "baseline",
        "value": "16726 tokens",
        "reading": "measured",
        "head": "f4d953a6",
        "taken": "2026-10-01T09:16Z",
        "command": "`python3 scripts/measure_token_budget.py --json`",
        **cells,
    }
    return "| " + " | ".join(row.values()) + " |"


def _sole_finding(findings: tuple[fc.Finding, ...], label: str) -> fc.Finding:
    assert len(findings) == 1, f"{label}: expected exactly one finding, got {findings}"
    return findings[0]


# --- spec tables ----------------------------------------------------------------------------


def test_parse_spec_tables_pins_golden_rows():
    good = _plan(
        _table(
            CRITERIA_HEADER,
            _criterion_row(
                id="FC-01",
                footprint="always-loaded-tokens",
                metric="always-loaded token count",
                limit="16,726 tokens",
                against="baseline: 16,726 tokens, recorded before the first production change",
                command="`python3 scripts/measure_token_budget.py --json`",
            ),
            _criterion_row(
                id="FC-02",
                footprint="test-suite",
                comparator="exactly",
                limit="0",
                against="Reference: absolute zero",
                command="`pytest -q \\| tail -n 3`",
            ),
        ),
        _table(
            DECLARATION_HEADER,
            "| spawn-count | the only spawn-count command counts a pipeline that has already run |",
        ),
    )

    parsed = fc.parse_spec_tables(good)

    assert parsed.findings == ()
    assert parsed.criteria == (
        fc.Criterion(
            id="FC-01",
            footprint="always-loaded-tokens",
            metric="always-loaded token count",
            comparator="at or below",
            limit="16,726 tokens",
            against=fc.Baseline("16,726 tokens, recorded before the first production change"),
            command="python3 scripts/measure_token_budget.py --json",
        ),
        fc.Criterion(
            id="FC-02",
            footprint="test-suite",
            metric="lines in the longest prompt",
            comparator="exactly",
            limit="0",
            against=fc.Reference("absolute zero"),
            command="pytest -q | tail -n 3",
        ),
    )
    assert parsed.not_measured == (
        fc.NotMeasured(
            "spawn-count", "the only spawn-count command counts a pipeline that has already run"
        ),
    )

    # Neither table: today's spec shape, nothing parsed, nothing reported.
    assert fc.parse_spec_tables(_plan()) == fc.SpecTables((), (), ())
    # The same tables outside `## Acceptance Criteria` (a design section quoting them) are not read.
    quoted = _plan(
        rest="## Architecture\n\n### Footprint Criteria\n\n"
        + _table(CRITERIA_HEADER, _criterion_row())
    )
    assert fc.parse_spec_tables(quoted) == fc.SpecTables((), (), ())

    for label, plan, reason in _BAD_SPEC_PLANS:
        parsed = fc.parse_spec_tables(plan)
        finding = _sole_finding(parsed.findings, label)
        assert (finding.code, finding.severity, finding.reason) == ("FP02", "fail", reason), label
        assert [c.id for c in parsed.criteria] == list(_SURVIVORS[label]), label


_GOOD_ROW = _criterion_row(id="FC-09", footprint="other")
_BAD_SPEC_PLANS = [
    (
        "bad-header",
        _plan(
            _table(
                "| Idx | Footprint | Metric | Comparator | Limit | Against | Command |", _GOOD_ROW
            )
        ),
        "bad-header",
    ),
    ("empty-table (no table)", _plan("(none yet)\n"), "empty-table"),
    ("empty-table (header only)", _plan(_table(CRITERIA_HEADER)), "empty-table"),
    (
        "missing-cell",
        _plan(_table(CRITERIA_HEADER, _criterion_row(limit=" "), _GOOD_ROW)),
        "missing-cell",
    ),
    ("bad-id", _plan(_table(CRITERIA_HEADER, _criterion_row(id="FC-1"), _GOOD_ROW)), "bad-id"),
    (
        "duplicate-id",
        _plan(_table(CRITERIA_HEADER, _GOOD_ROW, _criterion_row(id="FC-09"))),
        "duplicate-id",
    ),
    (
        "bad-against (unknown prefix)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(against="absolute: 5"), _GOOD_ROW)),
        "bad-against",
    ),
    (
        "bad-against (prefix without text)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(against="baseline:"), _GOOD_ROW)),
        "bad-against",
    ),
    (
        "command-span (no span)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(command="run the thing"), _GOOD_ROW)),
        "command-span",
    ),
    (
        "command-span (two spans)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(command="`a` then `b`"), _GOOD_ROW)),
        "command-span",
    ),
    *[
        (
            f"reasonless ({placeholder})",
            _plan(
                _GOOD_ROW and _table(CRITERIA_HEADER, _GOOD_ROW),
                _table(DECLARATION_HEADER, f"| spawn-count | {placeholder} |"),
            ),
            "reasonless",
        )
        for placeholder in ("-", "—", "n/a", "NA", "None", "tbd", "TODO", "?")
    ],
    (
        "bounded-and-declared",
        _plan(
            _table(CRITERIA_HEADER, _GOOD_ROW),
            _table(DECLARATION_HEADER, "| Other | no instrument exists for it |"),
        ),
        "bounded-and-declared",
    ),
]
# The criteria that survive each bad plan: the bad row is dropped, its good sibling is kept.
_SURVIVORS = {
    "bad-header": [],
    "empty-table (no table)": [],
    "empty-table (header only)": [],
    "missing-cell": ["FC-09"],
    "bad-id": ["FC-09"],
    "duplicate-id": ["FC-09"],
    "bad-against (unknown prefix)": ["FC-09"],
    "bad-against (prefix without text)": ["FC-09"],
    "command-span (no span)": ["FC-09"],
    "command-span (two spans)": ["FC-09"],
    **{f"reasonless ({p})": ["FC-09"] for p in ("-", "—", "n/a", "NA", "None", "tbd", "TODO", "?")},
    "bounded-and-declared": ["FC-09"],
}


# --- registry -------------------------------------------------------------------------------


def test_parse_registry_pins_golden_rows():
    good = _table(
        REGISTRY_HEADER,
        _registry_row(),
        _registry_row(
            "hook-latency", "hooks/*.py, hooks/hooks.json, !hooks/*test_*.py", "none", "—"
        ),
    )

    parsed = fc.parse_registry(good)

    assert parsed.findings == ()
    assert parsed.registry == fc.Registry(
        (
            fc.Footprint(
                name="prompt-size",
                include_globs=("agents/*.md",),
                exclude_globs=("agents/README.md",),
                command="python3 scripts/check_agent_prompt_size.py --json",
                reading="line counts",
            ),
            fc.Footprint(
                name="hook-latency",
                include_globs=("hooks/*.py", "hooks/hooks.json"),
                exclude_globs=("hooks/*test_*.py",),
                command=None,
                reading="—",
            ),
        )
    )
    # No registry file is a legal state, not a defect.
    assert fc.parse_registry(None) == fc.RegistryParse(fc.NoRegistry(), ())

    sibling = _registry_row("sibling", "src/*.py", "none", "none")
    bad_rows = [
        (
            "bad-header",
            "| Footprint | Globs | Command |\n|---|---|---|\n| a | b/* | none |\n",
            "malformed",
        ),
        ("no table", "# Footprints\n\nnothing here\n", "malformed"),
        ("header only", _table(REGISTRY_HEADER), "malformed"),
        (
            "uppercase name",
            _table(REGISTRY_HEADER, _registry_row("Prompt-Size"), sibling),
            "malformed",
        ),
        (
            "snake_case name",
            _table(REGISTRY_HEADER, _registry_row("prompt_size"), sibling),
            "malformed",
        ),
        ("empty paths", _table(REGISTRY_HEADER, _registry_row(paths=" "), sibling), "malformed"),
        (
            "exclude-only paths",
            _table(REGISTRY_HEADER, _registry_row(paths="!agents/*.md"), sibling),
            "malformed",
        ),
        (
            "command is prose",
            _table(REGISTRY_HEADER, _registry_row(command="run it"), sibling),
            "malformed",
        ),
        (
            "command has two spans",
            _table(REGISTRY_HEADER, _registry_row(command="`a` `b`"), sibling),
            "malformed",
        ),
        (
            "duplicate name",
            _table(
                REGISTRY_HEADER, _registry_row("sibling", "other/*.py", "none", "none"), sibling
            ),
            "duplicate",
        ),
    ]
    for label, text, reason in bad_rows:
        parsed = fc.parse_registry(text)
        finding = _sole_finding(parsed.findings, label)
        assert (finding.code, finding.severity, finding.reason) == ("FP05", "warn", reason), label
        names = [f.name for f in parsed.registry.footprints]
        assert names in ([], ["sibling"]), (label, names)
        assert "prompt-size" not in names, label
        assert "prompt_size" not in names, label


# --- measurement log ------------------------------------------------------------------------


def test_parse_measurements_pins_golden_rows():
    good = _table(
        LOG_HEADER,
        _log_row(),
        _log_row(criterion="FC-02", phase="baseline", value="81.28 s", reading="Estimate"),
        _log_row(criterion="FC-01", phase="final", value="16800 tokens", head="0badf00d"),
        _log_row(criterion="FC-03", phase="final", value="-", reading="none: tokenizer withheld"),
        _log_row(criterion="FC-01", phase="final", value="16790 tokens", taken="2026-10-01T11:02Z"),
    )

    parsed = fc.parse_measurements(good)

    assert parsed.findings == ()
    assert [(m.criterion, m.phase) for m in parsed.measurements] == [
        ("FC-01", "baseline"),
        ("FC-02", "baseline"),
        ("FC-01", "final"),
        ("FC-03", "final"),
        ("FC-01", "final"),
    ]
    first = parsed.measurements[0]
    assert first == fc.Measurement(
        criterion="FC-01",
        phase="baseline",
        value="16726 tokens",
        reading=fc.Measured(),
        head="f4d953a6",
        taken="2026-10-01T09:16Z",
        command="python3 scripts/measure_token_budget.py --json",
    )
    assert parsed.measurements[1].reading == fc.Estimate()
    assert parsed.measurements[3].reading == fc.NoReading("tokenizer withheld")

    latest = fc.latest(parsed.measurements)
    assert set(latest) == {
        ("FC-01", "baseline"),
        ("FC-02", "baseline"),
        ("FC-01", "final"),
        ("FC-03", "final"),
    }
    assert (
        latest[("FC-01", "final")].value == "16790 tokens"
    )  # the later row in document order wins

    # No log, or a log with no rows yet, is not a defect.
    assert fc.parse_measurements("") == fc.LogParse((), ())
    assert fc.parse_measurements(_table(LOG_HEADER)) == fc.LogParse((), ())

    sibling = _log_row(criterion="FC-07")
    bad_rows = [
        ("bad-header", "| Criterion | Phase |\n|---|---|\n| FC-01 | final |\n", "bad-header"),
        ("missing-cell", _table(LOG_HEADER, _log_row(value=" "), sibling), "missing-cell"),
        ("bad-id", _table(LOG_HEADER, _log_row(criterion="FC-1"), sibling), "bad-id"),
        ("bad-phase", _table(LOG_HEADER, _log_row(phase="initial"), sibling), "bad-phase"),
        ("bad-reading", _table(LOG_HEADER, _log_row(reading="guess"), sibling), "bad-reading"),
        ("bare none", _table(LOG_HEADER, _log_row(reading="none"), sibling), "reasonless"),
        (
            "placeholder none",
            _table(LOG_HEADER, _log_row(reading="none: tbd"), sibling),
            "reasonless",
        ),
        ("short head", _table(LOG_HEADER, _log_row(head="f4d953a"), sibling), "bad-head"),
        ("uppercase head", _table(LOG_HEADER, _log_row(head="F4D953A6"), sibling), "bad-head"),
        (
            "impossible date",
            _table(LOG_HEADER, _log_row(taken="2026-13-01T09:16Z"), sibling),
            "bad-taken",
        ),
        (
            "not UTC to the minute",
            _table(LOG_HEADER, _log_row(taken="2026-10-01 09:16"), sibling),
            "bad-taken",
        ),
        (
            "no command span",
            _table(LOG_HEADER, _log_row(command="ran it"), sibling),
            "command-span",
        ),
    ]
    for label, text, reason in bad_rows:
        parsed = fc.parse_measurements(text)
        finding = _sole_finding(parsed.findings, label)
        assert (finding.code, finding.severity, finding.reason) == ("FP02", "fail", reason), label
        assert all(m.criterion == "FC-07" for m in parsed.measurements), label


# --- finding table and docstring ------------------------------------------------------------


def test_finding_table_is_pinned():
    assert fc.FINDING_TABLE == (
        fc.FindingSpec("FP01", "unbounded", "warn", ("plan", "verify"), ("unbounded",)),
        fc.FindingSpec(
            "FP02",
            "malformed",
            "fail",
            ("spec", "plan", "verify"),
            (
                "bad-header",
                "empty-table",
                "missing-cell",
                "bad-id",
                "duplicate-id",
                "bad-against",
                "command-span",
                "reasonless",
                "bounded-and-declared",
                "unknown-criterion",
                "bad-phase",
                "bad-reading",
                "bad-head",
                "bad-taken",
            ),
        ),
        fc.FindingSpec(
            "FP03",
            "unmeasured",
            "fail",
            ("verify",),
            (
                "missing-final",
                "missing-baseline",
                "no-reading",
                "stale-final",
                "late-baseline",
                "incomparable",
                "wrong-command",
            ),
        ),
        fc.FindingSpec(
            "FP04", "unregistered", "info", ("spec", "plan", "verify"), ("unregistered",)
        ),
        fc.FindingSpec(
            "FP05",
            "registry",
            "warn",
            ("spec", "plan", "verify"),
            ("malformed", "duplicate", "dead-glob"),
        ),
    )
    assert fc.STAGES == ("spec", "plan", "verify")

    # The docstring is the one normative text: it names every code, name, reason and stage.
    doc = fc.__doc__
    for spec in fc.FINDING_TABLE:
        for token in (spec.code, spec.name, spec.severity, *spec.reasons, *spec.stages):
            assert token in doc, f"module docstring does not name {token!r} ({spec.code})"
    for token in ("--stage", "--paths", "--base-ref", "--repo-root", "--json", "schema"):
        assert token in doc, f"module docstring does not specify {token!r}"
    for placeholder in fc.PLACEHOLDER_REASONS:
        assert placeholder in doc, f"module docstring does not list the placeholder {placeholder!r}"

    # A finding takes its severity from the table, and an unknown reason is a programming error.
    finding = fc.make_finding(
        "FP03", "stale-final", "the final row predates a change", criterion="FC-01"
    )
    assert (finding.severity, finding.criterion, finding.footprint) == ("fail", "FC-01", None)
    for code, reason in (("FP03", "typo"), ("FP09", "unbounded")):
        try:
            fc.make_finding(code, reason, "x")
        except ValueError:
            continue
        raise AssertionError(f"make_finding accepted {code}/{reason}")


# --- the script itself ----------------------------------------------------------------------


def test_script_is_stdlib_only_and_python39_parseable():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 9))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import is not stdlib-only"
            imported.add((node.module or "").split(".")[0])
    assert imported, "the script imports nothing, which cannot be right"
    third_party = {name for name in imported if name not in sys.stdlib_module_names}
    assert not third_party, f"non-stdlib imports: {sorted(third_party)}"

    # Syntax a 3.9 parser accepts can still fail at import on 3.9: slotted or keyword-only dataclasses.
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in {"slots", "kw_only"}:
            raise AssertionError(f"line {node.value.lineno}: `{node.arg}=` needs Python 3.10")

    # It must import under a bare interpreter: isolated mode, no PYTHONPATH, no sibling modules.
    result = subprocess.run(
        [sys.executable, "-I", "-c", "import runpy, sys; runpy.run_path(sys.argv[1])", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    assert source.startswith("#!/usr/bin/env python3\n")
    assert os.access(SCRIPT, os.X_OK), "the script is not executable"
