"""Memory system metrics computed from memory.json and observations.jsonl."""

from __future__ import annotations

import collections
from datetime import UTC, datetime

from memory_mcp.observations import ObservationStore
from memory_mcp.schema import VALID_CATEGORIES


def compute_metrics(
    data: dict,
    obs_store: ObservationStore | None = None,
) -> dict:
    """Compute comprehensive metrics from memory data and observations.

    Args:
        data: The full memory.json data dict (with "memories" key).
        obs_store: Optional ObservationStore for observation-based metrics.

    Returns:
        Structured metrics dict with summary_markdown for display.
    """
    memories = data.get("memories", {})
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    store_metrics = _compute_store_metrics(memories, now)
    obs_metrics = _compute_observation_metrics(obs_store) if obs_store else {}
    summary_md = _format_summary_markdown(store_metrics, obs_metrics, data)

    return {
        "store": store_metrics,
        "observations": obs_metrics,
        "summary_markdown": summary_md,
    }


# -- Store metrics ------------------------------------------------------------


def _compute_store_metrics(memories: dict, now: str) -> dict:
    """Compute metrics from the curated memory store."""
    by_category: dict[str, dict] = {}
    all_tags: list[str] = []
    all_types: list[str] = []
    all_importances: list[int] = []
    all_access_counts: list[int] = []
    total_active = 0
    total_archived = 0
    total_superseded = 0
    never_accessed = 0
    total_links = 0
    has_confidence = 0
    created_by_counts: dict[str, int] = collections.Counter()
    source_type_counts: dict[str, int] = collections.Counter()
    ages_days: list[float] = []
    stale_since_days: list[float] = []

    for cat in VALID_CATEGORIES:
        entries = memories.get(cat, {})
        active = 0
        archived = 0
        superseded = 0

        for _key, entry in entries.items():
            status = entry.get("status", "active")
            if status == "active":
                active += 1
                total_active += 1
            elif status == "archived":
                archived += 1
                total_archived += 1
            elif status == "superseded":
                superseded += 1
                total_superseded += 1

            # Only compute detailed metrics for active entries
            if status != "active":
                continue

            tags = entry.get("tags", [])
            all_tags.extend(tags)

            entry_type = entry.get("type")
            if entry_type:
                all_types.append(entry_type)

            importance = entry.get("importance", 5)
            all_importances.append(importance)

            access_count = entry.get("access_count", 0)
            all_access_counts.append(access_count)
            if access_count == 0:
                never_accessed += 1

            links = entry.get("links", [])
            total_links += len(links)

            if entry.get("confidence") is not None:
                has_confidence += 1

            source = entry.get("source", {})
            if source.get("type"):
                source_type_counts[source["type"]] += 1

            created_by = entry.get("created_by")
            if created_by:
                created_by_counts[created_by] += 1

            created_at = entry.get("created_at", "")
            if created_at:
                try:
                    age = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    age_days = (datetime.now(UTC) - age).total_seconds() / 86400
                    ages_days.append(age_days)
                except (ValueError, TypeError):
                    pass

            last_accessed = entry.get("last_accessed")
            if last_accessed:
                try:
                    la = datetime.fromisoformat(last_accessed.replace("Z", "+00:00"))
                    stale_days = (datetime.now(UTC) - la).total_seconds() / 86400
                    stale_since_days.append(stale_days)
                except (ValueError, TypeError):
                    pass

        by_category[cat] = {
            "active": active,
            "archived": archived,
            "superseded": superseded,
        }

    tag_freq = dict(collections.Counter(all_tags).most_common(20))
    type_dist = dict(collections.Counter(all_types).most_common())
    importance_dist = dict(collections.Counter(all_importances).most_common())

    # Access count buckets
    access_buckets = {"0": 0, "1-5": 0, "6-20": 0, "21+": 0}
    for ac in all_access_counts:
        if ac == 0:
            access_buckets["0"] += 1
        elif ac <= 5:
            access_buckets["1-5"] += 1
        elif ac <= 20:
            access_buckets["6-20"] += 1
        else:
            access_buckets["21+"] += 1

    # Importance tiers (matches injection tiers)
    importance_tiers = {
        "tier1_always (7-10)": sum(1 for i in all_importances if i >= 7),
        "tier2_budget (4-6)": sum(1 for i in all_importances if 4 <= i <= 6),
        "tier3_search (1-3)": sum(1 for i in all_importances if i <= 3),
    }

    return {
        "total_active": total_active,
        "total_archived": total_archived,
        "total_superseded": total_superseded,
        "by_category": by_category,
        "never_accessed": never_accessed,
        "never_accessed_pct": (
            round(never_accessed / total_active * 100, 1) if total_active else 0
        ),
        "total_links": total_links,
        "has_confidence": has_confidence,
        "tag_frequency": tag_freq,
        "type_distribution": type_dist,
        "importance_distribution": importance_dist,
        "importance_tiers": importance_tiers,
        "access_buckets": access_buckets,
        "source_types": dict(source_type_counts),
        "created_by": dict(created_by_counts),
        "age_stats": _stats(ages_days, "days"),
        "staleness_stats": _stats(stale_since_days, "days"),
    }


