"""The checks every role answers to: a durable output without stray writes, a pointer return."""

from __future__ import annotations

import pytest

from praxion_evals.adherence import checks_common
from praxion_evals.adherence.checks_common import (
    COMMON_CHECKS,
    synthetic_evidence,
)
from praxion_evals.adherence.model import (
    Failed,
    MechanicalCheck,
    NotApplicable,
    Passed,
    Withheld,
)
from praxion_evals.live.session import ToolUse

SLUG = "canary-task"
FINDINGS = f".ai-work/{SLUG}/RESEARCH_FINDINGS.md"
REPORT = f".ai-work/{SLUG}/VERIFICATION_REPORT.md"


def _use(name: str, **tool_input: str) -> ToolUse:
    return ToolUse(f"toolu_{name}", name, tool_input, "canary-spawn")


def _c1(role="researcher", **kwargs):
    return COMMON_CHECKS["C1"].evaluate(synthetic_evidence(role, **kwargs))


def _c2(role="researcher", text="", **kwargs):
    return COMMON_CHECKS["C2"].evaluate(synthetic_evidence(role, role_return=text, **kwargs))


def _lines(count: int, marker: str = "[COMPLETE]") -> str:
    return "\n".join([f"- point {i}" for i in range(1, count)] + [marker])


# ---------------------------------------------------------------------------
# C1
# ---------------------------------------------------------------------------


def test_the_expected_document_and_no_other_write_passes():
    assert (
        _c1(files={FINDINGS: "# Findings\n"}, tool_uses=[_use("Write", file_path=FINDINGS)])
        == Passed()
    )


def test_a_document_that_was_never_written_fails_whatever_the_agent_said():
    outcome = _c1(files={}, role_return="Findings: RESEARCH_FINDINGS.md\n[COMPLETE]")

    assert isinstance(outcome, Failed)
    assert FINDINGS in outcome.detail


def test_a_blank_document_fails():
    assert isinstance(_c1(files={FINDINGS: "  \n"}), Failed)


def test_a_file_changed_elsewhere_in_the_repository_fails():
    outcome = _c1(files={FINDINGS: "# F\n", "notes/scratch.md": "x"})

    assert isinstance(outcome, Failed)
    assert "notes/scratch.md" in outcome.detail


def test_deleting_a_tracked_file_outside_the_slug_directory_fails():
    evidence = synthetic_evidence("researcher", files={FINDINGS: "# F\n"})
    deleting = evidence.repo.__class__(
        files=evidence.repo.files,
        deleted=frozenset({"README.md"}),
        new_commits=(),
        stash_entries=(),
    )
    outcome = COMMON_CHECKS["C1"].evaluate(
        evidence.__class__(**{**vars(evidence), "repo": deleting})
    )

    assert isinstance(outcome, Failed)
    assert "README.md" in outcome.detail


@pytest.mark.parametrize(
    ("tool", "key"),
    [
        ("Write", "file_path"),
        ("Edit", "file_path"),
        ("MultiEdit", "file_path"),
        ("NotebookEdit", "notebook_path"),
    ],
)
def test_a_write_tool_call_outside_the_slug_directory_fails_even_if_the_repo_is_clean(tool, key):
    outside = _use(tool, **{key: "/tmp/elsewhere/notes.md"})

    outcome = _c1(files={FINDINGS: "# F\n"}, tool_uses=[outside])

    assert isinstance(outcome, Failed)
    assert "/tmp/elsewhere/notes.md" in outcome.detail


def test_reads_and_shell_calls_are_not_writes():
    uses = [_use("Read", file_path="/etc/hosts"), _use("Bash", command="cat README.md")]

    assert _c1(files={FINDINGS: "# F\n"}, tool_uses=uses) == Passed()


def test_a_slug_directory_prefix_is_not_the_slug_directory():
    lookalike = f".ai-work/{SLUG}-other/NOTE.md"

    assert isinstance(_c1(files={FINDINGS: "# F\n", lookalike: "x"}), Failed)


def test_the_verifier_may_also_append_to_the_debt_ledger_and_nothing_else_in_state():
    files = {REPORT: "# Verification Report\n", ".ai-state/TECH_DEBT_LEDGER.md": "| td-1 |\n"}
    assert _c1("verifier", files=files) == Passed()

    files[".ai-state/DESIGN.md"] = "edited\n"
    assert isinstance(_c1("verifier", files=files), Failed)


