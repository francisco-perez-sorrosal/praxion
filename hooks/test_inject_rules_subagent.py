"""What the rule injector delivers to a spawn at `SubagentStart`.

An inheriting spawn in a managed scope receives the managed core units (the
protocol, the intermediate-documents rule and the ADR resident) and nothing else
of the session's delivery; a spawn that starts without instruction files
(`Explore`, `Plan`, a definition setting `omitClaudeMd`) and any spawn in an
unmanaged scope receive nothing. A definition that cannot be read counts as
inheriting, the safe direction.

The hook runs as a subprocess against the synthetic plugin tree of
`test_inject_rules.py`, its manifest given the flipped shape (core units as
managed-only hook-deliver rows) unless a test needs today's.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_inject_rules import (  # noqa: E402
    _GIT_CONVENTIONS_MARKER,
    _ROUTING_MARKER,
    HOOK_SCRIPT,
    _hook_env,
    _import_hook_module,
    _make_manifest,
    _managed_root,
    _run_hook,
    _write_project_config,
)
from test_rule_delivery_slots import (  # noqa: E402
    _CORE_UNIT_IDS,
    _LABEL,
    _add_managed_core_rows,
    _core_body,
)

_SLOTS_PROBED = 8
_INHERITING_ROLE = "praxion:systems-architect"
_LEAN_ROLE = "praxion:researcher"
_HOST_NATIVE = "general-purpose"
_CUSTOM = "custom-reviewer"
_LEAN_FRONTMATTER = "---\nname: {name}\ndescription: x\nomitClaudeMd: true\n---\n\nBody.\n"
_INHERITING_FRONTMATTER = "---\nname: {name}\ndescription: x\n---\n\nBody.\n"
_BIG_UNIT_MARKER = "## Big 0"
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_TEMPLATE = Path(".claude") / "praxion-rules.yaml.example"


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """The synthetic plugin, flipped, with one inheriting and one lean agent of its own."""
    _make_manifest(tmp_path)
    _add_managed_core_rows(tmp_path)
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "systems-architect.md").write_text(
        _INHERITING_FRONTMATTER.format(name="systems-architect")
    )
    (agents / "researcher.md").write_text(_LEAN_FRONTMATTER.format(name="researcher"))
    return tmp_path


@pytest.fixture
def managed(tmp_path: Path) -> Path:
    root, _ = _managed_root(tmp_path)
    return root


@pytest.fixture
def unmanaged(tmp_path: Path) -> Path:
    project = tmp_path / "plain"
    project.mkdir()
    return project


def _spawn(
    plugin_root: Path, cwd: Path, agent_type: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    payload = {
        "session_id": "s",
        "cwd": str(cwd),
        "hook_event_name": "SubagentStart",
        "agent_id": "agent-1",
        "agent_type": agent_type,
    }
    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={**_hook_env(plugin_root), **(env or {})},
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return result


def _slot_outputs(plugin_root: Path, cwd: Path, agent_type: str, **kw) -> list[dict]:
    outputs = []
    for slot in range(1, _SLOTS_PROBED + 1):
        stdout = _spawn(plugin_root, cwd, agent_type, "--slot", str(slot), **kw).stdout.strip()
        outputs.append(json.loads(stdout)["hookSpecificOutput"] if stdout else {})
    return outputs


def _received(plugin_root: Path, cwd: Path, agent_type: str, **kw) -> str:
    """Everything the spawn's slots deliver, joined."""
    outputs = _slot_outputs(plugin_root, cwd, agent_type, **kw)
    return "\n".join(output.get("additionalContext", "") for output in outputs)


def _core_units_in(text: str) -> list[bool]:
    return [_core_body(unit_id) in text for unit_id in _CORE_UNIT_IDS]


def _labelled_unit(text: str) -> str:
    label = _LABEL.match(text)
    assert label, f"an unlabelled part: {text[:80]!r}"
    return label.group(1)


def _write_definition(home: Path, name: str, text: str) -> None:
    agents = home / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    (agents / f"{name}.md").write_text(text)


# -- Who receives the core units ----------------------------------------------------------


@pytest.mark.parametrize("agent_type", [_INHERITING_ROLE, _HOST_NATIVE])
def test_an_inheriting_spawn_in_a_managed_scope_receives_only_the_core_units(
    plugin_root: Path, managed: Path, agent_type: str
) -> None:
    text = _received(plugin_root, managed, agent_type)

    assert _core_units_in(text) == [True] * 3
    assert _GIT_CONVENTIONS_MARKER not in text
    assert _ROUTING_MARKER not in text
    assert _BIG_UNIT_MARKER not in text  # managed-only, but not a core unit


