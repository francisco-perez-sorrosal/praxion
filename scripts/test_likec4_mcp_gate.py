"""Tests for likec4_mcp_gate.py -- the plugin's `likec4` MCP server runs only where it has a model.

The LikeC4 server reads one workspace, `LIKEC4_WORKSPACE` under the project directory. Where
that workspace holds no `.c4` source it serves nothing, yet its instructions and tool names
would reach every session. Each scenario starts the gate as Claude Code starts a stdio MCP
server, speaks MCP to it over stdin and stdout, and puts a stand-in `npx` first on PATH so the
real server is never fetched.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "likec4_mcp_gate.py"
PLUGIN_JSON = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
WORKSPACE = "docs/diagrams/"

# A stand-in `npx` that answers like the real LikeC4 server, so a test can tell which one ran.
_FAKE_NPX = """#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("id") is None:
        continue
    if message["method"] == "initialize":
        result = {"protocolVersion": message["params"]["protocolVersion"], "capabilities": {"tools": {}},
                  "serverInfo": {"name": "likec4-standin", "version": "0"},
                  "instructions": "STANDIN " + " ".join(sys.argv[1:])}
    else:
        result = {"tools": [{"name": "list-projects", "inputSchema": {"type": "object"}}]}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""


def _project(tmp_path: Path, *, sources: dict[str, str] | None = None) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    for relative, text in (sources or {}).items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return project


def _env(tmp_path: Path, project: Path | None, **extra: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    npx = bin_dir / "npx"
    npx.write_text(_FAKE_NPX, encoding="utf-8")
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["LIKEC4_WORKSPACE"] = WORKSPACE
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    env.update(extra)
    return env


def _talk(env: dict[str, str], cwd: Path) -> tuple[dict, dict]:
    """Initialize the server and list its tools, as an MCP client does at session start."""
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]  # fmt: skip
    stdin = "".join(json.dumps(r) + "\n" for r in requests)
    done = subprocess.run(
        [sys.executable, str(SCRIPT)], input=stdin, capture_output=True, text=True,
        env=env, cwd=cwd, timeout=60,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    replies = {m["id"]: m for m in map(json.loads, done.stdout.splitlines()) if "id" in m}
    return replies[1]["result"], replies[2]["result"]


def test_no_model_in_the_workspace_serves_no_instructions_and_no_tools(tmp_path: Path) -> None:
    project = _project(tmp_path, sources={"README.md": "no diagrams here\n"})
    init, tools = _talk(_env(tmp_path, project), project)
    assert not init.get("instructions")
    assert tools == {"tools": []}


def test_a_model_in_the_workspace_runs_the_likec4_server(tmp_path: Path) -> None:
    project = _project(tmp_path, sources={"docs/diagrams/arch/src/arch.c4": "model {}\n"})
    init, tools = _talk(_env(tmp_path, project), project)
    assert init["instructions"] == "STANDIN -y @likec4/mcp"
    assert [t["name"] for t in tools["tools"]] == ["list-projects"]


def test_a_model_outside_the_workspace_does_not_count(tmp_path: Path) -> None:
    project = _project(tmp_path, sources={"tests/fixtures/minimal.c4": "model {}\n"})
    init, tools = _talk(_env(tmp_path, project), project)
    assert not init.get("instructions")
    assert tools == {"tools": []}


def test_the_workspace_is_the_one_the_server_is_given(tmp_path: Path) -> None:
    project = _project(tmp_path, sources={"arch/model.c4": "model {}\n"})
    init, _ = _talk(_env(tmp_path, project, LIKEC4_WORKSPACE="arch"), project)
    assert init["instructions"] == "STANDIN -y @likec4/mcp"


def test_without_a_project_directory_the_working_directory_is_the_project(tmp_path: Path) -> None:
    project = _project(tmp_path, sources={"docs/diagrams/a.c4": "model {}\n"})
    init, _ = _talk(_env(tmp_path, None), project)
    assert init["instructions"] == "STANDIN -y @likec4/mcp"


def test_the_empty_server_answers_a_ping_and_rejects_an_unknown_method(tmp_path: Path) -> None:
    project = _project(tmp_path)
    stdin = "".join(
        json.dumps(r) + "\n"
        for r in (
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
            {"jsonrpc": "2.0", "id": 8, "method": "resources/list"},
        )
    )
    done = subprocess.run(
        [sys.executable, str(SCRIPT)], input=stdin, capture_output=True, text=True,
        env=_env(tmp_path, project), cwd=project, timeout=60,
    )  # fmt: skip
    replies = {m["id"]: m for m in map(json.loads, done.stdout.splitlines())}
    assert replies[7]["result"] == {}
    assert replies[8]["error"]["code"] == -32601


@pytest.mark.parametrize("field", ["command", "args", "env"])
def test_the_plugin_starts_likec4_through_the_gate(field: str) -> None:
    server = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["mcpServers"]["likec4"]
    expected = {
        "command": "python3",
        "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/likec4_mcp_gate.py"],
        "env": {"LIKEC4_WORKSPACE": WORKSPACE},
    }
    assert server[field] == expected[field]


def test_the_gate_never_reaches_the_path() -> None:
    assert not os.access(SCRIPT, os.X_OK), "an executable script under scripts/ is linked onto PATH"
