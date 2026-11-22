"""A copy of the whole checkout is not a read of each copied file; every other read still counts.

The selection audit traces each project below and asks the project's resolver whether a change to
each file a test read selects that test. A test that copies the checkout as a whole (every tracked
file, or every tracked file outside a part it leaves out) is not failed for the files its copy
read, whichever test the run credits with a copy one test made and later tests reuse. Copying one
particular directory or file is still a read of each file copied, a copying test's other reads
still count, and a read no change selects still fails the verdict. Every verdict's notes say how
many reads the copy rule set aside, made by how many tests, and that what those tests read later
from their copies is not audited, with a count of none when no test copied the checkout.

These run the audit's command, so they carry the `liveness` marker and run with the quick
scenarios, never inside the suite the audit itself traces.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.copy_reads import (
    ROUTED_TEST,
    AuditRun,
    build_project,
    copy_notes,
    numbers_in,
    run_audit,
    says_none,
    says_not_audited,
)

pytestmark = pytest.mark.liveness

# -- A run where copies, particular copies and real reads meet -----------------------------------

WHOLE_COPY_THEN_READS = "tests/test_copies_the_checkout_then_reads_two_files.py"
READ_DIRECTLY = "docs/also-copied/read-directly.txt"
READ_BY_A_CHILD = "docs/also-copied/read-by-a-child-process.txt"
ONE_DIRECTORY_COPY = "tests/test_copies_one_directory.py"
ONE_DIRECTORY_FILES = ("docs/one-directory/first.txt", "docs/one-directory/second.txt")
ONE_FILE_COPY = "tests/test_copies_one_file.py"
ONE_FILE = "docs/one-file.txt"
UNROUTED_READER = "tests/test_reads_a_file_no_route_names.py"
UNROUTED_FILE = "docs/unrouted.txt"

MIXED_PROJECT = {
    READ_DIRECTLY: "direct\n",
    READ_BY_A_CHILD: "child\n",
    ONE_DIRECTORY_FILES[0]: "first\n",
    ONE_DIRECTORY_FILES[1]: "second\n",
    ONE_FILE: "one file\n",
    UNROUTED_FILE: "unrouted\n",
    WHOLE_COPY_THEN_READS: """
        import shutil
        import subprocess
        import sys
        from pathlib import Path

        ROOT = Path(__file__).resolve().parents[1]
        ALSO_COPIED = ROOT / "docs" / "also-copied"


        def test_copies_the_checkout_then_reads_two_of_its_files(tmp_path):
            ignore = shutil.ignore_patterns(".*", "__pycache__")
            shutil.copytree(ROOT, tmp_path / "copy", ignore=ignore)
            direct = (ALSO_COPIED / "read-directly.txt").read_text(encoding="utf-8")
            child = subprocess.run(
                [sys.executable, "-c", "import sys; print(open(sys.argv[1]).read())",
                 str(ALSO_COPIED / "read-by-a-child-process.txt")],
                capture_output=True, text=True, check=True,
            ).stdout
            assert (direct.strip(), child.strip()) == ("direct", "child")
        """,
    ONE_DIRECTORY_COPY: """
        import shutil
        from pathlib import Path

        ROOT = Path(__file__).resolve().parents[1]


        def test_copies_one_directory_of_the_checkout(tmp_path):
            copied = shutil.copytree(ROOT / "docs" / "one-directory", tmp_path / "one-directory")
            assert sorted(p.name for p in copied.iterdir()) == ["first.txt", "second.txt"]
        """,
    ONE_FILE_COPY: """
        import shutil
        from pathlib import Path

        ROOT = Path(__file__).resolve().parents[1]


        def test_copies_one_file_of_the_checkout(tmp_path):
            copied = shutil.copy2(ROOT / "docs" / "one-file.txt", tmp_path / "one-file.txt")
            assert Path(copied).read_text(encoding="utf-8").strip() == "one file"
        """,
    UNROUTED_READER: """
        from pathlib import Path

        ROOT = Path(__file__).resolve().parents[1]


        def test_reads_a_file_no_route_names():
            assert (ROOT / "docs" / "unrouted.txt").read_text(encoding="utf-8").strip() == "unrouted"
        """,
}


@pytest.fixture(scope="module")
def mixed_run(tmp_path_factory) -> AuditRun:
    return run_audit(build_project(tmp_path_factory.mktemp("mixed"), MIXED_PROJECT))


def test_a_whole_copy_leaves_only_the_copying_tests_other_reads_unselected(mixed_run):
    assert mixed_run.unselected_reads_of(WHOLE_COPY_THEN_READS) == {
        READ_DIRECTLY,
        READ_BY_A_CHILD,
    }, mixed_run.describe()


def test_a_copying_test_still_answers_for_what_it_reads_itself_or_through_a_child(mixed_run):
    expected = {(WHOLE_COPY_THEN_READS, READ_DIRECTLY), (WHOLE_COPY_THEN_READS, READ_BY_A_CHILD)}
    assert expected <= mixed_run.unselected, mixed_run.describe()


def test_copying_one_directory_is_a_read_of_each_file_in_it(mixed_run):
    expected = {(ONE_DIRECTORY_COPY, copied) for copied in ONE_DIRECTORY_FILES}
    assert expected <= mixed_run.unselected, mixed_run.describe()


def test_copying_one_file_is_a_read_of_that_file(mixed_run):
    assert (ONE_FILE_COPY, ONE_FILE) in mixed_run.unselected, mixed_run.describe()


def test_a_read_no_change_selects_fails_the_verdict_beside_copies_of_the_checkout(mixed_run):
    assert not mixed_run.passed, mixed_run.describe()
    assert mixed_run.exit_code == 1, mixed_run.describe()
    assert (UNROUTED_READER, UNROUTED_FILE) in mixed_run.unselected, mixed_run.describe()


def test_a_failing_verdict_notes_the_one_copying_test_and_that_its_copy_is_not_audited(
    mixed_run,
):
    said = copy_notes(mixed_run)

    assert 1 in numbers_in(said), (
        f"no count of one copying test in {said!r}\n{mixed_run.describe()}"
    )
    assert says_not_audited(said), f"{said!r} does not say the copy is not audited"


# -- A run whose only copy is made once and reused -----------------------------------------------

COPY_MAKER = "tests/test_copies_listed_files.py"
COPY_REUSER = "tests/test_reuses_the_copy.py"
LEFT_OUT = "vendor/left-out.txt"

CACHED_COPY_PROJECT = {
    LEFT_OUT: "left out of the copy\n",
    "tests/checkout_copy.py": r'''
        """This process's copy of the checkout: made by the first test that asks, reused after."""

        import atexit
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path

        ROOT = Path(__file__).resolve().parents[1]
        LEFT_OUT = ("vendor/",)
        _copy = None


        def checkout_copy():
            global _copy
            if _copy is None:
                listed = subprocess.run(
                    ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
                ).stdout
                dest = Path(tempfile.mkdtemp(prefix="checkout-copy-"))
                atexit.register(shutil.rmtree, dest, ignore_errors=True)
                for rel in filter(None, listed.split("\0")):
                    if rel.startswith(LEFT_OUT):
                        continue
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / rel, target)
                _copy = dest
            return _copy
        ''',
    COPY_MAKER: """
        from checkout_copy import checkout_copy


        def test_the_copy_holds_the_project_file():
            assert (checkout_copy() / "pyproject.toml").read_text(encoding="utf-8")
        """,
    COPY_REUSER: """
        from checkout_copy import checkout_copy


        def test_the_reused_copy_holds_the_routed_file():
            text = (checkout_copy() / "docs" / "routed.txt").read_text(encoding="utf-8")
            assert text.strip() == "routed"
        """,
}


@pytest.fixture(scope="module")
def cached_copy_project(tmp_path_factory):
    return build_project(tmp_path_factory.mktemp("cached"), CACHED_COPY_PROJECT)


@pytest.fixture(scope="module")
def cached_copy_run(cached_copy_project) -> AuditRun:
    return run_audit(cached_copy_project)


def test_a_run_whose_only_unselected_reads_are_copies_passes(cached_copy_run):
    assert cached_copy_run.passed, cached_copy_run.describe()
    assert cached_copy_run.exit_code == 0, cached_copy_run.describe()
    assert cached_copy_run.unselected == frozenset(), cached_copy_run.describe()


def test_neither_the_test_that_made_a_shared_copy_nor_one_that_reused_it_is_failed_for_it(
    cached_copy_run,
):
    credited = cached_copy_run.unselected_reads_of(COPY_MAKER)
    credited |= cached_copy_run.unselected_reads_of(COPY_REUSER)
    assert credited == set(), cached_copy_run.describe()


def test_a_passing_verdict_notes_how_many_reads_one_copying_test_made_and_that_they_go_unaudited(
    cached_copy_project, cached_copy_run
):
    copied = [path for path in cached_copy_project.tracked_files() if path != LEFT_OUT]
    said = copy_notes(cached_copy_run)

    counts = numbers_in(said)
    assert {len(copied), 1} <= counts, (
        f"expected the notes to count {len(copied)} copy reads made by 1 test; they say {said!r}\n"
        f"{cached_copy_run.describe()}"
    )
    assert says_not_audited(said), f"{said!r} does not say the copy is not audited"


# -- A run in which no test copies the checkout --------------------------------------------------


@pytest.fixture(scope="module")
def no_copy_run(tmp_path_factory) -> AuditRun:
    return run_audit(build_project(tmp_path_factory.mktemp("no-copy"), {}))


def test_a_run_with_no_copy_notes_that_the_copy_rule_set_none_aside(no_copy_run):
    said = copy_notes(no_copy_run)

    assert no_copy_run.unselected_reads_of(ROUTED_TEST) == set(), no_copy_run.describe()
    assert said, f"no note speaks of copies of the checkout\n{no_copy_run.describe()}"
    assert says_none(said), f"{said!r} gives no count of none\n{no_copy_run.describe()}"
