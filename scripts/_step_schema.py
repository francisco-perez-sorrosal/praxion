"""The declared grammar every step-document reader shares.

Two readers (`check_test_results_shape.py`'s shape gate and
`reconcile_pipeline_state.py`'s ground-truth reconciler) each grew their own
regex for the same three things a pipeline document declares: a step id, a
step heading, and a `Result:` line. The regexes drifted -- one reader's
rework fixed a bug the other's never got. This module is the single parser
for all three, so drift becomes structurally impossible: there is nowhere
left for a second implementation to diverge from.

The charter is *what a step document declares*, read without touching git or
a filesystem. Beyond the grammar that means two pure readings only the
reconciler uses today: `parse_wip_claims` (a WIP document's checklist, status
table and heading markers as a claim map) and `recorded_runs` /
`step_test_status` (which recorded test run speaks for a step, so the shape
contract and the status it implies live beside the `Result:` parser). Each
reader keeps its own policy on top: the shape checker's byte ceiling, and the
reconciler's arbitration of those claims and statuses against git
(attribution, verdicts). A switch that only one reader needs belongs in that
reader, not here. The grammar of a single `Mutation:` or `mutation:` line is
the leaf `_mutation_grammar`'s; this module keeps which step and block such a
line belongs to.

Stdlib-only and loadable under the ambient interpreter: both readers above it
are invoked by a slash command or a git hook with a bare `python3`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import accumulate
from typing import Union

# The grammar of the `Mutation:` line and the `mutation:` tag lives in the leaf
# below this module and is re-exported through `__all__`, so importers and tests
# keep reaching it as `_step_schema.<name>`.
from _mutation_grammar import (
    DECLARED_LIMIT_REASONS,
    MutationMalformed,
    MutationRan,
    MutationReading,
    MutationRefused,
    _last_mutation,
    mutation_block_reason,
    parse_mutation_line,
    parse_mutation_tag,
    render_mutation_line,
)

__all__ = [
    "GREEN",
    "RED",
    "STEP_ID_RE",
    "Counts",
    "NoRun",
    "Malformed",
    "ResultLine",
    "StepBlock",
    "step_id_from_heading",
    "step_sort_key",
    "parse_result_line",
    "split_step_blocks",
    "non_step_headings",
    "Claim",
    "parse_wip_claims",
    "checklist_step_id",
    "RecordedRun",
    "recorded_runs",
    "step_test_status",
    "MutationRan",
    "MutationRefused",
    "MutationMalformed",
    "MutationReading",
    "DECLARED_LIMIT_REASONS",
    "parse_mutation_line",
    "render_mutation_line",
    "step_mutation_reading",
    "mutation_block_reason",
    "parse_mutation_tag",
    "mutation_tagged_steps",
    "mutation_block_reasons",
]

GREEN = "green"
RED = "red"

# "<digits><optional lowercase letter>" -- "1", "1b", "12c". A leading letter
# (e.g. a stray "Nb1") is not a step id; letters after the digits sort a
# lettered addendum after its parent (see step_sort_key).
STEP_ID_RE = re.compile(r"^\d+[a-z]?$")

_HEADING_STEP_RE = re.compile(r"^#{2,4}\s*Step\s+(\d+[a-z]?)\b")
_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]")
_CODE_FENCE_RE = re.compile(r"^[ \t]{0,3}(```|~~~)")
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
# fourth, distinct state from any of these three. `typing.Union`, not the
# `|` operator, because this is a plain runtime assignment (not deferred by
# `from __future__ import annotations`, which only defers annotations) --
# `Counts | NoRun | Malformed` would raise a TypeError under the bare
# `python3` this module's readers are invoked with on stock macOS (3.9).
ResultLine = Union[Counts, NoRun, Malformed]  # noqa: UP007 -- runtime value, 3.9 floor


@dataclass(frozen=True)
class StepBlock:
    """One step heading and everything under it, up to the next one.

    `text` is the heading plus body, right-stripped -- the span a byte
    ceiling measures. `results` holds every `Result:` line found in the
    block, in document order, each with its 1-based line number -- a
    sub-heading (e.g. `### Failures`) does not open a new block, so its
    `Result:` lines (if any) stay attributed to the parent step. `mutation`
    is the block's last `Mutation:` line read, or None when it has none.
    """

    step: str | None
    title: str
    text: str
    first_line: int
    results: tuple[tuple[int, ResultLine], ...]
    mutation: MutationReading | None = None


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

    A level-2 heading that is no step heading closes the open block (its lines
    belong to no step). A file with no step heading becomes a single
    `step=None` block (the whole text). Several blocks may share one `step`
    id -- addenda and per-writer blocks are legal, not merged.
    """
    lines = text.splitlines()
    openings = [
        (idx, step_id, _heading_title(line))
        for idx, line in enumerate(lines)
        if (step_id := step_id_from_heading(line)) is not None
    ]
    if not openings:
        return (
            StepBlock(
                None,
                "",
                text.rstrip(),
                1,
                _collect_results(lines, 0, len(lines)),
                _last_mutation(lines),
            ),
        )

    stops = sorted([s for s, _, _ in openings] + [n - 1 for n, _ in non_step_headings(text)])
    ends = {start: min(s for s in (*stops, len(lines)) if s > start) for start, _, _ in openings}
    return tuple(
        StepBlock(
            step=step_id,
            title=title,
            text="\n".join(lines[start : ends[start]]).rstrip(),
            first_line=start + 1,
            results=_collect_results(lines, start, ends[start]),
            mutation=_last_mutation(lines[start : ends[start]]),
        )
        for start, step_id, title in openings
    )


