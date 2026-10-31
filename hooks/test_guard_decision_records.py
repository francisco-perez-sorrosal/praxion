"""Tests for guard_decision_records.py -- the PreToolUse gate on decision-record writes and reads.

The hook runs as a subprocess, as Claude Code runs it, against a tmp_path repo (a directory
holding a ``.git`` entry), so no real decision record is read or written. Canaries prove it
refuses each shape the gate judges; the controls prove it stays silent for conforming writes,
for debt it does not touch, and for files that are not the gate's to judge.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import guard_decision_records as guard
import pytest

HOOK = Path(__file__).resolve().parent / "guard_decision_records.py"

DRAFT_NAME = "20261031-0900-fperez-apply-rule-moves-gate.md"
DRAFT_DIR = ".ai-state/decisions/drafts"
DRAFT_HASH = "1a2b3c4d"
DRAFT_ID = f"dec-draft-{DRAFT_HASH}"
VALID_DRAFT = f"---\nid: {DRAFT_ID}\ncategory: behavioral\ntitle: x\n---\nBody.\n"
INDEX = ".ai-state/decisions/DECISIONS_INDEX.md"


def _payload(repo: Path, tool_name: str, tool_input: dict) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "cwd": str(repo),
        "tool_name": tool_name,
        "tool_input": tool_input,
    }


def _run_subprocess(
    repo: Path, tool_name: str, tool_input: dict
) -> subprocess.CompletedProcess[str]:
    return _run_raw(json.dumps(_payload(repo, tool_name, tool_input)))


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """The hook's ``main`` run in this process, so the mutation sensor can see its code run."""

    def call(repo: Path, tool_name: str, tool_input: dict) -> subprocess.CompletedProcess[str]:
        stdin = io.StringIO(json.dumps(_payload(repo, tool_name, tool_input)))
        monkeypatch.setattr(sys, "stdin", stdin)
        guard.main()
        captured = capsys.readouterr()
        return subprocess.CompletedProcess([], 0, captured.out, captured.err)

    return call


def _run_raw(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _decision(result: subprocess.CompletedProcess[str]) -> dict | None:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"] if result.stdout.strip() else None


def _assert_silent(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def _assert_denied(result: subprocess.CompletedProcess[str], *needles: str) -> None:
    decision = _decision(result)
    assert decision is not None, "expected a refusal, got silence"
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    for needle in needles:
        assert needle in decision["permissionDecisionReason"]
    assert result.stderr == ""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / DRAFT_DIR).mkdir(parents=True)
    return tmp_path


def _write(repo: Path, rel: str, content: str) -> dict:
    return {"file_path": str(repo / rel), "content": content}


# -- Refused writes ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "content", "phrase"),
    [
        (".ai-state/decisions/loose-note.md", VALID_DRAFT, "directly under decisions/"),
        (".ai-state/decisions/042-picked.md", VALID_DRAFT, "numbered record"),
        (".ai-state/decisions/old/stray.md", VALID_DRAFT, "subdirectory"),
        (f"{DRAFT_DIR}/note.md", VALID_DRAFT, "dated fragment name"),
        (
            f"{DRAFT_DIR}/{DRAFT_NAME}",
            VALID_DRAFT.replace(DRAFT_ID, "dec-042"),
            "dec-NNN",
        ),
        (
            f"{DRAFT_DIR}/{DRAFT_NAME}",
            VALID_DRAFT.replace(DRAFT_HASH, "not-a-hash"),
            "dec-draft-<8-char-hash>",
        ),
        (
            f"{DRAFT_DIR}/{DRAFT_NAME}",
            VALID_DRAFT.replace("category: behavioral\n", ""),
            "no category",
        ),
        (
            f"{DRAFT_DIR}/{DRAFT_NAME}",
            VALID_DRAFT.replace("behavioral", "process"),
            "none of the four",
        ),
    ],
    ids=[
        "misplaced",
        "self-numbered",
        "nested",
        "malformed-name",
        "self-picked-id",
        "malformed-id",
        "no-category",
        "invalid-category",
    ],
)
def test_canary_refuses_a_write_that_leaves_a_stranded_record(
    run, repo: Path, rel: str, content: str, phrase: str
) -> None:
    result = run(repo, "Write", _write(repo, rel, content))
    _assert_denied(result, f"Refused {rel}", phrase, "Correct form")


