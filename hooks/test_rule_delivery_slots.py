"""The rule injector is registered with room for its largest delivery and a spare slot.

Each registered `inject_rules.py --slot N` prints one part of the plan, so a plan
with more parts than slots would lose its tail without a word. These tests count
the parts of the largest delivery the injector can plan (every hook-delivered
unit and every managed core unit, in a managed scope), read with the injector's
own readers, and hold the registered slots at that count plus one: a growing rule
fails here instead of being dropped.

The slot mode itself is tested here too, by running the hook against the synthetic
plugin tree of `test_inject_rules.py`: the parts the slots print, the floor an
impaired injection still delivers, and the units a user-scope link already loads.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _rule_blacklist  # noqa: E402
import inject_rules  # noqa: E402
from _project_scope import Managed  # noqa: E402
from _rule_delivery import MANAGED_CORE_UNITS, AgentKind, Event, plan_delivery  # noqa: E402
from test_inject_rules import (  # noqa: E402
    _GIT_CONVENTIONS_BODY,
    _GIT_CONVENTIONS_MARKER,
    _ROUTING_MARKER,
    HOOK_SCRIPT,
    _additional_context,
    _hook_env,
    _import_hook_module,
    _make_manifest,
    _managed_root,
    _write_project_config,
)

REPO_ROOT = next(
    root
    for root in Path(__file__).resolve().parents
    if (root / "rules" / "_manifest.yaml").is_file()
)
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
INJECTOR_COMMAND = "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/inject_rules.py"
EVENTS = {"SessionStart": Event.SESSION, "SubagentStart": Event.SUBAGENT}
SPARE_SLOTS = 1
SESSION_START_TIMEOUT = 15
MANAGED = Managed(REPO_ROOT, REPO_ROOT / ".ai-state")


def _injector_hooks(event: str) -> list[dict]:
    groups = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"].get(event, [])
    return [
        hook
        for group in groups
        for hook in group["hooks"]
        if hook.get("command", "").startswith(INJECTOR_COMMAND)
    ]


def _slots(event: str) -> list[int]:
    prefix = f"{INJECTOR_COMMAND} {inject_rules.SLOT_FLAG} "
    return [int(hook["command"].removeprefix(prefix)) for hook in _injector_hooks(event)]


def _largest_supply() -> dict[str, str]:
    """Every unit the injector can deliver, as it reads them: hook-deliver rows and the floor."""
    units, _ = inject_rules._hook_delivered_units(inject_rules._load_manifest(REPO_ROOT), REPO_ROOT)
    for unit in MANAGED_CORE_UNITS:
        units[unit.unit_id] = inject_rules._read_rule_body(REPO_ROOT, unit.path)
    return units


def _strings_needed(units: dict[str, str], event: Event) -> int:
    """The most strings one delivery prints: the whole managed plan, or the floor and its notice."""
    plan = plan_delivery(units, set(units), MANAGED, event, AgentKind.INHERITING, set(), set())
    core = {unit.unit_id for unit in MANAGED_CORE_UNITS}
    floor = [part for part in plan if part.unit_id in core]
    return max(len(plan), len(floor) + 1)


def _has_room(event: str, units: dict[str, str]) -> bool:
    return len(_slots(event)) >= _strings_needed(units, EVENTS[event]) + SPARE_SLOTS


REGISTERED_EVENTS = [event for event in EVENTS if _injector_hooks(event)]


def test_the_injector_is_registered_at_session_start_and_at_no_unknown_event():
    groups = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    found = {event for event in groups if _injector_hooks(event)}

    assert "SessionStart" in found
    assert found <= set(EVENTS)


@pytest.mark.parametrize("event", REGISTERED_EVENTS)
def test_every_event_has_a_slot_per_part_of_its_largest_delivery_and_a_spare(event):
    assert _has_room(event, _largest_supply()), (
        f"{event}: {len(_slots(event))} slots registered, "
        f"{_strings_needed(_largest_supply(), EVENTS[event])} strings needed plus {SPARE_SLOTS}"
    )


@pytest.mark.parametrize("event", REGISTERED_EVENTS)
def test_an_oversize_unit_leaves_the_registered_slots_short(event):
    section = "## Section\n\n" + "x" * 78 + "\n\n"
    units = {**_largest_supply(), "swe/oversize": section * 1_000}
    if event == "SubagentStart":  # a spawn plans only managed core units
        pytest.skip("the canary unit is not a core unit, so a spawn never plans it")

    assert not _has_room(event, units)


@pytest.mark.parametrize("event", REGISTERED_EVENTS)
def test_every_slot_is_registered_once_in_order_and_nothing_runs_without_a_slot(event):
    hooks = _injector_hooks(event)

    assert _slots(event) == list(range(1, len(hooks) + 1))
    assert all(f" {inject_rules.SLOT_FLAG} " in hook["command"] for hook in hooks)


def test_the_session_start_slots_keep_the_injectors_place_and_timeout():
    group = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["SessionStart"][0]
    commands = [hook["command"] for hook in group["hooks"]]
    first = commands.index(f"{INJECTOR_COMMAND} {inject_rules.SLOT_FLAG} 1")
    slots = len(_slots("SessionStart"))

    assert commands[first - 1].endswith("/hooks/inject_decisions.py")
    assert commands[first + slots].endswith("/hooks/surface_praxion_feedback.py")
    assert all(
        hook["timeout"] == SESSION_START_TIMEOUT and hook["async"] is False
        for hook in _injector_hooks("SessionStart")
    )


# ===========================================================================
# Slots, the impaired floor and units still linked at user scope
# ===========================================================================


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """The synthetic plugin tree `test_inject_rules.py` runs the hook against."""
    _make_manifest(tmp_path)
    return tmp_path


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """An unmanaged start directory with no blacklist."""
    project = tmp_path / "project"
    project.mkdir()
    return project


_CORE_UNIT_IDS = (
    "swe/swe-agent-coordination-protocol",
    "swe/agent-intermediate-documents",
    "swe/adr-conventions-resident",
)
_LABEL = re.compile(r"\A## Praxion Rules \(auto-injected\): (\S+), part (\d+) of (\d+)\n\n")
_SLOTS_PROBED = 12
_KILL_SWITCH = "PRAXION_DISABLE_RULE_INJECTION"
_KILL_SWITCH_IMPAIRMENT = "kill-switch"
_IMPAIRMENTS = (
    "kill-switch",
    "no-yaml",
    "manifest-missing",
    "manifest-unreadable",
    "manifest-not-yaml",
    "manifest-not-a-mapping",
    "row-not-a-mapping",
)
_SKIPPED_HEADER = "## Praxion rule injection skipped"


def _core_body(unit_id: str) -> str:
    return f"## {unit_id} (core rule body)"


def _impair(plugin_root: Path, impairment: str) -> dict[str, str]:
    """Impair the plugin's manifest as named; the extra variables the run needs."""
    manifest = plugin_root / "rules" / "_manifest.yaml"
    if impairment == _KILL_SWITCH_IMPAIRMENT:
        return {_KILL_SWITCH: "1"}
    if impairment == "manifest-missing":
        manifest.unlink()
    elif impairment == "manifest-unreadable":
        manifest.unlink()
        manifest.mkdir()
    elif impairment == "manifest-not-yaml":
        manifest.write_text("rules: [unterminated\n  - {id: : :\n", encoding="utf-8")
    elif impairment == "manifest-not-a-mapping":
        manifest.write_text("just a line of text\n", encoding="utf-8")
    elif impairment == "row-not-a-mapping":  # parses, then fails while it is applied
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text.replace("categories:", "- null\ncategories:", 1), encoding="utf-8")
    return {}


