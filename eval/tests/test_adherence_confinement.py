"""The confinement value: who gets one, what the rendered settings hold, and what it refuses to
build. Paths run through a symlinked prefix so the given and the realpath spellings differ."""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import get_args

import pytest

from praxion_evals.adherence.confinement import (
    CONFINED_ROLES,
    CREDENTIAL_LOCATIONS,
    SESSION_CREDENTIAL_VARIABLES,
    Confinement,
    Operator,
    Places,
    confinement_for,
    settings_of,
)
from praxion_evals.adherence.model import Role

# The locations the outer-loop test reads, relative to the real home.
ACCEPTANCE_LOCATIONS = (
    ".ssh/id_ed25519",
    ".ssh/config",
    ".aws/credentials",
    ".config/gcloud/application_default_credentials.json",
    ".azure/accessTokens.json",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials.toml",
    ".config/gh/hosts.yml",
    ".netrc",
    ".claude.json",
    ".claude/settings.json",
    ".claude/.credentials.json",
)
OTHER_ROLES = tuple(role for role in get_args(Role) if role not in CONFINED_ROLES)
AMBIENT = ("/usr/local/bin", "/usr/bin")
# The architect's real-home names, pinned apart from the module so a dropped one fails here.
EXPECTED_CREDENTIAL_LOCATIONS = {
    ".ssh",
    ".aws",
    ".config/gcloud",
    ".azure",
    ".kube",
    ".docker",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials.toml",
    ".gem/credentials",
    ".config/gh",
    ".netrc",
    ".claude",
    ".claude.json",
}


@dataclasses.dataclass(frozen=True)
class World:
    places: Places
    operator: Operator
    link: Path  # the symlinked prefix the given spellings go through
    real: Path  # what the link points at


@pytest.fixture
def world(tmp_path: Path) -> World:
    real = tmp_path / "real"
    for name in ("home", "copy", "run", "venv", "base"):
        (real / name).mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real)
    operator = Operator(
        home=link / "home",
        token_file=link / "home" / "session-token",
        runner_prefix=link / "venv",
        runner_base_prefix=link / "base",
        ambient_path=AMBIENT,
    )
    return World(Places(run_root=link / "run", plugin_copy=link / "copy"), operator, link, real)


def settings_for(world: World, role: Role = "implementer") -> dict:
    confinement = confinement_for(role, world.places, world.operator)
    assert confinement is not None
    return settings_of(confinement)["sandbox"]


def both_spellings(world: World, name: str) -> list[str]:
    return [str(world.link / name), os.path.realpath(world.link / name)]


def credential_paths(sandbox: dict) -> list[str]:
    return [entry["path"] for entry in sandbox["credentials"]["files"]]


def covered(path: str, roots: list[str]) -> bool:
    return any(path == root or path.startswith(root + os.sep) for root in roots)


# -- Who is confined ---------------------------------------------------------------------------


def test_the_confined_roles_are_the_implementer_and_the_verifier():
    assert CONFINED_ROLES == {"implementer", "verifier"}


@pytest.mark.parametrize("role", sorted(CONFINED_ROLES))
def test_a_confined_role_gets_a_confinement(world, role):
    assert isinstance(confinement_for(role, world.places, world.operator), Confinement)


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_every_other_role_gets_none(world, role):
    assert confinement_for(role, world.places, world.operator) is None


# -- The rendered settings -----------------------------------------------------------------------


def test_the_rendered_key_set_is_pinned(world):
    sandbox = settings_for(world)

    assert set(sandbox) == {
        "enabled",
        "failIfUnavailable",
        "allowUnsandboxedCommands",
        "autoAllowBashIfSandboxed",
        "filesystem",
        "credentials",
        "network",
    }
    assert set(sandbox["filesystem"]) == {"denyWrite", "denyRead", "allowRead"}
    assert set(sandbox["credentials"]) == {"files", "envVars"}
    assert all(set(entry) == {"path", "mode"} for entry in sandbox["credentials"]["files"])
    assert all(set(entry) == {"name", "mode"} for entry in sandbox["credentials"]["envVars"])


def test_the_fixed_flags_require_the_sandbox_and_allow_no_unconfined_command(world):
    sandbox = settings_for(world)

    assert sandbox["enabled"] is True
    assert sandbox["failIfUnavailable"] is True
    assert sandbox["allowUnsandboxedCommands"] is False
    assert sandbox["autoAllowBashIfSandboxed"] is True


def test_no_network_domain_is_allowed_and_a_host_outside_the_empty_list_is_denied_not_asked(world):
    assert settings_for(world)["network"] == {"strictAllowlist": True}


def test_the_file_tools_are_blocked_from_reading_outside_the_working_directories(world):
    settings = settings_of(confinement_for("verifier", world.places, world.operator))

    assert set(settings) == {"sandbox", "permissions"}
    assert settings["permissions"]["blockReadsOutsideWorkingDirectories"] is True


def test_every_shell_command_is_approved_because_the_sandbox_bounds_it(world):
    # A subshell, a `$?` expansion or an env prefix goes through the permission flow even when
    # sandboxed, and `-p` refuses whatever needs approval; the allow rule approves it, and the
    # sandbox still confines it.
    settings = settings_of(confinement_for("implementer", world.places, world.operator))

    assert settings["permissions"]["allow"] == ["Bash"]