def non_step_headings(text: str) -> tuple[tuple[int, str], ...]:
    """`(1-based line, text)` of each level-2 heading outside a code fence that is no step."""
    lines = text.splitlines()
    fence_lines = (bool(_CODE_FENCE_RE.match(line)) for line in lines)
    fenced = list(accumulate(fence_lines, bool.__xor__, initial=False))
    return tuple(
        (idx + 1, _heading_title(line))
        for idx, line in enumerate(lines)
        if not fenced[idx] and _heading_level(line) == 2 and step_id_from_heading(line) is None
    )


def _heading_title(line: str) -> str:
    return line.lstrip("#").strip()


def _heading_level(line: str) -> int:
    """A Markdown ATX heading's level (`## x` -> 2); 0 for any other line."""
    match = _ATX_HEADING_RE.match(line)
    return len(match.group(1)) if match else 0


def _collect_results(lines: list[str], start: int, end: int) -> tuple[tuple[int, ResultLine], ...]:
    collected = []
    for offset, line in enumerate(lines[start:end]):
        parsed = parse_result_line(line)
        if parsed is not None:
            collected.append((start + offset + 1, parsed))
    return tuple(collected)


# ---------------------------------------------------------------------------
# parse_wip_claims -- the three declared claim sources, merged
# ---------------------------------------------------------------------------

_STEP_ID_CORE = STEP_ID_RE.pattern.strip("^$")

# A claim marker, wherever a source declares one -- bare or backticked, since
# a backtick search still finds the bracket substring inside it.
_COMPLETE_MARKER_RE = re.compile(r"\[x\]|\[COMPLETE\]", re.IGNORECASE)
_IN_PROGRESS_MARKER_RE = re.compile(r"\[IN-PROGRESS\]|\[IMPLEMENTING\]", re.IGNORECASE)
_PENDING_MARKER_RE = re.compile(r"\[ \]")

# A checklist line's checkbox, and -- anchored immediately after it, past any
# bold/backtick emphasis -- the "Step <id>" it claims (a step mentioned later
# on the same line, e.g. a pre-mortem cross-reference, is not a claim for that
# step).
_CHECKLIST_BOX_RE = re.compile(r"^\s*-\s*\[(?P<box>[ xX])\]\s*(?P<rest>.*)$")
_ANCHORED_STEP_RE = re.compile(rf"^Step\s+(?P<id>{_STEP_ID_CORE})\b(?P<body>.*)$")

_TABLE_ROW_RE = re.compile(r"^\s*\|(?P<cells>.+)\|\s*$")
_TABLE_DELIMITER_CELL_RE = re.compile(r":?-+:?")
# A table's Step cell: a bare id, optionally preceded by "Step " and/or
# followed by a parenthetical label -- "<id>", "Step <id>" and "<id> (integration
# checkpoint)" all name the same step.
_TABLE_STEP_CELL_RE = re.compile(
    rf"^(?:Step\s+)?(?P<id>{_STEP_ID_CORE})(?:\s*\(.*\))?$", re.IGNORECASE
)

