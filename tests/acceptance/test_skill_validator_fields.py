"""The skill validator agrees with Claude Code on which frontmatter fields are valid.

It accepts every field Claude Code documents, still rejects an unknown or misspelled key by name,
rejects a name with consecutive hyphens with a message naming that defect, and keeps every
rejection, every valid skill and the packager's behavior it has today.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.skill_pages import schema_field_keys
from tests.acceptance.drivers.skill_validator import (
    long_body,
    package,
    rejection_probes,
    skill_md,
    unknown_field_errors,
    validate,
    validate_repository,
    write_skill,
)

PROBE = "probe-skill"
BODY_WITH_ARGUMENTS = "# Probe\n\n## Demo\n\nRuns on $ARGUMENTS and $target.\n"

# A documented value for each field, written as raw frontmatter YAML.
TODAY_FIELDS = {
    "license": "license: MIT",
    "compatibility": "compatibility: Claude Code",
    "metadata": "metadata:\n  owner: probes",
    "allowed-tools": "allowed-tools: [Read, Grep]",
    "staleness_sensitive_sections": 'staleness_sensitive_sections:\n  - "Demo"',
    "staleness_threshold_days": "staleness_threshold_days: 60",
}
NEW_FIELDS = {
    "user-invocable": "user-invocable: true",
    "context": "context: fork",
    "agent": "agent: Explore",
    "model": "model: sonnet",
    "effort": "effort: high",
    "hooks": (
        "hooks:\n  PreToolUse:\n    - matcher: Bash\n      hooks:\n"
        '        - type: command\n          command: "true"'
    ),
    "shell": "shell: bash",
    "background": "background: false",
    "disallowed-tools": "disallowed-tools: [WebFetch]",
}
OTHER_DOCUMENTED_FIELDS = {
    "disable-model-invocation": "disable-model-invocation: false",
    "paths": 'paths: ["**/*.py"]',
    "when_to_use": "when_to_use: When a probe needs a skill.",
    "argument-hint": 'argument-hint: "[target]"',
    "arguments": "arguments: [target]",
}
DOCUMENTED_FIELDS = {**TODAY_FIELDS, **NEW_FIELDS, **OTHER_DOCUMENTED_FIELDS}
MISSPELLED_FIELDS = {
    "bogus-key": "bogus-key: 1",
    "when-to-use": "when-to-use: When probing.",
    "disable_model_invocation": "disable_model_invocation: true",
    "allowed_tools": "allowed_tools: [Read]",
    "user_invocable": "user_invocable: true",
}


def probe_with(tmp_path, extra: str):
    return write_skill(tmp_path, PROBE, skill_md(PROBE, extra=extra, body=BODY_WITH_ARGUMENTS))


# --- every documented field is accepted --------------------------------------------------------


@pytest.mark.parametrize("field", sorted(NEW_FIELDS))
def test_a_field_claude_code_documents_draws_no_unknown_field_error(tmp_path, field):
    run = validate(probe_with(tmp_path, NEW_FIELDS[field]))

    assert not unknown_field_errors(run, field), run.describe()


def test_a_skill_using_every_documented_field_at_once_validates(tmp_path):
    run = validate(probe_with(tmp_path, "\n".join(DOCUMENTED_FIELDS.values())))
    unknown = {f: unknown_field_errors(run, f) for f in DOCUMENTED_FIELDS}

    assert not {f: e for f, e in unknown.items() if e}, run.describe()
    assert run.exit_code == 0, run.describe()


@pytest.mark.parametrize("field", sorted(MISSPELLED_FIELDS))
def test_a_key_outside_the_accepted_set_is_rejected_by_name(tmp_path, field):
    run = validate(probe_with(tmp_path, MISSPELLED_FIELDS[field]))

    assert run.exit_code != 0, run.describe()
    assert unknown_field_errors(run, field), f"no error names {field} as unknown; {run.describe()}"


# --- consecutive hyphens -----------------------------------------------------------------------


def test_a_name_with_consecutive_hyphens_is_rejected_naming_that_defect(tmp_path):
    probe = rejection_probes()["consecutive hyphens in the name"]
    run = validate(write_skill(tmp_path, probe.directory, probe.text))
    naming = [e for e in run.errors() if re.search(r"consecutive hyphen", e, re.I)]

    assert run.exit_code != 0, run.describe()
    assert naming, f"no error names consecutive hyphens; {run.describe()}"
    assert not [e for e in naming if re.search(r"lowercase|leading|trailing|uppercase", e, re.I)], (
        f"the message blames rules the name does not break: {naming}"
    )


# --- no regression for what validates and what is rejected today -------------------------------


@pytest.mark.parametrize("defect", sorted(rejection_probes()))
def test_a_skill_carrying_a_defect_rejected_today_is_still_rejected_with_an_error(tmp_path, defect):
    probe = rejection_probes()[defect]
    run = validate(write_skill(tmp_path, probe.directory, probe.text))

    assert run.exit_code != 0, run.describe()
    assert run.errors(), f"exit {run.exit_code} but no error is reported; {run.describe()}"


def test_every_shipped_skill_still_validates():
    run = validate_repository()

    assert run.exit_code == 0, run.describe()
    assert not run.errors(), run.describe()


def test_the_packager_still_packages_a_skill_whose_only_findings_are_warnings(tmp_path):
    skill_dir = write_skill(tmp_path / "skills", PROBE, skill_md(PROBE, body=long_body(600)))
    run = package(skill_dir, tmp_path / "dist")

    assert run.exit_code == 0, run.describe()
    assert (tmp_path / "dist" / f"{PROBE}.skill").is_file(), run.describe()


# --- one accepted field set: the validator agrees with the schema reference --------------------

FIELD_UNIVERSE = sorted(set(DOCUMENTED_FIELDS) | set(MISSPELLED_FIELDS))


@pytest.mark.parametrize("field", FIELD_UNIVERSE)
def test_the_validator_accepts_a_field_exactly_when_the_schema_reference_lists_it(tmp_path, field):
    listed = field in schema_field_keys()
    run = validate(probe_with(tmp_path, {**DOCUMENTED_FIELDS, **MISSPELLED_FIELDS}[field]))
    accepted = not unknown_field_errors(run, field)

    assert accepted == listed, (
        f"{field}: schema reference lists it={listed}, validator accepts it={accepted}"
    )


def test_every_field_the_schema_reference_lists_is_accepted_by_the_validator(tmp_path):
    listed = sorted(schema_field_keys() - {"name", "description"})
    extra = "\n".join(DOCUMENTED_FIELDS.get(f, f"{f}: probe") for f in listed)
    run = validate(probe_with(tmp_path, extra))
    rejected = [f for f in listed if unknown_field_errors(run, f)]

    assert listed, "the schema reference lists no field"
    assert not rejected, f"listed in the schema reference but rejected as unknown: {rejected}"
