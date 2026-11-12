"""The task-brief reminder names where it looked and when it is wrong.

When the reminder finds no TASK_BRIEF.md for the slug a spawn states, its advisory
names the checkout root it looked under and says that a brief kept in another
worktree of the repository, such as a pipeline worktree, is not seen from there, so
the advisory is false when the brief lives in that worktree. A found brief still draws
no advisory, and the reminder never blocks a spawn.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.acceptance.drivers.refusal_messages import main_with_briefed_worktree
from tests.acceptance.drivers.task_brief_reminder import run_reminder, spawn_payload, write_brief

SLUG = "widget-pipeline"
PROMPT = f"Task slug: {SLUG}\n\nDesign the widget."


def _advisory_from_the_main_checkout(tmp_path: Path) -> tuple[Path, str]:
    main, _ = main_with_briefed_worktree(tmp_path, SLUG)
    run = run_reminder(spawn_payload(PROMPT, main))
    assert run.exit_code == 0, run.stdout
    outputs = [a.get("hookSpecificOutput", {}) for a in run.advisories()]
    assert [o.get("permissionDecision") for o in outputs if "permissionDecision" in o] == []
    texts = [o["additionalContext"] for o in outputs if "additionalContext" in o]
    assert len(texts) == 1, f"expected one advisory from the main checkout, got: {run.stdout!r}"
    return main, texts[0]


def test_the_advisory_names_the_checkout_root_it_looked_under(tmp_path: Path) -> None:
    main, advisory = _advisory_from_the_main_checkout(tmp_path)

    roots = {str(main), str(main.resolve())}

    assert any(root in advisory for root in roots), (
        f"the advisory names no root of {roots}:\n{advisory}"
    )


def test_the_advisory_says_a_brief_in_another_worktree_is_not_seen(tmp_path: Path) -> None:
    _, advisory = _advisory_from_the_main_checkout(tmp_path)

    assert re.search(r"worktree", advisory, re.IGNORECASE), advisory
    assert re.search(
        r"false|wrong|mistaken|not seen|isn't seen|cannot see|can't see|not visible|does not see|doesn't see",
        advisory,
        re.IGNORECASE,
    ), advisory


def test_a_found_brief_draws_no_advisory(tmp_path: Path) -> None:
    main, _ = main_with_briefed_worktree(tmp_path, SLUG)
    write_brief(main, SLUG)

    run = run_reminder(spawn_payload(PROMPT, main))

    assert run.exit_code == 0
    assert run.stdout == "", run.stdout
