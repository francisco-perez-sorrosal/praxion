"""The diagram regeneration command's edge: toolchain gate, failures, modes, discovery.

`main(argv, tool_path=...)` is driven in-process against stub `likec4` and `d2` programs on a
private PATH, so every run is offline and fast; one test runs the real pinned toolchain on
Praxion's own model twice, with a proxy pointing at a closed port, and compares the bytes.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _diagram_testkit import D2_PIN, FAILURE_MESSAGE, LIKEC4_PIN, Toolchain, reading

REPO = Path(__file__).resolve().parent.parent
PRAXION_MODEL = REPO / "docs" / "diagrams" / "architecture" / "src"

CLOSED_PORT_PROXY = "http://127.0.0.1:9"
OFF_PIN = "1.56.0"
FAIL = "[diagram-regen] FAIL "
CAUSE = "[diagram-regen]   cause: "
FIX = "[diagram-regen]   fix: "


@pytest.fixture
def rd():
    return importlib.import_module("regenerate_diagrams")


@pytest.fixture(autouse=True)
def no_review(rd, monkeypatch):
    """Keep the review checks out of these tests: the stub `d2` writes no real render, and the
    checks have their own tests (`test_regenerate_diagrams_checks.py`)."""
    monkeypatch.setattr(rd, "run_checks", lambda projection, built, root: projection.findings)


@pytest.fixture
def tools(tmp_path) -> Toolchain:
    return Toolchain(tmp_path / "bin")


ARCH = Path("docs/diagrams/architecture")
SECOND = Path("docs/diagrams/second")


def make_root(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "model.c4").write_text("model {}\n", encoding="utf-8")


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    """A project directory that is the working directory, with one diagram root."""
    root = tmp_path / "project"
    make_root(root / ARCH)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def go(rd, tools, capsys):
    """Run the command on the stub toolchain: (exit code, stdout, stderr)."""

    def invoke(*argv: str) -> tuple[int, str, str]:
        code = rd.main(list(argv), tool_path=str(tools.directory))
        out, err = capsys.readouterr()
        return code, out, err

    return invoke


def rendered(project: Path, root: Path = ARCH) -> dict[str, bytes]:
    folder = project / root / "rendered"
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())} if folder.is_dir() else {}


def tree(top: Path) -> dict[str, bytes]:
    return {str(p.relative_to(top)): p.read_bytes() for p in sorted(top.rglob("*")) if p.is_file()}


def failure(err: str) -> tuple[str, str, str]:
    """The failure's header, its cause (possibly several lines) and its fix line."""
    lines = err.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(FAIL))
    fix = next(i for i, line in enumerate(lines) if line.startswith(FIX))
    return lines[start], "\n".join(lines[start + 1 : fix]), lines[fix]


# --- the toolchain gate ------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [[], ["--check"]])
@pytest.mark.parametrize(
    ("setting", "found", "pin"),
    [
        ("likec4_version", OFF_PIN, LIKEC4_PIN),
        ("d2_version", "v0.6.0", D2_PIN),
        ("likec4_version", "nightly", LIKEC4_PIN),
    ],
)
def test_a_tool_off_its_pin_is_refused_naming_the_pin(
    go, tools, project, mode, setting, found, pin
):
    tools.set(**{setting: found})

    code, _, err = go(*mode)

    assert code == 3
    assert pin in err
    assert found.lstrip("v") in err
    assert tools.calls == ["likec4 --version", "d2 --version"]
    assert rendered(project) == {}


def test_a_tool_that_prints_no_version_is_off_its_pin(go, tools, project):
    tools.set(d2_version="")

    code, _, err = go()

    assert code == 3
    assert "d2 no version found but 0.7.1 is pinned" in err


@pytest.mark.parametrize("mode", [[], ["--check"]])
def test_a_tool_missing_from_path_exits_3_naming_what_to_install(go, tools, project, mode):
    (tools.directory / "d2").unlink()

    code, _, err = go(*mode)

    assert code == 3
    assert "d2 is not installed (not on PATH); 0.7.1 is required" in err
    assert f"--version v{D2_PIN}" in err
    assert "likec4" not in err


