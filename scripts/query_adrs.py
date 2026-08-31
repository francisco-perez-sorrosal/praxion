#!/usr/bin/env python3
"""Read-only, token-free ADR retrieval by path/tag/grep intersection.

`.ai-state/decisions/` grows without bound and a full-index read burns tokens
on every ADR-aware agent turn. The Discovery Protocol (rules/swe/adr-conventions.md)
asks agents to grep-pre-scan instead of reading `DECISIONS_INDEX.md` whole; this
script is the precise query surface that makes that scan exact rather than a
best-effort grep over prose.

`affected_files` frontmatter is 99% populated across the finalized corpus (a
measured probe: median 4 paths, no globs, 94% of paths resolve on disk), which
is what makes path-intersection retrieval viable as a primary selector.

Usage:
    python3 scripts/query_adrs.py --paths skills/foo/SKILL.md
    python3 scripts/query_adrs.py --staged
    python3 scripts/query_adrs.py --tags observability testing
    python3 scripts/query_adrs.py --grep "memory subsystem" --all
    python3 scripts/query_adrs.py --paths skills/foo/ --tags api --format tsv

Exit codes: 0 (>=1 match), 1 (zero matches), 2 (usage error -- no selector, or
an invalid --grep pattern).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from _repo_root import resolve_repo_root as _resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

# Streamlined default view: the two statuses an agent should reach for when it
# just wants "what decision governs this" without wading through history.
DEFAULT_STATUSES = frozenset({"accepted", "re-affirmation"})

_FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---", re.DOTALL)
_FALLBACK_KEY_RE = re.compile(r"^(\w[\w-]*)\s*:\s*(.*)$")
_FALLBACK_BLOCK_ITEM_RE = re.compile(r"^\s+-\s*(.+)$")

EXAMPLES = """\
EXAMPLES
  # What decisions govern this file or directory?
  query_adrs.py --paths skills/foo/SKILL.md

  # What decisions govern what I'm about to commit?
  query_adrs.py --staged

  # Everything tagged "observability" or "testing"
  query_adrs.py --tags observability testing

  # Search title/summary text, including superseded/retired decisions
  query_adrs.py --grep "memory subsystem" --all

  # Combined AND filter, machine-readable output
  query_adrs.py --paths skills/foo/ --tags api --format tsv
