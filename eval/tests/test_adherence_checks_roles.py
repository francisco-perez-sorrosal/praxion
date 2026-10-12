"""The constructors the role check table is built from, each on a violation and on a clean session.

The script constructor runs the real ``check_state_ledgers.py`` over a real scratch
repository holding a planted ledger row, so a stubbed read or a swallowed exception
cannot produce the ``failed`` it asserts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from praxion_evals.adherence.checks_common import synthetic_evidence
from praxion_evals.adherence.checks_roles import (
    CHECKOUT_ROOT,
    Section,
    closed_tag_set,
    count_limit,
    first_line,
    has_content,
    path_scope,
    required_sections,
    script_exits_zero,
    section_body,
    title_marker_first_unmarked_last,
    tool_order,
    with_cwd,
)
from praxion_evals.adherence.model import (
    CheckErrored,
    Failed,
    NotApplicable,
    Passed,
    RuleRef,
    TaskFacts,
)
from praxion_evals.live.session import ToolUse

RULE = RuleRef("agents/researcher.md", "Constraints")
SLUG = "role-task"
DOC = "REPORT.md"
DOC_PATH = f".ai-work/{SLUG}/{DOC}"


def _use(name: str, **tool_input: str) -> ToolUse:
    return ToolUse(f"toolu_{name}_{len(tool_input)}", name, tool_input, "canary-spawn")


# ---------------------------------------------------------------------------
# Reading a document
# ---------------------------------------------------------------------------

DOCUMENT = """\
# Title

## Goal

Know the answer.

## Questions

[pending]

## Findings

### Detail

A real line.

```markdown
## Fenced heading that is not a heading
```

## Sources

