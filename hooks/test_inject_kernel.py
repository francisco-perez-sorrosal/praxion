"""Tests for hooks/inject_kernel.py -- the SubagentStart slot hook: who receives, and what.

Delivery, the adoption ledger, the cap, the in-stream marker and the observation row; the
project file's reading, bounds and imports are `test_inject_kernel_project_file.py`'s. The
scratch plugin, project and spawn are built by `_inject_kernel_testkit.py`.

Gate-liveness contract (rules/swe/gate-liveness.md): the hook decides who
receives a kernel, so each refusal below (no status, host-native agent, another
plugin's agent, no index, bad schema, an over-cap string) is a known-bad input
the hook must answer with nothing, beside the inputs that must receive it.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _inject_kernel_testkit import (  # noqa: E402
    AGENT_TYPE,
    ASTRAL,
    CAP,
    HOOK,
    MARKER_VERSION,
    PLUGIN_VARIABLE,
    ROLE,
    VERSION,
    delivered,
    inject_kernel,
    injected,
    ledger_text,
    make_plugin,
    make_project,
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


HELD = (
    "version: 1\neligible:\n- researcher\n- verifier\nroles:\n"
    f"  {ROLE}:\n    status: held\n    since: '2026-10-12'\n    runs:\n"
    "    - id: r1\n      complete_pairs: 24\n      passes_flip_rule: false\n"
    "    reason: the flip rule did not pass\n"
)


def test_a_role_recorded_held_receives_nothing_and_leaves_no_row(tmp_path):
    plugin = make_plugin(tmp_path, ledger=HELD, index_status="trial")
    project = make_project(tmp_path)

    assert inject_kernel.adoption_status(HELD, ROLE) == "held"
    assert delivered(spawn(tmp_path, plugin, project)) == []
    assert rows(project) == []


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


def test_a_kernel_string_under_the_cap_in_characters_and_over_it_in_units_is_refused_whole(
    tmp_path,
):
    plugin = make_plugin(tmp_path, strings=(ASTRAL * (CAP // 2 + 100),))
    project = make_project(tmp_path)

    assert delivered(spawn(tmp_path, plugin, project)) == []
    assert rows(project) == []


# -- Every slot decides the refusal alike --------------------------------------------------

LONGER_THAN_ITS_SLOTS = inject_kernel.ProjectFile(project_text(1000), True)


def run_slots(plugin, monkeypatch, capsys, slots=4):
    """What each slot printed for one in-process spawn whose project file outgrows its slots."""
    monkeypatch.setattr(
        inject_kernel, "read_project_file", lambda cwd, bound: LONGER_THAN_ITS_SLOTS
    )
    monkeypatch.setattr(inject_kernel, "record_delivery", lambda *args: None)
    printed = []
    for slot in range(1, slots + 1):
        environ = {"CLAUDE_PLUGIN_ROOT": str(plugin)}
        inject_kernel.run(slot, {"agent_type": AGENT_TYPE, "cwd": "."}, environ)
        printed.append(capsys.readouterr().out)
    return printed


def test_a_kernel_string_past_the_cap_makes_every_slot_print_nothing_not_just_its_own(
    tmp_path, monkeypatch, capsys
):
    plugin = make_plugin(tmp_path, strings=("FIRST", "x" * CAP), slots=4)

    assert run_slots(plugin, monkeypatch, capsys) == [""] * 4


def test_a_project_file_longer_than_its_slots_prints_in_every_slot_with_its_notice(
    tmp_path, monkeypatch, capsys
):
    plugin = make_plugin(tmp_path, strings=("FIRST", "SECOND"), slots=4)

    printed = run_slots(plugin, monkeypatch, capsys)

    assert [bool(out) for out in printed] == [True] * 4
    assert "read CLAUDE.md in the project root for the rest" in printed[-1]


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
