"""Starlette application with MCP server, HTTP API, and OTel relay."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from task_chronograph_mcp.events import (
    AgentStatus,
    Event,
    EventStore,
    EventType,
    Interaction,
)
from task_chronograph_mcp.file_watcher import watch_progress_file
from task_chronograph_mcp.otel_relay import OTelRelay

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8765
PORT_RANGE_SIZE = 1000  # ports 8765-9764
WATCH_DIR_ENV = "CHRONOGRAPH_WATCH_DIR"


def derive_port(project_dir: str) -> int:
    """Derive a deterministic port from the project directory path.

    Each project gets a stable port in the range 8765-9764 so multiple
    projects can run chronograph instances simultaneously without collision.
    Falls back to DEFAULT_PORT when no project directory is available.
    """
    if not project_dir:
        return DEFAULT_PORT
    import hashlib

    digest = hashlib.sha256(os.path.abspath(project_dir).encode()).digest()
    offset = int.from_bytes(digest[:2], "big") % PORT_RANGE_SIZE
    return DEFAULT_PORT + offset


mcp = FastMCP("Task Chronograph")
_store = EventStore()
_http_ready = threading.Event()


def _build_mcp_app() -> Starlette:
    """Build (or rebuild) the MCP HTTP sub-app.

    Each call creates a fresh session manager so that lifespan can be entered
    more than once (needed for tests).
    """
    mcp._session_manager = None  # noqa: SLF001 — force fresh session manager
    return mcp.streamable_http_app()


@asynccontextmanager
async def _core_lifespan(app: Starlette):
    """Reset store, start file watcher, init OTel relay, and expose to routes."""
    global _store  # noqa: PLW0603
    _store = EventStore()
    _store.set_loop(asyncio.get_running_loop())
    app.state.store = _store
    app.state.relay = OTelRelay()

    watch_dir = os.environ.get(WATCH_DIR_ENV, "")
    watcher_task: asyncio.Task | None = None
    if watch_dir:
        watch_path = Path(watch_dir)
        watcher_task = asyncio.create_task(watch_progress_file(watch_path, app.state.store))

    _http_ready.set()

    yield

    if watcher_task is not None:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass

    app.state.relay.shutdown()


@asynccontextmanager
async def app_lifespan(app: Starlette):
    """Full lifespan: core services + MCP session manager.

    Mount doesn't propagate lifespan events to sub-apps, so the MCP session
    manager must be started here.
    """
    async with _core_lifespan(app):
        async with mcp.session_manager.run():
            yield


def _relay_event(relay: OTelRelay, event: Event) -> None:
    """Route an event to the OTel relay. Fail-open: never raises."""
    try:
        match event.event_type:
            case EventType.SESSION_START:
                relay.start_session(event.session_id, event.project_dir)
            case EventType.SESSION_STOP:
                relay.end_session(event.session_id)
            case EventType.AGENT_START:
                relay.start_agent(
                    event.agent_id,
                    event.agent_type,
                    event.session_id,
                    event.parent_session_id,
                    project_dir=event.project_dir,
                )
            case EventType.AGENT_STOP:
                relay.end_agent(event.agent_id, event.message)
            case EventType.TOOL_USE:
                relay.record_tool(
                    event.agent_id,
                    event.tool_name,
                    str(event.metadata.get("input_summary", "")),
                    str(event.metadata.get("output_summary", "")),
                    is_error=False,
                    error_msg="",
                    session_id=event.session_id,
                    project_dir=event.project_dir,
                )
            case EventType.ERROR:
                relay.record_tool(
                    event.agent_id,
                    event.tool_name,
                    str(event.metadata.get("input_summary", "")),
                    "",
                    is_error=True,
                    error_msg=event.message,
                    session_id=event.session_id,
                    project_dir=event.project_dir,
                )
            case EventType.PHASE_TRANSITION:
                relay.add_phase_event(
                    event.agent_id, event.phase, event.total_phases, event.phase_name, event.message
                )
    except Exception:  # noqa: BLE001
        logger.warning("OTel relay failed for %s", event.event_type, exc_info=True)


async def receive_event(request: Request) -> JSONResponse:
    """POST /api/events -- ingest a pipeline event."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    if "event_type" not in body:
        return JSONResponse({"error": "Missing required field: event_type"}, status_code=400)

    try:
        event_type = EventType(body["event_type"])
    except ValueError:
        valid = [e.value for e in EventType]
        return JSONResponse(
            {"error": f"Invalid event_type: {body['event_type']}. Valid types: {valid}"},
            status_code=400,
        )

    event = Event(
        event_type=event_type,
        agent_type=body.get("agent_type", ""),
        session_id=body.get("session_id", ""),
        agent_id=body.get("agent_id", ""),
        parent_session_id=body.get("parent_session_id", ""),
        phase=body.get("phase", 0),
        total_phases=body.get("total_phases", 0),
        phase_name=body.get("phase_name", ""),
        status=AgentStatus(body.get("status", "running")),
        message=body.get("message", ""),
        labels=body.get("labels", {}),
        metadata=body.get("metadata", {}),
        tool_name=body.get("tool_name", ""),
        project_dir=body.get("project_dir", ""),
    )

    store: EventStore = request.app.state.store
    store.add(event)

    _relay_event(request.app.state.relay, event)

    return JSONResponse({"event_id": event.event_id}, status_code=201)


