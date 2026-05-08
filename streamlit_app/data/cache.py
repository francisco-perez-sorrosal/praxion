"""Cache layer for the Praxion Pipeline Dashboard.

Wraps `data.discovery` (filesystem listing) and `data.parsers` (file content)
with `@st.cache_data` keyed on (path_str, mtime).

Convention 1 exception: this is the ONLY module under `streamlit_app/data/`
that imports streamlit. The import is limited to `from streamlit import cache_data`.
Convention 2: every ``cached_parse_*`` function takes ``mtime: float`` as its
cache-busting parameter — note the parameter name does NOT start with an
underscore. Streamlit excludes ``_``-prefixed args from the cache hash; using
``_mtime`` would silently disable invalidation. The discovery wrappers below
DO use a leading-underscore ``_now_bucket`` arg deliberately, paired with
``ttl=15`` — that pattern is for unhashable cache-key contributors, not for
file-content invalidation. See `rules/swe/dashboard-conventions.md` §2.

Invalidation model
------------------
**Parser wrappers** (``cached_parse_*``) are keyed on ``(path_str, mtime)``.
Callers obtain the mtime via ``mtime_of(path)`` and pass it as the second
positional argument.

**Discovery wrappers** (``cached_list_*``) use ``ttl=15`` because directory
listings do not have a single representative mtime.  Callers pass
``_now_bucket = int(time.time() / 15)`` (a 15-second bucket integer) so that
all callers within the same window share a cache entry:

    import time
    bucket = int(time.time() / 15)
    slugs = cached_list_active_workshops(str(root), bucket)

**Low-level wrappers** (``cached_read_file``, ``cached_read_json``,
``cached_list_dir``) provide a path-agnostic cache layer for callers that need
raw file text, JSON, or directory listings without parser overhead.

    # Correct — parser wrapper
    fm, body = cached_parse_frontmatter(str(path), mtime_of(path))

    # Correct — clearing all caches when PROJECT_ROOT changes
    clear_all()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from streamlit import cache_data  # ONLY allowed streamlit import in data/

from . import discovery, parsers

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TTL_SECONDS = 15

# ---------------------------------------------------------------------------
# mtime helpers
# ---------------------------------------------------------------------------


def mtime_of(path: Path) -> float:
    """Return path.stat().st_mtime; 0.0 for non-existent paths.

    Stable cache key for absent files — callers can unconditionally write
    ``cached_parse_X(path, mtime_of(path))`` regardless of whether *path*
    exists.
    """
    try:
        return path.stat().st_mtime
    except (FileNotFoundError, PermissionError, OSError):
        return 0.0


# Alias used by callers that prefer the shorter name from the low-level API.
get_mtime = mtime_of


# ---------------------------------------------------------------------------
# Low-level cached wrappers (path-agnostic primitives)
# ---------------------------------------------------------------------------


@cache_data
def cached_read_file(path: Path, mtime: float) -> Optional[str]:
    """Return file text, or None when the file does not exist or is unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None


