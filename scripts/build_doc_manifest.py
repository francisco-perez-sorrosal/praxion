#!/usr/bin/env python3
"""Build .ai-state/doc_manifest.yaml from the project's documentation surfaces.

Walks the project filesystem according to the schema specified in
``skills/doc-management/references/doc-manifest-schema.md`` and emits a YAML
manifest the per-project Streamlit dashboard reads at session start.

The generator is deterministic: given the same filesystem state, it always
emits identical YAML (modulo `generated_at`). This is the contract that lets
the post-merge hook regenerate without merge drivers.

Usage::

    python3 scripts/build_doc_manifest.py [--root <path>] [--check]

  --root   Project root (default: cwd)
  --check  Don't write; exit 0 if manifest is already in sync, 1 otherwise.
           Used by sentinel EC07-doc-manifest-fresh and CI.

Skipped:
- Files under node_modules/, .git/, .claude/, .venv/, tmp/, dist/, build/
- Files matching **/diagrams/**/src/** (diagram source files are not surfaces)
- Files matching globs in .docmanifest_ignore at the project root
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1
GENERATOR_VERSION = "praxion-0.7.0"

# ---------------------------------------------------------------------------
# Filesystem walking
# ---------------------------------------------------------------------------

# Directories never walked
_EXCLUDED_DIRS = {
    "node_modules",
    ".git",
    ".claude",
    ".venv",
    "venv",
    "tmp",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
}

# Repo-root surfaces (curated, ordered)
_ROOT_SURFACES = [
    "README.md",
    "README_DEV.md",
    "CLAUDE.md",
    "AGENTS.md",
    "CHANGELOG.md",
]

# Recognized canonical filenames in .ai-state/
_AI_STATE_FILES = [
    "DESIGN.md",
    "SYSTEM_DEPLOYMENT.md",
    "TEST_TOPOLOGY.md",
    "TECH_DEBT_LEDGER.md",
    "TECH_DEBT_RESOLVED.md",
    "calibration_log.md",
    "DESIGN_CHANGELOG.md",
    "LANDSCAPE_WATCHLIST.md",
    "UPSTREAM_ISSUES.md",
]

# Pipeline artifacts in .ai-work/<slug>/ (when present)
_AI_WORK_FILES = [
    "IDEA_PROPOSAL.md",
    "RESEARCH_FINDINGS.md",
    "CONTEXT_REVIEW.md",
    "SYSTEMS_PLAN.md",
    "SPEC_DELTA.md",
    "SKILL_GENESIS_REPORT.md",
    "IMPLEMENTATION_PLAN.md",
    "WIP.md",
    "LEARNINGS.md",
    "TEST_RESULTS.md",
    "VERIFICATION_REPORT.md",
    "PROGRESS.md",
    "traceability.yml",
]

# Renderer mapping by Diátaxis quadrant + type
_DEFAULT_RENDERERS = {
    ("markdown", "tutorial"): "tutorial_shell",
    ("markdown", "how-to"): "how_to_shell",
    ("markdown", "reference"): "reference_shell",
    ("markdown", "explanation"): "explanation_shell",
    ("markdown", "concepts"): "explanation_shell",
}

# Filename-pattern → renderer for special-case surfaces
_RENDERER_BY_NAME: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^IMPLEMENTATION_PLAN\.md$"), "plan_view"),
    (re.compile(r"^VERIFICATION_REPORT\.md$"), "verification_report"),
    (re.compile(r"^IDEA_PROPOSAL\.md$"), "idea_grid"),
    (re.compile(r"^IDEA_LEDGER_.*\.md$"), "idea_grid"),
    (re.compile(r"^DESIGN\.md$"), "architecture_explorer"),
    (re.compile(r"^architecture\.md$"), "architecture_explorer"),
    (re.compile(r"^\d{3}-[a-z0-9-]+\.md$"), "adr_card"),
    (re.compile(r"^METRICS_REPORT_.*\.json$"), "metrics_view"),
    (re.compile(r"^traceability\.yml$"), "traceability_matrix"),
]

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.+?)\n---\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_LINK_RE = re.compile(r"\]\(([^)]+)\)")
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _read_text(path: Path) -> str:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return ""


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return ({}, text)
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = text[m.end() :]
    return (fm if isinstance(fm, dict) else {}, body)


def _first_h1(body: str) -> str | None:
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else None


def _first_paragraph(body: str) -> str | None:
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        # Skip headings and HTML comments (e.g. `<!-- aac:authored ... -->`)
        # — both render as empty/no-op markdown but the comment shape would
        # surface as a useless italic in any consuming renderer.
        if block and not block.startswith("#") and not block.startswith("<!--"):
            text = re.sub(r"\s+", " ", block)
            return text[:280] + ("..." if len(text) > 280 else "")
    return None


def _surface_id(rel_path: Path) -> str:
    """`docs/architecture.md` → `docs-architecture`; `.ai-state/DESIGN.md` →
    `ai-state-design`."""
    parts = list(rel_path.parts)
    parts[-1] = rel_path.stem  # strip extension
    parts = [p.lstrip(".") for p in parts]  # `.ai-state` → `ai-state`
    slug = "-".join(parts).lower()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _file_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".md": "markdown",
        ".markdown": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".svg": "svg",
        ".html": "html",
        ".ipynb": "jupyter",
    }.get(ext, "unknown")


def _pick_renderer(rel_path: Path, file_type: str, diataxis: str | None) -> str | None:
    """Default-renderer pick. Returns None when no good default exists."""
    name = rel_path.name
    for pat, renderer in _RENDERER_BY_NAME:
        if pat.match(name):
            return renderer
    if file_type == "markdown" and diataxis:
        return _DEFAULT_RENDERERS.get((file_type, diataxis), "default_markdown")
    if file_type == "markdown":
        return "default_markdown"
    if file_type in ("yaml", "json"):
        return "default_markdown"
    return None


# ---------------------------------------------------------------------------
# Surface-descriptor builders
# ---------------------------------------------------------------------------


def _build_surface(root: Path, rel_path: Path) -> dict[str, Any] | None:
    """Build a manifest entry for one file. Returns None if the file is
    skipped (e.g., empty, unreadable)."""
    abs_path = root / rel_path
    if not abs_path.is_file():
        return None

    file_type = _file_type(abs_path)
    text = _read_text(abs_path)

    frontmatter: dict[str, Any] = {}
    body = text
    if file_type == "markdown":
        frontmatter, body = _parse_frontmatter(text)

    diataxis = frontmatter.get("diataxis")
    audience = frontmatter.get("audience")
    title = frontmatter.get("title") or _first_h1(body) or rel_path.name
    summary = frontmatter.get("summary") or _first_paragraph(body)
    share_out = bool(frontmatter.get("share_out", False))
    renderer = _pick_renderer(rel_path, file_type, diataxis)

    # Outbound links to other surfaces (id-form, resolved later)
    referenced_paths = []
    if file_type == "markdown":
        for match in _LINK_RE.finditer(body):
            link = match.group(1).split("#", 1)[0].strip()
            if not link or link.startswith(("http://", "https://", "mailto:", "/")):
                continue
            # Resolve relative to the surface's directory
            try:
                resolved = (
                    (rel_path.parent / link).resolve().relative_to(root.resolve())
                )
            except (ValueError, OSError):
                continue
            referenced_paths.append(str(resolved))

    # Embedded diagrams (rendered SVGs/PNGs)
    diagrams: list[str] = []
    if file_type == "markdown":
        for match in _IMG_RE.finditer(body):
            link = match.group(1).split(" ", 1)[0].strip()
            if "/diagrams/" in link and "/rendered/" in link:
                try:
                    resolved = (
                        (rel_path.parent / link).resolve().relative_to(root.resolve())
                    )
                except (ValueError, OSError):
                    continue
                diagrams.append(str(resolved))

    descriptor: dict[str, Any] = {
        "id": _surface_id(rel_path),
        "path": str(rel_path),
        "type": file_type,
        "title": str(title),
        "last_modified": datetime.fromtimestamp(abs_path.stat().st_mtime)
        .date()
        .isoformat(),
    }
    if diataxis:
        descriptor["diataxis"] = str(diataxis)
    if audience:
        descriptor["audience"] = str(audience)
    if renderer:
        descriptor["renderer"] = renderer
    if summary:
        descriptor["summary"] = str(summary)
    if share_out:
        descriptor["share_out"] = True
    if referenced_paths:
        descriptor["referenced_paths"] = sorted(set(referenced_paths))
    if diagrams:
        descriptor["diagrams"] = sorted(set(diagrams))
    if frontmatter:
        descriptor["frontmatter"] = frontmatter

    return descriptor


def _walk_for_md(root: Path, subdir: str) -> list[Path]:
    """List all .md files under root/subdir, sorted, skipping excluded dirs
    and diagram src/ subdirectories."""
    base = root / subdir
    if not base.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(base.rglob("*.md")):
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if "/diagrams/" in str(path) and "/src/" in str(path):
            continue
        paths.append(path.relative_to(root))
    return paths


def _resolve_referenced_paths_to_ids(
    surfaces: list[dict[str, Any]],
) -> None:
    """Convert raw `referenced_paths` to manifest `surfaces_referenced` ids."""
    path_to_id = {s["path"]: s["id"] for s in surfaces}
    for s in surfaces:
        raw = s.pop("referenced_paths", [])
        ids = []
        for p in raw:
            if p in path_to_id and path_to_id[p] != s["id"]:
                ids.append(path_to_id[p])
        if ids:
            s["surfaces_referenced"] = sorted(set(ids))


def _build_groups(surfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group surfaces by Diátaxis quadrant for sidebar nav."""
    by_quadrant: dict[str, list[str]] = {
        "tutorial": [],
        "how-to": [],
        "reference": [],
        "explanation": [],
        "concepts": [],
    }
    transient: list[str] = []
    other: list[str] = []
    for s in surfaces:
        if s["path"].startswith(".ai-work/"):
            transient.append(s["id"])
        elif s.get("diataxis") in by_quadrant:
            by_quadrant[s["diataxis"]].append(s["id"])
        else:
            other.append(s["id"])

    groups = []
    labels = {
        "tutorial": "Tutorials (learning by doing)",
        "how-to": "How-to guides",
        "reference": "Reference",
        "explanation": "Explanation",
        "concepts": "Concepts",
    }
    for quadrant, ids in by_quadrant.items():
        if ids:
            groups.append(
                {"id": quadrant, "label": labels[quadrant], "surface_ids": sorted(ids)}
            )
    if other:
        groups.append({"id": "other", "label": "Other", "surface_ids": sorted(other)})
    if transient:
        groups.append(
            {
                "id": "pipeline-state",
                "label": "In-flight pipeline",
                "surface_ids": sorted(transient),
                "transient": True,
            }
        )
    return groups


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_manifest(root: Path) -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []

    # Repo-root surfaces
    for name in _ROOT_SURFACES:
        rel = Path(name)
        if (root / rel).is_file():
            d = _build_surface(root, rel)
            if d:
                surfaces.append(d)

    # docs/**
    for rel in _walk_for_md(root, "docs"):
        d = _build_surface(root, rel)
        if d:
            surfaces.append(d)

    # .ai-state/ canonical files
    for name in _AI_STATE_FILES:
        rel = Path(".ai-state") / name
        if (root / rel).is_file():
            d = _build_surface(root, rel)
            if d:
                surfaces.append(d)

    # .ai-state/decisions/<NNN>-*.md (finalized ADRs)
    decisions_dir = root / ".ai-state" / "decisions"
    if decisions_dir.is_dir():
        for path in sorted(decisions_dir.glob("[0-9][0-9][0-9]-*.md")):
            rel = path.relative_to(root)
            d = _build_surface(root, rel)
            if d:
                surfaces.append(d)
        index = decisions_dir / "DECISIONS_INDEX.md"
        if index.is_file():
            d = _build_surface(root, index.relative_to(root))
            if d:
                surfaces.append(d)

    # .ai-state/idea_ledgers, sentinel_reports, metrics_reports
    for subdir, pattern in [
        ("idea_ledgers", "IDEA_LEDGER_*.md"),
        ("sentinel_reports", "SENTINEL_REPORT_*.md"),
        ("metrics_reports", "METRICS_REPORT_*.json"),
        ("metrics_reports", "METRICS_REPORT_*.md"),
        ("specs", "SPEC_*.md"),
    ]:
        d = root / ".ai-state" / subdir
        if not d.is_dir():
            continue
        for path in sorted(d.glob(pattern)):
            rel = path.relative_to(root)
            entry = _build_surface(root, rel)
            if entry:
                surfaces.append(entry)

    # .ai-work/<active-slug>/ — for each subdirectory, emit the canonical
    # pipeline artifacts that exist
    ai_work = root / ".ai-work"
    if ai_work.is_dir():
        for slug_dir in sorted(p for p in ai_work.iterdir() if p.is_dir()):
            for name in _AI_WORK_FILES:
                file = slug_dir / name
                if file.is_file():
                    rel = file.relative_to(root)
                    entry = _build_surface(root, rel)
                    if entry:
                        surfaces.append(entry)

    # Resolve internal cross-references
    _resolve_referenced_paths_to_ids(surfaces)

    # Build manifest envelope
    project_name = root.name
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "project_name": project_name,
        "project_slug": re.sub(r"[^a-z0-9-]", "-", project_name.lower()).strip("-"),
        "surfaces": surfaces,
        "groups": _build_groups(surfaces),
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the doc manifest.")
    parser.add_argument("--root", default=".", help="Project root (default: cwd)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write; exit non-zero if manifest is out of sync",
    )
    parser.add_argument(
        "--output",
        default=".ai-state/doc_manifest.yaml",
        help="Output path relative to root (default: .ai-state/doc_manifest.yaml)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    output = root / args.output

    new_manifest = build_manifest(root)

    # Stable YAML output: sort keys at top level for determinism
    new_yaml = yaml.safe_dump(
        new_manifest,
        default_flow_style=False,
        sort_keys=False,
        width=200,
    )

    if args.check:
        if not output.is_file():
            print(f"FAIL: {output} does not exist", file=sys.stderr)
            return 1
        # Compare excluding the `generated_at` timestamp (which always drifts)
        old_text = output.read_text()
        old_no_ts = re.sub(
            r"^generated_at:.*$", "generated_at:", old_text, flags=re.MULTILINE
        )
        new_no_ts = re.sub(
            r"^generated_at:.*$", "generated_at:", new_yaml, flags=re.MULTILINE
        )
        if old_no_ts != new_no_ts:
            print(
                f"FAIL: {output} is out of sync (run scripts/build_doc_manifest.py)",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {output} is fresh")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(new_yaml)
    print(
        f"Wrote {output} — {len(new_manifest['surfaces'])} surfaces, {len(new_manifest['groups'])} groups"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
