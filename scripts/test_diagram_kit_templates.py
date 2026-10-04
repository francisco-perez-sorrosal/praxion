"""The onboarding templates for architecture diagrams: style kit, example model and CI job.

The kit and the example are checked as a unit: their LikeC4-native colours equal the renderer's
token table, and a scratch project holding them (suffix removed) regenerates with the pinned
toolchain and passes every per-render review check. The CI template is parsed with its
placeholders at their documented defaults and compared with the renderer's pins.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "claude" / "aac-templates"
KIT = TEMPLATES / "likec4-style-kit.c4.tmpl"
EXAMPLE = TEMPLATES / "likec4-example-model.c4.tmpl"
WORKFLOW = TEMPLATES / "architecture.yml.tmpl"

DIAGRAM_ROOT = Path("docs/diagrams/architecture")
VIEW_TAGS = (
    "c4_system_context",
    "c4_system_landscape",
    "c4_container",
    "c4_component",
    "c4_deployment",
)
PER_RENDER_CHECKS = tuple(f"DRC-{n:02d}" for n in range(1, 11))
PLACEHOLDER_DEFAULTS = {
    "PROJECT_PATHS_DIAGRAMS": "docs/diagrams",
    "PROJECT_PYTHON_VERSION": "3.13",
    "PROJECT_PLUGIN_DIR": ".",
}
DRIFT_JOB = "regenerate-and-diff"


@pytest.fixture
def rd():
    return importlib.import_module("regenerate_diagrams")


# --- the style kit ----------------------------------------------------------------------------


def _kit_kinds(text: str) -> dict[str, str | None]:
    """Each element kind's notation and its native colour (`#RRGGBB`), as the kit declares them."""
    colours = dict(re.findall(r"^\s*color\s+(\S+)\s+(#[0-9A-Fa-f]{6})\s*$", text, re.MULTILINE))
    kinds = {}
    for body in re.findall(r"^  element\s+\w+\s*\{(.*?)^  \}", text, re.MULTILINE | re.DOTALL):
        notation = re.search(r"notation\s+'([^']+)'", body)
        colour = re.search(r"\bcolor\s+(\S+)", body)
        kinds[notation.group(1)] = colours[colour.group(1)].upper() if colour else None
    return kinds


def _category_hue(rd, category: str) -> str:
    """The category's outline colour: its frame drawing's stroke when it has one, else its box's."""
    drawings = sorted(
        (t for t in rd.DEFAULT_TOKENS if t.category == category), key=lambda t: not t.frame
    )
    return drawings[0].stroke.upper()


def test_the_kit_declares_exactly_the_floor_vocabulary(rd):
    kinds = _kit_kinds(KIT.read_text(encoding="utf-8"))

    assert tuple(kinds) == rd.VOCABULARIES["kit"]


def test_the_kits_native_colours_equal_the_token_table(rd):
    kinds = _kit_kinds(KIT.read_text(encoding="utf-8"))

    assert {name: _category_hue(rd, name) for name in kinds} == kinds


def test_the_kit_declares_the_reads_kind_and_every_view_tag():
    text = KIT.read_text(encoding="utf-8")

    assert re.search(r"relationship\s+reads\s*\{", text)
    assert all(re.search(rf"^\s*tag\s+{tag}\s*$", text, re.MULTILINE) for tag in VIEW_TAGS)


def test_the_kit_keeps_the_component_kind_the_req_id_fragment_composes_with():
    fragment = (TEMPLATES / "likec4-req-ids.c4.frag").read_text(encoding="utf-8")

    assert re.search(r"=\s*component\s", fragment)
    assert re.search(r"^  element\s+component\s*\{", KIT.read_text(encoding="utf-8"), re.MULTILINE)


def test_the_templates_keep_their_suffix_and_hold_no_placeholder():
    assert [p.name for p in TEMPLATES.glob("*.c4")] == []
    assert all("{{" not in p.read_text(encoding="utf-8") for p in (KIT, EXAMPLE))


