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


# -- Renames, deletions and uncommitted edits --------------------------------


def _selected_paths(payload: dict) -> set[str]:
    return {t["path"] for pocket in payload["pockets"] for t in pocket["tests"]}


def _invocation_args(payload: dict) -> list[str]:
    return [
        arg
        for pocket in payload["pockets"]
        for invocation in pocket["invocations"]
        for arg in invocation["argv"]
    ]


def _add_literal_reader(repo: Path, name: str, literal: str) -> None:
    (repo / "tests" / name).write_text(
        f'TARGET = "{literal}"\n\n\ndef test_reads():\n    assert TARGET\n', encoding="utf-8"
    )


@pytest.fixture
def rename_repo(base_repo: Path) -> Path:
    """`config/a.yaml` plus a test that reads it by path, both committed."""
    (base_repo / "config").mkdir()
    (base_repo / "config" / "a.yaml").write_text("key: 1\n", encoding="utf-8")
    _add_literal_reader(base_repo, "test_reads_config.py", "config/a.yaml")
    _git(base_repo, "add", "-A")
    _git(base_repo, "commit", "-qm", "add config and its reader")
    return base_repo


def _assert_old_path_reader_covered(payload: dict) -> None:
    assert "config/a.yaml" in payload["changed"]["paths"]
    assert "config/b.yaml" in payload["changed"]["paths"]
    covered = "tests/test_reads_config.py" in _selected_paths(payload)
    assert covered or payload["decision"] == "widened", payload


