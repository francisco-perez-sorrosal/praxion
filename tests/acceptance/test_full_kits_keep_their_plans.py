"""The roles that already had full kits keep their plans and their checks.

The researcher's, the implementer's and the verifier's dry runs plan the same tasks in the same
order as before the writer roles' kits were filled, at the default seed and target and at
another seed and target, and each of those roles scores the same checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers.adherence_eval import (
    RunRequest,
    check_catalog,
    checkout_under_test,
    install_fake_claude,
    planned_sessions,
    run_adherence_eval,
)

FROZEN = Path(__file__).resolve().parent / "fixtures" / "full_kits_plans_before.json"
FULL_KIT_ROLES = ("researcher", "implementer", "verifier")
DRAWS = {"seed=7 required_pairs=default": (7, None), "seed=13 required_pairs=12": (13, 12)}


def before() -> dict:
    return json.loads(FROZEN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=sorted(DRAWS))
def draw(request, tmp_path_factory) -> tuple[str, dict[str, list[str]]]:
    seed, pairs = DRAWS[request.param]
    workspace = tmp_path_factory.mktemp("full-kits")
    fake = install_fake_claude(workspace)
    dry = RunRequest(
        roles=FULL_KIT_ROLES,
        arms=("full",),
        checkout=checkout_under_test(workspace),
        output=workspace / "dry" / "adherence.json",
        seed=seed,
        required_pairs=pairs,
        dry_run=True,
    )
    result = run_adherence_eval(dry, fake.bin_dir)
    assert result.exit_code == 0, f"the dry run failed: {result.stderr[-2000:]}"
    sessions = planned_sessions(result.stdout)
    return request.param, {
        role: [s.task_id for s in sessions if s.role == role] for role in FULL_KIT_ROLES
    }


@pytest.mark.parametrize("role", FULL_KIT_ROLES)
def test_a_full_kit_role_plans_the_same_tasks_in_the_same_order(draw, role):
    key, planned = draw

    assert planned[role] == before()["plans"][key][role]


@pytest.mark.parametrize("role", FULL_KIT_ROLES)
def test_a_full_kit_role_scores_the_same_checks(role):
    checks = [[c.name, c.kind] for c in check_catalog(role)]

    assert checks == before()["checks"][role]
