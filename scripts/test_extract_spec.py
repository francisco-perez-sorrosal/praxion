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

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_spec as es  # noqa: E402
from _extract_spec_testkit import (  # noqa: E402
    BRIEF,
    EXTRACT_NAME,
    SCRIPT,
    SCRIPTS_DIR,
    SLUG,
    extract_path,
    make_plan,
    make_project,
    req_id,
    run_cli,
    run_main,
)


def _headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


# -- The extract holds the spec and nothing else ----------------------------


def test_extract_holds_exactly_the_three_spec_sections(tmp_path, capsys):
    make_project(tmp_path)

    assert run_main(tmp_path) == 0
    text = extract_path(tmp_path).read_text()

    assert _headings(text) == [
        "## Key Signals",
        "## Acceptance Criteria",
        "## Behavioral Specification",
    ]
    assert "SIGNALMARKER" in text
    assert "A customer who asks for a refund gets the money back." in text
    assert "**the system** returns the money" in text


@pytest.mark.parametrize(
    "leaked", ["DESIGNMARKER", "RISKMARKER", "SCOPEMARKER", "Goal text", "## Architecture"]
)
def test_extract_carries_no_text_from_outside_the_spec_sections(tmp_path, leaked):
    make_project(tmp_path)

    assert run_main(tmp_path) == 0

    assert leaked not in extract_path(tmp_path).read_text()


def test_extract_header_names_the_slug_the_generator_the_digest_and_the_sources(tmp_path):
    make_project(tmp_path)

    assert run_main(tmp_path) == 0
    lines = extract_path(tmp_path).read_text().splitlines()

    assert lines[0] == f"# Spec Extract — {SLUG}"
    header = "\n".join(lines[:6])
    assert "extract_spec.py" in header
    assert "do not edit" in header
    assert re.search(r"\*\*Spec digest:\*\* sha256:[0-9a-f]{12}\b", header)
    assert "**Sources:** SYSTEMS_PLAN.md; TASK_BRIEF.md" in header


def test_headings_inside_fenced_blocks_do_not_split_or_start_sections():
    plan = make_plan(extra="")
    plan = plan.replace(
        "DESIGNMARKER the adapter layer lives in scripts/x.py",
        "```markdown\n## Acceptance Criteria\n\nFAKE_CRITERIA\n\n## Behavioral Specification\n```",
    )

    spec = es.parse_spec(plan, BRIEF)

    assert "FAKE_CRITERIA" not in spec.acceptance.body
    assert "A customer who asks" in spec.acceptance.body


def test_a_fenced_block_inside_a_spec_section_stays_inside_it():
    behavior = (
        f"### {req_id(1)}: Shape\n\nThe file looks like:\n\n"
        "```markdown\n## Not A Section\n```\n\nafter the block\n"
    )

    spec = es.parse_spec(make_plan(behavior=behavior), BRIEF)

    assert "## Not A Section" in spec.behavior.body
    assert "after the block" in spec.behavior.body


def _commented_extract_body(root: Path) -> str:
    """The extract body of a spec whose criteria and key signals carry HTML comments."""
    plan = make_plan(
        acceptance="<!-- author note -->\n- [ ] Refunds work. <!-- inline -->\n"
        "<!-- multi\nline\nnote -->\n- [ ] Second criterion.\n"
    )
    make_project(root, plan=plan, brief=BRIEF.replace("users want", "<!-- gone -->users want"))
    assert run_main(root) == 0
    return extract_path(root).read_text().split("## Key Signals", 1)[1]


@pytest.mark.parametrize("removed", ["author note", "inline", "multi", "gone", "<!--", "-->"])
def test_html_comment_text_never_reaches_the_extract(tmp_path, removed):
    assert removed not in _commented_extract_body(tmp_path)


def test_html_comments_are_stripped_from_every_section(tmp_path):
    body = _commented_extract_body(tmp_path)

    assert "- [ ] Refunds work." in body
    assert "- [ ] Second criterion." in body
    assert "\n\n\n" not in body


def test_a_comment_only_line_leaves_no_blank_line_behind():
    plan = make_plan(acceptance="- [ ] First.\n<!-- note -->\n- [ ] Second.\n")

    spec = es.parse_spec(plan, BRIEF)

    assert spec.acceptance.body == "- [ ] First.\n- [ ] Second."


# -- The digest ---------------------------------------------------------------


