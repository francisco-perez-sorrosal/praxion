"""Tests for hooks/inject_kernel.py -- the project's own CLAUDE.md beside the kernel.

How the project file is found, read within bounds and containment, split into parts under
the cap, and how its import lines are expanded. Delivery, the ledger and the row are
`test_inject_kernel.py`'s; the scratch plugin, project and spawn are built by
`_inject_kernel_testkit.py`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _inject_kernel_testkit import (  # noqa: E402
    ASTRAL,
    CAP,
    delivered,
    inject_kernel,
    injected,
    make_plugin,
    make_project,
    part_bodies,
    payload,
    project_text,
    run_hook,
    spawn,
)
from _observation_log import reader  # noqa: E402


def rows(project: Path) -> list:
    """The project's observation-log rows, oldest first; none when no log exists."""
    path = reader.log_path(project / ".ai-state")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# -- The project's own instruction file --------------------------------------------------


def test_a_small_project_file_arrives_whole_in_a_numbered_part_after_the_kernel(tmp_path):
    text = project_text(12)
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=text)

    strings = delivered(spawn(tmp_path, plugin, project))

    assert part_bodies(strings) == [text]
    assert strings[1].splitlines()[2] == "[project CLAUDE.md, part 1 of 1]"


def test_a_project_without_an_instruction_file_receives_only_the_kernel(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    assert len(delivered(spawn(tmp_path, plugin, project))) == 1


def test_a_large_project_file_arrives_as_parts_whose_text_is_the_file_in_order(tmp_path):
    text = project_text(400)
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=text)

    strings = delivered(spawn(tmp_path, plugin, project))

    assert len(text) > CAP
    assert [s for s in strings if len(s) > CAP] == []
    assert "".join(part_bodies(strings)) == text
    assert len(part_bodies(strings)) > 1


def test_a_project_file_is_delivered_with_its_own_line_endings(tmp_path):
    text = "first line\r\nsecond line\r\n"
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=text)

    assert part_bodies(delivered(spawn(tmp_path, plugin, project))) == [text]


def test_a_project_file_beyond_the_reserved_slots_says_what_was_left_out(tmp_path):
    text = project_text(400)
    plugin = make_plugin(tmp_path, slots=3)
    project = make_project(tmp_path, claude_md=text)

    strings = delivered(spawn(tmp_path, plugin, project, slots=3))
    row = rows(project)[0]

    assert len(strings) == 3
    assert "further part(s) were not delivered" in strings[-1]
    assert "read CLAUDE.md in the project root for the rest" in strings[-1]
    assert str(project.resolve()) not in strings[-1]
    assert row["project_file"]["omitted"] == len(inject_kernel.split_chunks(text, 9000)) - 2
    assert [s for s in strings if len(s) > CAP] == []


def test_a_project_deep_in_the_file_system_past_its_slots_still_delivers_and_names_no_path(
    tmp_path,
):
    deep = tmp_path.joinpath(*["d" * 200] * 4)
    deep.mkdir(parents=True)
    plugin = make_plugin(tmp_path, slots=3)
    project = make_project(deep, claude_md=project_text(400))

    strings = delivered(spawn(tmp_path, plugin, project, slots=3))

    assert len(strings) == 3
    assert "read CLAUDE.md in the project root for the rest" in strings[-1]
    assert "d" * 200 not in strings[-1]


def test_the_project_file_is_found_through_git_from_a_subdirectory(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=project_text(3))
    inner = project / "src" / "pkg"
    inner.mkdir(parents=True)

    stdin = payload(project, cwd=str(inner))
    strings = [injected(run_hook(tmp_path, plugin, stdin, str(n))) for n in (1, 2)]

    assert part_bodies(strings) == [project_text(3)]
    assert len(rows(project)) == 1


@pytest.mark.parametrize(
    ("line_length", "cuts"),
    [(CAP, 1), (3 * CAP + 7, 3)],
    ids=["a line at the cap", "a line over three caps"],
)
def test_a_line_longer_than_a_part_is_cut_inside_the_line_and_marked_at_each_cut(
    tmp_path, line_length, cuts
):
    long_line = "x" * line_length
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=f"before\n{long_line}\nafter\n")

    strings = delivered(spawn(tmp_path, plugin, project))
    text = "".join(part_bodies(strings))

    assert [s for s in strings if len(s) > CAP] == []
    assert text.replace(inject_kernel.LINE_CONTINUED, "") == f"before\n{long_line}\nafter\n"
    assert text.count(inject_kernel.LINE_CONTINUED) == cuts


# -- Pure helpers ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "one line",
        "a\nb\nc\n",
        "\n\n\n",
        "x" * 25 + "\nshort\n" + "y" * 40,
        "tail without newline",
    ],
    ids=["empty", "one line", "three lines", "blank lines", "long lines", "no final newline"],
)
def test_chunks_concatenate_back_to_the_text_and_never_pass_the_limit(text):
    chunks = inject_kernel.split_chunks(text, 20)

    assert [c for c in chunks if len(c) > 20] == []
    assert "".join(chunks).replace(inject_kernel.LINE_CONTINUED, "") == text


