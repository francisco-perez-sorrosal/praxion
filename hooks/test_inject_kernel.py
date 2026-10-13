"""Tests for hooks/inject_kernel.py -- the SubagentStart slot hook.

Every behavior runs the script as a separate process on a synthetic
`SubagentStart` payload, the way the harness runs it: the payload on stdin,
`CLAUDE_PLUGIN_ROOT` in the environment, one `--slot N` per injected string.
The plugin is a scratch directory holding only a kernel index; the project is a
scratch git working tree.

Gate-liveness contract (rules/swe/gate-liveness.md): the hook decides who
receives a kernel, so each refusal below (no status, host-native agent, another
plugin's agent, no index, bad schema, an over-cap string) is a known-bad input
the hook must answer with nothing, beside the inputs that must receive it.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
HOOK = HOOKS_DIR / "inject_kernel.py"
sys.path.insert(0, str(HOOKS_DIR))

import inject_kernel  # noqa: E402
from _observation_log import reader  # noqa: E402

ROLE = "researcher"
AGENT_TYPE = f"praxion:{ROLE}"
VERSION = "kernel-version-1"
PLUGIN_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
CAP = inject_kernel.INJECTION_CAP


# -- Scratch plugin, project and spawn ------------------------------------------------


def make_plugin(
    tmp_path: Path, strings=("KERNEL ONE",), status: str | None = "trial", slots=9, **index
) -> Path:
    """A plugin root whose index records `ROLE` with `strings` at `status`."""
    entry = {"status": status, "strings": list(strings)}
    document = {
        "schema": 1,
        "kernel_version": VERSION,
        "slots": slots,
        "roles": {ROLE: entry},
        **index,
    }
    path = tmp_path / "plugin" / "claude" / "kernels" / "index.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return tmp_path / "plugin"


def make_project(tmp_path: Path, claude_md: str | None = None, managed: bool = True) -> Path:
    """A git working tree; `managed` gives it `.ai-state/`, `claude_md` a root CLAUDE.md."""
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, env=_env(tmp_path, None))
    if managed:
        (project / ".ai-state").mkdir()
    if claude_md is not None:
        (project / "CLAUDE.md").write_text(claude_md, encoding="utf-8", newline="")
    return project


def _env(tmp_path: Path, plugin: Path | None, **extra: str) -> dict:
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "home")}
    if plugin is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
    return {**env, **extra}


def payload(project: Path, agent_type: str = AGENT_TYPE, **fields) -> str:
    return json.dumps(
        {
            "session_id": "session-1",
            "cwd": str(project),
            "hook_event_name": "SubagentStart",
            "agent_id": "agent-0001",
            "agent_type": agent_type,
            **fields,
        }
    )


def run_hook(tmp_path, plugin, stdin, slot="1", **extra_env) -> subprocess.CompletedProcess:
    args = [] if slot is None else ["--slot", slot]
    return subprocess.run(
        [sys.executable, str(HOOK), *args],
        input=stdin,
        env=_env(tmp_path, plugin, **extra_env),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )


def injected(done: subprocess.CompletedProcess) -> str | None:
    """The additionalContext the hook printed; None when it printed nothing."""
    if not done.stdout:
        return None
    output = json.loads(done.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SubagentStart"
    return output["additionalContext"]


def spawn(tmp_path, plugin, project, agent_type=AGENT_TYPE, slots=9, **env) -> list:
    """What each slot printed for one spawn, in slot order (None where nothing)."""
    stdin = payload(project, agent_type)
    return [injected(run_hook(tmp_path, plugin, stdin, str(n), **env)) for n in range(1, slots + 1)]


def delivered(strings: list) -> list:
    return [s for s in strings if s is not None]


def rows(project: Path) -> list:
    path = reader.log_path(project / ".ai-state")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def project_text(lines: int) -> str:
    return "".join(
        f"Project convention line {n:04d}: keep fixtures under data/.\n" for n in range(lines)
    )


def part_bodies(strings: list) -> list:
    """The project-file text of each delivered part: the string minus marker and header."""
    return [s.split("\n", 2)[2] for s in strings if "[project CLAUDE.md, part" in s]


# -- Who receives a kernel -------------------------------------------------------------


@pytest.mark.parametrize("status", ["trial", "switched"])
def test_a_role_at_trial_or_switched_receives_its_kernel_marked_with_version_and_slot(
    tmp_path, status
):
    plugin = make_plugin(tmp_path, status=status)
    project = make_project(tmp_path)

    done = run_hook(tmp_path, plugin, payload(project))

    assert done.returncode == 0
    assert injected(done) == f"[praxion kernel version={VERSION} slot=1]\nKERNEL ONE"


def test_each_slot_prints_the_string_of_that_ordinal(tmp_path):
    plugin = make_plugin(tmp_path, strings=("FIRST", "SECOND"))
    project = make_project(tmp_path)

    strings = spawn(tmp_path, plugin, project, slots=3)

    assert strings == [
        f"[praxion kernel version={VERSION} slot=1]\nFIRST",
        f"[praxion kernel version={VERSION} slot=2]\nSECOND",
        None,
    ]


@pytest.mark.parametrize("status", [None, "retired"])
def test_a_role_at_no_adoption_status_receives_nothing_and_leaves_no_row(tmp_path, status):
    plugin = make_plugin(tmp_path, status=status)
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project)) == []
    assert rows(project) == []


def test_a_role_the_index_does_not_know_receives_nothing(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project, "praxion:unknown-role")) == []


@pytest.mark.parametrize("agent_type", ["Explore", "Plan", "general-purpose"])
def test_a_host_native_agent_receives_no_role_kernel(tmp_path, agent_type):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project, agent_type)) == []


@pytest.mark.parametrize(
    "agent_type", [ROLE, f"other-plugin:{ROLE}", f"praxion:{ROLE}:extra", "praxion:"]
)
def test_an_agent_outside_this_plugin_sharing_a_role_name_receives_no_role_kernel(
    tmp_path, agent_type
):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project, agent_type)) == []


def test_a_plugin_without_a_kernel_index_injects_nothing(tmp_path):
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, tmp_path / "no-plugin", project)) == []


def test_an_index_of_an_unknown_schema_injects_nothing(tmp_path):
    plugin = make_plugin(tmp_path, schema=2)
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project)) == []


def test_a_kernel_and_a_ledger_found_in_the_project_are_never_read(tmp_path):
    plugin = make_plugin(tmp_path, status=None)
    project = make_project(tmp_path)
    (project / ".ai-state" / "kernel_adoption.yaml").write_text(
        f"version: 1\nroles:\n  {ROLE}:\n    status: trial\n", encoding="utf-8"
    )
    kernels = project / "claude" / "kernels"
    kernels.mkdir(parents=True)
    (kernels / "index.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "kernel_version": "decoy",
                "slots": 9,
                "roles": {ROLE: {"status": "trial", "strings": ["DECOY KERNEL"]}},
            }
        )
    )

    assert delivered(spawn(tmp_path, plugin, project)) == []


# -- Malformed input never blocks a spawn ----------------------------------------------


@pytest.mark.parametrize(
    "stdin",
    [
        "not json at all",
        "",
        "[]",
        "{}",
        '{"agent_type": 7}',
        '{"hook_event_name": "SubagentStart"}',
    ],
    ids=[
        "not JSON",
        "empty",
        "not an object",
        "no fields",
        "agent type not a string",
        "no agent type",
    ],
)
def test_malformed_input_prints_nothing_and_exits_zero(tmp_path, stdin):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    done = run_hook(tmp_path, plugin, stdin)

    assert (done.returncode, done.stdout) == (0, "")
    assert rows(project) == []


@pytest.mark.parametrize(
    "slot", [None, "0", "-1", "first"], ids=["absent", "zero", "negative", "word"]
)
def test_a_slot_argument_that_is_not_a_positive_number_prints_nothing_and_exits_zero(
    tmp_path, slot
):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    done = run_hook(tmp_path, plugin, payload(project), slot=slot)

    assert (done.returncode, done.stdout) == (0, "")


def test_without_a_plugin_root_the_hook_prints_nothing_and_exits_zero(tmp_path):
    project = make_project(tmp_path)

    done = run_hook(tmp_path, None, payload(project))

    assert (done.returncode, done.stdout) == (0, "")


# -- The running plugin, not the checkout it is run from ---------------------------------


def test_the_plugin_location_is_written_out_and_no_literal_variable_reaches_the_role(tmp_path):
    plugin = make_plugin(tmp_path, strings=(f"See {PLUGIN_VARIABLE}/claude/kernels/x.md",))
    project = make_project(tmp_path)

    first = delivered(spawn(tmp_path, plugin, project))[0]

    assert f"See {plugin}/claude/kernels/x.md" in first
    assert PLUGIN_VARIABLE not in first


def test_outside_the_praxion_checkout_the_running_plugins_kernel_arrives(tmp_path):
    plugin = make_plugin(tmp_path, strings=(f"RUNNING KERNEL {PLUGIN_VARIABLE}",))
    project = make_project(tmp_path, managed=False)
    decoy = project / "claude" / "kernels"
    decoy.mkdir(parents=True)
    (decoy / "core.md").write_text("DECOY KERNEL")

    received = "".join(delivered(spawn(tmp_path, plugin, project)))

    assert f"RUNNING KERNEL {plugin}" in received
    assert "DECOY KERNEL" not in received


# -- The project's own instruction file --------------------------------------------------


def test_a_small_project_file_arrives_whole_in_a_numbered_part_after_the_kernel(tmp_path):
    text = project_text(12)
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, claude_md=text)

    strings = delivered(spawn(tmp_path, plugin, project))

    assert part_bodies(strings) == [text]
    assert strings[1].splitlines()[1] == "[project CLAUDE.md, part 1 of 1]"


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
    text = project_text(1000)
    plugin = make_plugin(tmp_path, slots=3)
    project = make_project(tmp_path, claude_md=text)

    strings = delivered(spawn(tmp_path, plugin, project, slots=3))
    row = rows(project)[0]

    assert len(strings) == 3
    assert "further part(s) were not delivered" in strings[-1]
    assert str(project.resolve() / "CLAUDE.md") in strings[-1]
    assert row["project_file"]["omitted"] == len(inject_kernel.split_chunks(text, 9000)) - 2
    assert [s for s in strings if len(s) > CAP] == []


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


# -- The observation row -----------------------------------------------------------------


def test_a_spawn_that_receives_a_kernel_leaves_exactly_one_row_describing_it(tmp_path):
    plugin = make_plugin(tmp_path, strings=("FIRST", "SECOND"))
    plugin_index = plugin / "claude" / "kernels" / "index.json"
    document = json.loads(plugin_index.read_text())
    document["roles"][ROLE]["modules"] = ["core", "adr-reader"]
    plugin_index.write_text(json.dumps(document))
    project = make_project(tmp_path, claude_md=project_text(5))

    strings = delivered(spawn(tmp_path, plugin, project))
    (row,) = rows(project)

    assert row["event_type"] == "kernel_injected"
    assert (row["role"], row["agent_type"], row["agent_id"]) == (ROLE, AGENT_TYPE, "agent-0001")
    assert (row["session_id"], row["kernel_version"]) == ("session-1", VERSION)
    assert row["strings"] == [
        {"module": "core", "part": None, "chars": len(strings[0])},
        {"module": "adr-reader", "part": None, "chars": len(strings[1])},
        {"module": "project-claude-md", "part": 1, "chars": len(strings[2])},
    ]
    assert row["project_file"] == {"chars": len(project_text(5)), "parts": 1, "omitted": 0}


def test_a_row_without_a_project_file_records_none(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    spawn(tmp_path, plugin, project)

    assert rows(project)[0]["project_file"] is None


def test_a_spawn_that_receives_no_kernel_leaves_no_row(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    spawn(tmp_path, plugin, project, "Explore")

    assert rows(project) == []


def test_a_project_with_no_observation_log_still_gets_its_kernel_and_no_row(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path, managed=False)

    strings = delivered(spawn(tmp_path, plugin, project))

    assert len(strings) == 1
    assert not (project / ".ai-state").exists()


def test_switching_the_observation_log_off_stops_the_row_and_not_the_kernel(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    strings = spawn(tmp_path, plugin, project, PRAXION_OBSERVATION_LOG="off")

    assert len(delivered(strings)) == 1
    assert rows(project) == []


def test_a_slot_past_what_the_spawn_receives_prints_nothing(tmp_path):
    plugin = make_plugin(tmp_path)
    project = make_project(tmp_path)

    assert run_hook(tmp_path, plugin, payload(project), "5").stdout == ""
    assert run_hook(tmp_path, plugin, payload(project), "10").stdout == ""


# -- The cap -----------------------------------------------------------------------------


def test_a_kernel_string_that_passes_the_cap_once_the_location_is_written_out_is_refused_whole(
    tmp_path,
):
    nearly_full = "a" * (CAP - 200) + PLUGIN_VARIABLE * 20
    plugin = make_plugin(tmp_path, strings=("SMALL ONE", nearly_full))
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project)) == []
    assert rows(project) == []


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


def test_the_role_of_an_agent_is_read_from_this_plugins_namespace_only():
    roles = [
        inject_kernel.role_of(t) for t in (AGENT_TYPE, "other:researcher", "researcher", 7, None)
    ]

    assert roles == [ROLE, None, None, None, None]


# -- The script's own constraints --------------------------------------------------------


def test_the_script_parses_as_python_3_9():
    ast.parse(HOOK.read_text(encoding="utf-8"), feature_version=(3, 9))


def test_the_script_never_finds_the_plugin_or_the_project_from_its_own_path():
    source = HOOK.read_text(encoding="utf-8")

    assert "__file__" not in source


def imported_modules(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    plain = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    from_ = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
    return {name.split(".")[0] for name in plain + from_}


def test_the_script_reads_no_yaml_and_imports_only_the_standard_library_and_the_log_package():
    assert imported_modules(HOOK) <= set(sys.stdlib_module_names) | {"_observation_log"}