def test_digest_is_sha256_of_the_body_and_tracks_the_body(tmp_path):
    make_project(tmp_path)
    assert run_main(tmp_path) == 0
    first = extract_path(tmp_path).read_text()

    body = first[first.index("## Key Signals") :]
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
    assert f"**Spec digest:** sha256:{expected}" in first

    assert run_main(tmp_path) == 0
    assert extract_path(tmp_path).read_text() == first  # reproducible

    plan_path = tmp_path / ".ai-work" / SLUG / "SYSTEMS_PLAN.md"
    plan_path.write_text(plan_path.read_text().replace("returns the money", "returns cash"))
    assert run_main(tmp_path) == 0
    assert f"sha256:{expected}" not in extract_path(tmp_path).read_text()


# -- Key Signals from the brief -----------------------------------------------


def test_absent_brief_renders_the_none_form(tmp_path):
    make_project(tmp_path, brief=None)

    assert run_main(tmp_path) == 0
    text = extract_path(tmp_path).read_text()

    assert "_None: TASK_BRIEF.md absent._" in text
    assert "TASK_BRIEF.md absent" in text.split("## Key Signals")[0]


def test_a_brief_without_key_signals_renders_a_none_form_not_scope_text(tmp_path):
    make_project(tmp_path, brief="# Brief\n\n## Scope\n\nSCOPEMARKER only.\n")

    assert run_main(tmp_path) == 0
    text = extract_path(tmp_path).read_text()

    assert "SCOPEMARKER" not in text
    assert "_None:" in text.split("## Acceptance Criteria")[0]


def _brief_with(key_signals_heading: str) -> str:
    """A brief whose sibling sections sit at the same heading level as the given one."""
    level = key_signals_heading.split()[0]
    return (
        f"# Brief\n\n{level} Task Intent\n\nINTENTMARKER.\n\n"
        f"{key_signals_heading}\n\nSIGNALMARKER users want refunds.\n\n"
        f"{level} Health Guards\n\nGUARDMARKER stays green.\n"
    )


