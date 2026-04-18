"""Behavioral tests for OTelRelay -- the OTel span relay for Phoenix observability.

Tests are designed from the behavioral specification, not from implementation details.
The OTelRelay class is expected to translate session lifecycle events into OpenTelemetry
spans with openinference semantic conventions for Phoenix consumption.

Uses InMemorySpanExporter to verify span creation without requiring a live Phoenix instance.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

SESSION_ID = "sess-001"
SESSION_SPAN_NAME = "session"


class OTelRelayTestHarness:
    """Creates an OTelRelay wired to an InMemorySpanExporter for inspection."""

    def __init__(self, *, project_dir: str = "/tmp/test-project", otel_enabled: bool = True):
        self.exporter = InMemorySpanExporter()
        self.project_dir = project_dir

        env_patch = {"OTEL_ENABLED": str(otel_enabled).lower()}
        self._env_patcher = patch.dict(os.environ, env_patch)
        self._env_patcher.start()

        # Import after environment is set up
        from task_chronograph_mcp.otel_relay import OTelRelay

        self.relay = OTelRelay(
            exporter=self.exporter,
        )

    def teardown(self):
        self.relay.shutdown()
        self._env_patcher.stop()

    @property
    def finished_spans(self):
        return self.exporter.get_finished_spans()

    def session_span(self):
        """Return the session root span (identified by name, not by parent==None)."""
        matches = [s for s in self.finished_spans if s.name == SESSION_SPAN_NAME]
        assert len(matches) == 1, f"Expected 1 session span, found {len(matches)}"
        return matches[0]

    def spans_named(self, name: str):
        return [s for s in self.finished_spans if s.name == name]

    def spans_with_attribute(self, key: str, value: Any):
        return [s for s in self.finished_spans if s.attributes and s.attributes.get(key) == value]


@pytest.fixture
def harness():
    """Provide a fresh OTelRelay test harness with InMemorySpanExporter."""
    h = OTelRelayTestHarness()
    yield h
    h.teardown()


@pytest.fixture
def disabled_harness():
    """Provide an OTelRelay with OTEL_ENABLED=false."""
    h = OTelRelayTestHarness(otel_enabled=False)
    yield h
    h.teardown()


# ---------------------------------------------------------------------------
# 1. Session start creates a root CHAIN span
# ---------------------------------------------------------------------------


class TestSessionStartCreatesRootSpan:
    """Verify that start_session creates a root CHAIN span with correct attributes."""

    def test_session_start_creates_span_with_session_id_attribute(
        self, harness: OTelRelayTestHarness
    ):
        harness.relay.start_session("sess-abc-123", harness.project_dir)
        harness.relay.end_session("sess-abc-123")

        spans = harness.finished_spans
        assert len(spans) >= 1

        root = harness.session_span()
        assert root.attributes["session.id"] == "sess-abc-123"

    def test_session_start_produces_valid_trace_id(self, harness: OTelRelayTestHarness):
        harness.relay.start_session("sess-abc", harness.project_dir)
        harness.relay.end_session("sess-abc")

        root = harness.session_span()
        assert root.context.trace_id != 0

    def test_session_start_sets_project_name_as_basename(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        assert root.attributes["praxion.project_name"] == "test-project"

    def test_session_start_sets_full_project_dir(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        assert root.attributes["praxion.project_dir"] == "/tmp/test-project"

    def test_session_start_sets_span_kind_chain(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        assert root.attributes["openinference.span.kind"] == "CHAIN"


# ---------------------------------------------------------------------------
# 2. Agent start/stop creates AGENT child spans
# ---------------------------------------------------------------------------


class TestAgentSpanLifecycle:
    """Verify start_agent creates an AGENT span parented under session root."""

    def test_agent_span_has_agent_type_attribute(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Research complete")
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_type", "researcher")
        assert len(agent_spans) == 1

    def test_agent_span_has_agent_id_attribute(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_id", "agent-r1")
        assert len(agent_spans) == 1

    def test_agent_span_is_child_of_main_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        main = harness.spans_with_attribute("praxion.agent_type", "main-agent")[0]
        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]

        # Agent is a child of main-agent (hierarchy-aware parenting)
        assert agent.parent is not None
        assert agent.parent.span_id == main.context.span_id
        # All spans share the same trace
        assert agent.context.trace_id == root.context.trace_id

    def test_agent_span_kind_is_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["openinference.span.kind"] == "AGENT"

    def test_agent_stop_creates_summary_span_with_output(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Findings: auth uses OAuth2")
        harness.relay.end_session(SESSION_ID)

        summary_spans = harness.spans_named("agent-summary")
        assert len(summary_spans) == 1
        assert summary_spans[0].attributes["output.value"] == "Findings: auth uses OAuth2"
        assert summary_spans[0].attributes["praxion.tool_count"] == 0

        # Summary span is a child of the agent span
        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert summary_spans[0].parent.span_id == agent.context.span_id

    def test_praxion_agent_origin_detected(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "i-am:researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        # Implementation strips the i-am: prefix for praxion.agent_type
        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["praxion.agent_origin"] == "praxion"

    def test_claude_code_agent_origin_detected(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-gp1", "general-purpose", SESSION_ID)
        harness.relay.end_agent("agent-gp1", "Done")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "general-purpose")[0]
        assert agent.attributes["praxion.agent_origin"] == "claude-code"


# ---------------------------------------------------------------------------
# 2b. Agent spans are ended immediately for Phoenix visibility
# ---------------------------------------------------------------------------


class TestAgentSpanImmediateEnd:
    """Verify agent spans are ended immediately so Phoenix shows the hierarchy."""

    def test_agent_span_available_before_end_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)

        # Agent span should already be in finished spans (ended immediately)
        agent_spans = harness.spans_with_attribute("praxion.agent_type", "researcher")
        assert len(agent_spans) == 1
        assert agent_spans[0].end_time is not None

        harness.relay.end_agent("agent-r1")
        harness.relay.end_session(SESSION_ID)

    def test_tool_spans_parent_under_immediately_ended_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-i1", "implementer", SESSION_ID)
        harness.relay.record_tool(agent_id="agent-i1", tool_name="Read", input_summary="f.py")
        harness.relay.end_agent("agent-i1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_id", "agent-i1")[0]
        tool = harness.spans_with_attribute("tool.name", "Read")[0]
        assert tool.parent.span_id == agent.context.span_id

    def test_empty_agent_type_uses_agent_id_as_name(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("my-agent-id", "", SESSION_ID)
        harness.relay.end_agent("my-agent-id")
        harness.relay.end_session(SESSION_ID)

        # Should use agent_id as span name when agent_type is empty
        spans = harness.spans_named("my-agent-id")
        assert len(spans) == 1

    def test_fully_empty_agent_uses_unknown_name(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("", "", SESSION_ID)
        harness.relay.end_agent("")
        harness.relay.end_session(SESSION_ID)

        spans = harness.spans_named("unknown-agent")
        assert len(spans) == 1


# ---------------------------------------------------------------------------
# 3. Tool record creates TOOL child span
# ---------------------------------------------------------------------------


class TestToolSpanCreation:
    """Verify tool records create TOOL spans under the correct parent."""

    def test_tool_span_under_agent_parent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-i1", "implementer", SESSION_ID)
        harness.relay.record_tool(
            agent_id="agent-i1",
            tool_name="Read",
            input_summary="/src/main.py",
            output_summary="file contents...",
        )
        harness.relay.end_agent("agent-i1", "Done")
        harness.relay.end_session(SESSION_ID)

        tool_spans = harness.spans_with_attribute("tool.name", "Read")
        assert len(tool_spans) == 1

        agent = harness.spans_with_attribute("praxion.agent_id", "agent-i1")[0]
        tool = tool_spans[0]
        assert tool.parent is not None
        assert tool.parent.span_id == agent.context.span_id

    def test_tool_span_under_main_agent_when_no_agent_id(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            agent_id="",
            tool_name="Bash",
            input_summary="ls -la",
            output_summary="file list",
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_with_attribute("tool.name", "Bash")[0]
        main_agent = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")[0]
        assert tool.parent is not None
        assert tool.parent.span_id == main_agent.context.span_id

    def test_tool_span_falls_back_to_main_agent_when_unknown_agent_id(
        self, harness: OTelRelayTestHarness
    ):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            agent_id="nonexistent-agent",
            tool_name="Write",
            input_summary="path",
            output_summary="ok",
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_with_attribute("tool.name", "Write")[0]
        main_agent = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")[0]
        assert tool.parent is not None
        # Falls back to main-agent when the agent_id is unknown
        assert tool.parent.span_id == main_agent.context.span_id

    def test_tool_span_has_tool_name_attribute(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            agent_id="",
            tool_name="Grep",
            input_summary="pattern",
            output_summary="matches",
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_with_attribute("tool.name", "Grep")[0]
        assert tool.attributes["tool.name"] == "Grep"

    def test_tool_span_has_input_and_output_values(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            agent_id="",
            tool_name="Read",
            input_summary="/etc/config.yaml",
            output_summary="key: value",
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_with_attribute("tool.name", "Read")[0]
        assert tool.attributes["input.value"] == "/etc/config.yaml"
        assert tool.attributes["output.value"] == "key: value"

    def test_tool_span_kind_is_tool(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            agent_id="",
            tool_name="Edit",
            input_summary="file",
            output_summary="edited",
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_with_attribute("tool.name", "Edit")[0]
        assert tool.attributes["openinference.span.kind"] == "TOOL"


# ---------------------------------------------------------------------------
# 4. Error tool record sets span status to ERROR
# ---------------------------------------------------------------------------


class TestErrorToolRecord:
    """Verify that error tool records set ERROR status and add an error event."""

    def test_error_tool_sets_span_status_error(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            agent_id="",
            tool_name="Bash",
            input_summary="rm -rf /",
            output_summary="Permission denied",
            is_error=True,
            error_msg="Permission denied",
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_with_attribute("tool.name", "Bash")[0]
        assert tool.status.status_code == StatusCode.ERROR

    def test_error_tool_adds_error_event(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            agent_id="",
            tool_name="Bash",
            input_summary="bad-cmd",
            output_summary="command not found",
            is_error=True,
            error_msg="command not found",
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_with_attribute("tool.name", "Bash")[0]
        error_events = [e for e in tool.events if e.name == "error"]
        assert len(error_events) >= 1


# ---------------------------------------------------------------------------
# 5. Parallel agents create sibling AGENT spans
# ---------------------------------------------------------------------------


class TestParallelAgentSpans:
    """Verify parallel agents both parent under main-agent, not nested."""

    def test_parallel_agents_are_siblings_under_main_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-i1", "implementer", SESSION_ID)
        harness.relay.start_agent("agent-t1", "test-engineer", SESSION_ID)
        harness.relay.end_agent("agent-i1", "Code written")
        harness.relay.end_agent("agent-t1", "Tests written")
        harness.relay.end_session(SESSION_ID)

        main = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")[0]
        impl_span = harness.spans_with_attribute("praxion.agent_id", "agent-i1")[0]
        test_span = harness.spans_with_attribute("praxion.agent_id", "agent-t1")[0]

        # Both should be children of the main-agent span (hierarchy-aware)
        assert impl_span.parent.span_id == main.context.span_id
        assert test_span.parent.span_id == main.context.span_id

    def test_parallel_agents_have_distinct_span_ids(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-i1", "implementer", SESSION_ID)
        harness.relay.start_agent("agent-t1", "test-engineer", SESSION_ID)
        harness.relay.end_agent("agent-i1", "Done")
        harness.relay.end_agent("agent-t1", "Done")
        harness.relay.end_session(SESSION_ID)

        impl_span = harness.spans_with_attribute("praxion.agent_id", "agent-i1")[0]
        test_span = harness.spans_with_attribute("praxion.agent_id", "agent-t1")[0]
        assert impl_span.context.span_id != test_span.context.span_id

    def test_parallel_agents_share_same_trace_id(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-i1", "implementer", SESSION_ID)
        harness.relay.start_agent("agent-t1", "test-engineer", SESSION_ID)
        harness.relay.end_agent("agent-i1", "Done")
        harness.relay.end_agent("agent-t1", "Done")
        harness.relay.end_session(SESSION_ID)

        impl_span = harness.spans_with_attribute("praxion.agent_id", "agent-i1")[0]
        test_span = harness.spans_with_attribute("praxion.agent_id", "agent-t1")[0]
        root = harness.session_span()
        assert impl_span.context.trace_id == root.context.trace_id
        assert test_span.context.trace_id == root.context.trace_id


# ---------------------------------------------------------------------------
# 6. Phase transition event on agent span
# ---------------------------------------------------------------------------


class TestPhaseTransitionEvent:
    """Verify phase transitions appear as child spans under the agent."""

    def test_phase_creates_child_span_under_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.add_phase_event(
            agent_id="agent-r1",
            phase=2,
            total=5,
            name="analysis",
            summary="Analyzing auth libraries",
        )
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        phase_spans = harness.spans_named("phase:analysis")
        assert len(phase_spans) == 1

        phase = phase_spans[0]
        assert phase.attributes["phase.number"] == 2
        assert phase.attributes["phase.total"] == 5
        assert phase.attributes["phase.name"] == "analysis"
        assert phase.attributes["phase.summary"] == "Analyzing auth libraries"

        # Phase span is a child of the agent span
        agent = harness.spans_with_attribute("praxion.agent_id", "agent-r1")[0]
        assert phase.parent.span_id == agent.context.span_id


# ---------------------------------------------------------------------------
# 7. Decision event on agent span
# ---------------------------------------------------------------------------


class TestDecisionEvent:
    """Verify decision records appear as child spans under the agent."""

    def test_decision_creates_child_span_under_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-sa1", "systems-architect", SESSION_ID)
        harness.relay.add_decision_event(
            agent_id="agent-sa1",
            decision={
                "id": "dec-abc123",
                "category": "architectural",
                "text": "Use event sourcing for state management",
                "made_by": "agent",
            },
        )
        harness.relay.end_agent("agent-sa1", "Done")
        harness.relay.end_session(SESSION_ID)

        decision_spans = harness.spans_named("decision")
        assert len(decision_spans) == 1

        dec = decision_spans[0]
        assert dec.attributes["decision.id"] == "dec-abc123"
        assert dec.attributes["decision.category"] == "architectural"
        assert dec.attributes["decision.text"] == "Use event sourcing for state management"

        # Decision span is a child of the agent span
        agent = harness.spans_with_attribute("praxion.agent_id", "agent-sa1")[0]
        assert dec.parent.span_id == agent.context.span_id


# ---------------------------------------------------------------------------
# 8. Events on non-existent agent_id silently ignored
# ---------------------------------------------------------------------------


class TestEventsOnNonExistentAgent:
    """Verify that events targeting unknown agents are silently ignored."""

    def test_phase_transition_on_unknown_agent_does_not_raise(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Should not raise
        harness.relay.add_phase_event(
            agent_id="ghost-agent",
            phase=1,
            total=3,
            name="init",
            summary="Starting up",
        )
        harness.relay.end_session(SESSION_ID)

    def test_decision_on_unknown_agent_does_not_raise(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Should not raise
        harness.relay.add_decision_event(
            agent_id="ghost-agent",
            decision={
                "id": "dec-xyz",
                "category": "implementation",
                "text": "Use REST over GraphQL",
                "made_by": "agent",
            },
        )
        harness.relay.end_session(SESSION_ID)

    def test_end_agent_on_unknown_agent_does_not_raise(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Should not raise
        harness.relay.end_agent("ghost-agent", "Done")
        harness.relay.end_session(SESSION_ID)


# ---------------------------------------------------------------------------
# 9. end_session ends the root span
# ---------------------------------------------------------------------------


class TestEndSession:
    """Verify that end_session finishes the root span."""

    def test_end_session_ends_root_span(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        session_spans = harness.spans_named(SESSION_SPAN_NAME)
        assert len(session_spans) == 1
        # The span being in finished_spans means it was ended

    def test_root_span_appears_in_finished_after_end_session(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)

        # Before ending session, root might not be in finished spans yet
        # (it's still active)
        harness.relay.end_session(SESSION_ID)

        # After ending, root must appear in finished spans
        session_spans = harness.spans_named(SESSION_SPAN_NAME)
        assert len(session_spans) == 1


# ---------------------------------------------------------------------------
# 10. Graceful degradation when exporter fails
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Verify that exporter failures do not propagate as exceptions."""

    def test_broken_exporter_does_not_raise_on_session_start(self):
        from task_chronograph_mcp.otel_relay import OTelRelay

        # Create an exporter that will cause export failures
        failing_exporter = InMemorySpanExporter()
        failing_exporter.shutdown()  # Shutdown exporter so exports fail

        relay = OTelRelay(exporter=failing_exporter)

        # Should not raise
        relay.start_session(SESSION_ID, "/tmp/test")
        relay.start_agent("agent-r1", "researcher", SESSION_ID)
        relay.record_tool(
            agent_id="agent-r1",
            tool_name="Read",
            input_summary="file",
            output_summary="contents",
        )
        relay.end_agent("agent-r1", "Done")
        relay.end_session(SESSION_ID)
        relay.shutdown()


