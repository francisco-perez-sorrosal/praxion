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
MARKER_VERSION = VERSION[: inject_kernel.MARKER_VERSION_CHARS]
PLUGIN_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
CAP = inject_kernel.INJECTION_CAP


# -- Scratch plugin, project and spawn ------------------------------------------------


def ledger_text(status: str | None, role: str = ROLE) -> str:
    """The adoption ledger as its writers emit it (block style), the role at `status` if any."""
    roles = f"  {role}:\n    status: {status}\n    since: '2026-10-12'\n    runs: []\n"
    return (
        "version: 1\neligible:\n- researcher\n- verifier\n"
        f"roles:{' {}' if status is None else chr(10) + roles}"
    )


def make_plugin(
    tmp_path: Path,
    strings=("KERNEL ONE",),
    status: str | None = "trial",
    slots=9,
    ledger: str | None = "",
    index_status: str | None = None,
    **index,
) -> Path:
    """A plugin root whose ledger puts `ROLE` at `status` and whose index holds `strings`.

    `ledger` replaces the ledger's text; None writes no ledger. The index carries no status
    unless `index_status` says so: the ledger alone decides who receives a kernel.
    """
    entry = {"status": index_status, "strings": list(strings)}
    document = {
        "schema": 1,
        "kernel_version": VERSION,
        "slots": slots,
        "roles": {ROLE: entry},
        **index,
    }
    root = tmp_path / "plugin"
    (root / "claude" / "kernels").mkdir(parents=True)
    (root / "claude" / "kernels" / "index.json").write_text(json.dumps(document), encoding="utf-8")
    if ledger is not None:
        (root / ".ai-state").mkdir()
        text = ledger or ledger_text(status)
        (root / ".ai-state" / "kernel_adoption.yaml").write_text(text, encoding="utf-8")
    return root


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
    return [s.split("\n", 3)[3] for s in strings if "[project CLAUDE.md, part" in s]


# -- Who receives a kernel -------------------------------------------------------------


@pytest.mark.parametrize("status", ["trial", "switched"])
def test_a_role_at_trial_or_switched_receives_its_kernel_marked_with_version_and_slot(
    tmp_path, status
):
    plugin = make_plugin(tmp_path, status=status)
    project = make_project(tmp_path)

    done = run_hook(tmp_path, plugin, payload(project))

    assert done.returncode == 0
    assert injected(done) == f"[praxion {MARKER_VERSION} #1]\n\nKERNEL ONE\n\n"


def test_each_slot_prints_the_string_of_that_ordinal(tmp_path):
    plugin = make_plugin(tmp_path, strings=("FIRST", "SECOND"))
    project = make_project(tmp_path)

    strings = spawn(tmp_path, plugin, project, slots=3)

    assert strings == [
        f"[praxion {MARKER_VERSION} #1]\n\nFIRST\n\n",
        f"[praxion {MARKER_VERSION} #2]\n\nSECOND\n\n",
        None,
    ]


def test_strings_joined_end_to_end_keep_the_marker_a_short_paragraph_of_its_own(tmp_path):
    plugin = make_plugin(tmp_path, strings=("FIRST\n\nand more", "SECOND"))
    project = make_project(tmp_path)

    joined = "".join(delivered(spawn(tmp_path, plugin, project)))

    assert joined.split("\n\n") == [
        f"[praxion {MARKER_VERSION} #1]",
        "FIRST",
        "and more",
        f"[praxion {MARKER_VERSION} #2]",
        "SECOND",
        "",
    ]
    assert len(f"[praxion {MARKER_VERSION} #12]") < 24


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


# -- The adoption ledger decides who receives a kernel ----------------------------------

ONE_OF_SEVERAL = (
    "version: 1\neligible:\n- researcher\n- verifier\nroles:\n"
    "  verifier:\n    status: switched\n    since: '2026-10-12'\n    runs:\n"
    "    - id: r1\n      status: trial\n      complete_pairs: 24\n"
    f"  {ROLE}:\n    status: trial\n    since: '2026-10-13T09:00:00+00:00'\n    runs: []\n"
)


@pytest.mark.parametrize(
    "ledger",
    [
        "",
        "version: 1\nroles: {}\n",
        "version: 1\nroles:\n  verifier:\n    status: trial\n",
        "version: 1\nroles:\n  researcher:\n    status: retired\n",
        "roles: [\n  researcher: {status: trial\n",
        "\x00\x01 not a ledger at all \xff",
        "# roles:\n#   researcher:\n#     status: trial\n",
        "eligible:\n- researcher\nstatus: trial\n",
        f"version: 1\nroles:\n  {ROLE}:\n    runs:\n    - status: trial\n",
    ],
    ids=[
        "empty",
        "no roles",
        "another role only",
        "a status that is neither",
        "unbalanced flow syntax",
        "binary text",
        "all comments",
        "status outside the roles block",
        "a status nested under the role's runs",
    ],
)
def test_a_ledger_that_puts_the_role_at_no_status_injects_nothing_whatever_the_index_says(
    tmp_path, ledger
):
    plugin = make_plugin(tmp_path, ledger=ledger or "\n", index_status="switched")
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project)) == []
    assert rows(project) == []


