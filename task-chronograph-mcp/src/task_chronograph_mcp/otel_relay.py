"""OTel relay: translates chronograph events into OpenTelemetry spans for Phoenix.

The relay is split across cohesive modules to stay under the file-size ceiling,
joined by a linear inheritance chain (identical runtime behavior to the original
single class):

    relay_helpers      constants + stateless helpers (no internal deps)
    context_tracker    _RelayContextTracking -- shared state + agent-context tracking
    span_factory       _RelaySpanFactory -- span construction (extends the above)
    otel_relay         OTelRelay -- public event-ingestion API (this module)

Symbols that used to live here (the helpers, constants, and context dataclasses)
are re-exported below so existing ``from task_chronograph_mcp.otel_relay import X``
imports keep resolving.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import SpanKind

from .context_tracker import AgentContext, ForkCluster, SessionStats
from .relay_helpers import (
    AGENT_SPAN_TIMEOUT_S,
    AGENT_SPAWN_TOOL_NAME,
    _is_otel_enabled,
    _parse_transcript_usage,
)
from .span_factory import _RelaySpanFactory

logger = logging.getLogger(__name__)

# Re-exported for backward compatibility with importers of the pre-split module.
__all__ = [
    "AGENT_SPAN_TIMEOUT_S",
    "AgentContext",
    "ForkCluster",
    "OTelRelay",
    "SessionStats",
    "_parse_transcript_usage",
]


class OTelRelay(_RelaySpanFactory):
    """Translates chronograph events into OpenTelemetry spans exported to Phoenix.

    All public methods are fail-open: exceptions are logged as warnings and
    never propagate to the caller.  This ensures the EventStore path is never
    disrupted by OTel failures.

    Agent and session spans are ended immediately after creation so that
    Phoenix receives the trace structure right away (the BatchSpanProcessor
    only exports ended spans). Child spans reference their parent's
    SpanContext for linkage -- this works after the parent is closed because
    OTel links by IDs, not by live Span objects.

    Agent spans are parented under their spawning agent (hierarchy-aware),
    not flat under the session root. This produces accurate trace trees
    in Phoenix that reflect the real delegation depth.

    A background reaper thread cleans up stale context entries (agents whose
    SubagentStop hook never fired) to prevent memory leaks.
    """

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        session_id: str,
        project_dir: str,
        git_context: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the TracerProvider and open the root SESSION span.

        The chronograph-ctl instance persists across Claude Code session
        restarts. The TracerProvider is reused, but each new session gets
        its own root span. Duplicate session_start events within the same
        session are deduplicated via ``_session_context``.
        """
        if not _is_otel_enabled():
            return
        if self._session_context is not None:
            return  # already have an active session -- skip duplicate
        try:
            if self._provider is None:
                self._init_provider(project_dir)
            self._open_session_span(session_id, project_dir, git_context or {})
        except Exception:
            logger.warning("Failed to start OTel session", exc_info=True)

    def end_session(self, session_id: str) -> None:
        """Create session summary span, flush pending spans, and clear state.

        All spans (session, agents, tools) are already ended at creation
        time. This method creates a summary span with aggregate stats,
        cleans up tracking state, and flushes the exporter.
        """
        if not _is_otel_enabled():
            return
        try:
            self._create_session_summary()
            with self._span_lock:
                self._agent_contexts.clear()
                self._pending_spawns.clear()
                self._fork_clusters.clear()
            self._session_span = None
            self._session_context = None
            self._session_stats = None
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

    def _ensure_initialized(
        self,
        session_id: str = "",
        project_dir: str = "",
        git_context: dict[str, Any] | None = None,
    ) -> bool:
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
            self._open_session_span(session_id, effective_dir, git_context or {})
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
        git_context: dict[str, Any] | None = None,
        task_slug: str = "",
    ) -> None:
        """Open an AGENT child span under the spawning agent (hierarchy-aware)."""
        if not _is_otel_enabled():
            return
        try:
            self._ensure_initialized(session_id, project_dir=project_dir, git_context=git_context)
            self._start_agent_span(
                agent_id,
                agent_type,
                session_id,
                parent_session_id,
                git_context=git_context or {},
                task_slug=task_slug,
            )
        except Exception:
            logger.warning("Failed to start OTel agent span for %s", agent_id, exc_info=True)

    def end_agent(
        self,
        agent_id: str,
        output: str = "",
        *,
        agent_type: str = "",
        session_id: str = "",
        transcript_path: str = "",
    ) -> None:
        """Record agent completion: create summary span and clean up context.

        Creates an ``agent-summary`` child span carrying output value,
        aggregate stats (tool_count, error_count, child_count), and -- when
        ``transcript_path`` is provided and LLM attrs are not stripped --
        openinference-standard LLM attributes (token counts, model,
        system/provider) parsed from the subagent's JSONL transcript.

        If no agent context exists (SubagentStart hook was skipped for
        background agents), creates a synthetic agent span first so the
        summary still appears in the trace hierarchy.
        """
        if not _is_otel_enabled():
            return
        try:
            self._ensure_agent_context(agent_id, agent_type, session_id)
            with self._span_lock:
                agent_ctx = self._agent_contexts.pop(agent_id, None)
            if agent_ctx is None:
                logger.debug("No context found for agent_id=%s", agent_id)
                return
            if self._tracer is not None:
                duration_ms = int((time.monotonic() - agent_ctx.started_at) * 1000)
                attrs: dict[str, Any] = {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: (
                        OpenInferenceSpanKindValues.CHAIN.value
                    ),
                    SpanAttributes.SESSION_ID: agent_ctx.session_id,
                    "praxion.tool_count": agent_ctx.tool_count,
                    "praxion.error_count": agent_ctx.error_count,
                    "praxion.child_count": agent_ctx.child_count,
                    "praxion.skill_count": agent_ctx.skill_count,
                    "praxion.agent.duration_ms": duration_ms,
                }
                if agent_ctx.tools_used:
                    attrs["praxion.agent.tools_used"] = sorted(agent_ctx.tools_used)
                if agent_ctx.skills_used:
                    attrs["praxion.agent.skills_used"] = sorted(agent_ctx.skills_used)
                if agent_ctx.delegated_to:
                    attrs["praxion.agent.delegated_to"] = list(agent_ctx.delegated_to)
                if output:
                    attrs[SpanAttributes.OUTPUT_VALUE] = output
                if self._session_stats and self._session_stats.user_id:
                    attrs[SpanAttributes.USER_ID] = self._session_stats.user_id
                if transcript_path:
                    attrs.update(_parse_transcript_usage(transcript_path))
                span = self._tracer.start_span(
                    name="agent-summary",
                    context=agent_ctx.otel_context,
                    kind=SpanKind.INTERNAL,
                    attributes=attrs,
                )
                span.end()
        except Exception:
            logger.warning("Failed to end OTel agent span for %s", agent_id, exc_info=True)

    # ------------------------------------------------------------------
    # Tool recording
    # ------------------------------------------------------------------

    def start_tool(
        self,
        tool_use_id: str,
        agent_id: str,
        tool_name: str,
        *,
        timestamp: datetime | None = None,
        input_summary: str = "",
        session_id: str = "",
        project_dir: str = "",
        metadata: dict[str, Any] | None = None,
        agent_type: str = "",
    ) -> None:
        """Open a TOOL span at PreToolUse; held open until record_tool() fires.

        The span is kept in ``_open_tool_spans`` keyed by ``tool_use_id`` so
        PostToolUse can close it with a real end_time, producing a single
        duration-accurate span in Phoenix. A missing or duplicate
        ``tool_use_id`` is a no-op -- the PostToolUse path falls back to an
        instant span.
        """
        if not _is_otel_enabled():
            return
        if not tool_use_id:
            return
        try:
            self._ensure_initialized(session_id, project_dir=project_dir)
            self._ensure_agent_context(agent_id, agent_type, session_id)

            # If this is an Agent-spawn tool call, register the pending spawn
            # so the next SubagentStart can resolve its parent via FIFO.
            if tool_name == AGENT_SPAWN_TOOL_NAME:
                self._register_spawn(agent_id, tool_use_id)

            parent_context = self._get_parent_context(agent_id)
            if parent_context is None or self._tracer is None:
                return

            with self._span_lock:
                if tool_use_id in self._open_tool_spans:
                    return  # duplicate PreToolUse -- keep the earlier span

            start_time_ns: int | None = None
            if timestamp is not None:
                start_time_ns = int(timestamp.timestamp() * 1_000_000_000)

            attributes: dict[str, Any] = {
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.TOOL.value,
                SpanAttributes.TOOL_NAME: tool_name,
                SpanAttributes.TOOL_ID: tool_use_id,
                SpanAttributes.SESSION_ID: self._get_session_id_for_agent(agent_id),
            }
            meta = metadata or {}
            if input_summary:
                attributes[SpanAttributes.INPUT_VALUE] = input_summary
            if meta.get("artifact_type") == "mcp_tool":
                attributes["praxion.artifact_type"] = "mcp_tool"
                attributes["praxion.mcp_server"] = meta.get("mcp_server", "")
                attributes["praxion.mcp_tool"] = meta.get("mcp_tool", "")

            span = self._tracer.start_span(
                name=tool_name,
                context=parent_context,
                kind=SpanKind.INTERNAL,
                attributes=attributes,
                start_time=start_time_ns,
            )
            with self._span_lock:
                self._open_tool_spans[tool_use_id] = span
                self._open_tool_start_times[tool_use_id] = time.monotonic()
        except Exception:
            logger.warning("Failed to start OTel tool span for %s", tool_name, exc_info=True)

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
        metadata: dict[str, Any] | None = None,
        agent_type: str = "",
        tool_use_id: str = "",
        end_timestamp: datetime | None = None,
    ) -> None:
        """Close a paired tool span (when ``tool_use_id`` resolves) or emit instant.

        Pair-correlation path: look up the open span from ``start_tool`` and
        close it with explicit ``end_time`` so Phoenix shows real duration.
        Fallback path: no prior PreToolUse received (or no ``tool_use_id``) --
        emit the legacy instant span to preserve backward compatibility.
        """
        if not _is_otel_enabled():
            return
        try:
            if tool_use_id:
                with self._span_lock:
                    open_span = self._open_tool_spans.pop(tool_use_id, None)
                    self._open_tool_start_times.pop(tool_use_id, None)
                if open_span is not None:
                    self._finalize_tool_span(
                        open_span,
                        agent_id,
                        tool_name,
                        output_summary,
                        is_error,
                        error_msg,
                        metadata or {},
                        end_timestamp,
                    )
                    return
            # Fallback: no paired start -- instant span as before.
            self._ensure_initialized(session_id, project_dir=project_dir)
            self._ensure_agent_context(agent_id, agent_type, session_id)
            self._record_tool_span(
                agent_id,
                tool_name,
                input_summary,
                output_summary,
                is_error,
                error_msg,
                metadata or {},
                tool_use_id=tool_use_id,
            )
        except Exception:
            logger.warning("Failed to record OTel tool span for %s", tool_name, exc_info=True)

    # ------------------------------------------------------------------
    # Artifact recording (skills, commands)
    # ------------------------------------------------------------------

    def record_skill(
        self,
        agent_id: str,
        skill_name: str,
        *,
        session_id: str = "",
        project_dir: str = "",
        args: str = "",
    ) -> None:
        """Create a CHAIN span for a skill invocation under the given agent."""
        if not _is_otel_enabled():
            return
        try:
            self._ensure_initialized(session_id, project_dir=project_dir)
            parent_context = self._get_parent_context(agent_id)
            if parent_context is None or self._tracer is None:
                return
            span = self._tracer.start_span(
                name=f"skill:{skill_name}",
                context=parent_context,
                kind=SpanKind.INTERNAL,
                attributes={
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: (
                        OpenInferenceSpanKindValues.CHAIN.value
                    ),
                    SpanAttributes.SESSION_ID: self._get_session_id_for_agent(agent_id),
                    "praxion.artifact_type": "skill",
                    "praxion.skill_name": skill_name,
                    SpanAttributes.INPUT_VALUE: args,
                },
            )
            span.end()
            self._increment_stat(agent_id, "skill_count")
            self._track_skill_used(agent_id, skill_name)
            if self._session_stats:
                self._session_stats.skill_count += 1
        except Exception:
            logger.warning("Failed to record skill span for %s", skill_name, exc_info=True)

    # ------------------------------------------------------------------
    # Span events (emitted as child spans for immediate Phoenix visibility)
    # ------------------------------------------------------------------

    def add_phase_event(
        self,
        agent_id: str,
        phase: int,
        total: int,
        name: str,
        summary: str,
    ) -> None:
        """Create a ``phase`` child span under the given agent."""
        if not _is_otel_enabled():
            return
        try:
            with self._span_lock:
                agent_ctx = self._agent_contexts.get(agent_id)
                if agent_ctx:
                    agent_ctx.last_activity = time.monotonic()
            parent_context = agent_ctx.otel_context if agent_ctx else None
            if parent_context is None or self._tracer is None:
                logger.debug("No context for phase event, agent_id=%s", agent_id)
                return
            span = self._tracer.start_span(
                name=f"phase:{name}",
                context=parent_context,
                kind=SpanKind.INTERNAL,
                attributes={
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: (
                        OpenInferenceSpanKindValues.CHAIN.value
                    ),
                    SpanAttributes.SESSION_ID: self._get_session_id_for_agent(agent_id),
                    "phase.number": phase,
                    "phase.total": total,
                    "phase.name": name,
                    "phase.summary": summary,
                    "agent.type": agent_id,
                },
            )
            span.end()
        except Exception:
            logger.warning("Failed to add phase event for %s", agent_id, exc_info=True)

    def add_decision_event(self, agent_id: str, decision: dict[str, Any]) -> None:
        """Create a ``decision`` child span under the given agent.

        *decision* should contain keys ``id``, ``category``, ``text``, and
        ``made_by``.
        """
        if not _is_otel_enabled():
            return
        try:
            with self._span_lock:
                agent_ctx = self._agent_contexts.get(agent_id)
            parent_context = agent_ctx.otel_context if agent_ctx else None
            if parent_context is None or self._tracer is None:
                logger.debug("No context for decision event, agent_id=%s", agent_id)
                return
            span = self._tracer.start_span(
                name="decision",
                context=parent_context,
                kind=SpanKind.INTERNAL,
                attributes={
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: (
                        OpenInferenceSpanKindValues.CHAIN.value
                    ),
                    SpanAttributes.SESSION_ID: self._get_session_id_for_agent(agent_id),
                    "decision.id": decision.get("id", ""),
                    "decision.category": decision.get("category", ""),
                    "decision.text": decision.get("text", ""),
                    "decision.made_by": decision.get("made_by", ""),
                },
            )
            span.end()
        except Exception:
            logger.warning("Failed to add decision event for %s", agent_id, exc_info=True)
