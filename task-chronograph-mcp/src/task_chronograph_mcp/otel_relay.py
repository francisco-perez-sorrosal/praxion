"""OTel relay: translates chronograph events into OpenTelemetry spans for Phoenix."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
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
# Phase 3 (ADR 052): opt-out of LLM-level attributes (tokens, model, system)
# for users who want structural telemetry without any model metadata.
# Does not affect Phoenix's local cost computation (that's a Phoenix setting).
STRIP_LLM_ATTRS_ENV = "CHRONOGRAPH_STRIP_LLM_ATTRS"

TRACER_NAME = "praxion.chronograph"

# Agent origin detection prefix
_PRAXION_AGENT_PREFIX = "i-am:"

# Main agent synthetic span
MAIN_AGENT_ID = "__main_agent__"
MAIN_AGENT_TYPE = "main-agent"

# Trace type values
TRACE_TYPE_PIPELINE = "pipeline"
TRACE_TYPE_NATIVE = "native"

# Context reaper configuration
AGENT_SPAN_TIMEOUT_S = 60  # seconds of inactivity before reaping
REAPER_INTERVAL_S = 10  # seconds between reaper sweeps

# Phase 4 (ADR 052): time-clustering window for parallel-subagent fork detection.
# Agents that start within this window under the same parent get the same
# fork_group UUID so Phoenix can query sibling cohorts.
FORK_CLUSTER_WINDOW_S = 0.2  # 200 ms


def _is_otel_enabled() -> bool:
    """OTel export is enabled by default via plugin.json.

    Can be disabled by setting OTEL_ENABLED=false for debugging.
    """
    return os.environ.get(OTEL_ENABLED_ENV, "false").lower() in ("true", "1", "yes")


def _should_strip_llm_attrs() -> bool:
    """User opt-out: skip LLM-level attributes (tokens, model, system, provider).

    Structural telemetry (agent/tool/phase spans, durations, hierarchy) stays
    intact; only the model-metadata overlay is suppressed. See ADR 052.
    """
    return os.environ.get(STRIP_LLM_ATTRS_ENV, "").lower() in ("1", "true", "yes")


def _git_user_id(project_dir: str) -> str:
    """Best-effort user.id from `git config user.email`. Fail-open to empty."""
    if not project_dir:
        return ""
    try:
        email = (
            subprocess.check_output(
                ["git", "config", "user.email"],
                cwd=project_dir,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return email
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def _git_head_sha(project_dir: str) -> str:
    """Best-effort short git SHA of HEAD. Fail-open to empty."""
    if not project_dir:
        return ""
    try:
        sha = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=project_dir,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return sha
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def _read_pipeline_tier(project_dir: str) -> str:
    """Best-effort pipeline tier from .ai-state/calibration_log.md (last row).

    Per the agent-intermediate-documents rule, calibration_log is an
    append-only Markdown table with columns:
        timestamp | task | signals | recommended | actual | source | retro
    We take the last data row's "actual" column. Fail-open to empty string.
    """
    if not project_dir:
        return ""
    log_path = Path(project_dir) / ".ai-state" / "calibration_log.md"
    if not log_path.exists():
        return ""
    try:
        rows = [
            ln.strip()
            for ln in log_path.read_text().splitlines()
            if ln.strip().startswith("|") and not ln.strip().startswith("|-")
        ]
    except OSError:
        return ""
    data_rows = [r for r in rows if "timestamp" not in r.lower()]
    if not data_rows:
        return ""
    cols = [c.strip() for c in data_rows[-1].strip("|").split("|")]
    if len(cols) >= 5:
        return cols[4]
    return ""


def _parse_transcript_usage(transcript_path: str) -> dict[str, Any]:
    """Aggregate LLM token usage and model info from a Claude Code agent transcript.

    Transcript format is JSONL, one message per line, shape:
        {"type": "assistant", "message": {"model": "claude-opus-4-7",
         "role": "assistant", "usage": {"input_tokens": N, "output_tokens": M,
         "cache_creation_input_tokens": K, "cache_read_input_tokens": R, ...}}}

    Returns a dict of openinference-standard attributes suitable for merging
    into an agent-summary span. Returns ``{}`` when the file is absent,
    unreadable, has no usage, or when LLM attrs are suppressed via
    ``CHRONOGRAPH_STRIP_LLM_ATTRS=1``.

    Cache tokens are summed into prompt tokens so Phoenix's token aggregation
    reflects total input cost regardless of whether the bill was for read
    vs. creation.
    """
    if _should_strip_llm_attrs():
        return {}
    if not transcript_path:
        return {}
    path = Path(transcript_path)
    if not path.exists():
        return {}

    prompt_total = 0
    completion_total = 0
    model = ""
    try:
        with path.open() as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except (ValueError, TypeError):
                    continue
                msg = entry.get("message") if isinstance(entry, dict) else None
                if not isinstance(msg, dict):
                    continue
                seen_model = msg.get("model", "") or ""
                if seen_model:
                    model = seen_model
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                input_tokens = usage.get("input_tokens") or 0
                cache_creation = usage.get("cache_creation_input_tokens") or 0
                cache_read = usage.get("cache_read_input_tokens") or 0
                output_tokens = usage.get("output_tokens") or 0
                prompt_total += int(input_tokens) + int(cache_creation) + int(cache_read)
                completion_total += int(output_tokens)
    except OSError:
        return {}

    if prompt_total == 0 and completion_total == 0 and not model:
        return {}

    attrs: dict[str, Any] = {}
    if prompt_total or completion_total:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT] = prompt_total
        attrs[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] = completion_total
        attrs[SpanAttributes.LLM_TOKEN_COUNT_TOTAL] = prompt_total + completion_total
    if model:
        attrs[SpanAttributes.LLM_MODEL_NAME] = model
        # Infer system/provider from the model family
        if model.startswith("claude-"):
            attrs[SpanAttributes.LLM_SYSTEM] = "anthropic"
            attrs[SpanAttributes.LLM_PROVIDER] = "anthropic"
        elif model.startswith("gpt-") or model.startswith("o1-") or model.startswith("o3-"):
            attrs[SpanAttributes.LLM_SYSTEM] = "openai"
            attrs[SpanAttributes.LLM_PROVIDER] = "openai"
    return attrs


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


# ---------------------------------------------------------------------------
# Agent context tracking
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Tracks an active agent's OTel context and hierarchy position."""

    otel_context: context_api.Context
    agent_id: str
    agent_type: str
    session_id: str
    parent_agent_id: str  # "" for main-agent
    depth: int
    last_activity: float
    child_count: int = 0
    tool_count: int = 0
    error_count: int = 0
    skill_count: int = 0
    # Phase 4 (ADR 052): agent-scoped rollups for the agent-summary span.
    started_at: float = field(default_factory=time.monotonic)
    tools_used: set[str] = field(default_factory=set)
    skills_used: set[str] = field(default_factory=set)
    delegated_to: list[str] = field(default_factory=list)