# -- Observation metrics ------------------------------------------------------


def _compute_observation_metrics(obs_store: ObservationStore) -> dict:
    """Compute metrics from the observations JSONL layer."""
    observations = obs_store._read_all()  # noqa: SLF001
    if not observations:
        return {"total": 0}

    total = len(observations)
    event_types: dict[str, int] = collections.Counter()
    agents: dict[str, int] = collections.Counter()
    classifications: dict[str, int] = collections.Counter()
    tools: dict[str, int] = collections.Counter()
    sessions: dict[str, list] = collections.defaultdict(list)
    memory_ops: dict[str, int] = collections.Counter()
    outcomes: dict[str, int] = collections.Counter()

    for obs in observations:
        event_types[obs.get("event_type", "unknown")] += 1
        agents[obs.get("agent_type", "unknown")] += 1

        classification = obs.get("classification")
        if classification:
            classifications[classification] += 1

        tool_name = obs.get("tool_name")
        if tool_name:
            tools[tool_name] += 1
            # Track memory-specific operations
            if tool_name in (
                "remember",
                "recall",
                "search",
                "forget",
                "hard_delete",
                "consolidate",
                "session_start",
                "reflect",
                "browse_index",
                "connections",
                "add_link",
                "remove_link",
                "about_me",
                "about_us",
                "export_memories",
                "status",
                "timeline",
                "session_narrative",
            ):
                memory_ops[tool_name] += 1

        session_id = obs.get("session_id")
        if session_id:
            sessions[session_id].append(obs)

        outcome = obs.get("outcome")
        if outcome:
            outcomes[outcome] += 1

    # Per-session stats
    session_stats = []
    for sid, sess_obs in sessions.items():
        timestamps = [o.get("timestamp", "") for o in sess_obs if o.get("timestamp")]
        duration_s = None
        if len(timestamps) >= 2:
            try:
                first = datetime.fromisoformat(min(timestamps).replace("Z", "+00:00"))
                last = datetime.fromisoformat(max(timestamps).replace("Z", "+00:00"))
                duration_s = round((last - first).total_seconds())
            except (ValueError, TypeError):
                pass

        # Count memory ops in this session
        sess_memory_ops = sum(
            1 for o in sess_obs if o.get("tool_name") in ("remember", "recall", "search", "forget")
        )
        sess_remembers = sum(1 for o in sess_obs if o.get("tool_name") == "remember")

        session_stats.append(
            {
                "session_id": sid[:12],
                "events": len(sess_obs),
                "duration_s": duration_s,
                "memory_ops": sess_memory_ops,
                "remembers": sess_remembers,
                "agent_types": list({o.get("agent_type", "?") for o in sess_obs}),
            }
        )

    session_stats.sort(key=lambda s: s["events"], reverse=True)

    return {
        "total": total,
        "file_size_bytes": obs_store.file_size(),
        "sessions": len(sessions),
        "event_types": dict(event_types.most_common()),
        "agent_activity": dict(agents.most_common(15)),
        "classifications": dict(classifications.most_common()),
        "top_tools": dict(tools.most_common(15)),
        "memory_operations": dict(memory_ops.most_common()),
        "outcomes": dict(outcomes),
        "session_summary": session_stats[:10],
    }


# -- Formatting ---------------------------------------------------------------


