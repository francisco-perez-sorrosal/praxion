"""The skill validator warns on four authoring hazards the harness would not report.

Each hazard draws exactly one warning that names the skill, the hazard and the fix, apart from
errors, in a single-skill run and in a whole-tree run alike. A skill with no hazard draws no
warning, and a warning never changes the exit status.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from tests.acceptance.drivers.skill_validator import (
    long_body,
    skill_md,
    validate,
    validate_tree,
    write_skill,
)

PROBE = "probe-skill"
USES_ARGUMENTS = "# Probe\n\nRuns on $ARGUMENTS.\n"
NO_PLACEHOLDER = "# Probe\n\nRuns with no argument placeholder at all.\n"
MULTI_LINE_DESCRIPTION = "|\n  Runs the probe on request.\n  Then reports what it found."


@dataclass(frozen=True)
class Hazard:
    text: str
    hazard: str  # pattern the warning uses to name the hazard
    fix: str  # pattern the warning uses to name the fix


HAZARDS = {
    "an entry page over five hundred lines": Hazard(
        skill_md(PROBE, body=long_body(600)), r"\b500\b|lines", r"reference"
    ),
    "an empty argument-hint": Hazard(
        skill_md(PROBE, extra='argument-hint: ""', body=USES_ARGUMENTS),
        r"argument-hint",
        r"quot|value|empty",
    ),
    "an argument-hint key with no value": Hazard(
        skill_md(PROBE, extra="argument-hint:", body=USES_ARGUMENTS),
        r"argument-hint",
        r"quot|value|empty|remove|omit",
    ),
    "an unquoted argument-hint": Hazard(
        skill_md(PROBE, extra="argument-hint: <path>", body=USES_ARGUMENTS),
        r"argument-hint",
        r"quot",
    ),
    "a user-only skill with a description over more than one line": Hazard(
        skill_md(
            PROBE,
            description=MULTI_LINE_DESCRIPTION,
            extra="disable-model-invocation: true",
            body=USES_ARGUMENTS,
        ),
        r"description",
        r"one line|single line|one-line|single-line",
    ),
    "declared arguments with no placeholder in the body": Hazard(
        skill_md(PROBE, extra="arguments: [target]", body=NO_PLACEHOLDER),
        r"\barguments\b",
        r"\$ARGUMENTS|placeholder|\$target",
    ),
}

CLEAN = {
    "a minimal skill": skill_md(PROBE),
    "an entry page of four hundred lines": skill_md(PROBE, body=long_body(400)),
    "a quoted argument-hint read by the body": skill_md(
        PROBE, extra='argument-hint: "[path]"', body=USES_ARGUMENTS
    ),
    "a user-only skill with a one-line description": skill_md(
        PROBE, extra="disable-model-invocation: true", body=USES_ARGUMENTS
    ),
    "a model-invocable skill with a multi-line description": skill_md(
        PROBE, description=MULTI_LINE_DESCRIPTION
    ),
    "declared arguments read by name": skill_md(
        PROBE, extra="arguments: [target]", body="# Probe\n\nRuns on $target.\n"
    ),
    "declared arguments read as a whole": skill_md(
        PROBE, extra="arguments: [target]", body=USES_ARGUMENTS
    ),
    "declared arguments read by index": skill_md(
        PROBE, extra="arguments: [target]", body="# Probe\n\nRuns on $0.\n"
    ),
}


def run_in(mode: str, tmp_path, text: str):
    if mode == "single skill":
        return validate(write_skill(tmp_path, PROBE, text))
    return validate_tree(tmp_path, {PROBE: text})


MODES = ["single skill", "whole tree"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("hazard", sorted(HAZARDS))
def test_a_hazard_draws_one_warning_naming_the_skill_the_hazard_and_the_fix(tmp_path, hazard, mode):
    case = HAZARDS[hazard]
    run = run_in(mode, tmp_path, case.text)
    warnings = run.warnings(PROBE)

    assert len(warnings) == 1, f"expected one warning for {PROBE}; {run.describe()}"
    assert re.search(case.hazard, warnings[0], re.IGNORECASE), f"hazard not named: {warnings[0]}"
    assert re.search(case.fix, warnings[0], re.IGNORECASE), f"fix not named: {warnings[0]}"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("hazard", sorted(HAZARDS))
def test_a_warning_is_not_an_error_and_leaves_the_exit_status_at_success(tmp_path, hazard, mode):
    run = run_in(mode, tmp_path, HAZARDS[hazard].text)

    assert not run.errors(PROBE), run.describe()
    assert run.exit_code == 0, run.describe()


@pytest.mark.parametrize("mode", MODES)
def test_a_skill_with_every_hazard_draws_one_warning_per_hazard(tmp_path, mode):
    text = skill_md(
        PROBE,
        description=MULTI_LINE_DESCRIPTION,
        extra='disable-model-invocation: true\nargument-hint: ""\narguments: [target]',
        body=long_body(600),
    )
    run = run_in(mode, tmp_path, text)

    assert len(run.warnings(PROBE)) == 4, run.describe()
    assert run.exit_code == 0, run.describe()


@pytest.mark.parametrize("mode", MODES)
def test_warnings_leave_an_errors_exit_status_unchanged(tmp_path, mode):
    error_only = run_in(mode, tmp_path / "error-only", skill_md(PROBE, extra="bogus-key: 1"))
    with_warning = run_in(
        mode, tmp_path / "with-warning", skill_md(PROBE, extra="bogus-key: 1", body=long_body(600))
    )

    assert error_only.exit_code != 0, error_only.describe()
    assert with_warning.exit_code == error_only.exit_code, with_warning.describe()


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", sorted(CLEAN))
def test_a_skill_with_no_hazard_draws_no_warning(tmp_path, case, mode):
    run = run_in(mode, tmp_path, CLEAN[case])

    assert not run.warnings(PROBE), run.describe()
    assert run.exit_code == 0, run.describe()
