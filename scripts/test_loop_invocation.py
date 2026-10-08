"""Tests for the one renderer of the commands the step-loop command prints, and for the two
keywords ``drive`` takes (``scripts/_step_loop_render.py``, ``scripts/_step_loop_cli.py``,
``scripts/step_loop.py``).

The renderer cases are pure. The ``drive`` and ``execute`` cases run the real command over a
small checkout built in ``tmp_path``, as the other loop suites do.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import step_loop  # noqa: E402
from _step_loop_render import Invocation, StopView, stop_next_action, stop_stderr  # noqa: E402

STEP = "Step "
SLUG = "demo"
SCRIPT = SCRIPT_DIR / "step_loop.py"
PROGRAM = "python3 scripts/step_loop.py"
LOCATION = ("--repo-root", "/work/repo", "--base-ref", "main")
LOCATION_TEXT = "--repo-root /work/repo --base-ref main"
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
STUCK_DEPENDENCY = " [depends-on: 9]"


def plan(heading=""):
    block = f"### {STEP}1: Do it{heading}\n\n**Assignee**: implementer\n**Files**: `src/one.py`\n"
    return f"# Plan\n\n## Steps\n\n{block}{CHECK}\n"


WIP = f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n"


@pytest.fixture(autouse=True)
def started_by_path_to_the_script(monkeypatch):
    """The command is run by explicit path, so its directory is not a `PATH` entry."""
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])


def build(tmp_path, plan_text):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(plan_text, encoding="utf-8")
    (task / "WIP.md").write_text(WIP, encoding="utf-8")
    identity = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", *identity, "commit", "-q", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True
    )
    return tmp_path


def where(root):
    return ["--repo-root", str(root), "--base-ref", "HEAD"]


class NeverStarts:
    """A spawner whose agent call always fails before an agent starts."""

    def __init__(self):
        self.requests = []

    def spawn(self, request):
        self.requests.append(request)
        return step_loop.NotStarted("the call failed")


class Observed:
    """What `observe` was told, in call order."""

    def __init__(self):
        self.calls = []

    def __call__(self, request, returned, doc):
        self.calls.append((request, returned, doc))


# --- The renderer ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verb", "rest", "expected"),
    [
        ("next", (), f"{PROGRAM} next {SLUG}"),
        ("status", (), f"{PROGRAM} status {SLUG}"),
        (
            "record",
            ("--request", "s1-a1-implement"),
            f"{PROGRAM} record {SLUG} --request s1-a1-implement",
        ),
    ],
    ids=["next", "status", "record-with-its-request"],
)
def test_a_command_without_a_location_is_the_program_the_verb_and_the_slug(verb, rest, expected):
    assert Invocation(PROGRAM).command(verb, SLUG, *rest) == expected


@pytest.mark.parametrize(
    ("verb", "rest", "expected"),
    [
        ("next", (), f"{PROGRAM} next {SLUG} {LOCATION_TEXT}"),
        ("status", (), f"{PROGRAM} status {SLUG} {LOCATION_TEXT}"),
        ("record", ("--request", "r1"), f"{PROGRAM} record {SLUG} --request r1 {LOCATION_TEXT}"),
    ],
    ids=["next", "status", "record-with-its-request"],
)
def test_a_command_ends_with_the_location_after_the_rest(verb, rest, expected):
    assert Invocation(PROGRAM, LOCATION).command(verb, SLUG, *rest) == expected


def test_an_option_value_with_a_space_is_quoted_so_the_command_can_be_pasted():
    invocation = Invocation(PROGRAM, ("--repo-root", "/work/my repo"))

    assert invocation.command("next", SLUG).endswith("--repo-root '/work/my repo'")


def test_a_plain_program_string_stands_for_an_invocation_with_no_location():
    assert Invocation.of(PROGRAM) == Invocation(PROGRAM, ())


def test_an_invocation_passed_to_the_coercion_is_returned_unchanged():
    invocation = Invocation(PROGRAM, LOCATION)

    assert Invocation.of(invocation) is invocation


def stop_view(invoke):
    return StopView("dependency-defect", "1", "the evidence", (), SLUG, invoke)


def test_a_stop_block_and_a_handoff_paragraph_carry_the_location_the_invocation_holds():
    view = stop_view(Invocation(PROGRAM, LOCATION))

    assert f"then run: {PROGRAM} next {SLUG} {LOCATION_TEXT}\n" in stop_stderr(view) + "\n"
    assert f"(it runs `{PROGRAM} next {SLUG} {LOCATION_TEXT}`)" in stop_next_action(view)


def test_a_stop_view_given_a_plain_string_prints_what_it_always_printed():
    view = stop_view(PROGRAM)

    assert f"then run: {PROGRAM} next {SLUG}\n" in stop_stderr(view) + "\n"
    assert f"(it runs `{PROGRAM} next {SLUG}`)" in stop_next_action(view)


# --- drive ----------------------------------------------------------------------------------


def test_drive_by_default_prints_a_then_that_ends_at_the_request_id_and_its_placeholders(tmp_path):
    root = build(tmp_path, plan())
    observed = Observed()

    step_loop.drive(NeverStarts(), SLUG, where(root), observe=observed)

    ((_, _, doc),) = observed.calls
    assert doc["then"].startswith(f"{PROGRAM} record {SLUG} --request s1-a1-implement --agent-id")
    assert "--repo-root" not in doc["then"]


def test_drive_with_echo_ends_a_spawns_then_with_the_location(tmp_path):
    root = build(tmp_path, plan())
    observed = Observed()

    step_loop.drive(NeverStarts(), SLUG, where(root), echo=True, observe=observed)

    ((_, _, doc),) = observed.calls
    assert doc["then"].endswith(" ".join(where(root)))


def test_drive_by_default_returns_a_stops_resume_without_the_location(tmp_path):
    root = build(tmp_path, plan(STUCK_DEPENDENCY))

    final = step_loop.drive(NeverStarts(), SLUG, where(root))

    assert final["stop"]["resume"] == f"{PROGRAM} next {SLUG}"


def test_drive_with_echo_returns_a_stops_resume_with_the_location(tmp_path):
    root = build(tmp_path, plan(STUCK_DEPENDENCY))

    final = step_loop.drive(NeverStarts(), SLUG, where(root), echo=True)

    assert final["stop"]["resume"] == f"{PROGRAM} next {SLUG} {' '.join(where(root))}"


def test_drive_with_echo_writes_the_location_into_the_handoffs_next_action(tmp_path):
    root = build(tmp_path, plan(STUCK_DEPENDENCY))

    step_loop.drive(NeverStarts(), SLUG, where(root), echo=True)

    handoff = (root / ".ai-work" / SLUG / "HANDOFF.md").read_text(encoding="utf-8")
    assert f"{PROGRAM} next {SLUG} {' '.join(where(root))}`" in handoff


def test_drive_calls_observe_once_after_each_record_with_the_request_the_return_and_the_envelope(
    tmp_path,
):
    root = build(tmp_path, plan())
    spawner, observed = NeverStarts(), Observed()

    step_loop.drive(spawner, SLUG, where(root), observe=observed)

    ((request, returned, doc),) = observed.calls
    assert (request, returned) == (spawner.requests[0], step_loop.NotStarted("the call failed"))
    assert doc["recorded"]["stop_reason"] == "not-started"


def test_drive_given_no_observer_still_returns_the_final_envelope(tmp_path):
    root = build(tmp_path, plan())

    final = step_loop.drive(NeverStarts(), SLUG, where(root))

    assert final["recorded"]["stop_reason"] == "not-started"


# --- The status table -----------------------------------------------------------------------


def test_the_status_table_names_the_next_command_with_the_echoed_location(tmp_path):
    root = build(tmp_path, plan())

    shown = step_loop.execute(["status", SLUG, *where(root)], echo=where(root)).table

    assert f"run `{PROGRAM} next {SLUG} {' '.join(where(root))}` to start s1-a1-implement" in shown


def test_the_status_table_without_an_echo_names_the_bare_next_command(tmp_path):
    root = build(tmp_path, plan())

    shown = step_loop.execute(["status", SLUG, *where(root)]).table

    assert f"run `{PROGRAM} next {SLUG}` to start s1-a1-implement" in shown
