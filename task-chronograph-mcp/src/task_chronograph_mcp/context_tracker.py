"""Agent-context tracking and shared relay state.

``_RelayContextTracking`` is the base of the OTelRelay inheritance chain. A
single ``OTelRelay`` class was split into cohesive layers to keep each file
under the size ceiling; the split is by inheritance (not composition) so all
layers share one ``self`` and one ``__init__`` -- behavior is identical to the
original single class.

This layer owns the relay's mutable state (span/session bookkeeping dicts, the
lock, the reaper thread) and the operations over the agent-context map:
spawn correlation, fork-group clustering, the stale-context reaper, and the
per-agent stat/rollup helpers. Span construction lives one layer up in
``span_factory``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from opentelemetry import context as context_api
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.trace import StatusCode

from . import relay_helpers as rh
from .relay_helpers import (
    DEFAULT_PHOENIX_ENDPOINT,
    DEFAULT_PROJECT_NAME,
    MAIN_AGENT_ID,
    PHOENIX_ENDPOINT_ENV,
    PHOENIX_PROJECT_NAME_ENV,
    REAPER_INTERVAL_S,
    SPAWN_PENDING_TIMEOUT_S,
)

logger = logging.getLogger(__name__)


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


class _RelayContextTracking:
    """Shared relay state plus agent-context tracking (base of OTelRelay)."""

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

        # Agent-spawn correlation: Claude Code fires PreToolUse(Agent) from the
        # spawning agent's context, then SubagentStart for the spawnee (without
        # any parent signal). We FIFO-queue pending spawns on PreToolUse(Agent)
        # and dequeue in order on SubagentStart to resolve the real parent.
        # Each entry: (parent_agent_id, tool_use_id, enqueued_at_monotonic).
        self._pending_spawns: deque[tuple[str, str, float]] = deque()

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
    # Fork-group clustering (Phase 4: ADR 052)
    # ------------------------------------------------------------------

    def _register_spawn(self, caller_agent_id: str, tool_use_id: str) -> None:
        """Record that PreToolUse(Agent) fired; bind caller as prospective parent.

        Claude Code's Agent tool dispatches a subagent whose subsequent
        SubagentStart carries no parent linkage. By enqueuing (caller, id) on
        PreToolUse we can pop the FIFO-oldest entry on SubagentStart and treat
        that caller as the real parent -- correct for sequential, parallel, and
        nested spawns (PreToolUse always fires in caller's context).
        """
        caller = caller_agent_id or MAIN_AGENT_ID
        with self._span_lock:
            self._pending_spawns.append((caller, tool_use_id, time.monotonic()))

    def _pop_spawn_parent(self) -> str:
        """Pop the FIFO-oldest non-stale pending spawn, returning its caller.

        Returns MAIN_AGENT_ID when the queue is empty or all entries are stale
        (orphaned PreToolUse(Agent) without matching SubagentStart).
        """
        now = time.monotonic()
        with self._span_lock:
            while self._pending_spawns:
                caller, _tool_use_id, ts = self._pending_spawns.popleft()
                if now - ts <= SPAWN_PENDING_TIMEOUT_S:
                    return caller
        return MAIN_AGENT_ID

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
            if cluster is None or (now - cluster.opened_at) > rh.FORK_CLUSTER_WINDOW_S:
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
                if now - ctx.last_activity > rh.AGENT_SPAN_TIMEOUT_S
            ]
            for agent_id in stale_agents:
                self._agent_contexts.pop(agent_id, None)
                logger.info("Reaped stale agent context: %s", agent_id)

            stale_tools = [
                tid
                for tid, start in self._open_tool_start_times.items()
                if now - start > rh.AGENT_SPAN_TIMEOUT_S
            ]
            orphaned_spans = []
            for tool_use_id in stale_tools:
                span = self._open_tool_spans.pop(tool_use_id, None)
                self._open_tool_start_times.pop(tool_use_id, None)
                if span is not None:
                    orphaned_spans.append((tool_use_id, span))

            # Drop stale pending-spawn entries (PreToolUse(Agent) without a
            # matching SubagentStart within SPAWN_PENDING_TIMEOUT_S).
            while self._pending_spawns and (
                now - self._pending_spawns[0][2] > SPAWN_PENDING_TIMEOUT_S
            ):
                self._pending_spawns.popleft()

        # End orphaned spans outside the lock to keep the critical section short.
        for tool_use_id, span in orphaned_spans:
            try:
                span.set_status(StatusCode.ERROR, "orphaned-tool-start")
                span.end()
                logger.info("Reaped orphaned tool span: %s", tool_use_id)
            except Exception:
                logger.warning("Failed to end orphaned tool span %s", tool_use_id, exc_info=True)

    # ------------------------------------------------------------------
    # Per-agent rollups and lookups
    # ------------------------------------------------------------------

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