@dataclass
class ForkCluster:
    """Groups subagents that were spawned within ``FORK_CLUSTER_WINDOW_S``.

    Phoenix queries on ``praxion.fork_group`` reveal parallel fan-outs.
    Time clustering is heuristic -- concurrent subagent dispatch typically
    arrives within a few ms, so a 200 ms window catches siblings while
    almost never false-joining unrelated starts.
    """

    fork_group: str
    opened_at: float
    member_count: int = 0


@dataclass
class SessionStats:
    """Tracks aggregate stats for a session, used in the summary span."""

    session_id: str = ""
    agent_count: int = 0
    tool_count: int = 0
    skill_count: int = 0
    error_count: int = 0
    start_time: float = field(default_factory=time.monotonic)
    git_branch: str = ""
    is_worktree: bool = False
    worktree_name: str = ""
    task_slug: str = ""
    pipeline_tier: str = ""
    user_id: str = ""
    git_sha: str = ""


class OTelRelay:
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

        # Hierarchy-aware context tracking -- protected by _span_lock
        self._span_lock = threading.Lock()
        self._agent_contexts: dict[str, AgentContext] = {}

        # Tool duration correlation (Phase 2: ADR 052).
        # Keyed by Claude Code tool_use_id; populated at PreToolUse and
        # drained at PostToolUse so Phoenix sees one span with real start/end.
        self._open_tool_spans: dict[str, trace.Span] = {}
        self._open_tool_start_times: dict[str, float] = {}

        # Phase 4 fork clustering: one active cluster per parent_agent_id.
        # A new AGENT_START within FORK_CLUSTER_WINDOW_S of the cluster's
        # opened_at joins the cohort; otherwise a new UUID is minted.
        self._fork_clusters: dict[str, ForkCluster] = {}

        self._session_span: trace.Span | None = None
        self._session_context: context_api.Context | None = None
        self._session_stats: SessionStats | None = None

        # Reaper thread
        self._reaper_stop = threading.Event()
        self._reaper_thread: threading.Thread | None = None

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

    def _finalize_tool_span(
        self,
        span: trace.Span,
        agent_id: str,
        output_summary: str,
        is_error: bool,
        error_msg: str,
        metadata: dict[str, Any],
        end_timestamp: datetime | None,
    ) -> None:
        """Close an open tool span with output attrs and explicit end time.

        ``tool.id`` was set at ``start_tool`` time (as the correlation key),
        so there's no need to set it again here.
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
        tool_name_attr = (
            span.attributes.get(SpanAttributes.TOOL_NAME, "") if span.attributes else ""
        )
        if tool_name_attr:
            self._track_tool_used(agent_id, str(tool_name_attr))

        self._increment_stat(agent_id, "tool_count")
        if is_error:
            self._increment_stat(agent_id, "error_count")
        if self._session_stats:
            self._session_stats.tool_count += 1
            if is_error:
                self._session_stats.error_count += 1

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

    # ------------------------------------------------------------------
    # Fork-group clustering (Phase 4: ADR 052)
    # ------------------------------------------------------------------

    def _assign_fork_group(self, parent_agent_id: str) -> tuple[str, int]:
        """Return (fork_group, sibling_index) for an agent starting now.

        A fork cluster is shared by subagents that start within
        ``FORK_CLUSTER_WINDOW_S`` of each other under the same parent.
        Outside that window, a new cluster (new UUID) is minted.
        """
        from uuid import uuid4

        now = time.monotonic()
        with self._span_lock:
            cluster = self._fork_clusters.get(parent_agent_id)
            if cluster is None or (now - cluster.opened_at) > FORK_CLUSTER_WINDOW_S:
                cluster = ForkCluster(fork_group=str(uuid4()), opened_at=now, member_count=0)
                self._fork_clusters[parent_agent_id] = cluster
            sibling_index = cluster.member_count
            cluster.member_count += 1
            return cluster.fork_group, sibling_index

    # ------------------------------------------------------------------
    # Context reaper
    # ------------------------------------------------------------------

    def _start_reaper(self) -> None:
        """Start the background context reaper thread if not already running."""
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
        """Periodically check for and clean up stale agent contexts."""
        while not self._reaper_stop.wait(REAPER_INTERVAL_S):
            self._reap_stale_contexts()

    def _reap_stale_contexts(self) -> None:
        """Remove stale agent contexts and orphaned open tool spans.

        Agent spans are already ended at creation; this just clears tracking
        dicts to prevent memory leaks from hooks that never fire. Orphaned
        tool spans (PreToolUse without a matching PostToolUse) must be
        explicitly ended with an ERROR status so Phoenix doesn't drop them.
        """
        now = time.monotonic()
        with self._span_lock:
            stale_agents = [
                aid
                for aid, ctx in self._agent_contexts.items()
                if now - ctx.last_activity > AGENT_SPAN_TIMEOUT_S
            ]
            for agent_id in stale_agents:
                self._agent_contexts.pop(agent_id, None)
                logger.info("Reaped stale agent context: %s", agent_id)

            stale_tools = [
                tid
                for tid, start in self._open_tool_start_times.items()
                if now - start > AGENT_SPAN_TIMEOUT_S
            ]
            orphaned_spans = []
            for tool_use_id in stale_tools:
                span = self._open_tool_spans.pop(tool_use_id, None)
                self._open_tool_start_times.pop(tool_use_id, None)
                if span is not None:
                    orphaned_spans.append((tool_use_id, span))

        # End orphaned spans outside the lock to keep the critical section short.
        for tool_use_id, span in orphaned_spans:
            try:
                span.set_status(StatusCode.ERROR, "orphaned-tool-start")
                span.end()
                logger.info("Reaped orphaned tool span: %s", tool_use_id)
            except Exception:
                logger.warning("Failed to end orphaned tool span %s", tool_use_id, exc_info=True)

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
        user_id = _git_user_id(project_dir)
        # Phase 4 (ADR 052): cheap session-level context.
        git_sha = _git_head_sha(project_dir)
        pipeline_tier = _read_pipeline_tier(project_dir)

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
        """Create an AGENT span parented under the spawning agent (hierarchy-aware).

        The span is ended right away so Phoenix shows the trace hierarchy
        without waiting for SubagentStop. The span's context is stored in
        ``_agent_contexts`` for parenting child spans (tools, phases, decisions).

        Parent resolution:
        - Look up MAIN_AGENT_ID as the default parent (depth-1 agents)
        - This naturally handles the common case where the main agent spawns subagents
        """
        if self._tracer is None or self._session_context is None:
            return

        origin = _detect_agent_origin(agent_type)
        clean_type = _clean_agent_type(agent_type)

        # Determine parent: use main-agent as default parent for depth-1 agents
        parent_id = MAIN_AGENT_ID
        with self._span_lock:
            parent_ctx = self._agent_contexts.get(parent_id)
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

    def _track_tool_used(self, agent_id: str, tool_name: str) -> None:
        """Record that ``tool_name`` was used by ``agent_id`` for the agent-summary rollup."""
        lookup_id = agent_id if agent_id else MAIN_AGENT_ID
        with self._span_lock:
            ctx = self._agent_contexts.get(lookup_id)
            if ctx is not None:
                ctx.tools_used.add(tool_name)

    def _track_skill_used(self, agent_id: str, skill_name: str) -> None:
        """Record that ``skill_name`` was used by ``agent_id`` for the agent-summary rollup."""
        lookup_id = agent_id if agent_id else MAIN_AGENT_ID
        with self._span_lock:
            ctx = self._agent_contexts.get(lookup_id)
            if ctx is not None:
                ctx.skills_used.add(skill_name)

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

    def _get_parent_context(self, agent_id: str) -> context_api.Context | None:
        """Look up the OTel context for parenting a child span.

        Checks agent context map, falls back to main-agent, then session root.
        """
        lookup_id = agent_id if agent_id else MAIN_AGENT_ID
        with self._span_lock:
            agent_ctx = self._agent_contexts.get(lookup_id)
            if agent_ctx:
                agent_ctx.last_activity = time.monotonic()
                return agent_ctx.otel_context
            # Fallback to main-agent
            main_ctx = self._agent_contexts.get(MAIN_AGENT_ID)
            if main_ctx:
                return main_ctx.otel_context
        return self._session_context

    def _get_session_id_for_agent(self, agent_id: str) -> str:
        """Look up the session_id associated with an agent's context.

        Resolves in the same order as ``_get_parent_context``: agent-specific,
        then main-agent fallback. Returns an empty string when no context is
        available (e.g., pre-session tool spans should not normally reach here).
        """
        lookup_id = agent_id if agent_id else MAIN_AGENT_ID
        with self._span_lock:
            agent_ctx = self._agent_contexts.get(lookup_id)
            if agent_ctx:
                return agent_ctx.session_id
            main_ctx = self._agent_contexts.get(MAIN_AGENT_ID)
            if main_ctx:
                return main_ctx.session_id
        return ""

    def _increment_stat(self, agent_id: str, stat_name: str) -> None:
        """Increment a counter on an agent context. Thread-safe."""
        lookup_id = agent_id if agent_id else MAIN_AGENT_ID
        with self._span_lock:
            agent_ctx = self._agent_contexts.get(lookup_id)
            if agent_ctx:
                current = getattr(agent_ctx, stat_name, 0)
                setattr(agent_ctx, stat_name, current + 1)

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
