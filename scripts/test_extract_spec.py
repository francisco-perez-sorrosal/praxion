"""Tests for `extract_spec.py` -- the spec-extraction command.

The failure mode this closes: design text reaching the acceptance designer
through the spec, or an extract that has drifted from the spec it claims to
carry. The extract must hold exactly three sections, verbatim; `--check` must
notice any drift; a broken input must exit 2, distinct from a clean or a leaky
spec. Expected values come from the contract in the module docstring, not from
running the implementation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPTS_DIR / "extract_spec.py"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_spec as es  # noqa: E402

SLUG = "demo-task"
EXTRACT_NAME = "SPEC_EXTRACT.md"


# -- Fixtures and helpers -------------------------------------------------


def _req(number: int) -> str:
    """Requirement id built at run time so no id literal sits in this file."""
    return f"REQ-{number:02d}"


def _plan(
    *,
    acceptance: str = "- [ ] A customer who asks for a refund gets the money back.\n",
    behavior: str | None = None,
    extra: str = "",
) -> str:
    """A plan holding spec sections and design sections, all spec text plain."""
    if behavior is None:
        behavior = (
            "### Observable Surface\n\n"
            "- `extract_spec.py` -- the command\n\n"
            f"### {_req(1)}: Refunds are returned\n\n"
            "**When** a customer asks for a refund\n"
            "**the system** returns the money\n"
            "**so that** trust is kept.\n"
        )
    return (
        "# Plan: Demo\n\n"
        "## Goal\n\nGoal text.\n\n"
        f"## Acceptance Criteria\n\n{acceptance}\n"
        f"## Behavioral Specification\n\n{behavior}\n"
        "## Architecture\n\nDESIGNMARKER the adapter layer lives in scripts/x.py\n\n"
        "## Risk Assessment\n\nRISKMARKER\n" + extra
    )


BRIEF = (
    "# Task Brief\n\n"
    "## Key Signals\n\nSIGNALMARKER users want refunds.\n\n"
    "## Scope\n\nSCOPEMARKER touches billing.\n"
)


def _project(
    root: Path, plan: str | None = None, brief: str | None = BRIEF, slug: str = SLUG
) -> Path:
    """Create `.ai-work/<slug>/` under `root`; returns the task directory."""
    task_dir = root / ".ai-work" / slug
    task_dir.mkdir(parents=True)
    (task_dir / "SYSTEMS_PLAN.md").write_text(_plan() if plan is None else plan)
    if brief is not None:
        (task_dir / "TASK_BRIEF.md").write_text(brief)
    return task_dir


def _main(root: Path, *flags: str, slug: str = SLUG) -> int:
    return es.main([slug, "--repo-root", str(root), *flags])


def _extract_path(root: Path) -> Path:
    return root / ".ai-work" / SLUG / EXTRACT_NAME


def _headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


# -- The extract holds the spec and nothing else ----------------------------


def test_extract_holds_exactly_the_three_spec_sections(tmp_path, capsys):
    _project(tmp_path)

    assert _main(tmp_path) == 0
    text = _extract_path(tmp_path).read_text()

    assert _headings(text) == [
        "## Key Signals",
        "## Acceptance Criteria",
        "## Behavioral Specification",
    ]
    assert "SIGNALMARKER" in text
    assert "A customer who asks for a refund gets the money back." in text
    assert "**the system** returns the money" in text
    for leaked in ("DESIGNMARKER", "RISKMARKER", "SCOPEMARKER", "Goal text", "## Architecture"):
        assert leaked not in text


def test_extract_header_names_the_slug_the_generator_the_digest_and_the_sources(tmp_path):
    _project(tmp_path)

    assert _main(tmp_path) == 0
    lines = _extract_path(tmp_path).read_text().splitlines()

    assert lines[0] == f"# Spec Extract — {SLUG}"
    header = "\n".join(lines[:6])
    assert "extract_spec.py" in header
    assert "do not edit" in header
    assert re.search(r"\*\*Spec digest:\*\* sha256:[0-9a-f]{12}\b", header)
    assert "**Sources:** SYSTEMS_PLAN.md; TASK_BRIEF.md" in header


def test_headings_inside_fenced_blocks_do_not_split_or_start_sections():
    plan = _plan(extra="")
    plan = plan.replace(
        "DESIGNMARKER the adapter layer lives in scripts/x.py",
        "```markdown\n## Acceptance Criteria\n\nFAKE_CRITERIA\n\n## Behavioral Specification\n```",
    )

    spec = es.parse_spec(plan, BRIEF)

    assert "FAKE_CRITERIA" not in spec.acceptance.body
    assert "A customer who asks" in spec.acceptance.body


def test_a_fenced_block_inside_a_spec_section_stays_inside_it():
    behavior = (
        f"### {_req(1)}: Shape\n\nThe file looks like:\n\n"
        "```markdown\n## Not A Section\n```\n\nafter the block\n"
    )

    spec = es.parse_spec(_plan(behavior=behavior), BRIEF)

    assert "## Not A Section" in spec.behavior.body
    assert "after the block" in spec.behavior.body


def test_html_comments_are_stripped_from_every_section(tmp_path):
    plan = _plan(
        acceptance="<!-- author note -->\n- [ ] Refunds work. <!-- inline -->\n"
        "<!-- multi\nline\nnote -->\n- [ ] Second criterion.\n"
    )
    _project(tmp_path, plan=plan, brief=BRIEF.replace("users want", "<!-- gone -->users want"))

    assert _main(tmp_path) == 0
    body = _extract_path(tmp_path).read_text().split("## Key Signals", 1)[1]

    for removed in ("author note", "inline", "multi", "gone", "<!--", "-->"):
        assert removed not in body
    assert "- [ ] Refunds work." in body
    assert "- [ ] Second criterion." in body
    assert "\n\n\n" not in body


def test_a_comment_only_line_leaves_no_blank_line_behind():
    plan = _plan(acceptance="- [ ] First.\n<!-- note -->\n- [ ] Second.\n")

    spec = es.parse_spec(plan, BRIEF)

    assert spec.acceptance.body == "- [ ] First.\n- [ ] Second."


# -- The digest ---------------------------------------------------------------


def test_digest_is_sha256_of_the_body_and_tracks_the_body(tmp_path):
    _project(tmp_path)
    assert _main(tmp_path) == 0
    first = _extract_path(tmp_path).read_text()

    body = first[first.index("## Key Signals") :]
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
    assert f"**Spec digest:** sha256:{expected}" in first

    assert _main(tmp_path) == 0
    assert _extract_path(tmp_path).read_text() == first  # reproducible

    plan_path = tmp_path / ".ai-work" / SLUG / "SYSTEMS_PLAN.md"
    plan_path.write_text(plan_path.read_text().replace("returns the money", "returns cash"))
    assert _main(tmp_path) == 0
    assert f"sha256:{expected}" not in _extract_path(tmp_path).read_text()


# -- Key Signals from the brief -----------------------------------------------


def test_absent_brief_renders_the_none_form(tmp_path):
    _project(tmp_path, brief=None)

    assert _main(tmp_path) == 0
    text = _extract_path(tmp_path).read_text()

    assert "_None: TASK_BRIEF.md absent._" in text
    assert "TASK_BRIEF.md absent" in text.split("## Key Signals")[0]


def test_a_brief_without_key_signals_renders_a_none_form_not_scope_text(tmp_path):
    _project(tmp_path, brief="# Brief\n\n## Scope\n\nSCOPEMARKER only.\n")

    assert _main(tmp_path) == 0
    text = _extract_path(tmp_path).read_text()

    assert "SCOPEMARKER" not in text
    assert "_None:" in text.split("## Acceptance Criteria")[0]


# -- --check ------------------------------------------------------------------


def test_check_passes_on_a_fresh_extract_and_writes_nothing(tmp_path):
    _project(tmp_path)
    assert _main(tmp_path) == 0
    before = _extract_path(tmp_path).read_bytes()

    assert _main(tmp_path, "--check") == 0

    assert _extract_path(tmp_path).read_bytes() == before


def test_check_reports_stale_after_a_spec_edit_and_never_rewrites(tmp_path, capsys):
    _project(tmp_path)
    assert _main(tmp_path) == 0
    plan_path = tmp_path / ".ai-work" / SLUG / "SYSTEMS_PLAN.md"
    plan_path.write_text(plan_path.read_text().replace("returns the money", "returns cash"))
    before = _extract_path(tmp_path).read_bytes()
    capsys.readouterr()

    assert _main(tmp_path, "--check", "--json") == 1

    payload = json.loads(capsys.readouterr().out)
    assert [f["rule"] for f in payload["findings"]] == ["stale-extract"]
    assert payload["findings"][0]["severity"] == "blocking"
    assert _extract_path(tmp_path).read_bytes() == before


def test_check_reports_stale_after_a_hand_edit(tmp_path):
    _project(tmp_path)
    assert _main(tmp_path) == 0
    path = _extract_path(tmp_path)
    path.write_text(path.read_text().replace("Refunds are returned", "Refunds are ignored"))

    assert _main(tmp_path, "--check") == 1


def test_check_reports_a_missing_extract_and_does_not_create_one(tmp_path, capsys):
    _project(tmp_path)

    assert _main(tmp_path, "--check", "--json") == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["rule"] == "stale-extract"
    assert payload["extract"] is None
    assert not _extract_path(tmp_path).exists()


# -- Input errors exit 2 and name the input ------------------------------------


def test_missing_plan_exits_2_naming_the_plan(tmp_path, capsys):
    (tmp_path / ".ai-work" / SLUG).mkdir(parents=True)

    assert _main(tmp_path) == 2

    assert "SYSTEMS_PLAN.md" in capsys.readouterr().err
    assert not _extract_path(tmp_path).exists()


@pytest.mark.parametrize(
    ("plan", "named"),
    [
        (
            _plan().replace("## Acceptance Criteria", "## Criteria Of Sorts"),
            "Acceptance Criteria",
        ),
        (_plan(acceptance="\n<!-- only a comment -->\n\n"), "Acceptance Criteria"),
        (
            _plan().replace("## Behavioral Specification", "## Behaviour Notes"),
            "Behavioral Specification",
        ),
        (_plan(behavior="\n<!-- nothing here -->\n"), "Behavioral Specification"),
        (
            _plan(behavior="### Observable Surface\n\n- `extract_spec.py` -- the command\n"),
            "requirement block",
        ),
    ],
    ids=[
        "acceptance-absent",
        "acceptance-empty",
        "behavior-absent",
        "behavior-empty",
        "no-requirement-block",
    ],
)
def test_broken_spec_input_exits_2_naming_the_missing_part(tmp_path, capsys, plan, named):
    _project(tmp_path, plan=plan)

    assert _main(tmp_path) == 2

    assert named in capsys.readouterr().err
    assert not _extract_path(tmp_path).exists()


def test_input_errors_are_not_findings_and_print_no_json_payload(tmp_path, capsys):
    (tmp_path / ".ai-work" / SLUG).mkdir(parents=True)

    assert _main(tmp_path, "--json") == 2

    assert capsys.readouterr().out == ""


# -- --json ----------------------------------------------------------------------


def test_json_payload_shape_on_a_clean_write(tmp_path, capsys):
    _project(tmp_path)

    assert _main(tmp_path, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"schema", "slug", "extract", "digest", "removed_stale", "findings"}
    assert payload["schema"] == 1
    assert payload["slug"] == SLUG
    assert payload["extract"] == f".ai-work/{SLUG}/{EXTRACT_NAME}"
    assert payload["removed_stale"] is False
    assert payload["findings"] == []
    text = _extract_path(tmp_path).read_text()
    assert payload["digest"] == re.search(r"sha256:[0-9a-f]{12}", text).group(0)


def test_json_keeps_logs_off_stdout(tmp_path, capsys):
    _project(tmp_path)

    assert _main(tmp_path, "--json", "--verbose") == 0

    json.loads(capsys.readouterr().out)  # raises if a log line leaked in


# -- Root resolution ---------------------------------------------------------------


def test_explicit_repo_root_works_from_an_unrelated_cwd(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    _project(project)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert _main(project) == 0
    assert _extract_path(project).exists()


def test_root_defaults_to_the_git_toplevel_of_the_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _project(repo)
    nested = repo / "deep" / "dir"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert es.main([SLUG]) == 0
    assert _extract_path(repo).exists()


def test_outside_any_repo_without_a_root_exits_2_and_never_uses_the_script_location(
    tmp_path, monkeypatch, capsys
):
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    assert es.main([SLUG]) == 2

    assert "--repo-root" in capsys.readouterr().err
    assert not (SCRIPTS_DIR.parent / ".ai-work" / SLUG / EXTRACT_NAME).exists()


def test_a_repo_root_that_is_not_a_directory_exits_2(tmp_path, capsys):
    assert es.main([SLUG, "--repo-root", str(tmp_path / "missing")]) == 2

    assert "missing" in capsys.readouterr().err


@pytest.mark.parametrize("slug", ["../escape", "a/b", ".hidden", ""])
def test_a_slug_that_could_leave_the_task_directory_is_rejected(tmp_path, slug):
    with pytest.raises(SystemExit) as raised:
        es.main([slug, "--repo-root", str(tmp_path)])

    assert raised.value.code == 2


# -- The command as a process ------------------------------------------------------


def _cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd
    )


def test_the_three_exit_statuses_as_a_process(tmp_path):
    _project(tmp_path)
    root = str(tmp_path)

    clean = _cli(SLUG, "--repo-root", root)
    fresh = _cli(SLUG, "--repo-root", root, "--check")
    (_extract_path(tmp_path)).unlink()
    missing = _cli(SLUG, "--repo-root", root, "--check")
    broken = _cli("no-such-task", "--repo-root", root)

    assert (clean.returncode, fresh.returncode, missing.returncode, broken.returncode) == (
        0,
        0,
        1,
        2,
    )
    assert "stale-extract" in missing.stdout
    assert "no-such-task" in broken.stderr


def test_the_script_is_an_executable_with_a_portable_shebang():
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text().splitlines()[0] == "#!/usr/bin/env python3"


def test_help_works_under_the_ambient_interpreter():
    result = _cli("--help")

    assert result.returncode == 0
    assert "--check" in result.stdout


_LEGACY_INTERPRETER = "/usr/bin/python3"


@pytest.mark.skipif(
    not Path(_LEGACY_INTERPRETER).exists(),
    reason=f"{_LEGACY_INTERPRETER} not present on this machine",
)
def test_the_command_runs_under_a_legacy_bare_interpreter(tmp_path):
    """The command reaches managed projects as a symlink run by the ambient
    `python3`, whose version this project does not control: runtime `X | Y`
    unions or `match` anywhere in the module would break it at import."""
    _project(tmp_path)

    helped = subprocess.run(
        [_LEGACY_INTERPRETER, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    ran = subprocess.run(
        [_LEGACY_INTERPRETER, str(SCRIPT), SLUG, "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert helped.returncode == 0, helped.stderr
    assert ran.returncode == 0, ran.stderr
    assert _extract_path(tmp_path).exists()


def test_the_command_resolves_its_sibling_modules_through_a_symlink(tmp_path):
    link = tmp_path / "bin" / "extract_spec.py"
    link.parent.mkdir()
    link.symlink_to(SCRIPT)
    project = tmp_path / "project"
    project.mkdir()
    _project(project)

    result = subprocess.run(
        [sys.executable, str(link), SLUG, "--repo-root", str(project)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


# -- Design-vocabulary lint ----------------------------------------------------
#
# Goldens come from the rule table in the module docstring: each rule has a
# known-bad token that must fire (rule, section, line, token all asserted) and a
# known-good token that must not.

ACCEPTANCE_SECTION = "Acceptance Criteria"
BEHAVIOR_SECTION = "Behavioral Specification"


def _behavior(body: str, surface: str = "") -> str:
    return f"### Observable Surface\n\n{surface}\n\n### {_req(1)}: A requirement\n\n{body}\n"


def _lint(
    *,
    acceptance: str = "- [ ] Plain words only.\n",
    body: str = "Plain words only.",
    surface: str = "",
    brief: str | None = BRIEF,
) -> list:
    plan = _plan(acceptance=acceptance, behavior=_behavior(body, surface))
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
    assert found[0].line == _line_of(_plan(acceptance=acceptance), token)


@pytest.mark.parametrize("token", DV03_BAD)
def test_identifier_shaped_tokens_are_flagged_as_identifiers(token):
    acceptance = _in_sentence(token)

    found = _lint(acceptance=acceptance)

    assert [(f.rule, f.token, f.section, f.req) for f in found] == [
        ("DV03", token, ACCEPTANCE_SECTION, None)
    ]
    assert found[0].line == _line_of(_plan(acceptance=acceptance), token)


@pytest.mark.parametrize("token", PLAIN_GOOD)
def test_plain_language_slashes_versions_and_abbreviations_pass(token):
    assert _lint(acceptance=_in_sentence(token)) == []


def test_a_spaced_dash_pair_is_not_a_flag():
    assert _lint(acceptance="- [ ] It works -- even offline.\n") == []


def test_a_code_span_is_flagged_with_its_inner_text():
    acceptance = "- [ ] Run `parse_plan` first.\n"

    found = _lint(acceptance=acceptance)

    assert [(f.rule, f.token, f.line) for f in found] == [
        ("DV01", "parse_plan", _line_of(_plan(acceptance=acceptance), "parse_plan"))
    ]


def test_a_fenced_block_is_one_finding_at_its_opening_line():
    body = "Shape:\n\n```yaml\nkey: value\nother_key: parse_plan\n```\n\ndone."

    found = _lint(body=body)

    assert [(f.rule, f.req, f.section) for f in found] == [("DV01", _req(1), BEHAVIOR_SECTION)]
    assert found[0].line == _line_of(_plan(behavior=_behavior(body)), "```yaml")
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
    assert all(f.req == _req(1) and f.severity == "blocking" for f in found)


def test_findings_in_a_requirement_carry_its_id_and_the_source_line():
    body = "Line one is plain.\nLine two names parse_plan."

    found = _lint(body=body)

    assert [(f.req, f.token) for f in found] == [(_req(1), "parse_plan")]
    assert found[0].line == _line_of(_plan(behavior=_behavior(body)), "Line two")


def test_a_requirement_heading_is_linted_too():
    behavior = f"### Observable Surface\n\n### {_req(1)}: Uses parse_plan\n\nPlain.\n"

    found = list(es.lint_spec(es.parse_spec(_plan(behavior=behavior), BRIEF)))

    assert [(f.req, f.token) for f in found] == [(_req(1), "parse_plan")]


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
    plan = _plan(acceptance=acceptance)

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
    return _plan(acceptance="- [ ] The tool calls `parse_plan` today.\n")


def test_blocking_findings_exit_1_and_write_no_extract(tmp_path, capsys):
    _project(tmp_path, plan=_leaky_plan())

    assert _main(tmp_path, "--json") == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["extract"] is None
    assert payload["digest"] is None
    assert payload["removed_stale"] is False
    assert [f["rule"] for f in payload["findings"]] == ["DV01"]
    assert not _extract_path(tmp_path).exists()


def test_blocking_findings_delete_a_previous_extract_and_say_so(tmp_path, capsys):
    task_dir = _project(tmp_path)
    assert _main(tmp_path) == 0
    assert _extract_path(tmp_path).exists()
    (task_dir / "SYSTEMS_PLAN.md").write_text(_leaky_plan())
    capsys.readouterr()

    assert _main(tmp_path, "--json") == 1

    assert json.loads(capsys.readouterr().out)["removed_stale"] is True
    assert not _extract_path(tmp_path).exists()


def test_plain_output_lists_each_finding_with_rule_location_and_token(tmp_path, capsys):
    _project(tmp_path, plan=_leaky_plan())

    assert _main(tmp_path) == 1

    out = capsys.readouterr().out
    for expected in ("DV01", "parse_plan", ACCEPTANCE_SECTION):
        assert expected in out


def test_check_on_a_spec_with_blocking_findings_exits_1_with_those_findings(tmp_path, capsys):
    task_dir = _project(tmp_path)
    assert _main(tmp_path) == 0
    before = _extract_path(tmp_path).read_bytes()
    (task_dir / "SYSTEMS_PLAN.md").write_text(_leaky_plan())
    capsys.readouterr()

    assert _main(tmp_path, "--check", "--json") == 1

    rules = [f["rule"] for f in json.loads(capsys.readouterr().out)["findings"]]
    assert rules == ["DV01"]
    assert _extract_path(tmp_path).read_bytes() == before


def test_advisory_findings_never_change_the_exit_status(tmp_path, capsys):
    brief = "# Brief\n\n## Key Signals\n\nUsers want `parse_plan`.\n"
    _project(tmp_path, brief=brief)

    assert _main(tmp_path, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert [f["severity"] for f in payload["findings"]] == ["advisory"]
    assert _extract_path(tmp_path).exists()
    assert _main(tmp_path, "--check") == 0


def test_a_lint_clean_spec_that_declares_its_names_exits_0(tmp_path):
    surface = "- `extract_spec.py` -- the command\n- `SPEC_EXTRACT.md` -- the extract"
    acceptance = "- [ ] Running `extract_spec.py` writes SPEC_EXTRACT.md.\n"
    plan = _plan(acceptance=acceptance, behavior=_behavior("Plain words.", surface))
    _project(tmp_path, plan=plan)

    assert _main(tmp_path) == 0


def test_the_leaky_spec_exits_1_as_a_process(tmp_path):
    _project(tmp_path, plan=_leaky_plan())

    result = _cli(SLUG, "--repo-root", str(tmp_path))

    assert result.returncode == 1
    assert "parse_plan" in result.stdout