def test_every_missing_tool_is_reported(go, tools, project):
    (tools.directory / "likec4").unlink()
    (tools.directory / "d2").unlink()

    code, _, err = go()

    assert code == 3
    assert "likec4 is not installed" in err
    assert "d2 is not installed" in err


def test_tools_are_started_by_the_path_found_on_the_given_path_alone(go, tools, project):
    go()

    where = tools.directory
    assert tools.launches == {f"{where}/likec4 PATH={where}", f"{where}/d2 PATH={where}"}


def test_a_binary_that_fails_even_its_version_probe_is_a_toolchain_error(go, tools, project):
    tools.set(likec4_version_status=3)

    code, _, err = go()

    head, cause, _ = failure(err)
    assert code == 1
    assert head == f"{FAIL}toolchain-error likec4: likec4 exited with status 3"
    assert "likec4 --version" in cause


def test_a_program_that_cannot_be_started_is_a_toolchain_error(go, tools, project):
    (tools.directory / "likec4").write_text("#!/nonexistent/interpreter\n", encoding="utf-8")

    code, _, err = go()

    head, cause, _ = failure(err)
    assert code == 1
    assert head.startswith(f"{FAIL}toolchain-error likec4: likec4 could not be run")
    assert cause == f"{CAUSE}{tools.directory}/likec4 --version"


# --- regeneration failures ---------------------------------------------------------------------


def test_the_model_is_read_once_per_root_with_export_json_skip_layout(go, tools, project):
    go()

    (export,) = [call for call in tools.calls if "export" in call]
    words = export.split(" ")
    assert words[:4] == ["likec4", "export", "json", "--skip-layout"]
    assert words[4] == "-o"
    assert words[5].endswith("model.json")
    assert words[6:] == [f"{ARCH}/src"]


def test_a_failing_export_is_three_lines_with_the_command_and_its_stderr(go, tools, project):
    tools.set(export_status=3)

    code, _, err = go()

    head, cause, fix = failure(err)
    assert code == 1
    assert head == f"{FAIL}toolchain-error {ARCH}: likec4 exited with status 3"
    assert "export json --skip-layout" in cause.splitlines()[0]
    assert cause.splitlines()[1:] == [f"[diagram-regen]     {FAILURE_MESSAGE}"]
    assert fix.startswith(f"{FIX}run the command above by hand")


def test_a_failing_render_is_a_toolchain_error_naming_the_view(go, tools, project):
    tools.set(render_status=3)

    code, _, err = go()

    assert code == 1
    assert "FAIL toolchain-error index: d2 exited with status 3" in err
    assert FAILURE_MESSAGE in err
    assert rendered(project) == {}


def test_an_export_that_writes_no_model_is_a_toolchain_error(go, tools, project):
    tools.set(model_text="{not json")

    code, _, err = go()

    head, cause, _ = failure(err)
    assert code == 1
    assert head == f"{FAIL}toolchain-error {ARCH}: likec4 wrote no readable model"
    assert cause.startswith(f"{CAUSE}{tools.directory}/likec4 export json")
    assert "Expecting property name" in cause


@pytest.mark.parametrize("views", [{}, {"index": {"_type": "element", "nodes": []}}])
def test_a_model_with_no_view_showing_an_element_is_no_views(go, tools, project, views):
    tools.use_model({**tools.model, "views": views})

    code, _, err = go()

    head, cause, fix = failure(err)
    assert code == 1
    assert head == f"{FAIL}no-views {ARCH}: the model source yields no view that shows an element"
    assert cause == f"{CAUSE}the toolchain read {len(views)} view(s) and none includes an element"
    assert (
        fix == f"{FIX}declare a view that includes elements, such as `view index {{ include * }}`"
    )
    assert tools.renders_drawn == []


def test_a_declared_view_with_no_element_is_view_without_render_naming_it(go, tools, project):
    empty = {"_type": "element", "title": "Empty", "nodes": []}
    tools.use_model({**tools.model, "views": {**tools.model["views"], "probe_empty_view": empty}})

    code, _, err = go()

    head, cause, fix = failure(err)
    assert code == 1
    assert head.endswith(
        "view-without-render probe_empty_view: view 'probe_empty_view' includes no element"
    )
    assert cause == f"{CAUSE}its include predicates match nothing, so there is nothing to draw"
    assert fix.endswith(
        "add `include *` or an element to view 'probe_empty_view', or delete the view"
    )
    assert rendered(project) == {}


