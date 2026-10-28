"""Observing a copy offline: what is resident at session start and what a hook emits, with every
channel run rather than read from a declaration, and a refusal naming whatever cannot be run."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import observe
from praxion_evals.adherence.moves.declaration import KITS_ROOT
from praxion_evals.adherence.moves.observe import Observed, Refused

REPO_ROOT = Path(__file__).resolve().parents[2]
RULE_PATH = "rules/swe/vcs/git-conventions.md"
RULE_ID = "swe/vcs/git-conventions"
KERNEL_PATH = "rules/swe/vcs/git-conventions-resident.md"
KIT_HOOK = "inject_git_conventions_at_use.py"
RULE_BODY = ["## Git Conventions", "- Stage specific files by name", "- Never a bare `git stash`"]
KERNEL_BODY = ["- Stage specific files by name"]
INJECTION_HEADER = "## Praxion Rules (auto-injected)"
INJECTED = (INJECTION_HEADER, *RULE_BODY)
HOOK_COMMAND = f"python3 ${{CLAUDE_PLUGIN_ROOT}}/hooks/{KIT_HOOK}"
BASH_COMMIT = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}


BASELINE_ROW = ("baseline", "rules/baseline.md", "symlink")
BASELINE_RULE = '---\npaths:\n  - "nothing/**"\n---\n- never resident\n'


def _manifest(*rows: tuple[str, str, str]) -> str:
    """Always holds a linked path-scoped row: with none, the linker links every rule file."""
    entries = "".join(
        f"- id: {rule_id}\n  path: {path}\n  load: always_on\n  core: false\n  install: {install}\n"
        for rule_id, path, install in (BASELINE_ROW, *rows)
    )
    return f"version: 1\nrules:\n{entries}"


def _registry(event: str, matcher: str, *commands: str) -> str:
    hooks = [{"type": "command", "command": command, "timeout": 5} for command in commands]
    return json.dumps({"hooks": {event: [{"matcher": matcher, "hooks": hooks}]}})


def _write(root: Path, relative: str, text: str) -> None:
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    (root / relative).write_text(text, encoding="utf-8")


def _rule_text(body: list[str], frontmatter: str = "core: false\nload: always_on") -> str:
    return f"---\n{frontmatter}\n---\n" + "\n".join(body) + "\n"


def _files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def full_copy(tmp_path: Path) -> Path:
    """A minimal plugin copy: the real linker, rule injection and kit hook, one injected rule."""
    root = tmp_path / "copy"
    _write(root, "lib/install_shared.sh", (REPO_ROOT / "lib/install_shared.sh").read_text())
    for hook in ("inject_rules.py", "_hook_utils.py"):
        _write(root, f"hooks/{hook}", (REPO_ROOT / "hooks" / hook).read_text())
    _write(root, f"hooks/{KIT_HOOK}", (KITS_ROOT / "git-conventions" / KIT_HOOK).read_text())
    _write(root, RULE_PATH, _rule_text(RULE_BODY, "core: false\nload: always_on"))
    _write(root, BASELINE_ROW[1], BASELINE_RULE)
    _write(root, "rules/_manifest.yaml", _manifest((RULE_ID, RULE_PATH, "hook-deliver")))
    registry = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/inject_rules.py",
                        }
                    ],
                }
            ],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": HOOK_COMMAND}]}
            ],
        }
    }
    _write(root, "hooks/hooks.json", json.dumps(registry))
    return root


def _lean(copy: Path) -> Path:
    """The lean arm's copy: the row removed, the full rule left on disk, a linked kernel."""
    _write(copy, KERNEL_PATH, _rule_text(KERNEL_BODY))
    _write(
        copy,
        "rules/_manifest.yaml",
        _manifest(("swe/vcs/git-conventions-resident", KERNEL_PATH, "symlink")),
    )
    return copy


def _lines(observation: observe.Observation) -> tuple[str, ...]:
    assert isinstance(observation, Observed), observation
    return observation.lines


def _refusal(observation: observe.Observation) -> str:
    assert isinstance(observation, Refused), observation
    return observation.reason


# -- Session start ----------------------------------------------------------------------------


def test_the_full_copy_yields_the_whole_rule_at_session_start(full_copy):
    assert _lines(observe.session_start(full_copy)) == INJECTED


def test_a_copy_with_the_row_removed_yields_none_of_the_rule_though_the_file_stays(full_copy):
    _write(full_copy, "rules/_manifest.yaml", _manifest())

    assert _lines(observe.session_start(full_copy)) == ()
    assert (full_copy / RULE_PATH).is_file()


def test_the_lean_copy_yields_its_linked_kernel_and_not_the_rest_of_the_rule(full_copy):
    lines = _lines(observe.session_start(_lean(full_copy)))

    assert lines == tuple(KERNEL_BODY)
    assert RULE_BODY[2] not in lines


def test_a_path_scoped_linked_rule_is_not_resident_at_session_start(full_copy):
    _lean(full_copy)
    scoped = _rule_text(["- loads only for tests"], 'paths:\n  - "tests/**"')
    _write(full_copy, "rules/scoped.md", scoped)
    _write(
        full_copy,
        "rules/_manifest.yaml",
        _manifest(
            ("swe/vcs/git-conventions-resident", KERNEL_PATH, "symlink"),
            ("scoped", "rules/scoped.md", "symlink"),
        ),
    )

    assert _lines(observe.session_start(full_copy)) == tuple(KERNEL_BODY)


