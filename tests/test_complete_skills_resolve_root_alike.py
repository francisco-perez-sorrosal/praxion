"""The two complete-skills resolve the plugin root with one and the same block.

Both skills carry one `bash` block that reads the root Claude Code substituted for
`${CLAUDE_PLUGIN_ROOT}`, falls back to the plugin registry, and runs `install.sh code --check`
from the root it found. The blocks may differ only in the line that reports no installed plugin.
Neither may pick a version by listing the plugin cache, nor read a shell variable with a default.

Pure file parsing -- no subprocess, no installer invocation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_COMMAND = REPO_ROOT / "skills" / "praxion-complete-install" / "SKILL.md"
UNINSTALL_COMMAND = REPO_ROOT / "skills" / "praxion-complete-uninstall" / "SKILL.md"
COMMAND_FILES = (INSTALL_COMMAND, UNINSTALL_COMMAND)

NOT_FOUND_LINE = "Praxion plugin not found"
FORBIDDEN_IN_THE_BODY = ("ls -d", "head -1", "${CLAUDE_PLUGIN_ROOT:-", "plugins/cache")

_BASH_FENCE_RE = re.compile(r"^```bash[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def _bash_blocks(path: Path) -> list[str]:
    return _BASH_FENCE_RE.findall(path.read_text(encoding="utf-8"))


def _resolution_block(path: Path) -> str:
    blocks = _bash_blocks(path)
    assert len(blocks) == 1, f"{path.parent.name} holds {len(blocks)} bash blocks, expected one"
    return blocks[0]


def _without_the_not_found_line(block: str) -> list[str]:
    return [line for line in block.splitlines() if NOT_FOUND_LINE not in line]


def test_the_two_blocks_differ_only_in_the_not_found_line() -> None:
    install, uninstall = (_resolution_block(path) for path in COMMAND_FILES)

    assert any(NOT_FOUND_LINE in line for line in install.splitlines())
    assert any(NOT_FOUND_LINE in line for line in uninstall.splitlines())
    assert _without_the_not_found_line(install) == _without_the_not_found_line(uninstall)


@pytest.mark.parametrize("command_file", COMMAND_FILES, ids=lambda path: path.parent.name)
def test_no_skill_lists_the_cache_or_defaults_a_shell_variable(command_file: Path) -> None:
    text = command_file.read_text(encoding="utf-8")

    found = [needle for needle in FORBIDDEN_IN_THE_BODY if needle in text]
    assert not found, f"{command_file.parent.name} still holds {found}"


@pytest.mark.parametrize("command_file", COMMAND_FILES, ids=lambda path: path.parent.name)
def test_the_substituted_token_is_read_through_a_quoted_heredoc(command_file: Path) -> None:
    """Text Claude Code did not substitute must reach the shell as data, never as an expansion."""
    block = _resolution_block(command_file)

    opener = re.search(r"<<\s*'(\w+)'\s*\n\$\{CLAUDE_PLUGIN_ROOT\}\n\1\n", block)
    assert opener, "the token is not the body of a quoted heredoc"
    outside = block.replace(opener.group(0), "")
    assert "CLAUDE_PLUGIN_ROOT" not in outside, "the token is named outside the quoted heredoc"
