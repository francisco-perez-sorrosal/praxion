"""Tests for the decision-record gate's command line (``scripts/check_decision_records.py``).

Every case builds a throwaway git repository under ``tmp_path`` and runs ``main`` against it with
``--repo-root``, so nothing reads the checkout under test. Each refused shape names the defect it
must get, each allowed shape proves silence, and the three exit codes are pinned. The two
process-level facts (the file runs as a script, and ships executable) are checked on the real file.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_decision_records as cli  # noqa: E402
from _git_runner import run_git  # noqa: E402

DECISIONS = ".ai-state/decisions"
DRAFTS = f"{DECISIONS}/drafts"
FRAGMENT = "20261029-1430-fixture-person-record-storage-choice-adopt-sqlite.md"
DRAFT = f"{DRAFTS}/{FRAGMENT}"
NUMBERED = f"{DECISIONS}/007-adopt-sqlite.md"
DRAFT_HASH = "3f9a0c1e"
DRAFT_ID = f"dec-draft-{DRAFT_HASH}"


def record(id_: str | None = DRAFT_ID, category: str | None = "behavioral") -> str:
    fields = [f"id: {id_}"] if id_ is not None else []
    fields += ["title: Adopt SQLite", "status: proposed"]
    fields += [f"category: {category}"] if category is not None else []
    return "---\n" + "\n".join(fields) + "\n---\n\n# Adopt SQLite\n"


GOOD_DRAFT = record()
GOOD_NUMBERED = record("dec-007")


def git(repo: Path, *args: str) -> None:
    result = run_git(
        repo,
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false",
        "-c", "core.hooksPath=/dev/null",
        *args,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr


def put(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit_all(repo: Path, message: str = "fixture") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def make_repo(tmp_path: Path, branch: str = "main", name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", branch)
    put(repo, "README.md", "fixture\n")
    commit_all(repo, "initial")
    return repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@pytest.fixture
def feature(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    return repo


def run(repo: Path, *args: str, capsys) -> tuple[int, str, str]:
    code = cli.main(["--repo-root", str(repo), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# -- Allowed shapes -----------------------------------------------------------------------


def test_a_conforming_draft_is_clean(feature, capsys):
    put(feature, DRAFT, GOOD_DRAFT)
    assert run(feature, DRAFT, capsys=capsys) == (0, "", "")


@pytest.mark.parametrize(
    "rel", [f"{DECISIONS}/DECISIONS_INDEX.md", f"{DECISIONS}/CLAUDE.md", "docs/notes.md"]
)
def test_files_that_are_no_record_are_clean_whatever_they_hold(feature, capsys, rel):
    put(feature, rel, "no frontmatter at all\n")
    assert run(feature, rel, capsys=capsys)[0] == 0


def test_editing_an_existing_numbered_record_that_keeps_its_category_is_clean(feature, capsys):
    put(feature, NUMBERED, GOOD_NUMBERED)
    commit_all(feature)
    put(feature, NUMBERED, GOOD_NUMBERED + "\nA later paragraph.\n")
    assert run(feature, NUMBERED, capsys=capsys)[0] == 0


@pytest.mark.parametrize("branch", ["main", "master"])
def test_a_numbered_record_is_clean_on_the_default_branch(tmp_path, capsys, branch):
    repo = make_repo(tmp_path, branch=branch)
    put(repo, NUMBERED, GOOD_NUMBERED)
    assert run(repo, NUMBERED, capsys=capsys)[0] == 0


def test_a_numbered_record_the_default_branch_holds_is_clean_on_a_feature_branch(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "branch", "feature")
    put(repo, NUMBERED, GOOD_NUMBERED)
    commit_all(repo, "promoted on main")
    git(repo, "checkout", "-q", "feature")
    put(repo, NUMBERED, GOOD_NUMBERED)
    assert run(repo, NUMBERED, capsys=capsys)[0] == 0


def test_a_numbered_record_a_master_default_branch_holds_is_clean_on_a_feature_branch(
    tmp_path, capsys
):
    repo = make_repo(tmp_path, branch="master")
    git(repo, "branch", "feature")
    put(repo, NUMBERED, GOOD_NUMBERED)
    commit_all(repo, "promoted on master")
    git(repo, "checkout", "-q", "feature")
    put(repo, NUMBERED, GOOD_NUMBERED)
    assert run(repo, NUMBERED, capsys=capsys)[0] == 0


def test_an_absolute_path_inside_the_repository_is_judged_like_a_relative_one(feature, capsys):
    put(feature, DRAFT, GOOD_DRAFT)
    assert run(feature, str(feature / DRAFT), capsys=capsys) == (0, "", "")


# -- Refused shapes -----------------------------------------------------------------------

REFUSED = [
    pytest.param(NUMBERED, GOOD_NUMBERED, "self-numbered", id="numbered-on-a-feature-branch"),
    pytest.param(f"{DECISIONS}/{FRAGMENT}", GOOD_DRAFT, "misplaced", id="fragment-outside-drafts"),
    pytest.param(f"{DRAFTS}/nested/{FRAGMENT}", GOOD_DRAFT, "nested", id="nested-subdirectory"),
    pytest.param(f"{DRAFTS}/notes.md", GOOD_DRAFT, "malformed-name", id="malformed-draft-name"),
    pytest.param(DRAFT, record(f"dec-{DRAFT_HASH}"), "malformed-id", id="malformed-draft-id"),
    pytest.param(DRAFT, record("dec-042"), "self-picked-id", id="self-picked-id"),
    pytest.param(DRAFT, record(category=None), "no-category", id="no-category"),
    pytest.param(DRAFT, record(category="strategic"), "invalid-category", id="invalid-category"),
]


@pytest.mark.parametrize(("rel", "text", "defect"), REFUSED)
def test_reject_each_refused_shape_with_exit_1_naming_the_path_and_defect(
    feature, capsys, rel, text, defect
):
    put(feature, rel, text)
    code, out, err = run(feature, rel, capsys=capsys)
    assert code == 1
    assert err == ""
    assert out.startswith(f"{rel}: {defect}")
    assert "Correct form:" in out


def test_a_text_finding_is_one_line_per_path_with_every_defect_listed(feature, capsys):
    put(feature, DRAFT, record("dec-042", category=None))
    _, out, _ = run(feature, DRAFT, capsys=capsys)
    assert out.splitlines() == [f"{DRAFT}: {'self-picked-id, no-category'} -- {cli.CORRECT_FORM}"]


def test_every_offending_path_is_named(feature, capsys):
    put(feature, DRAFT, record(category=None))
    put(feature, NUMBERED, GOOD_NUMBERED)
    _, out, _ = run(feature, DRAFT, NUMBERED, capsys=capsys)
    assert [line.split(":")[0] for line in out.splitlines()] == [DRAFT, NUMBERED]


def test_a_clean_path_beside_a_refused_one_is_not_named(feature, capsys):
    put(feature, DRAFT, GOOD_DRAFT)
    put(feature, NUMBERED, GOOD_NUMBERED)
    _, out, _ = run(feature, DRAFT, NUMBERED, capsys=capsys)
    assert DRAFT not in out
    assert NUMBERED in out


def test_reject_an_edit_that_removes_an_existing_records_category(feature, capsys):
    put(feature, NUMBERED, GOOD_NUMBERED)
    commit_all(feature)
    put(feature, NUMBERED, record("dec-007", category=None))
    code, out, _ = run(feature, NUMBERED, capsys=capsys)
    assert code == 1
    assert out.startswith(f"{NUMBERED}: category-lost")


def test_explicit_paths_judge_against_the_head_blob_not_the_index(feature, capsys):
    put(feature, NUMBERED, GOOD_NUMBERED)
    commit_all(feature)
    put(feature, NUMBERED, record("dec-007", category=None))
    git(feature, "add", NUMBERED)
    put(feature, NUMBERED, GOOD_NUMBERED)
    assert run(feature, NUMBERED, capsys=capsys)[0] == 0


# -- The staged set -----------------------------------------------------------------------


def test_nothing_staged_is_clean(feature, capsys):
    assert run(feature, "--staged", capsys=capsys) == (0, "", "")


def test_a_staged_refused_record_is_refused_by_its_index_blob(feature, capsys):
    put(feature, DRAFT, record(category=None))
    git(feature, "add", DRAFT)
    put(feature, DRAFT, GOOD_DRAFT)
    code, out, _ = run(feature, "--staged", capsys=capsys)
    assert code == 1
    assert out.startswith(f"{DRAFT}: no-category")


def test_a_staged_conforming_record_is_clean_whatever_the_working_tree_holds(feature, capsys):
    put(feature, DRAFT, GOOD_DRAFT)
    git(feature, "add", DRAFT)
    put(feature, DRAFT, record(category=None))
    assert run(feature, "--staged", capsys=capsys)[0] == 0


def test_a_staged_numbered_record_on_a_feature_branch_is_refused_and_on_main_clean(repo, capsys):
    put(repo, NUMBERED, GOOD_NUMBERED)
    git(repo, "add", NUMBERED)
    assert run(repo, "--staged", capsys=capsys)[0] == 0
    git(repo, "checkout", "-q", "-b", "feature")
    code, out, _ = run(repo, "--staged", capsys=capsys)
    assert code == 1
    assert out.startswith(f"{NUMBERED}: self-numbered")


def test_a_staged_change_to_an_existing_record_is_judged_against_head(feature, capsys):
    put(feature, NUMBERED, GOOD_NUMBERED)
    commit_all(feature)
    put(feature, NUMBERED, record("dec-007", category=None))
    git(feature, "add", NUMBERED)
    code, out, _ = run(feature, "--staged", capsys=capsys)
    assert code == 1
    assert out.startswith(f"{NUMBERED}: category-lost")


def test_a_staged_deletion_of_a_record_is_not_judged(feature, capsys):
    put(feature, NUMBERED, record("dec-007", category=None))
    commit_all(feature)
    git(feature, "rm", "-q", NUMBERED)
    assert run(feature, "--staged", capsys=capsys) == (0, "", "")


def test_staged_files_outside_the_decisions_directory_are_not_read(feature, capsys):
    put(feature, "src/app.py", "print('hi')\n")
    git(feature, "add", "src/app.py")
    assert run(feature, "--staged", capsys=capsys) == (0, "", "")


# -- Machine output -----------------------------------------------------------------------


def test_json_for_a_clean_run_is_the_schema_with_no_findings(feature, capsys):
    put(feature, DRAFT, GOOD_DRAFT)
    code, out, _ = run(feature, "--json", DRAFT, capsys=capsys)
    assert (code, json.loads(out)) == (0, {"schema": 1, "findings": []})


def test_json_findings_carry_the_path_and_every_defect_value(feature, capsys):
    put(feature, DRAFT, record("dec-042", category=None))
    code, out, _ = run(feature, "--json", DRAFT, capsys=capsys)
    assert code == 1
    assert json.loads(out) == {
        "schema": 1,
        "findings": [{"path": DRAFT, "defects": ["self-picked-id", "no-category"]}],
    }


# -- Exit 2: a gate that cannot read its input never passes ---------------------------------


def test_missing_path_is_an_input_error(feature, capsys):
    code, out, err = run(feature, DRAFT, capsys=capsys)
    assert (code, out) == (2, "")
    assert "cannot read" in err
    assert DRAFT in err
    assert "No such file" in err


def test_a_directory_given_as_a_path_is_an_input_error(feature, capsys):
    (feature / DRAFTS).mkdir(parents=True)
    assert run(feature, DRAFTS, capsys=capsys)[0] == 2


@pytest.mark.parametrize("raw", ["..", "../elsewhere/x.md", "a/../../x.md"])
def test_a_relative_path_leaving_the_repository_is_an_input_error(feature, capsys, raw):
    code, _, err = run(feature, raw, capsys=capsys)
    assert code == 2
    assert "outside the repository" in err


def test_an_absolute_path_outside_the_repository_is_an_input_error(feature, tmp_path, capsys):
    outside = tmp_path / "outside.md"
    outside.write_text("x")
    code, _, err = run(feature, str(outside), capsys=capsys)
    assert code == 2
    assert "outside the repository" in err


def test_a_directory_that_is_no_repository_is_an_input_error(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out, err = run(plain, "--staged", capsys=capsys)
    assert (code, out) == (2, "")
    assert "not a git repository" in err


def test_a_plugin_cache_root_is_refused(tmp_path, capsys):
    cache_root = tmp_path / "plugins" / "cache" / "owner" / "praxion"
    cache_root.mkdir(parents=True)
    git(cache_root, "init", "-q", "-b", "main")
    code, _, err = run(cache_root, "--staged", capsys=capsys)
    assert code == 2
    assert "plugin-cache" in err


@pytest.mark.parametrize("argv", [[], ["--staged", "some.md"]])
def test_a_command_line_that_names_no_input_or_two_kinds_is_a_usage_error(argv, capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(argv)
    assert raised.value.code == 2
    assert "either --staged or one or more PATH" in capsys.readouterr().err


def test_help_describes_every_option_and_exits_0(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(["--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    for option in ("--staged", "--json", "--repo-root", "paths"):
        assert option in out


def test_outside_a_repository_and_with_no_repo_root_the_gate_does_not_pass(
    tmp_path, capsys, monkeypatch
):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    code = cli.main(["x.md"])
    assert code == 2
    assert "--repo-root" in capsys.readouterr().err


def test_bytes_that_are_not_utf8_are_judged_not_fatal(feature, capsys):
    path = feature / DRAFT
    path.parent.mkdir(parents=True)
    path.write_bytes(b"---\nid: " + DRAFT_ID.encode() + b"\ncategory: behavioral\n---\n\xff\xfe\n")
    assert run(feature, DRAFT, capsys=capsys)[0] == 0


def test_with_git_absent_the_gate_does_not_pass(feature, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "")
    put(feature, DRAFT, GOOD_DRAFT)
    assert run(feature, DRAFT, capsys=capsys)[0] == 2


# -- The branch decides, and an unborn one still has a name ---------------------------------


def test_an_unborn_main_branch_counts_as_main(tmp_path, capsys):
    repo = tmp_path / "fresh"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    put(repo, NUMBERED, GOOD_NUMBERED)
    assert run(repo, NUMBERED, capsys=capsys)[0] == 0


def test_a_detached_head_is_not_main(tmp_path, capsys):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "--detach")
    put(repo, NUMBERED, GOOD_NUMBERED)
    assert run(repo, NUMBERED, capsys=capsys)[0] == 1


# -- The real file ------------------------------------------------------------------------


def test_the_script_ships_as_an_executable_regular_file_with_a_shebang():
    path = SCRIPT_DIR / "check_decision_records.py"
    mode = path.stat().st_mode
    assert stat.S_ISREG(mode)
    assert mode & stat.S_IXUSR
    assert os.access(path, os.X_OK)
    assert path.read_text().startswith("#!/usr/bin/env python3\n")


def test_the_script_runs_as_a_process_and_exits_with_the_verdict(feature):
    put(feature, DRAFT, record(category=None))
    done = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "check_decision_records.py"),
            "--repo-root",
            str(feature),
            DRAFT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1
    assert done.stdout.startswith(f"{DRAFT}: no-category")
