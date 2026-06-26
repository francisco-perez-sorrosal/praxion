from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER_PATH = REPO_ROOT / "codex" / "config" / "export-codex-rules-bridge.py"


def _hermetic_env() -> dict[str, str]:
    """Subprocess env with ambient Praxion kill-switches stripped.

    The codex hook wrappers copy ``os.environ`` before dispatching. Without
    this, an ambient ``PRAXION_DISABLE_*`` flag set in the developer session
    leaks into the hook under test and silently flips its behavior. Tests
    control disable flags via the project settings overlay, never via inherited
    env -- so the test env must not carry them.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")}


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_codex_rules_bridge", EXPORTER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_hook(path: Path, payload: dict[str, object]) -> dict[str, object]:
    result = subprocess.run(
        ["python3", str(path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=_hermetic_env(),
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout) if result.stdout.strip() else {}


def run_hook_result(
    path: Path,
    payload: dict[str, object],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(path)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=cwd,
        env=_hermetic_env(),
    )


def write_rule(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_project_settings(path: Path, env: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"env": env}), encoding="utf-8")


def test_export_rules_bridge_writes_prefixed_hooks_and_manifest(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"

    written = exporter.export_rules_bridge(REPO_ROOT, out_dir)

    assert out_dir / "praxion" / "rules_manifest.json" in written
    assert out_dir / "hooks" / "praxion-session-start.py" in written
    assert out_dir / "hooks" / "praxion-decisions-session-start.py" in written
    assert out_dir / "hooks" / "praxion-observability-session-start.py" in written
    assert out_dir / "hooks" / "praxion-observability-post-tool-use.py" in written
    assert out_dir / "hooks" / "praxion-user-prompt-submit.py" in written
    assert out_dir / "hooks" / "praxion-process-framing-user-prompt-submit.py" in written
    assert out_dir / "hooks" / "praxion-subagent-pre-tool-use.py" in written
    assert out_dir / "hooks" / "praxion-worktree-guard-pre-tool-use.py" in written
    assert out_dir / "hooks" / "praxion-pre-tool-use.py" in written
    assert out_dir / "hooks" / "praxion-format-python-post-tool-use.py" in written
    assert out_dir / "hooks" / "praxion-detect-duplication-post-tool-use.py" in written
    assert out_dir / "hooks" / "praxion-precompact-state.py" in written
    assert out_dir / "praxion" / "hook_runtime.py" in written
    # Removed memory hooks must not be generated
    assert out_dir / "hooks" / "praxion-memory-session-start.py" not in written
    assert out_dir / "hooks" / "praxion-memory-stop.py" not in written
    assert out_dir / "hooks" / "praxion-commit-memory-pre-tool-use.py" not in written
    assert out_dir / "hooks" / "praxion-memory-subagent-stop.py" not in written

    manifest = json.loads((out_dir / "praxion" / "rules_manifest.json").read_text(encoding="utf-8"))
    relpaths = {rule["relpath"] for rule in manifest["rules"]}
    assert "rules/swe/agent-behavioral-contract.md" in relpaths
    assert "rules/swe/testing-conventions.md" in relpaths
    always_on = set(manifest["always_on_rule_ids"])
    assert "rules::swe::agent-model-routing" not in always_on
    assert "rules::swe::memory-protocol" not in always_on

    registrations = json.loads(
        (out_dir / "praxion" / "hook_registrations.json").read_text(encoding="utf-8")
    )
    hooks = registrations["hooks"]
    serialized_hooks = json.dumps(hooks)
    assert '"async"' not in serialized_hooks
    assert hooks["SessionStart"][0]["hooks"][0]["statusMessage"].startswith("Praxion:")
    assert "praxion-session-start.py" in hooks["SessionStart"][0]["hooks"][0]["command"]
    assert "praxion-decisions-session-start.py" in hooks["SessionStart"][1]["hooks"][0]["command"]
    assert "praxion-observability-stop.py" in hooks["Stop"][0]["hooks"][0]["command"]
    assert (
        "praxion-observability-post-tool-use.py" in hooks["PostToolUse"][0]["hooks"][0]["command"]
    )
    assert (
        "praxion-process-framing-user-prompt-submit.py"
        in hooks["UserPromptSubmit"][1]["hooks"][0]["command"]
    )
    assert (
        "praxion-observability-subagent-stop.py" in hooks["SubagentStop"][0]["hooks"][0]["command"]
    )
    assert "praxion-precompact-state.py" in hooks["PreCompact"][0]["hooks"][0]["command"]
    assert "git rev-parse" not in hooks["SessionStart"][0]["hooks"][0]["command"]
    assert "__PRAXION_PROJECT_ROOT__" in hooks["SessionStart"][0]["hooks"][0]["command"]
    pre_tool_commands = "\n".join(
        hook["command"] for group in hooks["PreToolUse"] for hook in group["hooks"]
    )
    assert "praxion-subagent-pre-tool-use.py" in pre_tool_commands
    assert "praxion-commit-memory-pre-tool-use.py" not in pre_tool_commands
    assert "praxion-worktree-guard-pre-tool-use.py" in pre_tool_commands
    rule_group = next(
        group
        for group in hooks["PreToolUse"]
        if "praxion-pre-tool-use.py" in group["hooks"][0]["command"]
    )
    assert rule_group["matcher"] == "Edit|MultiEdit|NotebookEdit|Write|apply_patch|ApplyPatch"


def test_generated_hooks_route_always_on_prompt_and_path_rules(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    session_hook = out_dir / "hooks" / "praxion-session-start.py"
    prompt_hook = out_dir / "hooks" / "praxion-user-prompt-submit.py"
    pre_hook = out_dir / "hooks" / "praxion-pre-tool-use.py"

    session_output = run_hook(
        session_hook, {"hook_event_name": "SessionStart", "cwd": str(tmp_path)}
    )
    session_context = session_output["hookSpecificOutput"]["additionalContext"]
    assert "rules/swe/agent-behavioral-contract.md" in session_context
    assert "rules/swe/agent-model-routing.md" not in session_context
    assert "rules/swe/memory-protocol.md" not in session_context

    prompt_output = run_hook(
        prompt_hook,
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "Please update the tests and pytest coverage",
        },
    )
    prompt_context = prompt_output["hookSpecificOutput"]["additionalContext"]
    assert prompt_output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "rules/swe/testing-conventions.md" in prompt_context

    prompt_path_output = run_hook(
        prompt_hook,
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "Edit tests/test_example.py",
        },
    )
    assert (
        "rules/swe/testing-conventions.md"
        in prompt_path_output["hookSpecificOutput"]["additionalContext"]
    )

    pre_output = run_hook(
        pre_hook,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": "tests/test_example.py"},
        },
    )
    pre_context = pre_output["hookSpecificOutput"]["additionalContext"]
    assert "rules/swe/testing-conventions.md" in pre_context

    read_output = run_hook(
        pre_hook,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": "tests/test_example.py"},
        },
    )
    assert read_output == {}

    bash_output = run_hook(
        pre_hook,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "cwd": str(tmp_path),
            "tool_input": {"command": "sed -n '1,20p' tests/test_example.py"},
        },
    )
    assert bash_output == {}


def test_project_settings_overlay_disables_codex_hooks(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    write_project_settings(
        tmp_path / ".codex" / "praxion" / "settings.json",
        {"PRAXION_DISABLE_PROCESS_INJECT": "1"},
    )
    (tmp_path / ".ai-state").mkdir()

    framing_hook = out_dir / "hooks" / "praxion-process-framing-user-prompt-submit.py"
    framing_output = run_hook(
        framing_hook,
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "Please design the adapter flow for Codex",
        },
    )
    assert framing_output == {}


def test_decisions_session_start_hook_waits_for_ai_state(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    decisions_hook = out_dir / "hooks" / "praxion-decisions-session-start.py"

    skipped = run_hook(
        decisions_hook,
        {"hook_event_name": "SessionStart", "cwd": str(tmp_path), "session_id": "s1"},
    )
    assert skipped == {}

    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    # Hook runs when .ai-state exists, even without a DECISIONS_INDEX.md
    result = run_hook_result(
        decisions_hook,
        {"hook_event_name": "SessionStart", "cwd": str(tmp_path), "session_id": "s1"},
    )
    assert result.returncode == 0


def test_observability_post_tool_use_hook_writes_observations(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    post_hook = out_dir / "hooks" / "praxion-observability-post-tool-use.py"

    result = run_hook_result(
        post_hook,
        {
            "hook_event_name": "PostToolUse",
            "cwd": str(tmp_path),
            "session_id": "session-1",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/example.py"},
            "tool_response": {},
        },
    )
    assert result.returncode == 0
    observations = (ai_state / "observations.jsonl").read_text(encoding="utf-8")
    assert '"event_type":"tool_use"' in observations
    assert '"tool_name":"Write"' in observations


def test_process_framing_hook_waits_for_ai_state_and_injects(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    framing_hook = out_dir / "hooks" / "praxion-process-framing-user-prompt-submit.py"

    skipped = run_hook(
        framing_hook,
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "Please design and implement the full adapter flow?",
        },
    )
    assert skipped == {}

    (tmp_path / ".ai-state").mkdir()
    active = run_hook(
        framing_hook,
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "Please design and implement the full adapter flow?",
        },
    )
    spec = active["hookSpecificOutput"]
    assert spec["hookEventName"] == "UserPromptSubmit"
    assert "tier selector" in spec["additionalContext"]
    assert "behavioral contract" in spec["additionalContext"]


def test_post_tool_use_wrappers_normalize_legacy_additional_context(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    duplicate_hook = out_dir / "hooks" / "praxion-detect-duplication-post-tool-use.py"
    target = tmp_path / "duplicate.py"
    target.write_text(
        """
