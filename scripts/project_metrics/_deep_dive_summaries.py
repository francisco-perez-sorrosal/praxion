"""Per-collector Deep Dive summarizers.

Each function takes one collector's ``data`` dict and returns a list of
bullet lines that render BELOW the layout bullets in ``_report_deep_dive``.
Summarizers exist so per-file dicts (churn_90d, ownership, files) and
similar heavy structures collapse to a few highlight lines instead of
being dumped wholesale into the MD report. Full per-file/per-pair detail
always remains available in the JSON sibling artifact.

Split out of ``_report_deep_dive.py`` (td-166): these nine functions are
pure data-in/lines-out transforms with no dependency on the layout map,
the registries, or the rendering entry point — a natural module boundary
along the existing summarizer-registry seam.
"""

from __future__ import annotations

from typing import Any

from scripts.project_metrics._report_format import (
    NULL_CELL,
    fmt_float_2,
    fmt_int,
    fmt_pct,
    fmt_score,
)

__all__ = [
    "_summarize_git",
    "_summarize_lizard",
    "_summarize_complexipy",
    "_pydeps_coverage_line",
    "_summarize_pydeps",
    "_summarize_scc",
    "_summarize_readiness",
    "_summarize_coverage_scope",
    "_summarize_coverage",
]


# ---------------------------------------------------------------------------
# How many lowest-covered files the coverage deep-dive lists before it
# truncates. Larger than the top-5 the other summarizers use because this
# list is read against a floor rather than skimmed for highlights: every
# module below the floor that the cap drops is a finding nobody can file.
# The cap is never applied silently — see ``_summarize_coverage``.
# ---------------------------------------------------------------------------

_COVERAGE_PER_FILE_CAP = 10


def _summarize_git(data: dict[str, Any]) -> list[str]:
    """Highlights for git's heavy per-file dicts; full data lives in JSON."""

    lines: list[str] = []
    churn = data.get("churn_90d")
    if isinstance(churn, dict) and churn:
        top = sorted(churn.items(), key=lambda kv: -fmt_score(kv[1]))[:5]
        lines.append(f"- Top {len(top)} churning files (of {len(churn)} touched):")
        for path, value in top:
            lines.append(f"    - `{path}` — {fmt_int(value)} lines")
    coupling = data.get("change_coupling")
    if isinstance(coupling, dict):
        pairs = coupling.get("pairs", [])
        if isinstance(pairs, list) and pairs:
            top_pairs = pairs[:5]
            threshold = coupling.get("threshold", "?")
            lines.append(
                f"- Top {len(top_pairs)} co-changing pairs "
                f"(threshold ≥{threshold}, {len(pairs)} total):"
            )
            for pair in top_pairs:
                files = pair.get("files", [])
                count = pair.get("count", "?")
                if isinstance(files, list) and len(files) == 2:
                    lines.append(f"    - `{files[0]}` ↔ `{files[1]}` — {count} commits")
    ownership = data.get("ownership")
    if isinstance(ownership, dict) and ownership:
        sole = sum(
            1
            for entry in ownership.values()
            if isinstance(entry, dict)
            and isinstance(entry.get("major"), list)
            and len(entry["major"]) == 1
        )
        total = len(ownership)
        pct = (sole / total * 100.0) if total else 0.0
        lines.append(f"- Files with a single major owner: {sole}/{total} ({pct:.1f}%)")
    age = data.get("age_days")
    if isinstance(age, dict) and age:
        try:
            oldest_path, oldest_days = max(age.items(), key=lambda kv: kv[1])
            newest_path, newest_days = min(age.items(), key=lambda kv: kv[1])
            lines.append(
                f"- Oldest in window: `{oldest_path}` ({oldest_days} days); "
                f"newest: `{newest_path}` ({newest_days} days)"
            )
        except (TypeError, ValueError):
            pass
    return lines