def test_a_d2_that_exits_zero_and_writes_nothing_is_view_without_render(go, tools, project):
    tools.set(output="none")

    code, _, err = go()

    head, cause, fix = failure(err)
    assert code == 1
    assert head == f"{FAIL}view-without-render index: d2 wrote no render for view 'index'"
    assert cause.endswith("exited 0 and left no index.svg")
    assert fix == f"{FIX}run the same command by hand with the pinned d2"


def test_a_render_that_spells_no_element_name_is_render_without_names(go, tools, project):
    tools.set(output="blank")

    code, _, err = go()

    head, cause, fix = failure(err)
    assert code == 1
    assert (
        head
        == f"{FAIL}render-without-names index: the render of view 'index' shows no element's name"
    )
    assert cause == f"{CAUSE}none of its 3 element names appears in index.svg"
    assert fix == f"{FIX}give the view's elements titles in the model, or report the renderer fault"
    assert rendered(project) == {}


def _drawn(key: str, text: str) -> str:
    """A d2 object's group: its class is the base64 of its key path, as d2 writes it."""
    path = base64.b64encode(key.encode("utf-8")).decode("ascii")
    return f'<g class="{path}"><g class="shape"/><text>{text}</text></g>'


def draw(tools: Toolchain, *objects: str) -> None:
    """Make the stub `d2` write an SVG of the given drawn objects."""
    body = "".join(objects).replace("'", "'\\''")
    script = (
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "v{D2_PIN}"; exit 0; fi\n'
        f'printf \'<svg data-d2-version="v0.7.1">{body}</svg>\' > "$2"\n'
    )
    stub = tools.directory / "d2"
    stub.write_text(script, encoding="utf-8")
    stub.chmod(0o755)


def test_names_only_in_the_title_block_and_the_legend_do_not_count_as_shown(go, tools, project):
    draw(
        tools,
        _drawn("Title", "Developer — system context diagram"),
        _drawn("Legend", "Legend"),
        _drawn("Legend.category_person", "Praxion"),
        _drawn("Legend.line_acts_on_sample.tail", "Claude Code"),
    )

    code, _, err = go()

    head, _, _ = failure(err)
    assert code == 1
    assert head.startswith(f"{FAIL}render-without-names index:")
    assert rendered(project) == {}


def test_a_name_drawn_as_an_element_counts_beside_a_title_that_spells_other_names(
    go, tools, project
):
    draw(
        tools,
        _drawn("Title", "Praxion — system context diagram"),
        _drawn('"developer"', "Developer"),
    )

    code, _, _ = go()

    assert code == 0
    assert "index.svg" in rendered(project)


def test_a_render_that_is_not_svg_is_render_without_names(go, tools, project):
    draw(tools, "<g>")

    code, _, err = go()

    head, cause, _ = failure(err)
    assert code == 1
    assert (
        head == f"{FAIL}render-without-names index: the render of view 'index' is not readable SVG"
    )
    assert "index.svg does not parse" in cause


def test_a_wrapped_and_escaped_element_name_still_counts_as_shown(go, tools, project):
    tools.use_model(reading("wrapped"))

    code, _, _ = go()

    assert code == 0
    assert b"Research &amp; Development" in rendered(project)["wrapped.svg"]


@pytest.mark.parametrize("mode", [[], ["--check"]])
def test_a_failed_run_leaves_the_committed_renders_untouched(go, tools, project, mode):
    folder = project / ARCH / "rendered"
    folder.mkdir()
    (folder / "old.svg").write_text("kept", encoding="utf-8")
    (folder / "README.md").write_text("kept", encoding="utf-8")
    tools.set(output="blank")

    assert go(*mode)[0] == 1
    assert rendered(project) == {"old.svg": b"kept", "README.md": b"kept"}


# --- default mode: render in place -------------------------------------------------------------