def _run(plugin_root: Path, cwd: Path, *args: str, impairment: str = "") -> str:
    """The hook's additionalContext for `args`, under one impairment of its injection."""
    extra = _impair(plugin_root, impairment)
    block_yaml = "sys.modules['yaml'] = None; " if impairment == "no-yaml" else ""
    launcher = (
        f"import runpy, sys; {block_yaml}sys.argv = [{str(HOOK_SCRIPT)!r}, *{list(args)!r}]; "
        f"sys.path.insert(0, {str(HOOK_SCRIPT.parent)!r}); "
        f"runpy.run_path({str(HOOK_SCRIPT)!r}, run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-c", launcher],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={**_hook_env(plugin_root), **extra},
        timeout=10,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    return _additional_context(result)


def _slot_texts(plugin_root: Path, cwd: Path) -> list[str]:
    return [_run(plugin_root, cwd, "--slot", str(n)) for n in range(1, _SLOTS_PROBED + 1)]


def _add_managed_core_rows(plugin_root: Path) -> None:
    """The flipped manifest's shape: the core units as managed-only hook-deliver rows, and
    one managed-only unit large enough to need several parts."""
    big = plugin_root / "rules" / "swe" / "big.md"
    big.write_text("".join(f"## Big {n}\n\n{'b' * 3_000}\n\n" for n in range(8)), encoding="utf-8")
    manifest = plugin_root / "rules" / "_manifest.yaml"
    text = manifest.read_text(encoding="utf-8")
    for unit_id in _CORE_UNIT_IDS:
        head = f"- id: {unit_id}\n  path: rules/{unit_id}.md\n  load: always_on\n  core: true\n"
        text = text.replace(
            head + "  install: symlink\n",
            head + "  install: hook-deliver\n  project_scope: managed\n",
        )
    row = (
        "- id: swe/big\n  path: rules/swe/big.md\n  load: always_on\n  core: false\n"
        "  install: hook-deliver\n  chars: 24000\n  project_scope: managed\n"
    )
    manifest.write_text(text.replace("categories:", row + "categories:"), encoding="utf-8")


