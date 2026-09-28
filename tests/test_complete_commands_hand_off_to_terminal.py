"""The /praxion-complete-install and /praxion-complete-uninstall commands must
never attempt to run the mutating installer invocation themselves.

Both commands drive `install.sh` through the Bash tool, whose stdin is not a
TTY -- the installer's first consent prompt hits EOF under `set -eo pipefail`
and exits before anything runs. These commands must instead: run only the
installer's read-only health check for the user, then hand the exact resolved
mutating command to the user to run in their own terminal, where the prompt
can actually be answered.

Pure file parsing -- no subprocess, no installer invocation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_COMMAND = REPO_ROOT / "commands" / "praxion-complete-install.md"
UNINSTALL_COMMAND = REPO_ROOT / "commands" / "praxion-complete-uninstall.md"
README = REPO_ROOT / "commands" / "README.md"

COMMAND_FILES = (INSTALL_COMMAND, UNINSTALL_COMMAND)

# The installer flags that change filesystem state -- these must never appear
# inside a fenced block the assistant would actually execute.
MUTATING_FLAGS = ("--complete-install", "--complete-uninstall", "--uninstall")

# The stable phrase both the command bodies and the README rows must use to
# tell the user the mutating command runs on their side, not the assistant's.
# The implementer must match this exact substring (case-insensitive).
TERMINAL_HANDOFF_PHRASE = "own terminal"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_FENCE_RE = re.compile(
    r"^[ \t]*```([a-zA-Z0-9_-]*)[ \t]*\n(.*?)^[ \t]*```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _split_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    match = _FRONTMATTER_RE.match(text)
    assert match, f"{path} has no frontmatter block"
    return yaml.safe_load(match.group(1)), match.group(2)


def _fenced_blocks(body: str) -> list[tuple[str, str]]:
    """Return (language, content) for every fenced code block in the body."""
    return [(m.group(1), m.group(2)) for m in _FENCE_RE.finditer(body)]


def _bash_blocks(body: str) -> list[str]:
    return [content for lang, content in _fenced_blocks(body) if lang == "bash"]


@pytest.mark.parametrize("command_file", COMMAND_FILES, ids=lambda p: p.name)
def test_no_bash_block_runs_a_mutating_installer_flag(command_file: Path) -> None:
    _, body = _split_frontmatter(command_file)
    bash_blocks = _bash_blocks(body)
    assert bash_blocks, f"{command_file.name} has no bash block at all"
    offending = [flag for block in bash_blocks for flag in MUTATING_FLAGS if flag in block]
    assert not offending, (
        f"{command_file.name} runs a mutating installer flag from a bash block "
        f"the assistant would execute: {offending}"
    )


@pytest.mark.parametrize("command_file", COMMAND_FILES, ids=lambda p: p.name)
def test_at_least_one_bash_block_runs_the_read_only_health_check(command_file: Path) -> None:
    _, body = _split_frontmatter(command_file)
    bash_blocks = _bash_blocks(body)
    assert any("--check" in block for block in bash_blocks), (
        f"{command_file.name} never runs the read-only `--check` health check "
        "from an executable bash block"
    )


OWN_MUTATING_FLAG = {
    INSTALL_COMMAND: "--complete-install",
    UNINSTALL_COMMAND: "--complete-uninstall",
}


@pytest.mark.parametrize("command_file", COMMAND_FILES, ids=lambda p: p.name)
def test_mutating_command_appears_only_as_text_for_the_user_to_run(command_file: Path) -> None:
    """The file's own mutating flag must be mentioned somewhere as text shown
    to the user -- a non-bash fence or inline code -- so the user actually
    receives the exact command to run. A mention of a *different* command's
    mutating flag (e.g. install.md's Reversal section naming uninstall) does
    not satisfy this -- each file must show its own command."""
    _, body = _split_frontmatter(command_file)
    own_flag = OWN_MUTATING_FLAG[command_file]
    fenced = _fenced_blocks(body)
    non_bash_hits = [content for lang, content in fenced if lang != "bash" and own_flag in content]
    inline_hits = [span for span in _INLINE_CODE_RE.findall(body) if own_flag in span]
    assert non_bash_hits or inline_hits, (
        f"{command_file.name} never shows its own mutating command ({own_flag}) "
        "to the user as plain text or inline code"
    )


@pytest.mark.parametrize("command_file", COMMAND_FILES, ids=lambda p: p.name)
def test_states_the_user_runs_the_mutating_command_in_their_own_terminal(
    command_file: Path,
) -> None:
    _, body = _split_frontmatter(command_file)
    assert TERMINAL_HANDOFF_PHRASE in body.lower(), (
        f"{command_file.name} never tells the user to run the mutating command "
        f"in their {TERMINAL_HANDOFF_PHRASE}"
    )


@pytest.mark.parametrize("command_file", COMMAND_FILES, ids=lambda p: p.name)
def test_frontmatter_tool_and_invocation_restrictions_are_unchanged(command_file: Path) -> None:
    frontmatter, _ = _split_frontmatter(command_file)
    assert frontmatter["allowed-tools"] == ["Bash"]
    assert frontmatter["disable-model-invocation"] is True


def _readme_row(command_name: str) -> str:
    text = README.read_text()
    pattern = re.compile(
        rf"^\|\s*`{re.escape(command_name)}`\s*\|\s*(.+?)\s*\|\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    assert match, f"no README row found for {command_name}"
    return match.group(1)


@pytest.mark.parametrize(
    "command_name", ["/praxion-complete-install", "/praxion-complete-uninstall"]
)
def test_readme_row_describes_the_terminal_hand_off(command_name: str) -> None:
    row = _readme_row(command_name)
    assert TERMINAL_HANDOFF_PHRASE in row.lower(), (
        f"the README row for {command_name} does not mention the "
        f"{TERMINAL_HANDOFF_PHRASE!r} hand-off: {row!r}"
    )
