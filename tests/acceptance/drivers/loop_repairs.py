"""Driver for the step-loop repairs: withdrawal, plan amendment, review rounds, node
entries, prompts, follow-ups, echoed location options, a record held in flight, Check
probing, unreadable plan fields and result-block size.

It builds on the step-loop driver (`step_loop`), which builds the checkout, the plan, the
progress file and the Agent tool's test double, and runs `scripts/step_loop.py` as the
orchestrator does. What this driver adds is reached through the same command line and the
same task-directory files, never through the driver's modules:

- a call with any combination of the three location options, or none (`call`);
- a person inserting a step block ahead of another in `IMPLEMENTATION_PLAN.md`;
- a return whose final message the scenario writes (a `Follow-ups:` line, a review verdict);
- the rendered prompt of a request (`prompt_path`), with its `<step ...>` element, the plan
  block copied verbatim, cut away so a scenario reads only what the driver itself says;
- a step's unit test that holds every run of itself until the scenario releases it, so a
  `record` call can be observed while it is still running.

Bound here, because the base commit's usage text or the specification fixes them:

- `then`, a stop's `resume`, `HANDOFF.md`'s next-action section and the status table carry
  the printed commands; a printed command is shell words, the location options as
  `--repo-root DIR`, `--worktree-root DIR`, `--base-ref REF`;
- the progress file's attempts line is `- Attempts: Step <id> count=<n> request=<id>`;
- the follow-up record is `.ai-work/<slug>/FOLLOW_UPS.md`, one item a line, `- [open] <item>`;
- the light review file is `.ai-work/<slug>/LIGHT_REVIEW_step-<id>.md`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tests.acceptance.drivers import step_loop
from tests.acceptance.drivers.step_loop import (
    DEFAULT_WORK,
    MARKER_TEXT,
    STEP_LOOP,
    Envelope,
    LoopTask,
    Step,
    Work,
    assert_well_formed,
    leave_agent_transcript,
    new_agent_id,
    step_block,
    work_on,
)

FOLLOW_UP_RECORD = "FOLLOW_UPS.md"
LOCATION_OPTIONS = ("--repo-root", "--worktree-root", "--base-ref")

# Stop causes the base commit's driver already prints; a new cause is none of these.
EXISTING_STOP_CAUSES = frozenset(
    {
        "loop-state-defect",
        "review-revised-twice",
        "human-verdict",
        "attempts-exhausted",
        "not-driven",
        "blocked-marker",
        "conflict-marker",
    }
)


# -- Calls with the location options a scenario chooses -------------------------------------


def location(task: LoopTask, *names: str) -> list[str]:
    """The location options `names` (among repo-root, worktree-root, base-ref) for `task`."""
    values = {"repo-root": str(task.root), "worktree-root": str(task.root), "base-ref": task.base}
    pairs: list[str] = []
    for name in names:
        pairs += [f"--{name}", values[name]]
    return pairs


def call(task: LoopTask, verb: str, *args: str, options: list[str] | None = None) -> Envelope:
    """`step_loop.py <verb> <slug> <args> <options>` from the checkout's root, one envelope."""
    result = subprocess.run(
        [sys.executable, str(STEP_LOOP), verb, task.slug, *args, *(options or [])],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=900,
        env=task.env,
    )
    return assert_well_formed(verb, result)


def status_table(task: LoopTask, options: list[str]) -> str:
    result = subprocess.run(
        [sys.executable, str(STEP_LOOP), "status", task.slug, *options],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=300,
        env=task.env,
    )
    return result.stdout


def status_json(task: LoopTask) -> dict[str, Any]:
    return step_loop.status(task, as_json=True).json()


def trailing_location(command: str) -> list[tuple[str, str]]:
    """The location-option pairs a printed command ends with, in order."""
    words = shlex.split(command)
    pairs: list[tuple[str, str]] = []
    while len(words) >= 2 and words[-2] in LOCATION_OPTIONS:
        pairs.insert(0, (words[-2], words[-1]))
        words = words[:-2]
    return pairs


def without_location(text: str) -> str:
    """A printed command minus the location options it ends with; any other text unchanged.

    The options echo the caller's own words, so two readers that were called differently
    print the same command up to them.
    """
    try:
        pairs = trailing_location(text)
    except ValueError:  # prose with an unbalanced quote is no command
        return text
    if not pairs:
        return text
    return text[: text.rindex(f" {pairs[0][0]} ")]


def as_pairs(options: list[str]) -> list[tuple[str, str]]:
    return list(zip(options[::2], options[1::2], strict=True))


def printed_commands(text: str) -> list[str]:
    """Each command a text prints: from a `step_loop.py` word to the end of its line or code span."""
    found = []
    for line in text.splitlines():
        for span in re.findall(r"`([^`]*step_loop\.py[^`]*)`", line) or [line]:
            match = re.search(r"(?:python3 \S*|\S*)step_loop\.py\b.*", span)
            if match:
                found.append(match.group(0).strip().rstrip(".;"))
    return found


