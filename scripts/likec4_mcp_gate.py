"""Start the plugin's `likec4` MCP server only where it has a model to serve.

The LikeC4 server reads one workspace, `LIKEC4_WORKSPACE` (the plugin sets `docs/diagrams/`)
under the project directory. Where that workspace holds no `.c4` source the server answers
every query with nothing, yet Claude Code would still put its instructions and the names of
its twenty tools into every session. Measured 2026-11-11 with the free token counter: about
1,330 tokens of instructions and about 460 of tool names.

So this launcher, which the plugin registers as the `likec4` server:

- runs `npx -y @likec4/mcp`, exactly the command the plugin ran before, when the workspace
  holds a `.c4` file;
- otherwise answers MCP itself as a server with no instructions and no tools, so the session
  sees a connected server that costs nothing, never a failed one.

A project that adds its first `.c4` source gets the real server from its next session; the
`likec4-diagramming` skill already reads `.c4` files directly when the server is absent.

The project directory is `CLAUDE_PROJECT_DIR`, which Claude Code exports to stdio MCP
servers, else the working directory. Stdlib-only, and in syntax Python 3.7 reads, because it
runs under whichever `python3` is first on the user's PATH. Not executable, so the installer
never links it onto PATH; the plugin runs it as `python3 <path>`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping

DEFAULT_WORKSPACE = "docs/diagrams/"
SERVER_COMMAND = ("npx", "-y", "@likec4/mcp")
# Directories that never hold a project's own model, and can be large.
_SKIPPED_DIRS = frozenset({".git", "node_modules", ".venv", "__pycache__"})
_METHOD_NOT_FOUND = -32601
_FALLBACK_PROTOCOL = "2025-06-18"


def main() -> int:
    """Run the real server where the workspace holds a model, else the empty one."""
    if workspace_has_model(workspace_dir(os.environ)):
        return run_server(SERVER_COMMAND)
    serve_empty(sys.stdin, sys.stdout)
    return 0


def workspace_dir(environ: Mapping[str, str]) -> str:
    """The directory the LikeC4 server would read: its workspace under the project directory."""
    project = environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    workspace = environ.get("LIKEC4_WORKSPACE") or DEFAULT_WORKSPACE
    return os.path.join(project, workspace)


def workspace_has_model(directory: str) -> bool:
    """True when `directory` holds at least one `.c4` file, at any depth."""
    for _root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in _SKIPPED_DIRS]
        if any(name.endswith(".c4") for name in files):
            return True
    return False


def run_server(command: tuple[str, ...]) -> int:
    """Hand the session's stdio to the real server and return its exit status."""
    program = shutil.which(command[0])
    if program is None:
        sys.stderr.write(f"likec4: {command[0]} not found on PATH\n")
        return 1
    if os.name == "posix":
        os.execv(program, [program, *command[1:]])
    return subprocess.call([program, *command[1:]])


def serve_empty(stdin, stdout) -> None:
    """Answer MCP over newline-delimited JSON-RPC as a server with nothing to offer."""
    for line in stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue  # a notification: nothing to answer
        stdout.write(json.dumps(reply(message)) + "\n")
        stdout.flush()


def reply(request: dict) -> dict:
    """The response to one request: an empty server's answer, or method-not-found."""
    method = request.get("method")
    if method == "initialize":
        params = request.get("params") or {}
        result = {
            "protocolVersion": params.get("protocolVersion") or _FALLBACK_PROTOCOL,
            "capabilities": {},
            "serverInfo": {"name": "likec4", "version": "0"},
        }
    elif method == "tools/list":
        result = {"tools": []}
    elif method == "ping":
        result = {}
    else:
        error = {"code": _METHOD_NOT_FOUND, "message": f"Method not found: {method}"}
        return {"jsonrpc": "2.0", "id": request["id"], "error": error}
    return {"jsonrpc": "2.0", "id": request["id"], "result": result}


if __name__ == "__main__":
    sys.exit(main())
