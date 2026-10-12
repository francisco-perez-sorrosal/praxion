"""The document, ledger, workflow and spawn constructors, each on a violation and on a clean session."""

from __future__ import annotations

import re

import pytest

from praxion_evals.adherence.checks_common import synthetic_evidence
from praxion_evals.adherence.checks_documents import (
    document_mentions,
    fields_per_section,
    labelled_values,
    ledger_rows_confined,
    log_preserved,
    log_row_for_report,
    returns_instead_of_writing,
    spawn_fan_out,
    spawn_prompts_carry,
    workflow_security,
)
from praxion_evals.adherence.model import (
    Failed,
    NotApplicable,
    Passed,
    RuleRef,
    Withheld,
)
from praxion_evals.live.session import ToolUse

RULE = RuleRef("agents/sentinel.md", "Constraints")
ROLE = "sentinel"
SLUG = "doc-task"
DOC = "REPORT.md"
DOC_PATH = f".ai-work/{SLUG}/{DOC}"


def _evidence(files=None, **kwargs):
    return synthetic_evidence(ROLE, slug=SLUG, files=files or {}, **kwargs)


# ---------------------------------------------------------------------------
# document_mentions
# ---------------------------------------------------------------------------


def test_a_document_that_mentions_the_pattern_passes_and_one_that_does_not_fails():
    check = document_mentions("m", RULE, ROLE, document=DOC, pattern=re.compile("AUTO"))

    assert check.evaluate(_evidence({DOC_PATH: "# T\n[AUTO]\n"})) == Passed()
    assert isinstance(check.evaluate(_evidence({DOC_PATH: "# T\nnothing\n"})), Failed)
    assert isinstance(check.evaluate(_evidence()), Failed)


def test_a_document_named_with_a_star_is_found_wherever_the_star_matches():
    check = document_mentions("m", RULE, ROLE, document="CONSULT_*.md", pattern=re.compile("ok"))
    files = {f".ai-work/{SLUG}/CONSULT_statistics.md": "ok"}

    assert check.evaluate(_evidence(files)) == Passed()


# ---------------------------------------------------------------------------
# fields_per_section
# ---------------------------------------------------------------------------

PARENTS = {"Stage One": ("Scope", "Findings"), "Stage Two": ("Scope", "Plan")}
STAGE_ONE = "## Stage One\n\n### Scope\nwhat\n\n### Findings\nthis\n"


def _fields():
    return fields_per_section("f", RULE, ROLE, document=DOC, parents=PARENTS)


def test_only_the_stage_sections_present_are_held_to_their_fields():
    assert _fields().evaluate(_evidence({DOC_PATH: STAGE_ONE})) == Passed()


def test_a_present_stage_section_missing_a_field_fails_and_names_it():
    outcome = _fields().evaluate(
        _evidence({DOC_PATH: STAGE_ONE + "\n## Stage Two\n### Scope\nx\n"})
    )

    assert isinstance(outcome, Failed)
    assert "'Stage Two' lacks 'Plan'" in outcome.detail


def test_a_field_left_as_a_placeholder_fails():
    text = "## Stage One\n\n### Scope\n[pending]\n\n### Findings\nthis\n"

    assert isinstance(_fields().evaluate(_evidence({DOC_PATH: text})), Failed)


def test_a_document_with_none_of_the_stage_sections_fails():
    assert isinstance(_fields().evaluate(_evidence({DOC_PATH: "# Other\n"})), Failed)


# ---------------------------------------------------------------------------
# labelled_values
# ---------------------------------------------------------------------------


def _labelled():
    return labelled_values("l", RULE, ROLE, document=DOC, label="Disposition", allowed={"pending"})


@pytest.mark.parametrize(
    "line",
    ["- **Disposition**: pending", "**Disposition:** Pending", "  * **Disposition**: PENDING"],
)
def test_a_label_with_an_allowed_value_passes_in_any_case_and_bullet(line):
    assert _labelled().evaluate(_evidence({DOC_PATH: line + "\n"})) == Passed()


def test_a_label_with_another_value_fails_and_names_it():
    outcome = _labelled().evaluate(_evidence({DOC_PATH: "- **Disposition**: approved\n"}))

    assert isinstance(outcome, Failed)
    assert "approved" in outcome.detail


def test_an_unwritten_document_fails_the_labelled_values():
    assert isinstance(_labelled().evaluate(_evidence()), Failed)


# ---------------------------------------------------------------------------
# log_row_for_report
# ---------------------------------------------------------------------------

REPORT = ".ai-state/reports/REPORT_*.md"
LOG = ".ai-state/reports/LOG.md"
REPORT_FILE = ".ai-state/reports/REPORT_2026.md"


def _log_row():
    return log_row_for_report("r", RULE, ROLE, report=REPORT, log=LOG)


def test_a_log_with_a_row_naming_the_report_passes():
    files = {REPORT_FILE: "# R\n", LOG: "| when | REPORT_2026.md |\n"}

    assert _log_row().evaluate(_evidence(files)) == Passed()


