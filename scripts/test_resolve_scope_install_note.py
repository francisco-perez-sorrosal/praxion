"""A JavaScript pocket whose command would install before it tests says so.

In a worktree with no `node_modules`, a package manager's runner (`pnpm exec`, `yarn`, `npx`)
installs the locked dependencies before the tests start. The resolver names that in the pocket's
`notes` and prints it as a `# NOTE` line, so a gate in a fresh worktree is not surprised by it; a
pocket that is installed, or a Python pocket, carries no note and keeps its shape.
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

POCKET = "web"
PACKAGE_JSON = json.dumps({"name": "web", "devDependencies": {"vitest": "1.0.0"}})
FILES = {
    "pyproject.toml": "[tool.pytest.ini_options]\n",
    "tests/test_root.py": "def test_root():\n    pass\n",
    f"{POCKET}/package.json": PACKAGE_JSON,
    f"{POCKET}/pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
    f"{POCKET}/src/a.test.ts": "export {};\n",
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
    _vcs(root, "add", ".")
    _vcs(root, "commit", "-q", "-m", "base")
    return root


def _full(capsys: pytest.CaptureFixture, repo: Path, *extra: str) -> tuple[str, str]:
    exit_code = rts.main(["--full", "--repo-root", str(repo), *extra])
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    return captured.out, captured.err


def _pocket(payload: dict, root: str) -> dict:
    return next(entry for entry in payload["pockets"] if entry["root"] == root)


def test_a_javascript_pocket_without_node_modules_notes_that_its_runner_installs_first(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    out, _ = _full(capsys, repo, "--json")

    notes = _pocket(json.loads(out), POCKET).get("notes", [])

    assert any("`pnpm exec` installs" in text for text in notes), notes


def test_the_plain_form_prints_the_install_note_on_stderr_and_keeps_stdout_runnable(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    out, err = _full(capsys, repo)

    assert f"# NOTE no node_modules in {POCKET}" in err, err
    assert "NOTE" not in out, out


def test_an_installed_javascript_pocket_carries_no_note(
    repo: Path, capsys: pytest.CaptureFixture
) -> None:
    (repo / POCKET / "node_modules").mkdir()

    out, _ = _full(capsys, repo, "--json")

    assert "notes" not in _pocket(json.loads(out), POCKET)


def test_a_python_pocket_carries_no_note(repo: Path, capsys: pytest.CaptureFixture) -> None:
    out, _ = _full(capsys, repo, "--json")

    assert "notes" not in _pocket(json.loads(out), ".")
