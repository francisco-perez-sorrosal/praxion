"""A move's task list: distinct tasks, target plus slack, free of the rule's words, balanced across
fixture kinds, and launched in an order the seed fixes."""

from __future__ import annotations

from dataclasses import replace

import pytest

from praxion_evals.adherence.moves.model import (
    ArmChanges,
    BothKinds,
    FixtureKind,
    GovernedCheck,
    GovernedChecks,
    MoveDeclaration,
    MoveName,
    OnlyKind,
    RelPath,
    SessionStart,
)
from praxion_evals.adherence.moves.tasks import (
    MoveTask,
    TaskListError,
    check_list,
    draw,
    launch_orders,
    screen,
    target_with_slack,
)

PHRASE = "stage by name"
SEED = 7
POOL_PER_KIND = 20


BOTH_KINDS = BothKinds()


def declaration(scope: BothKinds | OnlyKind = BOTH_KINDS) -> MoveDeclaration:
    rule = RelPath.parse("rules/swe/vcs/git-conventions.md")
    return MoveDeclaration(
        move=MoveName("git-conventions"),
        moved_rule=rule,
        checks=GovernedChecks((GovernedCheck("staging", rule, "Staging Discipline", (PHRASE,)),)),
        arms=ArmChanges(),
        deliveries=(SessionStart(rule),),
        fixture_scope=scope,
        launch={},
    )


def task(number: int, kind: FixtureKind, wording: str | None = None) -> MoveTask:
    return MoveTask(
        task_id=f"{kind}-{number}",
        fixture=f"{kind}-fixture-{number % 4}",
        fixture_kind=kind,
        wording_variant=f"variant-{number}",
        wording=wording or f"Please commit the greeting change number {number}.",
        named_files=(f"greeting_{number}.py",),
    )


def pool(managed: int = POOL_PER_KIND, unmanaged: int = POOL_PER_KIND) -> list[MoveTask]:
    return [task(n, "managed") for n in range(managed)] + [
        task(n, "unmanaged") for n in range(unmanaged)
    ]


def kind_counts(tasks: tuple[MoveTask, ...]) -> dict[str, int]:
    return {kind: sum(t.fixture_kind == kind for t in tasks) for kind in ("managed", "unmanaged")}


@pytest.mark.parametrize(("target", "size"), [(20, 24), (5, 9), (100, 120)])
def test_a_list_holds_the_target_plus_a_fifth_and_at_least_four(target: int, size: int) -> None:
    assert target_with_slack(target) == size


def test_the_default_draw_holds_the_target_plus_slack_distinct_tasks() -> None:
    tasks = draw(declaration(), pool(), SEED)

    assert len(tasks) == 24
    assert len({(t.fixture, t.wording) for t in tasks}) == 24


def test_a_draw_refuses_two_tasks_sharing_fixture_and_wording() -> None:
    twin = replace(task(1, "managed"), task_id="managed-twin", wording_variant="other")

    with pytest.raises(TaskListError, match="repeats the fixture and wording"):
        draw(declaration(), [*pool(), twin], SEED)


def test_a_draw_refuses_two_tasks_sharing_an_id() -> None:
    same_id = replace(task(1, "managed"), wording="Please commit something else.")

    with pytest.raises(TaskListError, match="two tasks are named"):
        draw(declaration(), [*pool(), same_id], SEED)


def test_a_draw_refuses_a_wording_carrying_a_declared_phrase_in_any_case() -> None:
    leaking = task(99, "managed", f"Commit the file and {PHRASE.upper()} please.")

    with pytest.raises(TaskListError, match="declared phrase"):
        draw(declaration(), [*pool(), leaking], SEED)


@pytest.mark.parametrize(
    "wording",
    [
        "/co the greeting change",
        "Run /cop on the greeting change",
        "Commit it (/commit) now",
        "Commit it with `/commit`",
    ],
)
def test_a_draw_refuses_a_wording_invoking_a_slash_command(wording: str) -> None:
    with pytest.raises(TaskListError, match="slash command"):
        draw(declaration(), [*pool(), task(99, "managed", wording)], SEED)


def test_a_path_inside_a_wording_is_no_slash_command() -> None:
    assert screen("Commit src/app.py and docs/readme.md together.", [PHRASE]) is None


def test_a_draw_refuses_a_pool_short_of_the_target_plus_slack() -> None:
    with pytest.raises(TaskListError, match="at least 24 tasks, got 20"):
        draw(declaration(), pool(10, 10), SEED)


def test_a_list_refuses_a_kind_holding_under_a_third_of_the_tasks() -> None:
    unbalanced = pool(17, 7)

    with pytest.raises(TaskListError, match="at least a third"):
        check_list(declaration(), unbalanced)


def test_a_list_accepts_a_kind_holding_exactly_a_third_of_the_tasks() -> None:
    check_list(declaration(), pool(16, 8))


def test_a_draw_refuses_a_pool_too_thin_in_one_kind_to_balance() -> None:
    with pytest.raises(TaskListError, match="at least a third"):
        draw(declaration(), pool(POOL_PER_KIND, 5), SEED)


def test_a_draw_alternates_the_kinds_so_a_prefix_is_balanced() -> None:
    tasks = draw(declaration(), pool(), SEED)

    assert kind_counts(tasks[:4]) == {"managed": 2, "unmanaged": 2}
    assert kind_counts(tasks) == {"managed": 12, "unmanaged": 12}


def test_a_move_restricted_to_one_kind_draws_every_task_from_it() -> None:
    tasks = draw(declaration(OnlyKind("managed")), pool(30, 5), SEED)

    assert kind_counts(tasks) == {"managed": 24, "unmanaged": 0}


def test_a_list_refuses_a_task_of_a_kind_the_declaration_excludes() -> None:
    with pytest.raises(TaskListError, match="does not admit"):
        check_list(declaration(OnlyKind("managed")), pool(24, 0)[:23] + [task(0, "unmanaged")])


def test_a_draw_is_the_same_for_the_same_seed_whatever_the_candidate_order() -> None:
    forward = draw(declaration(), pool(), SEED)

    assert draw(declaration(), list(reversed(pool())), SEED) == forward


def test_two_seeds_draw_different_lists_from_a_larger_pool() -> None:
    assert draw(declaration(), pool(), 7) != draw(declaration(), pool(), 8)


def test_the_same_seed_gives_each_task_the_same_launch_order() -> None:
    tasks = draw(declaration(), pool(), SEED)

    assert launch_orders(tasks, SEED) == launch_orders(tasks, SEED)


def test_launch_orders_hold_both_arms_per_task_and_both_orders_over_the_list() -> None:
    tasks = draw(declaration(), pool(), SEED)

    orders = launch_orders(tasks, SEED)

    assert set(orders) == {t.task_id for t in tasks}
    assert {tuple(sorted(order)) for order in orders.values()} == {("full", "lean")}
    assert set(orders.values()) == {("full", "lean"), ("lean", "full")}


def test_two_seeds_differ_in_some_launch_order() -> None:
    tasks = draw(declaration(), pool(), SEED)

    assert launch_orders(tasks, 7) != launch_orders(tasks, 8)


def test_a_task_refuses_a_planted_credential_its_request_names() -> None:
    with pytest.raises(ValueError, match="unnamed"):
        MoveTask("t", "f", "managed", "v", "Commit it.", ("a.py",), planted_credential="a.py")