- [A page](https://example.com/a)
"""


def test_a_section_runs_to_the_next_heading_as_high_or_higher():
    body = section_body(DOCUMENT, "Findings")

    assert body is not None
    assert "A real line." in "\n".join(body)
    assert "Know the answer." not in "\n".join(body)
    assert "[A page]" not in "\n".join(body)


def test_a_heading_inside_a_fenced_block_is_not_a_section():
    assert section_body(DOCUMENT, "Fenced heading that is not a heading") is None
    assert section_body(DOCUMENT, "Missing") is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (["", "[pending]", "  [not reached]"], False),
        (["### Sub heading", ""], False),
        (["", "real text"], True),
    ],
)
def test_content_is_a_line_that_is_neither_blank_a_heading_nor_a_placeholder(body, expected):
    assert has_content(body) is expected


def test_the_title_is_the_first_nonblank_line():
    assert first_line("\n\n# Report [PARTIAL]\nbody") == "# Report [PARTIAL]"
    assert first_line("") == ""


# ---------------------------------------------------------------------------
# required_sections
# ---------------------------------------------------------------------------


def _sections_check(*sections: Section):
    return required_sections(
        "sections", RULE, "researcher", document=DOC, sections=sections or (Section("Goal"),)
    )


def _evidence_with(text: str | None):
    files = {} if text is None else {DOC_PATH: text}
    return synthetic_evidence("researcher", slug=SLUG, files=files)


def test_sections_with_content_pass():
    check = _sections_check(Section("Goal"), Section("Findings"))

    assert check.evaluate(_evidence_with(DOCUMENT)) == Passed()


def test_a_section_left_as_a_placeholder_fails_and_is_named():
    outcome = _sections_check(Section("Questions")).evaluate(_evidence_with(DOCUMENT))

    assert isinstance(outcome, Failed)
    assert "Questions" in outcome.detail


def test_a_missing_section_and_a_missing_document_fail():
    check = _sections_check(Section("Absent"))

    assert isinstance(check.evaluate(_evidence_with(DOCUMENT)), Failed)
    assert isinstance(check.evaluate(_evidence_with(None)), Failed)


def test_a_section_whose_body_must_match_a_pattern_fails_without_it():
    links = re.compile(r"https?://")
    check = _sections_check(Section("Goal", links))

    assert isinstance(check.evaluate(_evidence_with(DOCUMENT)), Failed)
    assert _sections_check(Section("Sources", links)).evaluate(_evidence_with(DOCUMENT)) == Passed()


# ---------------------------------------------------------------------------
# title_marker_first_unmarked_last
# ---------------------------------------------------------------------------


def _marker_check(within_first: int = 3):
    return title_marker_first_unmarked_last(
        "marker", RULE, "verifier", document=DOC, marker="[PARTIAL]", within_first=within_first
    )


def _marker_evidence(actions, final: str | None, *, cwd: Path | None = None):
    files = {} if final is None else {DOC_PATH: final}
    evidence = synthetic_evidence("verifier", slug=SLUG, files=files, tool_uses=actions)
    return evidence if cwd is None else with_cwd(evidence, cwd)


def _write(content: str, path: str = DOC_PATH) -> ToolUse:
    return _use("Write", file_path=path, content=content)


def test_opened_marked_and_ended_unmarked_passes():
    evidence = _marker_evidence([_write("# Report [PARTIAL]\n")], "# Report\n")

    assert _marker_check().evaluate(evidence) == Passed()


@pytest.mark.parametrize(
    ("opening", "final", "fragment"),
    [
        ("# Report\n", "# Report\n", "opened without"),
        ("# Report [PARTIAL]\n", "# Report [PARTIAL]\n", "still carries"),
        ("# Report [PARTIAL]\n", None, "missing or empty"),
    ],
)
def test_each_way_to_break_the_marker_convention_fails(opening, final, fragment):
    outcome = _marker_check().evaluate(_marker_evidence([_write(opening)], final))

    assert isinstance(outcome, Failed)
    assert fragment in outcome.detail


def test_a_session_that_never_wrote_the_document_fails_and_says_why():
    outcome = _marker_check().evaluate(_marker_evidence([], "# Report\n"))

    assert isinstance(outcome, Failed)
    assert "no Write or Edit" in outcome.detail


def test_a_first_change_that_is_an_edit_does_not_record_the_opening():
    edit = _use("Edit", file_path=DOC_PATH, old_string="a", new_string="b")

    outcome = _marker_check().evaluate(_marker_evidence([edit], "# Report\n"))

    assert isinstance(outcome, Failed)
    assert "not a Write" in outcome.detail


def test_the_opening_write_must_come_within_the_first_tool_calls():
    reads = [_use("Read", file_path=f"f{i}.md") for i in range(3)]
    evidence = _marker_evidence([*reads, _write("# Report [PARTIAL]\n")], "# Report\n")

    assert isinstance(_marker_check(within_first=3).evaluate(evidence), Failed)
    assert _marker_check(within_first=4).evaluate(evidence) == Passed()


def test_an_absolute_tool_path_is_read_against_the_session_directory(tmp_path):
    absolute = str(tmp_path / DOC_PATH)
    evidence = _marker_evidence(
        [_write("# Report [PARTIAL]\n", absolute)], "# Report\n", cwd=tmp_path
    )

    assert _marker_check().evaluate(evidence) == Passed()


# ---------------------------------------------------------------------------
# tool_order
# ---------------------------------------------------------------------------

FETCH = _use("WebFetch", url="https://docs.example.com/llms.txt")
SEARCH = _use("WebSearch", query="example")


def _order_check():
    return tool_order(
        "order",
        RULE,
        "researcher",
        earlier=lambda evidence, use: use.name == "WebFetch",
        earlier_label="fetched a page",
        later=lambda evidence, use: use.name == "WebSearch",
        later_label="a search",
        earlier_sample=FETCH,
        later_sample=SEARCH,
    )


@pytest.mark.parametrize("uses", [[FETCH, SEARCH], [FETCH]])
def test_the_earlier_use_first_passes_with_or_without_the_later_one(uses):
    assert _order_check().evaluate(synthetic_evidence("researcher", tool_uses=uses)) == Passed()


def test_the_later_use_first_fails_naming_both_positions():
    outcome = _order_check().evaluate(synthetic_evidence("researcher", tool_uses=[SEARCH, FETCH]))

    assert isinstance(outcome, Failed)
    assert "tool call 1" in outcome.detail
    assert "tool call 2" in outcome.detail


def test_an_earlier_use_that_never_happens_fails_even_without_the_later_one():
    outcome = _order_check().evaluate(synthetic_evidence("researcher", tool_uses=[]))

    assert isinstance(outcome, Failed)
    assert "never" in outcome.detail


# ---------------------------------------------------------------------------
# path_scope
# ---------------------------------------------------------------------------


def _scope_check():
    return path_scope("scope", RULE, "implementer", forbidden=("tests/acceptance/", "tests/e2e"))


@pytest.mark.parametrize("path", ["tests/acceptance/test_a.py", "tests/e2e/drivers/d.py"])
def test_a_change_under_a_forbidden_path_fails(path):
    outcome = _scope_check().evaluate(synthetic_evidence("implementer", files={path: "x"}))

    assert isinstance(outcome, Failed)
    assert path in outcome.detail


@pytest.mark.parametrize("path", ["tests/acceptance_notes.md", "tests/unit/test_a.py", "src/a.py"])
def test_a_sibling_path_with_the_same_prefix_text_is_not_under_it(path):
    evidence = synthetic_evidence("implementer", files={path: "x"})

    assert _scope_check().evaluate(evidence) == Passed()


def test_a_write_call_to_a_forbidden_path_counts_without_a_file_on_disk():
    write = _use("Write", file_path="tests/e2e/x.py", content="")

    assert isinstance(
        _scope_check().evaluate(synthetic_evidence("implementer", tool_uses=[write])), Failed
    )


# ---------------------------------------------------------------------------
# closed_tag_set
# ---------------------------------------------------------------------------

REPORT = """\
# Verification Report

## Convention Compliance

### Behavioral Contract Findings

| 1 | FAIL | x.py:1 | `[BLOAT]` a finding | rule |
| 2 | WARN | y.py:2 | [SCOPE-CREEP] another, see [the rule](rules/a.md) | rule |

## Test Coverage Assessment

[NOT-A-CONTRACT-TAG] lives in another section
"""


def _tag_check():
    return closed_tag_set(
        "tags",
        RULE,
        "verifier",
        document=DOC,
        section="Behavioral Contract Findings",
        allowed={"BLOAT", "SCOPE-CREEP"},
    )


def test_tags_inside_the_closed_set_pass_and_links_and_other_sections_are_ignored():
    assert _tag_check().evaluate(_evidence_with(REPORT)) == Passed()


def test_an_invented_tag_fails_and_is_named():
    invented = REPORT.replace("[SCOPE-CREEP]", "[OVER-ENGINEERED]")

    outcome = _tag_check().evaluate(_evidence_with(invented))

    assert isinstance(outcome, Failed)
    assert "OVER-ENGINEERED" in outcome.detail


def test_a_report_without_the_section_fails():
    assert isinstance(_tag_check().evaluate(_evidence_with("# Report\n")), Failed)


# ---------------------------------------------------------------------------
# count_limit
# ---------------------------------------------------------------------------

SPAWN = _use("Agent", subagent_type="researcher")


def _limit_check():
    return count_limit(
        "limit",
        RULE,
        "roadmap-cartographer",
        matcher=lambda evidence, use: use.name == "Agent",
        limit=3,
        label="researcher spawns",
        sample=SPAWN,
    )


@pytest.mark.parametrize(("count", "expected"), [(3, Passed), (4, Failed)])
def test_a_count_over_the_limit_fails_and_at_it_passes(count, expected):
    uses = [ToolUse(f"spawn-{i}", "Agent", {}, None) for i in range(count)]

    outcome = _limit_check().evaluate(synthetic_evidence("roadmap-cartographer", tool_uses=uses))

    assert isinstance(outcome, expected)


# ---------------------------------------------------------------------------
# script_exits_zero, over a real scratch repository
# ---------------------------------------------------------------------------

LEDGER = ".ai-state/TECH_DEBT_LEDGER.md"
LEDGER_HEADER = (
    "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source"
    " | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |\n"
    f"|{'---|' * 15}\n"
)
CLEAN_LEDGER = f"# Technical Debt Ledger\n\n{LEDGER_HEADER}"
MALFORMED_ROW = "| td-001 | suggested |\n"


def _ledger_check(planted=None):
    return script_exits_zero(
        "ledger",
        RULE,
        "verifier",
        script="check_state_ledgers.py",
        arguments=("--check", "--repo-root", "{repo}"),
        planted=planted or {LEDGER: CLEAN_LEDGER + MALFORMED_ROW},
        watched=(LEDGER,),
    )


@pytest.fixture
def plugin_copy(tmp_path: Path) -> Path:
    """A plugin copy whose scripts are the checkout's own."""
    copy = tmp_path / "plugin-copy"
    copy.mkdir()
    (copy / "scripts").symlink_to(CHECKOUT_ROOT / "scripts", target_is_directory=True)
    return copy


def _scratch(tmp_path: Path, plugin: Path, ledger: str | None, *, wrote: bool = True):
    repo = tmp_path / "scratch"
    repo.mkdir(exist_ok=True)
    files = {}
    if ledger is not None:
        (repo / LEDGER).parent.mkdir(parents=True, exist_ok=True)
        (repo / LEDGER).write_text(ledger, encoding="utf-8")
        files = {LEDGER: ledger} if wrote else {}
    evidence = synthetic_evidence(
        "verifier", slug=SLUG, files=files, places=(tmp_path / "sandbox", plugin)
    )
    return with_cwd(evidence, repo)


def test_a_clean_ledger_passes(tmp_path, plugin_copy):
    evidence = _scratch(tmp_path, plugin_copy, CLEAN_LEDGER)

    assert _ledger_check().evaluate(evidence) == Passed()


def test_a_malformed_ledger_row_planted_in_a_real_repository_is_seen_as_failed(
    tmp_path, plugin_copy
):
    evidence = _scratch(tmp_path, plugin_copy, CLEAN_LEDGER + MALFORMED_ROW)

    outcome = _ledger_check().evaluate(evidence)

    assert isinstance(outcome, Failed)
    assert "field-count" in outcome.detail  # the script's own finding, not an exception fallback


def test_the_checks_own_canary_runs_the_real_script_and_is_failed():
    check = _ledger_check()

    outcome = check.evaluate(check.violation())

    assert isinstance(outcome, Failed)
    assert "field-count" in outcome.detail


def test_a_session_that_changed_no_watched_file_is_not_applicable(tmp_path, plugin_copy):
    evidence = _scratch(tmp_path, plugin_copy, CLEAN_LEDGER + MALFORMED_ROW, wrote=False)

    assert isinstance(_ledger_check().evaluate(evidence), NotApplicable)


def test_a_script_missing_from_the_plugin_copy_is_errored_never_failed(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()

    outcome = _ledger_check().evaluate(_scratch(tmp_path, bare, CLEAN_LEDGER))

    assert isinstance(outcome, CheckErrored)
    assert "not in the plugin copy" in outcome.reason


def test_a_script_error_exit_is_errored_never_failed(tmp_path):
    plugin = tmp_path / "stub-plugin"
    (plugin / "scripts").mkdir(parents=True)
    (plugin / "scripts" / "broken.py").write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
    check = script_exits_zero(
        "broken", RULE, "verifier", script="broken.py", arguments=(), planted={}
    )

    outcome = check.evaluate(_scratch(tmp_path, plugin, None))

    assert isinstance(outcome, CheckErrored)
    assert "exited 2" in outcome.reason


def test_a_session_with_no_recorded_directory_is_errored(plugin_copy):
    evidence = synthetic_evidence("verifier", slug=SLUG, places=(Path("/x"), plugin_copy))
    check = script_exits_zero(
        "any", RULE, "verifier", script="check_state_ledgers.py", arguments=(), planted={}
    )

    assert isinstance(check.evaluate(evidence), CheckErrored)


def test_the_script_runs_under_the_evals_own_interpreter(tmp_path):
    plugin = tmp_path / "echo-plugin"
    (plugin / "scripts").mkdir(parents=True)
    (plugin / "scripts" / "which.py").write_text(
        f"import sys\nsys.exit(0 if sys.version_info[:2] == {tuple(sys.version_info[:2])} else 1)\n",
        encoding="utf-8",
    )
    check = script_exits_zero(
        "which", RULE, "verifier", script="which.py", arguments=(), planted={}
    )

    assert check.evaluate(_scratch(tmp_path, plugin, None)) == Passed()


def test_the_facts_a_matcher_reads_reach_the_canary():
    facts = TaskFacts(False, False, False, None, None, "docs.example.com")
    seen = []

    def matcher(evidence, use):
        seen.append(evidence.facts.external_api_docs)
        return use.name == "WebFetch"

    check = tool_order(
        "facts",
        RULE,
        "researcher",
        earlier=matcher,
        earlier_label="fetched",
        later=lambda evidence, use: use.name == "WebSearch",
        later_label="searched",
        earlier_sample=FETCH,
        later_sample=SEARCH,
        facts=facts,
    )

    assert isinstance(check.evaluate(check.violation()), Failed)
    assert set(seen) == {"docs.example.com"}


# ---------------------------------------------------------------------------
# Documents named with a star or by repository path
# ---------------------------------------------------------------------------

REPORT_GLOB = ".ai-state/reports/REPORT_*.md"
REPORT_FILE = ".ai-state/reports/REPORT_2026.md"


def test_any_of_passes_when_one_section_has_content_and_fails_when_none_does():
    sections = (Section("One"), Section("Two"))
    check = required_sections("s", RULE, "researcher", document=DOC, sections=sections, any_of=True)
    one = synthetic_evidence("researcher", slug=SLUG, files={DOC_PATH: "## One\n\ntext\n"})
    none = synthetic_evidence("researcher", slug=SLUG, files={DOC_PATH: "## One\n\n[pending]\n"})

    assert check.evaluate(one) == Passed()
    assert isinstance(check.evaluate(none), Failed)


def test_without_any_of_every_section_is_still_required():
    sections = (Section("One"), Section("Two"))
    check = required_sections("s", RULE, "researcher", document=DOC, sections=sections)
    one = synthetic_evidence("researcher", slug=SLUG, files={DOC_PATH: "## One\n\ntext\n"})

    assert isinstance(check.evaluate(one), Failed)


def test_a_report_named_by_path_and_star_is_opened_marked_without_a_call_bound():
    check = title_marker_first_unmarked_last(
        "t", RULE, "sentinel", document=REPORT_GLOB, marker="[PARTIAL]"
    )
    opened = _use("Write", file_path=REPORT_FILE, content="# Report [PARTIAL]\n")
    late = [_use("Read", file_path="a"), _use("Read", file_path="b")] * 3 + [opened]

    done = synthetic_evidence(
        "sentinel", slug=SLUG, files={REPORT_FILE: "# Report\n"}, tool_uses=late
    )
    unmarked = _use("Write", file_path=REPORT_FILE, content="# Report\n")
    bad = synthetic_evidence(
        "sentinel", slug=SLUG, files={REPORT_FILE: "# Report\n"}, tool_uses=[unmarked]
    )

    assert check.evaluate(done) == Passed()
    assert isinstance(check.evaluate(bad), Failed)


def test_the_canary_of_a_starred_document_is_written_at_a_path_the_star_matches():
    check = required_sections(
        "s", RULE, "researcher", document=REPORT_GLOB, sections=(Section("One"),)
    )

    assert isinstance(check.evaluate(check.violation()), Failed)


def test_a_script_run_in_the_session_home_reads_the_transcripts_planted_there(tmp_path):
    check = script_exits_zero(
        "s",
        RULE,
        "researcher",
        script="check_lens_isolation.py",
        arguments=("--run", "latest", "--project-root", "{repo}"),
        planted={},
        planted_home=lambda repo: {"marker.txt": "x"},
    )

    outcome = check.evaluate(check.violation())

    assert isinstance(outcome, CheckErrored)  # no workflow run is planted: the script refuses
    assert "exited 2" in outcome.reason
