"""Shared test infrastructure for the ``eval`` package's pytest suite.

``fake_claude`` is the one fixture every paid-path test needs: a stand-in
``claude`` executable on a temporary ``PATH``, modelled on the pattern
already used for the subprocess boundary in ``test_live_session.py``
(``_stand_in_env``), generalized to answer every one of the nine seeded
scenarios plus the isolation preflight, so ``cli.main()`` can be driven
end-to-end without ever starting a real, API-metered session. It never
calls any network API and asserts nothing itself — it only emits
stream-json events, mirroring the shapes recorded in
``fixtures/live_scenarios/*.stream.jsonl``.

Per-test behavior is controlled through a small JSON "control" file the
fake process reads on every invocation (``FakeClaude.configure(...)``),
never through Python closures — the fake runs in a separate process, so
closures cannot cross that boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# The fake `claude` process
# ---------------------------------------------------------------------------

_FAKE_CLAUDE_SOURCE = r"""
import json, os, re, subprocess, sys
from pathlib import Path


def arg(flag):
    a = sys.argv
    return a[a.index(flag) + 1] if flag in a else None


prompt = arg("-p") or ""
plugin_dir = arg("--plugin-dir")
schema = arg("--json-schema")
config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "")
control_path = os.environ.get("FAKE_CLAUDE_CONTROL")
control = json.loads(Path(control_path).read_text()) if control_path and Path(control_path).exists() else {}
log_path = os.environ.get("FAKE_CLAUDE_LOG")

mutate_relpath = control.get("mutate_copy_relpath")
if mutate_relpath and plugin_dir:
    target = Path(plugin_dir) / mutate_relpath
    target.chmod(0o644)
    target.write_text(target.read_text(encoding="utf-8") + "\nFAKE-CLAUDE-MUTATION\n", encoding="utf-8")

events = [{
    "type": "system", "subtype": "init", "model": "claude-opus-5-5",
    "plugins": [
        {"name": "praxion", "source": "praxion@inline", "path": plugin_dir},
        {"name": "agents-md", "source": "agents-md@builtin", "path": "builtin"},
    ],
    "mcp_servers": [], "apiKeySource": "ANTHROPIC_API_KEY",
    "claude_code_version": "fake-test", "cwd": os.getcwd(),
}]
if control.get("preflight_breach") and "reply with nothing but every marker" in prompt.lower():
    events[0]["plugins"].append(
        {"name": "rogue", "source": "rogue@marketplace", "path": "/somewhere/else"}
    )

result = {
    "type": "result", "subtype": "success", "is_error": False, "result": "",
    "total_cost_usd": 0.25, "session_id": "fake-session", "num_turns": 2,
    "duration_ms": 1000,
    "usage": {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 0},
    "permission_denials": [],
}