@pytest.mark.parametrize("agent_type", ["Explore", "Plan", _LEAN_ROLE])
def test_a_spawn_without_instruction_files_receives_nothing_in_a_managed_scope(
    plugin_root: Path, managed: Path, agent_type: str
) -> None:
    assert _received(plugin_root, managed, agent_type).strip() == ""


@pytest.mark.parametrize(
    "agent_type", [_INHERITING_ROLE, _HOST_NATIVE, "Explore", "Plan", _LEAN_ROLE, _CUSTOM]
)
def test_no_spawn_in_an_unmanaged_scope_receives_anything(
    plugin_root: Path, unmanaged: Path, agent_type: str
) -> None:
    assert _received(plugin_root, unmanaged, agent_type).strip() == ""


def test_a_custom_agent_whose_definition_cannot_be_read_counts_as_inheriting(
    plugin_root: Path, managed: Path
) -> None:
    (managed / ".claude" / "agents" / f"{_CUSTOM}.md").mkdir(parents=True)

    assert _core_units_in(_received(plugin_root, managed, _CUSTOM)) == [True] * 3


def test_a_custom_agent_with_no_definition_counts_as_inheriting(
    plugin_root: Path, managed: Path
) -> None:
    assert _core_units_in(_received(plugin_root, managed, _CUSTOM)) == [True] * 3


@pytest.mark.parametrize("where", ["project", "user"])
def test_a_custom_agent_whose_definition_omits_the_instruction_files_receives_nothing(
    plugin_root: Path, managed: Path, where: str
) -> None:
    home = managed / ".claude" if where == "project" else plugin_root / "home" / ".claude"
    _write_definition(home, _CUSTOM, _LEAN_FRONTMATTER.format(name=_CUSTOM))

    assert _received(plugin_root, managed, _CUSTOM).strip() == ""


def test_the_projects_definition_wins_over_the_users(plugin_root: Path, managed: Path) -> None:
    _write_definition(managed / ".claude", _CUSTOM, _INHERITING_FRONTMATTER.format(name=_CUSTOM))
    _write_definition(
        plugin_root / "home" / ".claude", _CUSTOM, _LEAN_FRONTMATTER.format(name=_CUSTOM)
    )

    assert _core_units_in(_received(plugin_root, managed, _CUSTOM)) == [True] * 3


def test_a_subdirectory_spawn_reads_the_managed_roots_definition_after_its_own(
    plugin_root: Path, tmp_path: Path
) -> None:
    root, subdirectory = _managed_root(tmp_path)
    _write_definition(root / ".claude", _CUSTOM, _LEAN_FRONTMATTER.format(name=_CUSTOM))
    lean_from_the_root = _received(plugin_root, subdirectory, _CUSTOM)
    _write_definition(
        subdirectory / ".claude", _CUSTOM, _INHERITING_FRONTMATTER.format(name=_CUSTOM)
    )

    assert lean_from_the_root.strip() == ""
    assert _core_units_in(_received(plugin_root, subdirectory, _CUSTOM)) == [True] * 3


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through a 0-mode directory")
def test_a_definition_behind_an_unreadable_directory_counts_as_inheriting(
    plugin_root: Path, managed: Path
) -> None:
    agents = managed / ".claude" / "agents"
    _write_definition(managed / ".claude", _CUSTOM, _LEAN_FRONTMATTER.format(name=_CUSTOM))
    agents.chmod(0)
    try:
        received = _received(plugin_root, managed, _CUSTOM)
    finally:
        agents.chmod(0o755)

    assert _core_units_in(received) == [True] * 3


def test_another_plugins_agent_is_never_read_from_this_plugins_definitions(
    plugin_root: Path, managed: Path
) -> None:
    assert _core_units_in(_received(plugin_root, managed, "other:researcher")) == [True] * 3


# -- The slots ---------------------------------------------------------------------------


def test_a_spawns_slots_print_labelled_core_parts_for_subagent_start_then_nothing(
    plugin_root: Path, managed: Path
) -> None:
    outputs = _slot_outputs(plugin_root, managed, _INHERITING_ROLE)
    printed = [output for output in outputs if output]
    labels = [_labelled_unit(output["additionalContext"]) for output in printed]

    assert outputs[: len(printed)] == printed
    assert labels == list(_CORE_UNIT_IDS)
    assert {output["hookEventName"] for output in printed} == {"SubagentStart"}


def test_before_the_flip_no_spawn_receives_anything(tmp_path: Path, managed: Path) -> None:
    _make_manifest(tmp_path)  # today's manifest: the core units are linked, none managed-only

    assert _received(tmp_path, managed, _HOST_NATIVE).strip() == ""