def test_every_view_is_written_as_a_d2_and_an_svg_in_rendered(go, tools, project):
    code, out, err = go()

    assert code == 0
    assert out == ""
    assert f"[diagram-regen] {ARCH}: 2 renders written" in err
    assert sorted(rendered(project)) == ["index.d2", "index.svg", "structure.d2", "structure.svg"]
    assert b"Developer" in rendered(project)["index.svg"]


def test_the_d2_text_is_the_core_emission_for_the_view(rd, go, tools, project):
    go()

    view = next(v for v in rd.project(tools.model).views if v.id == "index")
    assert rendered(project)["index.d2"].decode("utf-8") == rd.emit_d2(view)


def test_the_d2_version_stamp_is_scrubbed_to_a_constant(go, tools, project):
    go()

    svg = rendered(project)["index.svg"]
    assert b'data-d2-version="pinned"' in svg
    assert b"v0.7.1" not in svg


def test_stale_renders_are_pruned_and_nothing_else_is_touched(go, tools, project):
    folder = project / ARCH / "rendered"
    (folder / "sub").mkdir(parents=True)
    for name in ("gone.svg", "gone.d2", "README.md", "sub/keep.svg"):
        (folder / name).write_text("old", encoding="utf-8")

    go()

    names = set(tree(folder))
    assert {"gone.svg", "gone.d2"}.isdisjoint(names)
    assert {"README.md", "sub/keep.svg"} <= names


def test_two_runs_write_identical_bytes(go, tools, project):
    go()
    first = rendered(project)

    go()

    assert rendered(project) == first


def test_default_mode_prints_failed_findings_but_still_renders_and_exits_0(go, tools, project):
    tools.use_model(reading("unresolved"))

    code, out, _ = go()

    assert code == 0
    assert out.startswith("DRC-05 unresolved FAIL ")
    assert (project / ARCH / "rendered" / "unresolved.svg").is_file()


# --- discovery ---------------------------------------------------------------------------------


def test_every_diagram_root_with_a_model_is_regenerated_by_default(go, tools, project):
    make_root(project / SECOND)
    (project / "docs/diagrams/mermaid-only/src").mkdir(parents=True)
    (project / "docs/diagrams/mermaid-only/src/flow.mmd").write_text("graph TD\n")

    go()

    assert rendered(project, SECOND)
    assert rendered(project)
    assert not (project / "docs/diagrams/mermaid-only/rendered").exists()


@pytest.mark.parametrize(
    ("argv", "root"),
    [
        (["--diagrams-dir", "design/diagrams"], Path("design/diagrams/overview")),
        ([str(SECOND)], SECOND),
    ],
)
def test_a_diagrams_dir_or_explicit_roots_replace_the_default_discovery(
    go, tools, project, argv, root
):
    make_root(project / root)

    go(*argv)

    assert rendered(project, root)
    assert rendered(project) == {}


