"""The decision-record gate is registered where the harness and the commit hook will run it.

Behavior is judged elsewhere (the acceptance nodes replay payloads through these registered
commands); this file pins only the wiring: three PreToolUse entries, the pre-commit hook with
the paths it fires on, and the executable bits a registered command needs.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}"
WRITE_COMMAND = f"{PLUGIN_ROOT_VAR}/hooks/decisions_gate.sh write"
READ_COMMAND = f"{PLUGIN_ROOT_VAR}/hooks/decisions_gate.sh read"
COMMIT_COMMAND = (
    f"{PLUGIN_ROOT_VAR}/hooks/commit_gate.sh --blocking "
    f"{PLUGIN_ROOT_VAR}/scripts/check_decision_records.py"
)
PRECOMMIT_HOOK_ID = "decision-records"
EXECUTABLES = (
    "hooks/decisions_gate.sh",
    "hooks/commit_gate.sh",
    "scripts/check_decision_records.py",
)


def _pre_tool_use_groups() -> list[dict]:
    registry = json.loads((REPO_ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
    return registry["hooks"]["PreToolUse"]


def _matchers_running(command: str) -> list[str]:
    return [
        group.get("matcher", "")
        for group in _pre_tool_use_groups()
        for hook in group["hooks"]
        if hook["command"] == command
    ]


def _precommit_hook() -> dict:
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [
        h for repo in config["repos"] for h in repo.get("hooks", []) if h["id"] == PRECOMMIT_HOOK_ID
    ]
    assert len(hooks) == 1, f"{PRECOMMIT_HOOK_ID!r} must be registered exactly once"
    return hooks[0]


def test_the_write_and_edit_hook_is_registered_once_under_its_matcher():
    assert _matchers_running(WRITE_COMMAND) == ["Write|Edit"]


def test_the_read_hook_is_registered_once_under_its_matcher():
    assert _matchers_running(READ_COMMAND) == ["Read"]


def test_the_commit_gate_is_registered_once_blocking_in_the_bash_group():
    assert _matchers_running(COMMIT_COMMAND) == ["Bash"]


def test_the_commit_gate_sits_beside_the_id_citation_entry():
    bash = next(g for g in _pre_tool_use_groups() if g.get("matcher") == "Bash")
    commands = [h["command"] for h in bash["hooks"]]
    id_citation = next(i for i, c in enumerate(commands) if "check_id_citation_discipline.py" in c)
    assert commands[id_citation + 1] == COMMIT_COMMAND


def test_the_precommit_hook_runs_the_staged_judgement_over_the_decisions_tree_only():
    hook = _precommit_hook()
    assert hook["entry"] == "python3 scripts/check_decision_records.py --repo-root . --staged"
    assert hook["language"] == "system"
    assert hook["pass_filenames"] is False


@pytest.mark.parametrize(
    "path",
    [
        ".ai-state/decisions/012-some-record.md",
        ".ai-state/decisions/drafts/20261031-0636-user-branch-slug.md",
        ".ai-state/decisions/DECISIONS_INDEX.md",
    ],
)
def test_the_precommit_pattern_fires_on_a_decision_path(path):
    assert re.search(_precommit_hook()["files"], path)


@pytest.mark.parametrize(
    "path", [".ai-state/DESIGN.md", "docs/decisions/x.md", "scripts/check_decision_records.py"]
)
def test_the_precommit_pattern_ignores_other_paths(path):
    assert not re.search(_precommit_hook()["files"], path)


@pytest.mark.parametrize("relative", EXECUTABLES)
def test_each_registered_command_is_executable(relative):
    assert os.access(REPO_ROOT / relative, os.X_OK), f"{relative} lost its executable bit"
