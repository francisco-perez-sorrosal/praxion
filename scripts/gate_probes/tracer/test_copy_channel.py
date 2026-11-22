"""Tests for the tracer's `copy` channel: reads made only to copy the checkout as a whole.

A test that lists the checkout with `git ls-files` at the repository root and copies
the listed files, each to a path that keeps its repository path, or that runs a
`copytree` of the repository root, is copying the checkout as a whole; the source-side
reads of those copies go on their own channel so the verdict can set them aside.
Everything short of that stays an ordinary read.
The in-process tests feed the tracer synthetic audit events, the way the tracer's
other unit tests do; one real traced pytest run in a scratch repository proves the
wiring through the interpreter's own events. This file imports only the tracer.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TRACER_DIR = Path(__file__).resolve().parent
TRACER_ENV = ("PX_TRACE_ROOT", "PX_TRACE_OUT", "PX_TRACE_PID", "PX_TRACE_TEST")
TEST_A, TEST_B = "tests/test_a.py", "tests/test_b.py"
LISTING = ["git", "ls-files", "-z"]


def _load_tracer_module():
    """The tracer module, loaded inert under the name the interpreter gives it."""
    spec = importlib.util.spec_from_file_location("sitecustomize", TRACER_DIR / "sitecustomize.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    saved = {key: os.environ.pop(key) for key in TRACER_ENV if key in os.environ}
    try:
        spec.loader.exec_module(module)
    finally:
        os.environ.update(saved)
    return module


@pytest.fixture
def traced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A `Tracer` over a throwaway root, attributing to one test file, with no hook installed."""
    root, out, copy = tmp_path / "root", tmp_path / "out", tmp_path / "copy"
    for directory in (root / "data", out, copy):
        directory.mkdir(parents=True)
    for name in TRACER_ENV[2:]:
        monkeypatch.setenv(name, "")  # registered, so `begin` cannot leak them
    monkeypatch.setenv("PX_TRACE_PID", str(os.getpid()))
    tracer = _load_tracer_module().Tracer(str(root), str(out))
    tracer.begin(TEST_A)
    return SimpleNamespace(tracer=tracer, root=root, out=out, copy=copy)


def _list_checkout(traced: SimpleNamespace, argv=LISTING, cwd: object = "root") -> None:
    directory = traced.root if cwd == "root" else cwd
    traced.tracer.on_audit("subprocess.Popen", (argv[0], argv, directory, None))


def _copy_and_read(traced: SimpleNamespace, source: Path, destination: Path) -> None:
    """What `shutil.copyfile` does to the tracer: its audit event, then the open of its source."""
    traced.tracer.on_audit("shutil.copyfile", (str(source), str(destination)))
    _read(traced, source)


def _read(traced: SimpleNamespace, path: Path) -> None:
    traced.tracer.on_audit("open", (str(path), "rb", os.O_RDONLY))


def _channels(traced: SimpleNamespace) -> list[tuple[str, str, str]]:
    lines = [
        line
        for f in sorted(traced.out.glob("trace-*.jsonl"))
        for line in f.read_text().splitlines()
    ]
    return [(r["t"], r["p"], r["c"]) for r in map(json.loads, lines)]


def test_a_path_keeping_copy_after_listing_the_checkout_is_a_copy_read(
    traced: SimpleNamespace,
) -> None:
    _list_checkout(traced)

    _copy_and_read(traced, traced.root / "data" / "x.txt", traced.copy / "data" / "x.txt")

    assert _channels(traced) == [(TEST_A, "data/x.txt", "copy")]


def test_listing_from_another_directory_with_the_c_option_naming_the_root_counts(
    traced: SimpleNamespace, tmp_path: Path
) -> None:
    _list_checkout(traced, ["git", "-C", str(traced.root), "ls-files"], cwd=tmp_path)

    _copy_and_read(traced, traced.root / "data" / "x.txt", traced.copy / "data" / "x.txt")

    assert [c for _, _, c in _channels(traced)] == ["copy"]


