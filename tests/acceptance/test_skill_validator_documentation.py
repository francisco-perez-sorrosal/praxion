"""What the documentation says about the skill validator is what the validator does.

The schema reference quotes each message the validator prints and the name pattern it enforces,
names its warnings and their effect on the exit status, and shows both ways to run it. The
skills-directory guidance agrees with the refreshed skill and states no stale proportion. The
tech-debt row that tracked the validator gap records its removal condition as met.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.skill_pages import (
    REPO_ROOT,
    read,
    read_tracked,
    schema_name_pattern,
    schema_text,
    schema_validation_section,
)
from tests.acceptance.drivers.skill_validator import (
    rejection_probes,
    skill_md,
    validate,
    write_skill,
)


def message_words(message: str, values: tuple[str, ...]) -> list[str]:
    """The constant words of a message: quoted text, probe values and numbers removed."""
    text = message
    for value in values:
        text = text.replace(value, " ")
    text = re.sub(r"'[^']*'|\"[^\"]*\"|\d+", " ", text)
    return [w.lower() for w in re.findall(r"[A-Za-z]{3,}", text)]


def documented(words: list[str], section: str) -> bool:
    """Whether one line of the section carries the words in the message's order."""
    pattern = re.compile(r"\b" + r"\b.*?\b".join(map(re.escape, words)) + r"\b")
    return any(pattern.search(line.lower()) for line in section.replace("`", "").splitlines())


# --- each message the validator prints is documented -------------------------------------------


@pytest.mark.parametrize("defect", sorted(rejection_probes()))
def test_the_schema_reference_quotes_the_message_the_validator_prints_for_each_defect(
    tmp_path, defect
):
    probe = rejection_probes()[defect]
    run = validate(write_skill(tmp_path, probe.directory, probe.text))
    section = schema_validation_section()
    undocumented = [
        e for e in run.errors() if not documented(message_words(e, probe.values), section)
    ]

    assert run.errors(), f"the validator printed no error for {defect}; {run.describe()}"
    assert not undocumented, f"messages missing from the validation section: {undocumented}"


NAME_PROBES = ["ab", "a1-b2", "skill", "Ab", "a_b", "-ab", "ab-"]


@pytest.mark.parametrize("name", NAME_PROBES)
def test_the_documented_name_pattern_agrees_with_the_validator(tmp_path, name):
    documented_valid = schema_name_pattern().fullmatch(name) is not None
    run = validate(write_skill(tmp_path, name, skill_md(name)))
    name_errors = [e for e in run.errors() if re.search(r"name", e, re.I)]

    assert (not name_errors) == documented_valid, (
        f"{name!r}: pattern says valid={documented_valid}; validator errors: {name_errors}"
    )


WARNING_HAZARDS = {
    "the entry-page length warning": r"500",
    "the argument-hint warning": r"argument-hint",
    "the user-only multi-line description warning": r"disable-model-invocation|user[- ]only",
    "the unused declared arguments warning": r"\barguments\b.{0,200}placeholder|placeholder.{0,200}\barguments\b",
}


@pytest.mark.parametrize("hazard", sorted(WARNING_HAZARDS))
def test_the_validation_section_names_each_warning(hazard):
    section = schema_validation_section().replace("`", "")

    assert re.search(WARNING_HAZARDS[hazard], section, re.I | re.S), f"not documented: {hazard}"


def test_the_validation_section_says_warnings_do_not_change_the_exit_status():
    section = schema_validation_section().replace("`", "")
    about_exit = [s for s in re.split(r"(?<=[.!?])\s+|\n", section) if re.search(r"exit", s, re.I)]

    assert any(re.search(r"warn", s, re.I) for s in about_exit), (
        f"no sentence ties warnings to the exit status: {about_exit}"
    )


@pytest.mark.parametrize(
    ("form", "pattern"),
    [("one skill", r"validate\.py\s+\S*skills/\S+"), ("the whole tree", r"validate\.py\s+--all")],
)
def test_the_validation_section_shows_how_to_run_the_validator(form, pattern):
    assert re.search(pattern, schema_validation_section()), f"no command validates {form}"


