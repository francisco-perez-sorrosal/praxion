"""Tests for the edges of ``hooks/_skill_delivery.py`` that its first reviews left open.

A step-loop pointer survives trailing whitespace, the failure report keeps its promises (never
raises, one stderr line per failure, a cause only where it means something), a fenced block reads as
an arrival on purpose, and the emitter's own tests leave this checkout's observation log alone.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402
import test_inject_subagent_context as emitter_tests  # noqa: E402
from _observation_log import reader  # noqa: E402
from _observation_log.location import locate  # noqa: E402
from _skill_delivery import Failed, Marked, Served, StepRequest, Unmarked  # noqa: E402

ROLE = "praxion:implementer"
SLUG = "demo"
REQUEST_ID = "s7-a2-implement"
REQUEST_PATH = Path("/work") / ".ai-work" / SLUG / f"PROMPT_{REQUEST_ID}.md"
MARKED_REQUEST = '<step id="4">\n### [Phase: Refactoring] Move the parser\n</step>\n'
STANDARD_MODE = {"PRAXION_OBSERVATION_LOG": "standard"}
SKILL_TEXT = "---\nname: refactoring\ndescription: x\n---\n\n# Pragmatic Refactoring\n"
MARKED_PROMPT = "### [Phase: Refactoring] Move the parser\n"


def pointer(slug_end: str = "", request_end: str = "") -> str:
    return (
        f"Task slug: {SLUG}{slug_end}\n"
        f"Spawn request: {REQUEST_ID}{request_end}\n"
        f"Read {REQUEST_PATH} first and follow it.\n"
    )


def classify_pointer(prompt: str, request: str = MARKED_REQUEST):
    return delivery.classify(ROLE, prompt, lambda _path: request)


# --- a pointer line may end in whitespace ---------------------------------------------------------


@pytest.mark.parametrize("trailing", [" ", "  ", "\t", "\r"], ids=["space", "spaces", "tab", "cr"])
def test_a_task_slug_line_with_trailing_whitespace_still_points(trailing):
    assert classify_pointer(pointer(slug_end=trailing)) == Marked(StepRequest(REQUEST_ID))


@pytest.mark.parametrize("trailing", [" ", "\t", "\r"], ids=["space", "tab", "cr"])
def test_a_spawn_request_line_with_trailing_whitespace_still_points(trailing):
    assert classify_pointer(pointer(request_end=trailing)) == Marked(StepRequest(REQUEST_ID))


@pytest.mark.parametrize("trailing", [" ", "\t", "\r"], ids=["space", "tab", "cr"])
def test_a_step_opening_with_trailing_whitespace_still_opens_the_step(trailing):
    request = MARKED_REQUEST.replace('<step id="4">', f'<step id="4">{trailing}')

    assert classify_pointer(pointer(), request) == Marked(StepRequest(REQUEST_ID))


def test_trailing_text_on_a_pointer_line_is_still_no_pointer():
    assert classify_pointer(pointer(slug_end=" and more")) == Unmarked()


# --- the failure report keeps its promises --------------------------------------------------------


class _RaisingStderr:
    def write(self, _text):
        raise RuntimeError("stderr is gone")

    def flush(self):
        raise RuntimeError("stderr is gone")


def make_installation(root: Path) -> Path:
    plugin = root / "plugin"
    (plugin / "agents").mkdir(parents=True)
    (plugin / "agents" / "implementer.md").write_text(
        "---\nname: implementer\nskills: [software-planning]\n---\n\nBody.\n", encoding="utf-8"
    )
    skill = plugin / "skills" / "refactoring"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")
    (skill / "references" / "patterns.md").write_text("patterns\n", encoding="utf-8")
    return plugin


@pytest.fixture
def plugin(tmp_path):
    return make_installation(tmp_path)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / ".ai-state").mkdir(parents=True)
    (root / ".git").mkdir()
    return root


def spawn_payload(project: Path) -> dict:
    return {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": ROLE, "prompt": MARKED_PROMPT},
        "cwd": str(project),
        "session_id": "s1",
        "tool_use_id": "toolu_01",
    }


def refuse_the_row(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("_observation_log.writer.record", refuse)


def test_a_stderr_that_raises_any_error_never_stops_the_delivery(plugin, project, monkeypatch):
    (plugin / "skills" / "refactoring" / "SKILL.md").unlink()
    monkeypatch.setattr(sys, "stderr", _RaisingStderr())

    outcome = delivery.deliver(spawn_payload(project), plugin, STANDARD_MODE)

    assert outcome == Failed("skill-unreadable")


def test_a_failure_whose_row_is_also_lost_prints_one_stderr_line(
    plugin, project, monkeypatch, capsys
):
    (plugin / "skills" / "refactoring" / "SKILL.md").unlink()
    refuse_the_row(monkeypatch)

    delivery.deliver(spawn_payload(project), plugin, STANDARD_MODE)

    (line,) = capsys.readouterr().err.splitlines()
    assert "(skill-unreadable)" in line
    assert "row not recorded: refactoring (OSError)" in line


def test_a_served_spawn_whose_row_is_lost_prints_only_the_lost_row(
    plugin, project, monkeypatch, capsys
):
    refuse_the_row(monkeypatch)

    assert isinstance(delivery.deliver(spawn_payload(project), plugin, STANDARD_MODE), Served)

    assert capsys.readouterr().err == ("skill delivery row not recorded: refactoring (OSError)\n")


def test_a_cause_is_refused_for_a_reason_it_means_nothing_to():
    with pytest.raises(ValueError, match="skill-unreadable"):
        Failed("skill-unreadable", "OSError")


def test_an_internal_error_carries_its_cause_without_changing_its_identity():
    assert Failed("internal-error", "OSError") == Failed("internal-error")


# --- a block pasted inside a fence is an arrival, on purpose --------------------------------------


def test_a_labelled_block_inside_a_fence_at_a_line_start_reads_as_an_arrival():
    """Kept on purpose: a delivered body is full of fences, so fences are not set aside.

    A matcher that skipped fenced text would miss a block whose body holds a fence of its own, and
    a relayed block inside a fence is still the delivered text arriving, which is what is asked.
    """
    block = delivery.render_block("\n# Refactoring\n\n```python\nprint(1)\n```\n", Path("/skill"))
    record = f"Report from the spawn:\n```\n{block}\n```\n"

    assert delivery.shows_arrival(record)


# --- the emitter's tests leave this checkout's log alone ------------------------------------------


def delivery_rows_of_this_checkout() -> list[dict]:
    location = locate(os.getcwd())
    if location is None:
        return []
    rows = reader.read_rows(location.state_dir)
    return [row for row in rows if row.get("event_type") == "skill_delivery"]


@pytest.mark.parametrize(
    "stdin", ["", "not valid json {{{"], ids=["empty-input", "malformed-input"]
)
def test_the_emitter_helper_runs_the_hook_without_logging_at_this_checkout(stdin, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN_ROOT))
    before = delivery_rows_of_this_checkout()

    result = emitter_tests._run_hook(None, raw_stdin=stdin)

    assert result.returncode == 0
    assert delivery_rows_of_this_checkout() == before
