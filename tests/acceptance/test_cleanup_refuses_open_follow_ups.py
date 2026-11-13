"""The cleanup safety check refuses a task directory while its follow-up record holds open work.

Every follow-up item is in exactly one of four states: `open`, `fixed <sha>`, `ledgered td-NNN`
or `dropped <reason>`. Only `open` is left; the other three are final. An item line the record
cannot show in one of the four, or a final state missing its commit, row id or reason, counts
as open. A directory with no follow-up record is classified exactly as before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import follow_ups as fu
from tests.acceptance.drivers.follow_ups import FollowUp, Workspace

SLUG = "feature-under-cleanup"
STALE_HELPER = "rename the stale helper the parser still imports"
DEAD_BRANCH = "delete the unreachable fallback branch in the exporter"
UNCHECKED_PLAN = "# WIP\n\n## Progress\n\n- [x] Write the parser\n- [ ] Wire the parser in\n"


@pytest.fixture
def space(tmp_path: Path) -> Workspace:
    return fu.workspace(tmp_path)


# -- An open follow-up refuses the directory ------------------------------------------------------


def test_one_open_follow_up_among_final_ones_blocks_the_directory(space: Workspace) -> None:
    space.write_record(
        SLUG, [fu.fixed("tidy an import"), fu.open_item(STALE_HELPER), fu.dropped("reword a log")]
    )

    verdict = fu.classify(space, SLUG)

    assert (verdict.classification, verdict.exit_code) == ("BLOCK", 1), verdict.output


def test_the_blocking_reason_names_the_record_and_every_open_follow_up(space: Workspace) -> None:
    space.write_record(SLUG, [fu.open_item(STALE_HELPER), fu.open_item(DEAD_BRANCH)])

    verdict = fu.classify(space, SLUG)

    [reason] = verdict.reasons_naming(fu.RECORD)
    assert STALE_HELPER in str(reason), reason
    assert DEAD_BRANCH in str(reason), reason


def test_the_text_verdict_shows_the_block_and_the_open_follow_up(space: Workspace) -> None:
    space.write_record(SLUG, [fu.open_item(STALE_HELPER)])

    result = fu.classify_text(space, SLUG)

    assert result.exit_code == 1, result.output
    assert "BLOCK" in result.output, result.output
    assert fu.RECORD in result.output, result.output


def test_an_open_follow_up_beside_an_unfinished_plan_adds_its_own_reason(
    space: Workspace,
) -> None:
    space.write(SLUG, "WIP.md", UNCHECKED_PLAN)
    space.write_record(SLUG, [fu.open_item(STALE_HELPER)])

    verdict = fu.classify(space, SLUG)

    assert verdict.classification == "BLOCK"
    assert verdict.reasons_naming("WIP.md") != [], "the unfinished plan's reason was lost"
    assert verdict.reasons_naming(fu.RECORD) != [], "the open follow-up gave no reason"


# -- Each of the four states ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("item", "classification"),
    [
        (fu.open_item(STALE_HELPER), "BLOCK"),
        (fu.fixed(STALE_HELPER), "SAFE"),
        (fu.ledgered(STALE_HELPER), "SAFE"),
        (fu.dropped(STALE_HELPER), "SAFE"),
    ],
    ids=["open", "fixed <sha>", "ledgered td-NNN", "dropped <reason>"],
)
def test_a_lone_follow_up_is_classified_by_its_state(
    space: Workspace, item: FollowUp, classification: str
) -> None:
    space.write_record(SLUG, [item])

    assert fu.classify(space, SLUG).classification == classification


def test_a_record_whose_items_are_all_final_adds_no_reason(space: Workspace) -> None:
    space.write(SLUG, "LEARNINGS.md", "- **[implementer]** a gotcha worth keeping\n")
    space.write_record(
        SLUG, [fu.fixed(STALE_HELPER), fu.ledgered(DEAD_BRANCH), fu.dropped("reword a log")]
    )

    verdict = fu.classify(space, SLUG)

    assert verdict.classification == "WARN"
    assert verdict.reasons_naming(fu.RECORD) == [], verdict.reasons


# -- What the record cannot show counts as open ------------------------------------------------


def test_an_item_in_no_known_state_counts_as_open(space: Workspace) -> None:
    space.write_record(SLUG, [FollowUp("done", "", STALE_HELPER)])

    verdict = fu.classify(space, SLUG)

    assert (verdict.classification, verdict.exit_code) == ("BLOCK", 1), verdict.output


@pytest.mark.parametrize(
    "item",
    [
        FollowUp("fixed", "", STALE_HELPER),
        FollowUp("ledgered", "", STALE_HELPER),
        FollowUp("dropped", "", STALE_HELPER),
        FollowUp("fixed", "soon", STALE_HELPER),
        FollowUp("ledgered", "row-seven", STALE_HELPER),
    ],
    ids=[
        "fixed without a commit",
        "ledgered without a row id",
        "dropped without a reason",
        "fixed with no commit sha",
        "ledgered with no td row id",
    ],
)
def test_a_final_state_missing_its_argument_counts_as_open(
    space: Workspace, item: FollowUp
) -> None:
    space.write_record(SLUG, [item])

    verdict = fu.classify(space, SLUG)

    assert (verdict.classification, verdict.exit_code) == ("BLOCK", 1), verdict.output


# -- No record: classified exactly as before ---------------------------------------------------


def test_a_directory_with_no_record_and_unmerged_learnings_is_warned_as_before(
    space: Workspace,
) -> None:
    space.write(SLUG, "LEARNINGS.md", "- **[implementer]** a gotcha worth keeping\n")

    verdict = fu.classify(space, SLUG)

    assert (verdict.classification, verdict.exit_code) == ("WARN", 0)
    assert [r["code"] for r in verdict.reasons] == ["unmerged-learnings"]


def test_a_directory_with_no_record_and_an_unfinished_plan_is_blocked_as_before(
    space: Workspace,
) -> None:
    space.write(SLUG, "WIP.md", UNCHECKED_PLAN)

    verdict = fu.classify(space, SLUG)

    assert (verdict.classification, verdict.exit_code) == ("BLOCK", 1)
    assert [r["code"] for r in verdict.reasons] == ["active-pipeline"]


def test_the_cleanup_command_still_lets_force_override_a_block() -> None:
    command = (fu.REPO_ROOT / "skills/clean-work/SKILL.md").read_text(encoding="utf-8")

    assert "--force <slug>" in command
    assert "BLOCK" in command