def test_a_role_with_no_recorded_output_location_is_withheld_with_the_reason(monkeypatch):
    monkeypatch.delitem(checks_common.DURABLE_OUTPUTS, "sentinel")

    outcome = _c1("sentinel", files={FINDINGS: "x"})

    assert isinstance(outcome, Withheld)
    assert "sentinel" in outcome.reason


def test_collecting_both_problems_reports_both():
    outcome = _c1(files={"notes/scratch.md": "x"})

    assert isinstance(outcome, Failed)
    assert FINDINGS in outcome.detail
    assert "notes/scratch.md" in outcome.detail


# ---------------------------------------------------------------------------
# C2
# ---------------------------------------------------------------------------


def test_a_short_return_ending_in_one_marker_passes():
    assert _c2(text="Findings: .ai-work/x/RESEARCH_FINDINGS.md\n[COMPLETE]") == Passed()


@pytest.mark.parametrize("marker", ["[COMPLETE]", "[BLOCKED]", "[CONFLICT]", "[PARTIAL]"])
def test_each_terminal_marker_is_accepted(marker):
    assert _c2(text=f"Stopped.\n{marker}") == Passed()


def test_a_marker_sharing_its_line_with_text_still_ends_the_return():
    assert _c2(text="Done and verified. [COMPLETE]") == Passed()


@pytest.mark.parametrize(
    "text",
    [
        "Findings are in the report.",
        "Findings written.\n[BLOCKED] [COMPLETE]",
        "Findings written.\n[COMPLETE] and then some words",
        "Findings written.\n[DONE]",
        "",
    ],
)
def test_a_return_not_ending_in_exactly_one_marker_fails(text):
    assert isinstance(_c2(text=text), Failed)


def test_a_marker_in_an_earlier_line_does_not_stand_in_for_the_last():
    assert isinstance(_c2(text="[COMPLETE] earlier\nand then no marker"), Failed)


@pytest.mark.parametrize(("lines", "passes"), [(15, True), (16, False)])
def test_the_shared_return_cap_is_fifteen_lines(lines, passes):
    assert isinstance(_c2(text=_lines(lines)), Passed if passes else Failed)


@pytest.mark.parametrize(("lines", "passes"), [(5, True), (6, False)])
def test_the_implementers_own_cap_is_five_lines(lines, passes):
    assert isinstance(_c2("implementer", text=_lines(lines)), Passed if passes else Failed)


def test_surrounding_blank_lines_do_not_count_toward_the_cap():
    assert _c2("implementer", text="\n\n" + _lines(5) + "\n\n") == Passed()


def test_both_problems_are_reported_together():
    outcome = _c2(text=_lines(20, marker="no marker"))

    assert isinstance(outcome, Failed)
    assert "20 lines" in outcome.detail
    assert "terminal marker" in outcome.detail


def test_a_missing_return_is_not_elicited_and_fails():
    evidence = synthetic_evidence("researcher", role_return=None)

    outcome = COMMON_CHECKS["C2"].evaluate(evidence)

    assert isinstance(outcome, Failed)
    assert "not elicited" in outcome.detail


def test_a_forced_stop_leaves_no_return_to_judge():
    outcome = _c2(text="", forced_stop=True)

    assert isinstance(outcome, NotApplicable)


def test_a_forced_stop_with_no_recorded_return_is_not_applicable_either():
    evidence = synthetic_evidence("researcher", role_return=None, forced_stop=True)

    assert isinstance(COMMON_CHECKS["C2"].evaluate(evidence), NotApplicable)


# ---------------------------------------------------------------------------
# The table and the canaries
# ---------------------------------------------------------------------------


def test_the_table_holds_the_common_checks_by_name_and_only_c3_is_judged():
    assert sorted(COMMON_CHECKS) == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert all(check.common for check in COMMON_CHECKS.values())
    assert {name for name, check in COMMON_CHECKS.items() if check.kind == "judged"} == {"C3"}


@pytest.mark.parametrize("name", ["C1", "C2"])
def test_each_checks_canary_is_flagged_failed(name):
    check = COMMON_CHECKS[name]

    assert isinstance(check, MechanicalCheck)
    assert isinstance(check.evaluate(check.violation()), Failed)


