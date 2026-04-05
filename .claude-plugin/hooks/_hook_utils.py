"""Shared utilities for memory enforcement hooks.

Provides transcript scanning and significance detection used by both
memory_gate.py (Stop) and validate_memory.py (SubagentStop).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# Tool classification for significance detection
EDIT_TOOLS = frozenset({"Write", "Edit"})
READ_TOOLS = frozenset({"Read"})
SEARCH_TOOLS = frozenset({"Grep", "Glob"})
DELEGATION_TOOLS = frozenset({"Agent"})
REMEMBER_SUBSTRING = "remember"

# Significance thresholds — any single criterion triggers the gate
MIN_EDITS = 3  # substantial code changes
MIN_READS = 5  # research / analysis session
MIN_SEARCHES = 3  # codebase exploration
MIN_TOTAL_TOOLS = 10  # general engagement fallback


@dataclass(frozen=True)
class TranscriptStats:
    """Statistics from scanning a Claude Code transcript."""

    edit_count: int = 0
    remember_count: int = 0
    read_count: int = 0
    search_count: int = 0
    agent_count: int = 0
    total_tool_count: int = 0
    wrote_learnings: bool = False

    @property
    def has_significant_work(self) -> bool:
        """Whether the transcript shows meaningful engagement worth remembering."""
        return (
            self.edit_count >= MIN_EDITS
            or self.agent_count >= 1
            or self.read_count >= MIN_READS
            or self.search_count >= MIN_SEARCHES
            or self.total_tool_count >= MIN_TOTAL_TOOLS
        )

    @property
    def work_summary(self) -> str:
        """Human-readable summary of work done."""
        parts: list[str] = []
        if self.edit_count > 0:
            parts.append(f"{self.edit_count} file edits")
        if self.agent_count > 0:
            parts.append(f"{self.agent_count} agent delegation(s)")
        if self.read_count > 0:
            parts.append(f"{self.read_count} file reads")
        if self.search_count > 0:
            parts.append(f"{self.search_count} searches")
        if self.wrote_learnings:
            parts.append("LEARNINGS.md update")
        if not parts:
            parts.append(f"{self.total_tool_count} tool calls")
        return ", ".join(parts)


def scan_transcript(transcript_path: str) -> TranscriptStats:
    """Scan a Claude Code transcript for work and memory indicators.

    Parses the JSONL transcript and classifies tool_use blocks into
    categories to determine whether significant work was done and
    whether remember() was called.
    """
    edit_count = 0
    remember_count = 0
    read_count = 0
    search_count = 0
    agent_count = 0
    total_tool_count = 0
    wrote_learnings = False

    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turn = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if turn.get("type") != "assistant":
                    continue

                message = turn.get("message", {})
                content = message.get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if block.get("type") != "tool_use":
                        continue

                    name = block.get("name", "")
                    tool_input = block.get("input", {})
                    total_tool_count += 1

                    if name in EDIT_TOOLS:
                        edit_count += 1
                        file_path = tool_input.get("file_path", "")
                        if "LEARNINGS" in file_path:
                            wrote_learnings = True
                    elif name in READ_TOOLS:
                        read_count += 1
                    elif name in SEARCH_TOOLS:
                        search_count += 1
                    elif name in DELEGATION_TOOLS:
                        agent_count += 1

                    if REMEMBER_SUBSTRING in name.lower():
                        remember_count += 1
    except OSError:
        pass

    return TranscriptStats(
        edit_count=edit_count,
        remember_count=remember_count,
        read_count=read_count,
        search_count=search_count,
        agent_count=agent_count,
        total_tool_count=total_tool_count,
        wrote_learnings=wrote_learnings,
    )


REMEMBER_PROMPT = (
    "Examples of what to remember:\n"
    "- Gotchas or non-obvious behaviors you discovered\n"
    "- Patterns that worked well and should be reused\n"
    "- User corrections or preferences expressed this session\n"
    "- Conventions or constraints not documented elsewhere\n"
    "- Architectural insights or trade-off rationales\n"
    "- Analysis findings, audit results, or health trends\n\n"
    'Call: mcp__plugin_i-am_memory__remember with category="learnings", '
    "a descriptive key, the insight as value, relevant tags, "
    "importance (3-8), a one-line summary, and type "
    "(decision/gotcha/pattern/convention/preference/correction/insight)."
)
