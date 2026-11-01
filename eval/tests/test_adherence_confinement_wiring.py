"""A confined kit's live session is started under its confinement and resolves programs from the
plugin copy first; every other kit's session is built exactly as before."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from praxion_evals.adherence import session_launch, tasks
from praxion_evals.adherence.confinement import CONFINED_ROLES, Confinement
from praxion_evals.adherence.model import ArmBuild, Role
from praxion_evals.adherence.session_launch import Launch, session_confinement
from praxion_evals.adherence.session_loop import RunConfig, _launch_of, session_env
from praxion_evals.live.session import SandboxPaths, build_argv

REPO_ROOT = Path(__file__).resolve().parents[2]
OTHER_ROLES: list[Role] = ["researcher", "doc-engineer"]
SEED = 7
AMBIENT = {"PATH": "/usr/local/bin:relative::/usr/bin"}


def _build(role: Role, tmp_path: Path) -> ArmBuild:
    root = tmp_path / "copy"
    (root / "agents").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "agents" / f"{role}.md", root / "agents" / f"{role}.md")
    return ArmBuild(role, "full", root, None, "digest", ())


def _task(role: Role):
    return tasks.generate(role, SEED, 1)[0]


def _confinement(role: Role, tmp_path: Path, token: Path | None = None) -> Confinement:
    found = session_confinement(
        role,
        tmp_path / "copy",
        tmp_path / "run",
        home=tmp_path / "home",
        token_file=token,
        ambient=AMBIENT,
    )
    assert found is not None
    return found


def _launch(tmp_path: Path, **overrides) -> Launch:
    fields = {
        "run_root": tmp_path / "run",
        "checkout_commit": "abc",
        "page_url": "",
        "judge": None,
        "seed": SEED,
        "model": "m",
        "effort": "low",
        "session_budget_usd": 1.0,
        "keep_sandbox": True,
        "env_for": lambda root, path_first: {},
        "real_home": tmp_path / "home",
        "ambient": AMBIENT,
    }
    return Launch(**{**fields, **overrides})


# -- the spec ----------------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(CONFINED_ROLES))
def test_a_confined_roles_spec_carries_settings_whose_copy_is_the_arms_copy(role, tmp_path):
    build = _build(role, tmp_path)
    confinement = _confinement(role, tmp_path)

    spec = tasks.session_spec(
        _task(role),
        build,
        SandboxPaths(tmp_path / "sandbox"),
        model="m",
        effort="low",
        max_budget_usd=1.0,
        confinement=confinement,
    )

    assert spec.settings is not None
    assert str(build.copy_root) in spec.settings["sandbox"]["filesystem"]["denyWrite"]
    assert "--settings" in build_argv(spec)


@pytest.mark.parametrize("role", sorted(CONFINED_ROLES))
def test_the_confinement_leaves_the_tool_grant_as_it_was(role, tmp_path):
    build = _build(role, tmp_path)
    sandbox = SandboxPaths(tmp_path / "sandbox")
    given = {"model": "m", "effort": "low", "max_budget_usd": 1.0}

    plain = tasks.session_spec(_task(role), build, sandbox, **given)
    confined = tasks.session_spec(
        _task(role), build, sandbox, confinement=_confinement(role, tmp_path), **given
    )

    assert confined.allowed_tools == plain.allowed_tools == tasks.allowed_tools(build)


def test_a_confinement_built_for_another_copy_is_refused(tmp_path):
    build = _build("implementer", tmp_path)
    elsewhere = _confinement("implementer", tmp_path / "other")

    with pytest.raises(ValueError, match="does not protect the plugin copy"):
        tasks.session_spec(
            _task("implementer"),
            build,
            SandboxPaths(tmp_path / "sandbox"),
            model="m",
            effort="low",
            max_budget_usd=1.0,
            confinement=elsewhere,
        )


@pytest.mark.parametrize("role", ["researcher", "verifier", "implementer"])
def test_a_spec_built_with_no_confinement_carries_no_settings(role, tmp_path):
    spec = tasks.session_spec(
        _task(role),
        _build(role, tmp_path),
        SandboxPaths(tmp_path / "sandbox"),
        model="m",
        effort="low",
        max_budget_usd=1.0,
    )

    assert spec.settings is None
    assert "--settings" not in build_argv(spec)


# -- the confinement a launch builds -------------------------------------------------------------


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_a_role_that_is_not_confined_gets_no_confinement(role, tmp_path):
    found = session_confinement(
        role, tmp_path / "copy", tmp_path / "run", home=tmp_path, token_file=None, ambient=AMBIENT
    )

    assert found is None


def test_the_copys_scripts_lead_the_program_order_and_only_absolute_path_entries_follow(tmp_path):
    order = _confinement("implementer", tmp_path).program_order

    assert order[0] == str(tmp_path / "copy" / "scripts")
    assert order[1] == str(Path(sys.prefix) / "bin")
    assert order[2:] == ("/usr/local/bin", "/usr/bin")


def test_the_operators_token_file_is_a_protected_credential(tmp_path):
    token = tmp_path / "home" / "session-token"

    confinement = _confinement("verifier", tmp_path, token)

    assert str(token) in confinement.credential_files


# -- the launch ----------------------------------------------------------------------------------


def test_prepare_puts_the_launchs_home_and_token_file_into_the_sessions_settings(tmp_path):
    token = tmp_path / "home" / "session-token"
    launch = _launch(tmp_path, token_file=token)
    build = _build("implementer", tmp_path)

    spec, _, confinement = session_launch._prepare(
        launch, _task("implementer"), build, lambda root: None, None, tmp_path / "sandbox"
    )

    credentials = [e["path"] for e in spec.settings["sandbox"]["credentials"]["files"]]  # type: ignore[index]
    assert confinement is not None
    assert str(token) in credentials
    assert str(tmp_path / "home") in spec.settings["sandbox"]["filesystem"]["denyRead"]  # type: ignore[index]


def test_prepare_gives_a_role_that_is_not_confined_no_confinement(tmp_path):
    build = _build("researcher", tmp_path)

    spec, _, confinement = session_launch._prepare(
        _launch(tmp_path), _task("researcher"), build, lambda root: None, None, tmp_path / "s"
    )

    assert (spec.settings, confinement) == (None, None)


@pytest.mark.parametrize(("role", "confined"), [("implementer", True), ("researcher", False)])
def test_a_launched_sessions_environment_is_built_with_the_confinements_program_order(
    role, confined, tmp_path, monkeypatch
):
    seen: dict[str, object] = {}
    build = _build(role, tmp_path)

    def env_for(root: Path, path_first: list[Path]) -> dict[str, str]:
        seen["path_first"] = path_first
        return {}

    monkeypatch.setattr(session_launch, "run_session", lambda spec, env: _stop())
    session_launch.attempt(
        _launch(tmp_path, env_for=env_for),
        session_launch.SpendLedger(cap_usd=10.0),
        _task(role),
        build,
        lambda root: None,
        None,
        lambda evidence: None,
    )

    expected = [build.copy_root / "scripts"] if confined else []
    assert seen["path_first"][:1] == expected  # type: ignore[index]


def _stop():
    raise RuntimeError("stop here: only the launch's inputs are under test")


def test_a_session_environment_resolves_the_given_directories_first(tmp_path):
    config = _config()
    copy_scripts = tmp_path / "copy" / "scripts"

    env = session_env(config, tmp_path / "sandbox", {"PATH": "/usr/bin"}, [copy_scripts])

    assert env["PATH"].split(os.pathsep)[0] == str(copy_scripts)


def test_the_run_builds_a_sessions_environment_with_the_directories_it_is_given(tmp_path):
    context = SimpleNamespace(
        config=_config(),
        checkout=SimpleNamespace(commit="abc"),
        run_root=tmp_path,
        page_url="",
        judge=None,
    )
    copy_scripts = tmp_path / "copy" / "scripts"

    env = _launch_of(context).env_for(tmp_path / "sandbox", [copy_scripts])  # type: ignore[arg-type]

    assert env["PATH"].split(os.pathsep)[0] == str(copy_scripts)


def test_a_session_environment_with_no_directories_given_is_as_it_was(tmp_path):
    env = session_env(_config(), tmp_path / "sandbox", {"PATH": "/usr/bin"})

    assert env["PATH"].endswith("/usr/bin")
    assert str(tmp_path) not in env["PATH"]


def test_the_run_launches_sessions_with_the_operators_token_file(tmp_path):
    token = tmp_path / "token"
    context = SimpleNamespace(
        config=replace(_config(), session_oauth_token_file=token),
        checkout=SimpleNamespace(commit="abc"),
        run_root=tmp_path,
        page_url="",
        judge=None,
    )

    assert _launch_of(context).token_file == token  # type: ignore[arg-type]


def _config() -> RunConfig:
    fields = dict.fromkeys(RunConfig.__dataclass_fields__)
    return RunConfig(**{**fields, "session_oauth_token_file": None})  # type: ignore[arg-type]
