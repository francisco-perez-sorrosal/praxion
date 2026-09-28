"""Tests for `resolve_test_scope.py` -- the resolver's CLI/JSON contract.

Gate-liveness contract (`rules/swe/gate-liveness.md`): the resolver decides
how much of a suite runs, so its failure mode is a *false all-clear* -- "no
tests to run" for a change nothing covers. Every widen reason gets its own
canary here (a change the resolver cannot vouch for must escalate), and every
input mode gets its own contract test (agents and humans share one entry
point, so each mode must emit the same schema-2 shape).

This rewrite retires the topology-reading resolver (`--tier`, `--topology`,
`--non-source`) in favour of the four-source Python graph plus declared-deps
list. `scripts/resolve_test_scope.py` still exists (the pre-rewrite,
topology-based implementation the paired step replaces), so collection
succeeds, but every test below calls the new `main(argv) -> int` contract and
asserts the new schema-2 payload shape -- both fail against the current
topology-based module (missing attribute or wrong output shape), which is
the correct RED state for this step.
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

# -- Fixtures and helpers -------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def base_repo(tmp_path: Path) -> Path:
    """A minimal single-pocket Python repo: one source/test pair (a layout
    edge) plus a valid declared-deps list -- the common substrate every
    CLI-contract test in this module starts from."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["pkg", "tests"]\naddopts = "-n auto"\n',
        encoding="utf-8",
    )
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "foo.py").write_text("value = 1\n", encoding="utf-8")
    (pkg / "test_foo.py").write_text(
        "import foo\n\n\ndef test_value():\n    assert foo.value == 1\n",
        encoding="utf-8",
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "declared-deps.toml").write_text(
        "schema = 1\n\n"
        "[[dep]]\n"
        'paths = [".ai-state/decisions/*.md"]\n'
        'tests = ["pkg/test_foo.py"]\n'
        'why = "placeholder mapping for CLI-contract tests"\n',
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


def _run(capsys: pytest.CaptureFixture, repo: Path, *args: str) -> tuple[int, dict]:
    exit_code = rts.main(["--repo-root", str(repo), "--json", *args])
    captured = capsys.readouterr()
    return exit_code, json.loads(captured.out)


# -- Input modes ----------------------------------------------------------


def test_changed_paths_mode_selects_the_layout_test_for_an_explicit_source(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code, payload = _run(capsys, base_repo, "--changed", "pkg/foo.py")

    assert exit_code == 0
    assert payload["schema"] == 2
    assert payload["changed"]["source"] == "explicit"
    assert payload["decision"] == "selected"
    tests = payload["pockets"][0]["tests"]
    assert any(t["path"] == "pkg/test_foo.py" and t["via"] == "layout" for t in tests)


def test_changed_from_mode_diffs_against_the_given_ref(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    base_sha = _git_output(base_repo, "rev-parse", "HEAD")
    (base_repo / "pkg" / "foo.py").write_text("value = 2\n", encoding="utf-8")
    _git(base_repo, "add", "-A")
    _git(base_repo, "commit", "-qm", "change foo")

    exit_code, payload = _run(capsys, base_repo, "--changed-from", base_sha)

    assert exit_code == 0
    assert payload["changed"]["source"].startswith("git-diff:")
    assert "pkg/foo.py" in payload["changed"]["paths"]


def test_full_mode_requests_the_full_suite_for_every_pocket(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code, payload = _run(capsys, base_repo, "--full")

    assert exit_code == 0
    assert payload["changed"]["source"] == "full-requested"
    assert all(p["selection"] == "full" for p in payload["pockets"])


def test_no_args_mode_reads_the_working_tree_diff_plus_untracked(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    (base_repo / "pkg" / "foo.py").write_text("value = 3\n", encoding="utf-8")
    (base_repo / "pkg" / "new_untracked.py").write_text("value = 4\n", encoding="utf-8")

    exit_code, payload = _run(capsys, base_repo)

    assert exit_code == 0
    assert payload["changed"]["source"] == "working-tree"
    assert {"pkg/foo.py", "pkg/new_untracked.py"} <= set(payload["changed"]["paths"])


# -- Widen reasons ---------------------------------------------------------


def test_widens_with_unmapped_path_when_nothing_depends_on_the_change(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    (base_repo / "pkg" / "orphan.py").write_text("value = 1\n", encoding="utf-8")
    _git(base_repo, "add", "-A")
    _git(base_repo, "commit", "-qm", "add orphan")
    parent = _git_output(base_repo, "rev-parse", "HEAD~1")

    exit_code, payload = _run(capsys, base_repo, "--changed-from", parent)

    assert exit_code == 0
    assert payload["decision"] == "widened"
    unmapped = [w for w in payload["widen"] if w["reason"] == "unmapped-path"]
    assert unmapped, payload["widen"]
    assert "pkg/orphan.py" in unmapped[0]["paths"]


def test_widens_with_selector_changed_when_a_resolver_module_changes(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code, payload = _run(capsys, base_repo, "--changed", "scripts/resolve_test_scope.py")

    assert exit_code == 0
    assert payload["decision"] == "widened"
    assert any(w["reason"] == "selector-changed" for w in payload["widen"])


def test_widens_with_declared_deps_changed_when_the_declared_list_itself_changes(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code, payload = _run(capsys, base_repo, "--changed", "tests/declared-deps.toml")

    assert exit_code == 0
    assert payload["decision"] == "widened"
    assert any(w["reason"] == "declared-deps-changed" for w in payload["widen"])


def test_widens_with_declared_deps_invalid_when_the_list_fails_to_parse(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    (base_repo / "tests" / "declared-deps.toml").write_text("schema = 2\n", encoding="utf-8")

    exit_code, payload = _run(capsys, base_repo, "--changed", "pkg/foo.py")

    assert exit_code == 0
    assert payload["decision"] == "widened"
    invalid = [w for w in payload["widen"] if w["reason"] == "declared-deps-invalid"]
    assert invalid, payload["widen"]
    assert "schema" in invalid[0]["detail"]


def test_widens_with_pocket_config_changed_when_pytest_config_changes(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code, payload = _run(capsys, base_repo, "--changed", "pyproject.toml")

    assert exit_code == 0
    assert payload["decision"] == "widened"
    assert any(w["reason"] == "pocket-config-changed" for w in payload["widen"])


# -- nothing-to-run and non-source exemption ---------------------------------


def test_nothing_to_run_when_the_only_change_is_git_ignored(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    exit_code, payload = _run(capsys, base_repo, "--changed", "ignored.log")

    assert exit_code == 0
    assert payload["decision"] == "nothing-to-run"
    assert payload["widen"] == []
    assert {"path": "ignored.log", "rule": "git-ignored"} in payload["ignored_non_source"]


# -- Exit codes -------------------------------------------------------------


def test_conflicting_input_modes_exit_with_a_usage_error(base_repo: Path) -> None:
    exit_code = rts.main(["--repo-root", str(base_repo), "--changed", "pkg/foo.py", "--full"])

    assert exit_code == 2
