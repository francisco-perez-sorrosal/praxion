"""The verifier's Calibration Verdict sub-step reaches the signals of all five tiers through
its own definition, word for word as the protocol's tier table states them, now that the tier
table no longer arrives at spawn; a copy that drifts from the table is refused by the kernel
checks; and the verdict's output contract is unchanged.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.acceptance.drivers import audience_split as split
from tests.acceptance.drivers import calibration_signals as signals
from tests.acceptance.drivers import kernel_sandbox
from tests.acceptance.drivers.audience_split import PROTOCOL, REPO_ROOT
from tests.acceptance.drivers.calibration_signals import TIERS
from tests.acceptance.drivers.kernel_sandbox import Sandbox


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    sandbox = kernel_sandbox.new_sandbox(template, tmp_path / "plugin")
    for rel in signals.carriers(REPO_ROOT):  # a carrier under a tree the sandbox leaves out
        if not sandbox.path(rel).exists():
            sandbox.path(rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, sandbox.path(rel))
    return sandbox


def test_one_carrier_the_sub_step_reaches_holds_every_tiers_signals_word_for_word() -> None:
    reached = {
        rel: signals.tiers_carried(text, signals.tier_signals(REPO_ROOT))
        for rel, text in signals.carriers(REPO_ROOT).items()
    }

    assert signals.signal_carrier(REPO_ROOT) is not None, (
        f"no carrier the Calibration Verdict sub-step reaches holds all of {TIERS}: {reached}"
    )


def test_the_verifiers_rule_delivery_holds_no_tier_table(tmp_path: Path) -> None:
    project = split.fresh_project(tmp_path / "project")
    received = split.spawn(REPO_ROOT, project, "praxion:verifier").text_of(PROTOCOL) or ""

    assert "### Process Calibration" not in received
    assert signals.tier_signals(REPO_ROOT)["Spike"] not in received


@pytest.mark.parametrize("tier", TIERS)
def test_a_copy_of_a_tiers_signals_that_differs_from_the_protocol_is_refused(
    sandbox: Sandbox, tier: str
) -> None:
    carrier = signals.signal_carrier(sandbox.root)
    assert carrier is not None, (
        "the Calibration Verdict sub-step reaches no carrier of the tier signals"
    )
    if carrier == signals.PROTOCOL:
        pytest.skip(
            "the sub-step reads the protocol's own table: there is no copy that could drift"
        )
    assert not split.kernel_gate(sandbox.root).refused, "the checkout must pass before the drift"

    signals.drift_copy(sandbox.root, tier)

    assert split.kernel_gate(sandbox.root).refused


@pytest.mark.parametrize(
    "contract",
    [
        "`## Calibration Verdict`",
        "Retrospective",
        "`correct`",
        "`over-calibrated`",
        "`under-calibrated`",
        "one-line evidence clause",
        "Standard/Full",
    ],
)
def test_the_calibration_verdicts_output_contract_is_unchanged(contract: str) -> None:
    assert contract in signals.calibration_substep(REPO_ROOT)
