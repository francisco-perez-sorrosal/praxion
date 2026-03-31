"""OTel relay: translates chronograph events into OpenTelemetry spans for Phoenix."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import UTC, datetime
from typing import Any

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import context as context_api
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    SpanKind,
    StatusCode,
    TraceFlags,
    set_span_in_context,
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

# Trace type values
TRACE_TYPE_PIPELINE = "pipeline"
TRACE_TYPE_NATIVE = "native"


def _is_otel_enabled() -> bool:
    return os.environ.get(OTEL_ENABLED_ENV, "true").lower() in ("true", "1", "yes")


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


def _generate_trace_id(session_id: str) -> int:
    """Deterministic 128-bit trace ID derived from the session ID."""
    return int.from_bytes(hashlib.sha256(session_id.encode()).digest()[:16], "big")


def _generate_span_id_seed(session_id: str) -> int:
    """Generate a 64-bit span ID seed from the session ID (bytes 16-24 of the hash)."""
    return int.from_bytes(hashlib.sha256(session_id.encode()).digest()[16:24], "big")


class OTelRelay:
    """Translates chronograph events into OpenTelemetry spans exported to Phoenix.

    All public methods are fail-open: exceptions are logged as warnings and
    never propagate to the caller.  This ensures the EventStore path is never
    disrupted by OTel failures.
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
        self._span_map: dict[str, trace.Span] = {}
        self._session_span: trace.Span | None = None
        self._session_context: context_api.Context | None = None
        self._trace_type_set = False

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self, session_id: str, project_dir: str) -> None:
        """Initialise the TracerProvider and open the root SESSION span."""
        if not _is_otel_enabled():
            return
        try:
            self._init_provider(project_dir)
            self._open_session_span(session_id, project_dir)
        except Exception:
            logger.warning("Failed to start OTel session", exc_info=True)

    def end_session(self, session_id: str) -> None:
        """End the root SESSION span and flush the exporter."""
        if not _is_otel_enabled():
            return
        try:
            if self._session_span is not None:
                self._session_span.end()
                self._session_span = None
                self._session_context = None
            if self._provider is not None:
                self._provider.force_flush()
        except Exception:
            logger.warning("Failed to end OTel session", exc_info=True)

    def shutdown(self) -> None:
        """Shut down the TracerProvider, releasing all resources."""
        try:
            if self._provider is not None:
                self._provider.shutdown()
                self._provider = None
                self._tracer = None
        except Exception:
            logger.warning("Failed to shutdown OTel provider", exc_info=True)

    def _ensure_initialized(self, session_id: str = "", project_dir: str = "") -> bool:
        """Lazy init: if no session was started, initialise from available context.

        Returns True if the relay is ready to create spans.
        """
        if self._provider is not None:
            return True
        if not _is_otel_enabled():
            return False
        # Auto-initialize with best-effort project info
        effective_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", "")
        self._init_provider(effective_dir)
        if session_id and self._session_span is None:
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
    ) -> None:
        """Open an AGENT child span under the session root."""
        if not _is_otel_enabled():
            return
        try:
            self._ensure_initialized(session_id)
            self._start_agent_span(agent_id, agent_type, session_id, parent_session_id)
        except Exception:
            logger.warning("Failed to start OTel agent span for %s", agent_id, exc_info=True)

    def end_agent(self, agent_id: str, output: str = "") -> None:
        """Set the output value and end the AGENT span."""
        if not _is_otel_enabled():
            return
        try:
            span = self._span_map.pop(agent_id, None)
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
    ) -> None:
        """Create a TOOL child span under the given agent (or session root)."""
        if not _is_otel_enabled():
            return
        try:
            self._ensure_initialized()
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
            span = self._span_map.get(agent_id)
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
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=self._endpoint)

        self._provider.add_span_processor(SimpleSpanProcessor(exporter))
        self._tracer = self._provider.get_tracer(TRACER_NAME)

    def _open_session_span(self, session_id: str, project_dir: str) -> None:
        """Start the root SESSION span with a deterministic trace ID."""
        if self._tracer is None:
            return

        trace_id = _generate_trace_id(session_id)
        span_id_seed = _generate_span_id_seed(session_id)

        # Build a synthetic parent context carrying our deterministic trace_id
        parent_ctx = SpanContext(
            trace_id=trace_id,
            span_id=span_id_seed,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        parent_span = NonRecordingSpan(parent_ctx)
        ctx = set_span_in_context(parent_span)

        project_name = os.path.basename(project_dir) if project_dir else self._default_project_name

        self._session_span = self._tracer.start_span(
            name="session",
            context=ctx,
            kind=SpanKind.INTERNAL,
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
                SpanAttributes.SESSION_ID: session_id,
                "praxion.project_name": project_name,
                "praxion.project_dir": project_dir,
                "praxion.session_start": datetime.now(UTC).isoformat(),
            },
        )
        self._session_context = trace.set_span_in_context(self._session_span)
        self._trace_type_set = False

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

        # Lazily set trace_type on the session span
        if not self._trace_type_set and self._session_span is not None:
            trace_type = TRACE_TYPE_PIPELINE if origin == "praxion" else TRACE_TYPE_NATIVE
            self._session_span.set_attribute("praxion.trace_type", trace_type)
            self._trace_type_set = True

        span = self._tracer.start_span(
            name=clean_type,
            context=self._session_context,
            kind=SpanKind.INTERNAL,
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                "praxion.agent_type": clean_type,
                "praxion.agent_origin": origin,
                "praxion.agent_id": agent_id,
                "praxion.session_id": session_id,
                "praxion.parent_session_id": parent_session_id,
            },
        )
        self._span_map[agent_id] = span

    def _record_tool_span(
        self,
        agent_id: str,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        is_error: bool,
        error_msg: str,
    ) -> None:
        """Create a TOOL span as a child of the agent span or session root."""
        if self._tracer is None:
            return

        # Determine parent: agent span if available, else session root
        parent_span = self._span_map.get(agent_id) if agent_id else None
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
