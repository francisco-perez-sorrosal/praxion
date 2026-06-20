#!/usr/bin/env python3
"""Regenerate SPECS_INDEX.md from SPEC_*.md files in .ai-state/specs/.

Reads all SPEC_*.md files, extracts bold-key metadata fields, and writes a
markdown index table sorted by Archived date (descending), tie-broken by slug.
SPEC files do NOT have YAML frontmatter — fields are encoded as bold-key lines:

    **Task slug**: `<slug>`
    **Archived**: YYYY-MM-DD
    **Status**: Shipped
    **Tier**: Full
    **ADRs**: `dec-NNN` (desc), ...

Any missing field produces a blank cell; no file is skipped for missing fields.

Usage: python scripts/regenerate_specs_index.py [--repo-root <path>]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Compiled pattern for Status short-form truncation.
# Truncates at the first occurrence of " — " (em-dash with spaces), " (",
# ";", or "," — whichever comes first — so only the leading token is kept.
_STATUS_TRUNCATION_RE = re.compile(r"( — | \(|;|,).*$")

from _repo_root import is_plugin_cache_path
from _repo_root import resolve_repo_root as _resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent
SPECS_DIR = SCRIPT_DIR.parent / ".ai-state" / "specs"
INDEX_PATH = SPECS_DIR / "SPECS_INDEX.md"

# Maximum characters for the Summary column (excluding ellipsis).
MAX_SUMMARY_LEN = 120

# Matches filenames like SPEC_some-slug_YYYY-MM-DD.md
SPEC_FILENAME_PATTERN = re.compile(r"^SPEC_.+_\d{4}-\d{2}-\d{2}\.md$")

# Matches a bold-key line: **Key**: value
_BOLD_KEY_RE = re.compile(r"^\*\*([^*]+)\*\*\s*:\s*(.*)$")

# Fallback for plain "Archived: YYYY-MM-DD" lines (no bold markup).
_PLAIN_ARCHIVED_RE = re.compile(r"^Archived:\s*(\d{4}-\d{2}-\d{2})")

# Extracts dec-NNN identifiers from an ADRs line value.
_DEC_ID_RE = re.compile(r"\bdec-\d+\b")

INDEX_HEADER = """\
# Specs Index

Auto-generated from SPEC_*.md bold-key fields. Do not edit manually.
Regenerate: `python scripts/regenerate_specs_index.py`

| Spec | Slug | Archived | Status | Tier | ADRs | Summary |
|------|------|----------|--------|------|------|---------|"""


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver."""
    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR)


def apply_repo_root(root: Path) -> None:
    """Rebind the module-level path constants to a resolved repo root."""
    global SPECS_DIR, INDEX_PATH
    SPECS_DIR = root / ".ai-state" / "specs"
    INDEX_PATH = SPECS_DIR / "SPECS_INDEX.md"


def _extract_bold_keys(content: str) -> dict[str, str]:
    """Parse bold-key lines from SPEC file content.

    Each line of the form ``**Key**: value`` is captured as key → value.
    Also handles a plain ``Archived: YYYY-MM-DD`` line (no bold markup) used
    by older spec files.
    Only lines before the first ``##`` section heading are scanned, so that
    body paragraphs containing bold text do not pollute the metadata.
    """
    fields: dict[str, str] = {}
    for line in content.splitlines():
        if line.startswith("##"):
            break
        stripped = line.strip()
        match = _BOLD_KEY_RE.match(stripped)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            # Strip surrounding backticks from quoted values like `slug`.
            if value.startswith("`") and value.endswith("`"):
                value = value[1:-1]
            fields[key] = value
            continue
        # Fallback: plain "Archived: YYYY-MM-DD" (not bold).
        plain = _PLAIN_ARCHIVED_RE.match(stripped)
        if plain and "Archived" not in fields:
            fields["Archived"] = plain.group(1)
    return fields


def _extract_summary(content: str) -> str:
    """Return the first non-blank line of the ## Feature Summary section."""
    in_summary = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Feature Summary"):
            in_summary = True
            continue
        if in_summary:
            if stripped.startswith("##"):
                break
            if stripped:
                return stripped
    return ""


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, appending '...' if truncated."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _format_adrs(raw_value: str) -> str:
    """Extract dec-NNN ids from the ADRs field value."""
    ids = _DEC_ID_RE.findall(raw_value)
    return ", ".join(ids)


