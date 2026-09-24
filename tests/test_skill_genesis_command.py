"""Structural tests for the /skill-genesis command and its agent's queue mode.

Cites: skills/command-crafting/SKILL.md § argument-hint -- a hint that omits
half the accepted flags is worse than none, because it reads as exhaustive.

The defect these guard: the harvest queue under `.ai-work/_harvest/` had no
reader for eleven days because the command's pre-flight globbed one level
deep and the agent contract named a single slug. The command must now hand
queue enumeration to `scripts/list_harvest_sources.py` and the agent must
accept a `Sources:` list in place of `.ai-work/<task-slug>/`.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMAND_FILE = REPO_ROOT / "commands" / "skill-genesis.md"
AGENT_FILE = REPO_ROOT / "agents" / "skill-genesis.md"


def _split(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert m, f"{path} has no frontmatter block"
    return yaml.safe_load(m.group(1)), m.group(2)


def test_argument_hint_lists_every_flag_the_flags_table_documents() -> None:
    fm, body = _split(COMMAND_FILE)
    hint = fm["argument-hint"]
    assert isinstance(hint, str), "argument-hint must be a quoted string, not a YAML flow sequence"
    table = body.split("## Flags", 1)[1].split("## Process", 1)[0]
    documented = set(re.findall(r"^\| `(--[a-z-]+)", table, re.MULTILINE))
    assert documented >= {"--since", "--scope", "--sources", "--cap", "--dry-run"}
    hinted = set(re.findall(r"--[a-z-]+", hint))
    assert documented == hinted, (
        f"flags table {sorted(documented)} != argument-hint {sorted(hinted)}"
    )


def test_queue_mode_delegates_enumeration_to_the_script_and_spawns_in_sequence() -> None:
    fm, body = _split(COMMAND_FILE)
    assert "scripts/list_harvest_sources.py" in body
    assert (REPO_ROOT / "scripts" / "list_harvest_sources.py").exists()
    assert any(str(t).startswith("Bash(python3") for t in fm["allowed-tools"]), (
        "the command runs the enumeration script, so python3 must be pre-approved"
    )
    assert re.search(r"one spawn per batch.*in sequence", body, re.DOTALL | re.IGNORECASE)
    assert "Sources (read each listed directory" in body, (
        "the batch prompt must carry the Sources: list"
    )


def test_agent_accepts_a_sources_list_and_dedups_against_sibling_reports() -> None:
    _, body = _split(AGENT_FILE)
    assert "queue mode" in body
    assert "`Sources:` list" in body
    assert "prior-report: yes" in body, "the agent must read the prior-report marker"
    assert "memory: yes" in body, "the agent must read the memory marker"
    assert "oversize" in body, "an over-cap source is sampled by section, not read whole"
    assert re.search(r"Sibling reports of this harvest run", body)
    assert "sources: <queue-dir-or-null>" in body, "the report frontmatter records the queue"
    assert "batch: <" in body, "the report frontmatter records the batch"
