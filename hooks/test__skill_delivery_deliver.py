"""Tests for the decision and the edge of ``hooks/_skill_delivery.py``.

The decision table is total over every verdict and preload state. The edge performs every read,
never raises, and leaves exactly one row for a served or failed spawn and none for a skip.
"""

from __future__ import annotations

import itertools
import os
import sys
import typing
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

import _skill_delivery as delivery  # noqa: E402
from _observation_log import reader  # noqa: E402
from _skill_delivery import (  # noqa: E402
    DefinitionUnreadable,
    Failed,
    Marked,
    NotPreloaded,
    NotServed,
    OwnWords,
    Preloaded,
    Served,
    Skipped,
    StepRequest,
    Unmarked,
    Unresolvable,
)

ROLE = "praxion:implementer"
MARKER = "[Phase: Refactoring]"
MARKED_PROMPT = f"### {MARKER} Move the parser\n"
SKILL_TEXT = "---\nname: refactoring\ndescription: x\n---\n\n# Pragmatic Refactoring\n"
BODY = "\n# Pragmatic Refactoring\n"
STANDARD_MODE = {"PRAXION_OBSERVATION_LOG": "standard"}
SLUG = "feature"
REQUEST_ID = "s4-a1-implement"

SKILL_DIR = Path("/plugins/praxion/skills/refactoring")
VERDICTS = [
    NotServed("praxion:verifier"),
    Unmarked(),
    Marked(OwnWords()),
    Marked(StepRequest(REQUEST_ID)),
    Unresolvable("grammar-unavailable"),
    Unresolvable("request-path-refused"),
    Unresolvable("request-unreadable"),
    Unresolvable("request-without-step"),
]
PRELOADS = [Preloaded(), NotPreloaded(), DefinitionUnreadable("definition-unreadable")]


# --- the decision table ------------------------------------------------------------------------


@pytest.fixture
def skill_dir(tmp_path):
    directory = tmp_path / "plugin" / "skills" / "refactoring"
    (directory / "references").mkdir(parents=True)
    (directory / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")
    (directory / "references" / "patterns.md").write_text("patterns\n", encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("verdict", "preload", "expected"),
    [
        (NotServed("praxion:verifier"), Preloaded(), Skipped("not-served")),
        (NotServed("praxion:verifier"), NotPreloaded(), Skipped("not-served")),
        (Unmarked(), NotPreloaded(), Skipped("unmarked")),
        (Unmarked(), DefinitionUnreadable("frontmatter-missing"), Skipped("unmarked")),
        (Marked(OwnWords()), Preloaded(), Skipped("preloaded")),
        (Marked(StepRequest(REQUEST_ID)), Preloaded(), Skipped("preloaded")),
        (
            Marked(OwnWords()),
            DefinitionUnreadable("skills-unparseable"),
            Failed("definition-unreadable"),
        ),
        (Unresolvable("request-unreadable"), NotPreloaded(), Failed("request-unresolvable")),
        (Unresolvable("request-without-step"), NotPreloaded(), Failed("request-unresolvable")),
        (Unresolvable("request-path-refused"), NotPreloaded(), Failed("request-unresolvable")),
        (Unresolvable("grammar-unavailable"), NotPreloaded(), Failed("grammar-unavailable")),
        (
            Unresolvable("request-unreadable"),
            DefinitionUnreadable("definition-unreadable"),
            Failed("request-unresolvable"),
        ),
        (Unresolvable("grammar-unavailable"), Preloaded(), Skipped("preloaded")),
    ],
)
def test_a_cell_that_reads_no_body_decides_without_one(verdict, preload, expected):
    assert delivery.decide(verdict, preload, SKILL_DIR) == expected


@pytest.mark.parametrize("route", [OwnWords(), StepRequest(REQUEST_ID)], ids=["own", "request"])
def test_a_marked_delegation_to_a_definition_without_the_preload_is_served_the_body(
    route, skill_dir
):
    outcome = delivery.decide(Marked(route), NotPreloaded(), skill_dir)

    assert outcome == Served(
        delivery.render_block(BODY, skill_dir), delivery.body_digest(BODY), route
    )


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        (lambda skill: (skill / "SKILL.md").unlink(), "skill-unreadable"),
        (lambda skill: (skill / "references" / "patterns.md").unlink(), "skill-unreadable"),
    ],
    ids=["no-skill-file", "no-reference-file"],
)
def test_a_marked_delegation_whose_body_cannot_be_read_fails(damage, reason, skill_dir):
    damage(skill_dir)

    assert delivery.decide(Marked(OwnWords()), NotPreloaded(), skill_dir) == Failed(reason)