"""


@dataclass(frozen=True)
class AdrRecord:
    """One ADR's frontmatter, normalized regardless of which parser read it."""

    id: str
    status: str
    title: str
    date: str
    tags: tuple[str, ...]
    summary: str
    category: str
    affected_files: tuple[str, ...]
    file: str  # repo-relative, posix separators


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver (never `__file__`-relative)."""
    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR)


# -- Frontmatter parsing -------------------------------------------------------


def _try_import_yaml():
    """Return the `yaml` module if PyYAML is importable, else None.

    Managed projects' ambient Python may lack PyYAML -- this script ships with
    the plugin and must degrade to the stdlib fallback parser rather than fail
    to run at all.
    """
    try:
        import yaml
    except ImportError:
        return None
    return yaml


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_inline_list(value: str) -> list[str]:
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_strip_quotes(item) for item in inner.split(",")]


def _parse_frontmatter_fallback(raw: str, path: Path) -> dict[str, object] | None:
    """Minimal stdlib line-parser for exactly the fields this script needs.

    Handles scalar values, inline lists (`[a, b]`), and block lists (`- item`).
    Kept honest per the fallback contract: any line it cannot classify --
    inside or outside a block, an unterminated inline list -- causes it to
    warn and skip the file rather than guess at a shape it does not recognize.
    """
    fields: dict[str, object] = {}
    block_key: str | None = None
    block_items: list[str] = []

    def flush_block() -> None:
        nonlocal block_key, block_items
        if block_key is not None:
            fields[block_key] = block_items
        block_key = None
        block_items = []

    for line in raw.splitlines():
        if not line.strip():
            continue

        block_item = _FALLBACK_BLOCK_ITEM_RE.match(line)
        if block_item and block_key is not None:
            block_items.append(_strip_quotes(block_item.group(1)))
            continue

        key_match = _FALLBACK_KEY_RE.match(line)
        if not key_match:
            print(
                f"warning: could not parse frontmatter line in {path}: {line!r}",
                file=sys.stderr,
            )
            return None

        flush_block()
        key, value = key_match.group(1), key_match.group(2).strip()
        if value == "":
            block_key, block_items = key, []
            continue
        if value.startswith("[") and value.endswith("]"):
            fields[key] = _parse_inline_list(value)
        elif value.startswith("["):
            print(
                f"warning: unterminated inline list for '{key}' in {path}",
                file=sys.stderr,
            )
            return None
        else:
            fields[key] = _strip_quotes(value)

    flush_block()
    return fields


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def load_adr(path: Path, repo_root: Path, yaml_module) -> AdrRecord | None:
    """Parse one ADR file into a normalized `AdrRecord`, or None if unreadable."""
    text = path.read_text(encoding="utf-8")
    frontmatter_match = _FRONTMATTER_RE.match(text)
    if not frontmatter_match:
        return None
    raw = frontmatter_match.group(1)

    if yaml_module is not None:
        try:
            data = yaml_module.safe_load(raw)
        except yaml_module.YAMLError:
            data = None
    else:
        data = _parse_frontmatter_fallback(raw, path)

    if not isinstance(data, dict):
        print(f"warning: could not parse frontmatter in {path}", file=sys.stderr)
        return None

    adr_id = str(data.get("id", "")).strip()
    status = str(data.get("status", "")).strip()
    title = str(data.get("title", "")).strip()
    if not adr_id or not status or not title:
        print(f"warning: missing required frontmatter fields in {path}", file=sys.stderr)
        return None

    return AdrRecord(
        id=adr_id,
        status=status,
        title=title,
        date=str(data.get("date", "")).strip(),
        tags=tuple(_as_list(data.get("tags"))),
        summary=str(data.get("summary", "")).strip(),
        category=str(data.get("category", "")).strip(),
        affected_files=tuple(_as_list(data.get("affected_files"))),
        file=path.relative_to(repo_root).as_posix(),
    )


def discover_adr_files(repo_root: Path) -> list[Path]:
    """Every finalized and in-flight-draft ADR file, finalized first."""
    decisions_dir = repo_root / ".ai-state" / "decisions"
    finalized = sorted(decisions_dir.glob("[0-9]*.md"))
    drafts = sorted((decisions_dir / "drafts").glob("*.md"))
    return finalized + drafts


# -- Matching -------------------------------------------------------------


def _normalize_path(value: str) -> str:
    return value.strip().rstrip("/")


def paths_match(query: str, entry: str) -> bool:
    """True on exact match or directory-prefix containment in either direction.

    `skills/foo/` matches an entry `skills/foo/SKILL.md`, and the reverse
    query `skills/foo/SKILL.md` matches an entry `skills/foo/` -- both read as
    "this ADR concerns something under/at this path". The `+"/"` boundary
    check is what stops `skills/foo` from falsely matching `skills/foobar`.
    """
    q, e = _normalize_path(query), _normalize_path(entry)
    if q == e:
        return True
    return e.startswith(q + "/") or q.startswith(e + "/")


def matched_paths(query_paths: list[str], record: AdrRecord) -> list[str]:
    return [q for q in query_paths if any(paths_match(q, e) for e in record.affected_files)]


def matched_tags(query_tags: list[str], record: AdrRecord) -> list[str]:
    lowered_record_tags = {t.lower() for t in record.tags}
    return [t for t in query_tags if t.lower() in lowered_record_tags]


def staged_paths(repo_root: Path) -> list[str]:
    """Union of `git diff --cached --name-only` and `git diff --name-only`."""
    paths: set[str] = set()
    for diff_args in (["--cached", "--name-only"], ["--name-only"]):
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", *diff_args],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            paths.update(p for p in result.stdout.splitlines() if p.strip())
    return sorted(paths)


# -- CLI --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="query_adrs.py",
        description="Read-only, token-free ADR retrieval by path/tag/grep intersection.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        metavar="PATH",
        help="Repo-relative paths; matches ADRs whose affected_files intersect "
        "(exact match, or directory-prefix containment in either direction).",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Derive query paths from `git diff --cached` + `git diff` (union) -- "
        "what decisions govern what you're touching right now.",
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        metavar="TAG",
        help="Case-insensitive membership over the tags frontmatter list.",
    )
    parser.add_argument(
        "--grep",
        metavar="REGEX",
        help="Case-insensitive regex search over title + summary frontmatter.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include every status (superseded, retired, ...), not just "
        "accepted and re-affirmation.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "tsv"),
        default="text",
        help="Output format. tsv emits id/status/title/file, no decoration.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root override (default: `git rev-parse --show-toplevel`).",
    )
    return parser


def _print_text(matches: list[tuple[AdrRecord, str]]) -> None:
    for record, matched in matches:
        print(f"{record.id} | {record.status} | {record.title}")
        print(f"  matched: {matched}")
        print(f"  file: {record.file}")
    count = len(matches)
    print(f"\n{count} match{'es' if count != 1 else ''}.")


def _print_tsv(matches: list[tuple[AdrRecord, str]]) -> None:
    for record, _matched in matches:
        print(f"{record.id}\t{record.status}\t{record.title}\t{record.file}")


def _select(
    records: list[AdrRecord],
    *,
    query_paths: list[str],
    query_tags: list[str] | None,
    grep_re: re.Pattern[str] | None,
    include_all_statuses: bool,
) -> list[tuple[AdrRecord, str]]:
    """Apply the default status view, then AND every active selector."""
    matches: list[tuple[AdrRecord, str]] = []
    for record in records:
        if not include_all_statuses and record.status.lower() not in DEFAULT_STATUSES:
            continue

        matched_parts: list[str] = []

        if query_paths:
            hits = matched_paths(query_paths, record)
            if not hits:
                continue
            matched_parts.append("paths=" + ",".join(hits))

        if query_tags:
            hits = matched_tags(query_tags, record)
            if not hits:
                continue
            matched_parts.append("tags=" + ",".join(hits))

        if grep_re is not None:
            if not grep_re.search(f"{record.title} {record.summary}"):
                continue
            matched_parts.append("grep")

        matches.append((record, "; ".join(matched_parts)))

    matches.sort(key=lambda pair: (pair[0].date, pair[0].id), reverse=True)
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root)

    query_paths = list(dict.fromkeys(args.paths or []))
    if args.staged:
        for path in staged_paths(repo_root):
            if path not in query_paths:
                query_paths.append(path)

    if not (query_paths or args.tags or args.grep):
        parser.print_help()
        return 2

    grep_re = None
    if args.grep:
        try:
            grep_re = re.compile(args.grep, re.IGNORECASE)
        except re.error as exc:
            print(f"error: invalid --grep pattern: {exc}", file=sys.stderr)
            return 2

    yaml_module = _try_import_yaml()
    records = [
        record
        for path in discover_adr_files(repo_root)
        if (record := load_adr(path, repo_root, yaml_module)) is not None
    ]

    matches = _select(
        records,
        query_paths=query_paths,
        query_tags=args.tags,
        grep_re=grep_re,
        include_all_statuses=args.all,
    )

    if args.format == "tsv":
        _print_tsv(matches)
    else:
        _print_text(matches)

    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