# The status-word vocabulary a WIP status table may use.
# Anything else, including "red", is AMBIGUOUS -- a word this vocabulary does
# not recognise is not evidence either way.
_COMPLETE_WORDS = {"complete", "completed", "done", "green"}
_IN_PROGRESS_WORDS = {"in-progress", "in progress", "implementing", "running"}
_PENDING_WORDS = {"pending", "not-started", "not started", "todo", "—", "-"}
_STATUS_VOCABULARY = (
    (_COMPLETE_WORDS, "COMPLETE"),
    (_IN_PROGRESS_WORDS, "IN-PROGRESS"),
    (_PENDING_WORDS, "PENDING"),
)
# A phrase-terminating delimiter after the leading word: a parenthetical, or a
# dash *surrounded by whitespace* -- never a bare hyphen, which is part of a
# vocabulary word itself ("in-progress", "not-started").
_STATUS_PHRASE_SPLIT_RE = re.compile(r"\(| — | - ")

Claim = str  # "COMPLETE" | "IN-PROGRESS" | "PENDING" | "AMBIGUOUS"


def parse_wip_claims(text: str) -> dict[str, Claim]:
    """Every step's claim, merged from the three sources a WIP document
    declares: an anchored checklist line, a status-table row, and a step
    heading's own marker. A step claimed differently by two sources collapses
    to AMBIGUOUS -- the caller's ground truth is the tiebreaker, not this
    parser guessing which source to trust.
    """
    claims: dict[str, Claim] = {}
    for step, claim in (*_checklist_claims(text), *_table_claims(text), *_heading_claims(text)):
        _merge_claim(claims, step, claim)
    return claims


def _merge_claim(claims: dict[str, Claim], step: str, claim: Claim) -> None:
    prev = claims.get(step)
    if prev is None:
        claims[step] = claim
    elif prev != claim and prev != "AMBIGUOUS":
        claims[step] = "AMBIGUOUS"


def _checklist_box_and_rest(line: str) -> tuple[str, str] | None:
    """The checkbox letter and the line's remainder past it and any markdown
    emphasis, or None when ``line`` is not a checklist line at all."""
    match = _CHECKLIST_BOX_RE.match(line)
    if match is None:
        return None
    return match.group("box"), match.group("rest").lstrip(" \t*`")


def checklist_step_id(line: str) -> str | None:
    """The ``"Step <id>"`` an anchored checklist line claims, or None.

    A checklist line claims a step only when its checkbox is immediately
    followed by ``Step <id>``, past any bold/backtick emphasis -- a step only
    mentioned later on the line is not this line's step. Shared by
    ``parse_wip_claims``'s checklist source and any other reader answering
    "which step does this checklist line belong to."
    """
    parsed = _checklist_box_and_rest(line)
    if parsed is None:
        return None
    step_match = _ANCHORED_STEP_RE.match(parsed[1])
    return f"Step {step_match.group('id')}" if step_match else None


def _checklist_claims(text: str) -> list[tuple[str, Claim]]:
    claims = []
    for line in text.splitlines():
        parsed = _checklist_box_and_rest(line)
        if parsed is None:
            continue
        box, rest = parsed
        step_match = _ANCHORED_STEP_RE.match(rest)
        if step_match is None:
            continue
        step_id = f"Step {step_match.group('id')}"
        claims.append((step_id, _claim_from_checkbox(box, step_match.group("body"))))
    return claims


def _claim_from_checkbox(box: str, body: str) -> Claim:
    if box.lower() == "x" or _COMPLETE_MARKER_RE.search(body):
        return "COMPLETE"
    if _IN_PROGRESS_MARKER_RE.search(body):
        return "IN-PROGRESS"
    return "PENDING"


def _heading_claims(text: str) -> list[tuple[str, Claim]]:
    claims: list[tuple[str, Claim]] = []
    for line in text.splitlines():
        step_id = step_id_from_heading(line)
        if step_id is None:
            continue
        marker_claim = _heading_marker_claim(line)
        if marker_claim is not None:
            claims.append((step_id, marker_claim))
    return claims


def _heading_marker_claim(line: str) -> Claim | None:
    if _COMPLETE_MARKER_RE.search(line):
        return "COMPLETE"
    if _IN_PROGRESS_MARKER_RE.search(line):
        return "IN-PROGRESS"
    if _PENDING_MARKER_RE.search(line):
        return "PENDING"
    return None


