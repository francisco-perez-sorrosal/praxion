"""Behavioral tests for the mechanical readiness check functions.

Each test builds a fixture repository under ``tmp_path`` with a specific set
of marker files, derives the project facts once, and asserts that the relevant
``check()`` predicate returns the correct boolean. The checks are pure and
deterministic — no network, no clocks, no external tools — so a fixed repo
state always yields the same verdict.

Determinism is verified directly: deriving facts twice over the same repo
state must produce byte-identical dicts.
"""

from __future__ import annotations

from pathlib import Path

from scripts.project_metrics.collectors.base import CollectionContext
from scripts.project_metrics.collectors.readiness import checks


def _ctx(repo_root: Path) -> CollectionContext:
    return CollectionContext(repo_root=str(repo_root), window_days=90, git_sha="0" * 40)


def _facts(repo_root: Path) -> dict[str, object]:
    return checks.derive_project_facts(repo_root)


def _write(repo_root: Path, relative: str, content: str = "x") -> None:
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Presence / absence of well-known signals.
# ---------------------------------------------------------------------------


def test_readme_present_passes(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# Project")
    assert checks.has_readme(_ctx(tmp_path), _facts(tmp_path)) is True


def test_readme_absent_fails(tmp_path: Path) -> None:
    assert checks.has_readme(_ctx(tmp_path), _facts(tmp_path)) is False


def test_license_present_passes(tmp_path: Path) -> None:
    _write(tmp_path, "LICENSE", "MIT")
    assert checks.has_license(_ctx(tmp_path), _facts(tmp_path)) is True


def test_gitignore_absent_fails(tmp_path: Path) -> None:
    assert checks.has_gitignore(_ctx(tmp_path), _facts(tmp_path)) is False


def test_build_manifest_detected_for_pyproject(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")
    assert checks.has_build_manifest(_ctx(tmp_path), _facts(tmp_path)) is True


def test_lockfile_detected_for_uv_lock(tmp_path: Path) -> None:
    _write(tmp_path, "uv.lock", "")
    assert checks.has_lockfile(_ctx(tmp_path), _facts(tmp_path)) is True


def test_test_directory_detected(tmp_path: Path) -> None:
    _write(tmp_path, "tests/test_x.py", "def test_x(): pass")
    assert checks.has_test_directory(_ctx(tmp_path), _facts(tmp_path)) is True


def test_editorconfig_detected(tmp_path: Path) -> None:
    _write(tmp_path, ".editorconfig", "root = true")
    assert checks.has_editorconfig(_ctx(tmp_path), _facts(tmp_path)) is True


def test_precommit_config_detected(tmp_path: Path) -> None:
    _write(tmp_path, ".pre-commit-config.yaml", "repos: []")
    assert checks.has_precommit_config(_ctx(tmp_path), _facts(tmp_path)) is True


def test_claude_md_detected(tmp_path: Path) -> None:
    _write(tmp_path, "CLAUDE.md", "# Project")
    assert checks.has_claude_md(_ctx(tmp_path), _facts(tmp_path)) is True


def test_ai_state_directory_detected(tmp_path: Path) -> None:
    (tmp_path / ".ai-state").mkdir()
    assert checks.has_ai_state(_ctx(tmp_path), _facts(tmp_path)) is True


# ---------------------------------------------------------------------------
# Config-parse-backed signals (tomllib reads of pyproject.toml sections).
# ---------------------------------------------------------------------------


def test_linter_config_detected_via_pyproject_ruff_section(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[tool.ruff]\nline-length = 88\n")
    assert checks.has_linter_config(_ctx(tmp_path), _facts(tmp_path)) is True


def test_typecheck_config_detected_via_pyproject_mypy_section(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[tool.mypy]\nstrict = true\n")
    assert checks.has_typecheck_config(_ctx(tmp_path), _facts(tmp_path)) is True


def test_complexity_gate_detected_via_coverage_section(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[tool.coverage.run]\nbranch = true\n")
    assert checks.has_complexity_gate(_ctx(tmp_path), _facts(tmp_path)) is True


def test_malformed_pyproject_does_not_raise(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "this is = = not valid toml [[[")
    # Derivation must degrade gracefully on a malformed manifest.
    facts = _facts(tmp_path)
    assert checks.has_linter_config(_ctx(tmp_path), facts) is False


# ---------------------------------------------------------------------------
# CI signals (heading/text detection in workflow files).
# ---------------------------------------------------------------------------


def test_ci_pipeline_detected_via_github_workflows(tmp_path: Path) -> None:
    _write(tmp_path, ".github/workflows/test.yml", "name: test")
    assert checks.has_ci_pipeline(_ctx(tmp_path), _facts(tmp_path)) is True


def test_ci_runs_tests_detected_when_workflow_invokes_pytest(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/workflows/test.yml",
        "jobs:\n  test:\n    steps:\n      - run: pytest -q\n",
    )
    assert checks.ci_runs_tests(_ctx(tmp_path), _facts(tmp_path)) is True


def test_ci_runs_tests_false_when_workflow_has_no_test_step(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/workflows/lint.yml",
        "jobs:\n  lint:\n    steps:\n      - run: ruff check\n",
    )
    assert checks.ci_runs_tests(_ctx(tmp_path), _facts(tmp_path)) is False


# ---------------------------------------------------------------------------
# Git-hooks detection.
# ---------------------------------------------------------------------------


def test_git_hooks_detected_via_githooks_dir(tmp_path: Path) -> None:
    (tmp_path / ".githooks").mkdir()
    assert checks.has_git_hooks(_ctx(tmp_path), _facts(tmp_path)) is True


def test_git_hooks_ignores_sample_hooks(tmp_path: Path) -> None:
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit.sample").write_text("#!/bin/sh", encoding="utf-8")
    assert checks.has_git_hooks(_ctx(tmp_path), _facts(tmp_path)) is False


def test_git_hooks_detects_installed_hook(tmp_path: Path) -> None:
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").write_text("#!/bin/sh", encoding="utf-8")
    assert checks.has_git_hooks(_ctx(tmp_path), _facts(tmp_path)) is True


# ---------------------------------------------------------------------------
# Determinism — facts derivation is byte-identical across calls.
# ---------------------------------------------------------------------------


def test_derive_project_facts_is_deterministic(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# Project")
    _write(tmp_path, "pyproject.toml", "[tool.ruff]\n")
    _write(tmp_path, "tests/test_x.py", "")
    first = checks.derive_project_facts(tmp_path)
    second = checks.derive_project_facts(tmp_path)
    assert first == second


def test_empty_repo_yields_all_false_facts(tmp_path: Path) -> None:
    facts = checks.derive_project_facts(tmp_path)
    assert all(value is False for value in facts.values())


# ---------------------------------------------------------------------------
# Healthcheck detection — root signals (preserved) and subdir-service signals.
# ---------------------------------------------------------------------------


def test_healthcheck_root_dockerfile_passes(tmp_path: Path) -> None:
    _write(tmp_path, "Dockerfile", "FROM x\nHEALTHCHECK CMD curl -f localhost/healthz\n")
    assert checks.has_healthcheck(_ctx(tmp_path), _facts(tmp_path)) is True


def test_healthcheck_root_package_json_passes(tmp_path: Path) -> None:
    _write(tmp_path, "package.json", '{"scripts": {"health": "curl /healthz"}}')
    assert checks.has_healthcheck(_ctx(tmp_path), _facts(tmp_path)) is True


def test_healthcheck_subdir_dockerfile_passes(tmp_path: Path) -> None:
    _write(tmp_path, "service/Dockerfile", "FROM x\nHEALTHCHECK CMD true\n")
    assert checks.has_healthcheck(_ctx(tmp_path), _facts(tmp_path)) is True


def test_healthcheck_subdir_package_json_passes(tmp_path: Path) -> None:
    _write(tmp_path, "webapp/package.json", '{"routes": ["/healthz"]}')
    assert checks.has_healthcheck(_ctx(tmp_path), _facts(tmp_path)) is True


def test_healthcheck_route_handler_in_subdir_passes(tmp_path: Path) -> None:
    # The Next.js app-router pattern: a route handler inside a health directory.
    _write(tmp_path, "dash/src/app/api/health/route.ts", "export const GET = () => {}")
    assert checks.has_healthcheck(_ctx(tmp_path), _facts(tmp_path)) is True


def test_healthcheck_absent_fails(tmp_path: Path) -> None:
    _write(tmp_path, "src/main.py", "print('hi')")
    assert checks.has_healthcheck(_ctx(tmp_path), _facts(tmp_path)) is False


def test_healthcheck_in_excluded_dir_ignored(tmp_path: Path) -> None:
    # A health route inside an excluded dependency tree must NOT count.
    _write(tmp_path, "node_modules/pkg/app/health/route.js", "export const GET = () => {}")
    assert checks.has_healthcheck(_ctx(tmp_path), _facts(tmp_path)) is False
