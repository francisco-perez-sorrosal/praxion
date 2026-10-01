"""The recording-class table: what gets written, in which mode, for whom.

``EventClass`` is the unit modes are defined over -- finer-grained than the
written ``event_type``, because three classes (``TOOL_FILE_CHANGE``,
``TOOL_FIRST_OF_SUBAGENT``, ``TOOL_OTHER``) all write ``tool_use``. ``EVENTS``
maps each class to its envelope; ``CONSUMERS`` states, per named reader, which
classes and fields it needs and at which minimum mode. ``records()`` is the
one function every writer consults -- it is the single place "does this mode
record this class" is decided, so a per-writer switch check (the bug that let
``record_gate_fire`` ignore the kill switch) cannot recur.

Representation constraint: this module is plain data -- ``enum`` plus
``tuple``/``frozenset``/``types.MappingProxyType`` and ``collections.namedtuple``
(not ``dataclasses`` or ``typing.NamedTuple``). ``writer.py`` imports this
module on the per-tool-call hot path, which must not pull in ``dataclasses``
or runtime ``typing``.
"""

from __future__ import annotations

from collections import namedtuple
from enum import Enum
from types import MappingProxyType

from .modes import Mode

# Tools whose call changes a file on disk. The single source of truth --
# ``hooks/remind_calibration.py`` imports this rather than re-literalling it
# (a later step's migration).
FILE_CHANGING_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


class EventClass(str, Enum):  # noqa: UP042 -- StrEnum needs 3.11; hooks/ targets 3.9+
    """The 13 recording classes. Many-to-one onto the written ``event_type``:
    three classes below write ``tool_use``, so every existing reader's
    ``event_type == "tool_use"`` filter stays valid across the split."""

    SESSION_START = "session_start"
    SESSION_STOP = "session_stop"
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    HELPER_STOP = "helper_stop"
    TOOL_FILE_CHANGE = "tool_file_change"
    TOOL_FIRST_OF_SUBAGENT = "tool_first_of_subagent"
    TOOL_OTHER = "tool_other"
    SKILL_ACTIVATION = "skill_activation"
    COMPACTION = "compaction"
    CONTEXT_SURFACE = "context_surface_measurement"
    GATE_FIRE = "gate_fire"
    RECOVERY = "recovery"


# One entry per class: the ``event_type`` it writes, the producing hook or
# script (documentation only), the modes it is recorded in, and the fields
# its row declares. `TOOL_OTHER` is the one class `standard` narrows out --
# a later, non-file-changing, non-first tool call from a subagent already
# seen in this log -- because it is the only class with no `min_mode:
# standard` consumer. Every other class is recorded in both `full` and
# `standard`.
EventSpec = namedtuple("EventSpec", ("event_type", "writer", "modes", "fields"))

_FULL_AND_STANDARD = frozenset({Mode.FULL, Mode.STANDARD})
_EVERY_MODE = frozenset(Mode)  # RECOVERY bypasses the writer -- never gated.

# Every lifecycle row (session/agent start/stop) shares this envelope; a stop
# adds usage fields, and session_start additionally carries `log_mode_source`
# (see `_SESSION_START_FIELDS` below).
_LIFECYCLE_FIELDS = (
    "timestamp",
    "session_id",
    "agent_type",
    "agent_id",
    "project",
    "event_type",
    "tool_name",
    "summary",
    "file_paths",
    "outcome",
    "classification",
    "agent_type_source",
    "start_correlation",
    "log_mode",
)
# session_start is the one row every reader can rely on to name *why* the
# process resolved the mode it did -- every other lifecycle row only carries
# the mode itself.
_SESSION_START_FIELDS = _LIFECYCLE_FIELDS + ("log_mode_source",)
# An agent_start written since stated slugs began joining at read time says so;
# a row without the marker predates that, and a reader charges it to `project`.
_AGENT_START_FIELDS = _LIFECYCLE_FIELDS + ("slug_attribution",)
_AGENT_STOP_USAGE_FIELDS = (
    "stop_source",
    "tokens_in",
    "tokens_out",
    "cache_read",
    "cache_create",
    "duration_ms",
    "model",
    "usage_source",
)

