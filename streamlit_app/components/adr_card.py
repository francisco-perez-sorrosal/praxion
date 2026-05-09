"""ADR card renderer — frontmatter chips + body collapse + supersede graph.

Used for surfaces under `.ai-state/decisions/<NNN>-*.md` (manifest assigns
`renderer: adr_card`). Per the doc-manifest schema reference, this renderer
provides three features that the default markdown view does not:

1. Frontmatter chips — status, category, date, author, tags
2. Cross-reference graph — supersedes / superseded_by / re_affirms /
   re_affirmed_by / affected_reqs / affected_files
3. Body collapse — H2 sections become expanders; Context / Decision /
   Prior Decision are open by default; long sections start collapsed

MD body is read live from disk per `rules/writing/html-output-conventions.md`
— manifest frontmatter is a snapshot and may drift between regenerations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from streamlit_app.components._base import (
    read_md,
    split_h2_sections,
    surface_title,
)


_STATUS_INDICATOR = {
    "accepted": "🟢",
    "proposed": "🟡",
    "superseded": "⚪",
    "rejected": "🔴",
    "re-affirmation": "🔵",
}

_SECTIONS_OPEN_BY_DEFAULT = {"Context", "Decision", "Prior Decision"}


def render(surface: dict[str, Any], project_root: Path) -> None:
    path = project_root / surface["path"]
    if not path.exists():
        st.error(f"Source file not found: `{surface['path']}`")
        return

    try:
        live_fm, body = read_md(path)
    except Exception as exc:  # noqa: BLE001 — surface read errors clearly
        st.error(f"Failed to parse `{surface['path']}`: {exc}")
        return

    # Live frontmatter is authoritative; manifest snapshot is the fallback.
    fm: dict[str, Any] = live_fm or surface.get("frontmatter") or {}

    _render_header(surface, fm, body)
    _render_cross_references(fm)
    _render_body(body, fm.get("status", ""))


def _render_header(surface: dict[str, Any], fm: dict[str, Any], body: str) -> None:
    status = str(fm.get("status") or "?")
    indicator = _STATUS_INDICATOR.get(status, "⚫")
    adr_id = str(fm.get("id") or "")
    title = str(fm.get("title") or surface_title(surface, body))

    id_chip = f"`{adr_id}` — " if adr_id else ""
    st.markdown(f"## {indicator} {id_chip}{title}")

    meta_parts: list[str] = [f"status: `{status}`"]
    if fm.get("category"):
        meta_parts.append(f"category: `{fm['category']}`")
    if fm.get("date"):
        meta_parts.append(f"`{fm['date']}`")

    made_by = str(fm.get("made_by") or "")
    agent_type = str(fm.get("agent_type") or "")
    if made_by == "agent" and agent_type:
        meta_parts.append(f"by `{agent_type}`")
    elif made_by:
        meta_parts.append(f"by `{made_by}`")
    st.caption(" · ".join(meta_parts))

    tags = fm.get("tags") or []
    if tags:
        tag_chips = " · ".join(f"`{t}`" for t in tags)
        st.caption(f"tags: {tag_chips}")

    st.caption(f"`{surface['path']}`")
    st.divider()


def _render_cross_references(fm: dict[str, Any]) -> None:
    relations = [
        ("Supersedes", _as_list(fm.get("supersedes"))),
        ("Superseded by", _as_list(fm.get("superseded_by"))),
        ("Re-affirms", _as_list(fm.get("re_affirms"))),
        ("Re-affirmed by", _as_list(fm.get("re_affirmed_by"))),
        ("Affected REQs", _as_list(fm.get("affected_reqs"))),
    ]
    relations = [(label, items) for label, items in relations if items]
    affected_files = _as_list(fm.get("affected_files"))

    if not relations and not affected_files:
        return

    st.markdown("**Related**")
    for label, items in relations:
        chips = " · ".join(f"`{x}`" for x in items)
        st.markdown(f"- {label}: {chips}")

    if affected_files:
        if len(affected_files) <= 4:
            chips = " · ".join(f"`{f}`" for f in affected_files)
            st.markdown(f"- Affected files: {chips}")
        else:
            with st.expander(f"Affected files ({len(affected_files)})", expanded=False):
                for f in affected_files:
                    st.markdown(f"- `{f}`")
    st.divider()


def _render_body(body: str, status: str) -> None:
    sections = split_h2_sections(body)
    pre_h2 = next((b for t, b in sections if not t and b), "")
    h2_sections = [(t, b) for t, b in sections if t]

    if pre_h2:
        st.markdown(pre_h2)

    for title, section_body in h2_sections:
        with st.expander(title, expanded=_section_default_open(title, status)):
            st.markdown(section_body)


def _section_default_open(section_title: str, status: str) -> bool:
    if section_title in _SECTIONS_OPEN_BY_DEFAULT:
        return True
    # On terminal-status ADRs the reader is usually doing forensic reading;
    # surface Consequences alongside the always-open sections.
    return status in ("superseded", "rejected") and section_title == "Consequences"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    return [str(value)]


__all__ = ["render"]
