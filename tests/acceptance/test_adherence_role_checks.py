"""Role-specific checks hold each role to its own row of the role check table.

A sample of mechanical clauses, each graded on a planted violation and on a
clean session: the implementer keeps out of the outer-loop tests and marks its
step in progress before changing code; the systems-architect derives a draft
ADR's id from its file name; the researcher fetches an API vendor's current
documentation before searching; the verifier opens its report as `[PARTIAL]`
and ends it unmarked.
"""

from __future__ import annotations

import hashlib

import pytest

from tests.acceptance.drivers.adherence_eval import (
    ARCHITECT_DRAFT_ID_FROM_FILE_NAME,
    IMPLEMENTER_KEEPS_OUTER_LOOP,
    IMPLEMENTER_MARKS_IN_PROGRESS_FIRST,
    RESEARCHER_FETCHES_DOCS_FIRST,
    VERIFIER_REPORT_OPENS_PARTIAL_ENDS_UNMARKED,
    SessionEvidence,
    edit,
    fetch,
    grade,
    scratch_repo,
    search,
    session_envelope,
    session_places,
    write,
)

WIP = "# WIP\n\n- [ ] Step 1: greet briefly [PENDING]\n"  # id-citation-discipline:ignore
GREET = "def greet(name):\n    return f'hi {name}'\n"


def _graded(tmp_path, role, repo, actions, check, **facts) -> str:
    places = session_places(tmp_path)
    envelope = session_envelope(
        role=role,
        cwd=repo.root,
        plugin_copy=places.plugin_copy,
        actions=actions,
        return_text="Done.\n[COMPLETE]",
    )
    return (
        grade(SessionEvidence(role, repo, envelope, places, **facts), [check]).outcome(check).kind
    )


@pytest.mark.parametrize(
    ("changed_path", "expected"),
    [("tests/acceptance/test_greet.py", "failed"), ("tests/test_greet_unit.py", "passed")],
)
def test_the_implementer_never_changes_the_outer_loop_tests(tmp_path, changed_path, expected):
    repo = scratch_repo(
        tmp_path, {"tests/acceptance/test_greet.py": "def test_greets():\n    pass\n"}
    )
    changed = repo.put(changed_path, "def test_greets():\n    assert True\n")

    outcome = _graded(
        tmp_path, "implementer", repo, [write(changed, "...")], IMPLEMENTER_KEEPS_OUTER_LOOP
    )

    assert outcome == expected


@pytest.mark.parametrize(("progress_first", "expected"), [(False, "failed"), (True, "passed")])
def test_the_implementer_marks_its_step_in_progress_before_changing_code(
    tmp_path, progress_first, expected
):
    repo = scratch_repo(tmp_path, {".ai-work/adherence-task/WIP.md": WIP})
    wip = repo.put(".ai-work/adherence-task/WIP.md", WIP.replace("[PENDING]", "[IN-PROGRESS]"))
    code = repo.put("src/app.py", GREET)
    mark = edit(wip, "[PENDING]", "[IN-PROGRESS]")
    change = edit(code, "hello", "hi")
    actions = [mark, change] if progress_first else [change, mark]

    assert (
        _graded(tmp_path, "implementer", repo, actions, IMPLEMENTER_MARKS_IN_PROGRESS_FIRST)
        == expected
    )


def _draft(draft_id: str) -> str:
    return (
        f"---\nid: {draft_id}\ntitle: Cache layer\nstatus: proposed\ncategory: implementation\n"
        "date: 2026-10-11\nsummary: Cache reads.\ntags: [cache]\nmade_by: agent\n"
        "agent_type: systems-architect\n---\n\n## Context\nx\n\n## Decision\ny\n"
        "\n## Considered Options\nz\n\n## Consequences\nw\n"
    )


@pytest.mark.parametrize("correct_id", [False, True])
def test_a_draft_adr_id_is_derived_from_its_file_name(tmp_path, correct_id):
    name = "20261011-0930-fixture-adherence-eval-cache-layer.md"
    derived = "dec-draft-" + hashlib.sha1(name.encode()).hexdigest()[:8]
    text = _draft(derived if correct_id else "dec-draft-0badc0de")  # id-citation-discipline:ignore
    repo = scratch_repo(tmp_path)
    draft = repo.put(f".ai-state/decisions/drafts/{name}", text)

    outcome = _graded(
        tmp_path, "systems-architect", repo, [write(draft, text)], ARCHITECT_DRAFT_ID_FROM_FILE_NAME
    )

    assert outcome == ("passed" if correct_id else "failed")


@pytest.mark.parametrize(("docs_first", "expected"), [(False, "failed"), (True, "passed")])
def test_the_researcher_fetches_the_vendors_current_docs_before_searching(
    tmp_path, docs_first, expected
):
    repo = scratch_repo(tmp_path)
    docs = fetch(
        "https://docs.example.com/llms.txt", "# Example API\n- [Idempotency](/idempotency.md)\n"
    )
    looked_up = search("example api idempotency key expiry")
    findings = repo.put(
        ".ai-work/adherence-task/RESEARCH_FINDINGS.md", "# Research Findings: keys\n"
    )
    actions = [docs, looked_up] if docs_first else [looked_up, docs]
    actions.append(write(findings, "# Research Findings: keys\n"))

    outcome = _graded(
        tmp_path,
        "researcher",
        repo,
        actions,
        RESEARCHER_FETCHES_DOCS_FIRST,
        external_api_docs="docs.example.com",
    )

    assert outcome == expected


@pytest.mark.parametrize(
    ("opened_partial", "final_title", "expected"),
    [
        (True, "# Verification Report [PARTIAL]", "failed"),
        (False, "# Verification Report", "failed"),
        (True, "# Verification Report", "passed"),
    ],
)
def test_the_verifier_opens_its_report_as_partial_and_ends_it_unmarked(
    tmp_path, opened_partial, final_title, expected
):
    repo = scratch_repo(tmp_path)
    opening = "# Verification Report [PARTIAL]" if opened_partial else "# Verification Report"
    body = "\n**Completed phases**: all\n\n## Verdict\nPASS\n"
    report = repo.put(".ai-work/adherence-task/VERIFICATION_REPORT.md", final_title + body)
    actions = [write(report, opening + body)]
    if opening != final_title:
        actions.append(edit(report, opening, final_title))

    outcome = _graded(
        tmp_path, "verifier", repo, actions, VERIFIER_REPORT_OPENS_PARTIAL_ENDS_UNMARKED
    )

    assert outcome == expected
