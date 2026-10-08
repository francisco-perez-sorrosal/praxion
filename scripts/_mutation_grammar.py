"""The grammar of one line: the sensor's `Mutation:` reading and the planner's tag.

Two lines in a pipeline document speak about mutation testing. The sensor
prints one `Mutation:` line per run, which a step's canonical writer copies
into its `TEST_RESULTS.md` section and the gate reads back; the planner writes
a `mutation: on|off` tag on a plan step to make that reading mandatory. This
module owns both grammars and the single policy over one reading
(`mutation_block_reason`), so the producer and the gate cannot drift apart.

It knows nothing of documents: which step and which block a line belongs to
is `_step_schema`'s concern, and `_step_schema` re-exports every public name
here so existing importers keep working. Stdlib-only and loadable under the
ambient interpreter, like the readers above it; imports nothing local.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

# ---------------------------------------------------------------------------
# The `Mutation:` line -- the mutation sensor's one stdout line, copied into a
# step's TEST_RESULTS.md section and read back by the gate. One renderer and
# one parser live here so the producer and the gate cannot drift apart.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MutationRan:
    """A completed run. `per_function` is the shown survivors in display order;
    `more` counts those the line's byte cap left out. `mutants >= 1` and
    `survivors + inconclusive <= mutants` are enforced by `parse_mutation_line`."""

    survivors: int
    mutants: int
    inconclusive: int
    targets: tuple[str, ...]
    per_function: tuple[tuple[str, int], ...]
    more: int


@dataclass(frozen=True)
class MutationRefused:
    """The sensor declined to count. `reason` is open at parse time -- a code
    this module has not seen is still a refusal (and blocks), never a crash."""

    reason: str
    detail: str


@dataclass(frozen=True)
class MutationMalformed:
    """A line that opens with `Mutation:` but breaks the grammar or an invariant."""

    text: str


# Absence of a line is `None`, a fourth state distinct from these three.
MutationReading = Union[MutationRan, MutationRefused, MutationMalformed]  # noqa: UP007 -- runtime value, 3.9 floor

# Refusals that state a limit of the sensor's reach, not a failure of the
# environment: the target is not in a flat layout, so there is nothing to mutate.
# Must stay a subset of `mutation_sensor.ReasonCode`'s values (pinned there).
DECLARED_LIMIT_REASONS = frozenset({"not-flat-layout"})

_MUTATION_RAN_RE = re.compile(
    r"^Mutation: survivors=(?P<survivors>\d+) mutants=(?P<mutants>\d+)"
    r"(?: inconclusive=(?P<inconclusive>\d+))?"
    r" targets=\[(?P<targets>[^\]]*)\] \((?P<functions>.*)\)$"
)
_MUTATION_REFUSED_RE = re.compile(
    r"^Mutation: unavailable reason=(?P<reason>[a-z][a-z-]*) \((?P<detail>.*)\)$"
)
_FUNCTION_COUNT_RE = re.compile(r"^(?P<name>.+): (?P<count>\d+)$")
_MORE_RE = re.compile(r"^\+(?P<more>\d+) more$")


def parse_mutation_line(line: str) -> MutationReading | None:
    """One line -> its reading; None if it is not a `Mutation:` line at all.

    The line must start at column 0 with `Mutation:`. Past that, anything the
    grammar or its invariants reject is `MutationMalformed`, never None -- a
    garbled line must not read as an absent one.
    """
    text = line.rstrip()
    if not text.startswith("Mutation:"):
        return None
    return _parse_ran(text) or _parse_refused(text) or MutationMalformed(text)


def _parse_ran(text: str) -> MutationRan | None:
    match = _MUTATION_RAN_RE.match(text)
    if match is None:
        return None
    survivors, mutants = int(match["survivors"]), int(match["mutants"])
    inconclusive = int(match["inconclusive"] or 0)
    functions = _parse_functions(match["functions"])
    if functions is None or mutants < 1 or survivors + inconclusive > mutants:
        return None
    shown, more = functions
    targets = tuple(match["targets"].split(", ")) if match["targets"] else ()
    return MutationRan(survivors, mutants, inconclusive, targets, shown, more)


def _parse_functions(body: str) -> tuple[tuple[tuple[str, int], ...], int] | None:
    """`f: 2, g: 1, +3 more` -> ((("f", 2), ("g", 1)), 3); None if any part is off-grammar."""
    parts = body.split(", ") if body else []
    more_match = _MORE_RE.match(parts[-1]) if parts else None
    more = int(more_match["more"]) if more_match else 0
    shown = []
    for part in parts[: -1 if more_match else None]:
        counted = _FUNCTION_COUNT_RE.match(part)
        if counted is None:
            return None
        shown.append((counted["name"], int(counted["count"])))
    return tuple(shown), more


def _parse_refused(text: str) -> MutationRefused | None:
    match = _MUTATION_REFUSED_RE.match(text)
    return None if match is None else MutationRefused(match["reason"], match["detail"])


def render_mutation_line(reading: MutationReading) -> str:
    """The inverse of `parse_mutation_line`; the sensor prints exactly this.

    A refusal's `detail` must already be one line -- the producer flattens its
    free text before it reaches the grammar."""
    if isinstance(reading, MutationRan):
        return _render_ran(reading)
    if isinstance(reading, MutationRefused):
        return f"Mutation: unavailable reason={reading.reason} ({reading.detail})"
    if isinstance(reading, MutationMalformed):
        return reading.text
    raise TypeError(f"not a MutationReading: {reading!r}")


def _render_ran(reading: MutationRan) -> str:
    parts = [f"Mutation: survivors={reading.survivors} mutants={reading.mutants}"]
    if reading.inconclusive:
        parts.append(f"inconclusive={reading.inconclusive}")
    parts.append(f"targets=[{', '.join(reading.targets)}]")
    shown = [f"{name}: {count}" for name, count in reading.per_function]
    if reading.more:
        shown.append(f"+{reading.more} more")
    parts.append(f"({', '.join(shown)})")
    return " ".join(parts)


def _last_mutation(lines: list[str]) -> MutationReading | None:
    readings = [r for r in map(parse_mutation_line, lines) if r is not None]
    return readings[-1] if readings else None


def mutation_block_reason(reading: MutationReading | None) -> str | None:
    """Why this reading blocks a `mutation: on` step from completing; None if it does not.

    The single policy: a ran line and the declared layout refusal pass; a
    missing, unreadable, or otherwise-refused line blocks.
    """
    if reading is None:
        return "no Mutation: line"
    if isinstance(reading, MutationRan):
        return None
    if isinstance(reading, MutationRefused):
        if reading.reason in DECLARED_LIMIT_REASONS:
            return None
        return f"refused, reason={reading.reason}"
    if isinstance(reading, MutationMalformed):
        return "unreadable Mutation: line"
    raise TypeError(f"not a MutationReading: {reading!r}")


# ---------------------------------------------------------------------------
# The `mutation: on|off` plan tag -- the planner's opt-in that makes a step's
# `Mutation:` reading mandatory. It fails closed, like the reading grammar:
# anything on a tag line that is not an explicit `off` arms the block, so a
# mis-formatted tag can never silently disarm the gate.
# ---------------------------------------------------------------------------

# A line that names the tag: any list/quote prefix and emphasis around the word.
_MUTATION_TAG_RE = re.compile(
    r"^\s*(?:(?:[-*+>]|\d+\.)\s+)*[\s*_`]*mutation[\s*_`]*:(?P<value>.*)$", re.IGNORECASE
)
_TAG_COMMENT_RE = re.compile(r"#.*")
# `off` disarms the tag even when a reason follows it (`off (no world reads)`).
_TAG_OFF_RE = re.compile(r"off\b")


def parse_mutation_tag(line: str) -> bool | None:
    """One line -> True (tagged), False (explicit `off`), None (not a tag line).

    Surrounding emphasis, a list prefix, case and a trailing `# comment` are
    all tolerated. A line that names the tag with any value but `off` -- `on`
    or something unreadable -- is tagged. A well-formed `Mutation:` reading is not a tag.
    """
    match = _MUTATION_TAG_RE.match(line)
    if match is None or isinstance(
        parse_mutation_line(line.strip()), (MutationRan, MutationRefused)
    ):
        return None
    value = _TAG_COMMENT_RE.sub("", match["value"]).strip(" \t*_`").lower()
    return _TAG_OFF_RE.match(value) is None
