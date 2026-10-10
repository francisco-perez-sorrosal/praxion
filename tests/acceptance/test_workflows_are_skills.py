"""Every former slash workflow is a skill with the name, invocation mode and contract it had.

The before-state is the frozen manifest; the after-state is `skills/<name>/SKILL.md` as Claude
Code reads it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest
import yaml

from tests.acceptance.drivers.command_migration import (
    DOLLAR_AMOUNT,
    REPO_ROOT,
    SHELL_DEFAULT,
    body,
    frontmatter,
    frontmatter_lines,
    manifest,
    names,
    reads_arguments,
    skill_text,
    tool_set,
    workflow,
)

ALL = names()
USER_ONLY = names("user-only")
MODEL_INVOCABLE = names("model-invocable")
WITH_HINT = [w["name"] for w in manifest()["workflows"] if w["argument_hint"] is not None]
WITHOUT_HINT = [w["name"] for w in manifest()["workflows"] if w["argument_hint"] is None]


def test_the_frozen_before_state_records_every_workflow_with_the_stated_totals():
    totals = manifest()["totals"]

    assert totals == {
        "entries": 44,
        "user_only": 33,
        "model_invocable": 11,
        "with_argument_hint": 37,
    }


def test_each_frozen_entry_records_the_fields_later_equivalence_checks_read():
    required = {
        "name", "frontmatter_keys", "description", "argument_hint", "argument_hint_type",
        "allowed_tools", "invocation", "body_sha256", "body_lines", "placeholders",
        "relative_links", "workflow_references", "carries_commit_process",
        "references_plugin_root", "scripts_invoked", "heading_outline",
    }  # fmt: skip

    missing = {w["name"]: sorted(required - w.keys()) for w in manifest()["workflows"]}

    assert not {k: v for k, v in missing.items() if v}, missing


def test_the_retired_workflow_directory_no_longer_exists():
    assert not (REPO_ROOT / "commands").exists(), (
        "a commands/ directory is scanned by Claude Code by default once the manifest stops "
        "naming it, so any file placed back there would silently register as a command"
    )


def test_the_plugin_manifest_neither_registers_nor_mentions_commands():
    manifest_text = (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    plugin = json.loads(manifest_text)

    assert "commands" not in plugin
    assert "commands" not in [k.lower() for k in plugin.get("keywords", [])]
    assert not re.search(r"\bcommands?\b", plugin.get("description", ""), re.IGNORECASE)


# The pre-existing warning set: hook quoting anywhere, and the missing-frontmatter warnings of
# the root guidance file and the agents directory's two prose files. Nothing else is tolerated.
_HOOK_QUOTING = r"Shell command uses \$\{CLAUDE_PLUGIN_ROOT\} without quotes"
_PRE_EXISTING_FILES = ("/CLAUDE.md", "/agents/README.md", "/agents/CLAUDE.md")


def _validator_sections(output: str) -> list[tuple[str, list[str]]]:
    """Each `Validating <kind>: <path>` section with the warning lines it carries."""
    sections = []
    for chunk in re.split(r"\n(?=Validating )", output):
        lines = chunk.splitlines()
        if lines and lines[0].startswith("Validating "):
            sections.append((lines[0], [ln.strip() for ln in lines if ln.strip().startswith("❯")]))
    return sections


def _tolerated(header: str, warning: str) -> bool:
    if re.search(_HOOK_QUOTING, warning):
        return True
    path = header.split(":", 1)[-1].strip()
    root_relative = path[len(str(REPO_ROOT)) :] if path.startswith(str(REPO_ROOT)) else path
    return root_relative in _PRE_EXISTING_FILES


@pytest.mark.skipif(shutil.which("claude") is None, reason="needs the Claude Code CLI on PATH")
def test_the_plugin_validates_with_no_error_and_only_the_pre_existing_warnings():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_"))}
    result = subprocess.run(
        ["claude", "plugin", "validate", "."],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180,
    )  # fmt: skip
    output = result.stdout + result.stderr
    sections = _validator_sections(output)
    unexpected = [f"{h}: {w}" for h, ws in sections for w in ws if not _tolerated(h, w)]
    naming_commands = [ln for ln in output.splitlines() if "commands/" in ln]

    assert result.returncode == 0, output[-2000:]
    assert not [h for h, _ in sections if h.startswith("Validating command")]
    assert not unexpected, unexpected
    assert not naming_commands, naming_commands


@pytest.mark.parametrize("name", ALL)
def test_each_workflow_is_a_skill_named_after_its_directory(name):
    meta = frontmatter(skill_text(name))

    assert meta.get("name") == name


@pytest.mark.parametrize("name", USER_ONLY)
def test_a_user_only_workflow_stays_user_only_on_one_exact_line(name):
    block_lines = skill_text(name).split("---", 2)[1].splitlines()

    assert "disable-model-invocation: true" in block_lines
    assert frontmatter(skill_text(name)).get("disable-model-invocation") is True


@pytest.mark.parametrize("name", MODEL_INVOCABLE)
def test_a_model_invocable_workflow_stays_model_invocable(name):
    assert frontmatter(skill_text(name)).get("disable-model-invocation") in (None, False)


@pytest.mark.parametrize("name", MODEL_INVOCABLE)
def test_a_model_invocable_description_is_byte_identical_to_the_frozen_one(name):
    assert frontmatter(skill_text(name)).get("description") == workflow(name)["description"]


@pytest.mark.parametrize("name", ALL)
def test_the_tool_list_is_one_line_and_names_the_frozen_tool_set(name):
    text = skill_text(name)
    lines = frontmatter_lines(text, "allowed-tools")
    expected = tool_set(workflow(name)["allowed_tools"])

    assert len(lines) == 1, f"allowed-tools is written on {len(lines)} opening lines"
    one_line = yaml.safe_load(lines[0])["allowed-tools"]
    assert isinstance(one_line, list), f"allowed-tools is not a list on its own line: {lines[0]!r}"
    assert tool_set(one_line) == expected
    assert tool_set(frontmatter(text).get("allowed-tools")) == expected


@pytest.mark.parametrize("name", WITH_HINT)
def test_a_declared_argument_hint_is_one_quoted_line_and_the_body_reads_the_arguments(name):
    text = skill_text(name)
    lines = frontmatter_lines(text, "argument-hint")

    assert len(lines) == 1, f"argument-hint opens on {len(lines)} lines"
    value = lines[0].split(":", 1)[1].strip()
    assert re.fullmatch(r"\"[^\"]*\"|'[^']*'", value), (
        f"argument-hint is not one quoted value: {value!r}"
    )
    assert isinstance(frontmatter(text).get("argument-hint"), str)
    assert reads_arguments(text), "the body never reads $ARGUMENTS or an indexed form of it"


@pytest.mark.parametrize("name", WITHOUT_HINT)
def test_a_workflow_that_declared_no_argument_hint_declares_none(name):
    assert "argument-hint" not in frontmatter(skill_text(name))


@pytest.mark.parametrize("name", ALL)
def test_the_description_is_non_empty_bounded_and_free_of_angle_brackets(name):
    description = frontmatter(skill_text(name)).get("description")

    assert isinstance(description, str)
    assert description.strip()
    assert len(description) <= 1024
    assert "<" not in description
    assert ">" not in description


@pytest.mark.parametrize("name", ALL)
def test_the_body_holds_no_unescaped_dollar_amount(name):
    found = DOLLAR_AMOUNT.findall(body(skill_text(name)))

    assert not found, f"text the harness would take for an argument placeholder: {found}"


@pytest.mark.parametrize("name", ALL)
def test_the_body_attaches_no_shell_default_to_an_argument_placeholder(name):
    found = [m.group(0) for m in SHELL_DEFAULT.finditer(body(skill_text(name)))]

    assert not found, found
