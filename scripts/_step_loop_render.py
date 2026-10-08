"""The pure render of the step-loop driver: request ids, the Agent call, the prompt files and
the texts a person or the version history reads. No file is opened and no clock is read, so
unchanged inputs give byte-identical output.

Normative grammar of a request id, characters `[a-z0-9-]`:

    s<step>[-p<k>]-a<n>-<kind>[-r<round>]

`-p<k>` appears only for attempt series k >= 2, `-r<round>` only on a `review` or `revise`
request, and those carry the attempt that verified. A prompt never holds a model name, plan
text outside the step block or a second `Read-only:` line.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, NamedTuple, cast, get_args

from _markdown_tables import find_section, split_lines
from _plan_steps import PlanStep
from _step_schema import STEP_ID_RE

PROMPT_CEILING = 16_000
DESCRIPTION_LIMIT = 40
SLOT_BOUNDS = {  # characters; a slot named here is cut to its bound
    "health-guards": 3_000,
    "review-findings": 3_000,
    "key-signals": 2_000,
    "corrections": 1_500,
    "previous-attempts": 1_000,
    "latest-reading": 1_500,
    "protected-paths": 1_500,
    "iteration-patches": 1_000,
}
PROGRESS_BOUND = 2_500  # a goal prompt keeps the newest progress lines within this

Kind = Literal["implement", "revise", "review"]
Model = Literal["opus", "sonnet"]


@dataclass(frozen=True)
class RequestKey:
    """What names a request; `attempt` is the attempt that verified for a revise or review."""

    step: str
    attempt: int
    kind: Kind
    series: int = 1
    round: int | None = None

    def __post_init__(self) -> None:
        round_ = 1 if self.round is None else self.round
        if STEP_ID_RE.match(self.step) is None or min(self.attempt, self.series, round_) < 1:
            raise ValueError(f"not a request: step {self.step!r}, attempt {self.attempt}")
        if self.kind not in get_args(Kind) or (self.kind == "implement") != (self.round is None):
            raise ValueError(f"not a request kind and round: {self.kind!r}, round {self.round}")

    @property
    def id(self) -> str:
        series = f"-p{self.series}" if self.series >= 2 else ""
        round_ = f"-r{self.round}" if self.round else ""
        return f"s{self.step}{series}-a{self.attempt}-{self.kind}{round_}"


_REQUEST_RE = re.compile(
    r"s(?P<step>[0-9]+[a-z]?)(?:-p(?P<series>[0-9]+))?-a(?P<attempt>[0-9]+)"
    r"-(?P<kind>implement|revise|review)(?:-r(?P<round>[0-9]+))?"
)


def parse_request_id(text: str) -> RequestKey | None:
    """The key whose `id` is `text`, or None when `text` is the id of no key."""
    found = _REQUEST_RE.fullmatch(text)
    if found is None:
        return None
    try:
        key = RequestKey(
            found["step"],
            int(found["attempt"]),
            cast(Kind, found["kind"]),
            int(found["series"] or 1),
            int(found["round"]) if found["round"] else None,
        )
    except ValueError:
        return None
    return key if key.id == text else None


@dataclass(frozen=True)
class AgentCall:
    """The Agent tool's parameters, passed unchanged by whoever executes the request."""

    subagent_type: Literal["praxion:implementer", "praxion:verifier"]
    model: Model
    description: str
    prompt: str

    def __post_init__(self) -> None:
        if self.model not in get_args(Model):
            raise ValueError(f"model must be one of {get_args(Model)}, got {self.model!r}")
        if len(self.description) > DESCRIPTION_LIMIT:
            raise ValueError(f"description is over {DESCRIPTION_LIMIT} characters")


@dataclass(frozen=True)
class SpawnRequest:
    """One agent to start; the key's attempt lies within the attempt cap."""

    key: RequestKey
    attempt_cap: int
    agent_call: AgentCall
    prompt_path: str
    reissued: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.key.attempt <= self.attempt_cap:
            raise ValueError(f"attempt {self.key.attempt} is outside 1..{self.attempt_cap}")