def _link_at_user_scope(plugin_root: Path, unit_id: str, target: Path) -> None:
    link = plugin_root / "home" / ".claude" / "rules" / f"{unit_id}.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)


def _rebuilt_units(texts: list[str]) -> str:
    """Each unit's chunks joined in slot order, the units joined as the whole mode joins them."""
    labelled = [(_LABEL.match(text), text) for text in texts]
    units = dict.fromkeys(match.group(1) for match, _ in labelled)
    return "\n\n".join(
        "".join(text[match.end() :] for match, text in labelled if match.group(1) == unit_id)
        for unit_id in units
    )


def test_slots_print_disjoint_labelled_parts_whose_union_is_the_whole_plan(
    plugin_root: Path, tmp_path: Path
) -> None:
    _add_managed_core_rows(plugin_root)
    root, _ = _managed_root(tmp_path)

    texts = [text for text in _slot_texts(plugin_root, root) if text]
    places = {(_LABEL.match(text).group(1), _LABEL.match(text).group(2)) for text in texts}
    whole = _run(plugin_root, root)

    assert len(places) == len(texts) > len(_CORE_UNIT_IDS) + 3
    assert max(len(text) for text in texts) <= 10_000
    assert whole == "## Praxion Rules (auto-injected)\n\n" + _rebuilt_units(texts)


def test_a_slot_past_the_plan_prints_nothing(plugin_root: Path, project_dir: Path) -> None:
    texts = _slot_texts(plugin_root, project_dir)

    assert [bool(text) for text in texts] == [True] * 3 + [False] * (_SLOTS_PROBED - 3)


@pytest.mark.parametrize("args", [("--slot", "0"), ("--slot", "x"), ("--slot",), ("--all",)])
def test_a_malformed_argument_prints_nothing(
    plugin_root: Path, project_dir: Path, args: tuple[str, ...]
) -> None:
    assert _run(plugin_root, project_dir, *args) == ""


def test_only_the_first_slot_writes_the_exclusions(plugin_root: Path, tmp_path: Path) -> None:
    root, _ = _managed_root(tmp_path)
    _write_project_config(root, "version: 1\ndisable: [ml/*]\n")

    _run(plugin_root, root, "--slot", "2")
    written_by_slot_two = (root / ".claude" / "settings.json").exists()
    _run(plugin_root, root, "--slot", "1")

    assert not written_by_slot_two
    assert "claudeMdExcludes" in (root / ".claude" / "settings.json").read_text()


@pytest.mark.parametrize("impairment", _IMPAIRMENTS)
def test_an_impaired_injection_still_delivers_the_core_units_to_a_managed_scope(
    plugin_root: Path, tmp_path: Path, impairment: str
) -> None:
    root, _ = _managed_root(tmp_path)

    context = _run(plugin_root, root, impairment=impairment)

    assert [_core_body(unit_id) in context for unit_id in _CORE_UNIT_IDS] == [True] * 3
    assert _GIT_CONVENTIONS_MARKER not in context
    assert _ROUTING_MARKER not in context


@pytest.mark.parametrize("impairment", _IMPAIRMENTS)
def test_an_impaired_injection_gives_an_unmanaged_scope_no_unit_only_the_unavailable_notice(
    plugin_root: Path, project_dir: Path, impairment: str
) -> None:
    context = _run(plugin_root, project_dir, impairment=impairment)

    assert "Praxion Rules (auto-injected)" not in context
    assert not any(_core_body(unit_id) in context for unit_id in _CORE_UNIT_IDS)
    assert (
        context == ""
        if impairment == _KILL_SWITCH_IMPAIRMENT
        else context.startswith(_SKIPPED_HEADER)
    )


