"""The shipped move kits are data the declaration boundary accepts, and the git-conventions
point-of-use hook delivers the rule at the right commands and nowhere else."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from praxion_evals.adherence.moves import declaration
from praxion_evals.adherence.moves.declaration import KITS_ROOT
from praxion_evals.adherence.moves.model import (
    HookContext,
    HookRegistered,
    KernelDerive,
    ManifestRowRemoved,
    ManifestRowScoped,
    Remove,
    SessionStart,
    Write,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_KIT = "git-conventions"
KITS = [GIT_KIT, "adr-conventions"]
HOOK_FILE = "inject_git_conventions_at_use.py"
RULE = "rules/swe/vcs/git-conventions.md"
RULE_ID = "swe/vcs/git-conventions"
ADR_KIT = "adr-conventions"
ADR_RULE = "rules/swe/adr-conventions.md"


@pytest.fixture(scope="module")
def hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("kit_hook", KITS_ROOT / GIT_KIT / HOOK_FILE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin_copy(tmp_path: Path) -> Path:
    """The layout an arm copy has: the hook under `hooks/`, the rule under `rules/`."""
    root = tmp_path / "plugin"
    (root / "hooks").mkdir(parents=True)
    (root / "rules/swe/vcs").mkdir(parents=True)
    shutil.copy(KITS_ROOT / GIT_KIT / HOOK_FILE, root / "hooks" / HOOK_FILE)
    shutil.copy(REPO_ROOT / RULE, root / RULE)
    return root


def _call(command: str, cwd: Path | None = None) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd or "/")}


def _rule_section(heading: str) -> str:
    text = (REPO_ROOT / RULE).read_text(encoding="utf-8")
    return text.split(f"### {heading}", 1)[1].split("\n### ", 1)[0]


# -- The kits load ------------------------------------------------------------------------


@pytest.mark.parametrize("name", KITS)
def test_a_kit_loads_through_the_declaration_boundary_under_its_own_name(name):
    assert declaration.kit(name).move.value == name


@pytest.mark.parametrize("name", KITS)
def test_each_governed_check_names_a_section_its_rule_file_holds_in_the_checkout(name):
    loaded = declaration.kit(name, REPO_ROOT)

    assert 1 <= len(loaded.checks.checks) <= 2


@pytest.mark.parametrize("name", KITS)
def test_a_kit_directory_holds_the_declaration_and_exactly_the_files_it_writes(name):
    kit_dir = KITS_ROOT / name
    written = {
        change.source for change in declaration.kit(name).arms.lean if isinstance(change, Write)
    }

    present = {path for path in kit_dir.iterdir() if path.is_file() and path.suffix != ".pyc"}

    assert present == {kit_dir / declaration.DECLARATION_FILE, *written}


# -- The git-conventions kit ----------------------------------------------------------------


def test_the_git_kit_governs_commit_message_form_and_staging_by_name():
    names = [check.name for check in declaration.kit(GIT_KIT).checks.checks]

    assert names == ["commit message form", "staging by name"]


def test_each_governed_phrase_is_a_phrase_of_its_own_section():
    checks = declaration.kit(GIT_KIT).checks.checks
    phrases_missing = [
        (check.name, phrase)
        for check in checks
        for phrase in check.phrases
        if phrase.casefold() not in _rule_section(check.section).casefold()
    ]

    assert phrases_missing == []
    assert all(check.phrases for check in checks)


def test_the_kernel_prefixes_each_pick_exactly_one_line_of_the_rule():
    (kernel,) = [c for c in declaration.kit(GIT_KIT).arms.lean if isinstance(c, KernelDerive)]
    rule_lines = (REPO_ROOT / RULE).read_text(encoding="utf-8").splitlines()

    picked = {
        prefix: [row for row in rule_lines if row.startswith(prefix)] for prefix in kernel.prefixes
    }

    assert len(kernel.prefixes) == 6
    assert {prefix: len(lines) for prefix, lines in picked.items()} == dict.fromkeys(
        kernel.prefixes, 1
    )


def test_the_lean_arm_writes_the_hook_derives_the_kernel_and_registration_and_leaves_the_rule():
    lean = declaration.kit(GIT_KIT).arms.lean

    kinds = sorted(type(change).__name__ for change in lean)
    paths = {change.path.value for change in lean}

    assert kinds == ["HookRegistered", "KernelDerive", "ManifestRowRemoved", "Write"]
    assert RULE not in paths


def test_the_floor_arm_removes_the_rule_and_its_manifest_row_and_the_full_arm_changes_nothing():
    loaded = declaration.kit(GIT_KIT)

    floor = loaded.arms.floor

    assert [type(change) for change in floor] == [Remove, ManifestRowRemoved]
    assert floor[0].path.value == RULE
    assert loaded.arms.for_arm("full") == ()


def test_the_rule_reaches_the_session_by_a_resident_kernel_and_by_the_hook_before_each_command():
    deliveries = declaration.kit(GIT_KIT).deliveries

    (session_start,) = [d for d in deliveries if isinstance(d, SessionStart)]
    (hook_context,) = [d for d in deliveries if isinstance(d, HookContext)]

    assert session_start.file.value.endswith("git-conventions-resident.md")
    assert (hook_context.event, hook_context.reads.value, hook_context.repeat) == (
        "PreToolUse",
        RULE,
        "each",
    )
    assert any(isinstance(c, HookRegistered) for c in declaration.kit(GIT_KIT).arms.lean)


# -- The point-of-use hook ------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git add greeting.py",
        "git stage greeting.py",
        "git commit -m 'Add greeting'",
        "git add greeting.py && git commit -m 'Add greeting'",
        "cd repo; git add greeting.py",
        "git -C repo commit -m 'Add greeting'",
        "GIT_AUTHOR_NAME=x git commit -m 'Add greeting'",
        "git status\ngit add greeting.py",
    ],
)
def test_the_hook_delivers_the_rule_before_a_staging_or_committing_command(
    hook, plugin_copy, command
):
    text = hook.context_for(_call(command), plugin_copy, {})

    assert text == hook.rule_body((REPO_ROOT / RULE).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "command",
    [
        "git stash",
        "git checkout -- greeting.py",
        "git status",
        "git diff --staged",
        "echo git add",
        "git log --oneline",
        "ls",
    ],
)
def test_the_hook_stays_silent_for_any_other_command(hook, plugin_copy, command):
    assert hook.context_for(_call(command), plugin_copy, {}) is None


def test_the_hook_emits_every_line_of_the_rule_body_and_no_other_line(hook, plugin_copy):
    emitted = hook.context_for(_call("git add a.py"), plugin_copy, {})

    rule = (REPO_ROOT / RULE).read_text(encoding="utf-8")
    assert not emitted.startswith("---")
    assert {row for row in emitted.splitlines() if row.strip()} <= set(rule.splitlines())
    assert "## Git Conventions" in emitted


@pytest.mark.parametrize(
    "disable",
    [RULE_ID, "swe/vcs/*", "swe/*/git-conventions"],
)
def test_the_hook_emits_nothing_when_the_project_disables_the_rule(
    hook, plugin_copy, tmp_path, disable
):
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude/praxion-rules.yaml").write_text(f"version: 1\ndisable:\n  - '{disable}'\n")

    assert hook.context_for(_call("git commit -m x", project), plugin_copy, {}) is None


@pytest.mark.parametrize(
    "config",
    [
        "disable:\n  - ml/*\n",
        "disable: swe/vcs/*\n",
        "disable: [unclosed\n",
        "version: 2\ndisable: ['*']\n",
    ],
    ids=["another-rule", "scalar-list", "malformed", "newer-schema"],
)
def test_the_hook_delivers_when_the_project_list_does_not_disable_the_rule(
    hook, plugin_copy, tmp_path, config
):
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude/praxion-rules.yaml").write_text(config)

    assert hook.context_for(_call("git commit -m x", project), plugin_copy, {}) is not None


def test_the_injection_kill_switch_silences_the_hook(hook, plugin_copy):
    env = {"PRAXION_DISABLE_RULE_INJECTION": "1"}

    assert hook.context_for(_call("git commit -m x"), plugin_copy, env) is None


def test_run_as_an_arm_copy_registers_it_the_hook_prints_one_pre_tool_use_context(plugin_copy):
    result = subprocess.run(
        [sys.executable, str(plugin_copy / "hooks" / HOOK_FILE)],
        input=json.dumps(_call("git add a.py")),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert result.returncode == 0
    assert output["hookEventName"] == "PreToolUse"
    assert output["additionalContext"].startswith("## Git Conventions")


# -- The adr-conventions kit ------------------------------------------------------------------


def _adr_section(heading: str) -> str:
    """The text under ``heading`` (any level) up to the next heading of the same or higher level."""
    lines = (REPO_ROOT / ADR_RULE).read_text(encoding="utf-8").splitlines()
    (start,) = [i for i, row in enumerate(lines) if row.lstrip("#").strip() == heading]
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    body: list[str] = []
    for row in lines[start + 1 :]:
        if row.startswith("#") and len(row) - len(row.lstrip("#")) <= level:
            break
        body.append(row)
    return "\n".join(body)


def test_the_adr_kit_governs_draft_placement_then_decision_category():
    names = [check.name for check in declaration.kit(ADR_KIT).checks.checks]

    assert names == ["decision draft placement", "decision category"]


def test_the_adr_kits_lean_arm_scopes_the_manifest_row_rather_than_removing_it():
    lean = declaration.kit(ADR_KIT).arms.lean

    assert sum(isinstance(c, ManifestRowScoped) for c in lean) == 1
    assert not [c for c in lean if isinstance(c, ManifestRowRemoved)]


def test_the_adr_kits_rule_copy_is_path_scoped_and_keeps_its_paths_and_codex_override():
    copy = KITS_ROOT / ADR_KIT / "rules__swe__adr-conventions.md"
    frontmatter = copy.read_text(encoding="utf-8").split("---", 2)[1].splitlines()

    assert "load: path_scoped" in frontmatter
    assert "load: always_on" not in frontmatter  # only the indented codex override remains
    assert "  - .ai-state/decisions/**" in frontmatter
    assert "codex:" in frontmatter
    assert "  load: always_on" in frontmatter


def test_each_adr_governed_phrase_lies_in_its_own_section():
    checks = declaration.kit(ADR_KIT, REPO_ROOT).checks.checks
    phrases_missing = [
        (check.name, phrase)
        for check in checks
        for phrase in check.phrases
        if phrase.casefold() not in _adr_section(check.section).casefold()
    ]

    assert phrases_missing == []
    assert all(check.phrases for check in checks)