def test_a_refusal_quotes_the_rule_it_enforces(run, repo: Path) -> None:
    result = run(repo, "Write", _write(repo, ".ai-state/decisions/loose-note.md", VALID_DRAFT))
    _assert_denied(result, "From the ADR conventions rule:")


def test_canary_refuses_an_unbounded_read_of_the_index(run, repo: Path) -> None:
    result = run(repo, "Read", {"file_path": str(repo / INDEX)})
    _assert_denied(result, "no line limit", "query_adrs.py")


def test_canary_refuses_an_edit_that_strips_the_category(run, repo: Path) -> None:
    record = repo / DRAFT_DIR / DRAFT_NAME
    record.write_text(VALID_DRAFT, encoding="utf-8")
    edit = {"file_path": str(record), "old_string": "category: behavioral\n", "new_string": ""}
    _assert_denied(run(repo, "Edit", edit), "without a valid category")


def test_canary_refuses_a_write_through_the_shadow_link(run, tmp_path: Path) -> None:
    project = tmp_path / "project"
    mount = tmp_path / "mount"
    (project / ".git").mkdir(parents=True)
    (mount / "decisions").mkdir(parents=True)
    (project / ".ai-state").symlink_to(mount, target_is_directory=True)
    rel = ".ai-state/decisions/loose-note.md"
    _assert_denied(run(project, "Write", _write(project, rel, VALID_DRAFT)), f"Refused {rel}")


def test_a_relative_path_is_resolved_against_the_payload_cwd(run, repo: Path) -> None:
    rel = ".ai-state/decisions/loose-note.md"
    result = run(repo, "Write", {"file_path": rel, "content": VALID_DRAFT})
    _assert_denied(result, f"Refused {rel}")


# -- Edits replayed against the file on disk ---------------------------------------------------


def test_an_edit_is_replayed_against_the_file_on_disk(run, repo: Path) -> None:
    record = repo / DRAFT_DIR / DRAFT_NAME
    record.write_text(VALID_DRAFT, encoding="utf-8")
    edit = {"file_path": str(record), "old_string": "behavioral", "new_string": "process"}
    _assert_denied(run(repo, "Edit", edit), "without a valid category")
    assert record.read_text(encoding="utf-8") == VALID_DRAFT, "the hook must never write"


def test_replace_all_reaches_a_second_occurrence(run, repo: Path) -> None:
    record = repo / DRAFT_DIR / DRAFT_NAME
    titled_first = f"---\nid: {DRAFT_ID}\ntitle: behavioral\ncategory: behavioral\n---\n"
    record.write_text(titled_first, encoding="utf-8")
    edit = {"file_path": str(record), "old_string": "behavioral", "new_string": "process"}
    _assert_silent(run(repo, "Edit", edit))
    _assert_denied(run(repo, "Edit", {**edit, "replace_all": True}), "without a valid category")


def test_an_edit_that_keeps_the_category_is_silent(run, repo: Path) -> None:
    record = repo / DRAFT_DIR / DRAFT_NAME
    record.write_text(VALID_DRAFT, encoding="utf-8")
    edit = {"file_path": str(record), "old_string": "Body.", "new_string": "A longer body."}
    _assert_silent(run(repo, "Edit", edit))


def test_an_edit_whose_old_string_is_absent_is_silent(run, repo: Path) -> None:
    record = repo / DRAFT_DIR / DRAFT_NAME
    record.write_text(VALID_DRAFT, encoding="utf-8")
    edit = {"file_path": str(record), "old_string": "not there", "new_string": ""}
    _assert_silent(run(repo, "Edit", edit))


def test_canary_refuses_an_edit_that_creates_a_misplaced_record(run, repo: Path) -> None:
    rel = ".ai-state/decisions/loose-note.md"
    edit = {"file_path": str(repo / rel), "old_string": "", "new_string": VALID_DRAFT}
    _assert_denied(run(repo, "Edit", edit), f"Refused {rel}", "directly under decisions/")