def test_with_no_root_to_regenerate_the_run_is_a_quiet_success(go, tools, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    code, _, err = go()

    assert code == 0
    assert "no diagram root" in err
    assert tools.calls == []


# --- --check -----------------------------------------------------------------------------------


def test_check_writes_nothing_in_the_checkout_and_exits_0_without_a_failed_finding(
    go, tools, project
):
    before = tree(project)

    code, out, err = go("--check")

    assert code == 0
    assert out == ""
    assert f"{ARCH}: 2 renders checked" in err
    assert tree(project) == before


def test_check_prints_each_finding_on_stdout_and_exits_1_when_one_failed(go, tools, project):
    tools.use_model(reading("unresolved"))

    code, out, _ = go("--check")

    assert code == 1
    assert [line.split(" ")[:3] for line in out.splitlines()] == [["DRC-05", "unresolved", "FAIL"]]


def test_json_prints_one_object_per_finding_with_all_six_keys(go, tools, project):
    tools.use_model(reading("unresolved"))

    _, out, _ = go("--check", "--json")

    (found,) = (json.loads(line) for line in out.splitlines())
    assert set(found) == {"check", "view", "status", "evidence", "measured", "threshold"}
    assert (found["check"], found["view"], found["status"]) == ("DRC-05", "unresolved", "FAIL")


def test_a_style_file_makes_its_category_known(go, tools, project):
    tools.model["elements"]["praxion"]["metadata"] = {"category": "Queue"}
    tools.write()
    assert "Queue" in go("--check")[1]

    queue = {"shape": "queue", "fill": "#FFF4D6", "stroke": "#8A5A00", "text_colour": "#0F172A"}
    style = {"schema": 1, "categories": {"Queue": {"box": queue}}}
    (project / ARCH / "style.json").write_text(json.dumps(style), encoding="utf-8")

    assert go("--check")[:2] == (0, "")


# --- usage errors ------------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [["--nope"], ["--staged", "--check"]])
def test_an_unknown_flag_or_staged_with_check_is_a_usage_error(go, tools, project, argv):
    with pytest.raises(SystemExit) as stop:
        go(*argv)

    assert stop.value.code == 2
    assert tools.calls == []


def test_a_root_without_a_model_source_is_a_usage_error_naming_it(go, tools, project):
    (project / "bare").mkdir()

    code, _, err = go("bare")

    assert code == 2
    assert "bare has no src/*.c4" in err
    assert tools.calls == []


def test_a_refused_style_file_is_a_usage_error_naming_the_file(go, tools, project):
    (project / ARCH / "style.json").write_text(json.dumps({"schema": 9}), encoding="utf-8")

    code, _, err = go()

    assert code == 2
    assert f"{ARCH / 'style.json'}: style.json: schema must be 1" in err
    assert rendered(project) == {}


# --- --staged ----------------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    who = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
    done = subprocess.run(["git", *who, *args], cwd=repo, env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def repo(project) -> Path:
    """The project as a git repository with one commit holding both diagram roots."""
    make_root(project / SECOND)
    (project / ARCH / "rendered").mkdir()
    (project / ARCH / "rendered" / "old.svg").write_text("old", encoding="utf-8")
    git(project, "init", "-q", "-b", "main")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "base")
    return project


def stage_model_change(repo: Path, root: Path = ARCH) -> None:
    source = repo / root / "src" / "model.c4"
    source.write_text(source.read_text(encoding="utf-8") + "// changed\n", encoding="utf-8")
    git(repo, "add", str(source))


def staged(repo: Path, *flags: str) -> list[str]:
    return git(repo, "diff", "--cached", "--name-only", *flags).split()


def test_staged_regenerates_only_the_roots_with_a_staged_source_and_stages_them(go, tools, repo):
    stage_model_change(repo)

    code, _, _ = go("--staged")

    assert code == 0
    assert set(staged(repo, "--diff-filter=A")) == {
        f"{ARCH}/rendered/{name}"
        for name in ("index.d2", "index.svg", "structure.d2", "structure.svg")
    }
    assert staged(repo, "--diff-filter=D") == [f"{ARCH}/rendered/old.svg"]
    assert not (repo / SECOND / "rendered").exists()


def test_staged_inside_a_git_hook_environment_stages_paths_from_the_work_tree_top(
    go, tools, repo, monkeypatch
):
    """Git exports GIT_DIR to hooks; a git call from a subdirectory would then treat it as the tree."""
    stage_model_change(repo)
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)

    code, _, _ = go("--staged")

    assert code == 0
    added = set(staged(repo, "--diff-filter=A"))
    assert added == {
        f"{ARCH}/rendered/{name}"
        for name in ("index.d2", "index.svg", "structure.d2", "structure.svg")
    }
    assert not any(name.startswith("rendered/") for name in added)


def test_staged_with_nothing_staged_runs_no_tool(go, tools, repo):
    assert go("--staged")[0] == 0
    assert tools.calls == []


def test_a_staged_path_that_is_not_a_model_source_triggers_nothing(go, tools, repo):
    notes, elsewhere = repo / ARCH / "src" / "notes.md", repo / "docs" / "model.c4"
    notes.write_text("notes", encoding="utf-8")
    elsewhere.write_text("model {}\n", encoding="utf-8")
    git(repo, "add", str(notes), str(elsewhere))

    assert go("--staged")[0] == 0
    assert tools.calls == []


