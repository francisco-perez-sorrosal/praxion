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

    def test_agent_span_is_child_of_session_root(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]

        assert agent.parent is not None
        assert agent.parent.span_id == root.context.span_id
        assert agent.context.trace_id == root.context.trace_id

    def test_agent_span_kind_is_agent(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Done")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["openinference.span.kind"] == "AGENT"

    def test_agent_stop_sets_output_value(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-r1", "researcher", SESSION_ID)
        harness.relay.end_agent("agent-r1", "Findings: auth uses OAuth2")
        harness.relay.end_session(SESSION_ID)

        agent = harness.spans_with_attribute("praxion.agent_type", "researcher")[0]
        assert agent.attributes["output.value"] == "Findings: auth uses OAuth2"

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

    def test_tool_span_under_session_root_when_unknown_agent_id(
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
        root = harness.session_span()
        assert tool.parent is not None
        assert tool.parent.span_id == root.context.span_id

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
    """Verify parallel agents both parent under session root, not nested."""

    def test_parallel_agents_are_siblings_under_session_root(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-i1", "implementer", SESSION_ID)
        harness.relay.start_agent("agent-t1", "test-engineer", SESSION_ID)
        harness.relay.end_agent("agent-i1", "Code written")
        harness.relay.end_agent("agent-t1", "Tests written")
        harness.relay.end_session(SESSION_ID)

        root = harness.session_span()
        impl_span = harness.spans_with_attribute("praxion.agent_id", "agent-i1")[0]
        test_span = harness.spans_with_attribute("praxion.agent_id", "agent-t1")[0]

        # Both should be children of the root span
        assert impl_span.parent.span_id == root.context.span_id
        assert test_span.parent.span_id == root.context.span_id

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
    """Verify phase transitions appear as events on the agent span."""

    def test_phase_event_appears_on_agent_span(self, harness: OTelRelayTestHarness):
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

        agent = harness.spans_with_attribute("praxion.agent_id", "agent-r1")[0]
        phase_events = [e for e in agent.events if e.name == "phase_transition"]
        assert len(phase_events) == 1

        event = phase_events[0]
        assert event.attributes["phase.number"] == 2
        assert event.attributes["phase.total"] == 5
        assert event.attributes["phase.name"] == "analysis"
        assert event.attributes["phase.summary"] == "Analyzing auth libraries"


# ---------------------------------------------------------------------------
# 7. Decision event on agent span
# ---------------------------------------------------------------------------


class TestDecisionEvent:
    """Verify decision records appear as events on the agent span."""

    def test_decision_event_appears_on_agent_span(self, harness: OTelRelayTestHarness):
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

        agent = harness.spans_with_attribute("praxion.agent_id", "agent-sa1")[0]
        decision_events = [e for e in agent.events if e.name == "decision_made"]
        assert len(decision_events) == 1

        event = decision_events[0]
        assert event.attributes["decision.id"] == "dec-abc123"
        assert event.attributes["decision.category"] == "architectural"
        assert event.attributes["decision.text"] == "Use event sourcing for state management"


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

    def test_main_agent_ended_on_session_end(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.record_tool(agent_id="", tool_name="Bash", input_summary="echo hi")
        harness.relay.end_session(SESSION_ID)

        main = harness.spans_with_attribute("praxion.agent_id", "__main_agent__")[0]
        assert main.end_time is not None
        assert main.end_time > main.start_time


# ---------------------------------------------------------------------------
# 14. Span reaper
# ---------------------------------------------------------------------------


class TestSpanReaper:
    """Verify the background span reaper for stale agent spans."""

    def test_stale_agent_span_reaped(self, harness: OTelRelayTestHarness):
        import task_chronograph_mcp.otel_relay as relay_mod

        orig_timeout = relay_mod.AGENT_SPAN_TIMEOUT_S
        relay_mod.AGENT_SPAN_TIMEOUT_S = 0.1  # 100ms for testing
        try:
            harness.relay.start_session(SESSION_ID, harness.project_dir)
            harness.relay.start_agent("bg-agent", "i-am:verifier", SESSION_ID)
            harness.relay.record_tool(agent_id="bg-agent", tool_name="Read", input_summary="f.py")

            # Wait for reaper to detect inactivity
            import time

            time.sleep(0.5)

            # Manually trigger reap (reaper thread may not have run yet)
            harness.relay._reap_stale_spans()

            harness.relay.end_session(SESSION_ID)

            reaped = [
                s
                for s in harness.exporter.get_finished_spans()
                if s.attributes.get("praxion.reaped") is True and s.name == "verifier"
            ]
            assert len(reaped) == 1
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

            harness.relay._reap_stale_spans()

            # Agent should still be in span map (not reaped)
            with harness.relay._span_lock:
                assert "active-agent" in harness.relay._span_map

            harness.relay.end_agent("active-agent")
            harness.relay.end_session(SESSION_ID)
        finally:
            relay_mod.AGENT_SPAN_TIMEOUT_S = orig_timeout

    def test_explicit_stop_prevents_reap(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)
        harness.relay.start_agent("agent-x", "i-am:sentinel", SESSION_ID)
        harness.relay.end_agent("agent-x", "Done")

        harness.relay._reap_stale_spans()

        # No reaped spans — agent was explicitly stopped
        reaped = [
            s
            for s in harness.exporter.get_finished_spans()
            if s.attributes.get("praxion.reaped") is True
        ]
        assert len(reaped) == 0
        harness.relay.end_session(SESSION_ID)

    def test_reaper_thread_stops_on_shutdown(self, harness: OTelRelayTestHarness):
        harness.relay.start_session(SESSION_ID, harness.project_dir)

        assert harness.relay._reaper_thread is not None
        assert harness.relay._reaper_thread.is_alive()

        harness.relay.shutdown()

        assert harness.relay._reaper_thread is None or not harness.relay._reaper_thread.is_alive()