def test_a_chunk_boundary_falls_at_a_line_end_when_no_line_is_over_the_limit():
    chunks = inject_kernel.split_chunks("aaaa\nbbbb\ncccc\n", 10)

    assert chunks == ["aaaa\nbbbb\n", "cccc\n"]


# -- The project file is read within bounds, and only from inside the project ----------


def kernel_only(strings: list) -> bool:
    received = delivered(strings)
    return len(received) == 1 and not part_bodies(received)


def test_a_project_file_that_links_outside_the_working_tree_is_not_delivered(tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("OUTSIDE SECRET\n")
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)
    (project / "CLAUDE.md").symlink_to(secret)

    strings = spawn(tmp_path, plugin, project)

    assert kernel_only(strings)
    assert "OUTSIDE SECRET" not in "".join(delivered(strings))
    assert rows(project)[0]["project_file"] is None


def test_a_project_file_that_links_to_another_file_inside_the_working_tree_is_delivered(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)
    (project / "AGENTS.md").write_text("shared conventions\n")
    (project / "CLAUDE.md").symlink_to("AGENTS.md")

    assert part_bodies(delivered(spawn(tmp_path, plugin, project))) == ["shared conventions\n"]


def test_a_project_file_that_is_a_directory_is_not_delivered(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)
    (project / "CLAUDE.md").mkdir()

    assert kernel_only(spawn(tmp_path, plugin, project))


def test_a_project_file_that_is_a_pipe_is_not_waited_for(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)
    os.mkfifo(project / "CLAUDE.md")

    assert kernel_only(spawn(tmp_path, plugin, project))


def test_a_project_file_past_the_read_bound_is_cut_at_it_and_the_notice_says_at_least(tmp_path):
    plugin = make_plugin(tmp_path, slots=3)
    project = make_project(tmp_path, claude_md=project_text(5000))

    strings = delivered(spawn(tmp_path, plugin, project, slots=3))

    assert rows(project)[0]["project_file"]["chars"] <= 3 * CAP
    assert "at least " in strings[-1]
    assert "further part(s) were not delivered" in strings[-1]


def test_undecodable_bytes_in_the_project_file_arrive_as_replacement_characters(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)
    (project / "CLAUDE.md").write_bytes(b"before \xff\xfe after\n")

    assert part_bodies(delivered(spawn(tmp_path, plugin, project))) == ["before �� after\n"]


@pytest.mark.parametrize(
    "where",
    ["outside any repository", "missing"],
)
def test_a_working_directory_with_no_repository_or_no_existence_gives_the_kernel_alone(
    tmp_path, where
):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=project_text(3))
    elsewhere = tmp_path / "plain" if where == "outside any repository" else tmp_path / "gone"
    elsewhere.mkdir(exist_ok=where != "missing")
    stdin = payload(project, cwd=str(elsewhere))

    strings = [injected(run_hook(tmp_path, plugin, stdin, str(n))) for n in (1, 2)]

    assert strings[0].endswith("KERNEL ONE\n\n")
    assert strings[1:] == [None]
    assert rows(project) == []


def test_when_the_version_control_tool_fails_the_kernel_still_arrives_without_the_project_file(
    tmp_path,
):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=project_text(3))

    done = run_hook(tmp_path, plugin, payload(project), PATH=str(tmp_path / "no-tools"))

    assert injected(done).endswith("KERNEL ONE\n\n")
    assert (
        run_hook(tmp_path, plugin, payload(project), "2", PATH=str(tmp_path / "no-tools")).stdout
        == ""
    )


def test_when_the_version_control_tool_prints_an_undecodable_path_the_kernel_arrives_alone(
    tmp_path,
):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=project_text(3))
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "git").write_bytes(b"#!/bin/sh\nprintf '\\351\\n'\nexit 0\n")  # byte 0xE9
    (tools / "git").chmod(0o755)
    path = f"{tools}{os.pathsep}{os.environ['PATH']}"

    strings = spawn(tmp_path, plugin, project, slots=2, PATH=path)

    assert strings[0].endswith("KERNEL ONE\n\n")
    assert strings[1] is None


def test_a_project_file_of_characters_outside_the_basic_plane_arrives_in_parts_under_the_cap(
    tmp_path,
):
    text = "".join(ASTRAL * 1000 + "\n" for _ in range(20))
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=text)

    strings = delivered(spawn(tmp_path, plugin, project))

    assert [s for s in strings if inject_kernel.units(s) > CAP] == []
    assert "".join(part_bodies(strings)) == text
    assert any(len(s) < inject_kernel.units(s) for s in strings[1:])


def test_a_long_line_of_wide_characters_is_cut_between_characters_and_under_the_limit():
    line = ASTRAL * 100

    pieces = inject_kernel.cut_long_line(line, 60)

    assert [p for p in pieces if inject_kernel.units(p) > 60] == []
    assert "".join(pieces).replace(inject_kernel.LINE_CONTINUED, "") == line


# -- A line `@<path>` imports a file once, outside fenced code ---------------------------


