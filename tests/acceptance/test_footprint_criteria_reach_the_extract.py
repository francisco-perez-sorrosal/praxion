"""A spec's footprint criteria reach whoever designs acceptance tests from it.

A change that moves a measurable footprint states, in its spec, a quantitative
criterion for each footprint (metric, comparator, limit, the baseline or
reference it is judged against, and the command that measures it), or a
reasoned declaration that the footprint is not measured. Acceptance tests are
designed from the spec extract alone, so the criterion -- command included --
and the declaration must come through the extract intact, and the spec that
carries them must pass the design-vocabulary lint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.footprint_spec import (
    NotMeasured,
    QuantitativeCriterion,
    spec_carrying,
)
from tests.acceptance.drivers.spec_extract import run_extract

ALWAYS_LOADED_TOKENS = QuantitativeCriterion(
    metric="always-loaded token count, on a tokenizer reading",
    comparator="at or below",
    limit="16,726 tokens",
    baseline="16,726 tokens, recorded before the first production change",
    command="python3 scripts/measure_token_budget.py --json",
)

SELECTION_SHARE = QuantitativeCriterion(
    metric="share of the suite a one-file change selects",
    comparator="at or below",
    limit="40 percent",
    baseline="36 percent at the base commit",
    command="scripts/measure_selection_size.py --compare-ref",
)

PROMPT_SIZE = QuantitativeCriterion(
    metric="line count of each agent prompt flagged at baseline",
    comparator="grows by at most",
    limit="10 lines",
    baseline="678 lines for the sentinel agent",
    command="python3 scripts/check_agent_prompt_size.py --json",
)

LATER_SPAWNS = NotMeasured(
    footprint="spawn count of later pipelines",
    reason=(
        "the only spawn-count command counts a pipeline that has already run, "
        "so no command measures how this change alters the spawns of later pipelines"
    ),
)


def _criterion_fields(criterion: QuantitativeCriterion) -> dict[str, str]:
    return {
        "metric": criterion.metric,
        "comparator": criterion.comparator,
        "limit": criterion.limit,
        "baseline or reference": criterion.baseline,
        "command": criterion.command,
    }


def _missing_from(extract: str, fields: dict[str, str]) -> dict[str, str]:
    return {name: value for name, value in fields.items() if value not in extract}


@pytest.mark.parametrize(
    "criterion",
    [ALWAYS_LOADED_TOKENS, SELECTION_SHARE],
    ids=["judged-against-a-baseline", "judged-against-a-reference"],
)
def test_a_quantitative_criterion_reaches_the_extract_with_its_command(
    tmp_path: Path, criterion: QuantitativeCriterion
) -> None:
    plan = spec_carrying(criteria=(criterion,))

    run = run_extract(tmp_path, plan)

    assert run.exit_code == 0, f"the spec was not extracted: {run.findings or run.stderr}"
    assert run.blocking() == [], f"the criterion tripped the spec lint: {run.blocking()}"
    assert run.extract is not None
    missing = _missing_from(run.extract, _criterion_fields(criterion))
    assert missing == {}, f"criterion parts absent from the extract: {missing}"


def test_a_not_measured_declaration_reaches_the_extract_with_its_reason(
    tmp_path: Path,
) -> None:
    plan = spec_carrying(declarations=(LATER_SPAWNS,))

    run = run_extract(tmp_path, plan)

    assert run.exit_code == 0, f"the spec was not extracted: {run.findings or run.stderr}"
    assert run.blocking() == [], f"the declaration tripped the spec lint: {run.blocking()}"
    assert run.extract is not None
    missing = _missing_from(
        run.extract,
        {"footprint": LATER_SPAWNS.footprint, "reason": LATER_SPAWNS.reason},
    )
    assert missing == {}, f"declaration parts absent from the extract: {missing}"


def test_every_footprint_of_a_spec_reaches_the_extract(tmp_path: Path) -> None:
    criteria = (ALWAYS_LOADED_TOKENS, SELECTION_SHARE, PROMPT_SIZE)
    plan = spec_carrying(criteria=criteria, declarations=(LATER_SPAWNS,))

    run = run_extract(tmp_path, plan)

    assert run.exit_code == 0, f"the spec was not extracted: {run.findings or run.stderr}"
    assert run.blocking() == [], f"the spec lint blocked the spec: {run.blocking()}"
    assert run.extract is not None
    missing = {
        criterion.metric: gaps
        for criterion in criteria
        if (gaps := _missing_from(run.extract, _criterion_fields(criterion)))
    }
    assert missing == {}, f"criteria with parts absent from the extract: {missing}"
    assert LATER_SPAWNS.reason in run.extract, "the not-measured declaration lost its reason"
