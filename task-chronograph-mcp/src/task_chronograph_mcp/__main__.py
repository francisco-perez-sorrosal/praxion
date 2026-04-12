"""Hybrid stdio+HTTP entry point: MCP tools over stdio, HTTP API in daemon thread.

The plugin system auto-registers this as a stdio MCP server. On startup, the
HTTP server (REST API for hook event ingestion + OTel relay) launches in a
daemon thread. The root route redirects to Phoenix UI at localhost:6006.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading

import uvicorn

from task_chronograph_mcp.server import _http_ready, app, derive_port, mcp


def _resolve_project_root(cwd: str) -> str:
    """Resolve the main repo root when running inside a git worktree.

    Must match the logic in hooks/send_event.py:_resolve_project_root().
    """
    if not cwd:
        return cwd
    try:
        common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=cwd,
            timeout=2,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        abs_common = os.path.normpath(os.path.join(cwd, common))
        if os.path.basename(abs_common) == ".git":
            return os.path.dirname(abs_common)
        return cwd
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return cwd


def _run_http_server(port: int) -> None:
    """Run the Starlette app (API + OTel relay) in its own event loop."""
    try:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
    except OSError as e:
        sys.stderr.write(
            f"Task Chronograph: HTTP port {port} unavailable ({e}). "
            "Hook events will go to the existing chronograph instance.\n"
        )


# Derive port: explicit env var > project-based derivation > default
if os.environ.get("CHRONOGRAPH_PORT"):
    port = int(os.environ["CHRONOGRAPH_PORT"])
else:
    port = derive_port(_resolve_project_root(os.getcwd()))

http_thread = threading.Thread(
    target=_run_http_server,
    args=(port,),
    daemon=True,
    name="chronograph-http",
)
http_thread.start()

if _http_ready.wait(timeout=5):
    sys.stderr.write(f"Task Chronograph: http://127.0.0.1:{port} (Phoenix UI at localhost:6006)\n")
else:
    sys.stderr.write("Task Chronograph: HTTP server failed to start\n")

mcp.run()
