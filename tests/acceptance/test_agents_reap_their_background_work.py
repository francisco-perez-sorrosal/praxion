"""Every agent definition carries, identically, the duty to reap its background work.

Each agent definition states that the agent stops or awaits every background job it started
before writing its final message, and that every watcher it starts carries a bound (a
timeout or an iteration cap), a watcher that matches processes by name excluding shells.
The text is the same in every definition. The acceptance-design procedure, the path classes
and the verifier's commit-order audit let the acceptance-design commit carry a secret-scanner
allowlist entry its fixtures need. These scenarios prove the texts are present; whether an
agent complies is the verifier's judgment.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.acceptance.drivers.shipped_texts import (
    COORDINATION_DETAILS,
    paragraphs,
    read,
    section,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFINITIONS = sorted(
    p.relative_to(REPO_ROOT).as_posix()
    for p in (REPO_ROOT / "agents").glob("*.md")
    if p.name not in {"README.md", "CLAUDE.md"}
)
REAPING_STATES = (
    r"background",
    r"\b(stop|await|reap)\w*",
    r"final message",
    r"\bwatcher",
    r"timeout",
    r"iteration cap",
    r"shell",
)
SCANNER_CONFIG = ".gitleaks.toml"


def _reaping_paragraphs(relative: str) -> list[str]:
    return [
        " ".join(p.split())
        for p in paragraphs(read(relative))
        if all(re.search(state, p, re.IGNORECASE) for state in REAPING_STATES)
    ]


@pytest.mark.parametrize("definition", DEFINITIONS)
def test_each_agent_definition_requires_reaping_background_work_and_bounding_watchers(
    definition: str,
) -> None:
    assert len(_reaping_paragraphs(definition)) == 1, (
        f"{definition} carries no single paragraph requiring background jobs be stopped or "
        "awaited before the final message and every watcher be bounded"
    )


def test_the_reaping_duty_reads_the_same_in_every_agent_definition() -> None:
    texts = {definition: tuple(_reaping_paragraphs(definition)) for definition in DEFINITIONS}

    assert all(texts.values()), texts
    assert len(set(texts.values())) == 1, texts


@pytest.mark.parametrize(
    "command",
    [
        ["scripts/check_agent_shared_blocks.py"],
        ["scripts/generate_kernels.py", "--check"],
    ],
    ids=["shared-blocks", "kernels-fresh"],
)
def test_the_shared_text_gates_pass(command: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, *command], cwd=REPO_ROOT, capture_output=True, text=True, timeout=300
    )

    assert result.returncode == 0, result.stdout + result.stderr


# -- The acceptance-design commit may carry a scanner allowlist entry --------------------------


def test_the_path_classes_place_an_outer_loop_scanner_allowlist_entry_in_the_outer_loop() -> None:
    classes = section(read(COORDINATION_DETAILS), r"path classes")

    assert SCANNER_CONFIG in classes, classes
    assert re.search(r"allowlist", classes, re.IGNORECASE), classes


def test_the_verifiers_commit_order_audit_cites_the_allowlist_class_with_its_cases() -> None:
    verifier = read("agents/verifier.md")
    audit = [p for p in paragraphs(verifier) if re.search(r"commit order", p, re.IGNORECASE)]

    joined = " ".join(audit)
    assert SCANNER_CONFIG in joined, joined
    assert re.search(r"bad[- ]case", joined, re.IGNORECASE), joined
    assert re.search(r"good[- ]case", joined, re.IGNORECASE), joined


def test_the_acceptance_designer_may_write_the_allowlist_entry_and_name_it_in_its_return() -> None:
    designer = section(read("agents/test-engineer.md"), r"mode: acceptance-design")

    assert SCANNER_CONFIG in designer, designer
    assert re.search(r"allowlist", designer, re.IGNORECASE), designer