def _table_claims(text: str) -> list[tuple[str, Claim]]:
    """Every claim in every ``Step``+``Status``-headed table in ``text``.

    A table lacking either column (e.g. a review table headed ``#``) mints no
    claims at all -- the two columns are what make a table a claim source, not merely "a table that happens to have a Status column."
    """
    lines = text.splitlines()
    claims: list[tuple[str, Claim]] = []
    index = 0
    while index < len(lines):
        header, index = _table_header_and_columns(lines, index)
        if header is None:
            continue
        step_col, status_col = header
        while index < len(lines):
            row = _table_cells(lines[index])
            if row is None:
                break
            claim = _table_row_claim(row, step_col, status_col)
            if claim is not None:
                claims.append(claim)
            index += 1
    return claims


def _table_header_and_columns(lines: list[str], index: int) -> tuple[tuple[int, int] | None, int]:
    """The (step_col, status_col) pair for the table opening at ``index``, and
    the index just past its header+delimiter -- or ``None`` and ``index + 1``
    when no table opens there (not a header row, or not a claim-source one)."""
    header = _table_cells(lines[index])
    if header is None or index + 1 >= len(lines) or not _is_table_delimiter(lines[index + 1]):
        return None, index + 1
    return _claim_columns(header), index + 2


def _table_cells(line: str) -> list[str] | None:
    match = _TABLE_ROW_RE.match(line)
    return None if match is None else [cell.strip() for cell in match.group("cells").split("|")]


def _is_table_delimiter(line: str) -> bool:
    cells = _table_cells(line)
    return cells is not None and all(_TABLE_DELIMITER_CELL_RE.fullmatch(c) for c in cells)


def _claim_columns(header: list[str]) -> tuple[int, int] | None:
    lowered = [cell.lower() for cell in header]
    if "step" not in lowered or "status" not in lowered:
        return None
    return lowered.index("step"), lowered.index("status")


def _table_row_claim(row: list[str], step_col: int, status_col: int) -> tuple[str, Claim] | None:
    if step_col >= len(row) or status_col >= len(row):
        return None
    step_id = _table_step_id(row[step_col])
    return None if step_id is None else (step_id, _status_word_claim(row[status_col]))


def _table_step_id(cell: str) -> str | None:
    candidate = cell.strip().strip("`*")
    match = _TABLE_STEP_CELL_RE.match(candidate)
    return f"Step {match.group('id').lower()}" if match else None


def _status_word_claim(cell: str) -> Claim:
    """The claim named by the cell's LEADING status word; trailing prose after
    it (``[COMPLETE] — merged``, ``complete + follow-up``) never changes it."""
    head = _STATUS_PHRASE_SPLIT_RE.split(cell.strip().lower(), maxsplit=1)[0]
    head = head.lstrip(" \t*`[")
    for words, claim in _STATUS_VOCABULARY:
        if any(_starts_with_word(head, word) for word in words):
            return claim
    return "AMBIGUOUS" if head.strip(" \t*`]") else "PENDING"


def _starts_with_word(phrase: str, word: str) -> bool:
    """``phrase`` opens with ``word`` followed by the end or a non-word character."""
    if not word or not phrase.startswith(word):
        return False
    rest = phrase[len(word) :]
    return not rest or not (rest[0].isalnum() or rest[0] in "-_")


# --- Per-step test evidence: which recorded run speaks for a step ---

# The legacy free-form pytest-summary phrasing -- word-boundary count tokens
# (never matches "ModuleNotFoundError") -- the fallback for a step block that
# carries no `Result:` line at all (an old TEST_RESULTS.md never migrated to
# the dec-386 shape).
_PYTEST_FAIL_RE = re.compile(r"\b(\d+)\s+(?:failed|errors?)\b", re.IGNORECASE)
_PYTEST_PASS_RE = re.compile(r"\b\d+\s+passed\b", re.IGNORECASE)


@dataclass(frozen=True)
class RecordedRun:
    """One test-evidence event attributable to a step, in document order.

    ``order`` is the recording's document position (a ``Result:`` line's own
    line number, or a legacy block's first line) -- it picks a step's
    *latest* recorded run and, when a step has none of its own, the file's
    overall latest run (today's global last-line-wins, preserved as the
    fallback for test-less/status-less steps).
    """

    order: int
    step: str | None
    status: str


