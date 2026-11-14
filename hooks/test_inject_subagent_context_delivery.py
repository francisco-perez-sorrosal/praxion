"""Tests for the skill delivery's trailing segment in ``hooks/inject_subagent_context.py``.

The emitter runs as the harness runs it, a separate process with ``CLAUDE_PLUGIN_ROOT`` naming an
installation, here a small plugin built in ``tmp_path``. A served delivery appends the skill's
block after the delegation, a failed one appends the notice, and neither ever refuses the spawn.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
HOOK = "inject_subagent_context.py"
MARKED = "Extract the pricing rules into their own module. [Phase: Refactoring]"
UNMARKED = "Write the pricing rules module."
BODY = "\n# Refactoring\n\nRestructure in small, safe steps.\n"
SKILL_HEADER = "---\nname: refactoring\ndescription: Pragmatic refactoring.\n---\n"
BLOCK_LABEL = "[Skill delivery: refactoring "
NOTICE_LABEL = "[Skill delivery failed: refactoring (skill-unreadable)]"
TIMING_BOUND_MS = 2000
LARGE_BODY_BYTES = 12 * 1024


def _plugin(root: Path, *, preloads: bool = False, body: str = BODY) -> Path:
    """An installation whose implementer definition preloads the skill or not."""
    skills = "[python-development, refactoring]" if preloads else "[python-development]"
    (root / "agents").mkdir(parents=True)
    (root / "agents" / "implementer.md").write_text(
        f"---\nname: implementer\nskills: {skills}\n---\nThe definition.\n", encoding="utf-8"
    )
    skill = root / "skills" / "refactoring"
    (skill / "references").mkdir(parents=True)
    (skill / "references" / "patterns.md").write_text("# Patterns\n", encoding="utf-8")
    (skill / "SKILL.md").write_text(SKILL_HEADER + body, encoding="utf-8")
    return root


def _hooks_without_delivery(dest: Path) -> Path:
    """A copy of the hooks directory with the delivery module removed, as a partial install."""
    shutil.copytree(
        HOOKS_DIR,
        dest,
        ignore=shutil.ignore_patterns("test_*", "__pycache__", "_skill_delivery.py"),
    )
    return dest


def _payload(prompt: str, cwd: Path, subagent_type: str = "praxion:implementer") -> str:
    tool_input = {"subagent_type": subagent_type, "prompt": prompt, "description": "work"}
    return json.dumps(
        {
            "tool_name": "Agent",
            "tool_input": tool_input,
            "cwd": str(cwd),
            "session_id": "delivery-segment-session",
            "tool_use_id": "toolu_delivery_segment",
        }
    )


def _run(
    stdin: str, plugin: Path, cwd: Path, hooks_dir: Path = HOOKS_DIR
) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PRAXION_")}
    env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
    return subprocess.run(
        [sys.executable, str(hooks_dir / HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=10,
    )


def _prompt_of(result: subprocess.CompletedProcess) -> str:
    return json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["prompt"]


def _decision_of(result: subprocess.CompletedProcess) -> str:
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_a_served_delivery_appends_the_block_after_the_verbatim_delegation(tmp_path):
    plugin = _plugin(tmp_path / "plugin")

    result = _run(_payload(MARKED, tmp_path), plugin, tmp_path)

    delegation, block = _prompt_of(result).split("\n\n", 1)
    assert delegation == MARKED
    assert block.startswith(BLOCK_LABEL)
    assert BODY in block


def test_a_failed_delivery_appends_the_notice_and_still_allows_the_spawn(tmp_path):
    plugin = _plugin(tmp_path / "plugin")
    (plugin / "skills" / "refactoring" / "SKILL.md").unlink()

    result = _run(_payload(MARKED, tmp_path), plugin, tmp_path)

    assert result.returncode == 0
    assert _decision_of(result) == "allow"
    delegation, notice = _prompt_of(result).split("\n\n", 1)
    assert delegation == MARKED
    assert notice.startswith(NOTICE_LABEL)
    assert str((plugin / "skills" / "refactoring" / "SKILL.md").resolve()) in notice


def test_a_definition_that_preloads_the_skill_adds_nothing(tmp_path):
    plugin = _plugin(tmp_path / "plugin", preloads=True)

    result = _run(_payload(MARKED, tmp_path), plugin, tmp_path)

    assert result.returncode == 0
    assert result.stdout == ""


def test_an_unmarked_delegation_adds_nothing(tmp_path):
    plugin = _plugin(tmp_path / "plugin")

    result = _run(_payload(UNMARKED, tmp_path), plugin, tmp_path)

    assert result.stdout == ""


def test_a_malformed_tool_input_prints_nothing_and_exits_zero(tmp_path):
    plugin = _plugin(tmp_path / "plugin")
    stdin = json.dumps({"tool_name": "Agent", "tool_input": ["not", "an", "object"]})

    result = _run(stdin, plugin, tmp_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


def test_without_the_delivery_module_the_leading_segments_still_emit(tmp_path):
    hooks = _hooks_without_delivery(tmp_path / "partial" / "hooks")
    plugin = _plugin(tmp_path / "plugin")
    project = tmp_path / "project"
    (project / ".ai-state").mkdir(parents=True)
    briefed = "/elsewhere/.claude/worktrees/feature-x"
    prompt = f"Work under {briefed} only: {MARKED}"

    result = _run(_payload(prompt, project, "Explore"), plugin, project, hooks)

    rewritten = _prompt_of(result)
    assert rewritten.startswith("[Praxion process active]")
    assert f"[Worktree briefing] This prompt names `{briefed}`" in rewritten
    assert rewritten.endswith(prompt)


def test_without_the_delivery_module_a_marked_spawn_gets_nothing_and_a_stderr_line(tmp_path):
    hooks = _hooks_without_delivery(tmp_path / "partial" / "hooks")
    plugin = _plugin(tmp_path / "plugin")

    result = _run(_payload(MARKED, tmp_path), plugin, tmp_path, hooks)

    assert result.returncode == 0
    assert result.stdout == ""
    assert "skill delivery unavailable: ModuleNotFoundError" in result.stderr


def test_a_served_delivery_of_a_12_kb_skill_completes_within_the_timing_bound(tmp_path):
    line = "Keep each refactoring commit structure-only, with every test green before and after.\n"
    body = BODY + line * (LARGE_BODY_BYTES // len(line) + 1)
    plugin = _plugin(tmp_path / "plugin", body=body)
    stdin = _payload(MARKED, tmp_path)

    started = time.perf_counter()
    result = _run(stdin, plugin, tmp_path)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert body in _prompt_of(result), "the 12 KB body was not delivered whole"
    assert elapsed_ms < TIMING_BOUND_MS, f"a served delivery took {elapsed_ms:.0f} ms"
