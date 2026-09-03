#!/usr/bin/env python3
"""Build .ai-state/doc_manifest.yaml from the project's documentation surfaces.

Walks the project filesystem according to the schema specified in
``skills/doc-management/references/doc-manifest-schema.md`` and emits a YAML
manifest the per-project dashboard reads at session start.

The generator is deterministic: given the same filesystem state, it always
emits identical YAML (modulo `generated_at`). That determinism is what makes a
regenerate-in-place safe without merge drivers. Regeneration is automatic via
the finalize chain (``finalize_chain.sh``) after each merge to ``main`` — the
chain calls this script when ``.ai-state/doc_manifest.yaml`` already exists,
after ``finalize_adrs.py`` and ``finalize_tech_debt_ledger.py`` complete.
Sentinel F11 flags a stale manifest (advisory) as a belt-and-suspenders
backstop for hook-bypass or hook-failure cases.

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
from functools import cache
from pathlib import Path
from typing import Any

from _git_runner import GitUnavailableError, git_output, run_git

try:
    import yaml
except ImportError:
    # This runs inside the finalize hook chain, where a raw traceback reads as
    # a crash and gets ignored as noise -- which is how a stale committed
    # manifest survived undetected. Name the interpreter actually in use, since
    # the usual cause is the chain resolving one that lacks the project's
    # declared dependencies rather than PyYAML being genuinely uninstalled.
    sys.exit(
        f"build_doc_manifest: PyYAML is not importable under {sys.executable}.\n"
        "  The finalize chain resolves, in order: $PRAXION_PYTHON, "
        "<repo>/.venv/bin/python, then the ambient python3.\n"
        "  Fix by creating the project venv, installing pyyaml into the "
        "interpreter above, or pointing PRAXION_PYTHON at one that has it.\n"
        "  Until then .ai-state/doc_manifest.yaml will drift (sentinel F11 warns on this)."
    )

SCHEMA_VERSION = 2  # v2: dropped on-demandable `summary` + redundant `frontmatter` embeds
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
    (re.compile(r"^IDEA_LEDGER.*\.md$"), "idea_grid"),  # living IDEA_LEDGER.md + legacy timestamped
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
        ".graphql": "graphql",
        ".graphqls": "graphql",
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


@cache
def _git_commit_dates(root: str) -> dict[str, str]:
    """Map every tracked path to the date of the commit that last touched it.

    Filesystem mtime cannot be used for `last_modified`: a fresh clone or CI
    checkout sets mtime to checkout time for every file, so the same tree
    yields a different manifest depending on where it is generated. That
    breaks the determinism this module documents and turns the regenerate-in-
    place step into a ping-pong -- CI stamps checkout day, a local run stamps
    real write times, and each commits over the other forever.

    Git commit dates are identical in every checkout, which is what makes the
    no-op-regen guard actually hold. One subprocess for the whole history
    rather than one per file.
    """
    # Through the shared runner, which scrubs the repository-scoping variables
    # git exports to its hooks: this runs inside the finalize chain, where an
    # inherited relative `GIT_DIR` would silently re-target `root`.
    shallow = git_output(root, "rev-parse", "--is-shallow-repository")
    if shallow == "true":
        # A shallow clone exposes one commit, so git log can date almost nothing
        # and nearly every surface falls back to mtime -- which in a fresh
        # checkout is checkout day. That reintroduces the churn this function
        # exists to remove, and it does so silently. Say so.
        print(
            "WARNING: build_doc_manifest: shallow repository -- last_modified will "
            "fall back to filesystem mtime for most surfaces and the manifest will "
            "not be reproducible across checkouts. Fetch full history "
            "(actions/checkout fetch-depth: 0) before regenerating.",
            file=sys.stderr,
        )

    try:
        result = run_git(root, "log", "--name-only", "--format=%x00%cs", "--no-merges", timeout=120)
    except GitUnavailableError:
        return {}
    if result.returncode != 0:
        return {}
    out = result.stdout

    dates: dict[str, str] = {}
    current = ""
    for line in out.splitlines():
        if line.startswith("\x00"):
            current = line[1:].strip()
        elif line.strip() and current and line not in dates:
            # git log walks newest-first, so the first sighting wins
            dates[line] = current
    return dates


def _last_modified(root: Path, abs_path: Path) -> str:
    """`last_modified` for a surface -- git commit date, mtime only as fallback.

    The fallback covers untracked files (a surface authored but not yet
    committed), where mtime is the only signal available.
    """
    try:
        rel = abs_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = ""
    committed = _git_commit_dates(str(root)).get(rel)
    if committed:
        return committed
    return datetime.fromtimestamp(abs_path.stat().st_mtime).date().isoformat()


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
                resolved = (rel_path.parent / link).resolve().relative_to(root.resolve())
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
                    resolved = (rel_path.parent / link).resolve().relative_to(root.resolve())
                except (ValueError, OSError):
                    continue
                diagrams.append(str(resolved))

    descriptor: dict[str, Any] = {
        "id": _surface_id(rel_path),
        "path": str(rel_path),
        "type": file_type,
        "title": str(title),
        "last_modified": _last_modified(root, abs_path),
    }
    if diataxis:
        descriptor["diataxis"] = str(diataxis)
    if audience:
        descriptor["audience"] = str(audience)
    if renderer:
        descriptor["renderer"] = renderer
    if share_out:
        descriptor["share_out"] = True
    if referenced_paths:
        descriptor["referenced_paths"] = sorted(set(referenced_paths))
    if diagrams:
        descriptor["diagrams"] = sorted(set(diagrams))

    return descriptor


def _walk_for_md(root: Path, subdir: str) -> list[Path]:
    """List all .md files under root/subdir, sorted, skipping excluded dirs
    and diagram src/ subdirectories."""
    base = root / subdir
    if not base.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(base.rglob("*.md")):
        # Check parts RELATIVE to root (mirroring _walk_for_api_specs): an
        # absolute-path check would spuriously exclude every surface when root
        # itself lives under an excluded dir — e.g. a worktree under .claude/.
        if any(part in _EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        if "/diagrams/" in str(path) and "/src/" in str(path):
            continue
        paths.append(path.relative_to(root))
    return paths


# Bounded locations searched for API-spec surfaces (relative to root).
_API_SPEC_DIRS = ["", "docs", "openapi", "api", "spec", "specs"]

# Exact filenames (OpenAPI / AsyncAPI) recognized as spec surfaces.
_API_SPEC_FILENAMES = {
    "openapi.yaml",
    "openapi.yml",
    "openapi.json",
    "asyncapi.yaml",
    "asyncapi.yml",
    "asyncapi.json",
}

# Extensions (GraphQL SDL) recognized as spec surfaces.
_API_SPEC_SUFFIXES = {".graphql", ".graphqls"}


def _walk_for_api_specs(root: Path) -> list[Path]:
    """List API-spec surfaces in a bounded set of locations.

    Searches the project root and `docs/` / `openapi/` / `api/` / `spec/` /
    `specs/` (when present) for `openapi.{yaml,json}`, `asyncapi.{yaml,json}`,
    and `*.graphql[s]` SDL files. The search is shallow per directory (no
    recursion) to keep the surface bounded and predictable. Excluded dirs are
    skipped. Returns root-relative paths, de-duplicated and sorted.
    """
    found: set[Path] = set()
    for subdir in _API_SPEC_DIRS:
        base = root / subdir if subdir else root
        if not base.is_dir():
            continue
        if any(part in _EXCLUDED_DIRS for part in base.relative_to(root).parts):
            continue
        for path in base.iterdir():
            if not path.is_file():
                continue
            name = path.name.lower()
            if name in _API_SPEC_FILENAMES or path.suffix.lower() in _API_SPEC_SUFFIXES:
                found.add(path.relative_to(root))
    return sorted(found)


def _spec_title(abs_path: Path, file_type: str, rel_path: Path) -> str:
    """Derive a spec title from `info.title` (+ `info.version`) for OpenAPI /
    AsyncAPI specs; fall back to the filename for GraphQL SDL or unparseable
    specs."""
    fallback = rel_path.name
    if file_type == "graphql":
        return fallback
    text = _read_text(abs_path)
    if not text.strip():
        return fallback
    try:
        # YAML safe_load parses JSON too, so a single path covers both.
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return fallback
    if not isinstance(data, dict):
        return fallback
    info = data.get("info")
    if not isinstance(info, dict):
        return fallback
    title = info.get("title")
    if not title:
        return fallback
    version = info.get("version")
    return f"{title} {version}" if version else str(title)


def _build_api_spec_surface(root: Path, rel_path: Path) -> dict[str, Any] | None:
    """Build a manifest entry for one API-spec surface. Spec surfaces always
    get `diataxis: reference` and `renderer: api_reference`."""
    abs_path = root / rel_path
    if not abs_path.is_file():
        return None
    file_type = _file_type(abs_path)
    return {
        "id": _surface_id(rel_path),
        "path": str(rel_path),
        "type": file_type,
        "title": _spec_title(abs_path, file_type, rel_path),
        "diataxis": "reference",
        "renderer": "api_reference",
        "last_modified": _last_modified(root, abs_path),
    }


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
    api_reference: list[str] = []
    other: list[str] = []
    for s in surfaces:
        if s.get("renderer") == "api_reference":
            api_reference.append(s["id"])
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
            groups.append({"id": quadrant, "label": labels[quadrant], "surface_ids": sorted(ids)})
    if api_reference:
        groups.append(
            {
                "id": "api-reference",
                "label": "API Reference",
                "surface_ids": sorted(api_reference),
            }
        )
    if other:
        groups.append({"id": "other", "label": "Other", "surface_ids": sorted(other)})
    return groups


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


def _strip_generated_at(text: str) -> str:
    """Erase the `generated_at` timestamp value so two manifests can be compared
    for content equality independent of when they were generated."""
    return re.sub(r"^generated_at:.*$", "generated_at:", text, flags=re.MULTILINE)


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
        ("idea_ledgers", "IDEA_LEDGER*.md"),
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

    # API-spec surfaces (OpenAPI / AsyncAPI / GraphQL SDL) in bounded locations
    existing_paths = {s["path"] for s in surfaces}
    for rel in _walk_for_api_specs(root):
        if str(rel) in existing_paths:
            continue
        entry = _build_api_spec_surface(root, rel)
        if entry:
            surfaces.append(entry)
            existing_paths.add(entry["path"])

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
        if _strip_generated_at(old_text) != _strip_generated_at(new_yaml):
            print(
                f"FAIL: {output} is out of sync (run scripts/build_doc_manifest.py)",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {output} is fresh")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    # Content-aware write: skip when the new manifest equals the existing one
    # modulo `generated_at`, so a no-op regen produces no diff and no churn.
    if output.is_file() and _strip_generated_at(output.read_text()) == _strip_generated_at(
        new_yaml
    ):
        print(f"{output} unchanged — skipping write")
        return 0
    output.write_text(new_yaml)
    print(
        f"Wrote {output} — {len(new_manifest['surfaces'])} surfaces, {len(new_manifest['groups'])} groups"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
