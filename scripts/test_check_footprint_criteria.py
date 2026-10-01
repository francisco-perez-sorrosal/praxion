"""Tests for `check_footprint_criteria.py` -- the shared contract of the footprint check.

The failure mode this closes: a footprint criterion, a registry row or a
measurement row that breaks its grammar passing silently, so a bounded
footprint reaches the verifier unmeasured. Each grammar test holds golden good
rows and one golden bad row per malformed reason; a bad row is the canary that
the parse-level check fires, and each case names the exact rows that survive
it, so a parser that drops more than the bad row is caught too. Expected values
come from the grammar in the module docstring, not from running the
implementation.

Later lanes cite the five pinning tests by node name; do not rename them.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
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


def _plan_under(heading: str, table: str) -> str:
    """A plan whose only table sits under `heading`, which is not one of the two read."""
    return f"# Plan\n\n## Acceptance Criteria\n\n- [ ] The change behaves\n\n{heading}\n\n{table}"


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


def _fenced(text: str) -> str:
    return "```\n" + text + "```\n\n"


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

    # A table inside a code fence is an example: neither read nor reported, even ahead of the real one.
    example = _fenced(_table(CRITERIA_HEADER, _criterion_row(id="FC-77", footprint="example")))
    fenced_first = fc.parse_spec_tables(_plan(example + _table(CRITERIA_HEADER, _GOOD_ROW)))
    assert fenced_first.findings == ()
    assert [c.id for c in fenced_first.criteria] == ["FC-09"]
    quoted = _plan(rest="## Architecture\n\n### Footprint Criteria\n\n" + example)
    assert fc.parse_spec_tables(quoted) == fc.SpecTables((), (), ())
    # So is a fenced heading: the section that is read is the first one outside any fence.
    heading_example = _fenced(
        "### Footprint Criteria\n\n" + _CRITERIA_ONLY.replace("FC-09", "FC-77")
    )
    fenced_heading = (
        "# Plan\n\n## Acceptance Criteria\n\n"
        + heading_example
        + "### Footprint Criteria\n\n"
        + _CRITERIA_ONLY
    )
    parsed = fc.parse_spec_tables(fenced_heading)
    assert parsed.findings == ()
    assert [c.id for c in parsed.criteria] == ["FC-09"]

    for label, plan, reason, survivors in _BAD_SPEC_PLANS:
        parsed = fc.parse_spec_tables(plan)
        finding = _sole_finding(parsed.findings, label)
        assert (finding.code, finding.severity, finding.reason) == ("FP02", "fail", reason), label
        assert [c.id for c in parsed.criteria] == survivors, label


_GOOD_ROW = _criterion_row(id="FC-09", footprint="other")
_LATER_ROW = _criterion_row(id="FC-08", footprint="later")
_CRITERIA_ONLY = _table(CRITERIA_HEADER, _GOOD_ROW)
_PLACEHOLDERS = (
    "-",
    "—",
    "–",
    "--",
    "...",
    "?",
    "n/a",
    "NA",
    "N/A.",
    "n / a",
    "None",
    "none.",
    "`n/a`",
    "tbd",
    "TBD.",
    "TODO",
    "tba",
)
# (label, plan, reason of the one finding, criteria that survive it)
_BAD_SPEC_PLANS = [
    (
        "bad-header",
        _plan(
            _table(
                "| Idx | Footprint | Metric | Comparator | Limit | Against | Command |", _GOOD_ROW
            )
        ),
        "bad-header",
        [],
    ),
    ("empty-table (no table)", _plan("(none yet)\n"), "empty-table", []),
    ("empty-table (header only)", _plan(_table(CRITERIA_HEADER)), "empty-table", []),
    (
        "missing-cell",
        _plan(_table(CRITERIA_HEADER, _criterion_row(limit=" "), _GOOD_ROW)),
        "missing-cell",
        ["FC-09"],
    ),
    *[
        (
            f"missing-cell (placeholder {column}={value!r})",
            _plan(_table(CRITERIA_HEADER, _criterion_row(**{column: value}), _GOOD_ROW)),
            "missing-cell",
            ["FC-09"],
        )
        for column, value in (("metric", "tbd"), ("comparator", "N/A."), ("limit", "?"))
    ],
    (
        "extra-cell (unescaped pipe in the last cell)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(command="`a` | `b`"), _GOOD_ROW)),
        "extra-cell",
        ["FC-09"],
    ),
    (
        "bad-id",
        _plan(_table(CRITERIA_HEADER, _criterion_row(id="FC-1"), _GOOD_ROW)),
        "bad-id",
        ["FC-09"],
    ),
    (
        "bad-id (non-ASCII digits)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(id="FC-٠١"), _GOOD_ROW)),
        "bad-id",
        ["FC-09"],
    ),
    (
        "duplicate-id",
        _plan(_table(CRITERIA_HEADER, _GOOD_ROW, _criterion_row(id="FC-09"))),
        "duplicate-id",
        ["FC-09"],
    ),
    (
        "bad-against (unknown prefix)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(against="absolute: 5"), _GOOD_ROW)),
        "bad-against",
        ["FC-09"],
    ),
    (
        "bad-against (prefix without text)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(against="baseline:"), _GOOD_ROW)),
        "bad-against",
        ["FC-09"],
    ),
    (
        "bad-against (placeholder text)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(against="baseline: -"), _GOOD_ROW)),
        "bad-against",
        ["FC-09"],
    ),
    (
        "command-span (no span)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(command="run the thing"), _GOOD_ROW)),
        "command-span",
        ["FC-09"],
    ),
    (
        "command-span (two spans)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(command="`a` then `b`"), _GOOD_ROW)),
        "command-span",
        ["FC-09"],
    ),
    (
        "command-span (dangling backtick)",
        _plan(_table(CRITERIA_HEADER, _criterion_row(command="`a` `b"), _GOOD_ROW)),
        "command-span",
        ["FC-09"],
    ),
    *[
        (
            f"reasonless ({placeholder})",
            _plan(_CRITERIA_ONLY, _table(DECLARATION_HEADER, f"| spawn-count | {placeholder} |")),
            "reasonless",
            ["FC-09"],
        )
        for placeholder in _PLACEHOLDERS
    ],
    (
        "bounded-and-declared",
        _plan(
            _CRITERIA_ONLY,
            _table(DECLARATION_HEADER, "| Other | no instrument exists for it |"),
        ),
        "bounded-and-declared",
        ["FC-09"],
    ),
    (
        "stray-row (after a blank line)",
        _plan(_CRITERIA_ONLY + "\n" + _LATER_ROW + "\n"),
        "stray-row",
        ["FC-09"],
    ),
    (
        "stray-row (after a comment line)",
        _plan(_CRITERIA_ONLY + "<!-- note -->\n" + _LATER_ROW + "\n"),
        "stray-row",
        ["FC-09"],
    ),
    (
        "stray-row (after a prose line)",
        _plan(_CRITERIA_ONLY + "Notes:\n" + _LATER_ROW + "\n"),
        "stray-row",
        ["FC-09"],
    ),
    (
        "stray-row (a second table)",
        _plan(_CRITERIA_ONLY + "\n" + _table(CRITERIA_HEADER, _LATER_ROW)),
        "stray-row",
        ["FC-09"],
    ),
    *[
        (
            f"misplaced-table ({heading})",
            _plan_under(heading, _CRITERIA_ONLY),
            "misplaced-table",
            [],
        )
        for heading in (
            "#### Footprint Criteria",
            "### Footprint Criteria (this change)",
            "### Footprint Criteria:",
            "### Footprint Criteria ###",
            "## Footprint Criteria",
            "### Measured Footprints",
        )
    ],
    (
        "misplaced-table (declarations under a drifted heading)",
        _plan_under(
            "### Footprints not measured:",
            _table(DECLARATION_HEADER, "| spawn-count | no instrument counts it |"),
        ),
        "misplaced-table",
        [],
    ),
    (
        "misplaced-table (an unfenced quote in a design section)",
        _plan(rest="## Architecture\n\n### Footprint Criteria\n\n" + _CRITERIA_ONLY),
        "misplaced-table",
        [],
    ),
]


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

    # Reading is optional, and `none` has one meaning whether or not it is backticked.
    no_reading = "| Footprint | Paths | Command |\n|---|---|---|\n| a-b | x/*.py | `none` |\n"
    parsed = fc.parse_registry(no_reading)
    assert parsed.findings == ()
    assert parsed.registry == fc.Registry((fc.Footprint("a-b", ("x/*.py",), (), None, ""),))

    # A fenced example ahead of the real table is not the table.
    example = _fenced(_table(REGISTRY_HEADER, _registry_row("example")))
    parsed = fc.parse_registry(example + good)
    assert parsed.findings == ()
    assert [f.name for f in parsed.registry.footprints] == ["prompt-size", "hook-latency"]

    for label, text, reason, survivors in _bad_registries():
        parsed = fc.parse_registry(text)
        finding = _sole_finding(parsed.findings, label)
        assert (finding.code, finding.severity, finding.reason) == ("FP05", "warn", reason), label
        assert [f.name for f in parsed.registry.footprints] == survivors, label


def _bad_registries():
    sibling = _registry_row("sibling", "src/*.py", "none", "none")
    first = _registry_row()
    return [
        (
            "bad-header",
            "| Footprint | Globs | Command |\n|---|---|---|\n| a | b/* | none |\n",
            "malformed",
            [],
        ),
        ("no table", "# Footprints\n\nnothing here\n", "malformed", []),
        ("header only", _table(REGISTRY_HEADER), "malformed", []),
        (
            "uppercase name",
            _table(REGISTRY_HEADER, _registry_row("Prompt-Size"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "snake_case name",
            _table(REGISTRY_HEADER, _registry_row("prompt_size"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "bad row after a good one",
            _table(REGISTRY_HEADER, sibling, _registry_row("Prompt-Size")),
            "malformed",
            ["sibling"],
        ),
        (
            "empty paths",
            _table(REGISTRY_HEADER, _registry_row(paths=" "), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "exclude-only paths",
            _table(REGISTRY_HEADER, _registry_row(paths="!agents/*.md"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "lone bang glob",
            _table(REGISTRY_HEADER, _registry_row(paths="agents/*.md, !"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "command is prose",
            _table(REGISTRY_HEADER, _registry_row(command="run it"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "command has two spans",
            _table(REGISTRY_HEADER, _registry_row(command="`a` `b`"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "command has a dangling backtick",
            _table(REGISTRY_HEADER, _registry_row(command="`a` `b"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "extra cell (unescaped pipe)",
            _table(REGISTRY_HEADER, _registry_row(reading="a | b"), sibling),
            "malformed",
            ["sibling"],
        ),
        (
            "duplicate name",
            _table(
                REGISTRY_HEADER, _registry_row("sibling", "other/*.py", "none", "none"), sibling
            ),
            "duplicate",
            ["sibling"],
        ),
        (
            "rows after a blank line",
            _table(REGISTRY_HEADER, sibling) + "\n" + first + "\n",
            "malformed",
            ["sibling"],
        ),
        (
            "a second table",
            _table(REGISTRY_HEADER, sibling) + "\n" + _table(REGISTRY_HEADER, first),
            "malformed",
            ["sibling"],
        ),
    ]


# --- measurement log ------------------------------------------------------------------------


def test_parse_measurements_pins_golden_rows():
    good = _table(
        LOG_HEADER,
        _log_row(),
        _log_row(criterion="FC-02", phase="baseline", value="81.28 s", reading="estimate"),
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
    assert parsed.measurements[0] == fc.Measurement(
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

    # No log, a log with no rows yet, and a log that opens with a heading or a BOM are not defects.
    assert fc.parse_measurements("") == fc.LogParse((), ())
    assert fc.parse_measurements("# Measurements\n\n" + _table(LOG_HEADER)) == fc.LogParse((), ())
    assert fc.parse_measurements("# Measurements\n") == fc.LogParse((), ())
    assert fc.parse_measurements("﻿" + good).measurements == parsed.measurements

    # A fenced example ahead of the real table is not the table.
    example = _fenced(_table(LOG_HEADER, _log_row(criterion="FC-77")))
    assert fc.parse_measurements(example + good) == parsed

    for label, text, reason, survivors in _bad_logs():
        parsed = fc.parse_measurements(text)
        finding = _sole_finding(parsed.findings, label)
        assert (finding.code, finding.severity, finding.reason) == ("FP02", "fail", reason), label
        assert [m.criterion for m in parsed.measurements] == survivors, label


def _bad_logs():
    sibling = _log_row(criterion="FC-07")
    return [
        ("bad-header", "| Criterion | Phase |\n|---|---|\n| FC-01 | final |\n", "bad-header", []),
        ("content with no table", "the measurements go here\n", "bad-header", []),
        (
            "rows without a separator row",
            "| FC-01 | final | 1 | measured | f4d953a6 | 2026-10-01T09:16Z | `c` |\n",
            "stray-row",
            [],
        ),
        (
            "missing-cell",
            _table(LOG_HEADER, _log_row(value=" "), sibling),
            "missing-cell",
            ["FC-07"],
        ),
        (
            "missing-cell (placeholder value for a measured reading)",
            _table(LOG_HEADER, _log_row(value="tbd"), sibling),
            "missing-cell",
            ["FC-07"],
        ),
        (
            "extra-cell",
            _table(LOG_HEADER, _log_row(command="`a` | `b`"), sibling),
            "extra-cell",
            ["FC-07"],
        ),
        ("bad-id", _table(LOG_HEADER, _log_row(criterion="FC-1"), sibling), "bad-id", ["FC-07"]),
        (
            "bad-id (non-ASCII digits)",
            _table(LOG_HEADER, _log_row(criterion="FC-٠١"), sibling),
            "bad-id",
            ["FC-07"],
        ),
        (
            "bad row after a good one",
            _table(LOG_HEADER, sibling, _log_row(phase="initial")),
            "bad-phase",
            ["FC-07"],
        ),
        (
            "bad-phase",
            _table(LOG_HEADER, _log_row(phase="initial"), sibling),
            "bad-phase",
            ["FC-07"],
        ),
        (
            "bad-phase (case-folded)",
            _table(LOG_HEADER, _log_row(phase="BASELINE"), sibling),
            "bad-phase",
            ["FC-07"],
        ),
        (
            "bad-reading",
            _table(LOG_HEADER, _log_row(reading="guess"), sibling),
            "bad-reading",
            ["FC-07"],
        ),
        (
            "bad-reading (case-folded)",
            _table(LOG_HEADER, _log_row(reading="Measured"), sibling),
            "bad-reading",
            ["FC-07"],
        ),
        (
            "bare none",
            _table(LOG_HEADER, _log_row(reading="none"), sibling),
            "reasonless",
            ["FC-07"],
        ),
        *[
            (
                f"placeholder none ({reason})",
                _table(LOG_HEADER, _log_row(reading=f"none: {reason}"), sibling),
                "reasonless",
                ["FC-07"],
            )
            for reason in ("tbd", "N/A.", "--", "`n/a`")
        ],
        (
            "short head",
            _table(LOG_HEADER, _log_row(head="f4d953a"), sibling),
            "bad-head",
            ["FC-07"],
        ),
        (
            "uppercase head",
            _table(LOG_HEADER, _log_row(head="F4D953A6"), sibling),
            "bad-head",
            ["FC-07"],
        ),
        *[
            (
                f"bad-taken ({taken})",
                _table(LOG_HEADER, _log_row(taken=taken), sibling),
                "bad-taken",
                ["FC-07"],
            )
            for taken in (
                "2026-13-01T09:16Z",
                "2026-10-01 09:16",
                "2026-1-1T9:5Z",
                "2026-10- 1T09:16Z",
                "２０２６-10-01T09:16Z",
            )
        ],
        (
            "no command span",
            _table(LOG_HEADER, _log_row(command="ran it"), sibling),
            "command-span",
            ["FC-07"],
        ),
        (
            "dangling backtick",
            _table(LOG_HEADER, _log_row(command="`a` `b"), sibling),
            "command-span",
            ["FC-07"],
        ),
        (
            "stray-row (after a blank line)",
            _table(LOG_HEADER, sibling) + "\n" + _log_row() + "\n",
            "stray-row",
            ["FC-07"],
        ),
        (
            "stray-row (a second table)",
            _table(LOG_HEADER, sibling) + "\n" + _table(LOG_HEADER, _log_row()),
            "stray-row",
            ["FC-07"],
        ),
    ]


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
                "misplaced-table",
                "stray-row",
                "extra-cell",
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

    # The docstring is the one normative text: its table, parsed, is the finding table row by row.
    expected = {
        spec.code: [spec.name, spec.severity, ", ".join(spec.stages), ", ".join(spec.reasons)]
        for spec in fc.FINDING_TABLE
    }
    assert _docstring_finding_rows(fc.__doc__) == expected
    for token in ("--stage", "--paths", "--base-ref", "--repo-root", "--json", "schema"):
        assert token in fc.__doc__, f"module docstring does not specify {token!r}"
    for placeholder in fc.PLACEHOLDER_REASONS:
        assert placeholder in fc.__doc__, f"module docstring omits the placeholder {placeholder!r}"

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

    # `feature_version` parses only syntax. What breaks a 3.9 import at run time is checked here:
    # annotations must stay lazy, and no union operator, slotted or keyword-only dataclass, or
    # `strict=` may be evaluated.
    assert "annotations" in _future_imports(tree), "annotations must be lazy for 3.9"
    in_annotation = _annotation_node_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            assert id(node) in in_annotation, f"line {node.lineno}: a runtime `X | Y` needs 3.10"
        if isinstance(node, ast.keyword):
            assert node.arg not in {"slots", "kw_only", "strict"}, (
                f"line {node.value.lineno}: `{node.arg}=` needs Python 3.10"
            )

    # It must import under a bare interpreter: isolated mode, no PYTHONPATH, no sibling modules.
    for interpreter in (sys.executable, *_python39_interpreters()):
        result = subprocess.run(
            [
                interpreter,
                "-I",
                "-c",
                "import runpy, sys; runpy.run_path(sys.argv[1])",
                str(SCRIPT),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{interpreter}: {result.stderr}"

    assert source.startswith("#!/usr/bin/env python3\n")
    assert os.access(SCRIPT, os.X_OK), "the script is not executable"

    # Until the stages exist, running it must not read as a clean pass.
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "any-slug"], capture_output=True, text=True, check=False
    )
    assert run.returncode == 2
    assert "stages not implemented" in run.stderr


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
