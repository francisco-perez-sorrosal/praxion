"""Tests for `check_footprint_criteria.py` -- the git edge and the command.

The grammars and the finding table are tested where they live, in
`test__footprint_grammar.py` and `test__markdown_tables.py`; the pure judge, in
`test_check_footprint_criteria_judge.py`. This file runs the command in real
temporary git repositories, in this process (so the mutation sensor sees it), and
once through a symlink in another directory, as a PATH-installed copy runs.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_footprint_criteria as cfc  # noqa: E402
from _footprint_testkit import (  # noqa: E402
    BUDGET_COMMAND,
    CRITERIA_HEADER,
    DECLARATION_HEADER,
    LOG_HEADER,
    PROMPT_COMMAND,
    REGISTRY_HEADER,
    criterion_row,
    log_row,
    plan,
    registry_row,
    table,
)

SCRIPT = Path(__file__).resolve().parent / "check_footprint_criteria.py"


def test_script_is_an_executable_python3_command():
    source = SCRIPT.read_text(encoding="utf-8")

    assert source.startswith("#!/usr/bin/env python3\n")
    assert os.access(SCRIPT, os.X_OK), "the script is not executable"


def test_docstring_points_at_the_grammar_it_does_not_restate():
    docstring = ast.get_docstring(ast.parse(SCRIPT.read_text(encoding="utf-8")))

    assert "_footprint_grammar.py" in docstring


# --- the command: real temporary repositories -----------------------------------------------

SLUG = "demo"
PROMPT_REGISTRY = registry_row("prompt-size", "agents/*.md, !agents/README.md", PROMPT_COMMAND)
CRITERION = criterion_row()  # FC-01 on prompt-size, relative to a baseline
FINDING_KEYS = ["code", "severity", "footprint", "criterion", "reason", "message"]
ENVELOPE_KEYS = [
    *("schema", "slug", "stage", "active", "registry", "base_ref", "moved"),
    *("criteria", "not_measured", "measurements", "findings"),
]
GIT_ENV = {
    **os.environ,
    **{"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com"},
    **{"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"},
    **{"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
}


def git(repo, *args):
    done = subprocess.run(
        ["git", *args], cwd=repo, env=GIT_ENV, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def short_head(repo, ref="HEAD"):
    return git(repo, "rev-parse", "--short=8", ref)


def write(repo, relative, text):
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_change(repo, relative="agents/a.md", text="changed\n"):
    write(repo, relative, text)
    git(repo, "add", relative)
    git(repo, "commit", "-q", "-m", f"change {relative}")


def write_plan(repo, *criteria, declared=()):
    spec = plan(
        table(CRITERIA_HEADER, *criteria) if criteria else None,
        table(DECLARATION_HEADER, *declared) if declared else None,
    )
    write(repo, f".ai-work/{SLUG}/SYSTEMS_PLAN.md", spec)


def write_log(repo, *rows):
    write(repo, f".ai-work/{SLUG}/MEASUREMENTS.md", table(LOG_HEADER, *rows))


def log_rows(baseline_head, final_head, command=PROMPT_COMMAND):
    return (
        log_row(phase="baseline", value="398 lines", head=baseline_head, command=command),
        log_row(phase="final", value="399 lines", head=final_head, command=command),
    )


@pytest.fixture
def repo(tmp_path):
    """A repository on branch `work`, one commit past `main`, with a measured, fresh footprint."""
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    write(root, ".gitignore", ".ai-work/\n")
    write(root, "agents/a.md", "a\n")
    write(root, "agents/README.md", "readme\n")
    write(root, "docs/x.md", "x\n")
    write(root, ".ai-state/FOOTPRINTS.md", table(REGISTRY_HEADER, PROMPT_REGISTRY))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    base = short_head(root)
    git(root, "checkout", "-q", "-b", "work")
    commit_change(root)
    write_plan(root, CRITERION)
    write_log(root, *log_rows(base, short_head(root)))
    return root


def cli(capsys, repo, *args, stage="verify"):
    """Run the command in this process (so the mutation sensor sees it); return code, json, stderr."""
    code = cfc.main([SLUG, "--stage", stage, "--repo-root", str(repo), "--json", *args])
    captured = capsys.readouterr()
    return code, (json.loads(captured.out) if captured.out else None), captured.err


def test_cli_exit_codes_and_json_envelope(repo, capsys):
    code, data, _ = cli(capsys, repo)

    assert code == 0
    assert list(data) == ENVELOPE_KEYS
    assert (data["schema"], data["slug"], data["stage"]) == (1, SLUG, "verify")
    assert (data["active"], data["registry"]) == (True, True)
    assert data["base_ref"] == git(repo, "rev-parse", "main")
    assert data["moved"] == [{"footprint": "prompt-size", "paths": ["agents/a.md"]}]
    assert data["criteria"] == [
        {
            "id": "FC-01",
            "footprint": "prompt-size",
            "metric": "lines in the longest prompt",
            "comparator": "at or below",
            "limit": "400 lines",
            "against": {"kind": "baseline", "text": "398 lines"},
            "command": "python3 scripts/check_agent_prompt_size.py --json",
        }
    ]
    assert data["not_measured"] == []
    assert [(m["criterion"], m["phase"], m["value"]) for m in data["measurements"]] == [
        ("FC-01", "baseline", "398 lines"),
        ("FC-01", "final", "399 lines"),
    ]
    assert data["measurements"][0]["reading"] == {"kind": "measured", "reason": None}
    assert data["findings"] == []


def test_a_not_measured_declaration_reaches_the_envelope(repo, capsys):
    write_plan(repo, CRITERION, declared=("| spawn-count | counts a finished run only |",))

    _, data, _ = cli(capsys, repo, stage="spec")

    assert data["not_measured"] == [
        {"footprint": "spawn-count", "reason": "counts a finished run only"}
    ]


def test_canary_fails_a_missing_final_row_with_exit_1_and_six_keyed_findings(repo, capsys):
    write_log(repo, log_rows(short_head(repo, "main"), short_head(repo))[0])

    code, data, _ = cli(capsys, repo)

    assert code == 1
    assert list(data["findings"][0]) == FINDING_KEYS
    assert (data["findings"][0]["code"], data["findings"][0]["reason"]) == ("FP03", "missing-final")


def test_canary_flags_a_missing_plan_with_exit_2_naming_it(repo, capsys):
    (repo / f".ai-work/{SLUG}/SYSTEMS_PLAN.md").unlink()

    code, data, err = cli(capsys, repo)

    assert (code, data) == (2, None)
    assert "SYSTEMS_PLAN.md" in err


def test_canary_flags_a_plan_with_no_acceptance_criteria_section(repo, capsys):
    write(repo, f".ai-work/{SLUG}/SYSTEMS_PLAN.md", "# Plan\n\n## Goal\n\nx\n")

    code, _, err = cli(capsys, repo)

    assert code == 2
    assert "## Acceptance Criteria" in err


def test_canary_flags_a_plan_that_is_not_utf8(repo, capsys):
    (repo / f".ai-work/{SLUG}/SYSTEMS_PLAN.md").write_bytes(b"\xff\xfe")

    code, _, err = cli(capsys, repo)

    assert code == 2
    assert "SYSTEMS_PLAN.md" in err


@pytest.mark.parametrize(
    ("stage", "args"),
    [("plan", ()), ("verify", ("--paths", "agents/a.md")), ("plan", ("--paths", "/abs/a.md"))],
    ids=["plan-needs-paths", "verify-rejects-paths", "paths-must-be-relative"],
)
def test_canary_rejects_a_bad_paths_argument(repo, capsys, stage, args):
    with pytest.raises(SystemExit) as stop:
        cli(capsys, repo, *args, stage=stage)

    assert stop.value.code == 2


def test_canary_flags_a_slug_that_walks_out_of_the_ai_work_directory(repo, capsys):
    with pytest.raises(SystemExit) as stop:
        cfc.main(["../escape", "--repo-root", str(repo)])

    assert stop.value.code == 2
    assert "slug" in capsys.readouterr().err


def test_canary_flags_a_directory_that_is_not_a_repository(tmp_path, capsys):
    plain = tmp_path / "plain"
    write(plain, f".ai-work/{SLUG}/SYSTEMS_PLAN.md", plan(table(CRITERIA_HEADER, CRITERION)))

    code, _, err = cli(capsys, plain, stage="spec")

    assert code == 2
    assert "git" in err


# --- freshness against real history ---------------------------------------------------------


def edit_tracked(repo):
    write(repo, "agents/a.md", "edited after the measurement\n")


def add_untracked(repo):
    write(repo, "agents/new.md", "new work\n")


def commit_a_change(repo):
    commit_change(repo, text="committed after the measurement\n")


@pytest.mark.parametrize(
    "move", [commit_a_change, edit_tracked, add_untracked],
    ids=["committed", "uncommitted-edit", "untracked-new-file"],
)  # fmt: skip
def test_canary_flags_a_final_row_followed_by_a_change_to_the_paths(repo, capsys, move):
    move(repo)

    code, data, _ = cli(capsys, repo)

    assert code == 1
    assert [f["reason"] for f in data["findings"]] == ["stale-final"]


@pytest.mark.parametrize("path", ["docs/x.md", "agents/README.md", ".ai-state/notes.md"])
def test_good_twin_a_change_outside_the_paths_leaves_the_final_fresh(repo, capsys, path):
    write(repo, path, "unrelated\n")

    code, data, _ = cli(capsys, repo)

    assert (code, data["findings"]) == (0, [])


def test_canary_flags_a_baseline_row_taken_after_a_change_to_the_paths(repo, capsys):
    after_the_change = short_head(repo)
    write_log(repo, *log_rows(after_the_change, after_the_change))

    code, data, _ = cli(capsys, repo)

    assert code == 1
    assert [f["reason"] for f in data["findings"]] == ["late-baseline"]


def test_canary_flags_a_head_that_names_no_commit(repo, capsys):
    write_log(repo, *log_rows(short_head(repo, "main"), "deadbeef"))

    code, data, _ = cli(capsys, repo)

    assert code == 1
    assert [f["reason"] for f in data["findings"]] == ["stale-final"]


def test_a_rename_out_of_the_paths_counts_as_moving_the_old_path(repo, capsys):
    git(repo, "mv", "agents/a.md", "docs/a.md")

    _, data, _ = cli(capsys, repo)

    assert data["moved"] == [{"footprint": "prompt-size", "paths": ["agents/a.md"]}]


def test_an_untracked_new_file_under_a_registered_path_is_moved_work(repo, capsys):
    write_plan(repo, criterion_row(footprint="listing-tokens", command=BUDGET_COMMAND))
    add_untracked(repo)

    _, data, _ = cli(capsys, repo)

    assert data["moved"][0]["paths"] == ["agents/a.md", "agents/new.md"]
    assert ("FP01", "unbounded") in {(f["code"], f["reason"]) for f in data["findings"]}


# --- the base ref ---------------------------------------------------------------------------


def test_canary_flags_an_unresolvable_default_base_with_exit_2_naming_the_flag(repo, capsys):
    git(repo, "branch", "-m", "main", "trunk")

    code, _, err = cli(capsys, repo)

    assert code == 2
    assert "--base-ref" in err


def test_good_twin_an_explicit_base_ref_replaces_the_default(repo, capsys):
    base = short_head(repo, "main")
    git(repo, "branch", "-m", "main", "trunk")

    code, data, _ = cli(capsys, repo, "--base-ref", base)

    assert (code, data["base_ref"]) == (0, base)


@pytest.mark.parametrize("ref", ["no-such-ref", "--output=x"])
def test_canary_flags_a_base_ref_that_is_no_commit(repo, capsys, ref):
    code, _, err = cli(capsys, repo, f"--base-ref={ref}")

    assert code == 2
    assert "--base-ref" in err


def test_the_spec_stage_needs_no_base(repo, capsys):
    git(repo, "branch", "-m", "main", "trunk")

    code, data, _ = cli(capsys, repo, stage="spec")

    assert (code, data["base_ref"], data["moved"]) == (0, None, [])


# --- stages ---------------------------------------------------------------------------------


def test_the_spec_stage_ignores_the_measurement_log(repo, capsys):
    write(repo, f".ai-work/{SLUG}/MEASUREMENTS.md", "this is not a table\n")

    code, data, _ = cli(capsys, repo, stage="spec")

    assert (code, data["measurements"], data["findings"]) == (0, [], [])


def test_the_plan_stage_reads_the_declared_paths_as_moved(repo, capsys):
    write_plan(repo, criterion_row(footprint="listing-tokens", command=BUDGET_COMMAND))

    code, data, _ = cli(capsys, repo, "--paths", "./agents/b.md", "docs/x.md", stage="plan")

    assert code == 0  # FP01 only warns
    assert data["moved"] == [{"footprint": "prompt-size", "paths": ["agents/b.md"]}]
    assert ("FP01", "warn") in {(f["code"], f["severity"]) for f in data["findings"]}


def test_the_inactive_check_is_a_no_op_through_the_cli(repo, capsys):
    (repo / ".ai-state/FOOTPRINTS.md").unlink()
    write_plan(repo)
    write_log(repo, *log_rows("not-hex", "worse"))

    code, data, _ = cli(capsys, repo)

    assert (code, data["active"], data["registry"], data["findings"]) == (0, False, False, [])


@pytest.mark.parametrize("base_args", [(), ("--base-ref", "no-such-ref")])
def test_an_inactive_check_exits_0_whatever_the_base_ref(repo, capsys, base_args):
    (repo / ".ai-state/FOOTPRINTS.md").unlink()
    write_plan(repo)
    git(repo, "branch", "-m", "main", "trunk")

    code, data, _ = cli(capsys, repo, *base_args)

    assert (code, data["active"], data["base_ref"], data["findings"]) == (0, False, None, [])


def test_the_text_report_names_each_finding_and_the_verdict(repo, capsys):
    write_log(repo)
    code = cfc.main([SLUG, "--repo-root", str(repo)])

    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL FP03 missing-final" in out
    assert "FC-01" in out


def test_the_text_report_of_an_inactive_check_says_so(repo, capsys):
    (repo / ".ai-state/FOOTPRINTS.md").unlink()
    write_plan(repo)

    code = cfc.main([SLUG, "--repo-root", str(repo)])

    assert code == 0
    assert "inactive" in capsys.readouterr().out


# --- the repository root, and what the command never does -----------------------------------


def test_the_root_is_the_git_toplevel_of_the_working_directory(repo, capsys, monkeypatch):
    monkeypatch.chdir(repo / "docs")

    code = cfc.main([SLUG, "--json"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["registry"] is True


def test_a_command_named_in_a_table_or_the_registry_is_never_run(repo, capsys):
    marker = "touch executed.marker"
    registry = registry_row("prompt-size", "agents/*.md", f"`{marker}`")
    write(repo, ".ai-state/FOOTPRINTS.md", table(REGISTRY_HEADER, registry))
    write_plan(repo, criterion_row(command=f"`{marker}`"))
    write_log(repo, *log_rows(short_head(repo, "main"), short_head(repo), command=f"`{marker}`"))

    code, _, _ = cli(capsys, repo)

    assert code == 0
    assert not list(repo.rglob("executed.marker"))
    assert not list(Path.cwd().glob("executed.marker"))


# --- the errors an operator reads -----------------------------------------------------------


def test_canary_flags_a_repo_root_that_is_not_a_directory(repo, capsys):
    code = cfc.main([SLUG, "--repo-root", str(repo / "nowhere")])

    assert code == 2
    assert "not a directory" in capsys.readouterr().err


def test_canary_flags_a_plan_that_cannot_be_read(repo, capsys):
    plan_path = repo / f".ai-work/{SLUG}/SYSTEMS_PLAN.md"
    plan_path.unlink()
    plan_path.mkdir()

    code, _, err = cli(capsys, repo)

    assert code == 2
    assert "cannot read" in err


def test_canary_flags_a_path_that_leaves_the_repository(repo, capsys):
    with pytest.raises(SystemExit):
        cli(capsys, repo, "--paths", "../outside.md", stage="plan")

    assert "inside the repository" in capsys.readouterr().err


def test_a_missing_log_leaves_every_criterion_without_a_final_row(repo, capsys):
    (repo / f".ai-work/{SLUG}/MEASUREMENTS.md").unlink()

    code, data, _ = cli(capsys, repo)

    assert code == 1
    assert data["measurements"] == []
    assert [f["reason"] for f in data["findings"]] == ["missing-final", "missing-baseline"]


def test_the_default_stage_is_verify(repo, capsys):
    code = cfc.main([SLUG, "--repo-root", str(repo), "--json"])

    assert (code, json.loads(capsys.readouterr().out)["stage"]) == (0, "verify")


def test_the_text_report_counts_findings_by_severity(repo, capsys):
    baseline_only = log_row(phase="baseline", head=short_head(repo, "main"), command=PROMPT_COMMAND)
    write_log(repo, baseline_only)
    add_untracked(repo)

    cfc.main([SLUG, "--repo-root", str(repo)])

    last_line = capsys.readouterr().out.splitlines()[-1]
    assert last_line == "footprint criteria (verify): 1 fail, 0 warn, 0 info"


def test_a_reference_criterion_and_a_withheld_reading_reach_the_envelope(repo, capsys):
    write_plan(repo, criterion_row(against="reference: the ceiling"))
    withheld = log_row(
        phase="final", reading="none: crashed", head=short_head(repo), command=PROMPT_COMMAND
    )
    write_log(repo, withheld)

    _, data, _ = cli(capsys, repo)

    assert data["criteria"][0]["against"] == {"kind": "reference", "text": "the ceiling"}
    assert data["measurements"][0]["reading"] == {"kind": "none", "reason": "crashed"}


def test_an_estimate_reading_reaches_the_envelope(repo, capsys):
    estimate = log_row(
        phase="final", reading="estimate", head=short_head(repo), command=PROMPT_COMMAND
    )
    write_plan(repo, criterion_row(against="reference: the ceiling"))
    write_log(repo, estimate)

    _, data, _ = cli(capsys, repo)

    assert data["measurements"][0]["reading"] == {"kind": "estimate", "reason": None}