# Every tool_use-writing class (capture_observations) shares this envelope;
# only SKILL_ACTIVATION adds its own field.
_TOOL_USE_FIELDS = (
    "timestamp",
    "session_id",
    "agent_type",
    "agent_id",
    "project",
    "event_type",
    "tool_name",
    "summary",
    "file_paths",
    "outcome",
    "classification",
    "trace_id",
    "span_id",
    "parent_span_id",
    "log_mode",
)

EVENTS = MappingProxyType(
    {
        EventClass.SESSION_START: EventSpec(
            "session_start", "capture_session", _FULL_AND_STANDARD, _SESSION_START_FIELDS
        ),
        EventClass.SESSION_STOP: EventSpec(
            "session_stop", "capture_session", _FULL_AND_STANDARD, _LIFECYCLE_FIELDS
        ),
        EventClass.AGENT_START: EventSpec(
            "agent_start", "capture_session", _FULL_AND_STANDARD, _AGENT_START_FIELDS
        ),
        EventClass.AGENT_STOP: EventSpec(
            "agent_stop",
            "capture_session",
            _FULL_AND_STANDARD,
            _LIFECYCLE_FIELDS + _AGENT_STOP_USAGE_FIELDS,
        ),
        EventClass.HELPER_STOP: EventSpec(
            "helper_stop",
            "capture_session",
            _FULL_AND_STANDARD,
            ("timestamp", "session_id", "agent_id", "project", "event_type", "log_mode"),
        ),
        EventClass.TOOL_FILE_CHANGE: EventSpec(
            "tool_use", "capture_observations", _FULL_AND_STANDARD, _TOOL_USE_FIELDS
        ),
        EventClass.TOOL_FIRST_OF_SUBAGENT: EventSpec(
            "tool_use", "capture_observations", _FULL_AND_STANDARD, _TOOL_USE_FIELDS
        ),
        EventClass.TOOL_OTHER: EventSpec(
            "tool_use", "capture_observations", frozenset({Mode.FULL}), _TOOL_USE_FIELDS
        ),
        EventClass.SKILL_ACTIVATION: EventSpec(
            "skill_activation",
            "capture_observations",
            _FULL_AND_STANDARD,
            _TOOL_USE_FIELDS + ("skill_name",),
        ),
        EventClass.COMPACTION: EventSpec(
            "compaction",
            "capture_session",
            _FULL_AND_STANDARD,
            ("event_type", "timestamp", "session_id", "trigger", "summary_bytes", "log_mode"),
        ),
        EventClass.CONTEXT_SURFACE: EventSpec(
            "context_surface_measurement",
            "measure_context_surface",
            _FULL_AND_STANDARD,
            (
                "timestamp",
                "session_id",
                "agent_type",
                "agent_id",
                "project",
                "event_type",
                "tool_name",
                "summary",
                "file_paths",
                "outcome",
                "classification",
                "log_mode",
            ),
        ),
        EventClass.GATE_FIRE: EventSpec(
            "gate_fire",
            "record_gate_fire",
            _FULL_AND_STANDARD,
            (
                "timestamp",
                "session_id",
                "event_type",
                "hook",
                "tool_name",
                "outcome",
                "reason",
                "log_mode",
            ),
        ),
        EventClass.RECOVERY: EventSpec(
            "recovery",
            "resume-pipeline (prose; bypasses the writer)",
            _EVERY_MODE,
            (
                "event_type",
                "timestamp",
                "project",
                "summary",
                "file_paths",
                "outcome",
                "classification",
            ),
        ),
    }
)


ConsumerSpec = namedtuple("ConsumerSpec", ("name", "kind", "needs", "min_mode"))

