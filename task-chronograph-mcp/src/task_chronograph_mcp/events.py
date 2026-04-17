"""Event model, Interaction model, and EventStore for pipeline observability."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class EventType(StrEnum):
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    PHASE_TRANSITION = "phase_transition"
    TOOL_START = "tool_start"
    TOOL_USE = "tool_use"
    ERROR = "error"
    SESSION_START = "session_start"
    SESSION_STOP = "session_stop"
    SKILL_USE = "skill_use"


class AgentStatus(StrEnum):
    RUNNING = "running"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"
    PENDING = "pending"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class Event:
    event_type: EventType
    agent_type: str
    timestamp: datetime = field(default_factory=_utcnow)
    event_id: str = field(default_factory=_uuid)
    session_id: str = ""
    agent_id: str = ""
    parent_session_id: str = ""
    phase: int = 0
    total_phases: int = 0
    phase_name: str = ""
    status: AgentStatus = AgentStatus.RUNNING
    message: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    tool_name: str = ""
    project_dir: str = ""
    # Git context
    git_branch: str = ""
    git_toplevel: str = ""
    is_worktree: bool = False
    worktree_name: str = ""
    # Artifact context
    artifact_type: str = ""
    artifact_name: str = ""
    # Pipeline context
    task_slug: str = ""
    # Tool correlation (Claude Code's tool_use_id, e.g. "toolu_xxx").
    # Present on TOOL_START and TOOL_USE events; pairs them for duration spans.
    tool_use_id: str = ""

    def to_dict(self) -> dict:
        d = {
            "event_type": self.event_type.value,
            "agent_type": self.agent_type,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "parent_session_id": self.parent_session_id,
            "phase": self.phase,
            "total_phases": self.total_phases,
            "phase_name": self.phase_name,
            "status": self.status.value,
            "message": self.message,
            "labels": dict(self.labels),
            "metadata": dict(self.metadata),
            "tool_name": self.tool_name,
            "project_dir": self.project_dir,
        }
        if self.git_branch:
            d["git_branch"] = self.git_branch
        if self.git_toplevel:
            d["git_toplevel"] = self.git_toplevel
        if self.is_worktree:
            d["is_worktree"] = self.is_worktree
            d["worktree_name"] = self.worktree_name
        if self.artifact_type:
            d["artifact_type"] = self.artifact_type
            d["artifact_name"] = self.artifact_name
        if self.task_slug:
            d["task_slug"] = self.task_slug
        if self.tool_use_id:
            d["tool_use_id"] = self.tool_use_id
        return d


@dataclass(frozen=True)
class Interaction:
    source: str
    target: str
    summary: str
    interaction_type: str
    interaction_id: str = field(default_factory=_uuid)
    timestamp: datetime = field(default_factory=_utcnow)
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "summary": self.summary,
            "interaction_type": self.interaction_type,
            "interaction_id": self.interaction_id,
            "timestamp": self.timestamp.isoformat(),
            "labels": dict(self.labels),
        }


@dataclass
class AgentState:
    agent_type: str
    agent_id: str
    status: AgentStatus
    current_phase: int = 0
    total_phases: int = 0
    phase_name: str = ""
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    task_summary: str = ""
    last_message: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    delegation_parent: str = ""
    delegation_children: list[str] = field(default_factory=list)
    last_event_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "current_phase": self.current_phase,
            "total_phases": self.total_phases,
            "phase_name": self.phase_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "task_summary": self.task_summary,
            "last_message": self.last_message,
            "labels": dict(self.labels),
            "delegation_parent": self.delegation_parent,
            "delegation_children": list(self.delegation_children),
        }


DEFAULT_MAX_EVENTS = 10_000
DEFAULT_EVENT_LIMIT = 20


class EventStore:
    def __init__(self, max_events: int = DEFAULT_MAX_EVENTS) -> None:
        self._events: deque[Event] = deque(maxlen=max_events)
        self._interactions: list[Interaction] = []
        self._agents: dict[str, AgentState] = {}
        self._lock = threading.Lock()
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the event loop for cross-thread SSE broadcasting."""
        self._loop = loop

    def add(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)
            self._update_agent_state(event)
        self._notify(event)

    def add_interaction(self, interaction: Interaction) -> str:
        with self._lock:
            self._interactions.append(interaction)
            if interaction.interaction_type == "delegation":
                self._register_delegation_from_interaction(interaction)
        synthetic = Event(
            event_type=EventType.TOOL_USE,
            agent_type=interaction.source,
            timestamp=interaction.timestamp,
            message=f"interaction:{interaction.interaction_type}:{interaction.target}",
            metadata={"interaction_id": interaction.interaction_id},
        )
        self._notify(synthetic)
        return interaction.interaction_id

    def _update_agent_state(self, event: Event) -> None:
        agent_key = event.agent_id or event.agent_type

        if event.event_type == EventType.AGENT_START:
            state = AgentState(
                agent_type=event.agent_type,
                agent_id=event.agent_id,
                status=AgentStatus.RUNNING,
                started_at=event.timestamp,
                labels=dict(event.labels),
            )
            self._apply_pending_delegation(state)
            self._agents[agent_key] = state
            return

        if agent_key not in self._agents:
            return

        state = self._agents[agent_key]
        state.last_event_at = event.timestamp

        if event.event_type == EventType.AGENT_STOP:
            state.status = AgentStatus.COMPLETE
            state.stopped_at = event.timestamp
        elif event.event_type == EventType.PHASE_TRANSITION:
            state.current_phase = event.phase
            state.total_phases = event.total_phases
            state.phase_name = event.phase_name
            state.last_message = event.message
            if event.labels:
                state.labels.update(event.labels)
        elif event.event_type == EventType.ERROR:
            state.status = AgentStatus.FAILED
            state.last_message = event.message

    def _register_delegation_from_interaction(self, interaction: Interaction) -> None:
        source_key = interaction.source
        target_key = interaction.target

        if source_key in self._agents:
            parent = self._agents[source_key]
            if target_key not in parent.delegation_children:
                parent.delegation_children.append(target_key)

        if target_key in self._agents:
            child = self._agents[target_key]
            if not child.delegation_parent:
                child.delegation_parent = source_key
            if not child.task_summary:
                child.task_summary = interaction.summary

    def _apply_pending_delegation(self, state: AgentState) -> None:
        """Check existing delegation interactions for an agent that just started."""
        agent_key = state.agent_id or state.agent_type
        for interaction in self._interactions:
            if interaction.interaction_type != "delegation":
                continue
            if interaction.target == agent_key and not state.delegation_parent:
                state.delegation_parent = interaction.source
                if not state.task_summary:
                    state.task_summary = interaction.summary
                if interaction.source in self._agents:
                    parent = self._agents[interaction.source]
                    if agent_key not in parent.delegation_children:
                        parent.delegation_children.append(agent_key)

    def get_delegation_chain(self) -> list[dict]:
        return [
            {
                "parent": interaction.source,
                "child": interaction.target,
                "reason": interaction.summary,
                "timestamp": interaction.timestamp.isoformat(),
            }
            for interaction in self._interactions
            if interaction.interaction_type == "delegation"
        ]

    def get_pipeline_summary(self) -> dict:
        return {
            "agents": {key: state.to_dict() for key, state in self._agents.items()},
            "interactions": [i.to_dict() for i in self._interactions],
            "delegation_chain": self.get_delegation_chain(),
            "event_count": len(self._events),
            "recent_events": [e.to_dict() for e in list(self._events)[-DEFAULT_EVENT_LIMIT:]],
        }

    def get_events_by_agent(
        self,
        agent_type: str,
        limit: int = DEFAULT_EVENT_LIMIT,
        label: str | None = None,
    ) -> list[dict]:
        matching = [e for e in self._events if e.agent_type == agent_type]
        if label is not None:
            matching = _filter_by_label(matching, label)
        return [e.to_dict() for e in matching[-limit:]]

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    def _notify(self, event: Event) -> None:
        """Broadcast event to SSE subscribers, safe from any thread."""
        if not self._loop or not self._subscribers:
            return
        for queue in list(self._subscribers):
            try:
                self._loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                pass  # event loop closed


def _filter_by_label(events: list[Event], label: str) -> list[Event]:
    """Filter events by label expression. Supports 'key=value' or 'key' (exists check)."""
    if "=" in label:
        key, value = label.split("=", 1)
        return [e for e in events if e.labels.get(key) == value]
    return [e for e in events if label in e.labels]