def _slug_from_filename(path: Path) -> str:
    """Derive a slug fallback from the filename (SPEC_<slug>_YYYY-MM-DD.md)."""
    # Strip SPEC_ prefix and _YYYY-MM-DD.md suffix.
    name = path.stem  # e.g. SPEC_some-slug_2026-04-23
    parts = name.split("_")
    # parts[0] == 'SPEC', parts[-1] == date, everything in between is the slug.
    if len(parts) >= 3:
        return "_".join(parts[1:-1])
    if len(parts) == 2:
        return parts[1]
    return name


def _normalize_status(raw: str) -> str:
    """Return the short form of a Status field value.

    Truncates at the first occurrence of ' — ' (em-dash with spaces), ' (',
    ';', or ',' — whichever comes first — so verbose status lines like
    "Shipped — verifier PASS-WITH-WARNINGS (step-21); ..." reduce to
    "Shipped". Whitespace is stripped from the result.
    """
    return _STATUS_TRUNCATION_RE.sub("", raw).strip()


def parse_spec_file(path: Path) -> dict[str, str]:
    """Parse a single SPEC_*.md file and return a metadata dict.

    All fields default to empty string when absent. Never raises for missing
    fields — the caller receives blank cells.
    """
    content = path.read_text(encoding="utf-8")
    fields = _extract_bold_keys(content)

    # Normalise key names tolerantly (the field names vary slightly across specs).
    slug = (
        fields.get("Task slug")
        or fields.get("task slug")
        or fields.get("Slug")
        or _slug_from_filename(path)
    )
    archived = fields.get("Archived") or fields.get("End date") or ""
    status = _normalize_status(fields.get("Status", ""))
    tier_raw = fields.get("Tier", "")
    # Trim parenthetical detail from Tier, e.g. "Full (escalated from Standard)"
    tier = tier_raw.split("(")[0].strip() if "(" in tier_raw else tier_raw
    adrs_raw = fields.get("ADRs", "")
    adrs = _format_adrs(adrs_raw)

    summary_raw = _extract_summary(content)
    summary = _truncate(summary_raw, MAX_SUMMARY_LEN)

    return {
        "_filename": path.name,
        "_path": path,
        "slug": slug,
        "archived": archived,
        "status": status,
        "tier": tier,
        "adrs": adrs,
        "summary": summary,
    }


def collect_specs() -> list[dict[str, str]]:
    """Collect and parse all SPEC_*.md files, sorted by archived date desc."""
    if not SPECS_DIR.is_dir():
        return []

    specs: list[dict[str, str]] = []
    for path in sorted(SPECS_DIR.iterdir()):
        if not SPEC_FILENAME_PATTERN.match(path.name):
            continue
        specs.append(parse_spec_file(path))

    # Primary: Archived date descending (blank → "0000-00-00" → sorts last).
    # Secondary: slug ascending for same-date ties.
    specs.sort(key=lambda s: (s["archived"] or "0000-00-00", s["slug"]))
    specs.sort(key=lambda s: s["archived"] or "0000-00-00", reverse=True)

    return specs


def generate_index(specs: list[dict[str, str]]) -> str:
    """Generate the full SPECS_INDEX.md markdown content."""
    lines = [INDEX_HEADER]

    for spec in specs:
        filename = spec["_filename"]
        spec_link = f"[{filename}]({filename})"
        slug = spec["slug"]
        archived = spec["archived"]
        status = spec["status"]
        tier = spec["tier"]
        adrs = spec["adrs"]
        summary = spec["summary"]

        lines.append(
            f"| {spec_link} | {slug} | {archived} | {status} | {tier} | {adrs} | {summary} |"
        )

    lines.append("")  # trailing newline
    return "\n".join(lines)


def _parse_repo_root_arg() -> str | None:
    """Extract `--repo-root <path>` from argv, if present."""
    if "--repo-root" in sys.argv:
        idx = sys.argv.index("--repo-root")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return None


def main() -> None:
    """Entry point: collect specs, generate index, write to file."""
    root = resolve_repo_root(_parse_repo_root_arg())
    if is_plugin_cache_path(root):
        print(
            f"refusing to regenerate index against a plugin-cache path: {root}",
            file=sys.stderr,
        )
        sys.exit(1)
    apply_repo_root(root)
    specs = collect_specs()
    index_content = generate_index(specs)
    INDEX_PATH.write_text(index_content, encoding="utf-8")

    print(f"Generated {INDEX_PATH} with {len(specs)} entries.")


if __name__ == "__main__":
    main()
