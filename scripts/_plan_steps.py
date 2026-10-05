"""What an implementation plan declares for each of its steps.

Today that is the `Files:` field: the paths a step is allowed to touch. The
reader here is pure -- it takes document text and returns values, never opens a
file or runs a command -- so the reconciler and the step-loop driver share one
grammar for it.

Normative grammar of the `Files:` field -- one logical line under a step
heading (or checklist step line), the label optionally bold, case-insensitive:

    **Files**: `scripts/a.py`, `scripts/b.py`

A value that wraps mid-list ends its line with a trailing comma; every further
line ending in a comma continues the same value, and a step heading or
checklist step line always closes it. A bare `none` or `n/a` declares zero
files. A candidate path is admitted only when it uses path-safe characters, holds
a `/` or `.`, has no trailing `/`, and is not a pointer into the pipeline's own
`.ai-work/` bookkeeping; parenthetical rationale is dropped before tokenizing.
"""

from __future__ import annotations

import re

from _step_schema import checklist_step_id, step_id_from_heading

# A "**Files**:" field line under a plan step.
FILES_FIELD_RE = re.compile(r"^\s*\*{0,2}Files\*{0,2}\s*:\s*(?P<files>.+)$", re.IGNORECASE)

# A field value that, once leading markdown emphasis is stripped, declares no
# files at all.
FILES_NONE_RE = re.compile(r"^(none|n/a)\b", re.IGNORECASE)
# A path-safe token -- letters, digits, the punctuation a path or glob uses.
FILE_CANDIDATE_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]-]+$")
# A parenthetical span in a Files: value is rationale ("(see WIP.md)"), never
# a path -- dropped before tokenizing so its contents can't be mistaken for one.
RATIONALE_RE = re.compile(r"\([^)]*\)")

_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
_BARE_SEPARATOR_RE = re.compile(r"[,\s]+")


def scan_step_files(text: str) -> dict[str, list[str]]:
    """Associate each ``Files:`` line of a plan/WIP text with its step.

    A ``Files:`` field that wraps mid-value ends its line with a trailing
    comma; every further line ending in a comma continues the same logical
    value, so the admission predicate in ``split_files`` sees the whole
    declaration rather than losing everything after the wrap.
    """
    lines = text.splitlines()
    result: dict[str, list[str]] = {}
    current: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        step_id = step_id_from_heading(line) or checklist_step_id(line)
        if step_id is not None:
            current = step_id
            index += 1
            continue
        field = FILES_FIELD_RE.match(line)
        if field and current:
            value, index = collect_files_value(field.group("files"), lines, index)
            result.setdefault(current, []).extend(split_files(value))
            continue
        index += 1
    return result


def collect_files_value(first: str, lines: list[str], index: int) -> tuple[str, int]:
    """Join a ``Files:`` value with its trailing-comma continuation lines,
    stopping at a step heading or checklist step line even when the current
    line still ends in a comma -- a plan heading always opens its own step.

    Returns the joined value and the index of the first line not consumed.
    """
    parts = [first]
    index += 1
    while parts[-1].rstrip().endswith(",") and index < len(lines):
        line = lines[index]
        if step_id_from_heading(line) is not None or checklist_step_id(line) is not None:
            break
        parts.append(line)
        index += 1
    return " ".join(parts), index


def split_files(raw: str) -> list[str]:
    """Split a ``Files:`` field value into the individual paths it declares.

    A bare ``none``/``n/a`` -- after stripping a bolded label's leading ``*``
    captured along with it -- declares zero files. Otherwise: strip
    parenthetical rationale spans; tokenize on backtick-quoted spans when the
    value contains any backtick, else on commas/whitespace; admit a candidate
    only when ``is_admitted_file`` accepts it.
    """
    value = raw.strip().lstrip("*").strip()
    if FILES_NONE_RE.match(value):
        return []
    value = RATIONALE_RE.sub(" ", value)
    tokens = _BACKTICK_SPAN_RE.findall(value) if "`" in value else _BARE_SEPARATOR_RE.split(value)
    candidates = (token.strip().strip("`").rstrip(".,;:") for token in tokens)
    return [c for c in candidates if c and is_admitted_file(c)]


def is_admitted_file(candidate: str) -> bool:
    """A path a step may be credited with: path-safe, shaped like a file, and
    not a pointer into this pipeline's own ``.ai-work/`` bookkeeping (a step may
    legitimately cite its own artifacts as rationale, but that is not a file it
    changed)."""
    return (
        bool(FILE_CANDIDATE_RE.match(candidate))
        and ("/" in candidate or "." in candidate)
        and not candidate.endswith("/")
        and not candidate.startswith(".ai-work/")
    )