def test_a_spawn_writes_nothing_and_logs_no_summary(plugin_root: Path, managed: Path) -> None:
    _write_project_config(managed, "version: 1\ndisable: [ml/*]\n")

    result = _spawn(plugin_root, managed, _INHERITING_ROLE, "--slot", "1")

    assert not (managed / ".claude" / "settings.json").exists()
    assert "injected" not in result.stderr


def test_a_spawn_places_no_template_where_its_session_would(
    plugin_root: Path, managed: Path
) -> None:
    source = plugin_root / "claude" / "config" / _TEMPLATE.name
    source.parent.mkdir(parents=True)
    source.write_text("version: 1\ndisable: []\n", encoding="utf-8")

    _spawn(plugin_root, managed, _INHERITING_ROLE, "--slot", "1")
    placed_by_the_spawn = (managed / _TEMPLATE).exists()
    _run_hook(plugin_root, managed)

    assert not placed_by_the_spawn
    assert (managed / _TEMPLATE).exists()  # the control: the session does place it


# -- The impaired floor -----------------------------------------------------------------


@pytest.mark.parametrize("impairment", ["kill-switch", "manifest-missing"])
def test_an_impaired_injection_still_gives_an_inheriting_managed_spawn_its_core_units(
    plugin_root: Path, managed: Path, unmanaged: Path, impairment: str
) -> None:
    env = {"PRAXION_DISABLE_RULE_INJECTION": "1"} if impairment == "kill-switch" else {}
    if impairment == "manifest-missing":
        (plugin_root / "rules" / "_manifest.yaml").unlink()

    inheriting = _received(plugin_root, managed, _HOST_NATIVE, env=env)

    assert _core_units_in(inheriting) == [True] * 3
    assert "Praxion rule injection skipped" not in inheriting  # its session is told, once
    assert _received(plugin_root, managed, "Explore", env=env).strip() == ""
    assert _received(plugin_root, unmanaged, _HOST_NATIVE, env=env).strip() == ""


# -- Reading a definition's flag ---------------------------------------------------------


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ("omitClaudeMd: true", True),
        ("omitClaudeMd: true  # lean since the trial", True),
        ("omitClaudeMd: True", False),
        ("omitClaudeMd: TRUE", False),
        ("omitClaudeMd: yes", False),
        ("omitClaudeMd: false", False),
        ('omitClaudeMd: "true"', False),
        ("omitClaudeMd: true\nomitClaudeMd: false", False),
        ("omitClaudeMd: false\nomitClaudeMd: true", True),
        ("description: omitClaudeMd: true", False),
        ("model: sonnet", False),
    ],
)
def test_the_flag_is_set_only_by_the_literal_true_the_last_duplicate_winning(
    tmp_path: Path, frontmatter: str, expected: bool
) -> None:
    definition = tmp_path / "agent.md"
    definition.write_text(f"---\nname: agent\n{frontmatter}\n---\n\nBody.\n")

    assert _import_hook_module()._omits_claude_md((definition,)) is expected


@pytest.mark.parametrize(
    "value",
    ["true", "true  # lean", "True", "TRUE", "yes", "false", '"true"', "true\nomitClaudeMd: no"],
)
def test_the_hook_and_the_commit_gate_read_the_flag_alike(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.syspath_prepend(str(_SCRIPTS))
    import kernel_ledger_checks as gate

    text = f"---\nname: agent\nomitClaudeMd: {value}\n---\n\nBody.\n"
    definition = tmp_path / "agent.md"
    definition.write_text(text)

    gate_sets = gate.omit_flags({"agent": text}).get("agent") == gate.OMIT_SET
    assert _import_hook_module()._omits_claude_md((definition,)) is gate_sets


def test_a_flag_outside_the_frontmatter_or_no_frontmatter_is_not_a_reading(
    tmp_path: Path,
) -> None:
    in_body = tmp_path / "in-body.md"
    in_body.write_text("---\nname: agent\n---\n\nomitClaudeMd: true\n")
    bare = tmp_path / "bare.md"
    bare.write_text("omitClaudeMd: true\n")
    module = _import_hook_module()

    assert module._omits_claude_md((in_body,)) is False
    assert module._omits_claude_md((bare,)) is None


@pytest.mark.parametrize("agent_type", ["../researcher", "praxion:../researcher", "praxion:", ""])
def test_a_name_that_is_not_a_file_name_has_no_definition(
    plugin_root: Path, agent_type: str
) -> None:
    module = _import_hook_module()

    scope = module.scope_of(str(plugin_root))

    assert module._definition_candidates(agent_type, plugin_root, plugin_root, scope) == ()
