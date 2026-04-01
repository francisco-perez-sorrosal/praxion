"""OTel relay: translates chronograph events into OpenTelemetry spans for Phoenix."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import context as context_api
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import (
    SpanKind,
    StatusCode,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"
DEFAULT_PROJECT_NAME = "praxion-default"
OTEL_ENABLED_ENV = "OTEL_ENABLED"
PHOENIX_ENDPOINT_ENV = "PHOENIX_ENDPOINT"
PHOENIX_PROJECT_NAME_ENV = "PHOENIX_PROJECT_NAME"

TRACER_NAME = "praxion.chronograph"

# Agent origin detection prefix
_PRAXION_AGENT_PREFIX = "i-am:"

# Main agent synthetic span
MAIN_AGENT_ID = "__main_agent__"
MAIN_AGENT_TYPE = "main-agent"

# Trace type values
TRACE_TYPE_PIPELINE = "pipeline"
TRACE_TYPE_NATIVE = "native"

# Span reaper configuration
AGENT_SPAN_TIMEOUT_S = 60  # seconds of inactivity before reaping
REAPER_INTERVAL_S = 10  # seconds between reaper sweeps


def _is_otel_enabled() -> bool:
    """OTel export is enabled by default via plugin.json.

    Can be disabled by setting OTEL_ENABLED=false for debugging.
    """
    return os.environ.get(OTEL_ENABLED_ENV, "false").lower() in ("true", "1", "yes")


def _detect_agent_origin(agent_type: str) -> str:
    """Determine whether an agent originated from the Praxion pipeline or Claude Code."""
    if agent_type.startswith(_PRAXION_AGENT_PREFIX):
        return "praxion"
    return "claude-code"


def _clean_agent_type(agent_type: str) -> str:
    """Strip the ``i-am:`` prefix if present to get the bare agent type name."""
    if agent_type.startswith(_PRAXION_AGENT_PREFIX):
        return agent_type[len(_PRAXION_AGENT_PREFIX) :]
    return agent_type


class OTelRelay:
    """Translates chronograph events into OpenTelemetry spans exported to Phoenix.

    All public methods are fail-open: exceptions are logged as warnings and
    never propagate to the caller.  This ensures the EventStore path is never
    disrupted by OTel failures.

    A background reaper thread ends agent spans that have had no tool activity
    for ``AGENT_SPAN_TIMEOUT_S`` seconds. This compensates for SubagentStop
    hooks not firing for background agents.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        default_project_name: str | None = None,
        *,
        exporter: SpanExporter | None = None,
    ) -> None:
        self._endpoint = endpoint or os.environ.get(PHOENIX_ENDPOINT_ENV, DEFAULT_PHOENIX_ENDPOINT)
        self._default_project_name = default_project_name or os.environ.get(
            PHOENIX_PROJECT_NAME_ENV, DEFAULT_PROJECT_NAME
        )
        # Allow injecting a custom exporter (e.g. InMemorySpanExporter for tests)
        self._custom_exporter = exporter

        self._provider: TracerProvider | None = None
        self._tracer: trace.Tracer | None = None

        # Span tracking — protected by _span_lock
        self._span_lock = threading.Lock()
        self._span_map: dict[str, trace.Span] = {}
        self._span_last_activity: dict[str, float] = {}

        self._session_span: trace.Span | None = None
        self._session_context: context_api.Context | None = None
        self._trace_type_set = False

        # Reaper thread
        self._reaper_stop = threading.Event()
        self._reaper_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self, session_id: str, project_dir: str) -> None:
        """Initialise the TracerProvider and open the root SESSION span.

        The chronograph-ctl instance persists across Claude Code session
        restarts. The TracerProvider is reused, but each new session gets
        its own root span. Duplicate session_start events within the same
        session are deduplicated via ``_session_context``.
        """
        if not _is_otel_enabled():
            return
        if self._session_context is not None:
            return  # already have an active session — skip duplicate
        try:
            if self._provider is None:
                self._init_provider(project_dir)
            self._open_session_span(session_id, project_dir)
        except Exception:
            logger.warning("Failed to start OTel session", exc_info=True)

    def end_session(self, session_id: str) -> None:
        """End all open agent spans, flush, and clear session state.

        The root span was already ended in ``_open_session_span``. This
        ends any orphaned agent spans, flushes, and resets so the next
        ``start_session`` can create a fresh root span.
        """
        if not _is_otel_enabled():
            return
        try:
            with self._span_lock:
                spans_to_end = list(self._span_map.items())
                self._span_map.clear()
                self._span_last_activity.clear()
            for _agent_id, span in spans_to_end:
                try:
                    span.end()
                except Exception:
                    logger.debug("Failed to end orphaned span %s", _agent_id)
            self._session_span = None
            self._session_context = None
            self._trace_type_set = False
            if self._provider is not None:
                self._provider.force_flush()
        except Exception:
            logger.warning("Failed to end OTel session", exc_info=True)

    def shutdown(self) -> None:
        """Shut down the TracerProvider and reaper thread, releasing all resources."""
        try:
            self._reaper_stop.set()
            if self._reaper_thread is not None:
                self._reaper_thread.join(timeout=5)
                self._reaper_thread = None
            if self._provider is not None:
                self._provider.shutdown()
                self._provider = None
                self._tracer = None
        except Exception:
            logger.warning("Failed to shutdown OTel provider", exc_info=True)

    def _ensure_initialized(self, session_id: str = "", project_dir: str = "") -> bool:
        """Lazy init: if no session was started, initialise from available context.

        Uses the first available project_dir from: the event, CLAUDE_PROJECT_DIR
        env, or cwd (which Claude Code sets to the project directory for hooks).
        Returns True if the relay is ready to create spans.
        """
        if not _is_otel_enabled():
            return False
        effective_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", "")
        if not effective_dir or effective_dir == "/":
            effective_dir = ""  # let it fall back to default_project_name
        if self._provider is None:
            self._init_provider(effective_dir)
        if session_id and self._session_context is None:
            self._open_session_span(session_id, effective_dir)
        return self._provider is not None

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def start_agent(
        self,
        agent_id: str,
        agent_type: str,
        session_id: str,
        parent_session_id: str = "",
        *,
        project_dir: str = "",
    ) -> None:
        """Open an AGENT child span under the session root."""
        if not _is_otel_enabled():
            return
        try:
            self._ensure_initialized(session_id, project_dir=project_dir)
            self._start_agent_span(agent_id, agent_type, session_id, parent_session_id)
        except Exception:
            logger.warning("Failed to start OTel agent span for %s", agent_id, exc_info=True)

    def end_agent(self, agent_id: str, output: str = "") -> None:
        """Set the output value and end the AGENT span."""
        if not _is_otel_enabled():
            return
        try:
            with self._span_lock:
                span = self._span_map.pop(agent_id, None)
                self._span_last_activity.pop(agent_id, None)
            if span is None:
                logger.debug("No span found for agent_id=%s", agent_id)
                return
            if output:
                span.set_attribute(SpanAttributes.OUTPUT_VALUE, output)
            span.end()
        except Exception:
            logger.warning("Failed to end OTel agent span for %s", agent_id, exc_info=True)

    # ------------------------------------------------------------------
    # Tool recording
    # ------------------------------------------------------------------

    def record_tool(
        self,
        agent_id: str,
        tool_name: str,
        input_summary: str = "",
        output_summary: str = "",
        *,
        is_error: bool = False,
        error_msg: str = "",
        session_id: str = "",
        project_dir: str = "",
    ) -> None:
        """Create a TOOL child span under the given agent (or main agent)."""
        if not _is_otel_enabled():
            return
        try:
            self._ensure_initialized(session_id, project_dir=project_dir)
            self._record_tool_span(
                agent_id, tool_name, input_summary, output_summary, is_error, error_msg
            )
        except Exception:
            logger.warning("Failed to record OTel tool span for %s", tool_name, exc_info=True)

    # ------------------------------------------------------------------
    # Span events
    # ------------------------------------------------------------------

    def add_phase_event(
        self,
        agent_id: str,
        phase: int,
        total: int,
        name: str,
        summary: str,
    ) -> None:
        """Add a ``phase_transition`` event to the given agent span."""
        if not _is_otel_enabled():
            return
        try:
            with self._span_lock:
                span = self._span_map.get(agent_id)
                if agent_id in self._span_last_activity:
                    self._span_last_activity[agent_id] = time.monotonic()
            if span is None:
                logger.debug("No span for phase event, agent_id=%s", agent_id)
                return
            span.add_event(
                "phase_transition",
                attributes={
                    "phase.number": phase,
                    "phase.total": total,
                    "phase.name": name,
                    "phase.summary": summary,
                    "agent.type": agent_id,
                },
            )
        except Exception:
            logger.warning("Failed to add phase event for %s", agent_id, exc_info=True)

    def add_decision_event(self, agent_id: str, decision: dict[str, Any]) -> None:
        """Add a ``decision_made`` event to the given agent span.

        *decision* should contain keys ``id``, ``category``, ``text``, and
        ``made_by``.
        """
        if not _is_otel_enabled():
            return
        try:
            with self._span_lock:
                span = self._span_map.get(agent_id)
            if span is None:
                logger.debug("No span for decision event, agent_id=%s", agent_id)
                return
            span.add_event(
                "decision_made",
                attributes={
                    "decision.id": decision.get("id", ""),
                    "decision.category": decision.get("category", ""),
                    "decision.text": decision.get("text", ""),
                    "decision.made_by": decision.get("made_by", ""),
                },
            )
        except Exception:
            logger.warning("Failed to add decision event for %s", agent_id, exc_info=True)

    # ------------------------------------------------------------------
    # Span reaper
    # ------------------------------------------------------------------

    def _start_reaper(self) -> None:
        """Start the background span reaper thread if not already running."""
        if self._reaper_thread is not None:
            return
        self._reaper_stop.clear()
        self._reaper_thread = threading.Thread(
            target=self._reaper_loop,
            daemon=True,
            name="otel-span-reaper",
        )
        self._reaper_thread.start()

    def _reaper_loop(self) -> None:
        """Periodically check for and end stale agent spans."""
        while not self._reaper_stop.wait(REAPER_INTERVAL_S):
            self._reap_stale_spans()

    def _reap_stale_spans(self) -> None:
        """End agent spans that haven't had activity recently."""
        now = time.monotonic()
        stale: list[tuple[str, trace.Span]] = []

        with self._span_lock:
            for agent_id, last_activity in list(self._span_last_activity.items()):
                if now - last_activity > AGENT_SPAN_TIMEOUT_S:
                    span = self._span_map.pop(agent_id, None)
                    self._span_last_activity.pop(agent_id, None)
                    if span is not None:
                        stale.append((agent_id, span))

        # End spans outside the lock (span.end triggers processor pipeline)
        for agent_id, span in stale:
            try:
                span.set_attribute("praxion.reaped", True)
                span.end()
                logger.info("Reaped stale agent span: %s", agent_id)
            except Exception:
                logger.debug("Failed to reap span %s", agent_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_provider(self, project_dir: str) -> None:
        """Create the TracerProvider with the appropriate exporter and resource."""
        from openinference.semconv.resource import ResourceAttributes

        project_name = os.path.basename(project_dir) if project_dir else self._default_project_name
        resource = Resource.create(
            {
                ResourceAttributes.PROJECT_NAME: project_name,
            }
        )

        self._provider = TracerProvider(resource=resource)

        if self._custom_exporter is not None:
            exporter = self._custom_exporter
            # Use SimpleSpanProcessor for injected exporters (tests)
            # to keep span export deterministic.
            self._provider.add_span_processor(SimpleSpanProcessor(exporter))
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=self._endpoint)
            self._provider.add_span_processor(
                BatchSpanProcessor(
                    exporter,
                    max_queue_size=512,
                    schedule_delay_millis=5000,
                    max_export_batch_size=64,
                )
            )

        self._tracer = self._provider.get_tracer(TRACER_NAME)

    def _open_session_span(self, session_id: str, project_dir: str) -> None:
        """Create the root SESSION span and end it immediately.

        The span is ended right away so Phoenix receives it and shows the
        trace in the Traces view. Child spans (agents, tools) reference
        the root's SpanContext for parent-child linkage — this works even
        after the root span is closed because OTel links by IDs, not by
        live Span objects.

        A synthetic ``main-agent`` AGENT span is also created to parent
        tool calls from the main Claude agent (which has no lifecycle hooks).
        The ``_session_context`` is preserved so child spans can be
        parented under this root throughout the session.
        """
        if self._tracer is None:
            return

        project_name = os.path.basename(project_dir) if project_dir else self._default_project_name

        # No parent context → true root span.
        self._session_span = self._tracer.start_span(
            name="session",
            kind=SpanKind.INTERNAL,
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
                SpanAttributes.SESSION_ID: session_id,
                "praxion.project_name": project_name,
                "praxion.project_dir": project_dir,
                "praxion.session_start": datetime.now(UTC).isoformat(),
            },
        )
        # Capture context BEFORE ending — child spans parent under this.
        self._session_context = trace.set_span_in_context(self._session_span)
        # End immediately so Phoenix receives the root span right away.
        # Child spans still link to it via the saved _session_context.
        self._session_span.end()
        self._trace_type_set = False

        # Create synthetic main-agent span for the main Claude agent.
        # Tool calls with empty agent_id will be parented under this span.
        main_span = self._tracer.start_span(
            name=MAIN_AGENT_TYPE,
            context=self._session_context,
            kind=SpanKind.INTERNAL,
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                "praxion.agent_type": MAIN_AGENT_TYPE,
                "praxion.agent_origin": "claude-code",
                "praxion.agent_id": MAIN_AGENT_ID,
                "praxion.session_id": session_id,
            },
        )
        with self._span_lock:
            self._span_map[MAIN_AGENT_ID] = main_span
            self._span_last_activity[MAIN_AGENT_ID] = time.monotonic()

        # Start reaper to handle background agent span cleanup
        self._start_reaper()

    def _start_agent_span(
        self,
        agent_id: str,
        agent_type: str,
        session_id: str,
        parent_session_id: str,
    ) -> None:
        """Create an AGENT span as a child of the session root."""
        if self._tracer is None or self._session_context is None:
            return

        origin = _detect_agent_origin(agent_type)
        clean_type = _clean_agent_type(agent_type)

        # Set trace_type on each agent span (session span is already ended)
        trace_type = TRACE_TYPE_PIPELINE if origin == "praxion" else TRACE_TYPE_NATIVE

        span = self._tracer.start_span(
            name=clean_type,
            context=self._session_context,
            kind=SpanKind.INTERNAL,
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                "praxion.agent_type": clean_type,
                "praxion.agent_origin": origin,
                "praxion.trace_type": trace_type,
                "praxion.agent_id": agent_id,
                "praxion.session_id": session_id,
                "praxion.parent_session_id": parent_session_id,
            },
        )
        with self._span_lock:
            self._span_map[agent_id] = span
            self._span_last_activity[agent_id] = time.monotonic()

    def _record_tool_span(
        self,
        agent_id: str,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        is_error: bool,
        error_msg: str,
    ) -> None:
        """Create a TOOL span as a child of the agent span or main agent."""
        if self._tracer is None:
            return

        # Determine parent: agent span if available, main agent for empty
        # agent_id, or session root as last resort
        lookup_id = agent_id if agent_id else MAIN_AGENT_ID

        with self._span_lock:
            parent_span = self._span_map.get(lookup_id)
            # Update activity timestamp for the parent agent
            if lookup_id in self._span_last_activity:
                self._span_last_activity[lookup_id] = time.monotonic()

        if parent_span is not None:
            parent_context = trace.set_span_in_context(parent_span)
        elif self._session_context is not None:
            parent_context = self._session_context
        else:
            return

        attributes: dict[str, str] = {
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.TOOL.value,
            SpanAttributes.TOOL_NAME: tool_name,
        }
        if input_summary:
            attributes[SpanAttributes.INPUT_VALUE] = input_summary
        if output_summary:
            attributes[SpanAttributes.OUTPUT_VALUE] = output_summary

        span = self._tracer.start_span(
            name=tool_name,
            context=parent_context,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        )

        if is_error:
            span.set_status(StatusCode.ERROR, error_msg)
            span.add_event(
                "error",
                attributes={
                    "exception.type": "ToolError",
                    "exception.message": error_msg,
                },
            )

        span.end()