# ---------------------------------------------------------------------------
# 11. OTEL_ENABLED=false disables all span creation
# ---------------------------------------------------------------------------


class TestOTelDisabled:
    """Verify that OTEL_ENABLED=false disables all span creation."""

    def test_no_spans_created_when_disabled(self, disabled_harness: OTelRelayTestHarness):
        disabled_harness.relay.start_session(SESSION_ID, disabled_harness.project_dir)
        disabled_harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        disabled_harness.relay.record_tool(
            agent_id="agent-r1",
            tool_name="Read",
            input_summary="file",
            output_summary="contents",
        )
        disabled_harness.relay.end_agent("agent-r1", "Done")
        disabled_harness.relay.end_session(SESSION_ID)

        assert len(disabled_harness.finished_spans) == 0

    def test_disabled_relay_methods_do_not_raise(self, disabled_harness: OTelRelayTestHarness):
        """All relay methods should be no-ops when disabled, not raise errors."""
        disabled_harness.relay.start_session(SESSION_ID, disabled_harness.project_dir)
        disabled_harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        disabled_harness.relay.add_phase_event(
            agent_id="agent-r1",
            phase=1,
            total=3,
            name="init",
            summary="Starting",
        )
        disabled_harness.relay.add_decision_event(
            agent_id="agent-r1",
            decision={
                "id": "dec-001",
                "category": "impl",
                "text": "Use X",
                "made_by": "agent",
            },
        )
        disabled_harness.relay.record_tool(
            agent_id="agent-r1",
            tool_name="Bash",
            input_summary="cmd",
            output_summary="out",
            is_error=True,
            error_msg="failed",
        )
        disabled_harness.relay.end_agent("agent-r1", "Done")
        disabled_harness.relay.end_session(SESSION_ID)
        # No assertions needed -- test passes if no exceptions raised


