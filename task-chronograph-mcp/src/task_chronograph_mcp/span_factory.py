"""Span construction for the OTel relay.

``_RelaySpanFactory`` is the middle layer of the OTelRelay inheritance chain.
It extends ``_RelayContextTracking`` (state + context tracking) with the methods
that actually build and end OpenTelemetry spans: provider init, the root session
span, agent spans, tool spans, and the session summary. ``_ensure_agent_context``
lives here -- not in the context layer -- because it lazily *creates* an agent
span, so it must sit above span construction.

Spans are ended immediately after creation; Phoenix links children to parents by
SpanContext IDs, so closing the parent first is fine.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.trace import SpanKind, StatusCode

from . import relay_helpers as rh
from .context_tracker import AgentContext, SessionStats, _RelayContextTracking
from .relay_helpers import (
    MAIN_AGENT_ID,
    MAIN_AGENT_TYPE,
    TRACE_TYPE_NATIVE,
    TRACE_TYPE_PIPELINE,
    TRACER_NAME,
    _clean_agent_type,
    _detect_agent_origin,
)

logger = logging.getLogger(__name__)


class _RelaySpanFactory(_RelayContextTracking):
    """Span-construction layer of OTelRelay (extends context tracking)."""

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

    def _open_session_span(
        self,
        session_id: str,
        project_dir: str,
        git_context: dict[str, Any],
    ) -> None:
        """Create the root SESSION span and end it immediately.

        The span is ended right away so Phoenix receives it and shows the
        trace in the Traces view. Child spans (agents, tools) reference
        the root's SpanContext for parent-child linkage -- this works even
        after the root span is closed because OTel links by IDs, not by
        live Span objects.

        A synthetic ``main-agent`` AGENT span is also created (and ended
        immediately) to parent tool calls from the main Claude agent
        (which has no lifecycle hooks). The ``_session_context`` is
        preserved so child spans can be parented under this root
        throughout the session.
        """
        if self._tracer is None:
            return

        project_name = os.path.basename(project_dir) if project_dir else self._default_project_name

        git_branch = git_context.get("git_branch", "")
        is_worktree = git_context.get("is_worktree", False)
        worktree_name = git_context.get("worktree_name", "")

        # Phase 3 (ADR 052): user.id from git identity, propagated to spans.
        user_id = rh._git_user_id(project_dir)
        # Phase 4 (ADR 052): cheap session-level context.
        git_sha = rh._git_head_sha(project_dir)
        pipeline_tier = rh._read_pipeline_tier(project_dir)

        # No parent context -> true root span.
        attrs: dict[str, Any] = {
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            SpanAttributes.SESSION_ID: session_id,
            "praxion.project_name": project_name,
            "praxion.project_dir": project_dir,
            "praxion.session_start": datetime.now(UTC).isoformat(),
        }
        if user_id:
            attrs[SpanAttributes.USER_ID] = user_id
        if git_branch:
            attrs["praxion.git.branch"] = git_branch
        if is_worktree:
            attrs["praxion.git.is_worktree"] = True
            attrs["praxion.git.worktree_name"] = worktree_name
        if git_sha:
            attrs["praxion.git.sha"] = git_sha
        if pipeline_tier:
            attrs["praxion.pipeline_tier"] = pipeline_tier

        self._session_span = self._tracer.start_span(
            name="session",
            kind=SpanKind.INTERNAL,
            attributes=attrs,
        )
        # Capture context BEFORE ending -- child spans parent under this.
        self._session_context = trace.set_span_in_context(self._session_span)
        # End immediately so Phoenix receives the root span right away.
        # Child spans still link to it via the saved _session_context.
        self._session_span.end()

        # Initialize session stats
        self._session_stats = SessionStats(
            session_id=session_id,
            git_branch=git_branch,
            is_worktree=is_worktree,
            worktree_name=worktree_name,
            user_id=user_id,
            git_sha=git_sha,
            pipeline_tier=pipeline_tier,
        )

        # Create synthetic main-agent span for the main Claude agent.
        # Tool calls with empty agent_id will be parented under this span.
        main_span = self._tracer.start_span(
            name=MAIN_AGENT_TYPE,
            context=self._session_context,
            kind=SpanKind.INTERNAL,
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
                SpanAttributes.AGENT_NAME: MAIN_AGENT_TYPE,
                SpanAttributes.GRAPH_NODE_ID: MAIN_AGENT_ID,
                SpanAttributes.GRAPH_NODE_NAME: MAIN_AGENT_TYPE,
                SpanAttributes.GRAPH_NODE_PARENT_ID: "",
                "praxion.agent_type": MAIN_AGENT_TYPE,
                "praxion.agent_origin": "claude-code",
                "praxion.agent_id": MAIN_AGENT_ID,
                SpanAttributes.SESSION_ID: session_id,
                "praxion.depth": 0,
            },
        )
        main_context = trace.set_span_in_context(main_span)
        main_span.end()  # End immediately for Phoenix visibility
        with self._span_lock:
            self._agent_contexts[MAIN_AGENT_ID] = AgentContext(
                otel_context=main_context,
                agent_id=MAIN_AGENT_ID,
                agent_type=MAIN_AGENT_TYPE,
                session_id=session_id,
                parent_agent_id="",
                depth=0,
                last_activity=time.monotonic(),
            )

        # Start reaper to handle stale context cleanup
        self._start_reaper()

    def _start_agent_span(
        self,
        agent_id: str,
        agent_type: str,
        session_id: str,
        parent_session_id: str,
        *,
        git_context: dict[str, Any] | None = None,
        task_slug: str = "",
    ) -> None:
        """Create an AGENT span parented under the actual spawning agent.

        The span is ended right away so Phoenix shows the trace hierarchy
        without waiting for SubagentStop. The span's context is stored in
        ``_agent_contexts`` for parenting child spans (tools, phases, decisions).

        Parent resolution: pop the FIFO-oldest pending spawn from the queue
        populated by PreToolUse(Agent). Falls back to MAIN_AGENT_ID when the
        queue is empty (e.g., a lazy-created context for a background agent
        whose Agent tool call never hit a hook).
        """
        if self._tracer is None or self._session_context is None:
            return

        origin = _detect_agent_origin(agent_type)
        clean_type = _clean_agent_type(agent_type)

        # Determine parent: pop the oldest pending spawn registered by
        # PreToolUse(Agent). Empty queue -> fall back to main-agent.
        parent_id = self._pop_spawn_parent()
        with self._span_lock:
            parent_ctx = self._agent_contexts.get(parent_id)
            if parent_ctx is None and parent_id != MAIN_AGENT_ID:
                # Parent resolved from the queue but we have no context for it
                # (shouldn't normally happen; degrade gracefully to main-agent).
                parent_id = MAIN_AGENT_ID
                parent_ctx = self._agent_contexts.get(MAIN_AGENT_ID)
        parent_otel_context = parent_ctx.otel_context if parent_ctx else self._session_context
        parent_depth = parent_ctx.depth if parent_ctx else 0

        # Set trace_type on each agent span
        trace_type = TRACE_TYPE_PIPELINE if origin == "praxion" else TRACE_TYPE_NATIVE

        # Ensure a meaningful span name for Phoenix display
        span_name = clean_type or agent_id or "unknown-agent"

        # Phase 4: fork-group time clustering.
        # Subagents spawned within FORK_CLUSTER_WINDOW_S under the same parent
        # share a fork_group UUID so Phoenix queries can reveal parallel cohorts.
        fork_group, sibling_index = self._assign_fork_group(parent_id)

        git = git_context or {}
        attrs: dict[str, Any] = {
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.AGENT.value,
            SpanAttributes.AGENT_NAME: span_name,
            SpanAttributes.GRAPH_NODE_ID: agent_id or span_name,
            SpanAttributes.GRAPH_NODE_NAME: span_name,
            SpanAttributes.GRAPH_NODE_PARENT_ID: parent_id,
            "praxion.agent_type": clean_type,
            "praxion.agent_origin": origin,
            "praxion.trace_type": trace_type,
            "praxion.agent_id": agent_id,
            SpanAttributes.SESSION_ID: session_id,
            "praxion.parent_session_id": parent_session_id,
            "praxion.depth": parent_depth + 1,
            "praxion.parent_agent_id": parent_id,
            "praxion.fork_group": fork_group,
            "praxion.sibling_index": sibling_index,
        }
        if self._session_stats and self._session_stats.user_id:
            attrs[SpanAttributes.USER_ID] = self._session_stats.user_id
        if self._session_stats and self._session_stats.git_sha:
            attrs["praxion.git.sha"] = self._session_stats.git_sha
        if self._session_stats and self._session_stats.pipeline_tier:
            attrs["praxion.pipeline_tier"] = self._session_stats.pipeline_tier
        if git.get("git_branch"):
            attrs["praxion.git.branch"] = git["git_branch"]
        if git.get("is_worktree"):
            attrs["praxion.git.is_worktree"] = True
            attrs["praxion.git.worktree_name"] = git.get("worktree_name", "")
        if task_slug:
            attrs["praxion.task_slug"] = task_slug

        span = self._tracer.start_span(
            name=span_name,
            context=parent_otel_context,
            kind=SpanKind.INTERNAL,
            attributes=attrs,
        )
        agent_context = trace.set_span_in_context(span)
        span.end()  # End immediately for Phoenix visibility

        now = time.monotonic()
        with self._span_lock:
            self._agent_contexts[agent_id] = AgentContext(
                otel_context=agent_context,
                agent_id=agent_id,
                agent_type=clean_type,
                session_id=session_id,
                parent_agent_id=parent_id,
                depth=parent_depth + 1,
                last_activity=now,
                started_at=now,
            )
            # Increment parent's child count and record delegation target
            if parent_ctx:
                parent_ctx.child_count += 1
                if clean_type and clean_type not in parent_ctx.delegated_to:
                    parent_ctx.delegated_to.append(clean_type)

        # Update session stats
        if self._session_stats:
            self._session_stats.agent_count += 1
            if task_slug and not self._session_stats.task_slug:
                self._session_stats.task_slug = task_slug

    def _record_tool_span(
        self,
        agent_id: str,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        is_error: bool,
        error_msg: str,
        metadata: dict[str, Any],
        *,
        tool_use_id: str = "",
    ) -> None:
        """Create a TOOL span as a child of the agent span or main agent."""
        if self._tracer is None:
            return

        parent_context = self._get_parent_context(agent_id)
        if parent_context is None:
            return

        attributes: dict[str, Any] = {
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.TOOL.value,
            SpanAttributes.TOOL_NAME: tool_name,
            SpanAttributes.SESSION_ID: self._get_session_id_for_agent(agent_id),
        }
        if tool_use_id:
            attributes[SpanAttributes.TOOL_ID] = tool_use_id
        if input_summary:
            attributes[SpanAttributes.INPUT_VALUE] = input_summary
        if output_summary:
            attributes[SpanAttributes.OUTPUT_VALUE] = output_summary

        # Phase 4: size-before-truncation and hook provenance
        input_bytes = metadata.get("input_size_bytes")
        if isinstance(input_bytes, int):
            attributes["praxion.io.input_size_bytes"] = input_bytes
        output_bytes = metadata.get("output_size_bytes")
        if isinstance(output_bytes, int):
            attributes["praxion.io.output_size_bytes"] = output_bytes
        hook_event = metadata.get("hook_event", "")
        if hook_event:
            attributes["praxion.hook_event"] = hook_event

        # MCP tool enrichment
        if metadata.get("artifact_type") == "mcp_tool":
            attributes["praxion.artifact_type"] = "mcp_tool"
            attributes["praxion.mcp_server"] = metadata.get("mcp_server", "")
            attributes["praxion.mcp_tool"] = metadata.get("mcp_tool", "")

        # OTel MCP semconv forward-compat: set when provided, omit otherwise
        mcp_session_id = metadata.get("mcp_session_id", "")
        if mcp_session_id:
            attributes["mcp.session.id"] = mcp_session_id
        jsonrpc_request_id = metadata.get("jsonrpc_request_id", "")
        if jsonrpc_request_id:
            attributes["jsonrpc.request.id"] = jsonrpc_request_id

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

        # Update stats
        self._increment_stat(agent_id, "tool_count")
        if is_error:
            self._increment_stat(agent_id, "error_count")
        self._track_tool_used(agent_id, tool_name)
        if self._session_stats:
            self._session_stats.tool_count += 1
            if is_error:
                self._session_stats.error_count += 1

    def _finalize_tool_span(
        self,
        span: trace.Span,
        agent_id: str,
        tool_name: str,
        output_summary: str,
        is_error: bool,
        error_msg: str,
        metadata: dict[str, Any],
        end_timestamp: datetime | None,
    ) -> None:
        """Close an open tool span with output attrs and explicit end time.

        ``tool.id`` was set at ``start_tool`` time (as the correlation key),
        so there's no need to set it again here. ``tool_name`` is passed in
        rather than recovered from ``span.attributes`` because the public
        ``trace.Span`` interface does not expose attribute readback.
        """
        if output_summary:
            span.set_attribute(SpanAttributes.OUTPUT_VALUE, output_summary)

        # Phase 4: size-before-truncation and hook provenance
        input_bytes = metadata.get("input_size_bytes")
        if isinstance(input_bytes, int):
            span.set_attribute("praxion.io.input_size_bytes", input_bytes)
        output_bytes = metadata.get("output_size_bytes")
        if isinstance(output_bytes, int):
            span.set_attribute("praxion.io.output_size_bytes", output_bytes)
        hook_event = metadata.get("hook_event", "")
        if hook_event:
            span.set_attribute("praxion.hook_event", hook_event)

        mcp_session_id = metadata.get("mcp_session_id", "")
        if mcp_session_id:
            span.set_attribute("mcp.session.id", mcp_session_id)
        jsonrpc_request_id = metadata.get("jsonrpc_request_id", "")
        if jsonrpc_request_id:
            span.set_attribute("jsonrpc.request.id", jsonrpc_request_id)

        if is_error:
            span.set_status(StatusCode.ERROR, error_msg)
            span.add_event(
                "error",
                attributes={
                    "exception.type": "ToolError",
                    "exception.message": error_msg,
                },
            )

        end_time_ns: int | None = None
        if end_timestamp is not None:
            end_time_ns = int(end_timestamp.timestamp() * 1_000_000_000)
        span.end(end_time=end_time_ns)

        # Record the tool name on the agent's rollup set for end_agent.
        if tool_name:
            self._track_tool_used(agent_id, tool_name)

        self._increment_stat(agent_id, "tool_count")
        if is_error:
            self._increment_stat(agent_id, "error_count")
        if self._session_stats:
            self._session_stats.tool_count += 1
            if is_error:
                self._session_stats.error_count += 1

    def _ensure_agent_context(self, agent_id: str, agent_type: str, session_id: str) -> None:
        """Lazily create an agent span if agent_id is unknown but agent_type is available.

        This handles the case where Claude Code doesn't fire SubagentStart hooks
        for background agents (run_in_background: true), but does fire PostToolUse
        hooks for their tool calls. Without this, tool spans from background agents
        would be misattributed to main-agent.
        """
        if not agent_id or not agent_type:
            return
        with self._span_lock:
            if agent_id in self._agent_contexts:
                return
        logger.info(
            "Lazy-creating agent span for %s (%s) — no prior agent_start received",
            agent_id,
            agent_type,
        )
        self._start_agent_span(agent_id, agent_type, session_id, parent_session_id="")

    def _create_session_summary(self) -> None:
        """Create a session-summary CHAIN span with aggregate stats."""
        if self._tracer is None or self._session_context is None or self._session_stats is None:
            return
        stats = self._session_stats
        duration_s = round(time.monotonic() - stats.start_time, 1)
        attrs: dict[str, Any] = {
            SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
            SpanAttributes.SESSION_ID: stats.session_id,
            "praxion.agent_count": stats.agent_count,
            "praxion.tool_count": stats.tool_count,
            "praxion.skill_count": stats.skill_count,
            "praxion.error_count": stats.error_count,
            "praxion.duration_s": duration_s,
            "praxion.session_summary": (
                f"{stats.agent_count} agents, {stats.tool_count} tools, "
                f"{stats.skill_count} skills, {stats.error_count} errors"
            ),
        }
        if stats.git_branch:
            attrs["praxion.git.branch"] = stats.git_branch
        if stats.is_worktree:
            attrs["praxion.git.is_worktree"] = True
            attrs["praxion.git.worktree_name"] = stats.worktree_name
        if stats.task_slug:
            attrs["praxion.task_slug"] = stats.task_slug
        if stats.pipeline_tier:
            attrs["praxion.pipeline_tier"] = stats.pipeline_tier

        span = self._tracer.start_span(
            name="session-summary",
            context=self._session_context,
            kind=SpanKind.INTERNAL,
            attributes=attrs,
        )
        span.end()