def test_a_copy_by_name_with_no_listing_is_a_direct_read(traced: SimpleNamespace) -> None:
    _copy_and_read(traced, traced.root / "data" / "x.txt", traced.copy / "data" / "x.txt")

    assert _channels(traced) == [(TEST_A, "data/x.txt", "direct")]


@pytest.mark.parametrize(
    ("argv", "directory"),
    [
        (["git", "status"], "root"),
        (["git", "ls-files"], "data"),
        (["git", "-C", "data", "ls-files"], "root"),
        (["ls", "-1"], "root"),
        (["git", "-c", "core.quotepath=off", "log"], "root"),
    ],
    ids=[
        "other-git-command",
        "a-subdirectory",
        "dash-C-a-subdirectory",
        "not-git",
        "option-argument",
    ],
)
def test_a_command_that_does_not_list_the_root_arms_nothing(
    traced: SimpleNamespace, argv: list[str], directory: str
) -> None:
    _list_checkout(traced, argv, cwd=traced.root / directory if directory != "root" else "root")

    _copy_and_read(traced, traced.root / "data" / "x.txt", traced.copy / "data" / "x.txt")

    assert [c for _, _, c in _channels(traced)] == ["direct"]


def test_a_listing_in_one_test_never_classifies_the_next_tests_copy(
    traced: SimpleNamespace,
) -> None:
    _list_checkout(traced)
    traced.tracer.begin(TEST_B)

    _copy_and_read(traced, traced.root / "data" / "x.txt", traced.copy / "data" / "x.txt")

    assert _channels(traced) == [(TEST_B, "data/x.txt", "direct")]


def test_a_copy_to_another_relative_path_is_a_direct_read(traced: SimpleNamespace) -> None:
    _list_checkout(traced)

    _copy_and_read(traced, traced.root / "data" / "x.txt", traced.copy / "renamed.txt")

    assert [c for _, _, c in _channels(traced)] == ["direct"]


def test_a_copy_of_a_file_outside_the_repository_is_not_recorded(
    traced: SimpleNamespace, tmp_path: Path
) -> None:
    _list_checkout(traced)

    _copy_and_read(traced, tmp_path / "elsewhere" / "x.txt", traced.copy / "elsewhere" / "x.txt")

    assert _channels(traced) == []


def _copytree_reading(traced: SimpleNamespace, source: Path, destination: Path, **options) -> None:
    """`shutil.copytree`, with a copy function that makes the audit events a real copy would."""

    def copy_function(file: object, target: str) -> None:
        _copy_and_read(traced, Path(os.fsdecode(file)), Path(target))

    shutil.copytree(source, destination, copy_function=copy_function, **options)


def test_a_copytree_of_the_root_with_an_ignore_filter_is_a_copy_read(
    traced: SimpleNamespace, tmp_path: Path
) -> None:
    (traced.root / "data" / "x.txt").write_text("x\n")
    (traced.root / "data" / "left-out.txt").write_text("y\n")

    _copytree_reading(
        traced, traced.root, tmp_path / "tree", ignore=shutil.ignore_patterns("left-out*")
    )

    assert _channels(traced) == [(TEST_A, "data/x.txt", "copy")]


def test_a_copytree_of_a_directory_below_the_root_is_a_direct_read(
    traced: SimpleNamespace, tmp_path: Path
) -> None:
    (traced.root / "data" / "x.txt").write_text("x\n")

    _copytree_reading(traced, traced.root / "data", tmp_path / "tree")

    assert _channels(traced) == [(TEST_A, "data/x.txt", "direct")]


def test_the_inner_recursion_of_a_copytree_of_the_root_does_not_hide_the_outermost(
    traced: SimpleNamespace, tmp_path: Path
) -> None:
    (traced.root / "data" / "deep").mkdir()
    (traced.root / "data" / "deep" / "y.txt").write_text("y\n")

    _copytree_reading(traced, traced.root, tmp_path / "tree")

    assert _channels(traced) == [(TEST_A, "data/deep/y.txt", "copy")]


