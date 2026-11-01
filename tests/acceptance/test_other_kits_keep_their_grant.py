"""Every kit outside the confined two keeps the read-only shell grant it was measured under.

A session of any role other than the implementer and the verifier is planned with the same
tools, the same read-only shell commands, the same command-line options and the same
environment as at the base commit, so no confinement setting reaches it.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import confined_kits as kits
from tests.acceptance.drivers.confined_kits import OTHER_ROLES


@pytest.fixture(scope="module")
def printed(tmp_path_factory) -> kits.DryRun:
    return kits.dry_run(tmp_path_factory.mktemp("other-kits-dry-run"), OTHER_ROLES)


def planned(printed: kits.DryRun, role: str):
    sessions = [s for s in printed.sessions if s.role == role]
    assert sessions, f"the dry run planned no session for the {role}"
    return sessions


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_another_kits_tool_grant_is_the_one_it_had(printed, role):
    before = kits.frozen_grants()[role]

    granted = {(s.arm, kits.granted_tools(s)) for s in planned(printed, role)}

    assert granted == {(arm, tuple(seen["tools"])) for arm, seen in before.items()}


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_another_kits_shell_grant_stays_read_only(printed, role):
    shell = {grant for s in planned(printed, role) for grant in kits.shell_grants(s)}

    unrestricted = sorted(g for g in shell if g in {"Bash", "Bash(*)"} or "pytest" in g)

    assert shell, f"the {role} lost its read-only shell grant"
    assert unrestricted == [], f"the {role} gained shell grants: {unrestricted}"


@pytest.mark.parametrize("role", OTHER_ROLES)
def test_another_kits_session_carries_no_added_option_or_variable(printed, role):
    before = kits.frozen_grants()[role]

    seen = {(s.arm, kits.option_names(s), frozenset(s.env_names)) for s in planned(printed, role)}

    assert seen == {
        (arm, tuple(kit["options"]), frozenset(kit["env_names"])) for arm, kit in before.items()
    }
