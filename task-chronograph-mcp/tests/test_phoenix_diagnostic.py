"""Diagnostic test: exercise OTelRelay against real Phoenix to find tracing issues.

Run with: OTEL_ENABLED=true uv run python -m pytest tests/test_phoenix_diagnostic.py -v -s
Requires Phoenix running on localhost:6006.
"""

from __future__ import annotations

import json
import time
import urllib.request
import uuid

import pytest

from task_chronograph_mcp.otel_relay import OTelRelay

PHOENIX_GQL = "http://localhost:6006/graphql"
PHOENIX_TRACES = "http://localhost:6006/v1/traces"


def _gql(query: str) -> dict:
    """Run a GraphQL query against Phoenix."""
    req = urllib.request.Request(
        PHOENIX_GQL,
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _phoenix_available() -> bool:
    try:
        _gql("{ projects { edges { node { name } } } }")
        return True
    except Exception:
        return False


def _get_spans_for_project(project_name: str) -> list[dict]:
    """Fetch all spans for a project from Phoenix."""
    # First find the project ID
    result = _gql("{ projects { edges { node { name id } } } }")
    project_id = None
    for edge in result["data"]["projects"]["edges"]:
        if edge["node"]["name"] == project_name:
            project_id = edge["node"]["id"]
            break
    if not project_id:
        return []

    # Fetch spans
    result = _gql(f"""{{
        node(id: "{project_id}") {{
            ... on Project {{
                spans(first: 100) {{
                    edges {{
                        node {{
                            name
                            spanKind
                            context {{ traceId spanId }}
                            parentId
                            startTime
                            endTime
                            statusCode
                        }}
                    }}
                }}
            }}
        }}
    }}""")
    return [e["node"] for e in result["data"]["node"]["spans"]["edges"]]


def _get_sessions_for_project(project_name: str) -> list[dict]:
    """Fetch sessions for a project from Phoenix."""
    result = _gql("{ projects { edges { node { name id } } } }")
    project_id = None
    for edge in result["data"]["projects"]["edges"]:
        if edge["node"]["name"] == project_name:
            project_id = edge["node"]["id"]
            break
    if not project_id:
        return []

    result = _gql(f"""{{
        node(id: "{project_id}") {{
            ... on Project {{
                sessions(first: 100) {{
                    edges {{
                        node {{
                            sessionId
                            numTraces
                            startTime
                            endTime
                        }}
                    }}
                }}
            }}
        }}
    }}""")
    return [e["node"] for e in result["data"]["node"]["sessions"]["edges"]]


def _delete_project(project_name: str) -> None:
    """Delete a Phoenix project by name. Silently ignores missing projects."""
    try:
        result = _gql("{ projects { edges { node { name id } } } }")
        for edge in result["data"]["projects"]["edges"]:
            if edge["node"]["name"] == project_name:
                pid = edge["node"]["id"]
                _gql(f'mutation {{ deleteProject(id: "{pid}") {{ __typename }} }}')
                return
    except Exception:
        pass


@pytest.fixture
def unique_project():
    """Return a unique project name for test isolation, cleaned up after the test."""
    name = f"diag-{uuid.uuid4().hex[:8]}"
    yield name
    # Teardown: remove the test project from Phoenix
    time.sleep(1)  # allow final export before deleting
    _delete_project(name)


@pytest.mark.skipif(not _phoenix_available(), reason="Phoenix not running on localhost:6006")
class TestPhoenixDiagnostic:
    """Diagnostic tests against real Phoenix to find tracing issues."""

    def test_01_single_session_full_lifecycle(self, unique_project, monkeypatch):
        """Basic test: session → agent → tools → agent end → session end.

        Verifies the expected span hierarchy appears in Phoenix.
        """
        monkeypatch.setenv("OTEL_ENABLED", "true")
        relay = OTelRelay(
            endpoint=PHOENIX_TRACES,
            default_project_name=unique_project,
        )
        session_id = f"sess-{uuid.uuid4().hex[:8]}"

        # Full lifecycle
        relay.start_session(session_id, "")
        relay.start_agent("agent-r1", "i-am:researcher", session_id, session_id)
        relay.record_tool("agent-r1", "Read", "file_path=/src/main.py", "200 lines")
        relay.record_tool("agent-r1", "Bash", "command=pytest", "3 passed")
        relay.end_agent("agent-r1", "Research complete")
        relay.end_session(session_id)
        relay.shutdown()

        # Wait for export
        time.sleep(2)

        # Query Phoenix
        spans = _get_spans_for_project(unique_project)
        print(f"\n=== Spans in Phoenix for {unique_project} ===")
        for s in spans:
            print(
                f"  {s['name']:20s}  kind={s['spanKind']:6s}  "
                f"trace={s['context']['traceId'][:12]}...  "
                f"span={s['context']['spanId']}  "
                f"parent={s['parentId']}"
            )

        # Verify
        session_spans = [s for s in spans if s["name"] == "session"]
        agent_spans = [s for s in spans if s["spanKind"] == "agent"]
        tool_spans = [s for s in spans if s["spanKind"] == "tool"]

        print(f"\nSession spans: {len(session_spans)}")
        print(f"Agent spans:   {len(agent_spans)}")
        print(f"Tool spans:    {len(tool_spans)}")

        assert len(session_spans) == 1, f"Expected 1 session span, got {len(session_spans)}"
        # 2 agent spans: researcher + synthetic main-agent
        assert len(agent_spans) == 2, f"Expected 2 agent spans, got {len(agent_spans)}"
        assert len(tool_spans) == 2, f"Expected 2 tool spans, got {len(tool_spans)}"

        # Check hierarchy: agent parented to session
        session_span_id = session_spans[0]["context"]["spanId"]
        for a in agent_spans:
            assert a["parentId"] == session_span_id, (
                f"Agent span parent={a['parentId']} != session span={session_span_id}"
            )

        # Check hierarchy: tools parented to the researcher agent (not main-agent)
        researcher_spans = [a for a in agent_spans if a["name"] == "researcher"]
        assert len(researcher_spans) == 1, "Expected exactly 1 researcher agent span"
        researcher_span_id = researcher_spans[0]["context"]["spanId"]
        for t in tool_spans:
            assert t["parentId"] == researcher_span_id, (
                f"Tool span parent={t['parentId']} != researcher span={researcher_span_id}"
            )

        # Check all same trace_id
        trace_id = session_spans[0]["context"]["traceId"]
        for s in spans:
            assert s["context"]["traceId"] == trace_id, (
                f"Span {s['name']} has trace_id={s['context']['traceId']} != {trace_id}"
            )

    def test_02_multi_session_lifecycle(self, unique_project, monkeypatch, tmp_path):
        """Test: two sessions in the same relay lifecycle.

        This simulates what happens when chronograph-ctl persists across
        Claude Code session restarts (the normal case). Uses an explicit
        project_dir (like production) so Phoenix groups all sessions under
        one project derived from the directory basename.
        """
        monkeypatch.setenv("OTEL_ENABLED", "true")
        # Create a fake project dir whose basename becomes the Phoenix project name
        project_dir = str(tmp_path / unique_project)
        relay = OTelRelay(endpoint=PHOENIX_TRACES)

        # --- Session 1 ---
        sid1 = f"sess1-{uuid.uuid4().hex[:8]}"
        relay.start_session(sid1, project_dir)
        relay.start_agent("agent-a1", "i-am:researcher", sid1, sid1)
        relay.record_tool("agent-a1", "Read", "file=a.py", "ok")
        relay.end_agent("agent-a1", "done")
        relay.end_session(sid1)

        # --- Session 2 (new Claude Code session, same chronograph process) ---
        sid2 = f"sess2-{uuid.uuid4().hex[:8]}"
        relay.start_session(sid2, project_dir)
        relay.start_agent("agent-b1", "i-am:implementer", sid2, sid2)
        relay.record_tool("agent-b1", "Edit", "file=b.py", "edited")
        relay.end_agent("agent-b1", "done")
        relay.end_session(sid2)

        relay.shutdown()
        time.sleep(2)

        spans = _get_spans_for_project(unique_project)
        print(f"\n=== Multi-session spans in Phoenix for {unique_project} ===")
        for s in spans:
            print(
                f"  {s['name']:20s}  kind={s['spanKind']:6s}  "
                f"trace={s['context']['traceId'][:12]}...  "
                f"parent={s['parentId']}"
            )

        session_spans = [s for s in spans if s["name"] == "session"]
        agent_spans = [s for s in spans if s["spanKind"] == "agent"]
        tool_spans = [s for s in spans if s["spanKind"] == "tool"]

        print(f"\nSession spans: {len(session_spans)}")
        print(f"Agent spans:   {len(agent_spans)}")
        print(f"Tool spans:    {len(tool_spans)}")

        # Both sessions should have their own trace
        assert len(session_spans) == 2, (
            f"Expected 2 session spans (one per session), got {len(session_spans)}"
        )
        # 4 agent spans: 1 explicit agent + 1 main-agent per session
        assert len(agent_spans) == 4, (
            f"Expected 4 agent spans (agent + main-agent per session), got {len(agent_spans)}"
        )
        assert len(tool_spans) == 2, (
            f"Expected 2 tool spans (one per session), got {len(tool_spans)}"
        )

        # Sessions should have DIFFERENT trace_ids
        trace_ids = {s["context"]["traceId"] for s in session_spans}
        print(f"Distinct trace_ids: {trace_ids}")
        assert len(trace_ids) == 2, (
            f"Expected 2 distinct trace_ids, got {len(trace_ids)}: {trace_ids}"
        )

        # Both sessions land under the SAME Phoenix project (derived from project_dir basename)
        sessions = _get_sessions_for_project(unique_project)
        session_ids_in_phoenix = {s["sessionId"] for s in sessions}
        print(f"Phoenix sessions: {session_ids_in_phoenix}")
        assert sid1 in session_ids_in_phoenix, (
            f"Session 1 ({sid1}) not found in Phoenix project {unique_project}"
        )
        assert sid2 in session_ids_in_phoenix, (
            f"Session 2 ({sid2}) not found in Phoenix project {unique_project}"
        )

    def test_03_tools_without_agent(self, unique_project, monkeypatch):
        """Test: tool calls from main agent (no SubagentStart event).

        When the main agent uses tools directly (no delegation), tools
        should still appear under the session span.
        """
        monkeypatch.setenv("OTEL_ENABLED", "true")
        relay = OTelRelay(
            endpoint=PHOENIX_TRACES,
            default_project_name=unique_project,
        )
        session_id = f"sess-{uuid.uuid4().hex[:8]}"

        relay.start_session(session_id, "")
        # Main agent tools — no agent_id (empty string)
        relay.record_tool("", "Bash", "command=ls", "/src /tests", session_id=session_id)
        relay.record_tool("", "Read", "file=README.md", "# Project", session_id=session_id)
        relay.end_session(session_id)
        relay.shutdown()

        time.sleep(2)

        spans = _get_spans_for_project(unique_project)
        print(f"\n=== No-agent tool spans for {unique_project} ===")
        for s in spans:
            print(f"  {s['name']:20s}  kind={s['spanKind']:6s}  parent={s['parentId']}")

        session_spans = [s for s in spans if s["name"] == "session"]
        main_spans = [s for s in spans if s["name"] == "main-agent"]
        tool_spans = [s for s in spans if s["spanKind"] == "tool"]

        assert len(session_spans) == 1
        assert len(main_spans) == 1
        assert len(tool_spans) == 2

        # Tools should be parented to main-agent (not session root)
        main_span_id = main_spans[0]["context"]["spanId"]
        for t in tool_spans:
            assert t["parentId"] == main_span_id

    def test_04_session_linkage(self, unique_project, monkeypatch):
        """Test: session_id attribute maps to Phoenix Sessions view."""
        monkeypatch.setenv("OTEL_ENABLED", "true")
        relay = OTelRelay(
            endpoint=PHOENIX_TRACES,
            default_project_name=unique_project,
        )
        session_id = f"sess-{uuid.uuid4().hex[:8]}"

        relay.start_session(session_id, "")
        relay.record_tool("", "Bash", "echo hi", "hi", session_id=session_id)
        relay.end_session(session_id)
        relay.shutdown()

        time.sleep(2)

        sessions = _get_sessions_for_project(unique_project)
        print(f"\n=== Sessions in Phoenix for {unique_project} ===")
        for s in sessions:
            print(f"  sessionId={s['sessionId']}  numTraces={s['numTraces']}")

        session_ids = [s["sessionId"] for s in sessions]
        assert session_id in session_ids, (
            f"Session {session_id} not found in Phoenix. Found: {session_ids}"
        )