def test_a_copytree_of_the_root_leaves_the_tests_other_reads_counted(
    traced: SimpleNamespace, tmp_path: Path
) -> None:
    (traced.root / "data" / "x.txt").write_text("x\n")

    _copytree_reading(traced, traced.root, tmp_path / "tree")
    _read(traced, traced.root / "data" / "x.txt")

    assert sorted(c for _, _, c in _channels(traced)) == ["copy", "direct"]


def test_both_records_exist_for_a_file_the_test_also_opens_itself(traced: SimpleNamespace) -> None:
    _list_checkout(traced)
    target = traced.root / "data" / "x.txt"

    _copy_and_read(traced, target, traced.copy / "data" / "x.txt")
    _read(traced, target)
    _read(traced, target)

    assert sorted(c for _, _, c in _channels(traced)) == ["copy", "direct"]


def test_a_stale_armed_copy_is_cleared_by_the_next_read_of_anything(
    traced: SimpleNamespace,
) -> None:
    _list_checkout(traced)
    target = traced.root / "data" / "x.txt"
    traced.tracer.on_audit("shutil.copyfile", (str(target), str(traced.copy / "data" / "x.txt")))

    _read(traced, traced.root / "data" / "other.txt")  # the copy never opened its source
    _read(traced, target)

    assert [(p, c) for _, p, c in _channels(traced)] == [
        ("data/other.txt", "direct"),
        ("data/x.txt", "direct"),
    ]


def test_a_copy_that_does_not_qualify_disarms_an_earlier_one(traced: SimpleNamespace) -> None:
    _list_checkout(traced)
    target = traced.root / "data" / "x.txt"
    traced.tracer.on_audit("shutil.copyfile", (str(target), str(traced.copy / "data" / "x.txt")))
    traced.tracer.on_audit("shutil.copyfile", (str(target), str(traced.copy / "renamed.txt")))

    _read(traced, target)

    assert [c for _, _, c in _channels(traced)] == ["direct"]


def test_a_write_open_neither_consumes_nor_is_a_copy_read(traced: SimpleNamespace) -> None:
    _list_checkout(traced)
    target = traced.root / "data" / "x.txt"
    traced.tracer.on_audit("shutil.copyfile", (str(target), str(traced.copy / "data" / "x.txt")))

    traced.tracer.on_audit("open", (str(traced.copy / "data" / "x.txt"), "wb", os.O_WRONLY))
    _read(traced, target)

    assert [c for _, _, c in _channels(traced)] == ["copy"]


def test_a_listing_made_in_another_process_arms_nothing(traced: SimpleNamespace) -> None:
    traced.tracer.tracing_pid = os.getpid() + 1
    _list_checkout(traced)
    traced.tracer.tracing_pid = os.getpid()

    _copy_and_read(traced, traced.root / "data" / "x.txt", traced.copy / "data" / "x.txt")

    assert [c for _, _, c in _channels(traced)] == ["direct"]


@pytest.mark.parametrize(
    ("event", "args"),
    [
        ("subprocess.Popen", ()),
        ("subprocess.Popen", (None, "git ls-files", None, None)),
        ("subprocess.Popen", (None, [object()], None, None)),
        ("subprocess.Popen", (None, [], None, None)),
        ("subprocess.Popen", (None, ["git", "ls-files"], object(), None)),
        ("shutil.copyfile", ()),
        ("shutil.copyfile", (object(), object())),
        ("shutil.copyfile", (None, None)),
        ("open", ()),
    ],
    ids=[
        "popen-empty",
        "popen-shell-string",
        "popen-argv-of-objects",
        "popen-empty-argv",
        "popen-cwd-object",
        "copy-empty",
        "copy-objects",
        "copy-none",
        "open-empty",
    ],
)
def test_a_malformed_event_never_raises_and_records_nothing(
    traced: SimpleNamespace, event: str, args: tuple
) -> None:
    traced.tracer.on_audit(event, args)

    assert _channels(traced) == []


# -- One real traced run: the interpreter's own events, in a scratch repository ----------------

