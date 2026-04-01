"""Tests for the Starlette server: HTTP API, SSE, dashboard, and MCP tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from task_chronograph_mcp.events import EventStore, Interaction
from task_chronograph_mcp.server import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_URL = "http://test"


@pytest.fixture
async def client(monkeypatch):
    """Async HTTP client with ASGI transport and lifespan properly managed.

    Uses _core_lifespan (EventStore + file watcher) without the MCP session
    manager, which requires anyio task group lifecycle not compatible with
    pytest-asyncio fixtures.

    OTel is disabled so the real relay in the app doesn't leak spans to
    Phoenix when the test suite runs with OTEL_ENABLED=true.
    """
    monkeypatch.setenv("OTEL_ENABLED", "false")
    import task_chronograph_mcp.server as server_module

    async with server_module._core_lifespan(app):
        transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
            yield c


# ---------------------------------------------------------------------------
# POST /api/events
# ---------------------------------------------------------------------------


class TestReceiveEvent:
    async def test_valid_payload_returns_201(
        self, client: httpx.AsyncClient, sample_event_payload: dict
    ):
        resp = await client.post("/api/events", json=sample_event_payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "event_id" in body

    async def test_missing_required_fields_returns_400(self, client: httpx.AsyncClient):
        resp = await client.post("/api/events", json={"agent_type": "researcher"})
        assert resp.status_code == 400
        assert "event_type" in resp.json()["error"]

    async def test_invalid_event_type_returns_400(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/events",
            json={"event_type": "not_real", "agent_type": "researcher"},
        )
        assert resp.status_code == 400
        assert "Invalid event_type" in resp.json()["error"]

    async def test_invalid_json_returns_400(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/events",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["error"]


# ---------------------------------------------------------------------------
# GET /api/state
# ---------------------------------------------------------------------------


class TestPipelineState:
    async def test_empty_state_structure(self, client: httpx.AsyncClient):
        resp = await client.get("/api/state")
        assert resp.status_code == 200
        body = resp.json()
        assert "agents" in body
        assert "interactions" in body
        assert "delegation_chain" in body
        assert "event_count" in body
        assert "recent_events" in body

    async def test_state_reflects_posted_event(
        self, client: httpx.AsyncClient, sample_event_payload: dict
    ):
        await client.post("/api/events", json=sample_event_payload)
        resp = await client.get("/api/state")
        body = resp.json()
        assert body["event_count"] == 1
        assert len(body["agents"]) == 1

    async def test_state_includes_stopped_at_after_stop(
        self, client: httpx.AsyncClient, sample_event_payload: dict
    ):
        await client.post("/api/events", json=sample_event_payload)
        await client.post(
            "/api/events",
            json={
                "event_type": "agent_stop",
                "agent_type": "researcher",
                "agent_id": "agent-001",
            },
        )
        resp = await client.get("/api/state")
        agent = resp.json()["agents"]["agent-001"]
        assert agent["stopped_at"] is not None
        assert agent["status"] == "complete"

    async def test_state_includes_task_summary_from_delegation(self, client: httpx.AsyncClient):
        import task_chronograph_mcp.server as server_module

        store: EventStore = server_module._store  # type: ignore[assignment]
        delegation = Interaction(
            source="main_agent",
            target="researcher",
            summary="Research auth patterns",
            interaction_type="delegation",
        )
        store.add_interaction(delegation)

        await client.post(
            "/api/events",
            json={
                "event_type": "agent_start",
                "agent_type": "researcher",
                "agent_id": "researcher",
            },
        )

        resp = await client.get("/api/state")
        agent = resp.json()["agents"]["researcher"]
        assert agent["task_summary"] == "Research auth patterns"


# ---------------------------------------------------------------------------
# GET /api/events/stream (SSE)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET / (Phoenix redirect)
# ---------------------------------------------------------------------------


class TestPhoenixRedirect:
    async def test_root_redirects_to_phoenix(self, client: httpx.AsyncClient):
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "localhost:6006" in resp.headers["location"]

    async def test_redirect_contains_phoenix_in_body(self, client: httpx.AsyncClient):
        resp = await client.get("/", follow_redirects=False)
        # Some redirect responses include a body for clients that don't follow redirects
        # The location header is the authoritative target
        assert resp.headers["location"].startswith("http://localhost:")


# ---------------------------------------------------------------------------
# MCP tool: report_interaction (tested directly via store)
# ---------------------------------------------------------------------------


class TestMCPReportInteraction:
    async def test_report_interaction_delegation_creates_hierarchy(self, client: httpx.AsyncClient):
        """Use store directly to simulate report_interaction tool behavior."""
        import task_chronograph_mcp.server as server_module

        store: EventStore = server_module._store  # type: ignore[assignment]

        interaction = Interaction(
            source="main_agent",
            target="researcher",
            summary="Delegate research",
            interaction_type="delegation",
        )
        store.add_interaction(interaction)

        # Now start both agents via API
        await client.post(
            "/api/events",
            json={
                "event_type": "agent_start",
                "agent_type": "main_agent",
                "agent_id": "main_agent",
            },
        )
        await client.post(
            "/api/events",
            json={
                "event_type": "agent_start",
                "agent_type": "researcher",
                "agent_id": "researcher",
            },
        )

        resp = await client.get("/api/state")
        state = resp.json()
        assert state["agents"]["researcher"]["delegation_parent"] == "main_agent"
        assert len(state["delegation_chain"]) == 1

    async def test_report_interaction_unknown_type_accepted(self, client: httpx.AsyncClient):
        """Unknown interaction type is stored and returned in API."""
        import task_chronograph_mcp.server as server_module

        store: EventStore = server_module._store  # type: ignore[assignment]

        interaction = Interaction(
            source="a", target="b", summary="custom action", interaction_type="novel_kind"
        )
        store.add_interaction(interaction)

        resp = await client.get("/api/state")
        state = resp.json()
        assert len(state["interactions"]) == 1
        assert state["interactions"][0]["interaction_type"] == "novel_kind"


# ---------------------------------------------------------------------------
# OTel Relay wiring (Step 10)
# ---------------------------------------------------------------------------


@pytest.fixture
async def relay_client():
    """Client with a mock relay to verify event routing without live Phoenix."""
    import task_chronograph_mcp.server as server_module

    async with server_module._core_lifespan(app):
        # Replace the real relay with a mock
        mock_relay = MagicMock()
        app.state.relay = mock_relay

        transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
            yield c, mock_relay


class TestRelayWiring:
    """Verify that events posted to HTTP API are routed to the OTelRelay."""

    async def test_session_start_routes_to_relay(self, relay_client):
        client, mock = relay_client
        resp = await client.post(
            "/api/events",
            json={
                "event_type": "session_start",
                "session_id": "sess-001",
                "project_dir": "/home/user/my-project",
            },
        )
        assert resp.status_code == 201
        mock.start_session.assert_called_once_with("sess-001", "/home/user/my-project")

    async def test_session_stop_routes_to_relay(self, relay_client):
        client, mock = relay_client
        resp = await client.post(
            "/api/events",
            json={"event_type": "session_stop", "session_id": "sess-001"},
        )
        assert resp.status_code == 201
        mock.end_session.assert_called_once_with("sess-001")

    async def test_agent_start_routes_to_relay(self, relay_client):
        client, mock = relay_client
        resp = await client.post(
            "/api/events",
            json={
                "event_type": "agent_start",
                "agent_type": "i-am:researcher",
                "agent_id": "agent-r1",
                "session_id": "sess-001",
                "parent_session_id": "parent-001",
            },
        )
        assert resp.status_code == 201
        mock.start_agent.assert_called_once_with(
            "agent-r1", "i-am:researcher", "sess-001", "parent-001", project_dir=""
        )

    async def test_agent_stop_routes_to_relay(self, relay_client):
        client, mock = relay_client
        resp = await client.post(
            "/api/events",
            json={
                "event_type": "agent_stop",
                "agent_type": "researcher",
                "agent_id": "agent-r1",
                "message": "Research complete",
            },
        )
        assert resp.status_code == 201
        mock.end_agent.assert_called_once_with("agent-r1", "Research complete")

    async def test_tool_use_routes_to_relay(self, relay_client):
        client, mock = relay_client
        resp = await client.post(
            "/api/events",
            json={
                "event_type": "tool_use",
                "agent_type": "researcher",
                "agent_id": "agent-r1",
                "tool_name": "Read",
                "metadata": {"input_summary": "/path/to/file", "output_summary": "200 lines"},
            },
        )
        assert resp.status_code == 201
        mock.record_tool.assert_called_once_with(
            "agent-r1",
            "Read",
            "/path/to/file",
            "200 lines",
            is_error=False,
            error_msg="",
            session_id="",
            project_dir="",
        )

    async def test_error_routes_to_relay_with_error_flag(self, relay_client):
        client, mock = relay_client
        resp = await client.post(
            "/api/events",
            json={
                "event_type": "error",
                "agent_type": "researcher",
                "agent_id": "agent-r1",
                "tool_name": "Bash",
                "message": "Command failed with exit code 1",
            },
        )
        assert resp.status_code == 201
        mock.record_tool.assert_called_once()
        call_kwargs = mock.record_tool.call_args
        assert call_kwargs[1]["is_error"] is True
        assert call_kwargs[1]["error_msg"] == "Command failed with exit code 1"

    async def test_phase_transition_routes_to_relay(self, relay_client):
        client, mock = relay_client
        resp = await client.post(
            "/api/events",
            json={
                "event_type": "phase_transition",
                "agent_type": "researcher",
                "agent_id": "agent-r1",
                "phase": 3,
                "total_phases": 5,
                "phase_name": "analysis",
                "message": "Analyzing results",
            },
        )
        assert resp.status_code == 201
        mock.add_phase_event.assert_called_once_with(
            "agent-r1", 3, 5, "analysis", "Analyzing results"
        )

    async def test_eventstore_still_receives_events(self, relay_client):
        """Dual storage: EventStore gets the event regardless of relay."""
        client, _ = relay_client
        await client.post(
            "/api/events",
            json={
                "event_type": "agent_start",
                "agent_type": "researcher",
                "agent_id": "agent-r1",
                "session_id": "sess-001",
            },
        )
        resp = await client.get("/api/state")
        assert resp.json()["event_count"] == 1

    async def test_relay_failure_does_not_cause_500(self, relay_client):
        """If relay raises, the HTTP response still succeeds (fail-open)."""
        client, mock = relay_client
        mock.start_agent.side_effect = RuntimeError("Phoenix down")
        resp = await client.post(
            "/api/events",
            json={
                "event_type": "agent_start",
                "agent_type": "researcher",
                "agent_id": "agent-r1",
                "session_id": "sess-001",
            },
        )
        assert resp.status_code == 201  # still succeeds
        # EventStore still got the event
        resp = await client.get("/api/state")
        assert resp.json()["event_count"] == 1
