"""The Codex exporter embeds each role's kernel and writes the plugin location out."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORTER_PATH = REPO_ROOT / "codex" / "config" / "export-codex-agents.py"
MAX_KERNEL_STRING_CHARS = 10_000


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_codex_agents_embed", EXPORTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def exporter():
    return load_exporter()


def write_index(root: Path, roles: dict[str, list[str]]) -> None:
    index = root / "claude" / "kernels" / "index.json"
    index.parent.mkdir(parents=True)
    body = {
        role: {"status": None, "modules": [], "strings": strings} for role, strings in roles.items()
    }
    index.write_text(json.dumps({"schema": 1, "roles": body}), encoding="utf-8")


def test_the_plugin_variable_is_replaced_by_the_checkout_location(exporter, tmp_path: Path):
    write_index(tmp_path, {"scribe": ["read `${CLAUDE_PLUGIN_ROOT}/claude/kernels/x.md`"]})

    kernels = exporter.load_role_kernels(tmp_path)

    assert kernels["scribe"] == [f"read `{tmp_path.resolve().as_posix()}/claude/kernels/x.md`"]


def test_a_missing_kernel_index_is_refused_naming_its_path(exporter, tmp_path: Path):
    with pytest.raises(exporter.AgentParseError, match="Kernel index not found"):
        exporter.load_role_kernels(tmp_path)


def test_the_kernel_strings_land_in_the_instructions_before_the_capsule(exporter):
    text = exporter.render_developer_instructions(
        "scribe", Path("/x/scribe.md"), ["name: scribe"], ["KERNEL ONE", "KERNEL TWO"]
    )

    assert text.index("KERNEL ONE") < text.index("KERNEL TWO") < text.index("```yaml")


def test_the_contract_is_not_written_a_second_time_beside_the_kernel(exporter):
    text = exporter.render_developer_instructions(
        "scribe", Path("/x/scribe.md"), ["name: scribe"], ["KERNEL"]
    )

    assert "Also apply the Praxion behavioral contract" not in text


def test_the_capsule_drops_omit_claude_md_and_keeps_other_keys(exporter):
    capsule = exporter.render_frontmatter_capsule(
        ["name: scribe", "omitClaudeMd: true", "tools: Read"]
    )

    assert "omitClaudeMd" not in capsule
    assert "name: scribe\ntools: Read" in capsule


def test_an_agent_without_a_kernel_in_the_index_is_refused(exporter, monkeypatch, tmp_path: Path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "scribe.md").write_text(
        "---\nname: scribe\ndescription: writes\n---\nbody\n", encoding="utf-8"
    )
    write_index(tmp_path, {"other": ["K"]})
    monkeypatch.setattr(exporter, "load_model_routes", lambda _root: {"scribe": {}})

    with pytest.raises(exporter.AgentParseError, match="missing kernel"):
        exporter.export_agents(tmp_path, tmp_path / "out")


def test_every_committed_kernel_string_fits_the_size_bound(exporter):
    strings = [s for role in exporter.load_role_kernels(REPO_ROOT).values() for s in role]

    assert strings
    assert max(len(s) for s in strings) <= MAX_KERNEL_STRING_CHARS
