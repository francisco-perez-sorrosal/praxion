"""Driver that serves this repository through the dashboard and fetches what it shows.

Starts the dashboard's development server from `dashboard_app/` (the documented
development launch: `PRAXION_PROJECT_ROOT=<project> next dev`) on a free local port,
pointed at this repository, waits until the architecture page answers, and stops
the server's whole process group afterwards, restoring the one tracked file the
development server rewrites (`next-env.d.ts`). Requires the dashboard's dependencies
(`dashboard_app/node_modules`); without them a scenario is skipped, not failed.

Isolation: no inherited `CLAUDE*`/`PRAXION_*` variables besides the project root,
telemetry off, the server bound to 127.0.0.1.
"""

from __future__ import annotations

import fcntl
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = REPO_ROOT / "dashboard_app"
NEXT_BIN = APP_DIR / "node_modules" / ".bin" / "next"
# `next dev` rewrites this tracked file on start; it is restored so a run leaves no trace.
NEXT_ENV_TYPES = APP_DIR / "next-env.d.ts"
STARTUP_TIMEOUT_SECONDS = 240


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: str


@dataclass(frozen=True)
class Dashboard:
    base_url: str

    def get(self, path: str) -> Response:
        try:
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=180) as reply:
                return Response(
                    reply.status,
                    reply.headers.get("Content-Type", ""),
                    reply.read().decode("utf-8", "replace"),
                )
        except urllib.error.HTTPError as error:
            return Response(
                error.code,
                error.headers.get("Content-Type", ""),
                error.read().decode("utf-8", "replace"),
            )

    def diagram(self, relative_path: str) -> Response:
        return self.get(f"/api/diagram?path={urllib.parse.quote(relative_path)}")


@contextmanager
def running_dashboard(project: Path = REPO_ROOT) -> Iterator[Dashboard]:
    if not NEXT_BIN.exists():
        pytest.skip(
            "dashboard dependencies are not installed (run `pnpm install` in dashboard_app/)"
        )
    # One development server per app directory at a time: concurrent `next dev`
    # processes share `dashboard_app/.next/` and break each other, so parallel test
    # workers queue on a lock for the server's whole lifetime.
    lock_path = Path(tempfile.gettempdir()) / "praxion-dashboard-e2e.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original_types = NEXT_ENV_TYPES.read_bytes() if NEXT_ENV_TYPES.exists() else None
        try:
            yield from _serve(project)
        finally:
            if original_types is not None:
                NEXT_ENV_TYPES.write_bytes(original_types)


def _serve(project: Path) -> Iterator[Dashboard]:
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_"))}
    env.update(
        {"PRAXION_PROJECT_ROOT": str(project), "NEXT_TELEMETRY_DISABLED": "1", "PORT": str(port)}
    )
    server = subprocess.Popen(
        [str(NEXT_BIN), "dev", "--hostname", "127.0.0.1", "--port", str(port)],
        cwd=APP_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        dashboard = Dashboard(f"http://127.0.0.1:{port}")
        _wait_until_ready(dashboard, server)
        yield dashboard
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(server.pid, signal.SIGKILL)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_ready(dashboard: Dashboard, server: subprocess.Popen) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise AssertionError(
                f"the dashboard server exited with {server.returncode} before answering"
            )
        try:
            if dashboard.get("/architecture").status < 500:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(1)
    raise AssertionError(f"the dashboard did not answer within {STARTUP_TIMEOUT_SECONDS}s")