def _format_summary_markdown(
    store: dict,
    obs: dict,
    data: dict,
) -> str:
    """Format metrics as readable Markdown for terminal display."""
    lines: list[str] = []
    lines.append("# Memory Metrics")
    lines.append("")

    # -- Overview
    lines.append("## Store Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Active entries | {store['total_active']} |")
    lines.append(f"| Archived | {store['total_archived']} |")
    lines.append(f"| Superseded (soft-deleted) | {store['total_superseded']} |")
    lines.append(f"| Never accessed | {store['never_accessed']} ({store['never_accessed_pct']}%) |")
    lines.append(f"| Total links | {store['total_links']} |")
    lines.append(f"| Schema version | {data.get('schema_version', '?')} |")
    lines.append(f"| Session count | {data.get('session_count', '?')} |")
    lines.append("")

    # -- By category
    lines.append("## Entries by Category")
    lines.append("")
    lines.append("| Category | Active | Archived | Superseded |")
    lines.append("|----------|--------|----------|------------|")
    for cat, counts in store["by_category"].items():
        if counts["active"] or counts["archived"] or counts["superseded"]:
            lines.append(
                f"| {cat} | {counts['active']} | {counts['archived']} | {counts['superseded']} |"
            )
    lines.append("")

    # -- Importance tiers
    lines.append("## Importance Tiers")
    lines.append("")
    lines.append("| Tier | Entries | Behavior |")
    lines.append("|------|---------|----------|")
    for tier, count in store["importance_tiers"].items():
        behavior = {
            "tier1_always (7-10)": "Always injected at session start",
            "tier2_budget (4-6)": "Injected if token budget allows",
            "tier3_search (1-3)": "Search-only, never auto-injected",
        }.get(tier, "")
        lines.append(f"| {tier} | {count} | {behavior} |")
    lines.append("")

    # -- Access distribution
    lines.append("## Access Distribution")
    lines.append("")
    lines.append("| Bucket | Count |")
    lines.append("|--------|-------|")
    for bucket, count in store["access_buckets"].items():
        bar = "█" * min(count, 30)
        lines.append(f"| {bucket} accesses | {count} {bar} |")
    lines.append("")

    # -- Type distribution
    if store["type_distribution"]:
        lines.append("## Knowledge Types")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for t, c in store["type_distribution"].items():
            lines.append(f"| {t} | {c} |")
        lines.append("")

    # -- Top tags
    if store["tag_frequency"]:
        lines.append("## Top Tags")
        lines.append("")
        lines.append("| Tag | Count |")
        lines.append("|-----|-------|")
        for tag, count in list(store["tag_frequency"].items())[:15]:
            lines.append(f"| {tag} | {count} |")
        lines.append("")

    # -- Source types
    if store["source_types"]:
        lines.append("## Source Types")
        lines.append("")
        for src, count in store["source_types"].items():
            lines.append(f"- **{src}**: {count}")
        lines.append("")

    # -- Age stats
    if store["age_stats"]:
        lines.append("## Entry Age")
        lines.append("")
        stats = store["age_stats"]
        lines.append(f"- Oldest: {stats.get('max', '?')} days")
        lines.append(f"- Newest: {stats.get('min', '?')} days")
        lines.append(f"- Median: {stats.get('median', '?')} days")
        lines.append("")

    # -- Observations section
    if obs and obs.get("total", 0) > 0:
        lines.append("---")
        lines.append("")
        lines.append("## Observations")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total events | {obs['total']} |")
        lines.append(f"| Sessions tracked | {obs['sessions']} |")
        size_kb = round(obs.get("file_size_bytes", 0) / 1024, 1)
        lines.append(f"| File size | {size_kb} KB |")
        lines.append("")

        # Memory operations
        if obs.get("memory_operations"):
            lines.append("## Memory Tool Usage")
            lines.append("")
            lines.append("| Operation | Count |")
            lines.append("|-----------|-------|")
            for op, count in obs["memory_operations"].items():
                lines.append(f"| {op} | {count} |")
            lines.append("")

        # Agent activity
        if obs.get("agent_activity"):
            lines.append("## Agent Activity")
            lines.append("")
            lines.append("| Agent | Events |")
            lines.append("|-------|--------|")
            for agent, count in obs["agent_activity"].items():
                lines.append(f"| {agent} | {count} |")
            lines.append("")

        # Top sessions
        if obs.get("session_summary"):
            lines.append("## Top Sessions (by event count)")
            lines.append("")
            lines.append("| Session | Events | Duration | Memory Ops | Remembers |")
            lines.append("|---------|--------|----------|------------|-----------|")
            for s in obs["session_summary"][:8]:
                dur = _fmt_duration(s.get("duration_s"))
                lines.append(
                    f"| {s['session_id']} | {s['events']} | {dur} | {s['memory_ops']} | {s['remembers']} |"
                )
            lines.append("")

        # Work classifications
        if obs.get("classifications"):
            lines.append("## Work Classifications")
            lines.append("")
            lines.append("| Classification | Count |")
            lines.append("|----------------|-------|")
            for cls, count in obs["classifications"].items():
                lines.append(f"| {cls} | {count} |")
            lines.append("")

    return "\n".join(lines)


# -- Utility ------------------------------------------------------------------


def _stats(values: list[float], unit: str) -> dict | None:
    """Compute min/max/median/mean for a list of floats."""
    if not values:
        return None
    values_sorted = sorted(values)
    n = len(values_sorted)
    median = (
        values_sorted[n // 2] if n % 2 else (values_sorted[n // 2 - 1] + values_sorted[n // 2]) / 2
    )
    return {
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "median": round(median, 1),
        "mean": round(sum(values) / n, 1),
        "count": n,
        "unit": unit,
    }


def _fmt_duration(seconds: int | None) -> str:
    """Format seconds as human-readable duration."""
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    return f"{hours}h {mins}m"
