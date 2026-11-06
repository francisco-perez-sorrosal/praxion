"""Both writer roles become switchable only through the eligibility pin, and stay unswitched.

The pin lists the test-engineer and the systems-architect beside the roles it already held. Once
they are eligible, the flip gate still refuses a commit that moves either one to switched
without a passing run of that role, and the kernel gates stay clean on the checkout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers import flip_gate, kernel_adoption, kernel_sandbox
from tests.acceptance.drivers.flip_gate import switch_with_flag
from tests.acceptance.drivers.kernel_sandbox import (
    PILOT_ROLES,
    REPO_ROOT,
    Sandbox,
    commit_gate,
    regenerate,
)
from tests.acceptance.drivers.writer_kits import WRITER_ROLES

ROLES_ELIGIBLE_BEFORE = {*PILOT_ROLES, "implementer"}


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


def test_the_pin_adds_both_writer_roles_to_the_roles_it_held():
    assert flip_gate.eligible_roles(REPO_ROOT) == ROLES_ELIGIBLE_BEFORE | set(WRITER_ROLES)


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_a_switch_of_an_eligible_writer_role_without_a_passing_run_is_refused(
    sandbox: Sandbox, role: str
) -> None:
    switch_with_flag(sandbox, kernel_adoption.full_switch_record(role))
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert role in flip_gate.eligible_roles(sandbox.root), f"the {role} is not eligible"
    assert verdict.refused, f"the {role} was switched with no passing run of its own"
    assert role in verdict.output, verdict.output


@pytest.mark.parametrize(
    "gate",
    [("check_kernel_manifest.py",), ("generate_kernels.py", "--check")],
    ids=["kernel manifest", "kernel generator"],
)
def test_the_kernel_gates_stay_clean_on_the_checkout(gate: tuple[str, ...]) -> None:
    script, *args = gate

    done = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]
