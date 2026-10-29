"""Observing a copy offline: what is resident at session start and what a hook emits, with every
channel run rather than read from a declaration, and a refusal naming whatever cannot be run."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
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
REAL_RULE_ID = "swe/agent-model-routing"
REAL_RULE_PATH = "rules/swe/agent-model-routing.md"
REAL_RULE_FIRST_LINE = "## Agent Model Routing"
GONE_WITHIN_SECONDS = 3


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


def _emitting(context: str) -> str:
    """A registered command printing a hook result that carries ``context``."""
    return "printf '%s' " + json.dumps(
        json.dumps({"hookSpecificOutput": {"additionalContext": context}})
    )


def _gone(pid: int) -> bool:
    deadline = time.monotonic() + GONE_WITHIN_SECONDS
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _without_row(manifest: str, rule_id: str) -> str:
    """The manifest text with the rule's row cut out, as the lean arm's text edit does."""
    return re.sub(rf"- id: {re.escape(rule_id)}\n(?:  .*\n)+", "", manifest)


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


# -- The real checkout ------------------------------------------------------------------------


@pytest.fixture
def real_copy(tmp_path: Path) -> Path:
    """The checkout's own rules, linker and hooks: the real manifest, linker and injector together."""
    root = tmp_path / "plugin"
    for tree in ("rules", "lib", "hooks"):
        shutil.copytree(REPO_ROOT / tree, root / tree)
    return root


def test_a_real_hook_delivered_rule_is_resident_until_its_real_manifest_row_is_removed(real_copy):
    assert REAL_RULE_FIRST_LINE in _lines(observe.session_start(real_copy))

    manifest = real_copy / "rules/_manifest.yaml"
    manifest.write_text(_without_row(manifest.read_text(), REAL_RULE_ID), encoding="utf-8")

    assert REAL_RULE_FIRST_LINE not in _lines(observe.session_start(real_copy))
    assert (real_copy / REAL_RULE_PATH).is_file()


def test_the_skip_header_is_the_one_the_real_rule_injection_prints():
    hook = (REPO_ROOT / "hooks/inject_rules.py").read_text(encoding="utf-8")

    assert observe.RULE_INJECTION_SKIPPED in hook


# -- Refusals, not empty observations ---------------------------------------------------------


def _refused_hook(copy: Path, registry: str, payload=BASH_COMMIT, event="PreToolUse") -> str:
    _write(copy, "hooks/hooks.json", registry)
    return _refusal(observe.hook_output(copy, event, payload))


def test_a_matcher_keyed_on_a_field_the_payload_lacks_is_refused_not_read_as_no_match(full_copy):
    registry = _registry("SubagentStart", "^praxion:.*", "exit 9")

    reason = _refused_hook(full_copy, registry, {"cwd": "/x"}, "SubagentStart")

    assert "^praxion:.*" in reason


def test_a_matcher_over_the_agent_type_is_applied_to_it(full_copy):
    registry = _registry("SubagentStart", "^praxion:.*", _emitting("- arrives"))
    _write(full_copy, "hooks/hooks.json", registry)

    hit = observe.hook_output(full_copy, "SubagentStart", {"agent_type": "praxion:verifier"})
    miss = observe.hook_output(full_copy, "SubagentStart", {"agent_type": "other"})

    assert (_lines(hit), _lines(miss)) == (("- arrives",), ())


def test_the_star_matcher_takes_every_event(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("Stop", "*", _emitting("- at stop")))

    assert _lines(observe.hook_output(full_copy, "Stop", {"cwd": "/x"})) == ("- at stop",)


