"""Tests for the collision-free invocations `resolve_test_scope.py` emits.

One pytest process holds one module per top-level import name, so a pocket's
selected tests that claim a name from two directories cannot share a process.
The fixture repository holds both clash shapes -- a regular package named
`tests` beside the rootdir-level `tests` directory, and two plain modules with
one basename -- and the assertions about collection run the emitted commands.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import resolve_test_scope as rts  # noqa: E402

PACKAGE_TEST = "fitness/tests/test_fit.py"
NAMESPACE_TEST = "tests/acceptance/test_accept.py"
SOLO_TEST = "tests/test_solo.py"
NESTED_PACKAGE_TEST = "tests/orchestration/test_nested.py"
TWIN_TESTS = ("alpha/test_twin.py", "beta/test_twin.py")

FILES = {
    "pyproject.toml": '[tool.pytest.ini_options]\npythonpath = ["."]\n',
    "tests/support.py": "VALUE = 1\n",
    NAMESPACE_TEST: (
        "from tests.support import VALUE\n\n\ndef test_accept():\n    assert VALUE == 1\n"
    ),
    SOLO_TEST: "def test_solo():\n    pass\n",
    "tests/orchestration/__init__.py": "",
    NESTED_PACKAGE_TEST: "def test_nested():\n    pass\n",
    "fitness/tests/__init__.py": "",
    PACKAGE_TEST: "def test_fit():\n    pass\n",
    TWIN_TESTS[0]: "def test_alpha():\n    pass\n",
    TWIN_TESTS[1]: "def test_beta():\n    pass\n",
}


def _vcs(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for name, text in FILES.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _vcs(root, "init", "-q")
    _vcs(root, "config", "user.email", "t@example.invalid")
    _vcs(root, "config", "user.name", "Test User")
    _vcs(root, "config", "commit.gpgsign", "false")
    _vcs(root, "add", "-A")
    _vcs(root, "commit", "-qm", "seed")
    return root


def _pocket(capsys: pytest.CaptureFixture, repo: Path, *changed: str) -> dict:
    exit_code = rts.main(["--repo-root", str(repo), "--json", "--changed", *changed])
    assert exit_code == 0
    pockets = json.loads(capsys.readouterr().out)["pockets"]
    assert len(pockets) == 1
    return pockets[0]


def _paths(argv: list[str]) -> list[str]:
    return [part for part in argv if part.endswith(".py")]


def _arguments(argv: list[str]) -> list[str]:
    """What follows `pytest` in an emitted command, whatever runner prefix precedes it."""
    return argv[argv.index("pytest") + 1 :]


def _collect(repo: Path, argv: list[str]) -> subprocess.CompletedProcess:
    """Run an emitted `pytest ...` command in collect-only mode, apart from the outer session."""
    command = [sys.executable, "-m", "pytest", *_arguments(argv)]
    command += ["--collect-only", "-q", "-p", "no:cacheprovider"]
    return subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)


def test_a_package_and_the_namespace_sharing_a_name_split_into_collectable_invocations(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    pocket = _pocket(capsys, repo, PACKAGE_TEST, NAMESPACE_TEST)

    invocations = [i["argv"] for i in pocket["invocations"]]
    assert len(invocations) == 2
    assert sorted(path for argv in invocations for path in _paths(argv)) == sorted(
        [PACKAGE_TEST, NAMESPACE_TEST]
    )
    assert all(_collect(repo, argv).returncode == 0 for argv in invocations)


def test_the_unsplit_command_would_not_collect(repo: Path) -> None:
    """Pins the premise: the clash is real, so splitting is not cosmetic."""
    assert _collect(repo, ["pytest", PACKAGE_TEST, NAMESPACE_TEST]).returncode != 0


def test_two_plain_modules_with_one_basename_split(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    pocket = _pocket(capsys, repo, *TWIN_TESTS)

    invocations = [i["argv"] for i in pocket["invocations"]]
    assert [_paths(argv) for argv in invocations] == [[TWIN_TESTS[0]], [TWIN_TESTS[1]]]
    assert all(_collect(repo, argv).returncode == 0 for argv in invocations)


def test_every_selected_test_lands_in_exactly_one_invocation_in_selection_order(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    pocket = _pocket(capsys, repo, PACKAGE_TEST, NAMESPACE_TEST, SOLO_TEST, *TWIN_TESTS)

    selected = [t["path"] for t in pocket["tests"]]
    grouped = [path for i in pocket["invocations"] for path in _paths(i["argv"])]
    assert sorted(grouped) == sorted(selected)
    for invocation in pocket["invocations"]:
        paths = _paths(invocation["argv"])
        assert paths == [path for path in selected if path in paths]


def test_a_selection_without_a_clash_is_the_single_invocation_it_always_was(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    pocket = _pocket(capsys, repo, NAMESPACE_TEST, SOLO_TEST)

    (invocation,) = pocket["invocations"]
    assert _arguments(invocation["argv"]) == [t["path"] for t in pocket["tests"]]


def test_a_package_inside_the_namespace_directory_does_not_clash_with_its_siblings(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    pocket = _pocket(capsys, repo, NESTED_PACKAGE_TEST, NAMESPACE_TEST, SOLO_TEST)

    assert len(pocket["invocations"]) == 1
    assert _collect(repo, pocket["invocations"][0]["argv"]).returncode == 0


def test_a_widened_pocket_still_runs_its_whole_suite_as_one_invocation(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    pocket = _pocket(capsys, repo, "scripts/resolve_test_scope.py", PACKAGE_TEST, NAMESPACE_TEST)

    assert pocket["selection"] == "full"
    assert len(pocket["invocations"]) == 1


@pytest.mark.parametrize(
    ("path", "claims"),
    [
        ("test_top.py", (("test_top", ""),)),
        ("tests/test_solo.py", (("test_solo", "tests"), ("tests", ""))),
        ("fitness/tests/test_fit.py", (("tests", "fitness"), ("fitness", ""))),
        ("tests/orchestration/test_nested.py", (("orchestration", "tests"), ("tests", ""))),
    ],
)
def test_import_claims_name_what_pytest_would_import(
    repo: Path, path: str, claims: tuple[tuple[str, str], ...]
) -> None:
    assert rts._import_claims(repo, path) == claims