def test_a_body_that_times_out_is_a_failure_of_its_own(skill_dir, monkeypatch):
    monkeypatch.setattr(
        delivery, "read_body", lambda _: delivery.BodyUnreadable("skill-read-timeout")
    )

    assert delivery.decide(Marked(OwnWords()), NotPreloaded(), skill_dir) == Failed(
        "skill-read-timeout"
    )


def test_every_verdict_and_preload_state_the_module_defines_is_decided(skill_dir):
    verdict_kinds = set(typing.get_args(delivery.Verdict))
    preload_kinds = set(typing.get_args(delivery.PreloadState))
    assert {type(verdict) for verdict in VERDICTS} == verdict_kinds
    assert {type(preload) for preload in PRELOADS} == preload_kinds

    for verdict, preload in itertools.product(VERDICTS, PRELOADS):
        assert isinstance(delivery.decide(verdict, preload, skill_dir), (Skipped, Served, Failed))


# --- the edge: a fake installation and a project the log serves --------------------------------


def make_installation(tmp_path, skills_line="skills: [software-planning]\n"):
    root = tmp_path / "plugin"
    (root / "agents").mkdir(parents=True)
    for role in ("implementer", "test-engineer"):
        (root / "agents" / f"{role}.md").write_text(
            f"---\nname: {role}\n{skills_line}model: sonnet\n---\n\nBody.\n", encoding="utf-8"
        )
    skill = root / "skills" / "refactoring"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")
    (skill / "references" / "patterns.md").write_text("patterns\n", encoding="utf-8")
    return root


@pytest.fixture
def plugin(tmp_path):
    return make_installation(tmp_path)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / ".ai-state").mkdir(parents=True)
    (root / ".git").mkdir()
    return root


def spawn_payload(project, prompt=MARKED_PROMPT, agent_type=ROLE, tool_use_id="toolu_01"):
    return {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": agent_type, "prompt": prompt},
        "cwd": str(project),
        "session_id": "s1",
        "tool_use_id": tool_use_id,
    }


def rows_of(project):
    return reader.read_rows(project / ".ai-state")


def deliver(payload, plugin):
    return delivery.deliver(payload, plugin, STANDARD_MODE)


def test_a_marked_spawn_is_served_and_leaves_one_row(plugin, project):
    outcome = deliver(spawn_payload(project), plugin)

    assert isinstance(outcome, Served)
    assert outcome.route == OwnWords()
    assert delivery.shows_arrival(outcome.block, BODY)
    (row,) = rows_of(project)
    assert row == {
        "timestamp": row["timestamp"],
        "session_id": "s1",
        "event_type": "skill_delivery",
        "agent_type": ROLE,
        "skill": "refactoring",
        "tool_use_id": "toolu_01",
        "outcome": "served",
        "route": "own-words",
        "body_digest": delivery.body_digest(BODY),
        "log_mode": "standard",
    }


def test_the_same_spawn_call_repeated_carries_one_dedup_key(plugin, project):
    deliver(spawn_payload(project), plugin)
    deliver(spawn_payload(project), plugin)

    first, second = rows_of(project)
    assert (first["tool_use_id"], first["event_type"]) == (
        second["tool_use_id"],
        second["event_type"],
    )


@pytest.mark.parametrize(
    ("prompt", "agent_type", "why"),
    [
        (MARKED_PROMPT, "praxion:verifier", "not-served"),
        ("### Move the parser\n", ROLE, "unmarked"),
    ],
    ids=["other-role", "unmarked"],
)
def test_a_spawn_with_nothing_to_deliver_is_skipped_without_a_row(
    prompt, agent_type, why, plugin, project, capsys
):
    outcome = deliver(spawn_payload(project, prompt, agent_type), plugin)

    assert outcome == Skipped(why)
    assert rows_of(project) == []
    assert capsys.readouterr().err == ""


def test_a_definition_that_preloads_the_skill_is_skipped_without_a_row(tmp_path, project, capsys):
    plugin = make_installation(tmp_path, "skills: [refactoring]\n")

    assert deliver(spawn_payload(project), plugin) == Skipped("preloaded")
    assert rows_of(project) == []
    assert capsys.readouterr().err == ""


def test_a_preloading_definition_stays_skipped_when_the_grammar_is_unavailable(
    tmp_path, project, monkeypatch
):
    monkeypatch.setattr(delivery, "MARKER_PATTERN", None)
    plugin = make_installation(tmp_path, "skills: [refactoring]\n")

    assert deliver(spawn_payload(project), plugin) == Skipped("preloaded")
    assert rows_of(project) == []


def test_without_the_grammar_a_spawn_without_the_preload_fails_loudly(
    plugin, project, monkeypatch, capsys
):
    monkeypatch.setattr(delivery, "MARKER_PATTERN", None)
    monkeypatch.setattr(delivery, "MARKER_IMPORT_ERROR", "ImportError: no scripts")

    assert deliver(spawn_payload(project), plugin) == Failed("grammar-unavailable")
    (row,) = rows_of(project)
    assert (row["outcome"], row["reason"]) == ("failed", "grammar-unavailable")
    assert "ImportError: no scripts" in capsys.readouterr().err