async def receive_interaction(request: Request) -> JSONResponse:
    """POST /api/interactions -- record a pipeline interaction."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    missing = [f for f in ("source", "target", "summary", "interaction_type") if f not in body]
    if missing:
        return JSONResponse(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status_code=400,
        )

    interaction = Interaction(
        source=body["source"],
        target=body["target"],
        summary=body["summary"],
        interaction_type=body["interaction_type"],
        labels=body.get("labels", {}),
    )

    store: EventStore = request.app.state.store
    interaction_id = store.add_interaction(interaction)
    return JSONResponse({"interaction_id": interaction_id}, status_code=201)


async def pipeline_state(request: Request) -> JSONResponse:
    """GET /api/state -- return full pipeline summary."""
    store: EventStore = request.app.state.store
    return JSONResponse(store.get_pipeline_summary())


async def phoenix_redirect(request: Request) -> RedirectResponse:
    """GET / -- redirect to Phoenix UI."""
    phoenix_port = os.environ.get("PHOENIX_PORT", "6006")
    return RedirectResponse(url=f"http://localhost:{phoenix_port}", status_code=302)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_pipeline_status() -> dict:
    """Get current status of all agents in the pipeline.

    Returns a summary of each agent's state including current phase,
    status (running/complete/failed), labels, delegation hierarchy,
    interaction timeline, and delegation chain.
    """
    return _store.get_pipeline_summary()


@mcp.tool()
def get_agent_events(agent_type: str, limit: int = 20, label: str = "") -> list[dict]:
    """Get recent events for a specific agent type.

    Args:
        agent_type: The agent type to query (e.g., "researcher", "systems-architect").
        limit: Maximum number of events to return (default 20).
        label: Optional label filter (e.g., "feature=auth"). Only events with matching label returned.
    """
    return _store.get_events_by_agent(agent_type, limit, label or None)


@mcp.tool()
def report_interaction(
    source: str,
    target: str,
    summary: str,
    interaction_type: str,
    labels: dict[str, str] | None = None,
) -> dict:
    """Record an interaction between pipeline participants.

    Call at key moments to build the interaction timeline:
    - "query": User asks the main agent something
    - "delegation": Main agent delegates to a subagent
    - "result": Agent returns findings to main agent
    - "decision": Main agent makes a pipeline routing decision
    - "response": Main agent responds to the user

    Delegation interactions implicitly create hierarchy links.
    Unknown types are accepted with a generic badge.

    Args:
        source: Who initiated (e.g., "user", "main_agent", "researcher").
        target: Who receives (e.g., "main_agent", "researcher", "user").
        summary: One-sentence description of what happened.
        interaction_type: One of "query", "delegation", "result", "decision", "response" (extensible).
        labels: Optional key-value annotations.
    """
    interaction = Interaction(
        source=source,
        target=target,
        summary=summary,
        interaction_type=interaction_type,
        labels=labels or {},
    )
    interaction_id = _store.add_interaction(interaction)
    return {"status": "recorded", "interaction_id": interaction_id}


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = Starlette(
    routes=[
        Route("/", phoenix_redirect, methods=["GET"]),
        Route("/api/events", receive_event, methods=["POST"]),
        Route("/api/interactions", receive_interaction, methods=["POST"]),
        Route("/api/state", pipeline_state, methods=["GET"]),
        Mount("", _build_mcp_app()),
    ],
    lifespan=app_lifespan,
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("CHRONOGRAPH_PORT", str(DEFAULT_PORT)))
    uvicorn.run(app, host="0.0.0.0", port=port)
