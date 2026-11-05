"""A task fixture is marked managed in the sandbox copy, and its launch environment keeps the
managed-only behaviours off, unless the fixture's overlay already carried state."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from praxion_evals.adherence import managed_fixture, session_launch, tasks
from praxion_evals.adherence.model import ArmBuild, Role
from praxion_evals.adherence.session_launch import Launch

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 7
STATE = managed_fixture.STATE_DIRNAME
SWITCHES = managed_fixture.UNMANAGED_BEHAVIOUR_SWITCHES
# the architect-validator's overlay ships a `.ai-state/`; the researcher's does not
CARRYING_ROLE: Role = "architect-validator"
BARE_ROLE: Role = "researcher"


def test_a_fixture_without_state_gets_an_empty_state_directory_and_the_switches(tmp_path):
    managed_fixture.mark_managed(tmp_path)

    assert (tmp_path / STATE).is_dir()
    assert list((tmp_path / STATE).iterdir()) == []
    assert managed_fixture.switches_for(tmp_path) == SWITCHES


def test_a_fixture_already_carrying_state_is_left_as_it_was_and_adds_no_switch(tmp_path):
    (tmp_path / STATE).mkdir()
    (tmp_path / STATE / "DESIGN.md").write_text("kept", encoding="utf-8")

    managed_fixture.mark_managed(tmp_path)

    assert [p.name for p in (tmp_path / STATE).iterdir()] == ["DESIGN.md"]
    assert managed_fixture.switches_for(tmp_path) == {}


def test_a_directory_with_no_state_adds_no_switch(tmp_path):
    assert managed_fixture.switches_for(tmp_path) == {}
    assert managed_fixture.switches_for(tmp_path / "missing") == {}


def test_the_switches_stop_the_prompt_reminder_and_the_observation_capture():
    assert dict(SWITCHES) == {
        "PRAXION_DISABLE_PROCESS_INJECT": "1",
        "PRAXION_DISABLE_OBSERVABILITY": "1",
    }


def test_an_empty_state_directory_is_invisible_to_git_status(tmp_path):
    managed_fixture.mark_managed(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, check=True, capture_output=True, text=True
    )

    assert status.stdout == ""


# -- the launch -----------------------------------------------------------------------------


def _build(role: Role, tmp_path: Path) -> ArmBuild:
    root = tmp_path / "copy"
    (root / "agents").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "agents" / f"{role}.md", root / "agents" / f"{role}.md")
    return ArmBuild(role, "full", root, None, "digest", ())


def _launch(tmp_path: Path) -> Launch:
    return Launch(
        run_root=tmp_path / "run",
        checkout_commit="abc",
        page_url="",
        judge=None,
        seed=SEED,
        model="m",
        effort="low",
        session_budget_usd=1.0,
        keep_sandbox=True,
        env_for=lambda root, path_first: {"BASE": "kept"},
        real_home=tmp_path / "home",
        ambient={"PATH": "/usr/bin"},
    )


def _launched(role: Role, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The spec and environment the session is started with, and its scratch repository."""
    seen: dict[str, object] = {}

    def stop(spec, env):
        seen.update(spec=spec, env=env)
        raise RuntimeError("stop here: only the launch's inputs are under test")

    monkeypatch.setattr(session_launch, "run_session", stop)
    task = next(t for t in tasks.generate(role, SEED, 8) if tasks.turn_cap_of(t) is None)
    session_launch.attempt(
        _launch(tmp_path),
        session_launch.SpendLedger(cap_usd=10.0),
        task,
        _build(role, tmp_path),
        lambda root: None,
        None,
        lambda evidence: None,
    )
    return seen["spec"], seen["env"]


def test_a_launched_session_in_a_bare_fixture_is_marked_and_switched(tmp_path, monkeypatch):
    spec, env = _launched(BARE_ROLE, tmp_path, monkeypatch)

    assert (spec.cwd / STATE).is_dir()
    assert {key: env[key] for key in SWITCHES} == dict(SWITCHES)
    assert env["BASE"] == "kept"


def test_the_marker_is_added_after_the_fixture_commit(tmp_path, monkeypatch):
    spec, _ = _launched(BARE_ROLE, tmp_path, monkeypatch)

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=spec.cwd, check=True, capture_output=True, text=True
    ).stdout.split()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=spec.cwd, check=True, capture_output=True, text=True
    ).stdout

    assert not any(path.startswith(STATE) for path in tracked)
    assert STATE not in status


def test_a_launched_session_whose_overlay_carries_state_gets_no_switch(tmp_path, monkeypatch):
    spec, env = _launched(CARRYING_ROLE, tmp_path, monkeypatch)

    assert any((spec.cwd / STATE).iterdir())
    assert not set(SWITCHES) & set(env)