def tool_use(tid, name, inp, parent=None, subagent_type=None):
    ev = {"type": "assistant", "parent_tool_use_id": parent,
          "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}
    if subagent_type:
        ev["subagent_type"] = subagent_type
    return ev


scenario = "lightweight-fix"
if "reply with nothing but every marker" in prompt.lower():
    scenario = "preflight"
    found = set()
    pattern = re.compile(r"PRXLIVE-[A-Z]+-[0-9a-f]{8}")
    for base in (Path(config_dir), Path(plugin_dir or ".")):
        if base.is_dir():
            for md in base.rglob("*.md"):
                try:
                    found |= set(pattern.findall(md.read_text(encoding="utf-8")))
                except OSError:
                    pass
    result["result"] = "\n".join(sorted(found))
elif schema is not None:
    task = prompt.split("Task:", 1)[-1]
    case = (
        "lightweight" if "Rename" in task
        else "standard" if "REST" in task
        else "full" if "Migrate" in task
        else "spike" if "Investigate" in task
        else "direct"
    )
    answers = {
        "direct": {"tier": "Direct", "agents": []},
        "lightweight": {"tier": "Lightweight", "agents": []},
        "spike": {"tier": "Spike", "agents": ["praxion:researcher"]},
        "standard": {
            "tier": "Standard",
            "agents": [
                "praxion:researcher", "praxion:systems-architect",
                "praxion:implementation-planner", "praxion:implementer",
                "praxion:test-engineer", "praxion:verifier",
            ],
        },
        "full": {
            "tier": "Full",
            "agents": [
                "praxion:researcher", "praxion:systems-architect", "praxion:interface-designer",
                "praxion:implementation-planner", "praxion:implementer", "praxion:test-engineer",
                "praxion:verifier", "praxion:doc-engineer", "praxion:context-engineer",
            ],
        },
    }
    override = (control.get("spawn_overrides") or {}).get(case)
    if override == "error":
        result.update(subtype="error_during_execution", is_error=True, result="simulated overload")
    elif override == "fail":
        result["structured_output"] = {"tier": "Direct", "agents": []}
    else:
        result["structured_output"] = answers[case]
    scenario = f"spawn-selection:{case}"
elif "Spawn exactly one" in prompt:
    scenario = "ui-step"
    events.append(tool_use("toolu_A", "Agent", {"subagent_type": "praxion:implementer"}))
    events.append({
        "type": "assistant", "parent_tool_use_id": "toolu_A", "subagent_type": "praxion:implementer",
        "message": {"content": [
            {"type": "text", "text": "Per web-ui-design: skeleton loader, five UI states."}
        ]},
    })
elif "Record the following decision" in prompt:
    scenario = "adr-authoring"
    drafts = Path(".ai-state/decisions/drafts")
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "20260924-0000-x-main-slug.md").write_text(
        "---\nid: dec-draft-00000000\n---\nbody\n",  # id-citation-discipline:ignore
        encoding="utf-8",
    )
elif "Commit it." in prompt:
    scenario = "commit-staging"
    command = control.get(
        "commit_command", "git add scripts/foo.py scripts/test_foo.py && git commit -q -m 'Fix typo'"
    )
    subprocess.run(command, shell=True, check=True)
    events.append(tool_use("toolu_B", "Bash", {"command": command}))
else:
    target = Path("scripts/paginate.py")
    if target.exists():
        target.write_text(target.read_text(encoding="utf-8") + "# fixed\n", encoding="utf-8")

if control.get("judge_overload"):
    pass  # judge exceptions are injected in-process; the fake process is not involved

events.append(result)
if log_path:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"scenario": scenario}) + "\n")
print("\n".join(json.dumps(e) for e in events))
"""


@dataclass
class FakeClaude:
    """Handle returned by the ``fake_claude`` fixture."""

    control_path: Path
    log_path: Path

    def configure(self, **control: object) -> None:
        """Write the per-test control file the fake process reads on every call."""
        self.control_path.write_text(json.dumps(control), encoding="utf-8")

    def calls(self) -> list[dict[str, object]]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines() if line.strip()]


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeClaude:
    """A stand-in ``claude`` on a temp ``PATH`` — never starts a real session.

    Mirrors ``test_live_session.py``'s ``_stand_in_env`` pattern: the bare
    command name ``claude`` (``session.CLAUDE_BINARY``, untouched) resolves
    through the built session env's own ``PATH``, which always reads from
    ``os.environ`` at call time — so patching the test process's ``PATH``
    here reaches every session the run launches.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text(f"#!{sys.executable}\n{_FAKE_CLAUDE_SOURCE}", encoding="utf-8")
    claude.chmod(0o755)

    control_path = tmp_path / "fake_claude_control.json"
    log_path = tmp_path / "fake_claude_calls.log"
    control_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-test-not-a-real-key")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("FAKE_CLAUDE_CONTROL", str(control_path))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log_path))
    return FakeClaude(control_path=control_path, log_path=log_path)


@pytest.fixture
def repo_root() -> Path:
    """This checkout's top-level directory — read-only for every consumer."""
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
