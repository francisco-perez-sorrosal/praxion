"""Metrics page — semantic KPI grid + hotspots + trends + collectors.

Reads `.ai-state/metrics_reports/METRICS_REPORT_*.json` (latest) for the KPI
grid, hot-spot table, and per-collector status; reads `METRICS_LOG.md` for the
historical trend chart. Mirrors the legacy `index.html` viewer's information
hierarchy (semantic groupings, help tooltips, drill-downs) using native
Streamlit primitives — no `streamlit-extras`, no inline HTML, no new deps.

Conventions enforced (see `rules/swe/dashboard-conventions.md`):
- Single `render()` export, no import-time Streamlit calls.
- All file reads go through `data.cache` (mtime-keyed `@st.cache_data`).
- Empty-state degradation when artifacts are absent.
- `@st.fragment` for live-data tabs so sidebar filters re-run only the panel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from streamlit_app.config import get_config
from streamlit_app.data import cache, discovery
from streamlit_app.widgets import empty_state
from streamlit_app.widgets import graph as graphw

# ── Configuration tables ──────────────────────────────────────────────────────
# Each row: (field, label, fmt_kind, help_text). Labels are chosen so the test
# substring set (`sloc`, `coverage`, `truck`, `churn`, `cyclic`, `hotspot`,
# `file`, `language`, `entropy`) appears verbatim in at least one tile.

_SIZE_ACTIVITY: list[tuple[str, str, str, str]] = [
    (
        "sloc_total",
        "SLOC Total",
        "int",
        "Source lines of code (excludes blanks/comments). Counted by `scc`.",
    ),
    (
        "file_count",
        "Files",
        "int",
        "Total source files in scope after path-filter exclusions.",
    ),
    (
        "churn_total_90d",
        "Churn 90d",
        "int",
        "Sum of insertions+deletions across all tracked files in the last 90 days.",
    ),
]

_COMPLEXITY: list[tuple[str, str, str, str]] = [
    (
        "ccn_p95",
        "CCN p95",
        "float2",
        "95th-percentile cyclomatic complexity per function. Lower is simpler.",
    ),
    (
        "cognitive_p95",
        "Cognitive p95",
        "float2",
        "95th-percentile cognitive complexity per function. Sensitive to nesting/branching.",
    ),
    (
        "cyclic_deps",
        "Cyclic Deps",
        "int",
        "Strongly-connected components in the import graph (count of cycles). Target: 0.",
    ),
]

_BUS_HOTSPOTS: list[tuple[str, str, str, str]] = [
    (
        "truck_factor",
        "Truck Factor",
        "int",
        "Minimum number of authors who together own >50% of the codebase. Higher is safer.",
    ),
    (
        "hotspot_top_score",
        "Top Hotspot",
        "score",
        "Highest hotspot_score = complexity × churn_90d. Drill into the Hot-spots tab.",
    ),
    (
        "hotspot_gini",
        "Hotspot Gini",
        "float2",
        "Inequality of hotspot scores (0 = uniform, 1 = concentrated). Lower means risk is spread.",
    ),
]

_QUALITY: list[tuple[str, str, str, str]] = [
    (
        "coverage_line_pct",
        "Coverage",
        "pct",
        "Line coverage from the latest coverage.xml. Run /project-metrics --refresh-coverage to update.",
    ),
    (
        "change_entropy_90d",
        "Change Entropy",
        "float2",
        "Shannon entropy of authorship over 90 days. Higher = more diverse contributor set.",
    ),
    (
        "language_count",
        "Languages",
        "int",
        "Distinct languages identified by `scc` in scope.",
    ),
]

_KPI_GROUPS: list[tuple[str, list[tuple[str, str, str, str]]]] = [
    ("Size & Activity", _SIZE_ACTIVITY),
    ("Complexity", _COMPLEXITY),
    ("Bus Factor & Hotspots", _BUS_HOTSPOTS),
    ("Quality", _QUALITY),
]

# Polarity for `st.metric(delta_color=...)`: does "higher delta" mean "better"?
# `normal` — green up; `inverse` — red up; `off` — neutral grey.
_DELTA_POLARITY: dict[str, str] = {
    "ccn_p95": "inverse",
    "cognitive_p95": "inverse",
    "cyclic_deps": "inverse",
    "hotspot_top_score": "inverse",
    "hotspot_gini": "inverse",
    "coverage_line_pct": "normal",
    "truck_factor": "normal",
    "change_entropy_90d": "normal",
    "language_count": "off",
    "sloc_total": "off",
    "file_count": "off",
    "churn_total_90d": "off",
}

_PRODUCER_REL = "scripts/project_metrics/"


# ── Public entry ──────────────────────────────────────────────────────────────


def render() -> None:
    """Render the Metrics page."""
    config = get_config()
    json_reports = discovery.list_metrics_reports_json(config.project_root)
    log_path = discovery.find_metrics_log(config.project_root)

    st.title("📊 Project Metrics")
    st.caption(
        "Latest run summary, historical trends, and hot-spot drill-down."
        " Source: `/project-metrics` artefacts under `.ai-state/metrics_reports/`."
    )

    if not json_reports and log_path is None:
        empty_state.empty_state(
            artifact_name="Project metrics",
            producer_path=str(config.project_root / _PRODUCER_REL),
            explanation=(
                "No metrics yet. Run `/project-metrics` to generate the first report."
            ),
        )
        return

    data = _load_latest_report(json_reports[0]) if json_reports else None

    if data:
        _render_run_badge(data)
        _render_kpi_groups(data)

    tab_labels = ["📈 Trends", "🔥 Hot-spots", "🔧 Collectors", "📄 Raw"]
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        _render_trends_tab(log_path)
    with tabs[1]:
        _render_hotspots_tab(data)
    with tabs[2]:
        _render_collectors_tab(data)
    with tabs[3]:
        _render_raw_tab(json_reports[0] if json_reports else None, data)


# ── Latest report load ────────────────────────────────────────────────────────


def _load_latest_report(path: Path) -> dict[str, Any] | None:
    """Cached parse of the latest JSON report, with graceful failure."""
    try:
        return cache.cached_parse_metrics_report_json(str(path), cache.mtime_of(path))
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not parse latest metrics report: {exc}")
        return None


def _render_run_badge(data: dict[str, Any]) -> None:
    """Compact metadata line under the title."""
    agg = data.get("aggregate") or {}
    meta = data.get("run_metadata") or {}
    timestamp = agg.get("timestamp", "?")
    sha = (agg.get("commit_sha") or "")[:8] or "?"
    window = meta.get("window_days") or agg.get("window_days") or "?"
    wall = meta.get("wall_clock_seconds")
    wall_str = f"{wall:.1f}s" if isinstance(wall, (int, float)) else "?"
    st.markdown(
        f"**Latest run:** `{timestamp}` · commit `{sha}` ·"
        f" window `{window}d` · wall `{wall_str}`"
    )


# ── KPI grid ──────────────────────────────────────────────────────────────────


def _fmt_value(kind: str, value: Any) -> str:
    """Format a scalar for display in a metric tile."""
    if value is None:
        return "—"
    if kind == "int":
        return f"{int(value):,}"
    if kind == "float2":
        return f"{float(value):.2f}"
    if kind == "pct":
        return f"{float(value):.1f}%"
    if kind == "score":
        return f"{float(value):,.0f}"
    return str(value)


def _fmt_delta(kind: str, delta_val: float) -> str:
    """Format a delta with sign for display alongside the metric tile."""
    if kind == "int":
        return f"{int(delta_val):+,}"
    if kind == "float2":
        return f"{delta_val:+.2f}"
    if kind == "pct":
        return f"{delta_val:+.1f}%"
    if kind == "score":
        return f"{delta_val:+,.0f}"
    return f"{delta_val:+}"


def _delta_for(field: str, kind: str, deltas: dict[str, Any]) -> tuple[str | None, str]:
    """Return (delta_str_or_None, delta_color) for a metric tile."""
    entry = deltas.get(field) if isinstance(deltas, dict) else None
    if not isinstance(entry, dict):
        return None, "off"
    delta_val = entry.get("delta")
    if delta_val is None or delta_val == 0:
        return None, "off"
    return _fmt_delta(kind, float(delta_val)), _DELTA_POLARITY.get(field, "off")


def _render_kpi_groups(data: dict[str, Any]) -> None:
    """Render the four semantic KPI group cards."""
    agg = data.get("aggregate") or {}
    deltas = (data.get("trends") or {}).get("deltas") or {}
    for group_label, fields in _KPI_GROUPS:
        with st.container(border=True):
            st.markdown(f"**{group_label}**")
            cols = st.columns(len(fields))
            for col, (field, label, kind, help_text) in zip(cols, fields):
                value = agg.get(field)
                delta_str, delta_color = _delta_for(field, kind, deltas)
                col.metric(
                    label=label,
                    value=_fmt_value(kind, value),
                    delta=delta_str,
                    delta_color=delta_color,
                    border=True,
                    help=help_text,
                )


# ── Trends tab ────────────────────────────────────────────────────────────────


@st.fragment
def _render_trends_tab(log_path: Path | None) -> None:
    """Trends panel — historical aggregate lines from METRICS_LOG.md."""
    if log_path is None:
        st.caption(
            "No `METRICS_LOG.md` yet — historical trends will appear after two or more runs."
        )
        return
    try:
        df = cache.cached_parse_metrics_log(str(log_path), cache.mtime_of(log_path))
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not parse metrics log: {exc}")
        return
    if df.empty:
        st.caption("`METRICS_LOG.md` exists but contains no data rows.")
        return
    st.caption(f"From `METRICS_LOG.md` — {len(df)} runs.")
    fig = graphw.metrics_aggregate_lines(df)
    st.plotly_chart(fig, use_container_width=True)


# ── Hot-spots tab ─────────────────────────────────────────────────────────────


_HOTSPOT_DISPLAY_COLUMNS: tuple[str, ...] = (
    "rank",
    "path",
    "churn_90d",
    "complexity",
    "hotspot_score",
)


def _hotspots_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a tidy DataFrame from the hotspots.top_n list, ordered for display."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    cols = [c for c in _HOTSPOT_DISPLAY_COLUMNS if c in df.columns]
    return df[cols]


def _hotspots_column_config(df: pd.DataFrame) -> dict[str, Any]:
    """Build st.column_config for the hot-spots dataframe with progress bars."""
    max_churn = int(df["churn_90d"].max()) if "churn_90d" in df.columns else 1
    max_complex = int(df["complexity"].max()) if "complexity" in df.columns else 1
    return {
        "rank": st.column_config.NumberColumn("Rank", width="small"),
        "path": st.column_config.TextColumn("File", width="large"),
        "churn_90d": st.column_config.ProgressColumn(
            "Churn 90d", min_value=0, max_value=max_churn or 1, format="%d"
        ),
        "complexity": st.column_config.ProgressColumn(
            "Complexity", min_value=0, max_value=max_complex or 1, format="%d"
        ),
        "hotspot_score": st.column_config.NumberColumn("Score", format="%.0f"),
    }


def _render_hotspots_tab(data: dict[str, Any] | None) -> None:
    """Hot-spots panel — top-N risky files as an inline-bar dataframe."""
    if data is None:
        st.caption("No metrics report available — hot-spots require a JSON report.")
        return
    hotspots = data.get("hotspots") or {}
    rows = hotspots.get("top_n") or []
    if not rows:
        st.caption(
            "No hot-spots in this report (collector unavailable or empty result)."
        )
        return
    df = _hotspots_dataframe(rows)
    if df.empty:
        st.caption("No hot-spots to display.")
        return
    st.dataframe(
        df,
        column_config=_hotspots_column_config(df),
        hide_index=True,
        use_container_width=True,
    )
    source = hotspots.get("complexity_source", "lizard")
    st.caption(f"**Score** = `complexity × churn_90d`. Complexity source: `{source}`.")


# ── Collectors tab ────────────────────────────────────────────────────────────


def _collectors_dataframe(tool_availability: dict[str, Any]) -> pd.DataFrame:
    """Flatten tool_availability into a per-tool row DataFrame."""
    rows: list[dict[str, Any]] = []
    for tool in sorted(tool_availability.keys()):
        info = tool_availability.get(tool) or {}
        rows.append(
            {
                "Tool": tool,
                "Status": info.get("status", "?"),
                "Version": info.get("version") or "—",
                "Reason": info.get("reason") or "—",
                "Hint": info.get("hint") or "—",
            }
        )
    return pd.DataFrame(rows)


def _render_collectors_tab(data: dict[str, Any] | None) -> None:
    """Collectors panel — per-tool availability and status."""
    if data is None:
        st.caption(
            "No metrics report available — collector status requires a JSON report."
        )
        return
    ta = data.get("tool_availability") or {}
    if not ta:
        st.caption("No tool-availability info in this report.")
        return
    df = _collectors_dataframe(ta)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(
        "`available` collectors ran successfully."
        " `unavailable` / `error` / `timeout` indicate tools missing on the host"
        " or runtime failures — `/project-metrics` degrades gracefully when a"
        " collector is missing."
    )


# ── Raw tab ───────────────────────────────────────────────────────────────────


def _render_raw_tab(json_path: Path | None, data: dict[str, Any] | None) -> None:
    """Raw JSON panel — for full-fidelity inspection."""
    if json_path is None or data is None:
        st.caption("No metrics report available.")
        return
    st.markdown(f"**Source:** `{json_path.name}`")
    with st.expander("Show full report (JSON)"):
        st.json(data)
