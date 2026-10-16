"""A paid run builds each named arm from its own copy and proves it before scoring.

`full` is the checkout as it is; `lean` differs only in that the measured role's
definition carries `omitClaudeMd: true` (and whatever `SubagentStart` injection the
checkout already ships). Sessions start only for the named roles and arms, the
checkout under test is the same after the run as before, and an arm whose proof
fails scores no session of that role and spends only the proof.
"""

from __future__ import annotations

from tests.acceptance.drivers.adherence_eval import SEED, split_definition, task_ids
from tests.e2e.drivers.adherence_journey import flagged_roles, run_journey, switched_in_checkout


def test_a_run_naming_one_role_and_the_lean_arm_launches_only_that_roles_lean_copy(tmp_path):
    journey = run_journey(tmp_path, roles=("verifier",), arms=("lean",))

    launches = journey.launches

    assert launches, f"the run launched no session; {journey.describe()}"
    already_switched = switched_in_checkout(journey.request.checkout)
    assert "verifier" not in already_switched, "the measured role must start unswitched"
    assert [flagged_roles(launch) for launch in launches] == [
        already_switched | {"verifier"}
    ] * len(launches), "a launch ran another role's or another arm's copy"


def test_the_lean_copy_differs_from_the_checkout_only_by_the_one_setting(tmp_path):
    journey = run_journey(tmp_path, roles=("verifier",), arms=("lean",))
    checkout = journey.request.checkout
    original = (checkout / "agents" / "verifier.md").read_text(encoding="utf-8")
    original_frontmatter, original_body = split_definition(original)

    launch = journey.launches[0]
    lean_frontmatter, lean_body = split_definition(launch.agent_texts["verifier.md"])

    assert lean_frontmatter == {**original_frontmatter, "omitClaudeMd": True}
    assert lean_body == original_body
    others = {n: t for n, t in launch.agent_texts.items() if n != "verifier.md"}
    assert others == {n: (checkout / "agents" / n).read_text(encoding="utf-8") for n in others}, (
        "the lean copy changed another agent definition"
    )
    assert set(launch.agent_texts) == {p.name for p in (checkout / "agents").glob("*.md")}
    assert launch.hooks_registration == (checkout / "hooks" / "hooks.json").read_text(
        encoding="utf-8"
    ), "the lean copy changed the checkout's hook registration"


def test_the_full_arm_runs_its_own_unaltered_copy_of_the_checkout(tmp_path):
    journey = run_journey(tmp_path, roles=("researcher",), arms=("full",))
    checkout = journey.request.checkout

    launches = journey.launches

    assert launches, f"the run launched no session; {journey.describe()}"
    for launch in launches:
        assert launch.plugin_dir, "a session was launched without a plugin copy"
        assert launch.plugin_dir != str(checkout), (
            "the full arm hands sessions the checkout itself rather than its own copy"
        )
        assert launch.agent_texts == {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted((checkout / "agents").glob("*.md"))
        }, "the full arm's copy differs from the checkout's agent definitions"


def test_a_run_of_both_arms_leaves_the_checkout_under_test_unchanged(tmp_path):
    journey = run_journey(tmp_path, roles=("researcher", "verifier"), arms=("full", "lean"))

    assert journey.launches, f"the run launched no session; {journey.describe()}"
    assert journey.checkout_after == journey.checkout_before, (
        "a tracked file of the checkout changed"
    )
    assert journey.state_after == journey.state_before, "the checkout's HEAD or status changed"


def test_an_arm_whose_proof_fails_scores_nothing_and_spends_only_the_proof(tmp_path):
    journey = run_journey(tmp_path, roles=("verifier",), arms=("full", "lean"))
    tasks = len(task_ids("verifier", SEED))

    results = journey.results

    for arm in ("full", "lean"):
        assert results.arm_built("verifier", arm) is False, (
            f"the {arm} arm passed a proof it cannot pass"
        )
        assert results.scored_sessions("verifier", arm) == 0
    assert 0 < len(journey.launches) < tasks, (
        f"{len(journey.launches)} launches for a role with {tasks} tasks: more than the proof was spent"
    )