COPIES_LISTED_FILES = """\
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_copies_the_listed_data_files(tmp_path):
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    for rel in filter(None, listed.split("\\0")):
        if rel.startswith("data/"):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, tmp_path / rel)
    assert (tmp_path / "data" / "listed.txt").read_text() == "listed\\n"
"""

COPIES_BY_NAME = """\
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_copies_one_file_by_name(tmp_path):
    (tmp_path / "data").mkdir()
    shutil.copy2(ROOT / "data" / "named.txt", tmp_path / "data" / "named.txt")
    assert (tmp_path / "data" / "named.txt").read_text() == "named\\n"
"""

READS_AND_COPIES = """\
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reads_a_listed_file_itself_and_copies_it(tmp_path):
    subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, check=True)
    assert (ROOT / "data" / "both.txt").read_text() == "both\\n"
    (tmp_path / "data").mkdir()
    shutil.copy2(ROOT / "data" / "both.txt", tmp_path / "data" / "both.txt")
"""

COPIES_THE_ROOT = """\
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_copies_the_root_but_not_the_tests(tmp_path):
    shutil.copytree(ROOT, tmp_path / "tree", ignore=shutil.ignore_patterns(".git", "tests"))
    assert (tmp_path / "tree" / "data" / "tree.txt").read_text() == "tree\\n"
"""

COPIES_A_SUBDIRECTORY = """\
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_copies_the_data_directory(tmp_path):
    shutil.copytree(ROOT / "data", tmp_path / "tree")
    assert (tmp_path / "tree" / "sub.txt").read_text() == "sub\\n"
"""


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    files = {
        "data/listed.txt": "listed\n",
        "data/named.txt": "named\n",
        "data/both.txt": "both\n",
        "data/tree.txt": "tree\n",
        "data/sub.txt": "sub\n",
        "tests/test_copies_the_root.py": COPIES_THE_ROOT,
        "tests/test_copies_a_subdirectory.py": COPIES_A_SUBDIRECTORY,
        "tests/test_copies_listed_files.py": COPIES_LISTED_FILES,
        "tests/test_copies_by_name.py": COPIES_BY_NAME,
        "tests/test_reads_and_copies.py": READS_AND_COPIES,
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    for command in (["git", "init", "-q"], ["git", "add", "."]):
        subprocess.run(command, cwd=root, env=git_env, capture_output=True, check=True)
    return root


def test_a_traced_run_classifies_listed_copies_and_leaves_other_reads_alone(
    scratch_repo: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in TRACER_ENV and not k.startswith("GIT_")}
    env.pop("PYTEST_ADDOPTS", None)
    env.update(
        PYTHONPATH=str(TRACER_DIR),
        PYTHONDONTWRITEBYTECODE="1",
        PX_TRACE_ROOT=str(scratch_repo),
        PX_TRACE_OUT=str(out),
    )

    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "selection_trace_plugin", "-p", "no:cacheprovider"]
        + ["-n", "0", "--rootdir", str(scratch_repo), str(scratch_repo)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 0, run.stdout + run.stderr
    lines = [line for f in sorted(out.glob("trace-*.jsonl")) for line in f.read_text().splitlines()]
    reads = {(r["t"], r["p"], r["c"]) for r in map(json.loads, lines) if "p" in r}
    assert ("tests/test_copies_listed_files.py", "data/listed.txt", "copy") in reads
    assert ("tests/test_copies_listed_files.py", "data/listed.txt", "direct") not in reads
    assert ("tests/test_copies_by_name.py", "data/named.txt", "direct") in reads
    assert ("tests/test_copies_by_name.py", "data/named.txt", "copy") not in reads
    assert ("tests/test_reads_and_copies.py", "data/both.txt", "direct") in reads
    assert ("tests/test_reads_and_copies.py", "data/both.txt", "copy") in reads
    assert ("tests/test_copies_the_root.py", "data/tree.txt", "copy") in reads
    assert ("tests/test_copies_the_root.py", "data/tree.txt", "direct") not in reads
    assert ("tests/test_copies_a_subdirectory.py", "data/sub.txt", "direct") in reads
    assert ("tests/test_copies_a_subdirectory.py", "data/sub.txt", "copy") not in reads
