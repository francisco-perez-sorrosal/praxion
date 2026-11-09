"""What a split recipient receives at `SubagentStart`: each core unit as its stored split text
when the spawn-split artifact is trusted for it, else whole.

A unit's split is trusted only when the artifact parses and three digests agree: the unit's
current body, the audience manifest's bytes and the stored text. Each unit is judged alone, so
one stale unit costs only its own split. The impaired floor (kill switch, no PyYAML, a damaged
rules manifest) applies the same split. The main session and every whole recipient receive the
units whole, whatever the artifact holds.

The hook runs as a subprocess against the synthetic plugin tree of `test_inject_rules.py`,
flipped as in `test_inject_rules_subagent.py`, with an audience manifest and an artifact cut
from its own core bodies.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_inject_rules import (  # noqa: E402
    HOOK_SCRIPT,
    _additional_context,
    _hook_env,
    _make_manifest,
    _managed_root,
)
from test_rule_delivery_slots import (  # noqa: E402
    _CORE_UNIT_IDS,
    _IMPAIRMENTS,
    _LABEL,
    _add_managed_core_rows,
    _core_body,
    _impair,
)

_REPO = Path(__file__).resolve().parent.parent
_ARTIFACT = "claude/kernels/spawn_split.json"
_AUDIENCE = "rules/_audience.yaml"
_AUDIENCE_BYTES = b"version: 1\nentries: []\n"
_SPLIT_UNIT_IDS = ("swe/swe-agent-coordination-protocol", "swe/agent-intermediate-documents")
_PROTOCOL, _DOCUMENTS = _SPLIT_UNIT_IDS
_ADR_RESIDENT = "swe/adr-conventions-resident"
_SPLIT_RECIPIENT = "praxion:systems-architect"
_WRONG_DIGEST = "0" * 64
_SLOT_CEILING = 16  # well past any plan here; probing stops at the first empty slot
_INHERITING_FRONTMATTER = "---\nname: {name}\ndescription: x\n---\n\nBody.\n"


def _sha256(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _split_text(unit_id: str) -> str:
    return f"## {unit_id} (split text)\n"


def _core_file(plugin_root: Path, unit_id: str) -> Path:
    return plugin_root / "rules" / f"{unit_id}.md"


def _valid_wire(plugin_root: Path) -> dict:
    """The artifact the generator would write for this plugin: both split units, current."""
    units = {}
    for unit_id in _SPLIT_UNIT_IDS:
        body = _core_file(plugin_root, unit_id).read_text(encoding="utf-8")
        text = _split_text(unit_id)
        units[unit_id] = {
            "source": f"rules/{unit_id}.md",
            "whole_sha256": _sha256(body),
            "text": text,
            "text_sha256": _sha256(text),
        }
    audience = (plugin_root / _AUDIENCE).read_bytes()
    return {"schema": 1, "manifest_sha256": _sha256(audience), "units": units}


def _write_artifact(plugin_root: Path, wire: dict) -> None:
    (plugin_root / _ARTIFACT).write_text(json.dumps(wire), encoding="utf-8")


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """The flipped synthetic plugin with one plugin role that keeps the instruction files,
    an audience manifest and a trusted artifact for both split units."""
    _make_manifest(tmp_path)
    _add_managed_core_rows(tmp_path)
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "systems-architect.md").write_text(
        _INHERITING_FRONTMATTER.format(name="systems-architect")
    )
    (tmp_path / _AUDIENCE).write_bytes(_AUDIENCE_BYTES)
    (tmp_path / _ARTIFACT).parent.mkdir(parents=True)
    _write_artifact(tmp_path, _valid_wire(tmp_path))
    return tmp_path


@pytest.fixture
def managed(tmp_path: Path) -> Path:
    root, _ = _managed_root(tmp_path)
    return root


def _slot(plugin_root: Path, cwd: Path, payload: dict, slot: int, impairment: str) -> str:
    """One slot's additionalContext, the hook run as the harness runs it; `no-yaml` hides PyYAML."""
    block_yaml = "sys.modules['yaml'] = None; " if impairment == "no-yaml" else ""
    launcher = (
        f"import runpy, sys; {block_yaml}sys.argv = [{str(HOOK_SCRIPT)!r}, '--slot', '{slot}']; "
        f"sys.path.insert(0, {str(HOOK_SCRIPT.parent)!r}); "
        f"runpy.run_path({str(HOOK_SCRIPT)!r}, run_name='__main__')"
    )
    env = _hook_env(plugin_root)
    if impairment == "kill-switch":
        env["PRAXION_DISABLE_RULE_INJECTION"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", launcher],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return _additional_context(result)


def _received_units(
    plugin_root: Path, cwd: Path, agent_type: str | None, impairment: str = ""
) -> dict[str, str]:
    """Each unit's chunks joined in slot order, keyed by unit in delivery order; a session
    (`agent_type` None) leaves its unlabelled notice out."""
    if impairment and impairment not in ("kill-switch", "no-yaml"):
        _impair(plugin_root, impairment)
    payload = {"session_id": "s", "cwd": str(cwd)}
    if agent_type is not None:
        payload |= {"hook_event_name": "SubagentStart", "agent_type": agent_type}
    units: dict[str, str] = {}
    for slot in range(1, _SLOT_CEILING + 1):
        text = _slot(plugin_root, cwd, payload, slot, impairment)
        if not text:
            break
        label = _LABEL.match(text)
        if label:
            units[label.group(1)] = units.get(label.group(1), "") + text[label.end() :]
    return units


def _whole(unit_id: str) -> str:
    return _core_body(unit_id) + "\n"


def _as_split(units: dict[str, str]) -> list[str]:
    """For each split unit, `split`, `whole` or what else it arrived as."""
    readings = []
    for unit_id in _SPLIT_UNIT_IDS:
        text = units.get(unit_id)
        readings.append(
            "split"
            if text == _split_text(unit_id)
            else "whole"
            if text == _whole(unit_id)
            else text
        )
    return readings


# -- A trusted artifact -------------------------------------------------------------------


def test_a_split_recipient_receives_each_split_unit_as_its_stored_split_text(
    plugin_root: Path, managed: Path
) -> None:
    units = _received_units(plugin_root, managed, _SPLIT_RECIPIENT)

    assert list(units) == list(_CORE_UNIT_IDS)
    assert _as_split(units) == ["split", "split"]
    assert units[_ADR_RESIDENT] == _whole(_ADR_RESIDENT)


@pytest.mark.parametrize("agent_type", [None, "general-purpose", "custom-reviewer"])
def test_the_main_session_and_every_whole_recipient_receive_the_units_whole(
    plugin_root: Path, managed: Path, agent_type: str | None
) -> None:
    units = _received_units(plugin_root, managed, agent_type)

    assert _as_split(units) == ["whole", "whole"]


@pytest.mark.parametrize("agent_type", ["Explore", "Plan"])
def test_a_spawn_without_instruction_files_still_receives_nothing(
    plugin_root: Path, managed: Path, agent_type: str
) -> None:
    assert _received_units(plugin_root, managed, agent_type) == {}


def test_an_unmanaged_split_recipient_still_receives_nothing(
    plugin_root: Path, tmp_path: Path
) -> None:
    project = tmp_path / "plain"
    project.mkdir()

    assert _received_units(plugin_root, project, _SPLIT_RECIPIENT) == {}


# -- An artifact that cannot be trusted ---------------------------------------------------


def _unreadable(path: Path) -> None:
    path.unlink()
    path.mkdir()


ARTIFACT_DAMAGE = {
    "absent": lambda path: path.unlink(),
    "a-directory": _unreadable,
    "not-json": lambda path: path.write_text("{not json", encoding="utf-8"),
    "not-utf8": lambda path: path.write_bytes(b"\xff\xfe{}"),
    "nested-past-the-parser": lambda path: path.write_text("[" * 100_000, encoding="utf-8"),
    "a-list": lambda path: path.write_text("[]", encoding="utf-8"),
    "another-schema": lambda path: path.write_text(
        path.read_text(encoding="utf-8").replace('"schema": 1', '"schema": 2'), encoding="utf-8"
    ),
}


@pytest.mark.parametrize("damage", ARTIFACT_DAMAGE)
def test_an_artifact_that_cannot_be_read_or_parsed_leaves_each_unit_whole(
    plugin_root: Path, managed: Path, damage: str
) -> None:
    ARTIFACT_DAMAGE[damage](plugin_root / _ARTIFACT)

    units = _received_units(plugin_root, managed, _SPLIT_RECIPIENT)

    assert list(units) == list(_CORE_UNIT_IDS)
    assert _as_split(units) == ["whole", "whole"]


def test_an_artifact_cut_under_another_audience_manifest_leaves_each_unit_whole(
    plugin_root: Path, managed: Path
) -> None:
    wire = _valid_wire(plugin_root)
    wire["manifest_sha256"] = _WRONG_DIGEST
    _write_artifact(plugin_root, wire)

    assert _as_split(_received_units(plugin_root, managed, _SPLIT_RECIPIENT)) == ["whole", "whole"]


@pytest.mark.parametrize("digest", ["whole_sha256", "text_sha256"])
def test_a_wrong_unit_digest_leaves_that_unit_whole_and_the_other_split(
    plugin_root: Path, managed: Path, digest: str
) -> None:
    wire = _valid_wire(plugin_root)
    wire["units"][_PROTOCOL][digest] = _WRONG_DIGEST
    _write_artifact(plugin_root, wire)

    assert _as_split(_received_units(plugin_root, managed, _SPLIT_RECIPIENT)) == ["whole", "split"]


def test_a_rule_edited_after_the_split_arrives_whole_while_the_other_keeps_its_split(
    plugin_root: Path, managed: Path
) -> None:
    edited = _core_file(plugin_root, _DOCUMENTS)
    edited.write_text(edited.read_text(encoding="utf-8") + "\nA later line.\n", encoding="utf-8")

    units = _received_units(plugin_root, managed, _SPLIT_RECIPIENT)

    assert units[_PROTOCOL] == _split_text(_PROTOCOL)
    assert units[_DOCUMENTS] == _whole(_DOCUMENTS) + "\nA later line.\n"


@pytest.mark.parametrize("change", ["edited", "absent", "a-directory"])
def test_an_audience_manifest_changed_or_unreadable_leaves_each_unit_whole(
    plugin_root: Path, managed: Path, change: str
) -> None:
    audience = plugin_root / _AUDIENCE
    if change == "edited":
        audience.write_bytes(_AUDIENCE_BYTES + b"# a later comment\n")
    elif change == "absent":
        audience.unlink()
    else:
        _unreadable(audience)

    assert _as_split(_received_units(plugin_root, managed, _SPLIT_RECIPIENT)) == ["whole", "whole"]


# -- The impaired floor -------------------------------------------------------------------


@pytest.mark.parametrize("impairment", _IMPAIRMENTS)
def test_a_split_recipient_on_the_impaired_floor_still_receives_the_split(
    plugin_root: Path, managed: Path, impairment: str
) -> None:
    units = _received_units(plugin_root, managed, _SPLIT_RECIPIENT, impairment)

    assert list(units) == list(_CORE_UNIT_IDS)
    assert _as_split(units) == ["split", "split"]
    assert units[_ADR_RESIDENT] == _whole(_ADR_RESIDENT)


@pytest.mark.parametrize("impairment", ["kill-switch", "manifest-missing"])
def test_a_whole_recipient_on_the_impaired_floor_still_receives_the_units_whole(
    plugin_root: Path, managed: Path, impairment: str
) -> None:
    units = _received_units(plugin_root, managed, "general-purpose", impairment)

    assert _as_split(units) == ["whole", "whole"]


# -- The shipped files, read from a plugin root ---------------------------------------------


def test_the_shipped_artifact_is_trusted_for_the_shipped_rules_read_from_the_plugin_root(
    plugin_root: Path, managed: Path
) -> None:
    """The generator and the hook digest the same bytes: with this checkout's rules, audience
    manifest and artifact copied under another plugin root, each unit arrives as its split."""
    for rel in (*(f"rules/{unit_id}.md" for unit_id in _SPLIT_UNIT_IDS), _AUDIENCE, _ARTIFACT):
        shutil.copyfile(_REPO / rel, plugin_root / rel)
    shipped = json.loads((_REPO / _ARTIFACT).read_text(encoding="utf-8"))["units"]

    units = _received_units(plugin_root, managed, _SPLIT_RECIPIENT)

    assert [units[unit_id] for unit_id in _SPLIT_UNIT_IDS] == [
        shipped[unit_id]["text"] for unit_id in _SPLIT_UNIT_IDS
    ]
