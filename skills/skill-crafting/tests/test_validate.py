"""Behavioral tests for `skills/skill-crafting/scripts/validate.py`.

The validator sorts what it finds into errors (the skill is malformed; the exit status fails)
and warnings (the skill loads but an authoring hazard will bite; the exit status is untouched).
These tests pin the raw-field parse the checks read, each hazard in both directions, the
separation of the two severities, the exit status as a function of errors alone, the message
texts, and the `validate_skill` wrapper the packager imports.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "validate.py"
PROBE = "probe-skill"
DESCRIPTION = "Use when probing the skill validator with a minimal skill."
USES_ARGUMENTS = "# Probe\n\nRuns on $ARGUMENTS.\n"
LONG_ENTRY_PAGE = "# Probe\n\n" + "\n".join(f"Line {i}." for i in range(600)) + "\n"
MULTI_LINE_DESCRIPTION = "|\n  Runs the probe on request.\n  Then reports what it found."


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_validate_under_test", VALIDATOR)
    assert spec is not None, f"cannot load {VALIDATOR}"
    assert spec.loader is not None, f"cannot load {VALIDATOR}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate = _load_validator()


def skill_text(
    *, name: str = PROBE, description: str = DESCRIPTION, extra: str = "", body: str = "# Probe\n"
) -> str:
    lines = ["---", f"name: {name}", f"description: {description}"]
    if extra:
        lines.append(extra)
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def write_skill(parent: Path, text: str, directory: str = PROBE) -> Path:
    skill_dir = parent / directory
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


def check(tmp_path: Path, text: str, directory: str = PROBE):
    return validate.check_skill(write_skill(tmp_path, text, directory))


# ---------------------------------------------------------------------------
# Raw-field parse
# ---------------------------------------------------------------------------


def test_parse_keeps_the_source_quoting_of_each_value():
    fields, errors = validate.parse_frontmatter('name: x\nargument-hint: "[path]"\nmodel: sonnet')

    assert errors == []
    assert fields["argument-hint"].value == '"[path]"'
    assert fields["model"].value == "sonnet"


def test_parse_counts_the_key_line_plus_its_continuation_lines():
    raw = "name: x\ndescription: >\n  first\n  second\nmodel: sonnet\nargument-hint:"
    fields, _ = validate.parse_frontmatter(raw)

    assert fields["name"].line_count == 1
    assert fields["description"].line_count == 3
    assert fields["description"].value == "first second"
    assert fields["argument-hint"].line_count == 1
    assert fields["argument-hint"].value == ""


# ---------------------------------------------------------------------------
# Hazards: each draws one warning, and its absence draws none
# ---------------------------------------------------------------------------

HAZARDS = {
    "entry page over five hundred lines": (skill_text(body=LONG_ENTRY_PAGE), "500"),
    "empty argument-hint": (skill_text(extra='argument-hint: ""', body=USES_ARGUMENTS), "empty"),
    "argument-hint with no value": (
        skill_text(extra="argument-hint:", body=USES_ARGUMENTS),
        "empty",
    ),
    "unquoted argument-hint": (
        skill_text(extra="argument-hint: <path>", body=USES_ARGUMENTS),
        "unquoted",
    ),
    "multi-line description on a user-only skill": (
        skill_text(
            description=MULTI_LINE_DESCRIPTION,
            extra="disable-model-invocation: true",
            body=USES_ARGUMENTS,
        ),
        "3 lines",
    ),
    "arguments without a placeholder": (
        skill_text(extra="arguments: [target]", body="# Probe\n\nNo placeholder.\n"),
        "placeholder",
    ),
}

CLEAN = {
    "minimal skill": skill_text(),
    "entry page of exactly five hundred lines": skill_text(body="\n".join(["x"] * 496) + "\n"),
    "single quoted argument-hint": skill_text(extra="argument-hint: '[path]'", body=USES_ARGUMENTS),
    "double quoted argument-hint": skill_text(extra='argument-hint: "[path]"', body=USES_ARGUMENTS),
    "one-line description on a user-only skill": skill_text(
        extra="disable-model-invocation: true", body=USES_ARGUMENTS
    ),
    "multi-line description on a model-invocable skill": skill_text(
        description=MULTI_LINE_DESCRIPTION, extra="disable-model-invocation: false"
    ),
    "arguments read as a whole": skill_text(extra="arguments: [target]", body=USES_ARGUMENTS),
    "arguments read by name": skill_text(extra="arguments: [target]", body="Runs on $target.\n"),
    "arguments read by index": skill_text(extra="arguments: [target]", body="Runs on $0.\n"),
    "arguments listed on separate lines": skill_text(
        extra="arguments:\n  - first\n  - second", body="Runs on $second.\n"
    ),
}


@pytest.mark.parametrize("hazard", sorted(HAZARDS))
def test_a_hazard_draws_exactly_one_warning_and_no_error(tmp_path, hazard):
    text, expected_fragment = HAZARDS[hazard]
    report = check(tmp_path, text)

    assert report.errors == ()
    assert len(report.warnings) == 1, report.warnings
    assert expected_fragment in report.warnings[0]


@pytest.mark.parametrize("case", sorted(CLEAN))
def test_a_skill_without_a_hazard_draws_no_finding(tmp_path, case):
    report = check(tmp_path, CLEAN[case])

    assert report.errors == ()
    assert report.warnings == ()


def test_a_skill_with_every_hazard_draws_one_warning_per_hazard(tmp_path):
    text = skill_text(
        description=MULTI_LINE_DESCRIPTION,
        extra='disable-model-invocation: true\nargument-hint: ""\narguments: [target]',
        body=LONG_ENTRY_PAGE,
    )

    assert len(check(tmp_path, text).warnings) == 4


def test_every_hazard_message_states_the_hazard_then_the_fix(tmp_path):
    for index, (text, _) in enumerate(HAZARDS.values()):
        warning = check(tmp_path / str(index), text).warnings[0]
        hazard, separator, fix = warning.partition(" — ")

        assert all((hazard, separator, fix)), warning


# ---------------------------------------------------------------------------
# Errors and warnings stay apart
# ---------------------------------------------------------------------------


def test_an_error_and_a_warning_on_one_skill_land_in_their_own_lists(tmp_path):
    report = check(tmp_path, skill_text(extra="bogus-key: 1", body=LONG_ENTRY_PAGE))

    assert len(report.errors) == 1
    assert "bogus-key" in report.errors[0]
    assert len(report.warnings) == 1
    assert "500" in report.warnings[0]


def test_a_missing_frontmatter_is_an_error_and_draws_no_warning(tmp_path):
    report = check(tmp_path, "# Probe\n\nNo frontmatter.\n")

    assert report.errors
    assert report.warnings == ()


def test_a_report_is_immutable(tmp_path):
    report = check(tmp_path, skill_text())

    with pytest.raises(AttributeError):
        report.errors = ("tampered",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def test_a_name_with_consecutive_hyphens_is_rejected_naming_only_that_defect(tmp_path):
    report = check(tmp_path, skill_text(name="probe--skill"), directory="probe--skill")

    assert report.errors == ("'name' must not contain consecutive hyphens (got 'probe--skill')",)


def test_a_name_that_does_not_match_its_directory_keeps_its_message(tmp_path):
    report = check(tmp_path, skill_text(name="other-name"))

    assert report.errors == ("'name' ('other-name') does not match directory name ('probe-skill')",)


def test_an_unknown_field_keeps_its_message(tmp_path):
    report = check(tmp_path, skill_text(extra="bogus-key: 1"))

    assert report.errors == ("Unknown frontmatter fields: bogus-key",)


# ---------------------------------------------------------------------------
# The packager's wrapper and the exit status
# ---------------------------------------------------------------------------


def test_validate_skill_returns_the_errors_as_a_list_and_leaves_warnings_out(tmp_path):
    skill_dir = write_skill(tmp_path, skill_text(extra="bogus-key: 1", body=LONG_ENTRY_PAGE))

    assert validate.validate_skill(skill_dir) == ["Unknown frontmatter fields: bogus-key"]


def test_validate_skill_is_empty_for_a_skill_whose_only_findings_are_warnings(tmp_path):
    skill_dir = write_skill(tmp_path, skill_text(body=LONG_ENTRY_PAGE))

    assert validate.validate_skill(skill_dir) == []


def run_main(monkeypatch, capsys, *argv: str) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["validate.py", *argv])
    code = validate.main()
    return code, capsys.readouterr().out


def test_the_exit_status_ignores_warnings(tmp_path, monkeypatch, capsys):
    skill_dir = write_skill(tmp_path, skill_text(body=LONG_ENTRY_PAGE))

    code, out = run_main(monkeypatch, capsys, str(skill_dir))

    assert code == 0
    assert "WARNINGS -- 1 warning(s):" in out
    assert "FAILED" not in out
    assert out.rstrip().splitlines()[-1] == "PASSED -- all validations succeeded (1 warning(s))"


def test_the_exit_status_fails_on_an_error_whatever_the_warnings(tmp_path, monkeypatch, capsys):
    skill_dir = write_skill(tmp_path, skill_text(extra="bogus-key: 1", body=LONG_ENTRY_PAGE))

    code, out = run_main(monkeypatch, capsys, str(skill_dir))

    assert code == 1
    assert "FAILED -- 1 error(s):" in out
    assert "WARNINGS -- 1 warning(s):" in out
    assert "PASSED" not in out


def test_a_clean_skill_prints_no_warning_block(tmp_path, monkeypatch, capsys):
    skill_dir = write_skill(tmp_path, skill_text())

    code, out = run_main(monkeypatch, capsys, str(skill_dir))

    assert code == 0
    assert out.splitlines()[0] == f"Validating skill: {PROBE}"
    assert "WARNINGS" not in out
    assert out.rstrip().splitlines()[-1] == "PASSED -- all validations succeeded"


def test_a_whole_tree_run_groups_errors_then_warnings_per_skill(tmp_path, capsys):
    skills = tmp_path / "skills"
    skills.mkdir()
    write_skill(skills, skill_text(name="bad-one", extra="bogus-key: 1"), "bad-one")
    write_skill(skills, skill_text(name="wordy", body=LONG_ENTRY_PAGE), "wordy")
    write_skill(skills, skill_text(name="fine"), "fine")

    code = validate._validate_all(tmp_path)
    out = capsys.readouterr().out

    assert code == 1
    assert "FAILED -- 1/3 skills have errors:" in out
    assert "WARNINGS -- 1/3 skills have warnings:" in out
    assert out.index("bad-one:") < out.index("WARNINGS") < out.index("wordy:")
    assert "PASSED" not in out


def test_a_whole_tree_run_of_warnings_alone_passes(tmp_path, capsys):
    skills = tmp_path / "skills"
    skills.mkdir()
    write_skill(skills, skill_text(name="wordy", body=LONG_ENTRY_PAGE), "wordy")

    code = validate._validate_all(tmp_path)
    out = capsys.readouterr().out

    assert code == 0
    assert "WARNINGS -- 1/1 skills have warnings:" in out
    assert out.rstrip().splitlines()[-1] == "PASSED -- all 1 skills validated"