def delivered_text(tmp_path, project):
    plugin = make_plugin(tmp_path)
    return "".join(part_bodies(delivered(spawn(tmp_path, plugin, project))))


def test_an_import_line_is_replaced_by_the_file_it_names(tmp_path):
    project = make_project(tmp_path, claude_md="top\n@AGENTS.md\nbottom\n")
    (project / "AGENTS.md").write_text("shared one\nshared two\n")

    assert delivered_text(tmp_path, project) == "top\nshared one\nshared two\nbottom\n"


def test_an_import_inside_an_imported_file_is_left_as_written(tmp_path):
    project = make_project(tmp_path, claude_md="@a.md\n")
    (project / "a.md").write_text("from a\n@b.md\n")
    (project / "b.md").write_text("from b\n")

    assert delivered_text(tmp_path, project) == "from a\n@b.md\n"


def test_an_import_of_a_file_beside_the_project_file_in_a_subdirectory_resolves_from_the_root(
    tmp_path,
):
    project = make_project(tmp_path, claude_md="@docs/rules.md\n")
    (project / "docs").mkdir()
    (project / "docs" / "rules.md").write_text("doc rules")

    assert delivered_text(tmp_path, project) == "doc rules\n"


@pytest.mark.parametrize(
    "line",
    ["@missing.md", "@docs", "@../outside.md", "@/etc/hosts", "@~/notes.md", "see @AGENTS.md here"],
    ids=["missing", "directory", "outside", "absolute", "home", "mid-line"],
)
def test_an_import_that_is_not_a_regular_file_inside_the_project_stays_as_written(tmp_path, line):
    project = make_project(tmp_path, claude_md=f"{line}\n")
    (project / "docs").mkdir()
    (project / "AGENTS.md").write_text("never shown\n")
    (tmp_path / "outside.md").write_text("never shown\n")

    assert delivered_text(tmp_path, project) == f"{line}\n"


@pytest.mark.parametrize(
    ("misses", "expected"),
    [
        (inject_kernel.IMPORT_ATTEMPT_LIMIT - 1, "shared\n"),
        (inject_kernel.IMPORT_ATTEMPT_LIMIT, "@AGENTS.md\n"),
    ],
    ids=["the last attempt resolves", "past the limit stays as written"],
)
def test_import_lines_are_tried_up_to_the_attempt_limit_and_no_further(tmp_path, misses, expected):
    unresolved = "@missing.md\n" * misses
    project = make_project(tmp_path, claude_md=unresolved + "@AGENTS.md\n")
    (project / "AGENTS.md").write_text("shared\n")

    assert delivered_text(tmp_path, project) == unresolved + expected


def test_a_file_of_thousands_of_unresolvable_imports_arrives_as_written_beside_the_kernel(
    tmp_path,
):
    project = make_project(tmp_path, claude_md="@a\n" * 30_000)
    plugin = make_plugin(tmp_path)

    strings = delivered(spawn(tmp_path, plugin, project))

    assert strings[0].endswith("KERNEL ONE\n\n")
    assert len(strings) == 9
    assert part_bodies(strings)[0] == "@a\n" * 3_000


@pytest.mark.parametrize(
    ("opening", "closing"),
    [("```", "```"), ("~~~", "~~~"), ("  ````text", "`````")],
    ids=["backticks", "tildes", "an indented longer fence with an info string"],
)
def test_an_import_line_inside_fenced_code_stays_as_written_and_the_same_line_outside_is_expanded(
    tmp_path, opening, closing
):
    fenced = f"{opening}\n@docs/x.md\n{closing}\n"
    project = make_project(tmp_path, claude_md=fenced + "@docs/x.md\n")
    (project / "docs").mkdir()
    (project / "docs" / "x.md").write_text("imported\n")

    assert delivered_text(tmp_path, project) == fenced + "imported\n"


@pytest.mark.parametrize(
    "text",
    [
        "~~~\n```\n@x.md\n",
        "````\n```\n@x.md\n",
        "```\n``` not a close\n@x.md\n",
        "```\n@x.md\n",
    ],
    ids=["the other character", "a shorter fence", "text after the fence", "never closed"],
)
def test_a_fence_stays_open_until_a_line_that_closes_it(tmp_path, text):
    (tmp_path / "x.md").write_text("imported\n")

    assert inject_kernel.expand_imports(text, str(tmp_path.resolve()), CAP) == text


def test_a_backtick_line_with_a_backtick_in_its_info_string_is_inline_code_not_a_fence(tmp_path):
    (tmp_path / "x.md").write_text("imported\n")

    expanded = inject_kernel.expand_imports("```js`\n@x.md\n", str(tmp_path.resolve()), CAP)

    assert expanded == "```js`\nimported\n"


def test_an_import_that_links_out_of_the_project_stays_as_written(tmp_path):
    project = make_project(tmp_path, claude_md="@escape.md\n")
    (tmp_path / "outside.md").write_text("never shown\n")
    (project / "escape.md").symlink_to(tmp_path / "outside.md")

    assert delivered_text(tmp_path, project) == "@escape.md\n"