def test_an_unreadable_skill_fails_with_one_row_and_one_stderr_line(plugin, project, capsys):
    (plugin / "skills" / "refactoring" / "SKILL.md").unlink()

    assert deliver(spawn_payload(project), plugin) == Failed("skill-unreadable")
    (row,) = rows_of(project)
    assert (row["outcome"], row["reason"], row["route"]) == (
        "failed",
        "skill-unreadable",
        "unknown",
    )
    assert "body_digest" not in row
    assert capsys.readouterr().err.count("\n") == 1


def test_an_unreadable_definition_fails_instead_of_risking_a_second_copy(plugin, project, capsys):
    (plugin / "agents" / "implementer.md").unlink()

    assert deliver(spawn_payload(project), plugin) == Failed("definition-unreadable")
    assert [row["reason"] for row in rows_of(project)] == ["definition-unreadable"]
    assert "definition-unreadable" in capsys.readouterr().err


def test_a_step_loop_pointer_to_a_marked_step_is_served_by_the_step_request_route(plugin, project):
    request = project / ".ai-work" / SLUG / f"PROMPT_{REQUEST_ID}.md"
    request.parent.mkdir(parents=True)
    request.write_text(f'Task slug: {SLUG}\n\n<step id="4">\n### {MARKER} Move\n</step>\n')
    pointer = (
        f"Task slug: {SLUG}\nSpawn request: {REQUEST_ID}\nRead {request} first and follow it.\n"
    )

    outcome = deliver(spawn_payload(project, pointer), plugin)

    assert isinstance(outcome, Served)
    assert outcome.route == StepRequest(REQUEST_ID)
    assert [row["route"] for row in rows_of(project)] == ["step-request"]


def test_a_step_loop_pointer_whose_request_is_missing_fails_as_unresolvable(plugin, project):
    pointer = (
        f"Task slug: {SLUG}\nSpawn request: {REQUEST_ID}\n"
        f"Read {project}/.ai-work/{SLUG}/PROMPT_{REQUEST_ID}.md first.\n"
    )

    assert deliver(spawn_payload(project, pointer), plugin) == Failed("request-unresolvable")
    assert [row["reason"] for row in rows_of(project)] == ["request-unresolvable"]


def test_a_request_behind_a_symlinked_directory_is_not_read(tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / f"PROMPT_{REQUEST_ID}.md").write_text("secret\n")
    (tmp_path / ".ai-work").mkdir()
    (tmp_path / ".ai-work" / SLUG).symlink_to(real)

    assert delivery.read_request(tmp_path / ".ai-work" / SLUG / f"PROMPT_{REQUEST_ID}.md") is None


@pytest.mark.parametrize("failing", ["preload_state", "classify", "read_body", "render_block"])
def test_a_dependency_that_raises_becomes_an_internal_error(
    failing, plugin, project, monkeypatch, capsys
):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(delivery, failing, boom)

    assert deliver(spawn_payload(project), plugin) == Failed("internal-error")
    assert [row["reason"] for row in rows_of(project)] == ["internal-error"]
    assert "internal-error" in capsys.readouterr().err


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not an object",
        {"tool_input": ["not", "an", "object"]},
        {"tool_input": {"subagent_type": 7, "prompt": MARKED_PROMPT}},
        {"tool_input": {"subagent_type": ROLE, "prompt": None}},
    ],
    ids=["none", "string", "list-input", "numeric-type", "null-prompt"],
)
def test_malformed_input_fails_and_is_recorded_where_the_process_runs(
    payload, plugin, project, monkeypatch
):
    monkeypatch.chdir(project)

    assert deliver(payload, plugin) == Failed("input-malformed")
    (row,) = rows_of(project)
    assert (row["outcome"], row["reason"]) == ("failed", "input-malformed")


def test_where_no_log_serves_the_project_nothing_is_written_and_nothing_raises(
    plugin, tmp_path, capsys
):
    unserved = tmp_path / "unserved"
    unserved.mkdir()
    (unserved / ".git").mkdir()
    (plugin / "skills" / "refactoring" / "SKILL.md").unlink()

    assert deliver(spawn_payload(unserved), plugin) == Failed("skill-unreadable")
    assert not (unserved / ".ai-state").exists()
    assert "skill-unreadable" in capsys.readouterr().err


def test_a_log_that_cannot_be_written_never_stops_the_delivery(plugin, project, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(os, "getcwd", refuse)
    monkeypatch.setattr("_observation_log.writer.record", refuse)

    assert isinstance(deliver(spawn_payload(project), plugin), Served)