def test_a_plugin_without_an_adoption_ledger_injects_nothing_even_if_the_index_says_trial(
    tmp_path,
):
    plugin = make_plugin(tmp_path, ledger=None, index_status="trial")
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project)) == []


def test_a_role_at_trial_among_other_roles_in_the_ledgers_own_shape_receives_its_kernel(tmp_path):
    plugin = make_plugin(tmp_path, ledger=ONE_OF_SEVERAL)
    project = make_project(tmp_path)

    assert len(delivered(spawn(tmp_path, plugin, project))) == 1


def test_an_unreadable_ledger_injects_nothing_and_exits_zero(tmp_path):
    plugin = make_plugin(tmp_path, ledger=None)
    (plugin / ".ai-state" / "kernel_adoption.yaml").mkdir(parents=True)
    project = make_project(tmp_path)

    done = run_hook(tmp_path, plugin, payload(project))

    assert (done.returncode, done.stdout) == (0, "")


@pytest.mark.parametrize(
    ("text", "status"),
    [
        (ledger_text("trial"), "trial"),
        (ledger_text("switched"), "switched"),
        (ledger_text(None), None),
        (ONE_OF_SEVERAL, "trial"),
        ("roles:\n  researcher:\n    status: 'trial'\n", None),
        (
            "roles:   # who is adopted\n  researcher:  # this one\n    status: trial  # yes\n",
            "trial",
        ),
    ],
    ids=["trial", "switched", "no roles", "among others", "a quoted value", "trailing comments"],
)
def test_the_status_is_read_from_the_ledgers_roles_block_for_the_role_alone(text, status):
    assert inject_kernel.adoption_status(text, ROLE) == status


# -- The project file is read as the harness would load it, within bounds ----------------


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


def test_an_index_modules_list_of_the_wrong_length_is_named_by_position(tmp_path):
    plugin = make_plugin(tmp_path, strings=("FIRST", "SECOND"))
    path = plugin / "claude" / "kernels" / "index.json"
    document = json.loads(path.read_text())
    document["roles"][ROLE]["modules"] = ["only-one"]
    path.write_text(json.dumps(document))
    project = make_project(tmp_path)

    spawn(tmp_path, plugin, project)

    assert [entry["module"] for entry in rows(project)[0]["strings"]] == ["kernel-1", "kernel-2"]


# -- The cap counts what the harness counts ------------------------------------------------

ASTRAL = "\U0001f600"  # one character, two UTF-16 units


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


def test_a_kernel_string_under_the_cap_in_characters_and_over_it_in_units_is_refused_whole(
    tmp_path,
):
    plugin = make_plugin(tmp_path, strings=(ASTRAL * (CAP // 2 + 100),))
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project)) == []
    assert rows(project) == []


def test_a_long_line_of_wide_characters_is_cut_between_characters_and_under_the_limit():
    line = ASTRAL * 100

    pieces = inject_kernel.cut_long_line(line, 60)

    assert [p for p in pieces if inject_kernel.units(p) > 60] == []
    assert "".join(pieces).replace(inject_kernel.LINE_CONTINUED, "") == line


# -- Every slot decides the refusal alike --------------------------------------------------


def run_slots(slots, monkeypatch, capsys, project_file):
    monkeypatch.setattr(inject_kernel, "read_project_file", lambda cwd, bound: project_file)
    monkeypatch.setattr(inject_kernel, "record_delivery", lambda *args: None)
    printed = []
    for slot in range(1, slots + 1):
        environ = {"CLAUDE_PLUGIN_ROOT": str(PLUGIN_UNDER_TEST[0])}
        inject_kernel.run(slot, {"agent_type": AGENT_TYPE, "cwd": "."}, environ)
        printed.append(capsys.readouterr().out)
    return printed


PLUGIN_UNDER_TEST: list = []


@pytest.fixture
def plugin_under_test(tmp_path):
    PLUGIN_UNDER_TEST[:] = [make_plugin(tmp_path, strings=("FIRST", "SECOND"), slots=4)]
    yield PLUGIN_UNDER_TEST[0]
    PLUGIN_UNDER_TEST.clear()


def test_a_project_part_past_the_cap_makes_every_slot_print_nothing_not_just_its_own(
    plugin_under_test, monkeypatch, capsys
):
    overflowing = inject_kernel.ProjectFile(
        "/" + "d" * 1500 + "/CLAUDE.md", project_text(1000), True
    )

    assert run_slots(4, monkeypatch, capsys, overflowing) == [""] * 4


def test_the_same_delivery_without_the_oversized_notice_prints_in_every_slot(
    plugin_under_test, monkeypatch, capsys
):
    fitting = inject_kernel.ProjectFile("/p/CLAUDE.md", project_text(1000), True)

    assert [bool(out) for out in run_slots(4, monkeypatch, capsys, fitting)] == [True] * 4


# -- A line `@<path>` imports a file once, as the harness loads it -----------------------


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


def test_an_import_that_links_out_of_the_project_stays_as_written(tmp_path):
    project = make_project(tmp_path, claude_md="@escape.md\n")
    (tmp_path / "outside.md").write_text("never shown\n")
    (project / "escape.md").symlink_to(tmp_path / "outside.md")

    assert delivered_text(tmp_path, project) == "@escape.md\n"


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
