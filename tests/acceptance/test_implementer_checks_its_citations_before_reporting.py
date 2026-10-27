"""Every form the implementer is spawned in tells it to run the commit's citation check first.

Before reporting a step done, the implementer runs `check_id_citation_discipline.py` over
the files it changed in that step, the same check the step's commit runs, and removes what
it refuses; where the check cannot run, it reports the check as not run. The instruction
reaches the implementer from its plugin definition, as a kernel-switched role, and from
the Codex export.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers import flip_gate, kernel_adoption, kernel_sandbox, kernel_spawn
from tests.acceptance.drivers.kernel_sandbox import (
    REPO_ROOT,
    codex_instructions,
    export_codex,
    normalize_plugin_location,
)
from tests.acceptance.drivers.shipped_texts import normalize, paragraphs

CHECK = "check_id_citation_discipline.py"
ROLE = "implementer"


def instruction_passages(text: str) -> list[str]:
    """Passages that name the check, speak of the changed files and of reporting, and say
    what to report when the check cannot run."""
    return [
        passage
        for passage in paragraphs(normalize(text))
        if CHECK in passage
        and "chang" in passage.lower()
        and "report" in passage.lower()
        and "not run" in passage.lower()
    ]


def test_the_plugin_definition_carries_the_pre_report_citation_check() -> None:
    definition = (REPO_ROOT / "agents" / f"{ROLE}.md").read_text(encoding="utf-8")

    assert instruction_passages(definition), f"no passage in agents/{ROLE}.md names {CHECK}"


def test_a_kernel_switched_implementer_receives_the_pre_report_citation_check(
    tmp_path: Path,
) -> None:
    plugin = kernel_sandbox.new_sandbox(
        kernel_sandbox.build_template(tmp_path / "template"), tmp_path / "plugin"
    )
    kernel_adoption.record(plugin.root, flip_gate.cited_switch_record(plugin.root, ROLE))
    kernel_sandbox.set_frontmatter_key(plugin, ROLE, "omitClaudeMd: true")
    kernel_sandbox.regenerate(plugin.root)
    project = kernel_spawn.project_checkout(tmp_path / "managed")

    injection = kernel_spawn.spawn(plugin.root, project, f"praxion:{ROLE}")

    received = normalize_plugin_location(injection.joined, plugin.root)
    definition = plugin.read(f"agents/{ROLE}.md")
    assert instruction_passages(received + "\n\n" + definition), (
        f"a switched {ROLE} receives no passage naming {CHECK}"
    )


def test_the_codex_export_carries_the_pre_report_citation_check(tmp_path: Path) -> None:
    wrappers = export_codex(REPO_ROOT, tmp_path / "codex")

    instructions = codex_instructions(wrappers[ROLE])

    assert instruction_passages(instructions), f"the Codex {ROLE} carries no passage on {CHECK}"