def spawn_request(slug: str, step: PlanStep, key: RequestKey, cap: int, work: str) -> SpawnRequest:
    """The request for `step`: who to start, with which model, and the file it reads."""
    if key.step != step.id:
        raise ValueError(f"the key names step {key.step!r}, not {step.id!r}")
    review, path = key.kind == "review", f"{work}/PROMPT_{key.id}.md"
    label = {
        "implement": f"attempt {key.attempt}/{cap}" + (f" · rev {key.series}" * (key.series >= 2)),
        "revise": f"revision {key.round}",
        "review": f"light review {key.round}",
    }[key.kind]
    holds = "the step and the change to review" if review else "your step and its constraints"
    prompt = f"Task slug: {slug}\nSpawn request: {key.id}\n"
    prompt += f"{'Mode: light-review. ' * review}Read {path} first and follow it; it holds {holds}."
    call = AgentCall(
        "praxion:verifier" if review else "praxion:implementer",
        "sonnet" if review else step.routing,
        f"Step {step.id} {label}",
        prompt,
    )
    return SpawnRequest(key, cap, call, path)


class PriorAttempt(NamedTuple):  # one earlier driver attempt, as the ledger and gate recorded it
    attempt: int
    agent_id: str
    stop_reason: str
    turns: int | None
    max_turns: int | None
    gate: str
    commit: str | None


@dataclass(frozen=True)
class GoalState:
    """What a goal step's prompt reads from the files besides its step block."""

    reading: tuple[str, ...] = ()
    protected: tuple[str, ...] = ()
    patches: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptInputs:
    """Everything a prompt is a function of; the texts are document contents (or "")."""

    request: SpawnRequest
    step: PlanStep
    work_dir: str
    brief_text: str = ""
    wip_text: str = ""
    findings_text: str = ""
    previous: tuple[PriorAttempt, ...] = ()
    dirty_files: tuple[str, ...] = ()
    review_range: tuple[str, str] | None = None
    goal: GoalState | None = None  # for a goal step's implement request


# (tag, the tag's `source` attribute or "", text, the path holding the full text a cut names)
_Slot = tuple[str, str, str, str]


def render_prompt(inputs: PromptInputs) -> tuple[str, tuple[tuple[str, str], ...]]:
    """The prompt file of a request and its (code, message) warnings; nothing timestamped."""
    step, request = inputs.step, inputs.request
    key, cap, sid = request.key, request.attempt_cap, f"Step {inputs.step.id}"
    kind = "goal" if inputs.goal is not None and key.kind == "implement" else key.kind
    opening = _OPENING[kind].format(sid=sid, n=key.attempt, cap=cap, r=key.round)
    shown = [_render_slot(slot) for slot in _slots(inputs)]
    sections = [
        "\n".join([*request.agent_call.prompt.splitlines()[:2], opening]),
        f'<step id="{step.id}">\n{step.block}\n</step>',
        *(element for element, _ in shown if element),
        _FINISH[kind].format(sid=sid, id=step.id, work=inputs.work_dir),
    ]
    text, warnings = "\n\n".join(sections) + "\n", tuple(w for _, w in shown if w)
    if len(text) > PROMPT_CEILING:
        warnings += (("step-block-oversize", f"{sid}: its block alone pushes the prompt over"),)
    return text, warnings


