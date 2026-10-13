"""A pilot role switched on its full record, end to end.

The journey crosses three boundaries: the adoption ledger and agent definition a
maintainer edits, the commit gate that accepts the flip, and the spawn hook that
delivers the kernel and the project's own instruction file to the switched role in
a managed project elsewhere on disk, leaving one kernel row at that project's root.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers import kernel_adoption, kernel_sandbox, kernel_spawn
from tests.acceptance.drivers.kernel_sandbox import (
    PLUGIN_ROOT_VARIABLE,
    module_text,
    normalize_plugin_location,
    paragraphs,
)

PROJECT_RULE = "Project convention: every fixture lives under data/fixtures/.\n"


def test_a_switched_researcher_receives_its_kernel_and_the_project_file_and_is_recorded(
    tmp_path: Path,
) -> None:
    plugin = kernel_sandbox.new_sandbox(
        kernel_sandbox.build_template(tmp_path / "template"), tmp_path / "plugin"
    )
    kernel_adoption.record(plugin.root, kernel_adoption.full_switch_record("researcher"))
    kernel_sandbox.set_frontmatter_key(plugin, "researcher", "omitClaudeMd: true")
    kernel_sandbox.regenerate(plugin.root)
    verdict = kernel_sandbox.commit_gate(plugin.root)
    project = kernel_spawn.project_checkout(tmp_path / "managed", instructions=PROJECT_RULE)
    inner = project / "src"
    inner.mkdir()

    injection = kernel_spawn.spawn(plugin.root, project, "praxion:researcher", process_cwd=inner)
    received = normalize_plugin_location(injection.joined, plugin.root)
    definition = normalize_plugin_location(plugin.read("agents/researcher.md"), plugin.root)
    core = normalize_plugin_location(module_text(plugin.root, "core"), plugin.root)

    assert not verdict.refused, verdict.output
    assert [p for p in paragraphs(core) if p not in received and p not in definition] == []
    assert PROJECT_RULE.strip() in injection.joined
    assert PLUGIN_ROOT_VARIABLE not in injection.joined
    assert len(kernel_spawn.kernel_rows(project)) == 1