def test_the_shell_allow_rule_rides_only_with_a_sandbox_no_command_can_leave(world):
    settings = settings_of(confinement_for("implementer", world.places, world.operator))
    sandbox = settings["sandbox"]

    assert (sandbox["allowUnsandboxedCommands"], sandbox["failIfUnavailable"]) == (False, True)
    assert "excludedCommands" not in sandbox, "an excluded command would run unconfined, approved"


def test_the_settings_serialize_to_json(world):
    settings = settings_of(confinement_for("verifier", world.places, world.operator))
    assert json.loads(json.dumps(settings)) == settings


# -- Writes and reads ------------------------------------------------------------------------------


def test_write_is_denied_over_the_plugin_copy_in_both_spellings(world):
    assert settings_for(world)["filesystem"]["denyWrite"] == both_spellings(world, "copy")


def test_read_is_denied_over_the_real_home_in_both_spellings(world):
    assert settings_for(world)["filesystem"]["denyRead"] == both_spellings(world, "home")


def test_read_is_reopened_for_the_runner_the_copy_and_the_run_root(world):
    expected = [
        *both_spellings(world, "venv"),
        *both_spellings(world, "base"),
        *both_spellings(world, "copy"),
        *both_spellings(world, "run"),
    ]
    assert settings_for(world)["filesystem"]["allowRead"] == expected


def test_the_token_file_is_denied_in_both_spellings(world):
    denied = credential_paths(settings_for(world))
    assert set(both_spellings(world, "home/session-token")) <= set(denied)


def test_no_token_file_adds_no_token_entry(world):
    operator = dataclasses.replace(world.operator, token_file=None)
    confinement = confinement_for("implementer", world.places, operator)
    assert not any("session-token" in path for path in confinement.credential_files)


def test_the_credential_locations_are_the_fourteen_named_ones():
    assert len(CREDENTIAL_LOCATIONS) == len(set(CREDENTIAL_LOCATIONS))
    assert set(CREDENTIAL_LOCATIONS) == EXPECTED_CREDENTIAL_LOCATIONS


@pytest.mark.parametrize("name", sorted(EXPECTED_CREDENTIAL_LOCATIONS))
def test_each_credential_location_is_denied_under_the_real_home(world, name):
    denied = credential_paths(settings_for(world))
    assert set(both_spellings(world, f"home/{name}")) <= set(denied)


def test_no_credential_entry_sits_under_the_sandbox_home(world):
    sandbox_home = world.places.run_root / "000-full" / "home"
    denied = credential_paths(settings_for(world))
    assert not any(covered(path, [str(sandbox_home)]) for path in denied)


@pytest.mark.parametrize("location", ACCEPTANCE_LOCATIONS)
def test_every_acceptance_location_is_covered_by_a_credential_entry(world, location):
    denied = credential_paths(settings_for(world))
    for spelling in both_spellings(world, f"home/{location}"):
        assert covered(spelling, denied), f"{spelling} is under no credential entry"


def test_the_three_session_credential_variables_are_dropped(world):
    dropped = settings_for(world)["credentials"]["envVars"]
    assert dropped == [{"name": name, "mode": "deny"} for name in SESSION_CREDENTIAL_VARIABLES]
    assert {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"} == {
        entry["name"] for entry in dropped
    }


# -- The program order -----------------------------------------------------------------------------


def test_programs_resolve_from_the_copys_scripts_then_the_runner_then_the_ambient_path(world):
    confinement = confinement_for("implementer", world.places, world.operator)
    assert confinement.program_order == (
        str(world.link / "copy" / "scripts"),
        str(world.link / "venv" / "bin"),
        *AMBIENT,
    )


# -- What it refuses to build -----------------------------------------------------------------------


@pytest.mark.parametrize("field", ["home", "token_file", "runner_prefix", "runner_base_prefix"])
def test_a_relative_operator_path_raises(world, field):
    operator = dataclasses.replace(world.operator, **{field: Path("relative/place")})
    with pytest.raises(ValueError, match="absolute"):
        confinement_for("implementer", world.places, operator)


@pytest.mark.parametrize("entry", ["", ".", "relative/bin"])
def test_a_relative_ambient_path_entry_raises(world, entry):
    operator = dataclasses.replace(world.operator, ambient_path=(*AMBIENT, entry))
    with pytest.raises(ValueError, match="absolute"):
        confinement_for("implementer", world.places, operator)


@pytest.mark.parametrize("field", ["run_root", "plugin_copy"])
def test_a_relative_place_raises(world, field):
    places = dataclasses.replace(world.places, **{field: Path("relative/place")})
    with pytest.raises(ValueError, match="absolute"):
        confinement_for("verifier", places, world.operator)


@pytest.mark.parametrize("swallowing", ["home", "home/.ssh", "home/.config"])
def test_an_allow_read_entry_covering_a_credential_raises(world, swallowing):
    places = dataclasses.replace(world.places, run_root=world.link / swallowing)
    with pytest.raises(ValueError, match="covers a credential"):
        confinement_for("implementer", places, world.operator)


def test_a_relative_path_raises_when_the_value_is_built_directly():
    with pytest.raises(ValueError, match="absolute"):
        Confinement((), ("relative",), (), (), (), ())


def test_a_confinement_cannot_be_changed(world):
    confinement = confinement_for("implementer", world.places, world.operator)
    with pytest.raises(dataclasses.FrozenInstanceError):
        confinement.deny_read = ()  # type: ignore[misc]
