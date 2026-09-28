"""The shipped test workflow's Python step, run for real against tiny projects.

Onboarding installs `claude/project-baseline/tests/test.yml.tmpl` into managed
projects. Its Python step must pass a brand-new project that has no tests yet
(pytest exits 5 on an empty collection, but reports 1 once a coverage floor is
set), and must still enforce the floor once tests exist. Structure checks
cannot tell those apart, so this runs the step's own shell with the
placeholders filled in.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = PROJECT_ROOT / "claude" / "project-baseline" / "tests" / "test.yml.tmpl"
PYTEST_BASELINE = PROJECT_ROOT / "skills" / "python-development" / "assets" / "pytest-baseline.toml"


def _python_step_script(floor: int) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("{{FULL_TEST_COMMAND}}", f"{sys.executable} -m pytest")
    text = text.replace("{{COVERAGE_FLOOR}}", str(floor))
    steps = yaml.safe_load(text)["jobs"]["test-python"]["steps"]
    (step,) = [s for s in steps if "coverage floor" in s.get("name", "")]
    return step["run"]


def _project(tmp_path: Path, tests: dict[str, str]) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        PYTEST_BASELINE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    for name, body in tests.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def _run(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def test_a_project_with_no_tests_yet_passes(tmp_path: Path) -> None:
    result = _run(_python_step_script(floor=80), _project(tmp_path, {}))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No tests collected yet" in result.stdout


def test_the_floor_still_fails_an_undercovered_project(tmp_path: Path) -> None:
    project = _project(
        tmp_path, {"test_trivial.py": "import app\n\n\ndef test_imports():\n    assert app\n"}
    )
    result = _run(_python_step_script(floor=100), project)
    assert result.returncode != 0, "a covered-below-floor suite must fail the step"


def test_a_covered_project_passes_the_floor(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        {"test_app.py": "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"},
    )
    result = _run(_python_step_script(floor=0), project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "junit.xml").is_file()
