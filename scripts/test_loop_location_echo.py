"""Tests for the location options a call echoes into every command it prints
(``location_echo`` in ``scripts/_step_loop_cli.py``, ``main`` in ``scripts/step_loop.py``).

``location_echo`` is pure: a call's own words in, the options to repeat out. The ``main`` and
``execute`` cases run the real command over a small checkout built in ``tmp_path``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_files as files  # noqa: E402
import step_loop  # noqa: E402
from _step_loop_cli import location_echo, same_next_action  # noqa: E402
from compose_handoff import SECTION_HEADINGS  # noqa: E402

STEP = "Step "
SLUG = "demo"
SCRIPT = SCRIPT_DIR / "step_loop.py"
PROGRAM = "python3 scripts/step_loop.py"
PLAN = (
    f"# Plan\n\n## Steps\n\n### {STEP}1: Do it\n\n**Assignee**: implementer\n"
    "**Files**: `src/one.py`\n**Check**: `python3 -m pytest -q` expects pass>=1 fail=0\n"
)
WIP = f"# WIP\n\n## Progress\n\n- [ ] {STEP}1: Do it\n"


@pytest.fixture(autouse=True)
def started_by_path_to_the_script(monkeypatch):
    """The command is run by explicit path, so its directory is not a `PATH` entry."""
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])


def build(tmp_path):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    (task / "IMPLEMENTATION_PLAN.md").write_text(PLAN, encoding="utf-8")
    (task / "WIP.md").write_text(WIP, encoding="utf-8")
    identity = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", *identity, "commit", "-q", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True
    )
    return tmp_path


# --- location_echo --------------------------------------------------------------------------


def test_a_call_with_no_location_option_echoes_nothing():
    assert location_echo(["next", SLUG]) == ()


def test_the_separate_spelling_is_echoed_as_the_option_and_its_value():
    assert location_echo(["next", SLUG, "--base-ref", "abc123"]) == ("--base-ref", "abc123")


def test_the_equals_spelling_is_echoed_as_the_option_and_its_value():
    assert location_echo(["next", SLUG, "--base-ref=abc123"]) == ("--base-ref", "abc123")


def test_the_options_keep_the_order_and_the_values_the_caller_gave():
    argv = ["next", SLUG, "--base-ref", "main", "--worktree-root=/w", "--repo-root", "/r"]

    assert location_echo(argv) == (
        "--base-ref",
        "main",
        "--worktree-root",
        "/w",
        "--repo-root",
        "/r",
    )


def test_an_option_that_is_not_a_location_is_left_out():
    argv = ["record", SLUG, "--request", "r1", "--agent-id", "a1", "--marker", "complete"]

    assert location_echo(argv) == ()


def test_a_location_option_among_other_options_is_found():
    argv = ["record", SLUG, "--request", "r1", "--base-ref", "main", "--marker", "none"]

    assert location_echo(argv) == ("--base-ref", "main")


def test_an_option_with_no_value_after_it_echoes_nothing():
    assert location_echo(["next", SLUG, "--base-ref"]) == ()


# --- execute and main -----------------------------------------------------------------------


def test_execute_called_directly_prints_the_bare_commands(tmp_path):
    root = build(tmp_path)

    asked = step_loop.execute(["next", SLUG, "--repo-root", str(root), "--base-ref", "HEAD"])

    assert asked.doc["then"].startswith(f"{PROGRAM} record {SLUG} --request ")
    assert "--base-ref" not in asked.doc["then"]


def test_main_prints_a_then_ending_with_the_options_the_call_was_given(tmp_path, capsys):
    root = build(tmp_path)
    given = ["--repo-root", str(root), "--base-ref", "HEAD"]

    step_loop.main(["next", SLUG, *given])

    then = json.loads(capsys.readouterr().out)["then"]
    assert then.endswith(" ".join(given))


def test_main_prints_a_then_with_no_location_for_a_call_given_none(tmp_path, capsys, monkeypatch):
    root = build(tmp_path)
    monkeypatch.chdir(root)

    step_loop.main(["next", SLUG])

    then = json.loads(capsys.readouterr().out)["then"]
    assert "--base-ref" not in then
    assert "--repo-root" not in then


# --- same_next_action and the handoff ---------------------------------------------------------

RESUME = f"{PROGRAM} next {SLUG}"
BASE = "--base-ref abc123"


def test_sections_differing_only_by_options_are_one_action_whichever_side_has_them():
    bare, based = RESUME, f"{RESUME} {BASE}"

    assert (same_next_action(bare, based), same_next_action(based, bare)) == (True, True)


def test_options_in_any_spelling_and_quoting_are_set_aside_when_comparing():
    held = f"run {RESUME} --repo-root '/a b'\nthen {RESUME} --worktree-root=/w"

    assert same_next_action(held, f"run {RESUME}\nthen {RESUME}")


def test_an_option_inside_a_sentence_is_set_aside_without_its_punctuation():
    held = f"(it runs `{RESUME}`)"

    assert same_next_action(held, f"(it runs `{RESUME} {BASE}`)")


def test_sections_carrying_different_options_are_not_one_action():
    assert not same_next_action(f"{RESUME} --repo-root /r {BASE}", f"{RESUME} {BASE}")


def test_sections_naming_different_commands_are_not_one_action():
    assert not same_next_action(RESUME, f"{PROGRAM} record {SLUG}")


def test_a_section_is_never_one_action_with_a_missing_one():
    assert not same_next_action(RESUME, None)


def handoff_text(next_action):
    sections = [f"## {heading}\n\nbody\n" for heading in SECTION_HEADINGS]
    sections[2] = f"## {SECTION_HEADINGS[2]}\n\n{next_action}\n"
    return "# Handoff\n\n" + "\n".join(sections)


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    """A stub composer that writes the next action it is given; the path of the file it targets."""
    path = tmp_path / "HANDOFF.md"

    def stub(slug, repo_root, **kwargs):
        return {"text": handoff_text(kwargs["next_action"]), "path": path}

    monkeypatch.setattr(files, "write_handoff", stub)
    return path


def write_stop(tmp_path, next_action):
    return files.write_stop_handoff(SLUG, tmp_path, next_action, same_action=same_next_action)


def test_a_handoff_differing_only_by_the_options_the_call_added_is_left_as_it_is(tmp_path, handoff):
    write_stop(tmp_path, f"{RESUME}")

    wrote = write_stop(tmp_path, f"{RESUME} {BASE}")

    assert (wrote, handoff.read_text()) == (False, handoff_text(RESUME))


def test_a_handoff_differing_only_by_the_options_the_call_left_out_is_left_as_it_is(
    tmp_path, handoff
):
    write_stop(tmp_path, f"{RESUME} {BASE}")

    wrote = write_stop(tmp_path, f"{RESUME}")

    assert (wrote, handoff.read_text()) == (False, handoff_text(f"{RESUME} {BASE}"))


def test_a_handoff_whose_options_the_call_changed_is_rewritten_with_the_options_of_the_call(
    tmp_path, handoff
):
    write_stop(tmp_path, f"{RESUME} --repo-root /r {BASE}")

    wrote = write_stop(tmp_path, f"{RESUME} {BASE}")

    assert (wrote, handoff.read_text()) == (True, handoff_text(f"{RESUME} {BASE}"))


def test_a_handoff_whose_next_action_moved_is_rewritten_with_the_options_of_the_call(
    tmp_path, handoff
):
    write_stop(tmp_path, f"{RESUME}")

    wrote = write_stop(tmp_path, f"{PROGRAM} record {SLUG} {BASE}")

    assert (wrote, handoff.read_text()) == (True, handoff_text(f"{PROGRAM} record {SLUG} {BASE}"))


def test_a_first_handoff_is_written_with_the_options_of_the_call(tmp_path, handoff):
    wrote = write_stop(tmp_path, f"{RESUME} {BASE}")

    assert (wrote, handoff.read_text()) == (True, handoff_text(f"{RESUME} {BASE}"))