def _summarize_lizard(data: dict[str, Any]) -> list[str]:
    """Highlights for lizard's per-file CCN map and aggregate block."""

    lines: list[str] = []
    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        for key, label, formatter in (
            ("total_function_count", "Functions analyzed", fmt_int),
            ("ccn_p95", "CCN p95", fmt_float_2),
            ("ccn_p75", "CCN p75", fmt_float_2),
        ):
            if key in aggregate and aggregate[key] is not None:
                lines.append(f"- {label}: {formatter(aggregate[key])}")
    files = data.get("files")
    if isinstance(files, dict) and files:
        scored: list[tuple[str, float, int]] = []
        for path, file_data in files.items():
            if not isinstance(file_data, dict):
                continue
            score = file_data.get("p95_ccn")
            if score is None:
                score = file_data.get("max_ccn", 0)
            scored.append((path, fmt_score(score), int(file_data.get("function_count", 0))))
        scored.sort(key=lambda triple: -triple[1])
        top = scored[:5]
        if top:
            lines.append(f"- Top {len(top)} most complex files by p95 CCN (of {len(files)}):")
            for path, score, fcount in top:
                score_str = f"{score:.1f}" if score % 1 else f"{int(score)}"
                lines.append(f"    - `{path}` — p95 CCN {score_str} ({fcount} functions)")
    return lines


def _summarize_complexipy(data: dict[str, Any]) -> list[str]:
    """Highlights for complexipy's per-file cognitive map and aggregate block."""

    lines: list[str] = []
    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        for key, label, formatter in (
            ("total_function_count", "Functions analyzed", fmt_int),
            ("cognitive_p95", "Cognitive p95", fmt_float_2),
            ("cognitive_p75", "Cognitive p75", fmt_float_2),
        ):
            if key in aggregate and aggregate[key] is not None:
                lines.append(f"- {label}: {formatter(aggregate[key])}")
    files = data.get("files")
    if isinstance(files, dict) and files:
        scored: list[tuple[str, float, int]] = []
        for path, file_data in files.items():
            if not isinstance(file_data, dict):
                continue
            score = file_data.get("p95_cognitive")
            if score is None:
                score = file_data.get("max_cognitive", 0)
            scored.append((path, fmt_score(score), int(file_data.get("function_count", 0))))
        scored.sort(key=lambda triple: -triple[1])
        top = scored[:5]
        if top:
            lines.append(
                f"- Top {len(top)} most cognitively complex files (p95 cognitive, of {len(files)}):"
            )
            for path, score, fcount in top:
                score_str = f"{score:.1f}" if score % 1 else f"{int(score)}"
                lines.append(f"    - `{path}` — p95 cognitive {score_str} ({fcount} functions)")
    return lines


def _pydeps_coverage_line(aggregate: dict[str, Any]) -> str | None:
    """Render the analysed-vs-repository denominator that bounds ``cyclic_deps``.

    Without it, ``Non-trivial cyclic SCCs: 0`` reads as a repo-wide all-clear
    even when the import graph covered a fraction of the tree. pydeps cannot
    see directories of loose modules (no ``__init__.py``), so some shortfall is
    expected — stating it is what keeps the zero a bounded claim.
    """

    analyzed = aggregate.get("analyzed_python_files")
    total = aggregate.get("repo_python_files")
    if not isinstance(analyzed, int) or not isinstance(total, int) or total <= 0:
        return None
    pct = aggregate.get("python_file_coverage_pct")
    pct_str = f"{pct}%" if isinstance(pct, (int, float)) else "n/a"
    roots = aggregate.get("package_roots")
    root_count = len(roots) if isinstance(roots, list) else 0
    return (
        f"- Import-graph coverage: {fmt_int(analyzed)} of {fmt_int(total)} "
        f"tracked Python files ({pct_str}) across {root_count} package "
        f"root{'' if root_count == 1 else 's'}"
    )