_FINISH_WORK = """\
<finish>
1. Record a `## {sid}` section in {work}/TEST_RESULTS.md ending with your Check: Result: line.
2. Flip only {sid}'s line in {work}/WIP.md; never edit an Attempts: or Check: line.
3. Stop in a committable state and never commit: the step-loop driver commits once it verifies.
4. End with at most 5 lines whose last line is one marker: [COMPLETE], [BLOCKED] (add a Spec
   Question if a due outer-loop test contradicts the spec), [CONFLICT] or [PARTIAL].
</finish>"""
_FINISH_REVIEW = """\
<finish>
1. Write your review to {work}/LIGHT_REVIEW_step-{id}.md: `verdict: [PARTIAL]` first, each finding
   as you confirm it, the verdict line last (`verdict: accept`, or `verdict: revise` + findings).
2. Review only the change in <diff> against the step above; edit no other file.
3. End with at most 15 lines: the verdict block, then one marker last: [COMPLETE] or [PARTIAL].
</finish>"""
_FINISH_GOAL = """\
<finish>
1. Pick one unit of the goal, finish it, and leave the tree committable.
2. Append one line to `## Progress record` in {work}/WIP.md: what was done, what remains and
   what was learned. Record nothing in TEST_RESULTS.md and tick nothing: the step-loop driver
   runs the gate.
3. Run the check exactly as written above, with no pipe: no other shell command is permitted.
   Quote its last lines.
4. Edit only the step's files; never commit, the step-loop driver commits once it keeps the unit.
5. End with at most 5 lines whose last line is one marker: [COMPLETE], [PARTIAL], [CONFLICT] or
   [BLOCKED] (when the goal cannot be met as stated).
</finish>"""
_OPENING = {
    "implement": "You are implementing {sid} of IMPLEMENTATION_PLAN.md, attempt {n} of {cap}.",
    "revise": "You are revising {sid} of IMPLEMENTATION_PLAN.md after its light review "
    "(round {r}). Address only the findings below.",
    "review": "You are the light reviewer for {sid} of IMPLEMENTATION_PLAN.md, round {r}.",
    "goal": "You are working toward the goal of {sid} of IMPLEMENTATION_PLAN.md, "
    "iteration {n} of {cap}.",
}
_FINISH = {
    "implement": _FINISH_WORK,
    "revise": _FINISH_WORK,
    "review": _FINISH_REVIEW,
    "goal": _FINISH_GOAL,
}


def _slots(inputs: PromptInputs) -> list[_Slot]:
    """The slots of the prompt's kind, in order."""
    work, kind, step = inputs.work_dir, inputs.request.key.kind, inputs.step

    def section(tag: str, doc: str, title: str) -> _Slot:
        text = inputs.wip_text if doc == "WIP.md" else inputs.brief_text
        return (tag, f"{doc} § {title}", section_body(text, title), f"{work}/{doc}")

    if kind == "review":
        if inputs.review_range is None:
            raise ValueError("a review prompt needs the commit range to review")
        diff = f"git diff {'..'.join(inputs.review_range)} -- {' '.join(step.files)}"
        return [section("key-signals", "TASK_BRIEF.md", "Key Signals"), ("diff", "", diff, "")]
    if inputs.goal is not None and kind == "implement":
        return _goal_slots(inputs, inputs.goal)
    if kind == "revise":
        file = f"LIGHT_REVIEW_step-{step.id}.md"
        lead = ("review-findings", file, inputs.findings_text.strip(), f"{work}/{file}")
    else:
        lines = [" · ".join(attempt_columns(a, "agent ")) for a in inputs.previous]
        if lines and inputs.dirty_files:
            edited = ", ".join(inputs.dirty_files)
            lines.append(f"Uncommitted edits to {edited} remain; read them first.")
        lead = ("previous-attempts", "", "\n".join(lines), f"{work}/ITERATION_LEDGER.jsonl")
    return [
        lead,
        section("health-guards", "TASK_BRIEF.md", "Health Guards"),
        section("corrections", "WIP.md", "Corrections in force"),
    ]