# -- The plan, amended by a person -------------------------------------------------------------


def insert_step_ahead(task: LoopTask, new: Step, before: str) -> None:
    """A person inserts `new`'s block in the plan directly ahead of step `before`'s block."""
    plan = task.plan_path.read_text(encoding="utf-8")
    anchor = step_block(task.step(before))
    assert anchor in plan, f"step {before}'s block is not in the plan as written"
    task.plan_path.write_text(
        plan.replace(anchor, step_block(new) + "\n" + anchor), encoding="utf-8"
    )
    ordered = []
    for s in task.steps:
        if s.id == before:
            ordered.append(new)
        ordered.append(s)
    task.steps = tuple(ordered)


def attempts_lines(task: LoopTask) -> list[str]:
    return [
        line.strip()
        for line in task.wip_path.read_text(encoding="utf-8").splitlines()
        if "Attempts:" in line
    ]


def requests_named_out(task: LoopTask) -> list[str]:
    """Every request id the progress file names as issued (`request=<id>`)."""
    return [m for line in attempts_lines(task) for m in re.findall(r"request=(\S+)", line)]


# -- Returns whose final message the scenario writes --------------------------------------------


def finish_with(
    task: LoopTask, request: dict[str, Any], final_text: str, work: Work = DEFAULT_WORK
) -> str:
    """The double does `work` for `request`, then its final message is `final_text`."""
    agent_id = work_on(task, request, work)
    leave_agent_transcript(
        task, request, agent_id, requests=work.requests, final_text=final_text, ended=True
    )
    return agent_id


def final_text(body: str, marker: str) -> str:
    return f"{body}\n{MARKER_TEXT[marker]}".strip()


def follow_up_record(task: LoopTask) -> Path:
    return task.task_dir / FOLLOW_UP_RECORD


def follow_up_items(task: LoopTask) -> list[str]:
    path = follow_up_record(task)
    if not path.exists():
        return []
    return [
        line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("- [")
    ]


# -- Light reviews in the shapes a reviewer leaves -------------------------------------------------

ROUND_ONE_FINDINGS = (
    "findings:\n"
    "  - id: F1\n"
    "    severity: FAIL\n"
    "    location: src/step_{step}.py:1\n"
    "    evidence: the module returns a constant instead of deriving the value.\n"
    "    criterion: the step's Done when clause.\n"
)


def second_round_file(step_id: str, verdict: str) -> str:
    """A round-2 review file: its own verdict first, then the superseded round-1 record."""
    findings = ROUND_ONE_FINDINGS.replace("{step}", step_id)
    own = "notes: the revision derives the value.\n" if verdict == "accept" else findings
    return (
        f"verdict: {verdict}\n"
        f"step: {step_id} · round 2\n"
        f"{own}\n"
        "---\n\n"
        "## Superseded round-1 record\n\n"
        "verdict: revise\n"
        f"{findings}"
    )


def partial_first_file(step_id: str, verdict: str) -> str:
    """A single-round file as the review prompt asks: `[PARTIAL]` first, findings, verdict last."""
    findings = (
        ROUND_ONE_FINDINGS.replace("{step}", step_id) if verdict == "revise" else "findings: []\n"
    )
    return f"verdict: [PARTIAL]\n{findings}verdict: {verdict}\n"


def answer_review(
    task: LoopTask, request: dict[str, Any], file_text: str, final_verdict: str
) -> Envelope:
    """A light reviewer leaves `file_text` and ends on `verdict: <final_verdict>` [COMPLETE]."""
    step_id = str(request["step"])
    (task.task_dir / f"LIGHT_REVIEW_step-{step_id}.md").write_text(file_text, encoding="utf-8")
    agent_id = new_agent_id()
    leave_agent_transcript(
        task,
        request,
        agent_id,
        requests=step_loop.REVIEW_TURNS,
        final_text=f"verdict: {final_verdict}\n[COMPLETE]",
        ended=True,
    )
    return step_loop.record(task, request["id"], agent_id=agent_id, marker="complete")


def next_request(task: LoopTask) -> dict[str, Any]:
    asked = step_loop.next_action(task)
    assert asked.request is not None, f"expected a request, got: {asked.doc}"
    return asked.request


def to_second_review(task: LoopTask) -> dict[str, Any]:
    """Drive a review-marked step 1 through its attempt, a round-1 revise and the revision,
    up to the round-2 review request; return that request."""
    step_loop.attempt(task, Work())
    first = next_request(task)
    assert first["kind"] == "review", first
    step_loop.record(
        task,
        first["id"],
        agent_id=step_loop.leave_review_verdict(task, first, "revise"),
        marker="complete",
    )
    revision = next_request(task)
    step_loop.record(
        task, revision["id"], agent_id=work_on(task, revision, Work()), marker="complete"
    )
    second = next_request(task)
    assert second["kind"] == "review", second
    return second


# -- What a rendered prompt says beyond the plan block ------------------------------------------