def alpha():
    value = 1
    total = value + 1
    print(total)
    print(total + 1)
    return total


def beta():
    value = 1
    total = value + 1
    print(total)
    print(total + 1)
    return total
""".strip()
        + "\n",
        encoding="utf-8",
    )

    output = run_hook(
        duplicate_hook,
        {
            "hook_event_name": "PostToolUse",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(target)},
        },
    )
    spec = output["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostToolUse"
    assert "[duplication]" in spec["additionalContext"]


def test_subagent_context_hook_updates_agent_and_task_payloads(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)
    (tmp_path / ".ai-state").mkdir()

    subagent_hook = out_dir / "hooks" / "praxion-subagent-pre-tool-use.py"
    for tool_name in ("Agent", "Task"):
        output = run_hook(
            subagent_hook,
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "cwd": str(tmp_path),
                "session_id": "session-1",
                "tool_input": {
                    "subagent_type": "general-purpose",
                    "prompt": "Inspect the adapter surface.",
                },
            },
        )
        spec = output["hookSpecificOutput"]
        assert spec["hookEventName"] == "PreToolUse"
        assert spec["permissionDecision"] == "allow"
        prompt = spec["updatedInput"]["tool_input"]["prompt"]
        assert "Surface Assumptions" in prompt
        assert "Inspect the adapter surface." in prompt


def test_cleanup_learnings_hook_surfaces_unpromoted_entries(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    learnings = tmp_path / ".ai-work" / "task-one" / "LEARNINGS.md"
    learnings.parent.mkdir(parents=True)
    learnings.write_text("- **[insight]** Keep adapters thin.\n", encoding="utf-8")

    cleanup_hook = out_dir / "hooks" / "praxion-cleanup-learnings-pre-tool-use.py"
    output = run_hook(
        cleanup_hook,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "cwd": str(tmp_path),
            "tool_input": {"command": "rm -rf .ai-work"},
        },
    )
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "LEARNINGS.md files found" in context
    assert ".ai-work/task-one/LEARNINGS.md" in context


def test_precompact_hook_writes_pipeline_state(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    wip = tmp_path / ".ai-work" / "adapter" / "WIP.md"
    wip.parent.mkdir(parents=True)
    wip.write_text("# WIP\n\nCurrent step: hook completion.\n", encoding="utf-8")

    precompact_hook = out_dir / "hooks" / "praxion-precompact-state.py"
    result = run_hook_result(
        precompact_hook,
        {"hook_event_name": "PreCompact", "cwd": str(tmp_path)},
    )
    assert result.returncode == 0
    state = (tmp_path / ".ai-work" / "PIPELINE_STATE.md").read_text(encoding="utf-8")
    assert "adapter/WIP.md" in state
    assert "Current step: hook completion." in state


def test_prompt_matching_avoids_generic_false_positives(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    prompt_hook = out_dir / "hooks" / "praxion-user-prompt-submit.py"
    output = run_hook(
        prompt_hook,
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(tmp_path),
            "prompt": "work on skills and agents export",
        },
    )
    spec = output["hookSpecificOutput"]
    assert spec["hookEventName"] == "UserPromptSubmit"
    context = spec["additionalContext"]
    assert "rules/swe/shipped-artifact-isolation.md" in context
    assert "rules/ml/eval-driven-verification.md" not in context
    assert "rules/ml/gpu-budget-conventions.md" not in context


def test_new_generic_rules_are_picked_up_automatically_without_allowlist(
    tmp_path: Path,
):
    exporter = load_exporter()
    repo_root = tmp_path / "repo"
    write_rule(
        repo_root / "rules" / "swe" / "new-portable-rule.md",
        "## New Portable Rule\n\nPortable guidance for code review.\n",
    )
    write_rule(
        repo_root / "rules" / "swe" / "new-path-rule.md",
        '---\npaths:\n  - "tests/**"\n---\n\n## New Path Rule\n\nRules for tests.\n',
    )

    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(repo_root, out_dir)

    manifest = json.loads((out_dir / "praxion" / "rules_manifest.json").read_text(encoding="utf-8"))
    rule_by_path = {rule["relpath"]: rule for rule in manifest["rules"]}
    assert rule_by_path["rules/swe/new-portable-rule.md"]["codex_load"] == "always_on"
    assert rule_by_path["rules/swe/new-path-rule.md"]["codex_load"] == "path_scoped"
    assert "rules::swe::new-portable-rule" in manifest["always_on_rule_ids"]
    assert "rules::swe::new-path-rule" in manifest["path_scoped_rule_ids"]


def test_codex_metadata_can_override_automatic_classification(tmp_path: Path):
    exporter = load_exporter()
    repo_root = tmp_path / "repo"
    write_rule(
        repo_root / "rules" / "swe" / "forced-portable.md",
        "---\ncodex:\n  portability: portable\n---\n\n## Forced Portable\n\nUse opus when thinking hard.\n",
    )
    write_rule(
        repo_root / "rules" / "swe" / "forced-exclude.md",
        "---\ncodex:\n  load: exclude\n---\n\n## Forced Exclude\n\nPortable but intentionally excluded.\n",
    )

    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(repo_root, out_dir)

    manifest = json.loads((out_dir / "praxion" / "rules_manifest.json").read_text(encoding="utf-8"))
    rule_by_path = {rule["relpath"]: rule for rule in manifest["rules"]}
    assert rule_by_path["rules/swe/forced-portable.md"]["codex_portability"] == "portable"
    assert rule_by_path["rules/swe/forced-portable.md"]["codex_load"] == "always_on"
    assert rule_by_path["rules/swe/forced-exclude.md"]["codex_load"] == "exclude"
