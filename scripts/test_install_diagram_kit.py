"""Tests for install_diagram_kit.py: the onboarding installer of the architecture-diagram kit.

Each test installs into a temporary git repository and asserts on what ends up on disk and
on the one-line-per-item report: a fresh project receives the whole kit, a second run
changes nothing, an existing model or command is never overwritten, and a project the
installer cannot serve is refused with the precondition exit code.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_diagram_kit as kit  # noqa: E402


def _plugin_root() -> Path:
    """The checkout holding the kit; found by its templates because the mutation sensor runs
    these tests from a copy of `scripts/` one directory deeper."""
    here = Path(__file__).resolve()
    return next(p for p in here.parents if (p / "claude" / "aac-templates").is_dir())


PLUGIN = _plugin_root()
COMMAND = Path("scripts/regenerate_diagrams.py")
WORKFLOW = Path(".github/workflows/architecture.yml")
MODEL_DIR = Path("docs/diagrams/architecture/src")
MODEL_FILES = (MODEL_DIR / "_spec.c4", MODEL_DIR / "architecture.c4")
TESTKIT = "_diagram_testkit"


def _git_project(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    return path


@pytest.fixture
def project(tmp_path) -> Path:
    return _git_project(tmp_path / "project")


def _install(project: Path, *extra: str, plugin: Path = PLUGIN) -> int:
    return kit.main(["--project-root", str(project), "--plugin-root", str(plugin), *extra])


def _report(capsys) -> list[str]:
    return capsys.readouterr().out.splitlines()


def _tree(project: Path) -> dict[str, str]:
    return {
        str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(project.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(project).parts
    }


def _sibling_modules_imported_by(command: Path) -> set[str]:
    """The names `command` imports from its own directory, followed transitively (regex read)."""
    found: set[str] = set()
    pending = [command]
    while pending:
        text = pending.pop().read_text(encoding="utf-8")
        for name in re.findall(r"^(?:from|import)\s+(_diagram_\w+)", text, re.MULTILINE):
            if name not in found:
                found.add(name)
                pending.append(command.parent / f"{name}.py")
    return found


# --- a fresh project ----------------------------------------------------------------------------


def test_a_fresh_project_receives_the_model_the_command_and_the_workflow(project, capsys):
    assert _install(project) == 0

    installed = {line.removeprefix("installed ") for line in _report(capsys)}
    assert {str(p) for p in (*MODEL_FILES, COMMAND, WORKFLOW)} <= installed
    for path in (*MODEL_FILES, COMMAND, WORKFLOW):
        assert (project / path).is_file()


def test_the_model_is_the_style_kit_and_the_example_with_the_template_suffix_removed(project):
    _install(project)

    templates = PLUGIN / "claude" / "aac-templates"
    assert (project / MODEL_FILES[0]).read_bytes() == (
        templates / "likec4-style-kit.c4.tmpl"
    ).read_bytes()
    assert (project / MODEL_FILES[1]).read_bytes() == (
        templates / "likec4-example-model.c4.tmpl"
    ).read_bytes()


def test_the_copied_modules_are_exactly_the_command_s_transitive_sibling_imports(project):
    _install(project)

    copied = {p.stem for p in (project / "scripts").glob("*.py")} - {COMMAND.stem}
    assert copied == _sibling_modules_imported_by(PLUGIN / COMMAND)
    assert copied
    assert TESTKIT not in copied


def test_the_copied_command_runs_from_the_project_root(project):
    _install(project)

    result = subprocess.run(
        [sys.executable, str(COMMAND), "--help"], cwd=project, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert "--check" in result.stdout


def test_the_command_set_is_copied_byte_for_byte(project):
    _install(project)

    for installed in (project / "scripts").glob("*.py"):
        assert installed.read_bytes() == (PLUGIN / "scripts" / installed.name).read_bytes()


# --- the workflow's substitutions -----------------------------------------------------------------


def _workflow_lines(project: Path) -> list[str]:
    text = (project / WORKFLOW).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def test_the_workflow_defaults_to_the_diagrams_directory_and_python_3_13(project):
    _install(project)

    lines = "\n".join(_workflow_lines(project))
    assert "{{PROJECT_" not in lines
    assert '"docs/diagrams/**"' in lines
    assert "python3 scripts/regenerate_diagrams.py --diagrams-dir docs/diagrams" in lines
    assert 'python-version: "3.13"' in lines


def test_the_workflow_takes_the_projects_requires_python_lower_bound(project):
    (project / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11,<4"\n', encoding="utf-8"
    )

    _install(project)

    assert 'python-version: "3.11"' in "\n".join(_workflow_lines(project))


def test_a_pyproject_without_requires_python_leaves_the_default(project):
    (project / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    _install(project)

    assert 'python-version: "3.13"' in "\n".join(_workflow_lines(project))


def test_the_workflow_keeps_its_comment_header_unsubstituted(project):
    _install(project)

    header = (project / WORKFLOW).read_text(encoding="utf-8").splitlines()[:12]
    assert any("{{PROJECT_PATHS_DIAGRAMS}}" in line for line in header)


def test_a_custom_diagrams_directory_moves_the_model_and_the_workflow_paths(project, capsys):
    assert _install(project, "--diagrams-dir", "docs/arch/") == 0

    assert (project / "docs/arch/architecture/src/_spec.c4").is_file()
    assert not (project / "docs/diagrams").exists()
    lines = "\n".join(_workflow_lines(project))
    assert "--diagrams-dir docs/arch" in lines
    assert "git status --porcelain -- docs/arch/" in lines


# --- a second run ---------------------------------------------------------------------------------


def test_a_second_run_skips_every_item_and_changes_no_file(project, capsys):
    _install(project)
    first = _report(capsys)
    before = _tree(project)

    assert _install(project) == 0

    second = _report(capsys)
    assert _tree(project) == before
    assert len(second) == len(first)
    assert all(line.startswith("skipped ") for line in second)


def test_a_diagrams_directory_holding_only_a_gitkeep_receives_the_kit(project):
    (project / "docs/diagrams").mkdir(parents=True)
    (project / "docs/diagrams/.gitkeep").write_text("", encoding="utf-8")

    _install(project)

    assert all((project / path).is_file() for path in MODEL_FILES)


# --- nothing the user owns is overwritten -----------------------------------------------------------


def test_an_existing_model_anywhere_under_the_diagrams_directory_keeps_the_kit_out(project, capsys):
    mine = project / "docs/diagrams/shop/src/shop.c4"
    mine.parent.mkdir(parents=True)
    mine.write_text("model { }\n", encoding="utf-8")

    assert _install(project) == 0

    assert mine.read_text(encoding="utf-8") == "model { }\n"
    assert not any((project / path).exists() for path in MODEL_FILES)
    skipped = [line for line in _report(capsys) if line.startswith("skipped docs/")]
    assert len(skipped) == 2
    assert "docs/diagrams/shop/src/shop.c4" in skipped[0]
    assert (project / COMMAND).is_file()
    assert (project / WORKFLOW).is_file()


def test_an_existing_command_keeps_the_whole_set_out_so_the_versions_never_mix(project, capsys):
    (project / "scripts").mkdir()
    (project / COMMAND).write_text("# my copy\n", encoding="utf-8")

    _install(project)

    assert (project / COMMAND).read_text(encoding="utf-8") == "# my copy\n"
    assert [p.name for p in (project / "scripts").iterdir()] == [COMMAND.name]
    set_lines = [line for line in _report(capsys) if line.split(" ", 1)[1].startswith("scripts/")]
    assert len(set_lines) > 1
    assert all(
        line.endswith("(the command is already installed; its set is kept as it is)")
        for line in set_lines
    )


def test_an_existing_workflow_is_left_as_it_is(project):
    (project / WORKFLOW).parent.mkdir(parents=True)
    (project / WORKFLOW).write_text("name: mine\n", encoding="utf-8")

    _install(project)

    assert (project / WORKFLOW).read_text(encoding="utf-8") == "name: mine\n"


def test_a_dry_run_reports_what_it_would_install_and_writes_nothing(project, capsys):
    before = _tree(project)

    assert _install(project, "--dry-run") == 0

    assert _tree(project) == before
    report = _report(capsys)
    assert report
    assert all(line.startswith("would install ") for line in report)
    assert f"would install {WORKFLOW}" in report


# --- a plugin laid out on its own: the script's default plugin root and the template markers ---


@pytest.fixture
def plugin_tree(tmp_path) -> Path:
    """A minimal plugin: the installer under test, the command set and the templates."""
    root = tmp_path / "plugin"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(kit.__file__, root / "scripts")
    for source in [PLUGIN / COMMAND, *(PLUGIN / "scripts").glob("_diagram_*.py")]:
        shutil.copy(source, root / "scripts")
    shutil.copytree(PLUGIN / "claude" / "aac-templates", root / "claude" / "aac-templates")
    return root


def test_run_from_a_plugin_without_a_plugin_root_it_installs_from_that_plugin(project, plugin_tree):
    result = subprocess.run(
        [sys.executable, str(plugin_tree / "scripts" / "install_diagram_kit.py"),
         "--project-root", str(project)],
        capture_output=True,
        text=True,
    )  # fmt: skip

    assert result.returncode == 0, result.stderr
    assert (project / COMMAND).is_file()
    assert (project / WORKFLOW).is_file()


def test_without_a_plugin_root_the_installer_serves_from_the_plugin_it_was_shipped_in(
    project, monkeypatch
):
    assert kit._shipped_from() == Path(kit.__file__).resolve().parent.parent
    monkeypatch.setattr(kit, "_shipped_from", lambda: PLUGIN)

    assert kit.main(["--project-root", str(project)]) == 0

    assert (project / COMMAND).is_file()


def test_the_architecture_docs_marker_is_filled_with_the_design_and_architecture_paths(
    project, plugin_tree, capsys
):
    template = plugin_tree / "claude" / "aac-templates" / "architecture.yml.tmpl"
    template.write_text(
        template.read_text(encoding="utf-8") + "docs: {{PROJECT_PATHS_ARCHITECTURE_DOCS}}\n",
        encoding="utf-8",
    )

    assert _install(project, plugin=plugin_tree) == 0

    assert "docs: **/DESIGN.md + docs/architecture.md" in _workflow_lines(project)


def test_render_fills_markers_outside_comments_and_leaves_comment_lines_as_written():
    text = "  # {{PROJECT_A}} stays\n{{PROJECT_A}} and ${{ github.ref }}\n"

    assert (
        kit.render(text, {"PROJECT_A": "v"}) == "  # {{PROJECT_A}} stays\nv and ${{ github.ref }}\n"
    )


def test_render_refuses_a_marker_it_has_no_value_for():
    with pytest.raises(kit.PreconditionError, match=r"unknown marker \{\{PROJECT_NOPE\}\}"):
        kit.render("{{PROJECT_NOPE}}\n", {})


# --- preconditions --------------------------------------------------------------------------------


def test_a_directory_that_is_not_a_git_repository_is_refused(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    assert _install(plain) == 2

    assert "not a git repository" in capsys.readouterr().err
    assert _tree(plain) == {}


def test_a_missing_project_root_is_refused(tmp_path, capsys):
    assert _install(tmp_path / "absent") == 2

    assert "absent" in capsys.readouterr().err


def test_a_plugin_root_without_the_templates_is_refused_before_anything_is_written(
    project, tmp_path, capsys
):
    bare = tmp_path / "bare-plugin"
    bare.mkdir()

    assert _install(project, plugin=bare) == 2

    assert "likec4-style-kit.c4.tmpl" in capsys.readouterr().err
    assert _tree(project) == {}


@pytest.mark.parametrize("bad", ["/abs/diagrams", "../outside", "docs/../../outside", "", "."])
def test_a_diagrams_directory_outside_the_project_is_refused(project, capsys, bad):
    assert _install(project, "--diagrams-dir", bad) == 2

    assert "--diagrams-dir" in capsys.readouterr().err
    assert _tree(project) == {}


def test_a_project_root_argument_is_required():
    with pytest.raises(SystemExit) as raised:
        kit.main([])

    assert raised.value.code == 2