def test_a_managed_scope_is_told_only_its_core_procedures_were_loaded(
    plugin_root: Path, tmp_path: Path
) -> None:
    root, _ = _managed_root(tmp_path)

    notice = _run(plugin_root, root, "--slot", "1", impairment="manifest-missing")

    assert notice.startswith(_SKIPPED_HEADER)
    assert "Only Praxion's managed core procedures were loaded this session" in notice
    assert "rules were NOT loaded this session" not in notice


def test_a_blacklist_entry_that_is_not_a_string_is_skipped_and_the_rest_applied(
    plugin_root: Path, tmp_path: Path
) -> None:
    root, _ = _managed_root(tmp_path)
    _write_project_config(root, "version: 1\ndisable:\n  -\n  - 3\n  - ml/*\n")

    context = _run(plugin_root, root)

    assert _GIT_CONVENTIONS_MARKER in context
    assert "**/.claude/rules/ml/" in (root / ".claude" / "settings.json").read_text()


def test_the_disable_patterns_keep_only_strings_and_warn_of_the_rest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _rule_blacklist.disable_patterns({"disable": [None, 3, "ml/*"]}) == ["ml/*"]
    assert "[None, 3] are not rule ids or globs; skipped" in capsys.readouterr().err


def test_an_unavailable_manifest_notice_is_the_first_slot_before_the_floor(
    plugin_root: Path, tmp_path: Path
) -> None:
    root, _ = _managed_root(tmp_path)

    texts = [
        _run(plugin_root, root, "--slot", str(n), impairment="manifest-not-a-mapping")
        for n in range(1, 6)
    ]

    assert texts[0].startswith("## Praxion rule injection skipped")
    assert [bool(text) for text in texts] == [True] * 4 + [False]


def test_a_unit_still_linked_at_user_scope_is_skipped(plugin_root: Path, tmp_path: Path) -> None:
    root, _ = _managed_root(tmp_path)
    linked = _CORE_UNIT_IDS[1]
    _link_at_user_scope(plugin_root, linked, plugin_root / "rules" / f"{linked}.md")

    floor = _run(plugin_root, root, impairment="kill-switch")
    _add_managed_core_rows(plugin_root)
    managed = _run(plugin_root, root)

    assert (_core_body(linked) in floor, _core_body(linked) in managed) == (False, False)
    assert _core_body(_CORE_UNIT_IDS[0]) in floor
    assert _core_body(_CORE_UNIT_IDS[0]) in managed


def test_a_unit_for_every_scope_still_linked_at_user_scope_stays_injected(
    plugin_root: Path, tmp_path: Path
) -> None:
    root, _ = _managed_root(tmp_path)
    linked = "swe/vcs/git-conventions"
    _link_at_user_scope(plugin_root, linked, plugin_root / "rules" / f"{linked}.md")

    assert _GIT_CONVENTIONS_BODY.strip() in _run(plugin_root, root)


def test_a_dangling_link_does_not_count_as_installed(plugin_root: Path, tmp_path: Path) -> None:
    root, _ = _managed_root(tmp_path)
    _link_at_user_scope(plugin_root, _CORE_UNIT_IDS[1], tmp_path / "missing.md")

    assert _core_body(_CORE_UNIT_IDS[1]) in _run(plugin_root, root, impairment="kill-switch")


def test_a_link_to_another_file_does_not_count_as_installed(
    plugin_root: Path, tmp_path: Path
) -> None:
    root, _ = _managed_root(tmp_path)
    other = tmp_path / "notes.md"
    other.write_text("notes\n")
    _link_at_user_scope(plugin_root, _CORE_UNIT_IDS[1], other)

    assert _core_body(_CORE_UNIT_IDS[1]) in _run(plugin_root, root, impairment="kill-switch")


def test_the_user_configuration_directory_variable_locates_the_user_scope_links(
    plugin_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    link = config / "rules" / f"{_CORE_UNIT_IDS[0]}.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(plugin_root / "rules" / f"{_CORE_UNIT_IDS[0]}.md")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    module = _import_hook_module()

    assert module._natively_installed(_CORE_UNIT_IDS) == {_CORE_UNIT_IDS[0]}


def test_no_unit_to_check_never_looks_up_the_home_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_home(cls) -> Path:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(no_home))
    module = _import_hook_module()

    assert module._natively_installed(set()) == frozenset()
    assert module._natively_installed(set(_CORE_UNIT_IDS)) == frozenset()