@pytest.mark.parametrize(
    "files",
    [
        {LOG: "| when | REPORT_2026.md |\n"},
        {REPORT_FILE: "# R\n"},
        {REPORT_FILE: "# R\n", LOG: "| when | REPORT_1999.md |\n"},
        {REPORT_FILE: "# R\n", LOG: "REPORT_2026.md was written\n"},
    ],
    ids=["no report", "no log", "row names another report", "prose is not a row"],
)
def test_a_log_without_a_row_for_the_report_it_wrote_fails(files):
    assert isinstance(_log_row().evaluate(_evidence(files)), Failed)


# ---------------------------------------------------------------------------
# ledger_rows_confined
# ---------------------------------------------------------------------------

LEDGER = ".ai-state/TECH_DEBT_LEDGER.md"
HEADER = "| id | severity | class | source |\n|---|---|---|---|\n"


def _confined():
    return ledger_rows_confined(
        "c", RULE, ROLE, ledger=LEDGER, source="sentinel", classes={"complexity", "drift"}
    )


def test_a_session_that_left_the_ledger_alone_has_nothing_to_confine():
    assert isinstance(_confined().evaluate(_evidence()), NotApplicable)


def test_rows_of_the_roles_source_in_its_classes_pass():
    rows = "| td-001 | important | drift | sentinel |\n| td-002 | suggested | complexity | sentinel |\n"

    assert _confined().evaluate(_evidence({LEDGER: HEADER + rows})) == Passed()


def test_a_row_of_the_roles_source_in_another_class_fails_and_names_it():
    outcome = _confined().evaluate(
        _evidence({LEDGER: HEADER + "| td-003 | important | docs-gap | sentinel |\n"})
    )

    assert isinstance(outcome, Failed)
    assert "docs-gap" in outcome.detail


def test_rows_of_another_source_are_not_the_roles_to_confine():
    rows = "| td-004 | important | docs-gap | verifier |\n"

    assert _confined().evaluate(_evidence({LEDGER: HEADER + rows})) == Passed()


# ---------------------------------------------------------------------------
# returns_instead_of_writing
# ---------------------------------------------------------------------------


def _returns():
    return returns_instead_of_writing(
        "t", RULE, ROLE, document=DOC, pattern=re.compile(r"\b(PASS|FAIL)\b")
    )


def test_a_verdict_in_the_return_and_no_file_passes():
    assert _returns().evaluate(_evidence(role_return="Overall Verdict: FAIL")) == Passed()


def test_a_written_report_fails_even_with_a_verdict_in_the_return():
    outcome = _returns().evaluate(_evidence({DOC_PATH: "# R\n"}, role_return="FAIL"))

    assert isinstance(outcome, Failed)
    assert DOC_PATH in outcome.detail


@pytest.mark.parametrize("role_return", [None, "all done"])
def test_a_return_without_the_verdict_fails(role_return):
    assert isinstance(_returns().evaluate(_evidence(role_return=role_return)), Failed)


# ---------------------------------------------------------------------------
# workflow_security
# ---------------------------------------------------------------------------

SHA = "a" * 40
WORKFLOW = ".github/workflows/ci.yml"
CLEAN = f"""\
name: ci
on: push
permissions: {{}}
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@{SHA}
        with:
          persist-credentials: false
      - uses: ./.github/actions/local
"""


def _security():
    return workflow_security("w", RULE, ROLE)


def test_a_session_that_wrote_no_workflow_has_nothing_to_hold():
    assert isinstance(_security().evaluate(_evidence({"src/app.py": "x"})), NotApplicable)


def test_a_workflow_with_every_item_passes():
    assert _security().evaluate(_evidence({WORKFLOW: CLEAN})) == Passed()


@pytest.mark.parametrize(
    ("broken", "named"),
    [
        (CLEAN.replace(f"@{SHA}", "@v4"), "not pinned"),
        (CLEAN.replace("permissions: {}\n", ""), "permissions"),
        (CLEAN.replace("permissions: {}", "permissions: read-all"), "permissions"),
        (CLEAN.replace("    timeout-minutes: 10\n", ""), "timeout-minutes"),
        (CLEAN.replace("persist-credentials: false", "persist-credentials: true"), "persist"),
        (CLEAN.replace("        with:\n          persist-credentials: false\n", ""), "persist"),
        ("a: [unclosed", "valid YAML"),
        ("- just\n- a list\n", "workflow mapping"),
    ],
    ids=[
        "tag",
        "no permissions",
        "wide permissions",
        "no timeout",
        "persist",
        "no with",
        "yaml",
        "list",
    ],
)
def test_each_missing_security_item_fails_and_is_named(broken, named):
    outcome = _security().evaluate(_evidence({WORKFLOW: broken}))

    assert isinstance(outcome, Failed)
    assert named in outcome.detail


def test_a_reusable_workflow_job_needs_a_pin_but_no_timeout():
    reusable = (
        f"permissions: {{}}\njobs:\n  call:\n    uses: org/repo/.github/workflows/w.yml@{SHA}\n"
    )
    loose = reusable.replace(f"@{SHA}", "@main")

    assert _security().evaluate(_evidence({WORKFLOW: reusable})) == Passed()
    assert isinstance(_security().evaluate(_evidence({WORKFLOW: loose})), Failed)


