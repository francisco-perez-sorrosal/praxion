"""The main session, every whole recipient, every lean spawn and every spawn in an unmanaged
scope receive exactly what they received at the pipeline base.

"What they received at the base" is observed, not remembered: the same checkout is delivered
once by its own hooks and once by the base commit's hooks (or, for the strings a lean role
receives, by everything the base commit's delivery read), in the very same project, and the two
readings must be byte for byte equal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.audience_split import IMPAIRMENTS, LEAN_ROLES, SPLIT_ROLES
from tests.acceptance.drivers.kernel_sandbox import Sandbox

pytestmark = pytest.mark.skipif(
    not split.base_commit_available(),
    reason=f"the base commit {split.BASE_COMMIT} is not in this clone's history (shallow clone); "
    "fetch full history to compare against the delivery before the change",
)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture(scope="module")
def base_arm(template: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return split.base_hooks_arm(template, tmp_path_factory.mktemp("base") / "checkout")


@pytest.fixture(scope="module")
def base_tree(template: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return split.base_tree_arm(template, tmp_path_factory.mktemp("base-tree") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def _both_arms_of(sandbox: Sandbox, tmp_path: Path, impairment: str) -> tuple[Path, Path, dict]:
    """The checkout and its base-delivery arm, both put in the same impaired state."""
    base = split.base_hooks_arm(sandbox.root, tmp_path / "base-plugin")
    split.impair(base, tmp_path / "scratch", impairment)
    env = split.impair(sandbox.root, tmp_path / "scratch", impairment)
    return sandbox.root, base, env


# -- The main session ------------------------------------------------------------------------


@pytest.mark.parametrize("managed", [True, False], ids=["managed", "unmanaged"])
@pytest.mark.parametrize(
    "blacklist",
    [None, ["swe/vcs/git-conventions", "swe/swe-agent-coordination-protocol"]],
    ids=["no-blacklist", "blacklist"],
)
def test_the_main_session_receives_the_same_rule_strings_as_at_the_base(
    template: Path, base_arm: Path, tmp_path: Path, managed: bool, blacklist: list[str] | None
) -> None:
    def started_by(plugin_root: Path) -> split.Delivery:
        project = split.fresh_project(tmp_path / "project", managed=managed)
        if blacklist is not None:
            split.write_blacklist(project, blacklist)
        return split.session_start(plugin_root, project, scratch=tmp_path / "scratch")

    assert started_by(template).rule_strings == started_by(base_arm).rule_strings


@pytest.mark.parametrize("managed", [True, False], ids=["managed", "unmanaged"])
@pytest.mark.parametrize("impairment", IMPAIRMENTS)
def test_an_impaired_main_session_receives_the_same_rule_strings_as_at_the_base(
    sandbox: Sandbox, tmp_path: Path, managed: bool, impairment: str
) -> None:
    current, base, env = _both_arms_of(sandbox, tmp_path, impairment)

    def started_by(plugin_root: Path) -> split.Delivery:
        project = split.fresh_project(tmp_path / "project", managed=managed)
        return split.session_start(plugin_root, project, scratch=tmp_path / "scratch", env=env)

    assert started_by(current).rule_strings == started_by(base).rule_strings


# -- Whole recipients ------------------------------------------------------------------------

WHOLE_RECIPIENTS = (
    "general-purpose",
    "statusline-setup",
    "fork",  # a fork: its payload names the agent type `fork`
    "other-plugin:verifier",
    "praxion:no-such-role",
    "release-reviewer",  # a project agent, defined in the project
    "personal-reviewer",  # a user agent, defined in the user's agents
    "undefined-reviewer",  # a custom agent with no definition anywhere
)


def _with_definitions(project: Path, scratch: Path) -> Path:
    split.write_definition(project / ".claude" / "agents", "release-reviewer")
    split.write_definition(split.user_agents_dir(scratch), "personal-reviewer")
    return project


@pytest.mark.parametrize("agent_type", WHOLE_RECIPIENTS)
def test_a_whole_recipient_receives_every_spawn_string_as_at_the_base(
    template: Path, base_arm: Path, tmp_path: Path, agent_type: str
) -> None:
    def spawned_by(plugin_root: Path) -> split.Delivery:
        scratch = tmp_path / "scratch"
        project = _with_definitions(split.fresh_project(tmp_path / "project"), scratch)
        return split.spawn(plugin_root, project, agent_type, scratch=scratch)

    assert spawned_by(template).strings == spawned_by(base_arm).strings


def test_a_plugin_role_whose_definition_cannot_be_read_receives_every_spawn_string_as_at_the_base(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    base = split.base_hooks_arm(sandbox.root, tmp_path / "base-plugin")
    split.unreadable(sandbox.path("agents/verifier.md"))
    split.unreadable(base / "agents" / "verifier.md")

    def spawned_by(plugin_root: Path) -> split.Delivery:
        project = split.fresh_project(tmp_path / "project")
        return split.spawn(plugin_root, project, "praxion:verifier", scratch=tmp_path / "scratch")

    assert spawned_by(sandbox.root).strings == spawned_by(base).strings


@pytest.mark.parametrize("impairment", IMPAIRMENTS)
def test_an_impaired_whole_recipient_receives_every_spawn_string_as_at_the_base(
    sandbox: Sandbox, tmp_path: Path, impairment: str
) -> None:
    current, base, env = _both_arms_of(sandbox, tmp_path, impairment)

    def spawned_by(plugin_root: Path) -> split.Delivery:
        project = split.fresh_project(tmp_path / "project")
        return split.spawn(
            plugin_root, project, "general-purpose", scratch=tmp_path / "scratch", env=env
        )

    assert spawned_by(current).strings == spawned_by(base).strings


# -- Lean spawns, Explore and Plan ---------------------------------------------------------


@pytest.mark.parametrize("agent_type", [*(f"praxion:{r}" for r in LEAN_ROLES), "Explore", "Plan"])
def test_a_spawn_without_instruction_files_receives_byte_for_byte_what_the_base_delivered(
    template: Path, base_tree: Path, tmp_path: Path, agent_type: str
) -> None:
    def spawned_by(plugin_root: Path) -> split.Delivery:
        project = split.fresh_project(tmp_path / "project")
        return split.spawn(plugin_root, project, agent_type, scratch=tmp_path / "scratch")

    delivery = spawned_by(template)

    assert delivery.rule_strings == ()
    assert delivery.strings == spawned_by(base_tree).strings


# -- Unmanaged scope ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_type", [*(f"praxion:{r}" for r in SPLIT_ROLES), *WHOLE_RECIPIENTS])
def test_no_spawn_in_an_unmanaged_scope_receives_rule_text(
    template: Path, base_arm: Path, tmp_path: Path, agent_type: str
) -> None:
    def spawned_by(plugin_root: Path) -> split.Delivery:
        project = split.fresh_project(tmp_path / "project", managed=False)
        return split.spawn(plugin_root, project, agent_type, scratch=tmp_path / "scratch")

    delivery = spawned_by(template)

    assert delivery.rule_strings == ()
    assert delivery.strings == spawned_by(base_arm).strings
