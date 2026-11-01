"""Tests and canaries for the spawn-model check (``scripts/check_spawn_models.py``).

The pure classification is driven with built ``Spawn`` values; the command line is driven over a
directory of transcripts written in the layout Claude Code records.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_spawn_models as csm  # noqa: E402
from spawn_transcripts import Spawn  # noqa: E402

REPO_ROOT = SCRIPT_DIR.parent
SESSION = "5e55a1b2-0000-4000-8000-000000000001"
FLOORS = {
    "systems-architect": "opus",
    "implementer": "sonnet",
    "verifier": "opus",
    "researcher": "sonnet",
    "test-engineer": "sonnet",
    "discipline-consultant": "sonnet",
    "doc-engineer": "claude-haiku-4-5",
}


def spawn(role, ran=None, requested=None, markers=(), agent_id="a1", session=SESSION) -> Spawn:
    return Spawn(session, agent_id, role, requested, ran, frozenset(markers))


def verdict_of(target: Spawn, *others: Spawn) -> str:
    return csm.classify(target, [target, *others], FLOORS)[0]


def steady_pair() -> tuple[Spawn, Spawn]:
    """Two spawns at their floors on different families, so no session reads as one pinned model."""
    return (
        spawn("systems-architect", ran="claude-opus-5-5", agent_id="s1"),
        spawn("implementer", ran="claude-sonnet-5-5", agent_id="s2"),
    )


# -- model families -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("opus", "opus"),
        ("claude-opus-5-5", "opus"),
        ("sonnet", "sonnet"),
        ("claude-sonnet-5-5", "sonnet"),
        ("claude-haiku-4-5", "claude-haiku-4-5"),
        ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
        ("haiku", "haiku-3.5"),
        ("claude-3-5-haiku-20241022", "haiku-3.5"),
        ("something-new", "something-new"),
    ],
)
def test_a_model_name_maps_to_its_family(model, family):
    assert csm.model_family(model) == family


def test_the_bare_haiku_alias_never_matches_the_pinned_haiku():
    assert csm.model_family("haiku") != csm.model_family("claude-haiku-4-5-20251001")


# -- classification -------------------------------------------------------------------------------


def test_a_spawn_on_its_floor_family_is_floor():
    assert verdict_of(spawn("implementer", ran="claude-sonnet-5-5")) == "floor"


def test_a_spawn_on_the_pinned_low_tier_floor_is_floor():
    assert verdict_of(spawn("doc-engineer", ran="claude-haiku-4-5-20251001")) == "floor"


def test_the_bare_haiku_alias_landing_on_the_old_family_is_not_the_pinned_floor():
    landed = spawn("doc-engineer", ran="claude-3-5-haiku-20241022", requested="haiku")
    steady = spawn("implementer", ran="claude-sonnet-5-5", agent_id="a2")

    assert verdict_of(landed, steady) == "unexplained"


def test_a_missing_ran_model_is_unknown():
    assert verdict_of(spawn("implementer", ran=None)) == "unknown"


def test_a_role_with_no_definition_is_unknown():
    assert verdict_of(spawn("ghost", ran="opus")) == "unknown"


def test_a_request_that_contradicts_the_floor_blocks_floor_even_when_it_ran_there():
    drifted = spawn("verifier", ran="claude-opus-5-5", requested="sonnet")
    steady = spawn("implementer", ran="claude-sonnet-5-5", agent_id="a2")

    assert verdict_of(drifted, steady) == "unexplained"


@pytest.mark.parametrize(
    "target",
    [
        spawn("researcher", ran="claude-opus-5-5", requested="opus"),
        spawn("researcher", ran="claude-haiku-4-5-20251001", requested="claude-haiku-4-5"),
        spawn(
            "discipline-consultant",
            ran="claude-opus-5-5",
            requested="opus",
            markers=["Mode: light-review"],
        ),
        spawn(
            "test-engineer",
            ran="claude-opus-5-5",
            requested="opus",
            markers=["Mode: acceptance-design"],
        ),
        spawn(
            "verifier", ran="claude-sonnet-5-5", requested="sonnet", markers=["Mode: light-review"]
        ),
        spawn("implementer", ran="claude-opus-5-5", requested="opus", markers=["tier: H"]),
        spawn(
            "implementer",
            ran="claude-haiku-4-5-20251001",
            requested="claude-haiku-4-5",
            markers=["tier: L"],
        ),
    ],
    ids=lambda s: f"{s.role}-{s.requested_model}",
)
def test_a_listed_deviation_that_ran_as_requested_is_an_override(target):
    assert verdict_of(target, *steady_pair()) == "override"


@pytest.mark.parametrize(
    "target",
    [
        spawn(
            "discipline-consultant", ran="claude-opus-5-5", requested="opus", markers=["routine"]
        ),
        spawn("test-engineer", ran="claude-opus-5-5", requested="opus"),
        spawn("verifier", ran="claude-sonnet-5-5", requested="sonnet"),
        spawn("implementer", ran="claude-opus-5-5", requested="opus"),
        spawn("implementer", ran="claude-opus-5-5", requested="opus", markers=["tier: L"]),
        spawn("systems-architect", ran="claude-sonnet-5-5", requested="sonnet"),
    ],
    ids=lambda s: f"{s.role}-{s.requested_model}-{sorted(s.prompt_markers)}",
)
def test_a_per_spawn_model_the_directive_does_not_list_is_unexplained(target):
    assert verdict_of(target, *steady_pair()) == "unexplained"


def test_a_listed_deviation_that_ran_elsewhere_than_requested_is_not_an_override():
    target = spawn("researcher", ran="claude-sonnet-5-5", requested="opus")

    assert verdict_of(target, *steady_pair()) == "unexplained"


def test_the_lone_spawn_off_its_floor_is_unknown_not_unexplained():
    assert verdict_of(spawn("verifier", ran="claude-sonnet-5-5")) == "unknown"


def test_a_session_on_one_model_with_differing_floors_is_the_kill_switch():
    pinned = "claude-haiku-4-5-20251001"
    spawns = [
        spawn("systems-architect", ran=pinned, agent_id="a1"),
        spawn("implementer", ran=pinned, agent_id="a2"),
    ]

    assert [csm.classify(s, spawns, FLOORS)[0] for s in spawns] == ["override", "override"]


def test_a_session_on_one_model_whose_floors_agree_is_not_the_kill_switch():
    spawns = [
        spawn("systems-architect", ran="claude-sonnet-5-5", agent_id="a1"),
        spawn("verifier", ran="claude-sonnet-5-5", agent_id="a2"),
    ]

    assert [csm.classify(s, spawns, FLOORS)[0] for s in spawns] == ["unexplained"] * 2


def test_the_kill_switch_is_judged_per_session():
    other = spawn("implementer", ran="claude-haiku-4-5-20251001", session="other", agent_id="b1")
    mine = spawn("verifier", ran="claude-haiku-4-5-20251001", agent_id="a1")
    steady = spawn("implementer", ran="claude-sonnet-5-5", agent_id="a2")

    judged = csm.judge([mine, steady, other], FLOORS)

    assert [v for _, v, _ in judged] == ["unexplained", "floor", "unknown"]


def test_classification_only_returns_closed_verdicts():
    target = spawn("verifier", ran="claude-sonnet-5-5")

    assert csm.classify(target, [target], FLOORS)[0] in csm.VERDICTS


# -- command line ---------------------------------------------------------------------------------


def _record(directory: Path, spawns: list[Spawn]) -> None:
    lines = []
    for item in spawns:
        use_id = f"toolu_{item.agent_id}"
        call = {"subagent_type": f"praxion:{item.role}", "prompt": "Do the step."}
        if item.requested_model:
            call["model"] = item.requested_model
        block = {"type": "tool_use", "id": use_id, "name": "Agent", "input": call}
        lines.append({"type": "assistant", "message": {"role": "assistant", "content": [block]}})
        result = {"type": "tool_result", "tool_use_id": use_id}
        lines.append(
            {
                "type": "user",
                "message": {"role": "user", "content": [result]},
                "toolUseResult": {"agentId": item.agent_id},
            }
        )
        if item.ran_model:
            own = directory / SESSION / "subagents" / f"agent-{item.agent_id}.jsonl"
            own.parent.mkdir(parents=True, exist_ok=True)
            reply = {"role": "assistant", "model": item.ran_model, "content": []}
            own.write_text(json.dumps({"type": "assistant", "message": reply}) + "\n")
    (directory / f"{SESSION}.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_spawn_models.py"), *argv],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _repo_floor(role: str) -> str:
    return {"implementer": "claude-sonnet-5-5", "systems-architect": "claude-opus-5-5"}[role]


def test_an_unexplained_spawn_exits_one(tmp_path):
    _record(
        tmp_path,
        [
            spawn("implementer", ran=_repo_floor("implementer"), agent_id="a1"),
            spawn("systems-architect", ran="claude-haiku-4-5-20251001", agent_id="a2"),
        ],
    )

    result = _run(str(tmp_path), "--repo-root", str(REPO_ROOT))

    assert result.returncode == 1, result.stderr
    assert "a2  systems-architect  unexplained" in result.stdout


def test_a_run_of_unknown_spawns_only_exits_zero_and_reports_them(tmp_path):
    _record(tmp_path, [spawn("implementer", ran=None)])

    result = _run(str(tmp_path), "--repo-root", str(REPO_ROOT))

    assert result.returncode == 0, result.stderr
    assert "a1  implementer  unknown" in result.stdout
    assert "unknown=1" in result.stdout.splitlines()[-1]


def test_a_missing_transcripts_directory_exits_two(tmp_path):
    result = _run(str(tmp_path / "absent"), "--repo-root", str(REPO_ROOT))

    assert result.returncode == 2
    assert "cannot read the inputs" in result.stderr


def test_a_checkout_without_agent_definitions_exits_two(tmp_path):
    (tmp_path / "transcripts").mkdir()

    result = _run(str(tmp_path / "transcripts"), "--repo-root", str(tmp_path))

    assert result.returncode == 2


def test_json_output_has_the_documented_shape(tmp_path):
    _record(tmp_path, [spawn("implementer", ran=_repo_floor("implementer"))])

    result = _run(str(tmp_path), "--repo-root", str(REPO_ROOT), "--json")

    payload = json.loads(result.stdout)
    assert payload["schema"] == 1
    assert set(payload["counts"]) == set(csm.VERDICTS)
    assert payload["counts"]["floor"] == 1
    assert set(payload["spawns"][0]) == {
        "session",
        "agent_id",
        "role",
        "requested_model",
        "ran_model",
        "verdict",
        "reason",
    }


def test_the_module_launches_no_subprocess(tmp_path, monkeypatch):
    _record(tmp_path, [spawn("implementer", ran=_repo_floor("implementer"))])

    def refuse(*args, **kwargs):
        raise AssertionError("the check must start no process")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)

    assert csm.main([str(tmp_path), "--repo-root", str(REPO_ROOT)]) == 0
    source = (SCRIPT_DIR / "check_spawn_models.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "os.system" not in source


def test_the_sanctioned_roles_are_agents_the_repository_defines():
    floors = csm.read_floors(REPO_ROOT)

    assert set(csm.SANCTIONED) <= set(floors)