# --- a scratch project holding the kit and the example ---------------------------------------


def _pinned_toolchain_is_on_path(rd) -> bool:
    for tool, pin in (("likec4", rd.LIKEC4_VERSION), ("d2", rd.D2_VERSION)):
        path = shutil.which(tool)
        if path is None:
            return False
        said = subprocess.run([path, "--version"], capture_output=True, text=True)
        if said.stdout.strip().lstrip("v") != pin:
            return False
    return True


@pytest.fixture
def scratch_project(rd, tmp_path, monkeypatch) -> Path:
    if not _pinned_toolchain_is_on_path(rd):
        pytest.skip("the pinned likec4 and d2 are not on PATH")
    source = tmp_path / DIAGRAM_ROOT / "src"
    source.mkdir(parents=True)
    shutil.copy(KIT, source / "_spec.c4")
    shutil.copy(EXAMPLE, source / "architecture.c4")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_example_regenerates_and_passes_every_per_render_check(rd, scratch_project, capsys):
    assert rd.main([]) == 0
    capsys.readouterr()

    code = rd.main(["--check", "--json"])
    findings = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    failed = [
        f"{f['check']} {f['view']}: {f['evidence']}" for f in findings if f["status"] == "FAIL"
    ]
    assert failed == []
    assert code == 0
    assert {(f["check"], f["view"]) for f in findings} >= {
        (check, view) for check in PER_RENDER_CHECKS for view in ("index", "containers")
    }


def test_the_example_draws_a_view_of_each_declared_type_and_all_its_elements(rd, scratch_project):
    assert rd.main([]) == 0

    renders = sorted(p.name for p in (scratch_project / DIAGRAM_ROOT / "rendered").glob("*.svg"))
    text = (scratch_project / DIAGRAM_ROOT / "rendered" / "containers.svg").read_text(
        encoding="utf-8"
    )

    assert renders == ["containers.svg", "index.svg"]
    assert all(
        name in text for name in ("Storefront", "Order service", "Order database", "Mail provider")
    )


# --- the CI template --------------------------------------------------------------------------


def _template(substitute) -> dict:
    text = re.sub(
        r"\{\{(PROJECT_[A-Z_]+)\}\}",
        lambda m: substitute(m.group(1)),
        WORKFLOW.read_text(encoding="utf-8"),
    )
    return yaml.safe_load(text)


def _runs() -> list[str]:
    """The drift job's shell steps, in order, with the placeholders at their documented defaults."""
    data = _template(lambda name: PLACEHOLDER_DEFAULTS.get(name, name))
    return [step["run"] for step in data["jobs"][DRIFT_JOB]["steps"] if "run" in step]


def test_the_ci_template_installs_the_pins_the_renderer_asserts(rd):
    likec4, d2 = _runs()[:2]

    assert likec4 == f"npm install -g likec4@{rd.LIKEC4_VERSION}"
    assert f"--version v{rd.D2_VERSION} --method standalone" in d2


def test_the_ci_template_job_is_installs_then_regenerate_then_status_gate_then_diff():
    regenerate, gate, show = _runs()[2:]

    assert regenerate == "python3 scripts/regenerate_diagrams.py --diagrams-dir docs/diagrams"
    assert "git status --porcelain -- docs/diagrams/" in gate
    assert "exit 1" in gate
    assert show.startswith("git diff")


def test_the_ci_template_runs_neither_the_native_projection_nor_a_normalizer():
    assert not any(re.search(r"normalize|@likec4/cli|gen d2", run) for run in _runs())
    assert len(_runs()) == 5


def test_the_ci_template_regenerates_when_the_command_changes():
    triggers = _template(lambda name: "x")[True]

    for event in ("pull_request", "push"):
        assert {"scripts/regenerate_diagrams.py", "scripts/_diagram_*.py"} <= set(
            triggers[event]["paths"]
        )
