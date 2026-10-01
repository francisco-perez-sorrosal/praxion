"""Shared builders and case tables for the footprint check's tests; not a test module.

Each `Case` is one malformed input, the reason of the one finding it must draw,
and the rows that must survive it. A parser that drops more than the bad row is
caught by the survivors, and one that drops nothing by the finding. Expected
values come from the grammar in `_footprint_grammar.py`'s docstring, not from
running the implementation.
"""

from __future__ import annotations

from typing import NamedTuple

CRITERIA_HEADER = "| Id | Footprint | Metric | Comparator | Limit | Against | Command |"
DECLARATION_HEADER = "| Footprint | Reason |"
REGISTRY_HEADER = "| Footprint | Paths | Command | Reading |"
LOG_HEADER = "| Criterion | Phase | Value | Reading | Head | Taken | Command |"
PROMPT_COMMAND = "`python3 scripts/check_agent_prompt_size.py --json`"
BUDGET_COMMAND = "`python3 scripts/measure_token_budget.py --json`"


class Case(NamedTuple):
    label: str
    text: str
    reason: str
    survivors: list[str]  # the ids (spec, log) or names (registry) that must be read


# --- builders -------------------------------------------------------------------------------


def table(header: str, *rows: str) -> str:
    separator = "|" + "---|" * (header.count("|") - 1)
    return "\n".join([header, separator, *rows]) + "\n"


def criterion_row(**cells: str) -> str:
    row = {
        "id": "FC-01",
        "footprint": "prompt-size",
        "metric": "lines in the longest prompt",
        "comparator": "at or below",
        "limit": "400 lines",
        "against": "baseline: 398 lines",
        "command": PROMPT_COMMAND,
        **cells,
    }
    return "| " + " | ".join(row.values()) + " |"


def plan(criteria: str | None = None, declared: str | None = None, *, rest: str = "") -> str:
    parts = ["# Plan", "", "## Acceptance Criteria", "", "- [ ] The change behaves", ""]
    if criteria is not None:
        parts += ["### Footprint Criteria", "", criteria]
    if declared is not None:
        parts += ["### Footprints Not Measured", "", declared]
    return "\n".join(parts) + "\n" + rest


def plan_under(heading: str, body: str) -> str:
    """A plan whose only table sits under `heading`, which is not one of the two read."""
    return f"# Plan\n\n## Acceptance Criteria\n\n- [ ] The change behaves\n\n{heading}\n\n{body}"


def registry_row(
    name: str = "prompt-size",
    paths: str = "agents/*.md, !agents/README.md",
    command: str = PROMPT_COMMAND,
    reading: str = "line counts",
) -> str:
    return f"| {name} | {paths} | {command} | {reading} |"


def log_row(**cells: str) -> str:
    row = {
        "criterion": "FC-01",
        "phase": "baseline",
        "value": "16726 tokens",
        "reading": "measured",
        "head": "f4d953a6",
        "taken": "2026-10-01T09:16Z",
        "command": BUDGET_COMMAND,
        **cells,
    }
    return "| " + " | ".join(row.values()) + " |"


def fenced(text: str) -> str:
    return "```\n" + text + "```\n\n"


GOOD_ROW = criterion_row(id="FC-09", footprint="other")
LATER_ROW = criterion_row(id="FC-08", footprint="later")
CRITERIA_ONLY = table(CRITERIA_HEADER, GOOD_ROW)
SIBLING_ROW = registry_row("sibling", "src/*.py", "none", "none")
SIBLING_LOG = log_row(criterion="FC-07")


def _criteria_with(**cells: str) -> str:
    """A plan whose criteria table holds a row built from `cells`, then a good one."""
    return plan(table(CRITERIA_HEADER, criterion_row(**cells), GOOD_ROW))


def _declared(reason: str) -> str:
    return plan(CRITERIA_ONLY, table(DECLARATION_HEADER, f"| spawn-count | {reason} |"))


def _registry_with(**cells: str) -> str:
    return table(REGISTRY_HEADER, registry_row(**cells), SIBLING_ROW)


def _log_with(**cells: str) -> str:
    return table(LOG_HEADER, log_row(**cells), SIBLING_LOG)


# --- spec cases -----------------------------------------------------------------------------

PLACEHOLDERS = (
    *("-", "—", "–", "--", "...", "?", "n/a", "NA", "N/A.", "n / a", "None", "none.", "`n/a`"),
    *("tbd", "TBD.", "TODO", "tba", "tbc", "nil", "pending", "Not Applicable", "none yet"),
    *("n/a, tbd", "N/A - TBD", "none (tbd)", "n/a n/a", "`tbd` / `tbc`"),
)
SPEC_MISPLACED_HEADINGS = (
    "#### Footprint Criteria",
    "### Footprint Criteria (this change)",
    "### Footprint Criteria:",
    "### Footprint Criteria ###",
    "## Footprint Criteria",
    "### Measured Footprints",
)
_WRONG_ID_HEADER = "| Idx | Footprint | Metric | Comparator | Limit | Against | Command |"
_UNDER_ARCHITECTURE = "## Architecture\n\n### Footprint Criteria\n\n"

