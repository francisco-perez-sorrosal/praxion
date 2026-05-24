"""Pure helpers and module constants for the OTel relay.

This is the lowest layer of the relay: configuration constants plus stateless
helper functions (env checks, git lookups, transcript parsing, agent-type
classification). It has no dependency on any other relay module, so both
``context_tracker`` and ``span_factory`` import from here freely.

The git/tier helpers and the two timing constants (``FORK_CLUSTER_WINDOW_S``,
``AGENT_SPAN_TIMEOUT_S``) are read *through this module* by their callers so the
test suite can monkeypatch them here -- their single home -- and have the patch
take effect across every reader.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from openinference.semconv.trace import SpanAttributes

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

# Spawn-correlation: a pending entry older than this is considered orphaned
# (PreToolUse(Agent) fired but the matching SubagentStart never did).
# PreToolUse→SubagentStart normally takes milliseconds; 60s is ample.
SPAWN_PENDING_TIMEOUT_S = 60

# Claude Code's subagent-spawning tool name -- PreToolUse(Agent) is the signal
# we use to identify the spawning parent for the next SubagentStart.
AGENT_SPAWN_TOOL_NAME = "Agent"

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
