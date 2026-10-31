"""Cursor, Codex and live-linked installs reach workflows as skills; the gates watch skill bodies;
test selection follows each moved workflow."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from tests.acceptance.drivers.command_migration import FIXTURES, names
from tests.acceptance.drivers.installers import (
    REPO_ROOT,
    codex_project,
    dev_link_home,
    findings,
    run_codex_install,
    run_cursor_install,
    run_dev_link,
    run_gate,
    snapshot,
    write,
)

# --- Cursor -----------------------------------------------------------------------------------


def test_the_cursor_command_exporter_is_gone():
    assert not (REPO_ROOT / "cursor" / "config" / "export-cursor-commands.py").exists()


# What the retired exporter wrote: every workflow export began with the description header it
# prepended; the guidance page was copied as CLAUDE.md and began with its own heading.
_STALE_EXPORT = "**Description:** left by an earlier install\n---\nthe old body\n"
_STALE_GUIDANCE = "# Commands\n\nSlash commands invocable during interactive sessions.\n"
_USERS_OWN = "the user's own command\n"


def _cursor_project_with(tmp_path, *stale, own=()):
    project = tmp_path / "project"
    for name in stale:
        body = _STALE_GUIDANCE if name == "CLAUDE.md" else _STALE_EXPORT
        write(project, f".cursor/commands/{name}", body)
    for name in own:
        write(project, f".cursor/commands/{name}", _USERS_OWN)
    return project


def test_a_cursor_reinstall_sweeps_stale_workflow_exports_and_keeps_the_users_own(tmp_path):
    # The user's own files survive: one with its own name, one named after a Praxion skill that
    # was never exported as a workflow, and one written by hand after upgrading under a workflow's
    # name (it lacks the header every real export carried). The guidance page export goes too, and
    # so do exports of workflows that releases before the last base wrote and retired since.
    project = _cursor_project_with(
        tmp_path,
        "co.md",
        "cop.md",
        "CLAUDE.md",
        "refresh-topology.md",
        "create_worktree.md",
        own=("my-own-shortcut.md", "code-review.md", "test.md"),
    )

    result = run_cursor_install(tmp_path, project)

    commands = project / ".cursor" / "commands"
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert sorted(p.name for p in commands.iterdir()) == [
        "code-review.md",
        "my-own-shortcut.md",
        "test.md",
    ]
    assert all(
        (commands / name).read_text(encoding="utf-8") == _USERS_OWN
        for name in (
            "my-own-shortcut.md",
            "code-review.md",
            "test.md",
        )
    )


def test_a_cursor_reinstall_removes_the_commands_directory_it_leaves_empty(tmp_path):
    project = _cursor_project_with(tmp_path, "co.md", "test.md")

    result = run_cursor_install(tmp_path, project)

    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert not (project / ".cursor" / "commands").exists()


def test_a_cursor_reinstall_reports_how_many_stale_exports_it_removed(tmp_path):
    project = _cursor_project_with(tmp_path, "co.md", "cop.md", "release.md")

    result = run_cursor_install(tmp_path, project)

    reporting = [
        ln
        for ln in result.stdout.splitlines()
        if "/" not in ln
        and re.search(r"\b3\b", ln)
        and re.search(r"remov|swept|sweep|prun|clean|delet", ln, re.IGNORECASE)
    ]
    assert reporting, result.stdout[-2000:]


def test_the_cursor_dry_run_succeeds_without_writing(tmp_path):
    project = _cursor_project_with(tmp_path, "co.md", "my-own-shortcut.md")
    before = snapshot(project)

    result = run_cursor_install(tmp_path, project, "--dry-run")

    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert snapshot(project) == before


# --- Codex ------------------------------------------------------------------------------------


def test_the_codex_command_exporter_is_gone():
    assert not (REPO_ROOT / "codex" / "config" / "export-codex-command-skills.py").exists()


def _plant_legacy_wrapper(project):
    target = project / ".agents" / "skills" / "praxion-command-co"
    shutil.copytree(FIXTURES / "legacy_codex_wrapper" / "praxion-command-co", target)


def test_a_codex_reinstall_prunes_every_legacy_command_wrapper(tmp_path):
    project = codex_project(tmp_path)
    _plant_legacy_wrapper(project)

    result = run_codex_install(tmp_path, project)

    left = sorted(p.name for p in (project / ".agents" / "skills").glob("praxion-command-*"))
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert not left, left


@pytest.fixture(scope="module")
def codex_install(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("codex")
    project = codex_project(tmp_path)
    result = run_codex_install(tmp_path, project)
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    return project


@pytest.mark.parametrize("name", names())
def test_a_codex_install_provides_each_workflow_through_the_skill_wrapper_named_after_it(
    codex_install, name
):
    wrapper = codex_install / ".agents" / "skills" / name / "SKILL.md"
    definition = str((REPO_ROOT / "skills" / name / "SKILL.md").resolve()).replace("\\", "/")

    assert wrapper.is_file(), f"no Codex wrapper named {name}"
    assert definition in wrapper.read_text(encoding="utf-8")


def test_the_codex_dry_run_succeeds_without_writing(tmp_path):
    project = codex_project(tmp_path)
    _plant_legacy_wrapper(project)
    before = snapshot(project)

    result = run_codex_install(tmp_path, project, "--dry-run")

    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert snapshot(project) == before


def test_the_codex_skill_export_parses_every_migrated_skill(tmp_path):
    result = subprocess.run(
        ["python3", "codex/config/export-codex-skills.py", "--repo-root", str(REPO_ROOT), "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    missing = [n for n in names() if not (tmp_path / n / "SKILL.md").is_file()]

    assert result.returncode == 0, result.stderr[-1500:]
    assert not missing, missing


# --- live-linked development -------------------------------------------------------------------


def test_a_live_link_serves_skills_hooks_and_scripts_from_the_checkout(tmp_path):
    paths = dev_link_home(tmp_path)

    result = run_dev_link(paths, "--dev-link")

    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    for surface in ("skills", "hooks", "scripts"):
        assert (paths["cache"] / surface).is_symlink(), f"{surface} is not linked"
        assert os.path.realpath(paths["cache"] / surface) == os.path.realpath(
            paths["source"] / surface
        )


def test_a_live_link_links_no_commands_tree(tmp_path):
    paths = dev_link_home(tmp_path)

    run_dev_link(paths, "--dev-link")

    assert not (paths["cache"] / "commands").is_symlink()


def test_turning_the_live_link_off_restores_the_fetched_skills(tmp_path):
    paths = dev_link_home(tmp_path)
    run_dev_link(paths, "--dev-link")

    result = run_dev_link(paths, "--dev-link=off")

    skills = paths["cache"] / "skills"
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert skills.is_dir()
    assert not skills.is_symlink()
    assert (skills / "marker.txt").read_text(encoding="utf-8") == "fetched-copy\n"


# --- gate liveness and argument-hint conformance over skill bodies -----------------------------

_GATE = "import zz_absent_package_for_liveness\n"


def _liveness_tree(tmp_path, caller_path, caller_text):
    root = tmp_path / "repo"
    write(root, "scripts/check_zz_widget.py", _GATE)
    write(root, caller_path, caller_text)
    return root


def _mentions(found, needle):
    return [f for f in found if needle in json.dumps(f)]


def test_an_agent_running_a_script_that_needs_an_absent_package_is_an_ambient_import_finding(
    tmp_path,
):
    root = _liveness_tree(
        tmp_path,
        "agents/zz-agent.md",
        "---\nname: zz\n---\nRun `python3 scripts/check_zz_widget.py`.\n",
    )

    report = run_gate("check_gate_liveness.py", "--check", "ambient-import", "--root", str(root))

    assert _mentions(findings(report, "GL05"), "check_zz_widget"), report


def test_a_skill_running_a_script_that_needs_an_absent_package_is_an_ambient_import_finding(
    tmp_path,
):
    root = _liveness_tree(
        tmp_path,
        "skills/zz-skill/SKILL.md",
        "---\nname: zz-skill\ndescription: zz\n---\nRun `python3 scripts/check_zz_widget.py`.\n",
    )

    report = run_gate("check_gate_liveness.py", "--check", "ambient-import", "--root", str(root))

    assert _mentions(findings(report, "GL05"), "check_zz_widget"), report


def test_a_gate_nothing_calls_is_an_uninvoked_gate_finding(tmp_path):
    root = tmp_path / "repo"
    write(root, "scripts/check_zz_lonely.py", "print('ok')\n")
    write(root, "agents/zz-agent.md", "---\nname: zz\n---\nNothing to run.\n")

    report = run_gate("check_gate_liveness.py", "--check", "uninvoked-gate", "--root", str(root))

    assert _mentions(findings(report, "GL04"), "check_zz_lonely"), report


def test_a_gate_whose_only_caller_is_a_skill_body_is_not_an_uninvoked_gate(tmp_path):
    root = tmp_path / "repo"
    write(root, "scripts/check_zz_lonely.py", "print('ok')\n")
    write(
        root,
        "skills/zz-skill/SKILL.md",
        "---\nname: zz-skill\ndescription: zz\n---\nRun `python3 scripts/check_zz_lonely.py`.\n",
    )

    report = run_gate("check_gate_liveness.py", "--check", "uninvoked-gate", "--root", str(root))

    assert not _mentions(findings(report, "GL04"), "check_zz_lonely"), report


def _conformance(tmp_path, skill_body, description="Run the zz workflow"):
    root = tmp_path / "repo"
    write(
        root,
        "skills/zz-flow/SKILL.md",
        f'---\nname: zz-flow\ndescription: "{description}"\nargument-hint: "[target]"\n---\n{skill_body}\n',
    )
    return run_gate("check_artifact_conformance.py", "--repo-root", str(root))


def test_a_skill_that_declares_a_hint_and_never_reads_its_arguments_is_reported(tmp_path):
    report = _conformance(tmp_path, "Do the thing.")

    assert _mentions(findings(report, "S04"), "zz-flow"), report


def test_a_skill_that_declares_a_hint_and_reads_its_arguments_is_not_reported(tmp_path):
    report = _conformance(tmp_path, "Act on `$ARGUMENTS`.")

    assert not _mentions(findings(report, "S04"), "zz-flow"), report


@pytest.mark.parametrize("variable", ["${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_SKILL_DIR}"])
def test_a_harness_path_variable_does_not_count_as_reading_the_arguments(tmp_path, variable):
    report = _conformance(tmp_path, f"Run `{variable}/scripts/zz.py`.")

    assert _mentions(findings(report, "S04"), "zz-flow"), report


@pytest.mark.parametrize("description", ["", "TODO"])
def test_a_skill_with_an_empty_or_placeholder_description_is_reported_under_the_description_check(
    tmp_path, description
):
    report = _conformance(tmp_path, "Act on `$ARGUMENTS`.", description=description)

    assert _mentions(findings(report, "C04"), "zz-flow"), report


def test_no_gate_hook_or_pre_commit_pattern_names_the_retired_directory():
    surfaces = (
        sorted(REPO_ROOT.glob("scripts/check_*.py"))
        + sorted(REPO_ROOT.glob("hooks/*.py"))
        + sorted(REPO_ROOT.glob("hooks/*.sh"))
    )
    surfaces.append(REPO_ROOT / ".pre-commit-config.yaml")
    naming = [
        str(p.relative_to(REPO_ROOT))
        for p in surfaces
        if p.is_file()
        and any(
            t in p.read_text(encoding="utf-8")
            for t in (
                '"commands/',
                "'commands/",
                "^commands/",
                '"commands"',
                "'commands'",
                "|commands/",
            )
        )
    ]

    assert not naming, naming


# --- test selection follows the moved workflows -------------------------------------------------

_BEFORE = json.loads((FIXTURES / "selection_before.json").read_text(encoding="utf-8"))["selected"]


# The one recorded test the change deletes on purpose: the Codex command-wrapper exporter goes
# with its tests. The frozen record keeps the path as history; it is compared only while it exists.
DELETED_ON_PURPOSE = {"scripts/test_export_codex_command_skills.py"}

# A recorded test a later change stops reaching on purpose, with its reason. The git-runner
# migration test was selected by a skill edit only through `check_id_citation_discipline.py`,
# whose exempt `skills/` prefix is a path literal; once that gate's git calls moved to
# `_commit_scope.py` the migration test names that module instead, and the edge went with it.
UNREACHED_ON_PURPOSE = {"scripts/test__git_runner.py"}


def _selected(changed: str) -> set[str] | None:
    result = subprocess.run(
        ["python3", "scripts/resolve_test_scope.py", "--changed", changed, "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    data = json.loads(result.stdout)
    if any(p.get("selection") != "tests" for p in data["pockets"] if p.get("root") == "."):
        return None
    return {t["path"] for p in data["pockets"] for t in (p.get("tests") or [])}


@pytest.mark.parametrize(
    "name", ["co", "test", "resume-pipeline", "merge-worktree", "eval-praxion", "dashboard"]
)
def test_editing_a_moved_workflow_selects_narrowly_every_test_its_old_file_selected(name):
    recorded = set(_BEFORE[name]["tests"])
    expected = {t for t in recorded if (REPO_ROOT / t).is_file()} - UNREACHED_ON_PURPOSE
    vanished = recorded - expected - DELETED_ON_PURPOSE - UNREACHED_ON_PURPOSE

    after = _selected(f"skills/{name}/SKILL.md")

    assert not vanished, (
        f"recorded tests missing from the tree for no stated reason: {sorted(vanished)}"
    )
    assert after is not None, "the selection widened to the whole suite"
    assert not expected - after, sorted(expected - after)


def test_no_declared_test_dependency_points_at_a_moved_workflow_file():
    declared = (REPO_ROOT / "tests" / "declared-deps.toml").read_text(encoding="utf-8")
    moved = {f"commands/{n}.md" for n in names()}
    stale = sorted(moved & set(re.findall(r"commands/[a-z0-9-]+\.md", declared)))

    assert not stale, stale