SPEC_CASES = (
    Case("bad-header", plan(table(_WRONG_ID_HEADER, GOOD_ROW)), "bad-header", []),
    Case("empty-table (no table)", plan("(none yet)\n"), "empty-table", []),
    Case("empty-table (header only)", plan(table(CRITERIA_HEADER)), "empty-table", []),
    Case("missing-cell", _criteria_with(limit=" "), "missing-cell", ["FC-09"]),
    *[
        Case(
            f"missing-cell ({column}={value!r})",
            _criteria_with(**{column: value}),
            "missing-cell",
            ["FC-09"],
        )
        for column, value in (
            ("metric", "tbd"),
            ("comparator", "N/A."),
            ("limit", "?"),
            ("limit", "n/a, tbd"),
        )
    ],
    Case("extra-cell", _criteria_with(command="`a` | `b`"), "extra-cell", ["FC-09"]),
    Case("bad-id", _criteria_with(id="FC-1"), "bad-id", ["FC-09"]),
    Case("bad-id (non-ASCII digits)", _criteria_with(id="FC-٠١"), "bad-id", ["FC-09"]),
    Case(
        "duplicate-id",
        plan(table(CRITERIA_HEADER, GOOD_ROW, criterion_row(id="FC-09"))),
        "duplicate-id",
        ["FC-09"],
    ),
    Case("bad-against (prefix)", _criteria_with(against="absolute: 5"), "bad-against", ["FC-09"]),
    Case("bad-against (no text)", _criteria_with(against="baseline:"), "bad-against", ["FC-09"]),
    Case("bad-against (-)", _criteria_with(against="baseline: -"), "bad-against", ["FC-09"]),
    Case(
        "bad-against (n/a, tbd)",
        _criteria_with(against="baseline: n/a, tbd"),
        "bad-against",
        ["FC-09"],
    ),
    Case("command-span (none)", _criteria_with(command="run the thing"), "command-span", ["FC-09"]),
    Case("command-span (two)", _criteria_with(command="`a` then `b`"), "command-span", ["FC-09"]),
    Case("command-span (dangling)", _criteria_with(command="`a` `b"), "command-span", ["FC-09"]),
    *[Case(f"reasonless ({p})", _declared(p), "reasonless", ["FC-09"]) for p in PLACEHOLDERS],
    Case(
        "bounded-and-declared",
        plan(CRITERIA_ONLY, table(DECLARATION_HEADER, "| Other | no instrument exists for it |")),
        "bounded-and-declared",
        ["FC-09"],
    ),
    Case(
        "stray-row (after a blank line)",
        plan(CRITERIA_ONLY + "\n" + LATER_ROW + "\n"),
        "stray-row",
        ["FC-09"],
    ),
    Case(
        "stray-row (after a comment line)",
        plan(CRITERIA_ONLY + "<!-- note -->\n" + LATER_ROW + "\n"),
        "stray-row",
        ["FC-09"],
    ),
    Case(
        "stray-row (after a prose line)",
        plan(CRITERIA_ONLY + "Notes:\n" + LATER_ROW + "\n"),
        "stray-row",
        ["FC-09"],
    ),
    Case(
        "stray-row (a second table)",
        plan(CRITERIA_ONLY + "\n" + table(CRITERIA_HEADER, LATER_ROW)),
        "stray-row",
        ["FC-09"],
    ),
    *[
        Case(f"misplaced-table ({h})", plan_under(h, CRITERIA_ONLY), "misplaced-table", [])
        for h in SPEC_MISPLACED_HEADINGS
    ],
    Case(
        "misplaced-table (declarations under a drifted heading)",
        plan_under(
            "### Footprints not measured:",
            table(DECLARATION_HEADER, "| spawn-count | no instrument counts it |"),
        ),
        "misplaced-table",
        [],
    ),
    Case(
        "misplaced-table (an unfenced quote in a design section)",
        plan(rest=_UNDER_ARCHITECTURE + CRITERIA_ONLY),
        "misplaced-table",
        [],
    ),
)

# --- registry cases -------------------------------------------------------------------------

