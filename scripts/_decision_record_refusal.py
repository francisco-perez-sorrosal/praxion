"""The decision-record gate's refusal text: the correct form plus the rule's own lines.

A refusal is only useful when it tells the author what to do instead, so every one states the
correct form and quotes the lines of ``adr-conventions.md`` that govern the defect family. The
rule text is a parameter: ``refusal_text`` and ``commit_refusal_text`` are pure, and
``find_rule_text`` is the module's one effect. The decision to refuse never depends on this
module, so an unreadable rule, a reworded heading or a rule line too long for the budget
degrades to a one-line message with the same correct form instead of a silent allow.

Stdlib-only and 3.9-safe, like ``_decision_records.py``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from _decision_records import CATEGORIES, Allowed, Defect, Refused, Verdict

# -- Where the rule lives -----------------------------------------------------------------

RULE_RELPATH = "rules/swe/adr-conventions.md"
PLUGIN_ROOT_ENV = "CLAUDE_PLUGIN_ROOT"

# -- What a refusal says ------------------------------------------------------------------

# About one screen of rule lines: enough to carry the governing sentence, not the whole rule.
RULE_CHAR_CAP = 700
MAX_LISTED_PATHS = 8

_DRAFTS_DIR = ".ai-state/decisions/drafts"
_INDEX_PATH = ".ai-state/decisions/DECISIONS_INDEX.md"
CORRECT_FORM = (
    f"Correct form: a fragment at {_DRAFTS_DIR}/<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md with id "
    "dec-draft-<8-char-hash>, numbered only by finalize at merge to main, with category one of "
    f"{', '.join(CATEGORIES)}."
)
READ_RETRY = (
    "Retry bounded: run `python3 scripts/query_adrs.py --paths <files>` (or `--grep <keyword>`), "
    f"or `grep -in '<keyword>' {_INDEX_PATH}`, then Read the index with `offset` and `limit` for "
    "the matching rows only. This refused Read loaded no path rule, so this text is the "
    "Discovery Protocol's only delivery at this moment."
)

_DEFECT_TEXT = {
    Defect.MISPLACED: "a record directly under decisions/, where finalize alone puts numbered ones",
    Defect.NESTED: "a record in a subdirectory finalize does not read",
    Defect.SELF_NUMBERED: "a numbered record; finalize numbers a record at merge to main",
    Defect.MALFORMED_NAME: "a draft whose name is not a dated fragment name with user, branch, slug",
    Defect.MALFORMED_ID: "a draft whose id is not dec-draft-<8-char-hash>",
    Defect.SELF_PICKED_ID: "a draft that picked its own dec-NNN id",
    Defect.NO_CATEGORY: "a record with no category",
    Defect.INVALID_CATEGORY: "a record whose category is none of the four values",
    Defect.CATEGORY_LOST: "an edit that leaves the record without a valid category",
    Defect.UNBOUNDED_INDEX_READ: "a Read of the decisions index with no line limit",
}


# -- Which rule lines govern which defect -------------------------------------------------


@dataclass(frozen=True)
class RuleLine:
    """One line of the rule: the ``ordinal``-th non-blank line under ``heading``."""

    heading: str
    ordinal: int


_FILE_FORMAT = RuleLine("### File Format", 0)
_FRAGMENT_SCHEMA = RuleLine("#### Fragment Filename Schema", 0)
_FINALIZED = RuleLine("#### Finalized ADRs (post-merge)", 0)
_ARCHITECTURAL_HEADING = "#### What makes a decision `architectural`"
_DISCOVERY_HEADING = "### Discovery Protocol"

# In priority order: lines are taken while they fit RULE_CHAR_CAP.
_PLACEMENT = (_FRAGMENT_SCHEMA, _FILE_FORMAT, _FINALIZED)
_NAME_AND_ID = (_FRAGMENT_SCHEMA,)
_CATEGORY = (
    RuleLine(_ARCHITECTURAL_HEADING, 0),  # "A decision is `architectural` iff ..."
    RuleLine(_ARCHITECTURAL_HEADING, 3),  # "... however consequential the trade-off"
    RuleLine(_ARCHITECTURAL_HEADING, 4),  # "Falsifier — name the component ..."
)
_INDEX_READ = (RuleLine(_DISCOVERY_HEADING, 0), RuleLine(_DISCOVERY_HEADING, 1))

_RULE_LINES_OF = {
    Defect.MISPLACED: _PLACEMENT,
    Defect.NESTED: _PLACEMENT,
    Defect.SELF_NUMBERED: _PLACEMENT,
    Defect.MALFORMED_NAME: _NAME_AND_ID,
    Defect.MALFORMED_ID: _NAME_AND_ID,
    Defect.SELF_PICKED_ID: _NAME_AND_ID,
    Defect.NO_CATEGORY: _CATEGORY,
    Defect.INVALID_CATEGORY: _CATEGORY,
    Defect.CATEGORY_LOST: _CATEGORY,
    Defect.UNBOUNDED_INDEX_READ: _INDEX_READ,
}


# -- Composing ----------------------------------------------------------------------------


def refusal_text(verdict: Verdict, rule_text: str | None) -> str:
    """The message for one refused write or read; empty for an allowed change."""
    if isinstance(verdict, Allowed):
        return ""
    head = f"Refused {verdict.path}: {_defects_text(verdict)}."
    return _compose(head, verdict.defects[0], rule_text)


def commit_refusal_text(refusals: Sequence[Refused], rule_text: str | None) -> str:
    """The message for a commit: the shared rule lines once, then one row per offending path.

    The rule lines are those of the first refusal's first defect: one defect family per message.
    """
    if not refusals:
        return ""
    count = len(refusals)
    head = f"Commit refused: {count} decision record(s) break the shape finalize promotes."
    return _compose(head, refusals[0].defects[0], rule_text, rows=_rows(refusals))


def _compose(head: str, primary: Defect, rule_text: str | None, rows: Sequence[str] = ()) -> str:
    form = READ_RETRY if primary is Defect.UNBOUNDED_INDEX_READ else CORRECT_FORM
    quoted = _quote_rule_lines(rule_text, _RULE_LINES_OF[primary])
    if quoted is None:
        return "\n".join([f"{head} {form}", *rows])
    return "\n".join([head, form, *rows, "From the ADR conventions rule:", *quoted])


def _defects_text(refused: Refused) -> str:
    return "; ".join(_DEFECT_TEXT[defect] for defect in refused.defects)


def _rows(refusals: Sequence[Refused]) -> list[str]:
    listed = [f"{r.path} - {_defects_text(r)}" for r in refusals[:MAX_LISTED_PATHS]]
    hidden = len(refusals) - MAX_LISTED_PATHS
    return listed + [f"and {hidden} more"] if hidden > 0 else listed


def _quote_rule_lines(rule_text: str | None, wanted: Sequence[RuleLine]) -> list[str] | None:
    """The wanted lines that fit the budget, or ``None`` when the rule cannot supply them."""
    if rule_text is None:
        return None
    quoted: list[str] = []
    used = 0
    for ref in wanted:
        line = _rule_line(rule_text, ref)
        if line is None:
            return None
        if used + len(line) <= RULE_CHAR_CAP:
            quoted.append(line)
            used += len(line)
    return quoted or None


def _rule_line(rule_text: str, ref: RuleLine) -> str | None:
    section = _section_lines(rule_text, ref.heading)
    return section[ref.ordinal] if section is not None and ref.ordinal < len(section) else None


def _section_lines(rule_text: str, heading: str) -> list[str] | None:
    """The non-blank lines between ``heading`` and the next heading of any level."""
    lines = rule_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return None
    section: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("#"):
            break
        if line.strip():
            section.append(line.strip())
    return section


# -- The one effect -----------------------------------------------------------------------


def rule_candidates(plugin_root: str | None, module_file: str, home: Path) -> list[Path]:
    """Where the rule may be read, best first: never the project tree being judged."""
    candidates = [Path(module_file).resolve().parents[1] / RULE_RELPATH]
    if plugin_root:
        candidates.insert(0, Path(plugin_root) / RULE_RELPATH)
    candidates.append(home / ".claude" / RULE_RELPATH)
    return candidates


def find_rule_text() -> str | None:
    """The rule's text from the first readable location, or ``None`` when none reads."""
    for path in rule_candidates(os.environ.get(PLUGIN_ROOT_ENV), __file__, Path.home()):
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue
    return None
