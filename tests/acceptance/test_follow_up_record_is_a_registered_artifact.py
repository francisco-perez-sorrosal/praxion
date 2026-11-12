"""The follow-up record is a registered pipeline artifact, and no consumer drifts from the registry.

The registry places it in the task directory with the cleanup policy of the artifacts the
cleanup check refuses to delete while live; the drift test passes with it registered, and
fails while any consumer the registry checks leaves it out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import registry_drift as rd
from tests.acceptance.drivers.follow_ups import RECORD
from tests.acceptance.drivers.kernel_sandbox import REPO_ROOT


def test_the_registry_places_the_follow_up_record_in_the_task_directory() -> None:
    artifact = rd.registry().by_name(RECORD)

    assert artifact is not None, f"{RECORD} is not registered"
    assert artifact.location == rd.registry().by_name("WIP.md").location


def test_the_follow_up_records_cleanup_policy_is_the_one_a_refusal_agrees_with() -> None:
    reg = rd.registry()
    refusing = {reg.cleanup_policy_for(name) for name in rd.REFUSED_WHILE_LIVE}

    assert len(refusing) == 1, f"the refused-while-live artifacts disagree: {refusing}"
    assert reg.cleanup_policy_for(RECORD) in refusing


def test_the_drift_test_passes_on_this_checkout() -> None:
    result = rd.drift_test(REPO_ROOT)

    assert result.exit_code == 0, result.output[-3000:]


@pytest.mark.parametrize("consumer", sorted(rd.CONSUMERS))
def test_the_drift_test_fails_while_a_consumer_leaves_the_follow_up_record_out(
    tmp_path: Path, consumer: str
) -> None:
    root = rd.checkout_copy(tmp_path / "checkout")
    rd.omit_from_consumer(root, consumer, RECORD)

    result = rd.drift_test(root)

    assert result.exit_code != 0, f"the drift test passed with {RECORD} missing from the {consumer}"