def _summarize_pydeps(data: dict[str, Any]) -> list[str]:
    """Highlights for pydeps's import-graph rollup."""

    lines: list[str] = []
    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        for key, label, formatter in (
            ("total_modules", "Modules analyzed", fmt_int),
            ("cyclic_deps", "Non-trivial cyclic SCCs", fmt_int),
        ):
            if key in aggregate and aggregate[key] is not None:
                lines.append(f"- {label}: {formatter(aggregate[key])}")
        coverage_line = _pydeps_coverage_line(aggregate)
        if coverage_line is not None:
            lines.append(coverage_line)
            roots = aggregate.get("package_roots")
            if isinstance(roots, list) and roots:
                lines.append("- Package roots analyzed: " + ", ".join(f"`{r}`" for r in roots))
    cyclic_sccs = data.get("cyclic_sccs")
    if isinstance(cyclic_sccs, list) and cyclic_sccs:
        lines.append(f"- Cyclic SCCs detected ({len(cyclic_sccs)}):")
        for index, scc in enumerate(cyclic_sccs[:5], start=1):
            if not isinstance(scc, list):
                continue
            members = ", ".join(f"`{m}`" for m in scc[:6])
            extra = "" if len(scc) <= 6 else f" (+{len(scc) - 6} more)"
            lines.append(f"    - SCC {index} ({len(scc)} modules): {members}{extra}")
    modules = data.get("modules")
    if isinstance(modules, dict) and modules:
        # Top 5 most-coupled modules by Ce + Ca.
        coupling: list[tuple[str, float, int, int]] = []
        for name, entry in modules.items():
            if not isinstance(entry, dict):
                continue
            ca = int(entry.get("afferent_coupling", 0) or 0)
            ce = int(entry.get("efferent_coupling", 0) or 0)
            coupling.append((name, float(ca + ce), ca, ce))
        coupling.sort(key=lambda quad: -quad[1])
        top = coupling[:5]
        if top:
            lines.append(f"- Top {len(top)} most-coupled modules by Ca + Ce (of {len(modules)}):")
            for name, total, ca, ce in top:
                lines.append(f"    - `{name}` — Ca {ca} + Ce {ce} = {int(total)}")
    return lines


def _summarize_scc(data: dict[str, Any]) -> list[str]:
    """Highlights for scc's language breakdown; full table lives further down and in JSON."""

    lines: list[str] = []
    breakdown = data.get("language_breakdown")
    if not isinstance(breakdown, dict) or not breakdown:
        return lines
    scored: list[tuple[str, int, int]] = []
    for name, entry in breakdown.items():
        if not isinstance(entry, dict):
            continue
        try:
            sloc_int = int(entry.get("sloc", 0))
        except (TypeError, ValueError):
            sloc_int = 0
        try:
            file_int = int(entry.get("file_count", 0))
        except (TypeError, ValueError):
            file_int = 0
        scored.append((str(name), file_int, sloc_int))
    scored.sort(key=lambda triple: -triple[2])
    top = scored[:5]
    if not top:
        return lines
    lines.append(f"- Top {len(top)} languages by SLOC (of {len(breakdown)}):")
    for language, files, sloc in top:
        lines.append(f"    - {language} — {fmt_int(files)} files, {fmt_int(sloc)} SLOC")
    return lines


def _summarize_readiness(data: dict[str, Any]) -> list[str]:
    """Highlights for agent-readiness: LLM scoring status + recommendations.

    Renders the LLM tier status and a bounded list of failing criteria with
    their remediation guidance — the human-readable face of the recommendations
    the evaluation embeds per-criterion. Full per-criterion detail (explanation,
    pass/fail, scope) lives in the JSON sibling artifact.
    """

    lines: list[str] = []

    if data.get("weighting_active"):
        adj_pct = data.get("adjusted_pass_pct")
        adj_level = data.get("adjusted_level")
        canon_pct = data.get("pass_pct")
        canon_level = data.get("level")
        if isinstance(adj_pct, (int, float)) and isinstance(canon_pct, (int, float)):
            lines.append(
                f"- Adjusted (your weights): {adj_pct * 100:.0f}% · L{adj_level} "
                f"(canonical Factory: {canon_pct * 100:.0f}% · L{canon_level})"
            )
        weights = data.get("pillar_weights")
        if isinstance(weights, dict):
            tuned = [f"{p} ×{w:g}" for p, w in sorted(weights.items()) if w != 1.0]
            if tuned:
                lines.append(f"- Pillar weights: {', '.join(tuned)} (others ×1)")

    llm = data.get("llm")
    if isinstance(llm, dict):
        status = llm.get("status")
        model = llm.get("model")
        if status == "scored" and model:
            lines.append(f"- LLM scoring: scored via `{model}`")
        elif status:
            lines.append(f"- LLM scoring: {status}")

    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        return lines
    failing = [
        c
        for c in criteria
        if isinstance(c, dict) and c.get("passed") is False and c.get("remediation")
    ]
    if not failing:
        return lines
    failing.sort(key=lambda c: (int(c.get("level", 1)), str(c.get("id", ""))))
    shown = failing[:10]
    lines.append(f"- Recommendations for {len(failing)} unmet criteria:")
    for crit in shown:
        tag = " (AI-tailored)" if crit.get("remediation_source") == "llm" else ""
        lines.append(
            f"    - L{crit.get('level')} `{crit.get('id')}`{tag}: {crit.get('remediation')}"
        )
    if len(failing) > len(shown):
        lines.append(f"    - …and {len(failing) - len(shown)} more (see JSON sibling)")
    return lines