def test_an_edit_that_creates_a_conforming_draft_is_silent(run, repo: Path) -> None:
    edit = {
        "file_path": str(repo / DRAFT_DIR / DRAFT_NAME),
        "old_string": "",
        "new_string": VALID_DRAFT,
    }
    _assert_silent(run(repo, "Edit", edit))


def test_an_edit_of_a_missing_file_is_silent(run, repo: Path) -> None:
    edit = {"file_path": str(repo / DRAFT_DIR / "gone.md"), "old_string": "a", "new_string": "b"}
    _assert_silent(run(repo, "Edit", edit))


def test_a_debt_record_is_never_judged_beyond_its_category(run, repo: Path) -> None:
    record = repo / ".ai-state/decisions/loose-note.md"
    record.write_text(VALID_DRAFT, encoding="utf-8")
    edit = {"file_path": str(record), "old_string": "Body.", "new_string": "More."}
    _assert_silent(run(repo, "Edit", edit))


# -- Silent allows ------------------------------------------------------------------------------


def test_a_conforming_draft_is_silent(run, repo: Path) -> None:
    _assert_silent(run(repo, "Write", _write(repo, f"{DRAFT_DIR}/{DRAFT_NAME}", VALID_DRAFT)))


def test_a_bounded_read_of_the_index_is_silent(run, repo: Path) -> None:
    _assert_silent(run(repo, "Read", {"file_path": str(repo / INDEX), "limit": 40, "offset": 3}))


@pytest.mark.parametrize(
    "rel",
    [".ai-state/decisions/001-some-record.md", "docs/guide.md", ".ai-state/DESIGN.md"],
)
def test_a_read_of_any_file_but_the_index_is_silent(run, repo: Path, rel: str) -> None:
    _assert_silent(run(repo, "Read", {"file_path": str(repo / rel)}))


@pytest.mark.parametrize(
    "rel",
    [
        INDEX,
        ".ai-state/decisions/CLAUDE.md",
        ".ai-state/decisions/notes.txt",
        ".ai-state/DESIGN.md",
    ],
)
def test_a_write_to_a_non_record_is_silent(run, repo: Path, rel: str) -> None:
    _assert_silent(run(repo, "Write", _write(repo, rel, "no frontmatter\n")))


def test_a_fixture_tree_that_is_not_a_repo_root_is_silent(run, repo: Path) -> None:
    rel = "tests/fixtures/project/.ai-state/decisions/loose-note.md"
    _assert_silent(run(repo, "Write", _write(repo, rel, "no frontmatter\n")))


def test_a_path_outside_any_repo_is_silent(run, tmp_path: Path) -> None:
    rel = ".ai-state/decisions/loose-note.md"
    _assert_silent(run(tmp_path, "Write", _write(tmp_path, rel, "no frontmatter\n")))


@pytest.mark.parametrize("file_path", ["", None, 5])
def test_a_call_without_a_usable_file_path_is_silent(run, repo: Path, file_path) -> None:
    decisions_dir = repo / ".ai-state" / "decisions"
    _assert_silent(run(decisions_dir, "Write", {"file_path": file_path, "content": VALID_DRAFT}))


@pytest.mark.parametrize("content", [None, 5, ["x"]])
def test_a_write_whose_content_is_not_text_is_silent(run, repo: Path, content) -> None:
    target = {"file_path": str(repo / ".ai-state/decisions/loose-note.md"), "content": content}
    _assert_silent(run(repo, "Write", target))


@pytest.mark.parametrize("tool_name", ["Bash", "Glob", "NotebookEdit"])
def test_a_tool_the_gate_does_not_judge_is_silent(run, repo: Path, tool_name: str) -> None:
    _assert_silent(run(repo, tool_name, {"file_path": str(repo / ".ai-state/decisions/x.md")}))


def test_the_hook_runs_as_claude_code_runs_it(repo: Path) -> None:
    refused = _run_subprocess(
        repo, "Write", _write(repo, ".ai-state/decisions/note.md", VALID_DRAFT)
    )
    _assert_denied(refused, "Refused .ai-state/decisions/note.md")
    allowed = _run_subprocess(repo, "Write", _write(repo, f"{DRAFT_DIR}/{DRAFT_NAME}", VALID_DRAFT))
    _assert_silent(allowed)


# -- Fail-open ----------------------------------------------------------------------------------


