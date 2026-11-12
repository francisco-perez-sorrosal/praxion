"""The hand path's skills run the installed version's check and hand over its command, or none.

`/praxion-complete-install` and `/praxion-complete-uninstall` take the plugin root from the path
Claude Code substitutes for `${CLAUDE_PLUGIN_ROOT}` when that is an existing directory, otherwise
from the praxion entry of `~/.claude/plugins/installed_plugins.json` whose install path exists, a
user-scope entry before any other. They never pick a version by listing the plugin cache, and
never take a `CLAUDE_PLUGIN_ROOT` the shell carries from the person's own configuration. With
neither root, they report the plugin as not found and run nothing, however many version
directories the cache still holds.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import hand_path_skill as hp
from tests.acceptance.drivers import plugin_update as pu

VERSIONS = [f"1.{minor}.0" for minor in range(13)]  # 1.0.0 lists first; 1.12.0 is the newest
NEWEST, OLDER_INSTALL, PROJECT_PIN = "1.12.0", "1.4.0", "1.3.0"
GONE = "9.9.9"  # a version whose directory is no longer in the cache


@pytest.fixture(scope="module")
def machine(tmp_path_factory) -> pu.Machine:
    root = tmp_path_factory.mktemp("hand-path-skill")
    source = pu.shipped_tree(root / "source")
    m = pu.Machine(root / "machine")
    hp.cache_of_versions(m, VERSIONS, source)
    hp.checkout_elsewhere(m)
    return m


def _entry(m: pu.Machine, scope: str, version: str) -> hp.Entry:
    return hp.Entry(scope, m.version(version), version)


# Each case: the substituted root (None: one that is not a directory), the registry's entries
# in order (None: no registry), whether the shell carries a checkout's root, and the root expected.
ROOT_CASES = {
    "the-registry-names-the-newest-of-thirteen": (None, [("user", NEWEST)], False, NEWEST),
    "the-registry-names-a-version-older-than-the-newest": (
        None, [("user", OLDER_INSTALL)], False, OLDER_INSTALL),
    "the-substituted-root-alone": (NEWEST, None, False, NEWEST),
    "the-substituted-root-over-a-registry-naming-another": (
        OLDER_INSTALL, [("user", NEWEST)], False, OLDER_INSTALL),
    "a-user-entry-over-an-earlier-project-entry": (
        None, [("project", PROJECT_PIN), ("user", NEWEST)], False, NEWEST),
    "an-entry-whose-directory-is-gone-is-passed-over": (
        None, [("user", GONE), ("project", NEWEST)], False, NEWEST),
    "a-shell-root-beside-the-substituted-root": (NEWEST, None, True, NEWEST),
    "a-shell-root-beside-the-registry": (None, [("user", NEWEST)], True, NEWEST),
}  # fmt: skip
NOT_FOUND_CASES = {
    "no-registry": None,
    "a-registry-naming-only-a-gone-directory": [("user", GONE)],
}


def _run(m: pu.Machine, skill: str, substituted, entries, shell) -> hp.SkillRun:
    hp.register(m, None if entries is None else [_entry(m, s, v) for s, v in entries])
    return hp.run_skill(
        skill, m,
        substituted=m.version(substituted or GONE),
        shell_root=m.root / "a-checkout" if shell else None,
    )  # fmt: skip


@pytest.fixture(scope="module")
def resolved(machine):
    """Each skill run over each root case, in turn, on the one machine."""
    return {
        (skill, case): _run(machine, skill, *args[:3])
        for skill in hp.SKILLS
        for case, args in ROOT_CASES.items()
    }


@pytest.fixture(scope="module")
def not_found(machine):
    return {
        (skill, case, shell): _run(machine, skill, None, entries, shell)
        for skill in hp.SKILLS
        for case, entries in NOT_FOUND_CASES.items()
        for shell in (False, True)
    }


# -- The installed version ------------------------------------------------------------------------


@pytest.mark.parametrize("case", ROOT_CASES)
@pytest.mark.parametrize("skill", hp.SKILLS)
def test_the_check_runs_from_the_installed_version_and_from_nowhere_else(
    resolved, machine, skill, case
):
    expected = str(machine.version(ROOT_CASES[case][3]))
    run = resolved[(skill, case)]

    assert run.checks() == [expected], f"checks ran from {run.checks()}, expected {expected}"
    assert {where for where, _ in run.calls} == {expected}, f"installers run: {run.calls}"


@pytest.mark.parametrize("case", ROOT_CASES)
@pytest.mark.parametrize("skill", hp.SKILLS)
def test_the_installed_versions_directory_is_written_out_for_the_person(
    resolved, machine, skill, case
):
    expected = ROOT_CASES[case][3]
    run = resolved[(skill, case)]
    others = [v for v in VERSIONS if v != expected and run.names(machine.version(v))]

    assert run.names(machine.version(expected)), (
        f"what the person reads never names {machine.version(expected)}"
    )
    assert not others, f"what the person reads names other cached versions: {others}"


# -- No installed plugin --------------------------------------------------------------------------


@pytest.mark.parametrize("shell", [False, True], ids=["no-shell-root", "a-shell-root"])
@pytest.mark.parametrize("case", NOT_FOUND_CASES)
@pytest.mark.parametrize("skill", hp.SKILLS)
def test_with_no_installed_plugin_no_installer_runs_despite_a_full_cache(
    not_found, skill, case, shell
):
    run = not_found[(skill, case, shell)]

    assert run.calls == [], f"an installer ran with no installed plugin: {run.calls}"


@pytest.mark.parametrize("case", NOT_FOUND_CASES)
def test_the_install_skill_reports_the_plugin_not_found_and_how_to_install_it(not_found, case):
    shown = not_found[("install", case, False)].shown

    assert hp.NOT_FOUND in shown
    assert hp.INSTALL_COMMAND in shown


@pytest.mark.parametrize("case", NOT_FOUND_CASES)
def test_the_uninstall_skill_reports_there_is_nothing_to_uninstall(not_found, case):
    assert hp.NOT_FOUND_UNINSTALL in not_found[("uninstall", case, False)].shown