@pytest.mark.parametrize(
    "heading",
    ["## Key Signals", "## Key Signals (acceptance, observable)", "### Key Signals"],
    ids=["exact-h2", "h2-with-qualifier", "template-h3"],
)
def test_key_signals_are_found_under_every_documented_heading_shape(tmp_path, capsys, heading):
    make_project(tmp_path, brief=_brief_with(heading))

    assert run_main(tmp_path, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    key_signals = extract_path(tmp_path).read_text().split("## Acceptance Criteria")[0]
    assert "SIGNALMARKER" in key_signals
    assert "INTENTMARKER" not in key_signals
    assert "GUARDMARKER" not in key_signals
    assert payload["findings"] == []


@pytest.mark.parametrize(
    "heading",
    ["## Scope", "## Key Signalling", "## Signals"],
    ids=["no-such-section", "longer-word", "shorter-title"],
)
def test_a_brief_with_no_matching_key_signals_section_reports_an_advisory_finding(
    tmp_path, capsys, heading
):
    make_project(tmp_path, brief=_brief_with(heading))

    assert run_main(tmp_path, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert [(f["rule"], f["severity"], f["section"]) for f in payload["findings"]] == [
        ("key-signals-missing", "advisory", "Key Signals")
    ]
    assert "TASK_BRIEF.md" in payload["findings"][0]["message"]
    assert "_None:" in extract_path(tmp_path).read_text().split("## Acceptance Criteria")[0]


def test_an_empty_key_signals_section_is_reported_like_a_missing_one(tmp_path, capsys):
    make_project(
        tmp_path, brief="# Brief\n\n## Key Signals\n\n<!-- to be filled -->\n\n## Scope\n\nx\n"
    )

    assert run_main(tmp_path, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert [f["rule"] for f in payload["findings"]] == ["key-signals-missing"]


def test_an_absent_brief_is_not_a_finding(tmp_path, capsys):
    make_project(tmp_path, brief=None)

    assert run_main(tmp_path, "--json") == 0

    assert json.loads(capsys.readouterr().out)["findings"] == []


# -- --check ------------------------------------------------------------------


def test_check_passes_on_a_fresh_extract_and_writes_nothing(tmp_path):
    make_project(tmp_path)
    assert run_main(tmp_path) == 0
    before = extract_path(tmp_path).read_bytes()

    assert run_main(tmp_path, "--check") == 0

    assert extract_path(tmp_path).read_bytes() == before


def test_check_reports_stale_after_a_spec_edit_and_never_rewrites(tmp_path, capsys):
    make_project(tmp_path)
    assert run_main(tmp_path) == 0
    plan_path = tmp_path / ".ai-work" / SLUG / "SYSTEMS_PLAN.md"
    plan_path.write_text(plan_path.read_text().replace("returns the money", "returns cash"))
    before = extract_path(tmp_path).read_bytes()
    capsys.readouterr()

    assert run_main(tmp_path, "--check", "--json") == 1

    payload = json.loads(capsys.readouterr().out)
    assert [f["rule"] for f in payload["findings"]] == ["stale-extract"]
    assert payload["findings"][0]["severity"] == "blocking"
    assert extract_path(tmp_path).read_bytes() == before


def test_check_reports_stale_after_a_hand_edit(tmp_path):
    make_project(tmp_path)
    assert run_main(tmp_path) == 0
    path = extract_path(tmp_path)
    path.write_text(path.read_text().replace("Refunds are returned", "Refunds are ignored"))

    assert run_main(tmp_path, "--check") == 1


def test_check_reports_a_missing_extract_and_does_not_create_one(tmp_path, capsys):
    make_project(tmp_path)

    assert run_main(tmp_path, "--check", "--json") == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["rule"] == "stale-extract"
    assert payload["extract"] is None
    assert not extract_path(tmp_path).exists()


# -- Input errors exit 2 and name the input ------------------------------------


def test_missing_plan_exits_2_naming_the_plan(tmp_path, capsys):
    (tmp_path / ".ai-work" / SLUG).mkdir(parents=True)

    assert run_main(tmp_path) == 2

    assert "SYSTEMS_PLAN.md" in capsys.readouterr().err
    assert not extract_path(tmp_path).exists()


@pytest.mark.parametrize(
    ("plan", "named"),
    [
        (
            make_plan().replace("## Acceptance Criteria", "## Criteria Of Sorts"),
            "Acceptance Criteria",
        ),
        (make_plan(acceptance="\n<!-- only a comment -->\n\n"), "Acceptance Criteria"),
        (
            make_plan().replace("## Behavioral Specification", "## Behaviour Notes"),
            "Behavioral Specification",
        ),
        (make_plan(behavior="\n<!-- nothing here -->\n"), "Behavioral Specification"),
        (
            make_plan(behavior="### Observable Surface\n\n- `extract_spec.py` -- the command\n"),
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
    make_project(tmp_path, plan=plan)

    assert run_main(tmp_path) == 2

    assert named in capsys.readouterr().err
    assert not extract_path(tmp_path).exists()


def test_input_errors_are_not_findings_and_print_no_json_payload(tmp_path, capsys):
    (tmp_path / ".ai-work" / SLUG).mkdir(parents=True)

    assert run_main(tmp_path, "--json") == 2

    assert capsys.readouterr().out == ""


# -- --json ----------------------------------------------------------------------


def test_json_payload_shape_on_a_clean_write(tmp_path, capsys):
    make_project(tmp_path)

    assert run_main(tmp_path, "--json") == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"schema", "slug", "extract", "digest", "removed_stale", "findings"}
    assert payload["schema"] == 1
    assert payload["slug"] == SLUG
    assert payload["extract"] == f".ai-work/{SLUG}/{EXTRACT_NAME}"
    assert payload["removed_stale"] is False
    assert payload["findings"] == []
    text = extract_path(tmp_path).read_text()
    assert payload["digest"] == re.search(r"sha256:[0-9a-f]{12}", text).group(0)


def test_json_keeps_logs_off_stdout(tmp_path, capsys):
    make_project(tmp_path)

    assert run_main(tmp_path, "--json", "--verbose") == 0

    json.loads(capsys.readouterr().out)  # raises if a log line leaked in


# -- Root resolution ---------------------------------------------------------------


def test_explicit_repo_root_works_from_an_unrelated_cwd(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    make_project(project)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert run_main(project) == 0
    assert extract_path(project).exists()


def test_root_defaults_to_the_git_toplevel_of_the_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    make_project(repo)
    nested = repo / "deep" / "dir"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert es.main([SLUG]) == 0
    assert extract_path(repo).exists()


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


def test_the_three_exit_statuses_as_a_process(tmp_path):
    make_project(tmp_path)
    root = str(tmp_path)

    clean = run_cli(SLUG, "--repo-root", root)
    fresh = run_cli(SLUG, "--repo-root", root, "--check")
    (extract_path(tmp_path)).unlink()
    missing = run_cli(SLUG, "--repo-root", root, "--check")
    broken = run_cli("no-such-task", "--repo-root", root)

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
    result = run_cli("--help")

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
    make_project(tmp_path)

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
    assert extract_path(tmp_path).exists()


def test_the_command_resolves_its_sibling_modules_through_a_symlink(tmp_path):
    link = tmp_path / "bin" / "extract_spec.py"
    link.parent.mkdir()
    link.symlink_to(SCRIPT)
    project = tmp_path / "project"
    project.mkdir()
    make_project(project)

    result = subprocess.run(
        [sys.executable, str(link), SLUG, "--repo-root", str(project)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
