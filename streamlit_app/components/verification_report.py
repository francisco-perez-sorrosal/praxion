"""Verification-report renderer — color-coded findings.

Renders `.ai-work/<slug>/VERIFICATION_REPORT.md` artifacts produced by the
verifier agent. Beyond the shared header + sidebar TOC pattern, this
renderer adds two color-coding affordances per the schema reference:

- **Verdict banner** — green / yellow / red banner reflecting the
  top-level `## Verdict` section's PASS / WARN / FAIL outcome
- **Inline finding chips** — every `**PASS**`, `**WARN**`, `**FAIL**`
  in section headers and table cells gets an emoji prefix so verdicts
  stand out at a glance without breaking the table layout

A heat-map summary at the top reports how many of each verdict-chip
appear in the body (an honest "how loud is this finding type" signal,
not a sub-criteria tally — a verifier may stamp the same verdict on a
sub-criterion, an AC group, and the overall report, so the count
overstates a strict "finding count").

MD body is read live from disk per `rules/writing/html-output-conventions.md`.
"""

from __future__ import annotations

import re
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


_VERDICT_EMOJI = {"PASS": "🟢", "FAIL": "🔴", "WARN": "🟡"}

# Match a bold verdict token inside the body. Two shapes the verifier emits:
# - `**PASS**` / `**FAIL**` / `**WARN**` (standalone in tables)
# - `**AC-A: PASS**` / `**Verdict: FAIL**` (label-prefixed)
# We capture the full bold span (group 1) for replacement, plus the verdict
# word (group 2) for color selection. The optional prefix requires a
# `<word>: ` separator so `**PASS-related**` does NOT match.
_VERDICT_TOKEN = re.compile(r"\*\*((?:[\w\s,-]+?:\s+)?(PASS|FAIL|WARN))\*\*")


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
    overall = _detect_overall_verdict(body)
    counts = _count_verdicts(body)

    _render_header(surface, title, summary, overall, counts)

    colored = _colorize_verdicts(body)
    sections = split_h2_sections(colored)
    _render_sidebar(sections)
    _render_body(sections)


def _render_header(
    surface: dict[str, Any],
    title: str,
    summary: str | None,
    overall: str | None,
    counts: dict[str, int],
) -> None:
    st.markdown(f"## ✅ {title}")
    if summary and not summary.lstrip().startswith("<!--"):
        st.markdown(f"*{summary}*")

    st.caption(f"Verification Report · source: `{surface['path']}`")

    if overall == "PASS":
        st.success(f"🟢 **Verdict: PASS** — `{surface['path']}`")
    elif overall == "FAIL":
        st.error(f"🔴 **Verdict: FAIL** — `{surface['path']}`")
    elif overall == "WARN":
        st.warning(f"🟡 **Verdict: WARN** — `{surface['path']}`")
    else:
        st.info("Verdict: (could not detect from `## Verdict` section)")

    if any(counts.values()):
        col_pass, col_warn, col_fail = st.columns(3)
        col_pass.metric("🟢 PASS chips", counts.get("PASS", 0))
        col_warn.metric("🟡 WARN chips", counts.get("WARN", 0))
        col_fail.metric("🔴 FAIL chips", counts.get("FAIL", 0))

    st.divider()


def _render_sidebar(sections: list[tuple[str, str]]) -> None:
    h2_titles = [t for t, _ in sections if t]
    with st.sidebar:
        st.markdown("**Sections**")
        if not h2_titles:
            st.caption("(No H2 sections in this verification report.)")
            return
        for heading in h2_titles:
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


# ---------------------------------------------------------------------------
# Verdict detection + colorization
# ---------------------------------------------------------------------------


def _detect_overall_verdict(body: str) -> str | None:
    """Return the verdict in the `## Verdict` H2 section, or None.

    The verifier convention is to place a single bold verdict token at the
    top of that section's body. We scan only that section to avoid picking
    up the first bold verdict that happens to appear earlier in the file.
    """
    for heading, section_body in split_h2_sections(body):
        if heading.strip().lower() == "verdict":
            match = _VERDICT_TOKEN.search(section_body)
            return match.group(2) if match else None
    return None


def _count_verdicts(body: str) -> dict[str, int]:
    """Count verdict-chip occurrences by verdict word.

    `_VERDICT_TOKEN.findall` returns `(full_bold_inner, verdict_word)` tuples
    because the regex has two capture groups; only the verdict word matters
    for the histogram.
    """
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0}
    for _, verdict in _VERDICT_TOKEN.findall(body):
        counts[verdict] += 1
    return counts


def _colorize_verdicts(body: str) -> str:
    """Prefix each verdict-chip bold span with its emoji indicator.

    Done as a regex substitution on the source markdown so st.markdown's
    table rendering still receives valid pipe-delimited rows; we only add
    a leading emoji + space, never break the cell structure. The full
    bold span (e.g. `AC-A: PASS`) is preserved — only the emoji prefix
    is added.
    """

    def _replace(match: re.Match[str]) -> str:
        full_bold_inner = match.group(1)
        verdict = match.group(2)
        emoji = _VERDICT_EMOJI[verdict]
        return f"{emoji} **{full_bold_inner}**"

    return _VERDICT_TOKEN.sub(_replace, body)


__all__ = ["render"]