REGISTRY_CASES = (
    Case(
        "bad-header",
        "| Footprint | Globs | Command |\n|---|---|---|\n| a | b/* | none |\n",
        "malformed",
        [],
    ),
    Case("no table", "# Footprints\n\nnothing here\n", "malformed", []),
    Case("header only", table(REGISTRY_HEADER), "malformed", []),
    Case("uppercase name", _registry_with(name="Prompt-Size"), "malformed", ["sibling"]),
    Case("snake_case name", _registry_with(name="prompt_size"), "malformed", ["sibling"]),
    Case(
        "bad row after a good one",
        table(REGISTRY_HEADER, SIBLING_ROW, registry_row("Prompt-Size")),
        "malformed",
        ["sibling"],
    ),
    Case("empty paths", _registry_with(paths=" "), "malformed", ["sibling"]),
    Case("exclude-only paths", _registry_with(paths="!agents/*.md"), "malformed", ["sibling"]),
    Case("lone bang glob", _registry_with(paths="agents/*.md, !"), "malformed", ["sibling"]),
    Case("command is prose", _registry_with(command="run it"), "malformed", ["sibling"]),
    Case("command has two spans", _registry_with(command="`a` `b`"), "malformed", ["sibling"]),
    Case("command dangles", _registry_with(command="`a` `b"), "malformed", ["sibling"]),
    Case("extra cell", _registry_with(reading="a | b"), "malformed", ["sibling"]),
    Case(
        "duplicate name",
        table(REGISTRY_HEADER, registry_row("sibling", "other/*.py", "none", "none"), SIBLING_ROW),
        "duplicate",
        ["sibling"],
    ),
    Case(
        "rows after a blank line",
        table(REGISTRY_HEADER, SIBLING_ROW) + "\n" + registry_row() + "\n",
        "malformed",
        ["sibling"],
    ),
    Case(
        "a second table",
        table(REGISTRY_HEADER, SIBLING_ROW) + "\n" + table(REGISTRY_HEADER, registry_row()),
        "malformed",
        ["sibling"],
    ),
)

# --- measurement log cases ------------------------------------------------------------------

LOG_STRAY_ROW = "| FC-01 | final | 1 | measured | f4d953a6 | 2026-10-01T09:16Z | `c` |\n"
BAD_TAKEN = (
    "2026-13-01T09:16Z",
    "2026-10-01 09:16",
    "2026-1-1T9:5Z",
    "2026-10- 1T09:16Z",
    "２０２６-10-01T09:16Z",
)
PLACEHOLDER_NONE_REASONS = ("tbd", "N/A.", "--", "`n/a`", "n/a, tbd", "pending")

LOG_CASES = (
    Case("bad-header", "| Criterion | Phase |\n|---|---|\n| FC-01 | final |\n", "bad-header", []),
    Case("content with no table", "the measurements go here\n", "bad-header", []),
    Case("rows without a separator row", LOG_STRAY_ROW, "stray-row", []),
    Case("missing-cell", _log_with(value=" "), "missing-cell", ["FC-07"]),
    Case("missing-cell (placeholder value)", _log_with(value="tbd"), "missing-cell", ["FC-07"]),
    Case("extra-cell", _log_with(command="`a` | `b`"), "extra-cell", ["FC-07"]),
    Case("bad-id", _log_with(criterion="FC-1"), "bad-id", ["FC-07"]),
    Case("bad-id (non-ASCII digits)", _log_with(criterion="FC-٠١"), "bad-id", ["FC-07"]),
    Case(
        "bad row after a good one",
        table(LOG_HEADER, SIBLING_LOG, log_row(phase="initial")),
        "bad-phase",
        ["FC-07"],
    ),
    Case("bad-phase", _log_with(phase="initial"), "bad-phase", ["FC-07"]),
    Case("bad-phase (case-folded)", _log_with(phase="BASELINE"), "bad-phase", ["FC-07"]),
    Case("bad-reading", _log_with(reading="guess"), "bad-reading", ["FC-07"]),
    Case("bad-reading (case-folded)", _log_with(reading="Measured"), "bad-reading", ["FC-07"]),
    Case("bare none", _log_with(reading="none"), "reasonless", ["FC-07"]),
    *[
        Case(f"none ({r})", _log_with(reading=f"none: {r}"), "reasonless", ["FC-07"])
        for r in PLACEHOLDER_NONE_REASONS
    ],
    Case("short head", _log_with(head="f4d953a"), "bad-head", ["FC-07"]),
    Case("uppercase head", _log_with(head="F4D953A6"), "bad-head", ["FC-07"]),
    *[Case(f"bad-taken ({t})", _log_with(taken=t), "bad-taken", ["FC-07"]) for t in BAD_TAKEN],
    Case("no command span", _log_with(command="ran it"), "command-span", ["FC-07"]),
    Case("dangling backtick", _log_with(command="`a` `b"), "command-span", ["FC-07"]),
    Case(
        "stray-row (after a blank line)",
        table(LOG_HEADER, SIBLING_LOG) + "\n" + log_row() + "\n",
        "stray-row",
        ["FC-07"],
    ),
    Case(
        "stray-row (a second table)",
        table(LOG_HEADER, SIBLING_LOG) + "\n" + table(LOG_HEADER, log_row()),
        "stray-row",
        ["FC-07"],
    ),
)
