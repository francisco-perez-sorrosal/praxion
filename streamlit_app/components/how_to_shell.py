"""Diátaxis how-to shell — goal-driven recipe wrapper.

Renders MD surfaces with `diataxis: how-to` frontmatter. The reading mode
for a how-to is "land on the section that solves my problem", not the
linear read of an explanation or the lookup-scan of a reference. So this
shell surfaces two sidebar blocks:

- **Sections** — full H2 TOC (anchor jumps for the whole document)
- **Quick links** — direct anchor jumps to common helper sections
  (Prerequisites / Setup / Quick Start / Troubleshooting) when present

Used for `docs/cursor-compat.md`, `docs/external-api-docs.md`, and
`docs/observability.md`.

MD body is read live from disk per `rules/writing/html-output-conventions.md`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from streamlit_app.components._base import (
    heading_to_anchor,
    read_md,
    split_h2_sections,
    surface_summary,
    surface_title,
)


# H2 titles that benefit from direct anchor-jump access in the sidebar.
# Match is case-insensitive; surface order in `_QUICK_LINK_LABELS` is
# preserved when rendering. The label order roughly mirrors a reader's
# decision flow ("can I run this?" → "how do I run it?" → "it broke,
# now what?").
_QUICK_LINK_LABELS = (
    "Prerequisites",
    "Setup",
    "Install",
    "Quick Start",
    "Configuration",
    "Troubleshooting",
)
_QUICK_LINK_TITLES = frozenset(label.lower() for label in _QUICK_LINK_LABELS)


def render(surface: dict[str, Any], project_root: Path) -> None:
    path = project_root / surface["path"]
    if not path.exists():
        st.error(f"Source file not found: `{surface['path']}`")
        return

    try:
        _, body = read_md(path)
    except Exception as exc:  # noqa: BLE001 — surface read errors clearly
        st.error(f"Failed to parse `{surface['path']}`: {exc}")
        return

    title = surface_title(surface, body)
    summary = surface_summary(surface, body)
    sections = split_h2_sections(body)

    _render_header(surface, title, summary)
    _render_sidebar(sections)
    _render_body(sections)


def _render_header(surface: dict[str, Any], title: str, summary: str | None) -> None:
    st.markdown(f"## 🛠 {title}")
    if summary and not summary.lstrip().startswith("<!--"):
        st.markdown(f"*{summary}*")
    st.caption(
        f"How-to · audience: {surface.get('audience', 'developer')} · "
        f"source: `{surface['path']}`"
    )
    st.divider()


def _render_sidebar(sections: list[tuple[str, str]]) -> None:
    h2_titles = [t for t, _ in sections if t]
    quick_links = _collect_quick_links(h2_titles)

    with st.sidebar:
        st.markdown("**Sections**")
        if not h2_titles:
            st.caption("(No H2 sections in this how-to.)")
        else:
            for heading in h2_titles:
                anchor = heading_to_anchor(heading)
                st.markdown(f"- [{heading}](#{anchor})")

        if quick_links:
            st.divider()
            st.markdown("**Quick links**")
            for heading in quick_links:
                anchor = heading_to_anchor(heading)
                st.markdown(f"- [{heading}](#{anchor})")


def _render_body(sections: list[tuple[str, str]]) -> None:
    pre_h2 = next((b for t, b in sections if not t and b), "")
    if pre_h2:
        st.markdown(pre_h2)

    for heading, section_body in [(t, b) for t, b in sections if t]:
        anchor = heading_to_anchor(heading)
        # Streamlit doesn't natively support fragment anchors; emit one as
        # declarative HTML (no JS) per html-output-conventions.md.
        st.markdown(f"<span id='{anchor}'></span>", unsafe_allow_html=True)
        st.markdown(f"### {heading}")
        st.markdown(section_body)


def _collect_quick_links(h2_titles: list[str]) -> list[str]:
    """Return H2 titles that match a `_QUICK_LINK_LABELS` entry, in the
    document's source order (so the sidebar respects authorial intent
    rather than imposing an external ordering).
    """
    return [t for t in h2_titles if t.strip().lower() in _QUICK_LINK_TITLES]


__all__ = ["render"]