# One entry per *need*, not per file: a consumer with fields available only
# at a higher mode (capture_session's summary, sentinel P04) is split into
# two entries so each carries one accurate `min_mode`.
CONSUMERS = (
    ConsumerSpec(
        "hooks/remind_calibration.py",
        "code",
        {
            EventClass.SESSION_START: ("timestamp", "session_id"),
            EventClass.TOOL_FILE_CHANGE: ("session_id", "event_type", "tool_name", "file_paths"),
            EventClass.GATE_FIRE: ("session_id", "event_type", "hook"),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "hooks/capture_session.py#summary",
        "code",
        {
            EventClass.SESSION_START: ("timestamp",),
            EventClass.AGENT_START: ("agent_id", "agent_type"),
            EventClass.AGENT_STOP: (
                "agent_id",
                "model",
                "timestamp",
                "tokens_in",
                "tokens_out",
                "cache_read",
                "cache_create",
            ),
            EventClass.GATE_FIRE: ("hook",),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "hooks/capture_session.py#summary-tool-calls-by-tool",
        "code",
        {EventClass.TOOL_OTHER: ("tool_name",)},
        Mode.FULL,
    ),
    ConsumerSpec(
        "hooks/capture_session.py#backfill",
        "code",
        {
            EventClass.AGENT_START: ("agent_id", "agent_type", "event_type"),
            EventClass.TOOL_FILE_CHANGE: ("agent_id", "agent_type", "event_type"),
            EventClass.TOOL_FIRST_OF_SUBAGENT: ("agent_id", "agent_type", "event_type"),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/spawn_count.py",
        "code",
        {
            EventClass.AGENT_START: (
                "agent_id",
                "agent_type",
                "timestamp",
                "session_id",
                "project",
                "slug_attribution",
            )
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/reconcile_pipeline_state.py",
        "code",
        {
            EventClass.TOOL_FILE_CHANGE: (
                "event_type",
                "agent_type",
                "file_paths",
                "agent_id",
                "timestamp",
            ),
            EventClass.AGENT_STOP: ("event_type", "agent_id", "timestamp"),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/_handoff_readiness.py",
        "code",
        {
            EventClass.SESSION_STOP: ("session_id",),
            EventClass.AGENT_START: ("agent_id", "event_type"),
            EventClass.AGENT_STOP: ("agent_id", "event_type"),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/context_baseline.py",
        "code",
        {EventClass.AGENT_START: ("event_type", "agent_id", "agent_type")},
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/query_memory_write_evidence.py",
        "code",
        {
            EventClass.AGENT_START: ("event_type", "agent_type"),
            EventClass.TOOL_FILE_CHANGE: ("event_type", "tool_name", "file_paths"),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/check_agent_lifecycle_pairing.py",
        "code",
        {
            EventClass.AGENT_START: (
                "event_type",
                "agent_id",
                "agent_type",
                "session_id",
                "timestamp",
                "start_correlation",
            ),
            EventClass.AGENT_STOP: (
                "event_type",
                "agent_id",
                "agent_type",
                "session_id",
                "timestamp",
                "start_correlation",
            ),
            EventClass.HELPER_STOP: ("event_type", "agent_id", "session_id", "timestamp"),
            EventClass.TOOL_FIRST_OF_SUBAGENT: ("event_type", "agent_id", "session_id"),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/project_metrics/collectors/cost_collector.py",
        "code",
        {
            EventClass.AGENT_STOP: (
                "agent_id",
                "session_id",
                "project",
                "agent_type",
                "agent_type_source",
                "model",
                "tokens_in",
                "tokens_out",
                "cache_read",
                "cache_create",
                "duration_ms",
                "timestamp",
                "usage_source",
            )
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "scripts/workflow_run_cost.py",
        "code",
        {
            EventClass.AGENT_STOP: (
                "event_type",
                "agent_id",
                "tokens_in",
                "tokens_out",
                "cache_read",
                "cache_create",
                "model",
                "duration_ms",
                "usage_source",
                "timestamp",
            ),
            EventClass.HELPER_STOP: ("event_type", "agent_id", "timestamp"),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "agents/sentinel.md#P03",
        "prompt",
        {
            EventClass.AGENT_START: ("agent_id", "agent_type", "session_id"),
            EventClass.AGENT_STOP: ("agent_id", "agent_type", "session_id", "start_correlation"),
            EventClass.HELPER_STOP: ("agent_id", "session_id"),
            EventClass.TOOL_FIRST_OF_SUBAGENT: ("agent_id",),
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "agents/sentinel.md#P04-write-surface",
        "prompt",
        {
            EventClass.TOOL_FILE_CHANGE: (
                "agent_id",
                "agent_type",
                "tool_name",
                "file_paths",
                "outcome",
            )
        },
        Mode.STANDARD,
    ),
    ConsumerSpec(
        "agents/sentinel.md#P04-grant",
        "prompt",
        {EventClass.TOOL_OTHER: ("agent_id", "agent_type", "tool_name", "file_paths", "outcome")},
        Mode.FULL,
    ),
)


def records(event_class: EventClass, mode: Mode) -> bool:
    """True when ``event_class`` is recorded under ``mode``, per this table."""
    return mode in EVENTS[event_class].modes