@pytest.mark.parametrize("field", ["background", "disallowed-tools"])
def test_the_claude_code_field_table_lists_the_fields_added_since_the_last_refresh(field):
    rows = re.findall(r"^\|\s*`([\w-]+)`\s*\|", schema_text(), re.M)

    assert field in rows, f"no field-table row for {field}"


# --- the validator-gap deferral is closed ------------------------------------------------------


def ledger_row(row_id: str) -> dict[str, str] | None:
    for relative in (".ai-state/TECH_DEBT_LEDGER.md", ".ai-state/TECH_DEBT_RESOLVED.md"):
        header: list[str] | None = None
        for line in (read_tracked(relative) or "").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if line.startswith("|") and "id" in cells and "status" in cells:
                header = cells
            elif header and line.startswith("|") and cells and cells[0] == row_id:
                return dict(zip(header, cells, strict=False))
    return None


def test_the_validator_gap_debt_row_records_its_removal_condition_as_met():
    row = ledger_row("td-391")

    assert row is not None, "td-391 is in neither tech-debt file"
    assert row.get("status") == "resolved" or re.search(r"\bmet\b", row.get("notes", ""), re.I), (
        f"td-391 does not record its removal condition as met: {row}"
    )


# --- the skills-directory guidance agrees with the refreshed skill -----------------------------

SKILLS_GUIDANCE = "skills/CLAUDE.md"
GUIDANCE_STATEMENTS = {
    "running the validator after modifying a skill": r"validate\.py",
    "the validator's --all form": r"--all",
    "that validator warnings do not fail the run": (
        r"warning.{0,160}\b(not|never)\b.{0,60}(fail|exit)|\b(not|never)\b.{0,60}fail.{0,160}warning"
    ),
    "the entry page target under 500 lines": r"500",
    "depth moved to reference pages": r"references/",
    "the authoring skill covering invocation modes": r"invocation",
    "the authoring skill covering the eval-first loop": r"eval",
    "the scaffold, validate and package workflow": r"package",
}


@pytest.mark.parametrize("what", sorted(GUIDANCE_STATEMENTS))
def test_the_skills_directory_guidance_states_what_the_refreshed_skill_teaches(what):
    text = read(REPO_ROOT / SKILLS_GUIDANCE).replace("`", "")

    assert re.search(GUIDANCE_STATEMENTS[what], text, re.I), (
        f"{SKILLS_GUIDANCE} does not state {what}"
    )


def back_link_share() -> float:
    pages = sorted((REPO_ROOT / "skills").glob("*/references/*.md"))
    linked = [p for p in pages if re.search(r"\]\(\.\./SKILL\.md", p.read_text(encoding="utf-8"))]
    return 100 * len(linked) / len(pages)


def stated_proportions(text: str) -> list[tuple[int, str]]:
    return [
        (int(m.group(1)), line.strip())
        for line in text.splitlines()
        for m in re.finditer(r"(\d+)\s*%", line)
    ]


def test_every_proportion_the_skills_directory_guidance_states_holds_when_re_measured():
    stated = stated_proportions(read(REPO_ROOT / SKILLS_GUIDANCE))
    measured = back_link_share()
    unmeasurable = [
        line for _, line in stated if not re.search(r"back-?link|\.\./SKILL\.md", line, re.I)
    ]
    wrong = [
        f"{value}% (measured {measured:.0f}%): {line}"
        for value, line in stated
        if abs(value - measured) > 5
    ]

    assert not unmeasurable, f"proportions with no re-measurable subject: {unmeasurable}"
    assert not wrong, f"stated proportions that no longer hold: {wrong}"


def test_every_count_of_skills_the_guidance_states_matches_the_tree():
    on_disk = len(list((REPO_ROOT / "skills").glob("*/SKILL.md")))
    stated = [int(n) for n in re.findall(r"\b(\d+)\s+skills\b", read(REPO_ROOT / SKILLS_GUIDANCE))]

    assert all(n == on_disk for n in stated), f"stated skill counts {stated}; on disk {on_disk}"