@cache_data
def cached_read_json(path: Path, mtime: float) -> Optional[dict]:  # type: ignore[type-arg]
    """Return parsed JSON dict, or None on any error (missing file or bad JSON)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, PermissionError, OSError, json.JSONDecodeError):
        return None


@cache_data
def cached_list_dir(path: Path, _now_bucket: int) -> list[Path]:
    """Return sorted list of children under *path*, or [] if path does not exist."""
    try:
        return sorted(path.iterdir(), key=lambda p: p.name)
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return []


# ---------------------------------------------------------------------------
# Cached parser wrappers — keyed on (path_str, mtime)
# ---------------------------------------------------------------------------


@cache_data
def cached_parse_frontmatter(path_str: str, mtime: float) -> tuple[dict, str]:  # type: ignore[type-arg]
    """Return ``(frontmatter_dict, body_text)`` for a markdown file."""
    return parsers.parse_frontmatter(Path(path_str))


@cache_data
def cached_parse_yaml(path_str: str, mtime: float) -> Any:
    """Return the parsed Python structure from a YAML file."""
    return parsers.parse_yaml(Path(path_str))


@cache_data
def cached_parse_md_sections(
    path_str: str, mtime: float, level: int = 2
) -> dict[str, str]:
    """Return ``{heading_text: section_body}`` for a markdown file."""
    return parsers.parse_md_sections(Path(path_str), level)


@cache_data
def cached_parse_metrics_log(path_str: str, mtime: float) -> pd.DataFrame:
    """Return METRICS_LOG.md parsed into a DataFrame."""
    return parsers.parse_metrics_log(Path(path_str))


@cache_data
def cached_parse_metrics_report_json(path_str: str, mtime: float) -> dict[str, Any]:
    """Return a METRICS_REPORT JSON file parsed into a dict."""
    return parsers.parse_metrics_report_json(Path(path_str))


@cache_data
def cached_parse_sentinel_log(path_str: str, mtime: float) -> pd.DataFrame:
    """Return SENTINEL_LOG.md parsed into a DataFrame."""
    return parsers.parse_sentinel_log(Path(path_str))


@cache_data
def cached_parse_wip(path_str: str, mtime: float) -> dict[str, Any]:
    """Return WIP.md parsed into structured data."""
    return parsers.parse_wip(Path(path_str))


@cache_data
def cached_parse_progress(path_str: str, mtime: float) -> list[dict[str, Any]]:
    """Return PROGRESS.md parsed into a list of phase-transition event dicts."""
    return parsers.parse_progress(Path(path_str))


# ---------------------------------------------------------------------------
# Cached discovery wrappers — TTL-based (15 s)
# ---------------------------------------------------------------------------
# Directory listings have no single representative mtime.  Callers pass
# ``_now_bucket = int(time.time() / 15)`` (a 15-second bucket integer) to
# align invalidation cycles across the app.  The leading underscore tells
# Streamlit not to include the value in its hash; TTL=15s drives expiry.


@cache_data(ttl=TTL_SECONDS)
def cached_list_active_workshops(root_str: str, _now_bucket: int) -> list[str]:
    """Return list of active workshop dir paths as strings."""
    return [str(p) for p in discovery.list_active_workshops(Path(root_str))]


@cache_data(ttl=TTL_SECONDS)
def cached_list_adrs_finalized(root_str: str, _now_bucket: int) -> list[str]:
    """Return list of finalized ADR paths as strings, NNN-sorted ascending."""
    return [str(p) for p in discovery.list_adrs_finalized(Path(root_str))]


@cache_data(ttl=TTL_SECONDS)
def cached_list_adrs_drafts(root_str: str, _now_bucket: int) -> list[str]:
    """Return list of draft ADR paths as strings, alpha-sorted ascending."""
    return [str(p) for p in discovery.list_adrs_drafts(Path(root_str))]


@cache_data(ttl=TTL_SECONDS)
def cached_list_sentinel_reports(root_str: str, _now_bucket: int) -> list[str]:
    """Return SENTINEL_REPORT paths as strings, newest filename first."""
    return [str(p) for p in discovery.list_sentinel_reports(Path(root_str))]


@cache_data(ttl=TTL_SECONDS)
def cached_list_metrics_reports_md(root_str: str, _now_bucket: int) -> list[str]:
    """Return METRICS_REPORT .md paths as strings, newest filename first."""
    return [str(p) for p in discovery.list_metrics_reports_md(Path(root_str))]


@cache_data(ttl=TTL_SECONDS)
def cached_list_metrics_reports_json(root_str: str, _now_bucket: int) -> list[str]:
    """Return METRICS_REPORT .json paths as strings, newest filename first."""
    return [str(p) for p in discovery.list_metrics_reports_json(Path(root_str))]


@cache_data(ttl=TTL_SECONDS)
def cached_list_idea_ledgers(root_str: str, _now_bucket: int) -> list[str]:
    """Return IDEA_LEDGER paths as strings, newest filename first."""
    return [str(p) for p in discovery.list_idea_ledgers(Path(root_str))]


@cache_data(ttl=TTL_SECONDS)
def cached_list_specs(root_str: str, _now_bucket: int) -> list[str]:
    """Return archived SPEC paths as strings, newest filename first."""
    return [str(p) for p in discovery.list_specs(Path(root_str))]


# ---------------------------------------------------------------------------
# Bulk-clear helper
# ---------------------------------------------------------------------------


def clear_all() -> None:
    """Clear every cache wrapper in this module.

    Call when ``PRAXION_PROJECT_ROOT`` changes so stale directory listings
    and file content do not persist from the previous project.
    """
    cached_read_file.clear()
    cached_read_json.clear()
    cached_list_dir.clear()
    cached_parse_frontmatter.clear()
    cached_parse_yaml.clear()
    cached_parse_md_sections.clear()
    cached_parse_metrics_log.clear()
    cached_parse_metrics_report_json.clear()
    cached_parse_sentinel_log.clear()
    cached_parse_wip.clear()
    cached_parse_progress.clear()
    cached_list_active_workshops.clear()
    cached_list_adrs_finalized.clear()
    cached_list_adrs_drafts.clear()
    cached_list_sentinel_reports.clear()
    cached_list_metrics_reports_md.clear()
    cached_list_metrics_reports_json.clear()
    cached_list_idea_ledgers.clear()
    cached_list_specs.clear()