def test_a_manifest_with_no_linked_row_is_observed_as_the_linker_treats_it_linking_every_rule(
    full_copy,
):
    _write(
        full_copy,
        "rules/_manifest.yaml",
        f"version: 1\nrules:\n- id: {RULE_ID}\n  path: {RULE_PATH}\n  install: hook-deliver\n",
    )

    assert _lines(observe.session_start(full_copy)) == (*RULE_BODY, *INJECTED)


def test_a_manifest_row_of_an_unknown_install_kind_is_refused_naming_the_row(full_copy):
    _write(full_copy, "rules/_manifest.yaml", _manifest((RULE_ID, RULE_PATH, "teleport")))

    reason = _refusal(observe.session_start(full_copy))

    assert RULE_ID in reason
    assert "teleport" in reason


def test_a_missing_manifest_is_refused_not_read_as_no_rules(full_copy):
    (full_copy / "rules/_manifest.yaml").unlink()

    assert "_manifest.yaml" in _refusal(observe.session_start(full_copy))


def test_a_rule_injection_that_reports_it_was_skipped_is_refused(full_copy):
    skipped = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"{observe.RULE_INJECTION_SKIPPED}\n\nPyYAML is missing.",
        }
    }
    _write(full_copy, "hooks/inject_rules.py", f"import json\nprint(json.dumps({skipped!r}))\n")

    assert "PyYAML is missing" in _refusal(observe.session_start(full_copy))


def test_the_operators_own_home_and_settings_never_reach_the_observation(
    full_copy, tmp_path, monkeypatch
):
    operator_home = tmp_path / "operator"
    _write(operator_home, ".claude/rules/mine.md", "- the operator's own rule\n")
    monkeypatch.setenv("HOME", str(operator_home))
    monkeypatch.setenv("PRAXION_DISABLE_RULE_INJECTION", "1")

    assert _lines(observe.session_start(full_copy)) == INJECTED


def test_observing_writes_nothing_into_the_copy(full_copy):
    before = _files(full_copy)

    observe.session_start(full_copy)
    observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT)

    assert _files(full_copy) == before


# -- One hook ---------------------------------------------------------------------------------


def test_a_hook_matching_the_declared_command_emits_the_rules_lines(full_copy):
    assert _lines(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT)) == tuple(RULE_BODY)


def test_a_command_the_hook_does_not_declare_emits_nothing(full_copy):
    listing = {"tool_name": "Bash", "tool_input": {"command": "git stash"}}

    assert _lines(observe.hook_output(full_copy, "PreToolUse", listing)) == ()


def test_a_hook_whose_matcher_misses_the_tool_is_not_run(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", "exit 9"))

    assert _lines(observe.hook_output(full_copy, "PreToolUse", {"tool_name": "Edit"})) == ()


def test_an_event_with_no_registered_hook_emits_nothing(full_copy):
    assert _lines(observe.hook_output(full_copy, "PostToolUse", BASH_COMMIT)) == ()


def test_a_broken_hook_is_refused_naming_the_hook(full_copy):
    command = "echo 'boom: the rule file is gone' >&2; exit 3"
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", command))

    reason = _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))

    assert command in reason
    assert "exited 3" in reason
    assert "boom" in reason


def test_a_hook_printing_something_that_is_not_a_hook_result_is_refused(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", "echo not json"))

    assert "echo not json" in _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))


def test_a_hook_that_outlasts_the_timeout_is_refused(full_copy, monkeypatch):
    monkeypatch.setattr(observe, "SUBPROCESS_TIMEOUT_SECONDS", 1)
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", "sleep 10"))

    assert "did not finish" in _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))


def test_a_missing_hook_registry_is_refused_not_read_as_no_hooks(full_copy):
    (full_copy / "hooks/hooks.json").unlink()

    assert "hooks.json" in _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))


def test_naming_the_script_runs_only_that_hook_among_the_registered(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", "exit 9", HOOK_COMMAND))

    narrowed = observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT, script=KIT_HOOK)

    assert _lines(narrowed) == tuple(RULE_BODY)
    assert "exit 9" in _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))


def test_a_malformed_matcher_is_refused_not_skipped(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "(", HOOK_COMMAND))

    assert "malformed" in _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))


def test_the_kit_hook_in_a_real_checkout_copy_is_observed_with_the_checkouts_own_rule(tmp_path):
    root = tmp_path / "plugin"
    shutil.copytree(REPO_ROOT / "rules/swe/vcs", root / "rules/swe/vcs")
    _write(root, f"hooks/{KIT_HOOK}", (KITS_ROOT / "git-conventions" / KIT_HOOK).read_text())
    _write(root, "hooks/hooks.json", _registry("PreToolUse", "Bash", HOOK_COMMAND))

    lines = _lines(observe.hook_output(root, "PreToolUse", BASH_COMMIT))

    assert "## Git Conventions" in lines
    assert any(line.startswith("- Stage specific files by name") for line in lines)
