#!/usr/bin/env python3
"""Cross-Reference Validator -- validates intra-repo Markdown links.

Six link classes:
  1. Intra-skill relative -- FAIL if broken
  2. Sibling-skill relative -- FAIL if broken
  3. Cross-artifact (rules/**, agents/**, commands/**, docs/**) -- FAIL if broken
  4. Anchor same-file (#slug) -- FAIL if slug not found
  5. Anchor cross-file (path#slug) -- FAIL file missing; WARN slug missing
  6. Code-file allowlisted (.py/.yaml/.ts/...) -- FAIL if missing

External URLs skipped. Bare-backtick code paths ignored. Ignore mechanisms:
  - Inline  ``<!-- validate-references:ignore -->``  suppresses the link on that line
  - Frontmatter  ``validate-references: off``  suppresses all findings in the file

Exit codes: 0 = clean (or only WARN in --warn-only); 1 = >=1 FAIL; 2 = script error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

# fmt: off
CODE_EXTENSIONS = frozenset({".py", ".yaml", ".yml", ".ts", ".tsx", ".js", ".jsx", ".toml", ".json", ".sh"})
ALLOWLIST_PREFIXES = ("memory-mcp/", "task-chronograph-mcp/", "hooks/", "scripts/", "skills/", "agents/", "rules/", "commands/", ".ai-state/", "docs/")
IGNORED_PATH_SEGMENTS = (".ai-work/", "node_modules/", ".venv/", "target/", "dist/", "build/")
EXCLUDED_GLOB_PREFIXES = (".ai-work/", "node_modules/", ".venv/", "target/", "dist/", "build/", "memory-mcp/", "task-chronograph-mcp/")
URL_SCHEMES = ("http://", "https://", "mailto:", "ftp://", "ftps://", "tel:")
INCLUDE_PATTERNS = ("skills/*/SKILL.md", "skills/*/README.md", "skills/*/references/*.md", "skills/*/contexts/*.md", "skills/*/phases/*.md", "skills/*/assets/*.md", "rules/**/*.md", "agents/*.md", "commands/**/*.md", "docs/**/*.md", ".ai-state/decisions/*.md", "CLAUDE.md", "README.md", "ROADMAP.md", "README_DEV.md", "CHANGELOG.md")
# fmt: on

INLINE_IGNORE_MARKER = "<!-- validate-references:ignore -->"

INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
REF_DEF_RE = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(\S+)")
HEADING_RE = re.compile(r"^(#+)\s+(.+?)\s*$")
CODE_FENCE_RE = re.compile(r"^(```|~~~)")
EXPLICIT_ANCHOR_RE = re.compile(r"\s*\{#([^}]+)\}\s*$")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
LINK_TITLE_RE = re.compile(r'^(\S+)(?:\s+".*")?$')
FRONTMATTER_RE = re.compile(r"^([a-zA-Z][\w-]*)\s*:\s*(.*?)\s*$")
SLUG_STRIP_RE = re.compile(r"[^\w\- ]+", re.UNICODE)
SLUG_SPACE_RE = re.compile(r"\s+")

FAIL = "FAIL"
WARN = "WARN"


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    severity: str
    link_class: str
    target: str
    reason: str


@dataclass(frozen=True)
class RawLink:
    line: int
    text: str
    target: str
    ignored: bool


def github_slug(heading: str) -> str:
    """GitHub-compatible anchor slug: lowercase, strip punct except -/_, spaces->-."""
    s = SLUG_STRIP_RE.sub("", heading.strip().lower())
    return SLUG_SPACE_RE.sub("-", s).strip("-_")


def build_slug_map(headings: list[str]) -> tuple[set[str], set[str]]:
    """Return (valid_slugs, ambiguous_base_slugs). Duplicates get -1, -2 suffixes."""
    counts: dict[str, int] = defaultdict(int)
    valid: set[str] = set()
    ambiguous: set[str] = set()
    for heading in headings:
        base = github_slug(heading)
        if not base:
            continue
        if counts[base] == 0:
            valid.add(base)
        else:
            ambiguous.add(base)
            valid.add(f"{base}-{counts[base]}")
        counts[base] += 1
    return valid, ambiguous


def strip_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    """Strip YAML frontmatter; return (body, fields). Only key: value lines parsed."""
    if not (text.startswith("---\n") or text.startswith("---\r\n")):
        return text, {}
    close = text.find("\n---", 3)
    if close == -1:
        return text, {}
    raw = text[4:close]
    body_start = close + len("\n---")
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        m = FRONTMATTER_RE.match(line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return text[body_start:], fields


def extract_headings(body: str) -> list[str]:
    """Extract heading texts, skipping code fences; honor explicit {#id}."""
    headings: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        raw = m.group(2).strip()
        explicit = EXPLICIT_ANCHOR_RE.search(raw)
        if explicit:
            headings.append(explicit.group(1))
            stripped = EXPLICIT_ANCHOR_RE.sub("", raw).strip()
            if stripped:
                headings.append(stripped)
        else:
            headings.append(raw)
    return headings


def extract_links(body: str) -> list[RawLink]:
    """Extract inline links; skip code fences and inline code spans."""
    links: list[RawLink] = []
    in_fence = False
    for idx, raw_line in enumerate(body.splitlines(), start=1):
        if CODE_FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence or REF_DEF_RE.match(raw_line):
            continue
        ignored = INLINE_IGNORE_MARKER in raw_line
        scanned = INLINE_CODE_RE.sub("", raw_line)
        for m in INLINE_LINK_RE.finditer(scanned):
            target = m.group(2).strip()
            split = LINK_TITLE_RE.match(target)
            if split:
                target = split.group(1)
            links.append(RawLink(idx, m.group(1), target, ignored))
    return links


def is_external(target: str) -> bool:
    return any(target.startswith(scheme) for scheme in URL_SCHEMES)


def split_target(target: str) -> tuple[str, str]:
    if "#" not in target:
        return target, ""
    path, _, anchor = target.partition("#")
    return path, anchor


def path_matches_allowlist(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALLOWLIST_PREFIXES)


def path_in_ignored_dir(path: str) -> bool:
    return any(seg in path for seg in IGNORED_PATH_SEGMENTS)


def classify_link(target: str) -> str:
    if is_external(target):
        return "external-url"
    path, anchor = split_target(target)
    if not path and anchor:
        return "anchor-same-file"
    if anchor:
        return "anchor-cross-file"
    if Path(path).suffix.lower() in CODE_EXTENSIONS:
        return "code-file"
    return "relative-path"


def _load_slug_map(
    path: Path, cache: dict[Path, tuple[set[str], set[str]] | None]
) -> tuple[set[str], set[str]] | None:
    if path in cache:
        return cache[path]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        cache[path] = None
        return None
    body, _ = strip_frontmatter(text)
    cache[path] = build_slug_map(extract_headings(body))
    return cache[path]


def validate_one_link(
    link: RawLink,
    source: Path,
    repo_root: Path,
    same_slugs: set[str],
    same_ambiguous: set[str],
    cache: dict[Path, tuple[set[str], set[str]] | None],
) -> list[Finding]:
    """Return zero or more Findings for a single link."""
    if link.ignored or not link.target or is_external(link.target):
        return []
    klass = classify_link(link.target)
    path_part, anchor = split_target(link.target)
    rel = source.relative_to(repo_root).as_posix()

    def fnd(sev: str, cls: str, reason: str) -> list[Finding]:
        return [Finding(rel, link.line, sev, cls, link.target, reason)]

    # fmt: off
    if klass == "anchor-same-file":
        if anchor not in same_slugs:
            return fnd(FAIL, "anchor-same-file", f"anchor '#{anchor}' not found in this file")
        if anchor in same_ambiguous:
            return fnd(WARN, "ambiguous-slug", f"anchor '#{anchor}' matches multiple headings in this file")
        return []

    if path_in_ignored_dir(path_part):
        return fnd(WARN, "path-in-ignored-dir", "link points into an ignored directory (likely paste error)")

    resolved = (source.parent / path_part).resolve()

    if klass == "code-file":
        try:
            rel_resolved = resolved.relative_to(repo_root).as_posix()
        except ValueError:
            return []
        if not path_matches_allowlist(rel_resolved):
            return []
        if not resolved.is_file():
            return fnd(FAIL, "code-file", f"file '{path_part}' does not exist")
        return []

    if not resolved.exists():
        return fnd(FAIL, klass, f"file '{path_part}' does not exist")

    if anchor and resolved.is_file() and resolved.suffix.lower() == ".md":
        dest = _load_slug_map(resolved, cache)
        if dest is None:
            return []
        dest_slugs, dest_ambiguous = dest
        if anchor not in dest_slugs:
            return fnd(FAIL, "anchor-cross-file", f"anchor '#{anchor}' not found in destination file")
        if anchor in dest_ambiguous:
            return fnd(WARN, "ambiguous-slug", f"anchor '#{anchor}' matches multiple headings in destination")
    return []
    # fmt: on


def is_excluded(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in EXCLUDED_GLOB_PREFIXES)


def collect_files(repo_root: Path) -> list[Path]:
    """Walk repo and collect markdown files matching the include set."""
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in INCLUDE_PATTERNS:
        for match in repo_root.glob(pat):
            if not match.is_file() or match in seen:
                continue
            if is_excluded(match.relative_to(repo_root).as_posix()):
                continue
            seen.add(match)
            out.append(match)
    return sorted(out)


def validate_file(
    path: Path,
    repo_root: Path,
    slug_cache: dict[Path, tuple[set[str], set[str]] | None],
) -> list[Finding]:
    """Validate all links in a single markdown file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        rel = path.relative_to(repo_root).as_posix()
        return [Finding(rel, 0, FAIL, "io-error", "", f"cannot read file: {exc}")]

    body, frontmatter = strip_frontmatter(text)
    if frontmatter.get("validate-references", "").strip().lower() == "off":
        return []

    same_slugs, same_ambiguous = build_slug_map(extract_headings(body))
    slug_cache[path] = (same_slugs, same_ambiguous)
    out: list[Finding] = []
    for link in extract_links(body):
        out.extend(
            validate_one_link(
                link, path, repo_root, same_slugs, same_ambiguous, slug_cache
            )
        )
    return out


def format_text(findings: list[Finding]) -> str:
    if not findings:
        return "no findings\n"
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        grouped[f.file].append(f)
    lines: list[str] = []
    for file_name in sorted(grouped):
        lines.append(f"\n{file_name}:")
        for f in sorted(grouped[file_name], key=lambda x: (x.line, x.severity)):
            lines.append(
                f"  [{f.severity}] line {f.line}: ({f.link_class}) {f.target} -- {f.reason}"
            )
    return "\n".join(lines) + "\n"


def format_json(findings: list[Finding]) -> str:
    return json.dumps(
        [
            {
                "file": f.file,
                "line": f.line,
                "severity": f.severity,
                "class": f.link_class,
                "target": f.target,
                "reason": f.reason,
            }
            for f in findings
        ],
        indent=2,
    )


def apply_mode(findings: list[Finding], warn_only: bool, strict: bool) -> list[Finding]:
    """Adjust finding severity per --warn-only / --strict."""
    if warn_only:
        return [replace(f, severity=WARN) for f in findings]
    if strict:
        return [replace(f, severity=FAIL) for f in findings]
    return findings


def compute_exit_code(findings: list[Finding]) -> int:
    return 1 if any(f.severity == FAIL for f in findings) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate intra-repo Markdown cross-references."
    )
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--all", action="store_true", help="validate the default include set"
    )
    scope.add_argument("--file", type=Path, help="validate a single file")
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    p.add_argument(
        "--warn-only",
        action="store_true",
        help="downgrade all FAIL findings to WARN (exploratory runs)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="upgrade all WARN findings to FAIL (strict CI mode)",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="override repo root (default: auto-detected from script location)",
    )
    return p


def resolve_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    # Script lives at <repo>/skills/skill-crafting/scripts/validate_references.py
    return Path(__file__).resolve().parents[3]


def _resolve_scope(args: argparse.Namespace, repo_root: Path) -> tuple[list[Path], int]:
    if args.all:
        return collect_files(repo_root), 0
    single = args.file.resolve() if args.file else None
    if single is None or not single.is_file():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return [], 2
    return [single], 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.warn_only and args.strict:
        parser.error("--warn-only and --strict are mutually exclusive")
        return 2

    repo_root = resolve_repo_root(args.repo_root)
    if not repo_root.is_dir():
        print(f"error: repo root not found: {repo_root}", file=sys.stderr)
        return 2

    files, err = _resolve_scope(args, repo_root)
    if err:
        return err

    slug_cache: dict[Path, tuple[set[str], set[str]] | None] = {}
    findings: list[Finding] = []
    for f in files:
        findings.extend(validate_file(f, repo_root, slug_cache))
    findings = apply_mode(findings, args.warn_only, args.strict)

    if args.format == "json":
        print(format_json(findings))
    else:
        fail_count = sum(1 for f in findings if f.severity == FAIL)
        warn_count = sum(1 for f in findings if f.severity == WARN)
        header = (
            f"scanned {len(files)} file(s); {fail_count} FAIL, {warn_count} WARN"
            if findings
            else f"scanned {len(files)} file(s); no findings"
        )
        print(header)
        sys.stdout.write(format_text(findings))

    return compute_exit_code(findings)


if __name__ == "__main__":
    sys.exit(main())