# ---------------------------------------------------------------------------
# spawn_fan_out and spawn_prompts_carry
# ---------------------------------------------------------------------------


def _spawns(count, subagent="researcher", tool="Agent", prompt=""):
    return [
        ToolUse(f"s{i}", tool, {"subagent_type": subagent, "prompt": prompt}, None)
        for i in range(count)
    ]


def _fan_out():
    return spawn_fan_out("o", RULE, ROLE, subagent="researcher", wave=3, total=6)


@pytest.mark.parametrize("count", [0, 3])
def test_a_wave_or_fewer_passes(count):
    assert _fan_out().evaluate(_evidence(tool_uses=_spawns(count))) == Passed()


@pytest.mark.parametrize("count", [4, 6])
def test_more_than_a_wave_is_withheld_because_the_stream_does_not_show_waves(count):
    assert isinstance(_fan_out().evaluate(_evidence(tool_uses=_spawns(count))), Withheld)


def test_more_than_the_cap_in_all_fails():
    outcome = _fan_out().evaluate(_evidence(tool_uses=_spawns(7)))

    assert isinstance(outcome, Failed)
    assert "7" in outcome.detail


def test_only_spawns_of_the_named_subagent_count_whatever_the_tool_is_called():
    uses = _spawns(7, subagent="verifier") + _spawns(3, tool="Task")

    assert _fan_out().evaluate(_evidence(tool_uses=uses)) == Passed()
    assert isinstance(_fan_out().evaluate(_evidence(tool_uses=_spawns(7, tool="Task"))), Failed)


def _prompts():
    return spawn_prompts_carry(
        "p", RULE, ROLE, subagent="researcher", deliverable=re.compile("AUDIT_")
    )


def test_a_spawn_prompt_with_the_slug_and_the_deliverable_passes():
    prompt = f"Task slug: {SLUG}\nWrite AUDIT_lens.md"

    assert _prompts().evaluate(_evidence(tool_uses=_spawns(2, prompt=prompt))) == Passed()


def test_no_spawn_leaves_nothing_to_hold():
    assert isinstance(_prompts().evaluate(_evidence()), NotApplicable)


@pytest.mark.parametrize(
    ("prompt", "named"),
    [("Write AUDIT_lens.md", "Task slug"), (f"Task slug: {SLUG}", "AUDIT_")],
)
def test_a_prompt_missing_the_slug_or_the_deliverable_fails_and_names_it(prompt, named):
    outcome = _prompts().evaluate(_evidence(tool_uses=_spawns(1, prompt=prompt)))

    assert isinstance(outcome, Failed)
    assert named in outcome.detail


def test_a_slug_that_is_another_tasks_fails():
    prompt = "Task slug: other-task\nWrite AUDIT_lens.md"

    assert isinstance(_prompts().evaluate(_evidence(tool_uses=_spawns(1, prompt=prompt))), Failed)


# ---------------------------------------------------------------------------
# log_preserved
# ---------------------------------------------------------------------------

ROADMAP = "ROADMAP.md"
PRIOR = "- `2026-01-01` decided x"
SHOWN = f"     1\t# Roadmap\n     2\t## Decision Log\n     3\t{PRIOR}\n"


def _preserved():
    return log_preserved("d", RULE, ROLE, document="./ROADMAP.md", section="Decision Log")


def _read(path=ROADMAP):
    return ToolUse("r1", "Read", {"file_path": path}, None)


def _log_evidence(final, *, read=True):
    uses = [_read()] if read else []
    return _evidence({ROADMAP: final}, tool_uses=uses, tool_results={"r1": SHOWN})


def test_prior_entries_kept_and_one_added_pass():
    final = f"# Roadmap\n## Decision Log\n{PRIOR}\n- `2026-02-02` decided y\n"

    assert _preserved().evaluate(_log_evidence(final)) == Passed()


def test_a_rewritten_prior_entry_fails():
    final = "## Decision Log\n- `2026-01-01` decided x, reworded\n- `2026-02-02` decided y\n"

    outcome = _preserved().evaluate(_log_evidence(final))

    assert isinstance(outcome, Failed)
    assert "lost or rewrote 1" in outcome.detail


def test_a_log_that_gained_nothing_fails():
    assert isinstance(_preserved().evaluate(_log_evidence(f"## Decision Log\n{PRIOR}\n")), Failed)


def test_a_session_that_never_read_the_document_has_no_prior_log_to_compare():
    final = f"## Decision Log\n{PRIOR}\n- `2026-02-02` decided y\n"

    assert isinstance(_preserved().evaluate(_log_evidence(final, read=False)), Withheld)


def test_only_a_read_of_the_document_itself_gives_the_prior_log():
    other = _evidence(
        {ROADMAP: f"## Decision Log\n{PRIOR}\n- new\n"},
        tool_uses=[_read("README.md")],
        tool_results={"r1": SHOWN},
    )

    assert isinstance(_preserved().evaluate(other), Withheld)
