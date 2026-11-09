"""The budget counts what a session in the measured directory loads.

A directory outside any managed project is not served the `project_scope:
managed` rows, so the always-loaded reading of it leaves them out; a managed
directory (Praxion's own checkout is one) counts every row, as it always did.
The decision is the hooks' own predicate, held to it here on every layout the
hooks' unit tests specify.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import measure_token_budget as mtb
import pytest
from _budget_scope import loaded_rows

SCRIPTS = Path(__file__).resolve().parent
# The hooks' own modules, which this file holds the budget to, sit beside scripts/.
sys.path.insert(0, str(SCRIPTS.parent / "hooks"))
from _project_scope import Managed, scope_of  # noqa: E402 (after sys.path injection)
from _rule_delivery import AgentKind, Event, plan_delivery  # noqa: E402
from test_project_scope import _LAYOUTS, _project  # noqa: E402

MANIFEST = """\
version: 1
rules:
- id: swe/everywhere
  path: rules/swe/everywhere.md
  load: always_on
  install: hook-deliver
  chars: 10
- id: swe/procedure
  path: rules/swe/procedure.md
  load: always_on
  install: hook-deliver
  chars: 20
  project_scope: managed
- id: swe/scoped
  path: rules/swe/scoped.md
  load: path_scoped
  install: symlink
  chars: 30
  paths:
  - .ai-state/decisions/**
"""


def _ids(rows: list[dict[str, str]]) -> list[str]:
    return [row["id"] for row in rows]


@pytest.fixture
def rows() -> list[dict[str, str]]:
    return mtb._manifest_rows(MANIFEST)


# -- the manifest scan learns the key ---------------------------------------------


def test_the_scan_reads_each_row_with_its_scope(rows: list[dict[str, str]]) -> None:
    assert _ids(rows) == ["swe/everywhere", "swe/procedure", "swe/scoped"]
    assert [row.get("project_scope") for row in rows] == [None, "managed", None]
    assert rows[1]["path"] == "rules/swe/procedure.md"
    assert rows[1]["install"] == "hook-deliver"


def test_the_scan_keeps_the_path_globs_out_of_the_rows(rows: list[dict[str, str]]) -> None:
    assert "paths" not in rows[2]
    assert ".ai-state/decisions/**" not in rows[2].values()


def test_the_scan_ignores_the_header_before_the_first_row() -> None:
    assert mtb._manifest_rows("version: 1\ngenerated_at: '2026-01-01T00:00:00Z'\n") == []


# -- which rows a directory loads -------------------------------------------------


def test_an_unmanaged_directory_loads_no_managed_row(
    tmp_path: Path, rows: list[dict[str, str]]
) -> None:
    assert _ids(loaded_rows(tmp_path, rows)) == ["swe/everywhere", "swe/scoped"]


def test_a_managed_directory_loads_every_row(tmp_path: Path, rows: list[dict[str, str]]) -> None:
    project = _project(tmp_path / "project")

    assert loaded_rows(project, rows) == rows


def test_a_subdirectory_of_a_managed_project_loads_every_row(
    tmp_path: Path, rows: list[dict[str, str]]
) -> None:
    below = _project(tmp_path / "project") / "src"
    below.mkdir()

    assert loaded_rows(below, rows) == rows


def test_a_relative_root_is_read_from_where_the_process_stands(
    tmp_path: Path, rows: list[dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_project(tmp_path / "project"))

    assert loaded_rows(Path("."), rows) == rows


def test_a_scope_value_other_than_managed_leaves_the_row_loaded(tmp_path: Path) -> None:
    damaged = [{"id": "swe/odd", "path": "rules/swe/odd.md", "project_scope": "Managed "}]

    assert loaded_rows(tmp_path, damaged) == damaged


def test_the_rows_given_are_not_changed(tmp_path: Path, rows: list[dict[str, str]]) -> None:
    before = [dict(row) for row in rows]

    loaded_rows(tmp_path, rows)

    assert rows == before


# -- the budget and the hooks give one answer on every layout ----------------------


@pytest.fixture(params=sorted(_LAYOUTS))
def start(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    return str(_LAYOUTS[request.param](tmp_path))


def test_the_budget_counts_what_the_hooks_deliver_on_every_layout(
    start: str, rows: list[dict[str, str]]
) -> None:
    hook_rows = [row for row in rows if row["install"] == "hook-deliver"]
    managed_only = {row["id"] for row in hook_rows if row.get("project_scope") == "managed"}
    delivered = plan_delivery(
        {row["id"]: "body" for row in hook_rows},
        managed_only,
        scope_of(start),
        Event.SESSION,
        AgentKind.WHOLE_RECIPIENT,
        (),
        (),
    )

    counted = [row["id"] for row in loaded_rows(Path(start), hook_rows)]

    assert counted == [part.unit_id for part in delivered]


def test_the_layouts_cover_both_answers(tmp_path: Path) -> None:
    # Guards the parity test above against passing on one answer only.
    answers = set()
    for name, build in _LAYOUTS.items():
        base = tmp_path / name
        base.mkdir()
        answers.add(isinstance(scope_of(str(build(base))), Managed))

    assert answers == {True, False}


# -- the file set ------------------------------------------------------------------


def _checkout_with_manifest(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory whose rules tree carries MANIFEST and both hook-delivered files."""
    home = root / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    project = root / "project"
    (project / "rules" / "swe").mkdir(parents=True)
    (project / "rules" / "_manifest.yaml").write_text(MANIFEST, encoding="utf-8")
    for name in ("everywhere", "procedure"):
        (project / "rules" / "swe" / f"{name}.md").write_text(f"{name}\n", encoding="utf-8")
    return project


def _hook_delivered_names(project: Path) -> list[str]:
    return [name for _, name in mtb._hook_delivered_files(project)]


def test_an_unmanaged_directory_counts_no_managed_only_hook_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _checkout_with_manifest(tmp_path, monkeypatch)

    assert _hook_delivered_names(project) == ["swe/everywhere.md"]


def test_a_managed_directory_counts_every_hook_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _checkout_with_manifest(tmp_path, monkeypatch)
    (project / ".ai-state").mkdir()

    assert _hook_delivered_names(project) == ["swe/everywhere.md", "swe/procedure.md"]


def _import_in_a_fresh_interpreter(scripts: Path, probe: str) -> subprocess.CompletedProcess[str]:
    code = f"import sys; sys.path.insert(0, {str(scripts)!r}); {probe}"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)


def test_importing_the_scope_reader_leaves_the_import_path_as_it_was() -> None:
    probe = (
        "before = list(sys.path); import _budget_scope; "
        "print(sys.path == before, '_project_scope' in sys.modules)"
    )

    result = _import_in_a_fresh_interpreter(SCRIPTS, probe)

    assert result.stdout.split() == ["True", "False"], result.stderr


def test_a_copy_with_no_hooks_above_it_fails_naming_the_module_it_needs(tmp_path: Path) -> None:
    copy = tmp_path / "scripts"
    copy.mkdir()
    shutil.copy2(SCRIPTS / "_budget_scope.py", copy / "_budget_scope.py")

    result = _import_in_a_fresh_interpreter(copy, "import _budget_scope")

    assert "ImportError" in result.stderr
    assert "hooks/_project_scope.py" in result.stderr