def test_a_staged_rename_counts_the_old_path_as_changed(
    rename_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    _git(rename_repo, "mv", "config/a.yaml", "config/b.yaml")

    exit_code, payload = _run(capsys, rename_repo)

    assert exit_code == 0
    _assert_old_path_reader_covered(payload)


def test_a_committed_rename_counts_the_old_path_as_changed(
    rename_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    base_sha = _git_output(rename_repo, "rev-parse", "HEAD")
    _git(rename_repo, "mv", "config/a.yaml", "config/b.yaml")
    _git(rename_repo, "commit", "-qm", "rename config")

    exit_code, payload = _run(capsys, rename_repo, "--changed-from", base_sha)

    assert exit_code == 0
    _assert_old_path_reader_covered(payload)


def test_changed_from_includes_uncommitted_edits_to_tracked_files(
    base_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    base_sha = _git_output(base_repo, "rev-parse", "HEAD")
    (base_repo / "pkg" / "foo.py").write_text("value = 5\n", encoding="utf-8")

    exit_code, payload = _run(capsys, base_repo, "--changed-from", base_sha)

    assert exit_code == 0
    assert "pkg/foo.py" in payload["changed"]["paths"]
    assert payload["decision"] == "selected"
    assert "pkg/test_foo.py" in _selected_paths(payload)


@pytest.fixture
def deletion_repo(base_repo: Path) -> Path:
    """`pkg/foo.py` with its layout test plus a second test reading it by path;
    the declared list names only the survivor, so deleting the pair leaves it valid."""
    _add_literal_reader(base_repo, "test_reads_foo.py", "pkg/foo.py")
    (base_repo / "tests" / "declared-deps.toml").write_text(
        "schema = 1\n\n"
        "[[dep]]\n"
        'paths = [".ai-state/decisions/*.md"]\n'
        'tests = ["tests/test_reads_foo.py"]\n'
        'why = "decision records feed the reader test"\n',
        encoding="utf-8",
    )
    _git(base_repo, "add", "-A")
    _git(base_repo, "commit", "-qm", "add a reader of foo")
    return base_repo


def test_a_deleted_test_file_is_never_emitted_as_a_target(
    deletion_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    _git(deletion_repo, "rm", "-q", "pkg/test_foo.py")

    exit_code, payload = _run(capsys, deletion_repo)

    assert exit_code == 0
    assert "pkg/test_foo.py" in payload["changed"]["paths"]
    assert payload["decision"] == "nothing-to-run", payload
    assert not any("test_foo.py" in arg for arg in _invocation_args(payload))


def test_a_deleted_source_selects_its_surviving_tests_only(
    deletion_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    _git(deletion_repo, "rm", "-q", "pkg/foo.py", "pkg/test_foo.py")

    exit_code, payload = _run(capsys, deletion_repo)

    assert exit_code == 0
    assert payload["decision"] == "selected", payload
    assert _selected_paths(payload) == {"tests/test_reads_foo.py"}
    assert not any("test_foo.py" in arg for arg in _invocation_args(payload))


# -- --per-path: one payload per changed path, from one process --------------------

PER_PATH_SAMPLE = (
    "pkg/foo.py",  # layout edge (and the declared list names its test)
    "lib/helper.py",  # import edge
    "data/table.csv",  # path-literal edge
    ".ai-state/decisions/001-choice.md",  # declared edge
    "pkg/orphan.py",  # reaches no test: widens
    "README.md",  # reaches no test and is root narrative: ignored
    "scripts/_python_selection.py",  # a resolver source: widens
    "pkg/deleted.py",  # not in the inventory
)


@pytest.fixture
def per_path_repo(base_repo: Path) -> Path:
    """`base_repo` plus one path for every edge source, a widening one and an ignored one."""
    files = {
        "lib/helper.py": "value = 2\n",
        "tests/test_uses_helper.py": "import helper\n\n\ndef test_it():\n    assert helper.value\n",
        "data/table.csv": "a,b\n",
        "tests/test_reads_table.py": 'NAME = "table.csv"\n\n\ndef test_it():\n    assert NAME\n',
        ".ai-state/decisions/001-choice.md": "# choice\n",
        "pkg/orphan.py": "value = 3\n",
        "README.md": "# repo\n",
    }
    for rel, text in files.items():
        target = base_repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(base_repo, "add", "-A")
    _git(base_repo, "commit", "-qm", "one path per edge source")
    return base_repo


def _per_path_lines(capsys: pytest.CaptureFixture, repo: Path, *paths: str) -> list[str]:
    exit_code = rts.main(["--repo-root", str(repo), "--json", "--per-path", "--changed", *paths])
    assert exit_code == 0
    return capsys.readouterr().out.splitlines()


def _single_path_line(capsys: pytest.CaptureFixture, repo: Path, path: str) -> str:
    """What `--changed <path> --json` prints, on one line: the same payload, the same bytes."""
    _, payload = _run(capsys, repo, "--changed", path)
    return json.dumps(payload)


@pytest.mark.parametrize("path", PER_PATH_SAMPLE)
def test_per_path_line_equals_single_path_output_for_each_edge_source(
    per_path_repo: Path, capsys: pytest.CaptureFixture, path: str
) -> None:
    lines = _per_path_lines(capsys, per_path_repo, *PER_PATH_SAMPLE)

    by_path = {json.loads(line)["changed"]["paths"][0]: line for line in lines}
    assert len(lines) == len(PER_PATH_SAMPLE)
    assert by_path[path] == _single_path_line(capsys, per_path_repo, path)


def test_per_path_sample_covers_selected_widened_and_ignored_outcomes(
    per_path_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    lines = _per_path_lines(capsys, per_path_repo, *PER_PATH_SAMPLE)
    payloads = [json.loads(line) for line in lines]

    decisions = {p["changed"]["paths"][0]: p["decision"] for p in payloads}
    assert decisions["pkg/foo.py"] == "selected"
    assert decisions["pkg/orphan.py"] == "widened"
    assert decisions["scripts/_python_selection.py"] == "widened"
    assert decisions["README.md"] == "nothing-to-run"
    ignored = {p["changed"]["paths"][0]: p["ignored_non_source"] for p in payloads}
    assert ignored["README.md"] == [{"path": "README.md", "rule": "root-narrative"}]


def test_per_path_lines_follow_the_sorted_unique_changed_paths(
    per_path_repo: Path, capsys: pytest.CaptureFixture
) -> None:
    lines = _per_path_lines(capsys, per_path_repo, "pkg/orphan.py", "pkg/foo.py", "./pkg/foo.py")

    firsts = [json.loads(line)["changed"]["paths"][0] for line in lines]
    assert firsts == ["pkg/foo.py", "pkg/orphan.py"]


@pytest.mark.parametrize(
    "args",
    [
        ["--per-path", "--json"],
        ["--per-path", "--changed", "pkg/foo.py"],
        ["--per-path", "--json", "--changed-from", "HEAD"],
        ["--per-path", "--json", "--full"],
    ],
    ids=["no-changed", "no-json", "changed-from", "full"],
)
def test_per_path_without_changed_and_json_is_a_usage_error(
    per_path_repo: Path, capsys: pytest.CaptureFixture, args: list[str]
) -> None:
    exit_code = rts.main(["--repo-root", str(per_path_repo), *args])

    assert exit_code == 2
    assert capsys.readouterr().out == ""


def test_per_path_builds_the_import_graph_once_for_every_inventory_path(
    per_path_repo: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[int] = []
    original_init = rts.Graph.__init__

    def counting_init(self: object, *args: object, **kwargs: object) -> None:
        built.append(1)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(rts.Graph, "__init__", counting_init)
    inventory_paths = [p for p in PER_PATH_SAMPLE if p != "pkg/deleted.py"]

    lines = _per_path_lines(capsys, per_path_repo, *inventory_paths)

    assert len(lines) == len(inventory_paths)
    assert len(built) == 1