def recorded_runs(text: str) -> list[RecordedRun]:
    """Every ``RecordedRun`` in ``text``, in document order.

    A block's own ``Result:`` line(s) are authoritative when present: only a
    ``Counts`` line carries a status, so a later ``Malformed`` or
    ``Result: none`` line contributes no evidence and can never launder an
    earlier red run into a false green. A block with no ``Result:`` line at
    all falls back to the legacy free-form pytest-summary phrasing, for
    TEST_RESULTS.md files that never adopted the ``Result:`` convention.
    """
    runs: list[RecordedRun] = []
    for block in split_step_blocks(text):
        counted = [(n, r) for n, r in block.results if isinstance(r, Counts)]
        if counted:
            runs.extend(RecordedRun(n, block.step, r.status) for n, r in counted)
            continue
        if block.results:
            continue  # a Malformed/NoRun line exists -- no legacy fallback here
        legacy = _legacy_block_status(block.text)
        if legacy is not None:
            runs.append(RecordedRun(block.first_line, block.step, legacy))
    return runs


def _legacy_block_status(block_text: str) -> str | None:
    """A free-form pytest-summary status for a block with no ``Result:`` line."""
    status = None
    for line in block_text.splitlines():
        fail = _PYTEST_FAIL_RE.search(line)
        if fail and int(fail.group(1)) > 0:
            status = "red"
        elif _PYTEST_PASS_RE.search(line):
            status = "green"
    return status


def step_test_status(step: str, runs: list[RecordedRun]) -> str:
    """A step's test status: its own latest run -- or, with no own run, the
    file's overall latest run (today's global fallback, preserved). An own
    red run is cleared by ANY green run recorded later anywhere in the file;
    a later red never clears an existing green."""
    own = [r for r in runs if r.step == step]
    pool = own or runs
    if not pool:
        return "absent"
    latest = max(pool, key=lambda r: r.order)
    if latest.status == "green":
        return "green"
    superseded = any(r.status == "green" and r.order > latest.order for r in runs)
    return "green" if superseded else latest.status


def step_mutation_reading(step: str, blocks: tuple[StepBlock, ...]) -> MutationReading | None:
    """The reading in the step's own latest block (`"Step N"` or a bare `"N"`).

    No file-wide fallback: a step is judged by its own newest block, so a later
    run supersedes an earlier one and another step's line never speaks for it.
    """
    label = step if step.startswith("Step") else f"Step {step}"
    own = [block for block in blocks if block.step == label]
    return own[-1].mutation if own else None


def mutation_tagged_steps(plan_text: str) -> frozenset[str]:
    """The `"Step <id>"` labels a plan (or WIP checklist) tags `mutation: on`.

    A tag line belongs to the step heading or checklist line above it; the
    last tag under a step wins, and a tag before any step belongs to none.
    A step's block ends at an ATX heading (`#` .. `######` then a space) of its
    own level or higher -- a checklist step's at any such heading -- so a
    tag-shaped line in a later section such as `## Notes` can never untag the
    last step, while a deeper subsection stays inside it. A line inside a ```
    or ~~~ code fence is never a heading. Other section breaks (a bold label,
    a `---` rule, a setext heading) do not end a step.
    """
    tagged: set[str] = set()
    current: str | None = None
    current_level = 0  # heading level that opened `current`; 0 for a checklist step
    fence: str | None = None  # the open code fence's marker, while inside one
    for line in plan_text.splitlines():
        fence_marker = _CODE_FENCE_RE.match(line)
        if fence_marker:
            marker = fence_marker.group(1)
            fence = None if fence == marker else (fence or marker)
            continue
        if fence is None:  # headings and step lines exist only outside a code fence
            heading_step = step_id_from_heading(line)
            step_id = heading_step or checklist_step_id(line)
            if step_id is not None:
                current = step_id
                current_level = len(line) - len(line.lstrip("#")) if heading_step else 0
                continue
            level = _heading_level(line)
            if level and (current_level == 0 or level <= current_level):
                current = None
                continue
        tag = parse_mutation_tag(line)
        if tag is None or current is None:
            continue
        if tag:
            tagged.add(current)
        else:
            tagged.discard(current)
    return frozenset(tagged)


def mutation_block_reasons(plan_text: str, test_results_text: str) -> dict[str, str]:
    """Map each `mutation: on` step to why its reading blocks it from completing.

    A tagged step whose reading is acceptable is absent, as is any untagged
    step. The reading is the step's own latest block, so a later run
    supersedes an earlier one.
    """
    blocks = split_step_blocks(test_results_text)
    reasons = {
        step: mutation_block_reason(step_mutation_reading(step, blocks))
        for step in mutation_tagged_steps(plan_text)
    }
    return {step: reason for step, reason in reasons.items() if reason is not None}