def _summarize_coverage_scope(data: dict[str, Any]) -> list[str]:
    """Render the measured-vs-source scope line, plus a withheld-coverage note when partial.

    ``line_pct`` alone cannot distinguish a repo-wide measurement from a
    scoped one that happens to still be present and well-formed -- the exact
    failure this project's own ``coverage.xml`` demonstrated: two runs at the
    same commit recorded 0.8514 then 0.5071 because a scoped test invocation
    had rewritten the artifact in between, with no change to what it claimed
    to measure. Stating scope in the human-facing report, not just the JSON
    sibling, is what makes that distinction visible to a reader.
    """

    lines: list[str] = []
    measured = data.get("measured_files")
    total_files = data.get("source_files_total")
    if isinstance(measured, int) and isinstance(total_files, int) and total_files > 0:
        scope_pct = data.get("artifact_scope_pct")
        pct_str = fmt_pct(scope_pct) if isinstance(scope_pct, (int, float)) else NULL_CELL
        lines.append(
            f"- Artifact scope: {fmt_int(measured)} of {fmt_int(total_files)} "
            f"source files ({pct_str})"
        )
    if data.get("status") == "partial":
        lines.append(
            "- Line coverage withheld: the artifact measures too small a share of "
            "the repository to trust a repo-wide percentage — regenerate from the "
            "full test suite; see the scope line above."
        )
    return lines


def _summarize_coverage(data: dict[str, Any]) -> list[str]:
    """Artifact scope, then lowest-covered files, ascending — the bottom of the distribution.

    The ``line_pct`` bullet above is an aggregate, and an aggregate is
    structurally blind to one badly-tested module inside a healthy repository
    — precisely the failure a *per-module* coverage floor exists to catch.
    This project's own report is the worked example: 85.02% overall, nine files
    under 70%, the worst at 42.86%. Rendering only the aggregate let that read
    as a clean bill of health, and left the sentinel's per-module coverage
    check with no per-module input to read.

    The cap is **disclosed, never implied**. The header states shown-of-total,
    and a truncated list names the coverage every omitted file clears, so a
    reader holding a floor at or below that bound knows the list is exhaustive
    for that floor, and a reader holding a higher one is told plainly to read
    the JSON. A silent top-N would reintroduce the same false all-clear in a
    smaller font: the reader could not tell "no further offenders" from
    "offenders not shown".

    The floor itself is deliberately *not* encoded here. It is the consumer's
    parameter (the sentinel defaults to 70%), and duplicating it in the
    renderer would create a second site to drift.
    """

    scope_lines = _summarize_coverage_scope(data)

    per_file = data.get("per_file")
    if not isinstance(per_file, dict) or not per_file:
        return scope_lines

    ranked: list[tuple[float, str, Any, Any]] = []
    for path, entry in per_file.items():
        if not isinstance(entry, dict):
            continue
        pct = entry.get("line_pct")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            continue
        ranked.append((float(pct), str(path), entry.get("lines_covered"), entry.get("lines_total")))
    if not ranked:
        return scope_lines

    # Path breaks ties so equally-covered files order deterministically.
    ranked.sort(key=lambda row: (row[0], row[1]))
    shown = ranked[:_COVERAGE_PER_FILE_CAP]
    omitted = len(ranked) - len(shown)

    scope = f"all {len(ranked)}" if omitted == 0 else f"{len(shown)} of {len(ranked)}"
    lines = [*scope_lines, f"- Lowest-covered files ({scope}, worst first):"]
    for pct, path, covered, total in shown:
        detail = ""
        if isinstance(covered, int) and isinstance(total, int):
            detail = f" ({covered}/{total} lines)"
        lines.append(f"    - `{path}` — {fmt_pct(pct)}{detail}")

    if omitted:
        bound = fmt_pct(ranked[len(shown)][0])
        lines.append(
            f"- The {omitted} files not listed are all at or above {bound} line coverage "
            f"— a floor at or below {bound} is fully covered by this list; a higher floor "
            f"must read `coverage.per_file` in the JSON sibling."
        )
    return lines