def test_a_staged_deletion_of_a_source_triggers_regeneration(go, tools, repo):
    (repo / ARCH / "src" / "extra.c4").write_text("model {}\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "extra source")
    git(repo, "rm", "-q", str(repo / ARCH / "src" / "extra.c4"))

    go("--staged")

    assert len(tools.renders_drawn) == 2


def test_staged_with_explicit_roots_still_skips_unstaged_ones(go, tools, repo):
    stage_model_change(repo, SECOND)

    go("--staged", str(ARCH), str(SECOND))

    assert rendered(repo, SECOND)
    assert rendered(repo) == {"old.svg": b"old"}


def test_staged_skips_with_a_warning_when_a_tool_is_missing(go, tools, repo):
    stage_model_change(repo)
    (tools.directory / "d2").unlink()

    code, _, err = go("--staged")

    assert code == 0
    assert "WARN d2 is not installed (not on PATH); skipping diagram regeneration" in err
    assert rendered(repo) == {"old.svg": b"old"}


def test_staged_skips_with_a_warning_naming_the_pins_when_a_tool_is_off_its_pin(go, tools, repo):
    stage_model_change(repo)
    tools.set(likec4_version=OFF_PIN)

    code, _, err = go("--staged")

    assert code == 0
    assert f"WARN likec4 {OFF_PIN} found but {LIKEC4_PIN} is pinned; skipping" in err
    assert f"pinned likec4 {LIKEC4_PIN} and d2 {D2_PIN}" in err
    assert f"found likec4 {OFF_PIN} and d2 {D2_PIN}" in err
    assert rendered(repo) == {"old.svg": b"old"}
    assert staged(repo) == [f"{ARCH.as_posix()}/src/model.c4"]


def test_staged_aborts_on_a_regeneration_failure_with_the_message(go, tools, repo):
    stage_model_change(repo)
    tools.set(render_status=3)

    code, _, err = go("--staged")

    assert code == 1
    assert "FAIL toolchain-error" in err
    assert FAILURE_MESSAGE in err


def test_staged_prints_failed_findings_as_non_blocking_warnings_on_stderr(go, tools, repo):
    tools.use_model(reading("unresolved"))
    stage_model_change(repo)

    code, out, err = go("--staged")

    assert code == 0
    assert out == ""
    assert "[diagram-regen] WARN DRC-05 unresolved " in err


def test_staged_outside_a_git_repository_is_a_usage_error(go, tools, project):
    code, _, err = go("--staged")

    assert code == 2
    assert "usage error: git rev-parse --show-toplevel failed in " in err


def test_a_failed_git_add_is_a_toolchain_error(go, tools, repo):
    stage_model_change(repo)
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")

    code, _, err = go("--staged")

    head, cause, _ = failure(err)
    assert code == 1
    assert head == f"{FAIL}toolchain-error {ARCH}/rendered: git failed"
    assert cause.splitlines()[0] == f"{CAUSE}git add {ARCH}/rendered"
    assert "index.lock" in cause


# --- the real toolchain ------------------------------------------------------------------------


def _pinned_toolchain_is_on_path(rd) -> bool:
    for tool, pin in (("likec4", rd.LIKEC4_VERSION), ("d2", rd.D2_VERSION)):
        path = shutil.which(tool)
        if path is None:
            return False
        said = subprocess.run([path, "--version"], capture_output=True, text=True)
        if said.stdout.strip().lstrip("v") != pin:
            return False
    return True


def test_the_pinned_toolchain_regenerates_praxions_model_identically_offline(
    rd, tmp_path, monkeypatch
):
    if not PRAXION_MODEL.is_dir() or not _pinned_toolchain_is_on_path(rd):
        pytest.skip("Praxion's model or the pinned likec4 and d2 are not available")
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(variable, CLOSED_PORT_PROXY)
    shutil.copytree(PRAXION_MODEL, tmp_path / ARCH / "src")
    monkeypatch.chdir(tmp_path)

    assert rd.main([]) == 0
    first = rendered(tmp_path)
    assert rd.main([]) == 0

    assert rendered(tmp_path) == first
    assert {"index.svg", "index.d2", "components.svg"} <= set(first)
    assert all(b'data-d2-version="pinned"' in svg for n, svg in first.items() if n.endswith(".svg"))