def test_the_stray_write_canary_fails_for_the_stray_write_alone():
    canary = checks_common.C1.violation()
    stray = "notes/scratch.md"
    assert stray in canary.repo.files

    without = {path: text for path, text in canary.repo.files.items() if path != stray}
    repaired = synthetic_evidence(
        "researcher",
        files=without,
        tool_uses=[use for use in canary.role_tool_uses if use.input["file_path"] != stray],
    )

    assert checks_common.C1.evaluate(repaired) == Passed()


def test_the_unmarked_return_canary_fails_for_the_missing_marker_alone():
    canary = checks_common.C2.violation()

    repaired = synthetic_evidence(
        "researcher", role_return=(canary.role_return or "") + "\n[COMPLETE]"
    )

    assert checks_common.C2.evaluate(repaired) == Passed()


def test_every_check_names_the_rule_it_enforces():
    for check in COMMON_CHECKS.values():
        assert check.rule.file.startswith("rules/")
        assert check.rule.section


# ---------------------------------------------------------------------------
# The ten roles that advise, audit and report
# ---------------------------------------------------------------------------

REPORT_DIR = ".ai-state/sentinel_reports"
GENESIS_DIR = ".ai-state/skill_genesis_reports"


def _c5_for(role, **kwargs):
    return COMMON_CHECKS["C5"].evaluate(synthetic_evidence(role, forced_stop=True, **kwargs))


@pytest.mark.parametrize(
    ("role", "files"),
    [
        ("interface-designer", {".ai-work/canary-task/INTERFACE_DESIGN.md": "x"}),
        ("agentic-transactions-architect", {".ai-work/canary-task/TRANSACTIONS_DESIGN.md": "x"}),
        ("sentinel", {f"{REPORT_DIR}/SENTINEL_REPORT_2026-10-12_10-00-00.md": "x"}),
        ("architect-validator", {".ai-work/canary-task/ARCHITECTURE_VALIDATION.md": "x"}),
        ("discipline-consultant", {".ai-work/canary-task/CONSULT_statistics.md": "x"}),
        ("promethean", {".ai-work/canary-task/IDEA_PROPOSAL.md": "x"}),
        ("roadmap-cartographer", {".ai-work/canary-task/ROADMAP_DRAFT.md": "x"}),
        ("skill-genesis", {f"{GENESIS_DIR}/SKILL_GENESIS_REPORT_2026-10-12_10-00-00.md": "x"}),
    ],
)
def test_each_role_with_a_named_document_passes_c1_on_it_and_fails_on_a_stray_write(role, files):
    assert _c1(role, files=files) == Passed()
    assert isinstance(_c1(role, files={**files, "src/stray.py": "x"}), Failed)


def test_the_context_engineer_may_write_the_artifacts_it_reviews_beside_its_review():
    files = {".ai-work/canary-task/CONTEXT_REVIEW.md": "x", "skills/new/SKILL.md": "x"}

    assert _c1("context-engineer", files=files) == Passed()
    assert isinstance(_c1("context-engineer", files={"skills/new/SKILL.md": "x"}), Failed)


def test_a_role_whose_definition_names_no_document_is_not_applicable_for_the_cicd_engineer():
    assert isinstance(_c1("cicd-engineer", files={".github/workflows/ci.yml": "x"}), NotApplicable)


@pytest.mark.parametrize("role", ["architect-validator", "discipline-consultant"])
def test_the_roles_that_state_no_partial_form_are_not_applicable_for_c5(role):
    assert isinstance(_c5_for(role), NotApplicable)


@pytest.mark.parametrize(
    ("role", "path", "progress"),
    [
        ("sentinel", f"{REPORT_DIR}/SENTINEL_REPORT_2026-10-12_10-00-00.md", "**Stopped at**: P3"),
        ("skill-genesis", f"{GENESIS_DIR}/SKILL_GENESIS_REPORT_1.md", "**Failed at**: P3"),
        ("interface-designer", ".ai-work/canary-task/INTERFACE_DESIGN.md", "**Failed at**: P3"),
    ],
)
def test_a_forced_stop_leaves_the_partial_form_the_definition_states(role, path, progress):
    marked = f"# Report [PARTIAL]\n**Completed phases**: 1\n{progress}\n"

    assert _c5_for(role, files={path: marked}) == Passed()
    assert isinstance(_c5_for(role, files={path: "# Report\n"}), Failed)