def prompt_text(request: dict[str, Any]) -> str:
    return Path(request["prompt_path"]).read_text(encoding="utf-8")


def outside_step_block(prompt: str) -> str:
    """The prompt with its `<step ...>...</step>` element (the plan block, verbatim) cut away."""
    return re.sub(r"<step\b[^>]*>.*?</step>", "", prompt, flags=re.DOTALL)


NEGATION = re.compile(r"\b(not|never|no|don't|do not|must not|cannot)\b", re.IGNORECASE)


def lines_granting_edit(text: str, path: str) -> list[str]:
    """Lines (sentences) naming `path` that say it may be edited, with no negation in them."""
    pieces = re.split(r"(?<=[.;])\s+|\n", text)
    return [
        p
        for p in pieces
        if path in p and re.search(r"\bedit", p, re.IGNORECASE) and not NEGATION.search(p)
    ]


# -- A record call observed while it runs --------------------------------------------------------


def holding_test(log: Path, releases: Path) -> str:
    """A unit test that logs each run of itself and waits until that run is released.

    Run n appends a line to `log` and waits for `releases/<n>`; whatever runs the step's
    unit test (the Check, the gate's scope) is therefore held at a point the scenario sees.
    """
    return (
        "import time\nfrom pathlib import Path\n\n"
        "from src.step_1 import value\n\n"
        f"LOG = Path({str(log)!r})\nRELEASES = Path({str(releases)!r})\n\n\n"
        "def test_value_is_the_step_id():\n"
        "    LOG.parent.mkdir(parents=True, exist_ok=True)\n"
        "    with LOG.open('a') as out:\n        out.write('run\\n')\n"
        "    n = len(LOG.read_text().splitlines())\n"
        "    stop_at = time.monotonic() + 240\n"
        "    while not (RELEASES / str(n)).exists() and time.monotonic() < stop_at:\n"
        "        time.sleep(0.1)\n"
        "    assert value() == '1'\n"
    )


@dataclass(frozen=True)
class HeldRecord:
    log: Path
    releases: Path


def held_work(task: LoopTask) -> tuple[Work, HeldRecord]:
    """The double's work for step 1, whose unit test is held at each run."""
    held = HeldRecord(
        log=task.root.parent / "held" / "runs.log", releases=task.root.parent / "held"
    )
    held.releases.mkdir(parents=True, exist_ok=True)
    work = Work(other_edits=(("tests/test_step_1.py", holding_test(held.log, held.releases)),))
    return work, held


def start_record(
    task: LoopTask, request_id: str, agent_id: str, marker: str = "complete"
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            str(STEP_LOOP),
            "record",
            task.slug,
            "--request",
            request_id,
            "--agent-id",
            agent_id,
            "--marker",
            marker,
            *location(task, "repo-root", "base-ref"),
        ],
        cwd=task.root,
        env=task.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def runs_seen(held: HeldRecord) -> int:
    return len(held.log.read_text().splitlines()) if held.log.exists() else 0


def wait_for_run(
    held: HeldRecord, n: int, process: subprocess.Popen[str], deadline: float = 240
) -> bool:
    """Wait until run `n` of the held test has started; False when `process` ended first."""
    stop_at = time.monotonic() + deadline
    while time.monotonic() < stop_at:
        if runs_seen(held) >= n:
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.1)
    raise AssertionError(f"run {n} of the held test did not start in {deadline} s")


def release(held: HeldRecord, n: int) -> None:
    (held.releases / str(n)).touch()


def release_all(held: HeldRecord, upto: int = 20) -> None:
    for n in range(1, upto + 1):
        release(held, n)


def at_each_held_run(
    held: HeldRecord, process: subprocess.Popen[str], visit: Callable[[int], Any], limit: int = 6
) -> list[Any]:
    """Call `visit(n)` while run n of the held test waits, then release it; until `process` ends."""
    seen = []
    for n in range(1, limit + 1):
        if not wait_for_run(held, n, process):
            break
        seen.append(visit(n))
        release(held, n)
    process.wait(timeout=600)
    return seen


def envelope_of(process: subprocess.Popen[str]) -> Envelope:
    stdout, stderr = process.communicate(timeout=600)
    done = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    return assert_well_formed("record", done)


# -- A plan field written by hand ---------------------------------------------------------------


def set_check(task: LoopTask, step_id: str, command: str, expects: str) -> None:
    """Replace step `step_id`'s Check line with `command` and its expectation."""
    old = task.step(step_id)
    plan = task.plan_path.read_text(encoding="utf-8")
    line = f"**Check**: `{old.check_command}` expects pass=1 fail=0 skip=0"
    assert line in plan, plan
    task.plan_path.write_text(
        plan.replace(line, f"**Check**: `{command}` expects {expects}"), encoding="utf-8"
    )


def with_annotation(step: Step, line: str) -> Step:
    return replace(step, annotations=(*step.annotations, line))


def env_without(names: tuple[str, ...]) -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in names}


def dump(value: Any) -> str:
    return json.dumps(value, indent=1, default=str)
