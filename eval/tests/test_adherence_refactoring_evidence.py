"""What decides a paid refactoring run's results: a damaged record proves nothing, and a test run
that could not run is no failed checklist item.

Nothing here starts a session. The delivery module that counts blocks is this checkout's own; the
repositories graded are tiny ones built under ``tmp_path``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from praxion_evals.adherence import checks_refactoring, grade, refactoring_arms, session_loop
from praxion_evals.adherence.arms import ArmCopyError, require_regular_definition
from praxion_evals.adherence.model import CheckErrored, Failed, NotBuilt, Passed
from praxion_evals.adherence.refactoring_arms import build_refactoring_copy, observe_delivery
from praxion_evals.adherence.refactoring_assess import _outcome
from praxion_evals.adherence.transcript import UserMessagesRead, read_role_user_messages

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION, AGENT = "sess-evidence", "a2450d924b822afe6"
_RENDER = (
    "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1] + '/hooks'); "
    "import _skill_delivery as d; skill = d.skill_dir(Path(sys.argv[1])); "
    "print(d.render_block(d.read_body(skill), skill), end='')"
)
END_LINE = "[End of skill delivery: refactoring]"


@pytest.fixture(scope="module")
def block() -> str:
    done = subprocess.run(
        [sys.executable, "-B", "-c", _RENDER, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def _counted(*messages: str) -> tuple[int, int] | NotBuilt:
    return refactoring_arms._count_blocks(messages, REPO_ROOT)


# --- a record that lost a line proves nothing -------------------------------------------------


def _write_transcript(tmp_path: Path, text: str) -> None:
    path = tmp_path / "projects" / "-w" / SESSION / "subagents" / f"agent-{AGENT}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(text)


def test_the_user_messages_reader_keeps_the_flag_of_a_record_that_lost_a_line(tmp_path):
    whole = '{"type": "user", "message": {"role": "user", "content": "kept"}}\n'
    _write_transcript(tmp_path, "not a record\n" + whole)

    read = read_role_user_messages(tmp_path, "/w", SESSION, AGENT)

    assert isinstance(read, UserMessagesRead)
    assert read.messages == ("kept",)
    assert not read.all_whole


def test_the_user_messages_reader_flags_a_whole_record_as_whole(tmp_path):
    _write_transcript(tmp_path, '{"type": "user", "message": {"role": "user", "content": "a"}}\n')

    read = read_role_user_messages(tmp_path, "/w", SESSION, AGENT)

    assert isinstance(read, UserMessagesRead)
    assert read.all_whole


def test_a_record_that_lost_a_line_is_not_observed_whatever_it_holds(tmp_path, monkeypatch):
    torn = UserMessagesRead(tmp_path / "t.jsonl", ("a delegation with no block",), all_whole=False)
    monkeypatch.setattr(refactoring_arms, "unobserved_proof", lambda evidence, home: None)
    monkeypatch.setattr(grade, "role_user_messages", lambda evidence: torn)

    seen = observe_delivery(cast(Any, object()), tmp_path)

    assert isinstance(seen, NotBuilt)
    assert "lost a line" in seen.reason


# --- the block counter asks the matcher about the text as it stands ---------------------------


def test_an_end_line_followed_by_text_on_its_line_is_no_arrival(block):
    assert _counted(block + " and then more") == (0, 1)


def test_a_stale_label_before_a_real_block_is_a_stray(block):
    stale = block.splitlines()[0].replace(block.split("]")[0][-8:], "0" * 8)

    assert _counted(f"{stale}\n{block}") == (1, 1)


def test_a_block_is_counted_where_it_lies_among_other_text(block):
    assert _counted(f"Task slug: x.\n{block}\nafter") == (1, 0)


def test_a_body_that_cannot_be_read_is_reported_as_that_without_a_traceback(tmp_path):
    shutil.copytree(REPO_ROOT / "hooks", tmp_path / "hooks")  # a copy that holds no skill

    counted = refactoring_arms._count_blocks(("anything",), tmp_path)

    assert isinstance(counted, NotBuilt)
    assert "skill cannot be read" in counted.reason
    assert "Traceback" not in counted.reason


@pytest.mark.parametrize(
    "printed", ["", "not json", "3 0", "[1, 2]", '{"blocks": "x", "strays": 0}']
)
def test_counts_the_program_did_not_print_as_counts_are_not_built(monkeypatch, printed):
    monkeypatch.setattr(refactoring_arms, "_run", lambda *args, **options: printed)

    counted = refactoring_arms._count_blocks(("a",), REPO_ROOT)

    assert isinstance(counted, NotBuilt)
    assert "not its counts" in counted.reason


# --- the arm build: a definition that is a link, a prompt that does not end in the block ------


def test_a_definition_that_is_a_link_is_refused_before_anything_is_copied(tmp_path):
    root, dest = tmp_path / "checkout", tmp_path / "copy"
    (root / "agents").mkdir(parents=True)
    (root / "elsewhere.md").write_text("---\nname: implementer\n---\n")
    (root / "agents" / "implementer.md").symlink_to(root / "elsewhere.md")
    original = cast(Any, SimpleNamespace(root=root))

    with pytest.raises(ArmCopyError, match="no regular file agents/implementer.md"):
        build_refactoring_copy(original, dest, "implementer", "delivered", 5)

    assert not dest.exists()


def test_a_missing_definition_is_not_a_regular_file(tmp_path):
    with pytest.raises(ArmCopyError, match="no regular file"):
        require_regular_definition(tmp_path, "test-engineer")


@pytest.mark.parametrize(
    ("rewritten", "arrives"),
    [
        ("{block}", True),
        ("Task slug: x.\n{block}", True),
        ("{block}\nand a note after it", False),
        ("{block}\n\n{block}\nextra", False),
        ("Task slug: x. No block here.", False),
    ],
)
def test_a_rewritten_prompt_must_end_in_the_block(block, rewritten, arrives):
    prompt = rewritten.format(block=block)

    assert refactoring_arms._ask_copy(REPO_ROOT, refactoring_arms._ARRIVES, prompt) is arrives


# --- a test run that could not run is not a failed item ---------------------------------------


def _repo_running(tmp_path: Path, test_source: str) -> Path:
    (tmp_path / "test_run.py").write_text(test_source)
    return tmp_path


@pytest.mark.parametrize(
    ("test_source", "holds"),
    [
        ("def test_ok():\n    assert True\n", True),
        ("def test_bad():\n    assert False\n", False),
    ],
)
def test_the_exit_codes_pytest_gives_a_verdict_with_decide_the_item(tmp_path, test_source, holds):
    assert checks_refactoring._pytest_passes(_repo_running(tmp_path, test_source)) is holds


@pytest.mark.parametrize("returncode", [2, 3, 4])
def test_a_run_that_was_interrupted_or_broke_is_errored_with_the_output(tmp_path, returncode):
    source = f"import pytest\n\ndef test_stop():\n    pytest.exit('broke here', returncode={returncode})\n"

    with pytest.raises(checks_refactoring.PytestRunError, match=f"exited {returncode}") as caught:
        checks_refactoring._pytest_passes(_repo_running(tmp_path, source))

    assert "broke here" in str(caught.value)


def test_a_run_that_collects_no_test_is_errored_not_failed(tmp_path):
    with pytest.raises(checks_refactoring.PytestRunError, match="exited 5"):
        checks_refactoring._pytest_passes(tmp_path)


def test_a_run_that_outlasts_its_time_is_errored(tmp_path, monkeypatch):
    monkeypatch.setattr(checks_refactoring, "TEST_TIMEOUT_SECONDS", 1)
    source = "import time\n\ndef test_slow():\n    time.sleep(30)\n"

    with pytest.raises(checks_refactoring.PytestRunError, match="did not finish within 1 s"):
        checks_refactoring._pytest_passes(_repo_running(tmp_path, source))


def test_the_nested_run_keeps_its_temporary_files_in_a_directory_of_its_own(tmp_path):
    """The graded run gets a base temporary directory the grader makes and removes.

    Why: a clean end state failed "behaviour is unchanged" in two outer-loop nodes of one gate under
    eight parallel workers, and one item once in a whole-pocket run, while the same test passed
    thirty times of thirty alone. The task repositories' tests use ``tmp_path``, and pytest's
    numbered-directory cleanup could remove a directory of another session in the instant before
    that session locks it. That cause is unconfirmed: the failure was not reproduced here, and the
    subprocess's own output was never seen. A private base removes the shared root either way.
    """
    seen = tmp_path / "seen.txt"
    source = (
        "def test_where(tmp_path):\n"
        f"    open({str(seen)!r}, 'w').write(str(tmp_path))\n"
        "    assert tmp_path.is_dir()\n"
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    assert checks_refactoring._pytest_passes(_repo_running(repo, source))

    where = Path(seen.read_text())
    assert "pytest-of-" not in str(where)  # not pytest's shared numbered root
    assert not where.exists()  # the grader removed what it made


def _graded_workspace(tmp_path: Path, tests: dict[str, str]) -> Path:
    """A repository whose only commit holds the manifest, the source and ``tests``."""
    files = {
        "refactoring.toml": (
            'source = "src/a.py"\ntarget = "src/b.py"\ntests = "tests"\nmoving = ["moving"]\n'
        ),
        "src/a.py": "def moving():\n    return 1\n",
        **tests,
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    identity = ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid")
    for step in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "start")):
        subprocess.run(["git", *identity, *step], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_a_grade_over_tests_that_collect_nothing_errors_the_items_that_run_them(tmp_path):
    workspace = _graded_workspace(tmp_path, {"tests/note.txt": "no test module\n"})

    result = checks_refactoring.grade_workspace("implementer", workspace, "")

    assert set(result.errored) == {"the tests still pass", "behaviour is unchanged"}
    assert "exited 5" in result.errored["the tests still pass"]
    assert not set(result.errored) & set(result.failed)
    assert not result.passed


def test_an_errored_item_is_an_errored_outcome_with_the_output_and_never_a_failed_one():
    outcome = _outcome("x", failed=set(), errored={"x": "pytest exited 3\nINTERNALERROR"})

    assert isinstance(outcome, CheckErrored)
    assert "INTERNALERROR" in outcome.reason
    assert isinstance(_outcome("x", failed={"x"}, errored={}), Failed)
    assert isinstance(_outcome("x", failed=set(), errored={}), Passed)


# --- the test-engineer's public-surface check reads only the tests the session added ----------

OLD_TEST = "from a import moving\n\n\ndef test_old():\n    assert moving() == 1\n"
SOUND_TEST = "\n\ndef test_sound(tmp_path):\n    assert 1 + 1 == 2\n"
NAMING_TEST = "\n\ndef test_new_names_it():\n    assert moving() == 1\n"
PIN_PUBLIC = "characterization tests pin behaviour through the public surface"


def _test_engineer_grade(tmp_path: Path, added: str, old: str = OLD_TEST):
    workspace = _graded_workspace(tmp_path, {"tests/test_old.py": old})
    (workspace / "tests" / "test_old.py").write_text(old + added)
    return checks_refactoring.grade_workspace("test-engineer", workspace, "")


def test_an_old_test_that_names_moving_code_does_not_fail_a_session_that_added_sound_ones(tmp_path):
    assert PIN_PUBLIC not in _test_engineer_grade(tmp_path, SOUND_TEST).failed


def test_an_added_test_that_names_moving_code_still_fails_the_session(tmp_path):
    assert PIN_PUBLIC in _test_engineer_grade(tmp_path, SOUND_TEST + NAMING_TEST).failed


ALIASED_OLD = "from a import moving as m\nfrom a import other as o\n"


def test_an_added_test_that_reaches_moving_code_through_an_import_alias_still_fails(tmp_path):
    added = "\n\ndef test_new_uses_the_alias():\n    assert m() == 1\n"

    assert PIN_PUBLIC in _test_engineer_grade(tmp_path, added, ALIASED_OLD).failed


def test_an_added_test_that_uses_an_alias_of_something_else_does_not_fail(tmp_path):
    added = "\n\ndef test_new_uses_another_alias():\n    assert o() is None\n"

    assert PIN_PUBLIC not in _test_engineer_grade(tmp_path, added, ALIASED_OLD).failed


# --- the eval's git wrapper carries git's own message -----------------------------------------


def test_a_failing_git_call_carries_gits_own_stderr(tmp_path):
    with pytest.raises(ValueError, match="not a git repository") as caught:
        session_loop._git(tmp_path, "rev-parse", "--show-toplevel")

    assert "rev-parse --show-toplevel" in str(caught.value)


def test_a_missing_git_binary_is_reported_by_what_failed_not_as_a_guess(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(ValueError, match="failed in") as caught:
        session_loop._git(tmp_path, "rev-parse", "HEAD")

    assert "No such file or directory" in str(caught.value)
    assert "not a git checkout" not in str(caught.value)
