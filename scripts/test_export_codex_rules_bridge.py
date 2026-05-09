from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER_PATH = REPO_ROOT / "codex" / "config" / "export-codex-rules-bridge.py"


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
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout) if result.stdout.strip() else {}


def write_rule(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_export_rules_bridge_writes_prefixed_hooks_and_manifest(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"

    written = exporter.export_rules_bridge(REPO_ROOT, out_dir)

    assert out_dir / "praxion" / "rules_manifest.json" in written
    assert out_dir / "hooks" / "praxion-session-start.py" in written
    assert out_dir / "hooks" / "praxion-user-prompt-submit.py" in written
    assert out_dir / "hooks" / "praxion-pre-tool-use.py" in written

    manifest = json.loads((out_dir / "praxion" / "rules_manifest.json").read_text(encoding="utf-8"))
    relpaths = {rule["relpath"] for rule in manifest["rules"]}
    assert "rules/swe/agent-behavioral-contract.md" in relpaths
    assert "rules/swe/testing-conventions.md" in relpaths
    always_on = set(manifest["always_on_rule_ids"])
    assert "rules::swe::agent-model-routing" not in always_on
    assert "rules::swe::memory-protocol" not in always_on

    registrations = json.loads((out_dir / "praxion" / "hook_registrations.json").read_text(encoding="utf-8"))
    hooks = registrations["hooks"]
    assert hooks["SessionStart"][0]["hooks"][0]["statusMessage"].startswith("Praxion:")
    assert "praxion-session-start.py" in hooks["SessionStart"][0]["hooks"][0]["command"]
    assert "git rev-parse" not in hooks["SessionStart"][0]["hooks"][0]["command"]
    assert "__PRAXION_PROJECT_ROOT__" in hooks["SessionStart"][0]["hooks"][0]["command"]
    pre_tool_matcher = hooks["PreToolUse"][0]["matcher"]
    assert pre_tool_matcher == "Edit|MultiEdit|NotebookEdit|Write"


def test_generated_hooks_route_always_on_prompt_and_path_rules(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    session_hook = out_dir / "hooks" / "praxion-session-start.py"
    prompt_hook = out_dir / "hooks" / "praxion-user-prompt-submit.py"
    pre_hook = out_dir / "hooks" / "praxion-pre-tool-use.py"

    session_output = run_hook(session_hook, {"hook_event_name": "SessionStart", "cwd": str(tmp_path)})
    session_context = session_output["hookSpecificOutput"]["additionalContext"]
    assert "rules/swe/agent-behavioral-contract.md" in session_context
    assert "rules/swe/agent-model-routing.md" not in session_context
    assert "rules/swe/memory-protocol.md" not in session_context

    prompt_output = run_hook(
        prompt_hook,
        {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "Please update the tests and pytest coverage"},
    )
    prompt_context = prompt_output["hookSpecificOutput"]["additionalContext"]
    assert "rules/swe/testing-conventions.md" in prompt_context

    prompt_path_output = run_hook(
        prompt_hook,
        {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "Edit tests/test_example.py"},
    )
    assert "rules/swe/testing-conventions.md" in prompt_path_output["hookSpecificOutput"]["additionalContext"]

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


def test_prompt_matching_avoids_generic_false_positives(tmp_path: Path):
    exporter = load_exporter()
    out_dir = tmp_path / ".codex"
    exporter.export_rules_bridge(REPO_ROOT, out_dir)

    prompt_hook = out_dir / "hooks" / "praxion-user-prompt-submit.py"
    output = run_hook(
        prompt_hook,
        {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "work on skills and agents export"},
    )
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "rules/swe/shipped-artifact-isolation.md" in context
    assert "rules/ml/eval-driven-verification.md" not in context
    assert "rules/ml/gpu-budget-conventions.md" not in context


def test_new_generic_rules_are_picked_up_automatically_without_allowlist(tmp_path: Path):
    exporter = load_exporter()
    repo_root = tmp_path / "repo"
    write_rule(
        repo_root / "rules" / "swe" / "new-portable-rule.md",
        "## New Portable Rule\n\nPortable guidance for code review.\n",
    )
    write_rule(
        repo_root / "rules" / "swe" / "new-path-rule.md",
        "---\npaths:\n  - \"tests/**\"\n---\n\n## New Path Rule\n\nRules for tests.\n",
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