def test_a_hook_that_is_not_a_command_is_refused_naming_it(full_copy):
    registry = json.dumps(
        {"hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "prompt", "prompt": "be brief"}]}]}}
    )

    assert "be brief" in _refused_hook(full_copy, registry, {"cwd": "/x"}, "Stop")


def test_a_result_with_no_additional_context_is_refused_not_read_as_empty(full_copy):
    command = 'echo \'{"systemMessage": "remember"}\''

    reason = _refused_hook(full_copy, _registry("PreToolUse", "Bash", command))

    assert "no additionalContext" in reason


def test_a_result_that_is_json_but_not_an_object_is_refused(full_copy):
    reason = _refused_hook(full_copy, _registry("PreToolUse", "Bash", "echo '[1]'"))

    assert "not a hook result" in reason


def test_an_empty_result_object_is_a_real_empty_observation(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", "echo '{}'"))

    assert _lines(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT)) == ()


def test_a_script_no_registered_hook_runs_is_refused_not_read_as_emitting_nothing(full_copy):
    reason = _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT, script="gone.py"))

    assert "gone.py" in reason


def test_a_session_start_copy_that_does_not_register_the_rule_injection_is_refused(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("SessionStart", "", "true"))

    assert observe.RULE_INJECTION_HOOK in _refusal(observe.session_start(full_copy))


@pytest.mark.parametrize("registry", ["[]", '{"hooks": []}', '{"hooks": {"PreToolUse": null}}'])
def test_a_registry_of_the_wrong_shape_is_refused_not_raised(full_copy, registry):
    assert "hooks.json" in _refused_hook(full_copy, registry)


def test_a_registry_that_is_not_utf8_is_refused(full_copy):
    (full_copy / "hooks/hooks.json").write_bytes(b"\xff\xfe")

    assert "hooks.json" in _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))


@pytest.mark.parametrize("manifest", ["", "rules: [", "[]", "rules: {}"])
def test_a_manifest_that_holds_no_list_of_rules_is_refused(full_copy, manifest):
    _write(full_copy, "rules/_manifest.yaml", manifest)

    assert "_manifest.yaml" in _refusal(observe.session_start(full_copy))


def test_a_manifest_row_that_is_not_a_mapping_is_refused(full_copy):
    _write(full_copy, "rules/_manifest.yaml", "version: 1\nrules:\n- just-a-string\n")

    assert "just-a-string" in _refusal(observe.session_start(full_copy))


def test_a_manifest_that_is_not_utf8_is_refused(full_copy):
    (full_copy / "rules/_manifest.yaml").write_bytes(b"\xff\xfe")

    assert "_manifest.yaml" in _refusal(observe.session_start(full_copy))


def test_a_linked_rule_that_cannot_be_read_is_refused_naming_it(full_copy):
    _lean(full_copy)
    (full_copy / KERNEL_PATH).write_bytes(b"\xff\xfe")

    assert "git-conventions-resident.md" in _refusal(observe.session_start(full_copy))


# -- The sandbox ------------------------------------------------------------------------------


def test_the_side_effect_kill_switches_reach_the_hooks(full_copy):
    command = 'printf \'{"hookSpecificOutput":{"additionalContext":"%s"}}\' "$PRAXION_DISABLE_EVENT_POSTING"'
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", command))

    assert _lines(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT)) == ("1",)


def test_a_relative_copy_path_is_observed_as_the_copy_it_names(full_copy, monkeypatch):
    monkeypatch.chdir(full_copy.parent)

    assert _lines(observe.session_start(Path(full_copy.name))) == INJECTED


def test_non_ascii_rule_text_is_delivered_intact(full_copy):
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", _emitting("- café")))

    assert _lines(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT)) == ("- café",)


def test_a_timeout_takes_the_hooks_grandchildren_with_it(full_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(observe, "SUBPROCESS_TIMEOUT_SECONDS", 1)
    pid_file = tmp_path / "grandchild.pid"
    command = f"sleep 30 & echo $! > {pid_file}; wait"
    _write(full_copy, "hooks/hooks.json", _registry("PreToolUse", "Bash", command))

    assert "did not finish" in _refusal(observe.hook_output(full_copy, "PreToolUse", BASH_COMMIT))
    assert _gone(int(pid_file.read_text()))
