"""The declared grammar every step-document reader shares.

Two readers (`check_test_results_shape.py`'s shape gate and
`reconcile_pipeline_state.py`'s ground-truth reconciler) each grew their own
regex for the same three things a pipeline document declares: a step id, a
step heading, and a `Result:` line. The regexes drifted -- one reader's
rework fixed a bug the other's never got. This module is the single parser
for all three, so drift becomes structurally impossible: there is nowhere
left for a second implementation to diverge from.

Each reader keeps its own policy on top of these primitives (the shape
checker's byte ceiling, the reconciler's per-step status and attribution) --
this module owns only the shared grammar, not what either reader does with
it.

Stdlib-only and loadable under the ambient interpreter: both readers above it
are invoked by a slash command or a git hook with a bare `python3`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

GREEN = "green"
RED = "red"

# "<digits><optional lowercase letter>" -- "1", "1b", "12c". A leading letter
# (e.g. a stray "Nb1") is not a step id; letters after the digits sort a
# lettered addendum after its parent (see step_sort_key).
STEP_ID_RE = re.compile(r"^\d+[a-z]?$")

_HEADING_STEP_RE = re.compile(r"^#{2,4}\s*Step\s+(\d+[a-z]?)\b")
_SORT_KEY_RE = re.compile(r"(\d+)([a-z]?)\s*$")

_RESULT_PREFIX_RE = re.compile(r"^Result:\s*(.*)$")
_TOKEN_RE = re.compile(r"(?P<key>[A-Za-z]+)=(?P<value>\S+)")
_KNOWN_KEYS = ("pass", "fail", "skip", "error", "preexisting")
_REQUIRED_KEYS = ("pass", "fail")


@dataclass(frozen=True)
class Counts:
    """A parsed `Result: pass=<n> fail=<n> ...` line.

    `preexisting` counts baseline failures still red (raw pytest failed =
    `fail + preexisting`); `status` never reads it -- a writer's
    classification can never turn red into green by inflating the baseline.
    """

    passed: int
    failed: int
    skipped: int = 0
    errors: int = 0
    preexisting: int = 0

    @property
    def status(self) -> str:
        if self.passed == 0 or self.failed > 0 or self.errors > 0:
            return RED
        return GREEN


@dataclass(frozen=True)
class NoRun:
    """A declared `Result: none` line -- no test evidence, not a failure."""

    rationale: str


@dataclass(frozen=True)
class Malformed:
    """A `Result:` line that fails the grammar, naming why."""

    reason: str


# The three shapes a `Result:` line can take. `parse_result_line` returns
# `ResultLine | None`, where `None` means "not a Result: line at all" -- a
# fourth, distinct state from any of these three.
ResultLine = Counts | NoRun | Malformed


@dataclass(frozen=True)
class StepBlock:
    """One step heading and everything under it, up to the next one.

    `text` is the heading plus body, right-stripped -- the span a byte
    ceiling measures. `results` holds every `Result:` line found in the
    block, in document order, each with its 1-based line number -- a
    sub-heading (e.g. `### Failures`) does not open a new block, so its
    `Result:` lines (if any) stay attributed to the parent step.
    """

    step: str | None
    title: str
    text: str
    first_line: int
    results: tuple[tuple[int, ResultLine], ...]


def step_id_from_heading(line: str) -> str | None:
    """A step heading (`##`-`####`, `Step <id>`) -> its `"Step <id>"` label; any other line -> None."""
    match = _HEADING_STEP_RE.match(line)
    return f"Step {match.group(1)}" if match else None


def step_sort_key(step: str) -> tuple[int, str]:
    """Order ids the way readers expect: `1 < 1b < 2 < 10`.

    Accepts either the full `"Step <id>"` label or a bare id -- both the
    reconciler's plan-heading ids and the composer's verdict-JSON `step`
    values pass through here. A string with no trailing id sorts first,
    stable on its own text.
    """
    match = _SORT_KEY_RE.search(step)
    if match is None:
        return (0, step)
    return (int(match.group(1)), match.group(2))


def parse_result_line(line: str) -> ResultLine | None:
    """Parse one line's `Result:` contract; None if it isn't a Result: line.

    The line must start at column 0 with `Result:`. `none` is recognised
    case-insensitively as the first word after the colon. Recognised keys:
    `pass`, `fail`, `skip`, `error`, `preexisting` -- `pass` and `fail` are
    required and each known key may appear at most once; an unrecognised
    `key=<value>` token is ignored (additive evolution: a future `xfail=`
    does not break an old reader).
    """
    match = _RESULT_PREFIX_RE.match(line)
    if match is None:
        return None
    rest = match.group(1).strip()

    none_run = _maybe_none(rest)
    if none_run is not None:
        return none_run
    return _parse_counts(rest)


def _maybe_none(rest: str) -> NoRun | None:
    if not rest:
        return None
    parts = rest.split(None, 1)
    if parts[0].lower() != "none":
        return None
    remainder = parts[1] if len(parts) > 1 else ""
    return NoRun(remainder.lstrip("—-").strip())


def _parse_counts(rest: str) -> Counts | Malformed:
    tokens = _TOKEN_RE.findall(rest)
    if not tokens:
        return Malformed(f"no recognized key=value tokens: {rest!r}")

    seen: dict[str, int] = {}
    for key, value in tokens:
        key_lower = key.lower()
        if key_lower not in _KNOWN_KEYS:
            continue  # future keys are additive -- ignored, not rejected
        if key_lower in seen:
            return Malformed(f"repeated key: {key_lower}")
        if not value.isdigit():
            return Malformed(f"non-numeric value for {key_lower}: {value!r}")
        seen[key_lower] = int(value)

    missing = [key for key in _REQUIRED_KEYS if key not in seen]
    if missing:
        return Malformed(f"missing required key(s): {', '.join(missing)}")

    return Counts(
        passed=seen["pass"],
        failed=seen["fail"],
        skipped=seen.get("skip", 0),
        errors=seen.get("error", 0),
        preexisting=seen.get("preexisting", 0),
    )


def split_step_blocks(text: str) -> tuple[StepBlock, ...]:
    """Split `text` into `StepBlock`s at `#{2,4} Step <id>` headings only.

    A file with no step heading becomes a single `step=None` block (the
    whole text). Several blocks may share one `step` id -- addenda and
    per-writer blocks are legal, not merged.
    """
    lines = text.splitlines()
    openings = [
        (idx, step_id, _heading_title(line))
        for idx, line in enumerate(lines)
        if (step_id := step_id_from_heading(line)) is not None
    ]
    if not openings:
        return (StepBlock(None, "", text.rstrip(), 1, _collect_results(lines, 0, len(lines))),)

    boundaries = [start for start, _, _ in openings] + [len(lines)]
    return tuple(
        StepBlock(
            step=step_id,
            title=title,
            text="\n".join(lines[start : boundaries[i + 1]]).rstrip(),
            first_line=start + 1,
            results=_collect_results(lines, start, boundaries[i + 1]),
        )
        for i, (start, step_id, title) in enumerate(openings)
    )


def _heading_title(line: str) -> str:
    return line.lstrip("#").strip()


def _collect_results(lines: list[str], start: int, end: int) -> tuple[tuple[int, ResultLine], ...]:
    collected = []
    for offset, line in enumerate(lines[start:end]):
        parsed = parse_result_line(line)
        if parsed is not None:
            collected.append((start + offset + 1, parsed))
    return tuple(collected)