def _goal_slots(inputs: PromptInputs, goal: GoalState) -> list[_Slot]:
    """A goal step's slots. The step block already carries the goal, its check and its files."""
    work = inputs.work_dir
    wip, plan, results = (
        f"{work}/{name}.md" for name in ("WIP", "IMPLEMENTATION_PLAN", "TEST_RESULTS")
    )
    progress = section_body(inputs.wip_text, "Progress record").splitlines()
    return [
        ("latest-reading", "TEST_RESULTS.md", "\n".join(goal.reading) or "No reading yet.", results),
        ("progress-record", "WIP.md, Progress record, newest first",
         _newest_first([line for line in progress if line.strip()], PROGRESS_BOUND, wip), wip),
        ("protected-paths", "", "\n".join(f"- {path}" for path in goal.protected), plan),
        ("iteration-patches", work,"\n".join(goal.patches), work),
    ]  # fmt: skip


_LINES_CUT = "[{count} earlier lines cut: full record in {path}]"


def _newest_first(lines: Sequence[str], bound: int, path: str) -> str:
    """`lines` newest first, whole lines only, the newest always; a cut says how many it dropped."""
    kept: list[str] = []
    for line in reversed(lines):
        left = len(lines) - len(kept) - 1
        tail = [_LINES_CUT.format(count=left, path=path)] if left else []
        if kept and len("\n".join([*kept, line, *tail])) > bound:
            break
        kept.append(line)
    cut = len(lines) - len(kept)
    return "\n".join([*kept, *([_LINES_CUT.format(count=cut, path=path)] if cut else [])])


def section_body(text: str, title: str) -> str:
    """The body of the `## <title>` or `### <title>` section; "" when absent or empty."""
    lines = split_lines(text)
    span = next(filter(None, (find_section(lines, level, title) for level in (2, 3))), (0, 0))
    return "\n".join(lines[span[0] : span[1]]).strip("\n").rstrip()


def _render_slot(slot: _Slot) -> tuple[str, tuple[str, str] | None]:
    """The tagged slot ("" when empty) and the warning a cut raises."""
    tag, source, text, path = slot
    bound, warning = SLOT_BOUNDS.get(tag), None
    if bound and len(text) > bound:
        marker, kept = f"[truncated: full text in {path}]", []
        for line in text.splitlines():
            if len("\n".join([*kept, line, marker])) > bound:
                break
            kept.append(line)
        text = "\n".join([*kept, marker])
        warning = ("slot-truncated", f"{tag} cut to {bound} characters: full text in {path}")
    attribute = f' source="{source}"' if source else ""
    return (f"<{tag}{attribute}>\n{text}\n</{tag}>" if text else ""), warning


def attempt_columns(attempt: PriorAttempt, agent_label: str) -> list[str]:
    """One attempt as columns: dot-joined in a prompt and a handoff, space-joined on stderr."""
    turns = "?" if attempt.turns is None else f"{attempt.turns}/{attempt.max_turns or '?'}"
    commit = attempt.commit[:7] if attempt.commit else "no commit"
    return [
        f"attempt {attempt.attempt}",
        f"{agent_label}{attempt.agent_id}",
        f"{attempt.stop_reason} {turns}",
        attempt.gate,
        commit,
    ]


@dataclass(frozen=True)
class Invocation:
    """How the command was started and the options a printed command echoes (empty unless asked).

    `command` is the one place a printed command is built. It lives here, beside the texts that
    embed it, because the CLI module imports this one and not the reverse.
    """

    program: str
    location: tuple[str, ...] = ()

    @classmethod
    def of(cls, invoke: str | Invocation) -> Invocation:
        """A plain program string stands for an invocation with no options to echo."""
        return invoke if isinstance(invoke, cls) else cls(invoke)

    def command(self, verb: str, slug: str, *rest: str) -> str:
        quoted = tuple(shlex.quote(option) for option in self.location)
        return " ".join((self.program, verb, slug, *rest, *quoted))


class StopView(NamedTuple):
    """A stop as its surfaces show it; `evidence` is the one line the loop state wrote."""

    cause: str
    step: str | None
    evidence: str
    attempts: tuple[PriorAttempt, ...]
    slug: str
    invoke: str | Invocation