@pytest.mark.parametrize("stdin", ["not json", "", "[1, 2]", '{"tool_input": "oops"}'])
def test_a_payload_that_fails_to_parse_is_silent(stdin: str) -> None:
    _assert_silent(_run_raw(stdin))


def test_a_hook_whose_gate_modules_are_missing_lets_the_call_through(tmp_path: Path) -> None:
    lone_hook = tmp_path / "hooks" / HOOK.name
    lone_hook.parent.mkdir()
    lone_hook.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
    payload = _payload(tmp_path, "Write", _write(tmp_path, ".ai-state/decisions/x.md", "x"))
    result = subprocess.run(
        [sys.executable, str(lone_hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    _assert_silent(result)


def test_an_unreadable_target_lets_the_write_through(repo: Path) -> None:
    (repo / DRAFT_DIR / DRAFT_NAME).mkdir()
    edit = {"file_path": str(repo / DRAFT_DIR / DRAFT_NAME), "old_string": "a", "new_string": "b"}
    _assert_silent(_run_subprocess(repo, "Edit", edit))


# -- Pure helpers ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "old", "new", "replace_all", "expected"),
    [
        ("a b a", "a", "c", False, "c b a"),
        ("a b a", "a", "c", True, "c b c"),
        ("a b", "z", "c", False, None),
        ("a b", "", "c", False, None),
        (None, "", "c", False, "c"),
        ("", "", "c", False, "c"),
        (" \n", "", "c", True, "c"),
        (None, "a", "c", False, None),
        ("a b", None, "c", False, None),
        ("a b", "a", None, False, None),
    ],
)
def test_apply_edit(before, old, new, replace_all, expected) -> None:
    assert guard.apply_edit(before, old, new, replace_all) == expected


def test_repo_relative_starts_at_the_anchor_and_ignores_case(repo: Path) -> None:
    absolute = str(repo / ".AI-State" / "Decisions" / "x.md")
    assert guard.repo_relative(absolute) == ".AI-State/Decisions/x.md"


def test_repo_relative_collapses_dot_segments_before_anchoring(repo: Path) -> None:
    payload_path = {"file_path": str(repo / "docs" / ".." / ".ai-state/decisions/loose.md")}
    request = guard.build_request("Write", {**payload_path, "content": "x"}, str(repo))
    assert request is not None
    assert request.path == ".ai-state/decisions/loose.md"


def test_a_limit_of_zero_still_counts_as_bounded(repo: Path) -> None:
    request = guard.build_request("Read", {"file_path": str(repo / INDEX), "limit": 0}, str(repo))
    assert request is not None
    assert request.bounded is True


def test_the_directory_itself_is_anchored(repo: Path) -> None:
    assert guard.repo_relative(str(repo / ".ai-state" / "decisions")) == ".ai-state/decisions"


def test_a_relative_path_has_no_repo_root_to_anchor_in(repo: Path, monkeypatch) -> None:
    monkeypatch.chdir(repo)
    assert guard.repo_relative(".ai-state/decisions/x.md") is None


def _hook_at(monkeypatch, hook_dir: Path) -> None:
    hook_dir.mkdir(parents=True)
    monkeypatch.setattr(guard, "__file__", str(hook_dir / "guard_decision_records.py"))


def test_the_scripts_directory_beside_the_hooks_is_preferred(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "root" / "scripts").mkdir(parents=True)
    _hook_at(monkeypatch, tmp_path / "root" / "hooks")
    assert guard._scripts_dir() == (tmp_path / "root" / "scripts").resolve()


def test_the_scripts_directory_one_level_further_up_is_the_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "scripts").mkdir()
    _hook_at(monkeypatch, tmp_path / "copy" / "hooks")
    assert guard._scripts_dir() == (tmp_path / "scripts").resolve()


def test_the_gate_core_is_found_beside_the_hook() -> None:
    scripts = guard._scripts_dir()
    assert scripts.name == "scripts"
    assert (scripts / "_decision_records.py").is_file()


def test_a_path_without_the_decisions_directory_has_no_anchor(repo: Path) -> None:
    assert guard.repo_relative(str(repo / ".ai-state")) is None
    assert guard.repo_relative(str(repo / ".ai-state" / "DESIGN.md")) is None