# ---------------------------------------------------------------------------
# 12. Trace type detection
# ---------------------------------------------------------------------------


class TestTraceTypeDetection:
    """Verify trace_type attribute on agent spans based on their origin."""

    def test_praxion_agent_has_pipeline_trace_type(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "i-am:researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_named("researcher")[0]
        assert agent.attributes.get("praxion.trace_type") == "pipeline"

    def test_native_agent_has_native_trace_type(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-gp1", "general-purpose", SESSION_ID)
        harness.relay.end_agent("agent-gp1", "Done")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_named("general-purpose")[0]
        assert agent.attributes.get("praxion.trace_type") == "native"

    def test_mixed_agents_each_carry_their_own_trace_type(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "i-am:researcher", SESSION_ID)
        harness.relay.start_agent("agent-gp1", "general-purpose", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_agent("agent-gp1", "Done")
        harness.relay.end_session(SESSION_ID)

        researcher = harness.spans_named("researcher")[0]
        gp = harness.spans_named("general-purpose")[0]
        assert researcher.attributes.get("praxion.trace_type") == "pipeline"
        assert gp.attributes.get("praxion.trace_type") == "native"


# ---------------------------------------------------------------------------
# 13. Main agent span
# ---------------------------------------------------------------------------


class TestMainAgentSpan:
    """Verify the synthetic main-agent span created on session start."""

    def test_main_agent_span_created_on_session_start(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        main_spans = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")
        assert len(main_spans) == 1
        main = main_spans[0]
        assert main.name == "main-agent"
        assert main.attributes.get("openinference.span.kind") == "AGENT"
        assert main.attributes.get("praxion.agent_origin") == "claude-code"

    def test_main_agent_is_child_of_session_root(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        main = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")[0]
        root = harness.session_span()
        assert main.parent is not None
        assert main.parent.span_id == root.context.span_id

    def test_empty_agent_id_tools_go_under_main_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(agent_id="", tool_name="Read", input_summary="f.py")
        harness.relay.record_tool(agent_id="", tool_name="Bash", input_summary="ls")
        harness.relay.end_session(SESSION_ID)

        main = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")[0]
        tools = [s for s in harness.exporter.get_finished_spans() if s.attributes.get("tool.name")]
        assert len(tools) == 2
        for tool in tools:
            assert tool.parent is not None
            assert tool.parent.span_id == main.context.span_id

    def test_subagent_tools_not_affected_by_main_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "i-am:researcher", SESSION_ID)
        harness.relay.record_tool(agent_id="a1", tool_name="Glob", input_summary="*.py")
        harness.relay.end_agent("a1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_named("researcher")[0]
        tool = harness.spans_with_attribute("tool.name", "Glob")[0]
        assert tool.parent is not None
        assert tool.parent.span_id == agent.context.span_id

    def test_main_agent_ended_immediately(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Main agent span is already ended (immediately at session start)
        main = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")[0]
        assert main.end_time is not None
        assert main.end_time >= main.start_time

        # Tool calls still parent under it via saved context
        harness.relay.record_tool(agent_id="", tool_name="Bash", input_summary="echo hi")
        harness.relay.end_session(SESSION_ID)

        tools = [s for s in harness.exporter.get_finished_spans() if s.attributes.get("tool.name")]
        assert len(tools) == 1
        assert tools[0].parent.span_id == main.context.span_id


# ---------------------------------------------------------------------------
# 14. Span reaper
# ---------------------------------------------------------------------------


class TestContextReaper:
    """Verify the background reaper cleans up stale agent contexts."""

    def test_stale_agent_context_reaped(self, harness: OTelRelayTestHarness):
        import task_chronograph_mcp.otel_relay as relay_mod

        orig_timeout = relay_mod.AGENT_SPAN_TIMEOUT_S
        relay_mod.AGENT_SPAN_TIMEOUT_S = 0.1  # 100ms for testing
        try:
            harness.relay.start_session(SESSION_ID, harness.project_dir)
            harness.relay.start_agent("bg-agent", "i-am:verifier", SESSION_ID)
            harness.relay.record_tool(agent_id="bg-agent", tool_name="Read", input_summary="f.py")

            # Wait for inactivity to exceed timeout
            import time

            time.sleep(0.5)

            # Manually trigger reap (reaper thread may not have run yet)
            harness.relay._reap_stale_contexts()

            # Context should be cleaned up
            with harness.relay._span_lock:
                assert "bg-agent" not in harness.relay._agent_contexts

            harness.relay.end_session(SESSION_ID)
        finally:
            relay_mod.AGENT_SPAN_TIMEOUT_S = orig_timeout

    def test_active_agent_not_reaped(self, harness: OTelRelayTestHarness):
        import task_chronograph_mcp.otel_relay as relay_mod

        orig_timeout = relay_mod.AGENT_SPAN_TIMEOUT_S
        relay_mod.AGENT_SPAN_TIMEOUT_S = 10  # long timeout
        try:
            harness.relay.start_session(SESSION_ID, harness.project_dir)
            harness.relay.start_agent("active-agent", "i-am:researcher", SESSION_ID)
            harness.relay.record_tool(
                agent_id="active-agent", tool_name="Read", input_summary="f.py"
            )

            harness.relay._reap_stale_contexts()

            # Agent should still be in context map (not reaped)
            with harness.relay._span_lock:
                assert "active-agent" in harness.relay._agent_contexts

            harness.relay.end_agent("active-agent")
            harness.relay.end_session(SESSION_ID)
        finally:
            relay_mod.AGENT_SPAN_TIMEOUT_S = orig_timeout

    def test_explicit_stop_prevents_reap(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-x", "i-am:sentinel", SESSION_ID)
        harness.relay.end_agent("agent-x", "Done")

        harness.relay._reap_stale_contexts()

        # Context already removed by end_agent -- nothing to reap
        with harness.relay._span_lock:
            assert "agent-x" not in harness.relay._agent_contexts
        harness.relay.end_session(SESSION_ID)

    def test_reaper_thread_stops_on_shutdown(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)

        assert harness.relay._reaper_thread is not None
        assert harness.relay._reaper_thread.is_alive()

        harness.relay.shutdown()

        assert harness.relay._reaper_thread is None or not harness.relay._reaper_thread.is_alive()


# ---------------------------------------------------------------------------
# Git context on spans
# ---------------------------------------------------------------------------


class TestGitContextOnSpans:
    """Verify that git context (branch, worktree) is attached to spans."""

    def test_session_span_has_git_branch_attribute(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(
            SESSION_ID, harness.project_dir, git_context={"git_branch": "feat/auth"}
        )
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        assert root.attributes["praxion.git.branch"] == "feat/auth"

    def test_session_span_has_worktree_attributes(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(
            SESSION_ID,
            harness.project_dir,
            git_context={"git_branch": "feat/auth", "is_worktree": True, "worktree_name": "auth"},
        )
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        assert root.attributes["praxion.git.is_worktree"] is True
        assert root.attributes["praxion.git.worktree_name"] == "auth"

    def test_session_span_omits_git_when_not_provided(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        assert "praxion.git.branch" not in root.attributes

    def test_agent_span_has_git_branch_attribute(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent(
            "agent-r1",
            "researcher",
            SESSION_ID,
            git_context={"git_branch": "feat/auth"},
        )
        harness.relay.end_agent("agent-r1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["praxion.git.branch"] == "feat/auth"


# ---------------------------------------------------------------------------
# Agent hierarchy depth
# ---------------------------------------------------------------------------


class TestAgentDepthAttribute:
    """Verify that agent spans carry correct depth attribute."""

    def test_main_agent_has_depth_zero(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        main = harness.spans_with_attribute("praxion.agent_type", "main-agent")[0]
        assert main.attributes["praxion.depth"] == 0

    def test_depth_one_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["praxion.depth"] == 1

    def test_parent_agent_id_attribute(self, harness: OTelRelayTestHarness):
        """With no preceding PreToolUse(Agent), the FIFO queue is empty and the
        agent falls back to main-agent as its parent -- the baseline behavior."""
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["praxion.parent_agent_id"] == "__main_agent__"


# ---------------------------------------------------------------------------
# Spawn correlation: PreToolUse(Agent) + SubagentStart FIFO hierarchy
# ---------------------------------------------------------------------------


class TestSpawnCorrelationHierarchy:
    """Verify that PreToolUse(Agent) drives correct parent resolution for
    subagent spans, so Phoenix shows depth-2+ agent chains properly."""

    def _simulate_agent_tool(self, harness, *, caller_agent_id: str, tool_use_id: str):
        """Fire a PreToolUse(Agent) as the given caller. The tool span itself
        is a side effect; what matters is the pending-spawn registration."""
        harness.relay.start_tool(
            tool_use_id=tool_use_id,
            agent_id=caller_agent_id,
            tool_name="Agent",
            session_id=SESSION_ID,
        )

    def test_depth_2_agent_is_child_of_spawning_subagent(self, harness: OTelRelayTestHarness):
        """When subagent A invokes the Agent tool to spawn B, B's parent is A
        -- not main-agent. This is the core regression this fix addresses."""
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Main spawns A
        self._simulate_agent_tool(harness, caller_agent_id="", tool_use_id="t1")
        harness.relay.start_agent("agent-A", "architect", SESSION_ID)
        # A spawns B
        self._simulate_agent_tool(harness, caller_agent_id="agent-A", tool_use_id="t2")
        harness.relay.start_agent("agent-B", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-B")
        harness.relay.end_agent("agent-A")
        harness.relay.end_session(SESSION_ID)

        agent_b = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        agent_a = harness.spans_with_attribute("praxion.agent_type", "architect")[0]
        assert agent_b.attributes["praxion.parent_agent_id"] == "agent-A"
        assert agent_b.parent is not None
        assert agent_b.parent.span_id == agent_a.context.span_id

    def test_parallel_spawns_from_main_all_have_main_as_parent(self, harness: OTelRelayTestHarness):
        """Main spawns three subagents in quick succession. Each subagent's
        SubagentStart pops one FIFO entry; all three resolve to main-agent."""
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        for i in range(3):
            self._simulate_agent_tool(harness, caller_agent_id="", tool_use_id=f"t{i}")
        for i in range(3):
            harness.relay.start_agent(f"agent-p{i}", "researcher", SESSION_ID)
            harness.relay.end_agent(f"agent-p{i}")
        harness.relay.end_session(SESSION_ID)

        subagents = harness.spans_with_attribute("praxion.agent_type", "researcher")
        assert len(subagents) == 3
        for s in subagents:
            assert s.attributes["praxion.parent_agent_id"] == "__main_agent__"

    def test_nested_chain_preserves_hierarchy_at_depth_3(self, harness: OTelRelayTestHarness):
        """Main → A → B → C: each level parents under its spawner, not main."""
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        self._simulate_agent_tool(harness, caller_agent_id="", tool_use_id="t1")
        harness.relay.start_agent("agent-A", "architect", SESSION_ID)
        self._simulate_agent_tool(harness, caller_agent_id="agent-A", tool_use_id="t2")
        harness.relay.start_agent("agent-B", "researcher", SESSION_ID)
        self._simulate_agent_tool(harness, caller_agent_id="agent-B", tool_use_id="t3")
        harness.relay.start_agent("agent-C", "implementer", SESSION_ID)
        harness.relay.end_agent("agent-C")
        harness.relay.end_agent("agent-B")
        harness.relay.end_agent("agent-A")
        harness.relay.end_session(SESSION_ID)

        agent_c = harness.spans_with_attribute("praxion.agent_type", "implementer")[0]
        agent_b = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent_c.attributes["praxion.parent_agent_id"] == "agent-B"
        assert agent_c.attributes["praxion.depth"] == 3
        assert agent_c.parent.span_id == agent_b.context.span_id

    def test_agent_start_without_pretool_use_falls_back_to_main(
        self, harness: OTelRelayTestHarness
    ):
        """Background agents (hooks never fire PreToolUse before SubagentStart)
        must still produce a valid span rooted under main-agent."""
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-bg", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-bg")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["praxion.parent_agent_id"] == "__main_agent__"


# ---------------------------------------------------------------------------
# Skill invocation spans
# ---------------------------------------------------------------------------


class TestSkillInvocationSpans:
    """Verify that record_skill creates CHAIN spans with correct attributes."""

    def test_skill_span_created_with_name(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_skill("", "software-planning", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        skill_spans = harness.spans_named("skill:software-planning")
        assert len(skill_spans) == 1

    def test_skill_span_has_artifact_type(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_skill("", "python-development", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        skill = harness.spans_named("skill:python-development")[0]
        assert skill.attributes["praxion.artifact_type"] == "skill"
        assert skill.attributes["praxion.skill_name"] == "python-development"

    def test_skill_span_is_chain_kind(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_skill("", "testing-strategy", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        skill = harness.spans_named("skill:testing-strategy")[0]
        assert skill.attributes["openinference.span.kind"] == "CHAIN"

    def test_skill_span_parented_under_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.record_skill("agent-r1", "refactoring", session_id=SESSION_ID)
        harness.relay.end_agent("agent-r1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        skill = harness.spans_named("skill:refactoring")[0]
        assert skill.parent.span_id == agent.context.span_id


# ---------------------------------------------------------------------------
# MCP tool enrichment
# ---------------------------------------------------------------------------


class TestMcpToolEnrichment:
    """Verify that MCP tool spans carry server/tool metadata."""

    def test_mcp_tool_has_server_and_tool_attributes(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            "",
            "mcp__plugin_i-am_memory__remember",
            "key=test",
            "ok",
            session_id=SESSION_ID,
            metadata={
                "artifact_type": "mcp_tool",
                "mcp_server": "memory",
                "mcp_tool": "remember",
            },
        )
        harness.relay.end_session(SESSION_ID)

        tool = harness.spans_named("mcp__plugin_i-am_memory__remember")[0]
        assert tool.attributes["praxion.artifact_type"] == "mcp_tool"
        assert tool.attributes["praxion.mcp_server"] == "memory"
        assert tool.attributes["praxion.mcp_tool"] == "remember"


# ---------------------------------------------------------------------------
# Session summary span
# ---------------------------------------------------------------------------


class TestSessionSummarySpan:
    """Verify that end_session creates a session-summary span with aggregates."""

    def test_session_summary_span_created(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID)
        harness.relay.record_tool("a1", "Read", "f", "ok", session_id=SESSION_ID)
        harness.relay.record_tool("a1", "Write", "f", "ok", session_id=SESSION_ID)
        harness.relay.end_agent("a1")
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")
        assert len(summary) == 1

    def test_session_summary_has_agent_count(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID)
        harness.relay.start_agent("a2", "implementer", SESSION_ID)
        harness.relay.end_agent("a1")
        harness.relay.end_agent("a2")
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        assert summary.attributes["praxion.agent_count"] == 2

    def test_session_summary_has_tool_count(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool("", "Read", "f", "ok", session_id=SESSION_ID)
        harness.relay.record_tool("", "Write", "f", "ok", session_id=SESSION_ID)
        harness.relay.record_tool("", "Bash", "cmd", "ok", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        assert summary.attributes["praxion.tool_count"] == 3

    def test_session_summary_has_error_count(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            "", "Bash", "cmd", "", is_error=True, error_msg="fail", session_id=SESSION_ID
        )
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        assert summary.attributes["praxion.error_count"] == 1

    def test_session_summary_has_git_branch(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(
            SESSION_ID, harness.project_dir, git_context={"git_branch": "main"}
        )
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        assert summary.attributes["praxion.git.branch"] == "main"

    def test_session_summary_has_skill_count(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_skill("", "python-dev", session_id=SESSION_ID)
        harness.relay.record_skill("", "testing", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        assert summary.attributes["praxion.skill_count"] == 2

    def test_session_summary_has_duration(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        assert "praxion.duration_s" in summary.attributes
        assert summary.attributes["praxion.duration_s"] >= 0

    def test_session_summary_has_readable_text(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID)
        harness.relay.record_tool("a1", "Read", "f", "ok", session_id=SESSION_ID)
        harness.relay.end_agent("a1")
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        text = summary.attributes["praxion.session_summary"]
        assert "1 agents" in text
        assert "1 tools" in text


# ---------------------------------------------------------------------------
# Agent summary spans with stats
# ---------------------------------------------------------------------------


class TestAgentSummaryStats:
    """Verify that agent-summary spans carry tool/error/child counts."""

    def test_agent_summary_tracks_tool_count(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID)
        harness.relay.record_tool("a1", "Read", "f", "ok", session_id=SESSION_ID)
        harness.relay.record_tool("a1", "Grep", "p", "ok", session_id=SESSION_ID)
        harness.relay.end_agent("a1", "done")
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("agent-summary")[0]
        assert summary.attributes["praxion.tool_count"] == 2

    def test_agent_summary_tracks_error_count(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID)
        harness.relay.record_tool(
            "a1", "Bash", "cmd", "", is_error=True, error_msg="fail", session_id=SESSION_ID
        )
        harness.relay.end_agent("a1", "done")
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("agent-summary")[0]
        assert summary.attributes["praxion.error_count"] == 1

    def test_agent_summary_tracks_skill_count(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID)
        harness.relay.record_skill("a1", "python-dev", session_id=SESSION_ID)
        harness.relay.end_agent("a1", "done")
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("agent-summary")[0]
        assert summary.attributes["praxion.skill_count"] == 1

    def test_agent_summary_without_output(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID)
        harness.relay.end_agent("a1")  # no output
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("agent-summary")[0]
        assert "output.value" not in summary.attributes


# ---------------------------------------------------------------------------
# Task slug propagation
# ---------------------------------------------------------------------------


class TestTaskSlugPropagation:
    """Verify task_slug is captured on agent spans."""

    def test_task_slug_on_agent_span(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID, task_slug="auth-flow")
        harness.relay.end_agent("a1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["praxion.task_slug"] == "auth-flow"

    def test_task_slug_propagated_to_session_summary(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("a1", "researcher", SESSION_ID, task_slug="auth-flow")
        harness.relay.end_agent("a1")
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("session-summary")[0]
        assert summary.attributes["praxion.task_slug"] == "auth-flow"


# ---------------------------------------------------------------------------
# Phoenix Agent Graph attributes (graph.node.*)
# ---------------------------------------------------------------------------


class TestGraphNodeAttributes:
    """Verify graph.node.* attributes for Phoenix Agent Graph view."""

    def test_main_agent_has_graph_node_id(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)

        main = harness.spans_with_attribute("praxion.agent_type", "main-agent")[0]
        assert main.attributes["graph.node.id"] == "__main_agent__"
        assert main.attributes["graph.node.name"] == "main-agent"
        assert main.attributes["graph.node.parent_id"] == ""

    def test_agent_has_graph_node_with_parent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["graph.node.id"] == "agent-r1"
        assert agent.attributes["graph.node.name"] == "researcher"
        assert agent.attributes["graph.node.parent_id"] == "__main_agent__"

    def test_agent_has_agent_name_attribute(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "i-am:researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["agent.name"] == "researcher"


# ---------------------------------------------------------------------------
# Lazy agent context creation for background agents
# ---------------------------------------------------------------------------


class TestLazyAgentContextCreation:
    """Verify that agent spans are auto-created when tool events arrive
    for an unknown agent_id with a populated agent_type.

    This handles Claude Code not firing SubagentStart hooks for background
    agents (run_in_background: true).
    """

    def test_tool_creates_agent_span_for_unknown_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # No start_agent call — simulates missing SubagentStart hook
        harness.relay.record_tool(
            "bg-agent-001", "Bash", agent_type="Explore", session_id=SESSION_ID
        )
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_type", "Explore")
        assert len(agent_spans) == 1, "Lazy agent span should be created"
        assert agent_spans[0].attributes["praxion.agent_id"] == "bg-agent-001"

    def test_lazy_agent_span_parents_tool_spans(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            "bg-agent-001", "Bash", agent_type="Explore", session_id=SESSION_ID
        )
        harness.relay.record_tool(
            "bg-agent-001", "Read", agent_type="Explore", session_id=SESSION_ID
        )
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_type", "Explore")
        assert len(agent_spans) == 1, "Only one agent span despite multiple tools"
        tool_spans = [s for s in harness.finished_spans if s.name in ("Bash", "Read")]
        assert len(tool_spans) == 2
        # Tool spans should be parented under the lazy agent span
        agent_ctx = agent_spans[0].context
        for tool in tool_spans:
            assert tool.parent.span_id == agent_ctx.span_id

    def test_no_lazy_span_without_agent_type(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Empty agent_type should fall back to main-agent, not create lazy span
        harness.relay.record_tool("bg-agent-001", "Bash", agent_type="", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_id", "bg-agent-001")
        assert len(agent_spans) == 0, "No lazy span without agent_type"

    def test_no_lazy_span_without_agent_id(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool("", "Bash", agent_type="Explore", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_type", "Explore")
        assert len(agent_spans) == 0, "No lazy span without agent_id"

    def test_lazy_span_not_duplicated_on_subsequent_tools(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        for _ in range(5):
            harness.relay.record_tool(
                "bg-agent-001", "Bash", agent_type="Explore", session_id=SESSION_ID
            )
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_type", "Explore")
        assert len(agent_spans) == 1, "Agent span created only once"

    def test_end_agent_creates_summary_for_lazy_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Tools arrive before end_agent (no start_agent)
        harness.relay.record_tool(
            "bg-agent-001", "Bash", agent_type="Explore", session_id=SESSION_ID
        )
        harness.relay.end_agent("bg-agent-001", "Done", agent_type="Explore", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        summaries = harness.spans_named("agent-summary")
        assert len(summaries) >= 1
        summary = summaries[-1]
        assert summary.attributes["praxion.tool_count"] == 1

    def test_end_agent_without_prior_tools_creates_agent_span(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # end_agent arrives with no prior tool events or start_agent
        harness.relay.end_agent(
            "bg-agent-001", "Done", agent_type="plugin-dev:plugin-validator", session_id=SESSION_ID
        )
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute(
            "praxion.agent_type", "plugin-dev:plugin-validator"
        )
        assert len(agent_spans) == 1

    def test_explicit_start_agent_not_overwritten_by_lazy(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Normal flow: start_agent then tools
        harness.relay.start_agent("fg-agent-001", "i-am:researcher", SESSION_ID)
        harness.relay.record_tool(
            "fg-agent-001", "Bash", agent_type="i-am:researcher", session_id=SESSION_ID
        )
        harness.relay.end_agent(
            "fg-agent-001", "Done", agent_type="i-am:researcher", session_id=SESSION_ID
        )
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_type", "researcher")
        assert len(agent_spans) == 1, "Explicit agent span not duplicated by lazy check"


# ---------------------------------------------------------------------------
# Tool duration correlation (Phase 2 -- ADR 052)
# ---------------------------------------------------------------------------


class TestToolDurationCorrelation:
    """Paired PreToolUse/PostToolUse events produce a single span with real duration."""

    def _start_session(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)

    def test_start_tool_opens_span_but_does_not_finish_it(self, harness: OTelRelayTestHarness):
        self._start_session(harness)
        harness.relay.start_tool(
            tool_use_id="toolu_pending",
            agent_id="",
            tool_name="Bash",
            session_id=SESSION_ID,
        )
        # Span is held open -- must not appear in finished exports yet
        pending_spans = [s for s in harness.finished_spans if s.name == "Bash"]
        assert pending_spans == []

    def test_record_tool_after_start_produces_one_span_with_real_duration(
        self, harness: OTelRelayTestHarness
    ):
        self._start_session(harness)
        from datetime import UTC, datetime, timedelta

        start_ts = datetime.now(UTC)
        end_ts = start_ts + timedelta(milliseconds=250)

        harness.relay.start_tool(
            tool_use_id="toolu_timed",
            agent_id="",
            tool_name="Bash",
            session_id=SESSION_ID,
            timestamp=start_ts,
        )
        harness.relay.record_tool(
            "",
            "Bash",
            output_summary="ok",
            session_id=SESSION_ID,
            tool_use_id="toolu_timed",
            end_timestamp=end_ts,
        )

        bash_spans = harness.spans_named("Bash")
        assert len(bash_spans) == 1
        span = bash_spans[0]
        duration_ns = span.end_time - span.start_time
        # Expected ~250 ms; assert comfortably above 200 ms to tolerate clock skew
        assert duration_ns > 200_000_000

    def test_record_tool_without_prior_start_uses_fallback_instant_span(
        self, harness: OTelRelayTestHarness
    ):
        self._start_session(harness)
        # No start_tool call; record_tool should fall through to instant-span path
        harness.relay.record_tool(
            "",
            "Read",
            input_summary="file=/tmp/x",
            output_summary="contents",
            session_id=SESSION_ID,
            tool_use_id="toolu_unpaired",
        )
        read_spans = harness.spans_named("Read")
        assert len(read_spans) == 1

    def test_record_tool_without_tool_use_id_uses_fallback(self, harness: OTelRelayTestHarness):
        self._start_session(harness)
        harness.relay.record_tool(
            "",
            "Grep",
            input_summary="pattern=foo",
            output_summary="found",
            session_id=SESSION_ID,
            # tool_use_id omitted -- must still produce an instant span
        )
        assert len(harness.spans_named("Grep")) == 1

    def test_start_tool_with_empty_tool_use_id_is_noop(self, harness: OTelRelayTestHarness):
        self._start_session(harness)
        harness.relay.start_tool(
            tool_use_id="",
            agent_id="",
            tool_name="Bash",
            session_id=SESSION_ID,
        )
        # Nothing open, nothing tracked -- verify via the private dict
        assert harness.relay._open_tool_spans == {}

    def test_duplicate_start_tool_keeps_first_span(self, harness: OTelRelayTestHarness):
        self._start_session(harness)
        harness.relay.start_tool(
            tool_use_id="toolu_dup", agent_id="", tool_name="Bash", session_id=SESSION_ID
        )
        first_span = harness.relay._open_tool_spans["toolu_dup"]
        harness.relay.start_tool(
            tool_use_id="toolu_dup", agent_id="", tool_name="Bash", session_id=SESSION_ID
        )
        assert harness.relay._open_tool_spans["toolu_dup"] is first_span

    def test_paired_tool_span_with_error_sets_error_status(self, harness: OTelRelayTestHarness):
        self._start_session(harness)
        harness.relay.start_tool(
            tool_use_id="toolu_err", agent_id="", tool_name="Bash", session_id=SESSION_ID
        )
        harness.relay.record_tool(
            "",
            "Bash",
            is_error=True,
            error_msg="exit 1",
            session_id=SESSION_ID,
            tool_use_id="toolu_err",
        )
        span = harness.spans_named("Bash")[0]
        assert span.status.status_code == StatusCode.ERROR

    def test_paired_mcp_tool_preserves_mcp_attributes(self, harness: OTelRelayTestHarness):
        self._start_session(harness)
        harness.relay.start_tool(
            tool_use_id="toolu_mcp",
            agent_id="",
            tool_name="mcp__plugin_i-am_memory__remember",
            session_id=SESSION_ID,
            metadata={
                "artifact_type": "mcp_tool",
                "mcp_server": "memory",
                "mcp_tool": "remember",
            },
        )
        harness.relay.record_tool(
            "",
            "mcp__plugin_i-am_memory__remember",
            session_id=SESSION_ID,
            tool_use_id="toolu_mcp",
            metadata={"artifact_type": "mcp_tool", "mcp_server": "memory", "mcp_tool": "remember"},
        )
        span = harness.spans_named("mcp__plugin_i-am_memory__remember")[0]
        assert span.attributes["praxion.mcp_server"] == "memory"

    def test_orphaned_tool_start_reaped_as_error(self, harness: OTelRelayTestHarness):
        self._start_session(harness)
        harness.relay.start_tool(
            tool_use_id="toolu_orphan", agent_id="", tool_name="Bash", session_id=SESSION_ID
        )
        # Age the pending start past the timeout, then trigger the reaper directly.
        import time as _time

        from task_chronograph_mcp.otel_relay import AGENT_SPAN_TIMEOUT_S

        with harness.relay._span_lock:
            harness.relay._open_tool_start_times["toolu_orphan"] = (
                _time.monotonic() - AGENT_SPAN_TIMEOUT_S - 10
            )
        harness.relay._reap_stale_contexts()

        span = harness.spans_named("Bash")[0]
        assert span.status.status_code == StatusCode.ERROR
        assert "toolu_orphan" not in harness.relay._open_tool_spans


# ---------------------------------------------------------------------------
# Openinference-standard attributes (Phase 3 -- ADR 052)
# ---------------------------------------------------------------------------


class TestToolIdAttribute:
    """tool.id -- Claude Code's tool_use_id -- is the openinference correlation key."""

    def test_paired_tool_span_carries_tool_id_from_pretooluse(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_tool(
            tool_use_id="toolu_paired", agent_id="", tool_name="Bash", session_id=SESSION_ID
        )
        harness.relay.record_tool("", "Bash", session_id=SESSION_ID, tool_use_id="toolu_paired")
        span = harness.spans_named("Bash")[0]
        assert span.attributes["tool.id"] == "toolu_paired"

    def test_fallback_tool_span_with_tool_use_id_carries_tool_id(
        self, harness: OTelRelayTestHarness
    ):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # No start_tool -- fallback path, but tool_use_id still present
        harness.relay.record_tool("", "Read", session_id=SESSION_ID, tool_use_id="toolu_fallback")
        span = harness.spans_named("Read")[0]
        assert span.attributes["tool.id"] == "toolu_fallback"

    def test_fallback_tool_span_without_tool_use_id_omits_tool_id(
        self, harness: OTelRelayTestHarness
    ):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool("", "Grep", session_id=SESSION_ID)
        span = harness.spans_named("Grep")[0]
        assert "tool.id" not in (span.attributes or {})


class TestUserIdAttribute:
    """user.id from git identity must flow from session span to agent spans."""

    def test_session_span_includes_user_id_when_git_identity_available(
        self, harness: OTelRelayTestHarness, monkeypatch
    ):
        from task_chronograph_mcp import otel_relay

        monkeypatch.setattr(otel_relay, "_git_user_id", lambda _p: "test@example.com")
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)
        assert harness.session_span().attributes["user.id"] == "test@example.com"

    def test_session_span_omits_user_id_when_git_identity_missing(
        self, harness: OTelRelayTestHarness, monkeypatch
    ):
        from task_chronograph_mcp import otel_relay

        monkeypatch.setattr(otel_relay, "_git_user_id", lambda _p: "")
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)
        assert "user.id" not in (harness.session_span().attributes or {})

    def test_agent_span_propagates_user_id_from_session(
        self, harness: OTelRelayTestHarness, monkeypatch
    ):
        from task_chronograph_mcp import otel_relay

        monkeypatch.setattr(otel_relay, "_git_user_id", lambda _p: "dev@example.com")
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-u1", "i-am:researcher", SESSION_ID)
        harness.relay.end_agent("agent-u1", "", agent_type="i-am:researcher", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        agent_spans = harness.spans_with_attribute("praxion.agent_type", "researcher")
        assert agent_spans[0].attributes["user.id"] == "dev@example.com"


class TestTranscriptUsageParsing:
    """_parse_transcript_usage must aggregate tokens + infer provider from real transcripts."""

    def _write_transcript(self, path, messages):
        import json

        with path.open("w") as fh:
            for msg in messages:
                fh.write(json.dumps(msg) + "\n")

    def test_aggregates_tokens_across_assistant_messages(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        transcript = tmp_path / "agent.jsonl"
        self._write_transcript(
            transcript,
            [
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-7",
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                    },
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-7",
                        "usage": {"input_tokens": 200, "output_tokens": 75},
                    },
                },
            ],
        )
        attrs = _parse_transcript_usage(str(transcript))
        assert attrs["llm.token_count.prompt"] == 300
        assert attrs["llm.token_count.completion"] == 125
        assert attrs["llm.token_count.total"] == 425

    def test_cache_tokens_added_to_prompt_total(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        transcript = tmp_path / "agent.jsonl"
        self._write_transcript(
            transcript,
            [
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-7",
                        "usage": {
                            "input_tokens": 10,
                            "cache_creation_input_tokens": 1000,
                            "cache_read_input_tokens": 500,
                            "output_tokens": 20,
                        },
                    },
                },
            ],
        )
        attrs = _parse_transcript_usage(str(transcript))
        assert attrs["llm.token_count.prompt"] == 1510

    def test_infers_anthropic_system_from_claude_model(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        transcript = tmp_path / "agent.jsonl"
        self._write_transcript(
            transcript,
            [
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-7",
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                },
            ],
        )
        attrs = _parse_transcript_usage(str(transcript))
        assert attrs["llm.system"] == "anthropic"
        assert attrs["llm.provider"] == "anthropic"
        assert attrs["llm.model_name"] == "claude-opus-4-7"

    def test_missing_file_returns_empty_dict(self, monkeypatch):
        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        assert _parse_transcript_usage("/nonexistent/path/agent.jsonl") == {}

    def test_empty_path_returns_empty_dict(self, monkeypatch):
        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        assert _parse_transcript_usage("") == {}

    def test_malformed_json_line_skipped_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        transcript = tmp_path / "agent.jsonl"
        transcript.write_text(
            "this is not json\n"
            '{"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-4-7", '
            '"usage": {"input_tokens": 5, "output_tokens": 3}}}\n'
        )
        attrs = _parse_transcript_usage(str(transcript))
        assert attrs["llm.token_count.total"] == 8

    def test_strip_env_flag_suppresses_all_llm_attrs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHRONOGRAPH_STRIP_LLM_ATTRS", "1")
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        transcript = tmp_path / "agent.jsonl"
        self._write_transcript(
            transcript,
            [
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-opus-4-7",
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                    },
                },
            ],
        )
        assert _parse_transcript_usage(str(transcript)) == {}

    def test_transcript_without_usage_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        from task_chronograph_mcp.otel_relay import _parse_transcript_usage

        transcript = tmp_path / "agent.jsonl"
        self._write_transcript(
            transcript,
            [{"type": "user", "message": {"role": "user", "content": "hi"}}],
        )
        assert _parse_transcript_usage(str(transcript)) == {}


class TestEndAgentLlmAttrs:
    """end_agent must fold transcript-derived LLM attributes into agent-summary spans."""

    def test_end_agent_sets_llm_attrs_when_transcript_provided(
        self, harness: OTelRelayTestHarness, tmp_path, monkeypatch
    ):
        import json

        monkeypatch.delenv("CHRONOGRAPH_STRIP_LLM_ATTRS", raising=False)
        transcript = tmp_path / "agent.jsonl"
        with transcript.open("w") as fh:
            fh.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "model": "claude-opus-4-7",
                            "usage": {"input_tokens": 42, "output_tokens": 17},
                        },
                    }
                )
                + "\n"
            )
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-t1", "i-am:researcher", SESSION_ID)
        harness.relay.end_agent(
            "agent-t1",
            "done",
            agent_type="i-am:researcher",
            session_id=SESSION_ID,
            transcript_path=str(transcript),
        )
        harness.relay.end_session(SESSION_ID)

        summaries = harness.spans_named("agent-summary")
        summary = summaries[-1]
        assert summary.attributes["llm.token_count.prompt"] == 42
        assert summary.attributes["llm.token_count.completion"] == 17
        assert summary.attributes["llm.model_name"] == "claude-opus-4-7"

    def test_end_agent_without_transcript_omits_llm_attrs(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-t2", "i-am:researcher", SESSION_ID)
        harness.relay.end_agent(
            "agent-t2", "done", agent_type="i-am:researcher", session_id=SESSION_ID
        )
        harness.relay.end_session(SESSION_ID)

        summaries = harness.spans_named("agent-summary")
        summary = summaries[-1]
        assert "llm.token_count.total" not in (summary.attributes or {})


# ---------------------------------------------------------------------------
# Fork-group clustering and agent rollups (Phase 4 -- ADR 052)
# ---------------------------------------------------------------------------


class TestForkGroupClustering:
    """Subagents spawned within the clustering window share a fork_group UUID."""

    def test_single_agent_gets_fork_group_with_sibling_index_zero(
        self, harness: OTelRelayTestHarness
    ):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-solo", "i-am:researcher", SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["praxion.fork_group"]  # non-empty UUID
        assert agent.attributes["praxion.sibling_index"] == 0

    def test_concurrent_agents_share_fork_group(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # Two starts with no wait -- well within FORK_CLUSTER_WINDOW_S
        harness.relay.start_agent("agent-a", "i-am:researcher", SESSION_ID)
        harness.relay.start_agent("agent-b", "i-am:implementer", SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        a = harness.spans_with_attribute("praxion.agent_id", "agent-a")[0]
        b = harness.spans_with_attribute("praxion.agent_id", "agent-b")[0]
        assert a.attributes["praxion.fork_group"] == b.attributes["praxion.fork_group"]

    def test_siblings_have_distinct_sibling_index(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-a", "i-am:researcher", SESSION_ID)
        harness.relay.start_agent("agent-b", "i-am:implementer", SESSION_ID)
        harness.relay.start_agent("agent-c", "i-am:verifier", SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        indices = sorted(
            harness.spans_with_attribute("praxion.agent_id", aid)[0].attributes[
                "praxion.sibling_index"
            ]
            for aid in ("agent-a", "agent-b", "agent-c")
        )
        assert indices == [0, 1, 2]

    def test_agents_outside_window_get_new_fork_group(
        self, harness: OTelRelayTestHarness, monkeypatch
    ):
        from task_chronograph_mcp import otel_relay

        # Shrink the window to 0 so two consecutive starts are always "outside"
        monkeypatch.setattr(otel_relay, "FORK_CLUSTER_WINDOW_S", 0.0)
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-a", "i-am:researcher", SESSION_ID)
        import time as _time

        _time.sleep(0.001)
        harness.relay.start_agent("agent-b", "i-am:implementer", SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        a = harness.spans_with_attribute("praxion.agent_id", "agent-a")[0]
        b = harness.spans_with_attribute("praxion.agent_id", "agent-b")[0]
        assert a.attributes["praxion.fork_group"] != b.attributes["praxion.fork_group"]
        assert b.attributes["praxion.sibling_index"] == 0


class TestSessionLevelPhase4Attrs:
    """git.sha and pipeline_tier surface on session + agent spans."""

    def test_session_span_includes_git_sha_when_available(
        self, harness: OTelRelayTestHarness, monkeypatch
    ):
        from task_chronograph_mcp import otel_relay

        monkeypatch.setattr(otel_relay, "_git_head_sha", lambda _p: "abc1234")
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)
        assert harness.session_span().attributes["praxion.git.sha"] == "abc1234"

    def test_session_span_includes_pipeline_tier_when_available(
        self, harness: OTelRelayTestHarness, monkeypatch
    ):
        from task_chronograph_mcp import otel_relay

        monkeypatch.setattr(otel_relay, "_read_pipeline_tier", lambda _p: "Standard")
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.end_session(SESSION_ID)
        assert harness.session_span().attributes["praxion.pipeline_tier"] == "Standard"

    def test_agent_span_inherits_git_sha_and_tier(self, harness: OTelRelayTestHarness, monkeypatch):
        from task_chronograph_mcp import otel_relay

        monkeypatch.setattr(otel_relay, "_git_head_sha", lambda _p: "deadbee")
        monkeypatch.setattr(otel_relay, "_read_pipeline_tier", lambda _p: "Full")
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-gsh", "i-am:researcher", SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_id", "agent-gsh")[0]
        assert agent.attributes["praxion.git.sha"] == "deadbee"
        assert agent.attributes["praxion.pipeline_tier"] == "Full"


class TestToolSpanPhase4Attrs:
    """I/O byte counts and hook_event flow onto tool spans (paired + fallback)."""

    def test_paired_tool_span_carries_io_bytes_and_hook_event(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_tool(
            tool_use_id="toolu_io",
            agent_id="",
            tool_name="Bash",
            session_id=SESSION_ID,
            metadata={
                "input_size_bytes": 1234,
                "hook_event": "PreToolUse",
            },
        )
        harness.relay.record_tool(
            "",
            "Bash",
            session_id=SESSION_ID,
            tool_use_id="toolu_io",
            metadata={
                "output_size_bytes": 5678,
                "hook_event": "PostToolUse",
            },
        )
        span = harness.spans_named("Bash")[0]
        # Input bytes come from the start metadata; output bytes from the finalize metadata
        assert span.attributes["praxion.io.output_size_bytes"] == 5678
        # hook_event from the finalize path wins (PostToolUse fires last)
        assert span.attributes["praxion.hook_event"] == "PostToolUse"

    def test_fallback_tool_span_carries_io_bytes(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(
            "",
            "Read",
            session_id=SESSION_ID,
            metadata={
                "input_size_bytes": 100,
                "output_size_bytes": 200,
                "hook_event": "PostToolUse",
            },
        )
        span = harness.spans_named("Read")[0]
        assert span.attributes["praxion.io.input_size_bytes"] == 100
        assert span.attributes["praxion.io.output_size_bytes"] == 200
        assert span.attributes["praxion.hook_event"] == "PostToolUse"


class TestAgentSummaryRollups:
    """end_agent rolls up duration_ms, tools_used, skills_used, delegated_to."""

    def test_agent_summary_includes_duration_ms(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-dur", "i-am:researcher", SESSION_ID)
        harness.relay.end_agent(
            "agent-dur", "", agent_type="i-am:researcher", session_id=SESSION_ID
        )
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("agent-summary")[-1]
        assert isinstance(summary.attributes["praxion.agent.duration_ms"], int)
        assert summary.attributes["praxion.agent.duration_ms"] >= 0

    def test_agent_summary_includes_tools_used_set(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-tu", "i-am:researcher", SESSION_ID)
        harness.relay.record_tool(
            "agent-tu", "Bash", agent_type="i-am:researcher", session_id=SESSION_ID
        )
        harness.relay.record_tool(
            "agent-tu", "Read", agent_type="i-am:researcher", session_id=SESSION_ID
        )
        harness.relay.record_tool(
            "agent-tu", "Bash", agent_type="i-am:researcher", session_id=SESSION_ID
        )  # duplicate
        harness.relay.end_agent("agent-tu", "", agent_type="i-am:researcher", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("agent-summary")[-1]
        tools = list(summary.attributes["praxion.agent.tools_used"])
        assert tools == ["Bash", "Read"]  # sorted, deduped

    def test_agent_summary_includes_skills_used(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-sk", "i-am:researcher", SESSION_ID)
        harness.relay.record_skill("agent-sk", "python-development", session_id=SESSION_ID)
        harness.relay.record_skill("agent-sk", "testing-strategy", session_id=SESSION_ID)
        harness.relay.end_agent("agent-sk", "", agent_type="i-am:researcher", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        summary = harness.spans_named("agent-summary")[-1]
        skills = list(summary.attributes["praxion.agent.skills_used"])
        assert skills == ["python-development", "testing-strategy"]

    def test_agent_summary_includes_delegated_to_children(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        # main-agent spawns two children
        harness.relay.start_agent("agent-child-a", "i-am:researcher", SESSION_ID)
        harness.relay.start_agent("agent-child-b", "i-am:implementer", SESSION_ID)
        harness.relay.end_agent(
            "agent-child-a", "", agent_type="i-am:researcher", session_id=SESSION_ID
        )
        harness.relay.end_agent(
            "agent-child-b", "", agent_type="i-am:implementer", session_id=SESSION_ID
        )
        # Force main-agent to end so we get its summary (end_session alone won't)
        harness.relay.end_agent("__main_agent__", "", session_id=SESSION_ID)
        harness.relay.end_session(SESSION_ID)

        # Find the main-agent's summary span (not the children's)
        main_summary = None
        for s in harness.spans_named("agent-summary"):
            delegated = s.attributes.get("praxion.agent.delegated_to")
            if delegated:
                main_summary = s
                break
        assert main_summary is not None
        delegated = list(main_summary.attributes["praxion.agent.delegated_to"])
        assert "researcher" in delegated
        assert "implementer" in delegated
