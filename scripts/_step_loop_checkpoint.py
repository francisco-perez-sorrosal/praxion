"""The pockets a step's gate leaves for the loop's checkpoint, and the checkpoint block's grammar.

A gate that leaves a widened pocket unrun writes one `Deferred:` line for it in the step's block
of `TEST_RESULTS.md`; once every step is done the loop runs each waiting pocket's whole suite
once and writes one checkpoint block for it. Which pockets wait, and for which steps, is never
stored: `waiting_pockets` derives it on every call from that file and the ledger's records, so
there is no second writer and no ordering hazard against the commit.

A pocket waits from the first committed step that deferred it until a green checkpoint block for
its root appears after that deferral. A deferral counts only once its attempt is committed (the
ledger record names the request and a commit), because an uncommitted attempt's work is not part
of the history a checkpoint would judge. A file written before deferrals existed holds no
`Deferred:` line and derives nothing.

Pure leaf: values in, values out; this module reads no file and no clock. It never imports the
gate or the run modules, which import it, so no cycle can form (`_step_loop_files` is imported
only for the gate block's heading and the step label).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from _step_loop_files import STEP_LABEL, gate_heading
from _step_schema import (
    CHECKPOINT_HEADING_PREFIX,
    GREEN,
    Counts,
    is_checkpoint_heading,
    parse_result_line,
    step_id_from_heading,
    step_sort_key,
)

if TYPE_CHECKING:
    from iteration_ledger import IterationRecord

_HEADING_MARK = "## "
_FENCES = ("```", "~~~")
_DEFERRED_PREFIX = "Deferred: "
_DEFERRED_SUFFIX = " (widened): whole suite waits for the checkpoint"
_AT = " at "
_COVERS_PREFIX = "Covers: "


# --- The `Deferred:` line ---------------------------------------------------------------------


def deferred_line(root: str) -> str:
    """The line a gate writes for a widened pocket it left unrun (`.` names the root pocket)."""
    return f"{_DEFERRED_PREFIX}{root}{_DEFERRED_SUFFIX}"


def deferred_roots(lines: Iterable[str]) -> tuple[str, ...]:
    """The pocket roots the `Deferred:` lines among `lines` name, in order. A line counts only
    at column 0 and outside a code fence, as every other line of a results block does."""
    roots = (_deferred_root(line) for line in _outside_fences(lines))
    return tuple(root for root in roots if root is not None)


def _outside_fences(lines: Iterable[str]) -> tuple[str, ...]:
    """The lines that sit outside a code fence, the fence lines themselves left out."""
    outside = []
    inside_fence = False
    for line in lines:
        if line.lstrip().startswith(_FENCES):
            inside_fence = not inside_fence
        elif not inside_fence:
            outside.append(line)
    return tuple(outside)


def _deferred_root(line: str) -> str | None:
    named = len(line) - len(_DEFERRED_PREFIX) - len(_DEFERRED_SUFFIX)
    if named > 0 and line.startswith(_DEFERRED_PREFIX) and line.endswith(_DEFERRED_SUFFIX):
        return line[len(_DEFERRED_PREFIX) : len(line) - len(_DEFERRED_SUFFIX)]
    return None


# --- A waiting pocket -------------------------------------------------------------------------


@dataclass(frozen=True)
class WaitingPocket:
    """A pocket whose whole suite waits for the checkpoint, and the steps that left it unrun.

    The steps are bare ids, each once, in plan order; `waiting_pockets` is the one builder.
    """

    root: str
    steps: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError(f"pocket {self.root!r} waits for no step")
        if len(set(self.steps)) != len(self.steps):
            raise ValueError(f"pocket {self.root!r} names a step twice: {self.steps}")
        if self.steps != tuple(sorted(self.steps, key=step_sort_key)):
            raise ValueError(f"pocket {self.root!r} names steps out of plan order: {self.steps}")


def waiting_pockets(
    results_text: str, records: Iterable[IterationRecord]
) -> tuple[WaitingPocket, ...]:
    """The pockets that wait, derived from the results file and the ledger's records.

    One pass in file order, which is time order (a gate block rewritten for a refusal keeps its
    place): a committed step's `Deferred:` lines add the step to each named pocket, and a green
    checkpoint block for a root clears every deferral of it read so far.
    """
    committed = _committed_gate_blocks(records)
    waiting: dict[str, set[str]] = {}
    for heading, body in _blocks(results_text):
        step_id = committed.get(heading)
        if step_id is not None:
            for deferred in deferred_roots(body):
                waiting.setdefault(deferred, set()).add(step_id)
        elif (checked := checkpoint_root(heading.removeprefix(_HEADING_MARK))) is not None:
            if _decided_green(body):  # a red or cut-off run clears nothing
                waiting.pop(checked, None)
    return tuple(
        WaitingPocket(root, tuple(sorted(steps, key=step_sort_key)))
        for root, steps in waiting.items()
    )


def _committed_gate_blocks(records: Iterable[IterationRecord]) -> dict[str, str]:
    """The heading of each gate block whose attempt was committed, mapped to its bare step id."""
    committed = {}
    for record in records:
        if record.request is not None and record.commit is not None:
            step_id = record.step.removeprefix(STEP_LABEL)
            committed[gate_heading(step_id, record.request)] = step_id
    return committed


def _blocks(text: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each block of the text as `(its heading line, the lines under it outside code fences)`.

    A block runs to the next level-2 heading or step heading, the ends the shape checker gives a
    checkpoint block; a heading inside a code fence opens nothing.
    """
    blocks: list[tuple[str, list[str]]] = []
    for line in _outside_fences(text.splitlines()):
        if line.startswith(_HEADING_MARK) or step_id_from_heading(line):
            blocks.append((line, []))
        elif blocks:
            blocks[-1][1].append(line)
    return tuple((heading, tuple(body)) for heading, body in blocks)


def _decided_green(body: Iterable[str]) -> bool:
    """The block's deciding line, its last `Result:` line, counts a pass: a cut-off run
    (`Result: none`), a failing run and a line that breaks the grammar clear nothing."""
    deciding = None
    for line in body:
        deciding = parse_result_line(line) or deciding
    return isinstance(deciding, Counts) and deciding.status == GREEN


# --- The checkpoint block's heading and `Covers:` line ------------------------------------------


def checkpoint_heading(root: str, head: str) -> str:
    """The heading of the block a checkpoint run of `root` at the commit `head` writes."""
    return f"{_HEADING_MARK}{CHECKPOINT_HEADING_PREFIX}{root}{_AT}{head}"


def checkpoint_root(title: str) -> str | None:
    """The pocket root a checkpoint heading's text names; None for any other heading."""
    if not is_checkpoint_heading(title):
        return None
    root, at, _ = title[len(CHECKPOINT_HEADING_PREFIX) :].rpartition(_AT)
    return root if at and root else None


def covers_line(steps: Iterable[str]) -> str:
    """The line naming the steps a checkpoint block answers for (bare ids, as given)."""
    return _COVERS_PREFIX + ", ".join(f"{STEP_LABEL}{step_id}" for step_id in steps)
