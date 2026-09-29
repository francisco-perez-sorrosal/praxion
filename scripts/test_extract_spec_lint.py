"""Tests for the design-vocabulary lint of `extract_spec.py`.

Goldens come from the rule table in that module's docstring: each rule has a
known-bad token that must fire (rule, section, line, token all asserted) and a
known-good token that must not. Extraction, `--check` and exit-code behavior
are in `test_extract_spec.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_spec as es  # noqa: E402
from _extract_spec_testkit import (  # noqa: E402
    BRIEF,
    SLUG,
    extract_path,
    make_plan,
    make_project,
    req_id,
    run_cli,
    run_main,
)

ACCEPTANCE_SECTION = "Acceptance Criteria"
BEHAVIOR_SECTION = "Behavioral Specification"


def _behavior(body: str, surface: str = "") -> str:
    return f"### Observable Surface\n\n{surface}\n\n### {req_id(1)}: A requirement\n\n{body}\n"


def _lint(
    *,
    acceptance: str = "- [ ] Plain words only.\n",
    body: str = "Plain words only.",
    surface: str = "",
    brief: str | None = BRIEF,
) -> list:
    plan = make_plan(acceptance=acceptance, behavior=_behavior(body, surface))
    return list(es.lint_spec(es.parse_spec(plan, brief)))


def _line_of(text: str, needle: str) -> int:
    return next(n for n, line in enumerate(text.splitlines(), start=1) if needle in line)


def _in_sentence(token: str) -> str:
    return f"- [ ] The tool accepts {token} today.\n"


DV02_BAD = [
    "scripts/_spec.py",
    "src/auth/session",
    "docs/v2",
    "README.md",
    "./run",
    "../up",
    "~/notes",
    "/etc/hosts",
    "docs/",
]
DV03_BAD = [
    "parse_plan",
    "RefundPolicy",
    "SPEC_MAX_LINES",
    "auth.session",
    "RefundPolicy.apply()",
    "--strict",
    "getUser",
]
PLAIN_GOOD = [
    "pass/fail",
    "input/output",
    "and/or",
    "CLI/HTTP",
    "e.g.",
    "i.e.",
    "Opus",
    "3.11",
    "v0.41.0",
    "well-known",
]


@pytest.mark.parametrize("token", DV02_BAD)
def test_path_like_tokens_are_flagged_as_paths(token):
    acceptance = _in_sentence(token)

    found = _lint(acceptance=acceptance)

    assert [(f.rule, f.token, f.section, f.req, f.severity) for f in found] == [
        ("DV02", token, ACCEPTANCE_SECTION, None, "blocking")
    ]
    assert found[0].line == _line_of(make_plan(acceptance=acceptance), token)


@pytest.mark.parametrize("token", DV03_BAD)
def test_identifier_shaped_tokens_are_flagged_as_identifiers(token):
    acceptance = _in_sentence(token)

    found = _lint(acceptance=acceptance)

    assert [(f.rule, f.token, f.section, f.req) for f in found] == [
        ("DV03", token, ACCEPTANCE_SECTION, None)
    ]
    assert found[0].line == _line_of(make_plan(acceptance=acceptance), token)


@pytest.mark.parametrize("token", PLAIN_GOOD)
def test_plain_language_slashes_versions_and_abbreviations_pass(token):
    assert _lint(acceptance=_in_sentence(token)) == []


def test_a_spaced_dash_pair_is_not_a_flag():
    assert _lint(acceptance="- [ ] It works -- even offline.\n") == []


def test_a_code_span_is_flagged_with_its_inner_text():
    acceptance = "- [ ] Run `parse_plan` first.\n"

    found = _lint(acceptance=acceptance)

    assert [(f.rule, f.token, f.line) for f in found] == [
        ("DV01", "parse_plan", _line_of(make_plan(acceptance=acceptance), "parse_plan"))
    ]


def test_a_fenced_block_is_one_finding_at_its_opening_line():
    body = "Shape:\n\n```yaml\nkey: value\nother_key: parse_plan\n```\n\ndone."

    found = _lint(body=body)

    assert [(f.rule, f.req, f.section) for f in found] == [("DV01", req_id(1), BEHAVIOR_SECTION)]
    assert found[0].line == _line_of(make_plan(behavior=_behavior(body)), "```yaml")
    assert found[0].token.startswith("```")


def test_a_seeded_bad_requirement_fires_every_rule_shape():
    body = (
        "Uses `code_span` and scripts/module.py and snake_name and CamelName and "
        "CONST_NAME and pkg.mod and call() and --flag.\n\n```\nblock\n```"
    )

    found = _lint(body=body)

    assert {f.token for f in found} >= {
        "code_span",
        "scripts/module.py",
        "snake_name",
        "CamelName",
        "CONST_NAME",
        "pkg.mod",
        "call()",
        "--flag",
    }
    assert {f.rule for f in found} == {"DV01", "DV02", "DV03"}
    assert all(f.req == req_id(1) and f.severity == "blocking" for f in found)


def test_findings_in_a_requirement_carry_its_id_and_the_source_line():
    body = "Line one is plain.\nLine two names parse_plan."

    found = _lint(body=body)

    assert [(f.req, f.token) for f in found] == [(req_id(1), "parse_plan")]
    assert found[0].line == _line_of(make_plan(behavior=_behavior(body)), "Line two")


def test_a_requirement_heading_is_linted_too():
    behavior = f"### Observable Surface\n\n### {req_id(1)}: Uses parse_plan\n\nPlain.\n"

    found = list(es.lint_spec(es.parse_spec(make_plan(behavior=behavior), BRIEF)))

    assert [(f.req, f.token) for f in found] == [(req_id(1), "parse_plan")]


def test_emphasis_markers_do_not_hide_or_create_findings():
    found = _lint(acceptance="- [ ] **The system** keeps **snake_case** words.\n")

    assert [f.token for f in found] == ["snake_case"]


# -- Declared names ---------------------------------------------------------------


def test_a_declared_name_passes_as_a_span_and_as_plain_text():
    surface = "- `parse_plan` -- the parser\n- `docs/v2` -- the docs\n- `acceptance:` -- the key"
    acceptance = "- [ ] Run `parse_plan`, read docs/v2 and set acceptance: values.\n"

    assert _lint(acceptance=acceptance, surface=surface) == []


def test_an_undeclared_name_still_fails_when_another_is_declared():
    found = _lint(
        acceptance="- [ ] Run `other_tool` and `parse_plan`.\n", surface="- `parse_plan` -- parser"
    )

    assert [f.token for f in found] == ["other_tool"]


def test_the_observable_surface_subsection_is_not_linted():
    surface = (
        "- `scripts/_spec.py` -- a file\n- `RefundPolicy.apply()` -- a call\n- `--strict` -- a flag"
    )

    assert _lint(surface=surface) == []


def test_a_name_in_plain_prose_under_observable_surface_declares_nothing():
    found = _lint(acceptance=_in_sentence("parse_plan"), surface="parse_plan is mentioned here")

    assert [f.token for f in found] == ["parse_plan"]


# -- Which text is linted -----------------------------------------------------------


def test_design_text_outside_the_spec_sections_is_never_linted():
    found = _lint()  # the fixture's design section names a file path

    assert found == []


def test_html_comments_are_removed_before_linting_and_keep_line_numbers():
    acceptance = (
        "<!-- a note about `parse_plan` and docs/v2\nspanning two lines -->\n"
        "- [ ] Plain first.\n- [ ] Names parse_plan second.\n"
    )
    plan = make_plan(acceptance=acceptance)

    found = list(es.lint_spec(es.parse_spec(plan, BRIEF)))

    assert [(f.token, f.line) for f in found] == [("parse_plan", _line_of(plan, "Names"))]


def test_key_signal_findings_are_advisory_and_use_the_brief_line():
    brief = "# Brief\n\n## Key Signals\n\nUsers want `parse_plan` in scripts/x.py.\n"

    found = _lint(brief=brief)

    assert [(f.rule, f.severity, f.section, f.req, f.line) for f in found] == [
        ("DV01", "advisory", "Key Signals", None, 5),
        ("DV02", "advisory", "Key Signals", None, 5),
    ]


def test_a_declared_name_is_exempt_in_key_signals_too():
    brief = "# Brief\n\n## Key Signals\n\nUsers want parse_plan.\n"

    assert _lint(brief=brief, surface="- `parse_plan` -- parser") == []


# -- Exit status and the extract on disk -----------------------------------------------


def _leaky_plan() -> str:
    return make_plan(acceptance="- [ ] The tool calls `parse_plan` today.\n")


def test_blocking_findings_exit_1_and_write_no_extract(tmp_path, capsys):
    make_project(tmp_path, plan=_leaky_plan())

    assert run_main(tmp_path, "--json") == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["extract"] is None
    assert payload["digest"] is None
    assert payload["removed_stale"] is False
    assert [f["rule"] for f in payload["findings"]] == ["DV01"]
    assert not extract_path(tmp_path).exists()


def test_blocking_findings_delete_a_previous_extract_and_say_so(tmp_path, capsys):
    task_dir = make_project(tmp_path)
    assert run_main(tmp_path) == 0
    assert extract_path(tmp_path).exists()
    (task_dir / "SYSTEMS_PLAN.md").write_text(_leaky_plan())
    capsys.readouterr()

    assert run_main(tmp_path, "--json") == 1

    assert json.loads(capsys.readouterr().out)["removed_stale"] is True
    assert not extract_path(tmp_path).exists()


@pytest.mark.parametrize("expected", ["DV01", "parse_plan", ACCEPTANCE_SECTION])
def test_plain_output_lists_each_finding_with_rule_location_and_token(tmp_path, capsys, expected):
    make_project(tmp_path, plan=_leaky_plan())

    assert run_main(tmp_path) == 1

    assert expected in capsys.readouterr().out


def test_check_on_a_spec_with_blocking_findings_exits_1_with_those_findings(tmp_path, capsys):
    task_dir = make_project(tmp_path)
    assert run_main(tmp_path) == 0
    before = extract_path(tmp_path).read_bytes()
    (task_dir / "SYSTEMS_PLAN.md").write_text(_leaky_plan())
    capsys.readouterr()

    assert run_main(tmp_path, "--check", "--json") == 1

    rules = [f["rule"] for f in json.loads(capsys.readouterr().out)["findings"]]
    assert rules == ["DV01"]
    assert extract_path(tmp_path).read_bytes() == before


def test_advisory_findings_never_change_the_exit_status(tmp_path, capsys):
    brief = "# Brief\n\n## Key Signals\n\nUsers want `parse_plan`.\n"
    make_project(tmp_path, brief=brief)

    assert run_main(tmp_path, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert [f["severity"] for f in payload["findings"]] == ["advisory"]
    assert extract_path(tmp_path).exists()
    assert run_main(tmp_path, "--check") == 0


def test_a_lint_clean_spec_that_declares_its_names_exits_0(tmp_path):
    surface = "- `extract_spec.py` -- the command\n- `SPEC_EXTRACT.md` -- the extract"
    acceptance = "- [ ] Running `extract_spec.py` writes SPEC_EXTRACT.md.\n"
    plan = make_plan(acceptance=acceptance, behavior=_behavior("Plain words.", surface))
    make_project(tmp_path, plan=plan)

    assert run_main(tmp_path) == 0


def test_the_leaky_spec_exits_1_as_a_process(tmp_path):
    make_project(tmp_path, plan=_leaky_plan())

    result = run_cli(SLUG, "--repo-root", str(tmp_path))

    assert result.returncode == 1
    assert "parse_plan" in result.stdout