_ACTIONS = {  # `{step}` is the stop's step id
    "attempts-exhausted": "revise the step block (split it, or fix its Check: line)",
    "stalled": (
        "read ITERATION_*.patch and the progress record, then reset the goal or take it by hand"
    ),
    "blocked-marker": "resolve the blocker, then record the resolution in the step block",
    "conflict-marker": "add the path to the step's Files: or split the step",
    "human-verdict": "verify the step by hand and correct WIP.md, or restore the mutation sensor",
    "unnamed-attempts": "name the step on the Attempts: line or delete the line",
    "review-revised-twice": "set verdict: accept in LIGHT_REVIEW_step-{step}.md or revise the step",
    "review-unfinished": "finish LIGHT_REVIEW_step-{step}.md with verdict: accept or revise",
    "revision-failed": "revise the step block, or finish the revision by hand and accept it",
    "not-driven": "run the step outside the loop as the plan says and tick its WIP.md line",
    "dependency-defect": "correct the [depends-on: ...] annotations in IMPLEMENTATION_PLAN.md",
    "commit-disturbed-tree": "restore what you need from the snapshot, then delete it",
    "loop-state-defect": "keep the request whose agent ran and remove request=<id> from the other",
    "iteration-budget": "re-tier or split the remaining steps with the user",
}


def stop_stderr(stop: StopView) -> str:
    """The block a person watching reads: what happened, why, what to do and where."""
    who = f"Step {stop.step}" if stop.step else "the loop"
    action = _ACTIONS[stop.cause].format(step=stop.step)
    what = {
        "iteration-budget": "the iteration budget is used up",
        "not-driven": f"{who} is handed back to you",
    }.get(stop.cause, f"{who} needs a human decision")
    return "\n".join([
        f"step_loop: stopped — {what} ({stop.cause}).",
        *("  " + "  ".join(attempt_columns(a, "")) for a in stop.attempts),
        f"  Why: {stop.evidence}",
        f"  Next: {action}, then run: {Invocation.of(stop.invoke).command('next', stop.slug)}",
        f"  Handoff: .ai-work/{stop.slug}/HANDOFF.md (§2 carries this stop)",
    ])  # fmt: skip


def stop_next_action(stop: StopView) -> str:
    """The paragraph that becomes the handoff's next-action section."""
    budget = stop.cause == "iteration-budget"
    resume = Invocation.of(stop.invoke).command("next", stop.slug)
    what = "iteration budget used up" if budget else stop.cause
    action = _ACTIONS[stop.cause].format(step=stop.step)
    owed = "Orchestrator action owed" if stop.cause == "not-driven" else "Human decision owed"
    where = f" at `Step {stop.step}`" if stop.step else ""
    return "\n".join([
        f"The step-loop driver stopped{where}: {what} (exit {3 if budget else 2}).",
        stop.evidence,
        *(f"- {' · '.join(attempt_columns(a, 'agent '))}" for a in stop.attempts),
        f"{owed}: {action}.",
        f"Then resume the loop: `/praxion:step-loop {stop.slug}` (it runs `{resume}`).",
    ])  # fmt: skip


def commit_message(step: PlanStep, slug: str, request: SpawnRequest, result_line: str) -> str:
    """The message of a verified step's commit: subject, one sentence, deciding line, trailer."""
    key = request.key
    if key.kind == "review" or "\n" in result_line:
        raise ValueError("a commit follows an implement or revise request and one Result: line")
    subject = " ".join(re.sub(r"\[[^\]]*\]", " ", step.title).split()) or f"Step {step.id}"
    turn = f"attempt {key.attempt}" if key.kind == "implement" else f"review revision {key.round}"
    sentence = f"Step {step.id} of {slug}, {turn}: verified by the step-loop driver."
    return f"{subject}\n\n{sentence}\n{result_line}\n\nStep-Loop-Request: {key.id}"
