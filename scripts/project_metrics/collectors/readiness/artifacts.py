"""Judge artifacts for the LLM-scored readiness criteria.

Each LLM-judged criterion needs project evidence (the "artifact") for the
judge to evaluate. This module owns that assembly: :data:`_GATHERERS` maps a
criterion id to a dedicated gatherer, with the two long-standing fallbacks
preserved — ``c.docs.*`` criteria read the README and every other criterion
reads a deterministic top-level repository listing.

``c.testing.test_quality`` gets a multi-section evidence bundle (framework
configuration, coverage configuration plus the coverage collector's parsed
result, a test-file inventory, deterministic samples of real test code, and
testing-policy documentation) because a bare directory listing gives the
judge nothing to assess test quality against.

Design constraints (shared with the rest of the metrics package):

* stdlib-only, no subprocesses;
* deterministic for a given tree — sorted walks, spread-index sampling,
  stable truncation — so judge prompts are reproducible and the
  prior-verdict grounding stays meaningful;
* graceful degradation — missing files shrink the bundle, never raise;
* bounded size — every section and the total artifact are clipped so the
  judge request stays small regardless of repository size.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from scripts.project_metrics._path_filter import DEFAULT_EXCLUDED_DIRS

__all__ = ["ArtifactContext", "artifact_for", "read_readme", "repo_listing"]


# ---------------------------------------------------------------------------
# Size budgets — chars, not tokens; the total keeps the judge request small.
# Samples get the largest share: real test code is the most probative
# evidence for the "behavior-focused assertions" judgment.
# ---------------------------------------------------------------------------

_TOTAL_CHAR_LIMIT: int = 16_000
_CONFIG_CHAR_LIMIT: int = 2_500
_COVERAGE_CHAR_LIMIT: int = 1_500
_INVENTORY_CHAR_LIMIT: int = 1_500
_SAMPLES_CHAR_LIMIT: int = 6_000
_POLICY_DOCS_CHAR_LIMIT: int = 3_000
_PER_FILE_SNIPPET_LIMIT: int = 900
_PER_SAMPLE_CHAR_LIMIT: int = 1_900
_SAMPLE_FILE_COUNT: int = 3
_SAMPLE_LINE_COUNT: int = 60
_DISCOVERY_FILE_CAP: int = 400
_MAX_COUNT_READ_BYTES: int = 262_144
_TRUNCATION_MARKER: str = "\n... [truncated]"


@dataclass(frozen=True)
class ArtifactContext:
    """Inputs available to artifact gatherers.

    ``coverage`` is the coverage collector's ``data`` block from the same
    metrics run (``line_pct``, ``artifact_format``, ``status``, ``per_file``,
    ...) so gatherers reuse the already-parsed result instead of re-reading
    ``coverage.xml``. ``None`` when the collector produced no data.
    """

    repo_root: Path
    coverage: Mapping[str, object] | None = None


Gatherer = Callable[[ArtifactContext], str]


# ---------------------------------------------------------------------------
# Public entry point + the two legacy fallbacks.
# ---------------------------------------------------------------------------


def artifact_for(criterion_id: str, ctx: ArtifactContext) -> str:
    """Return the project text the judge evaluates for ``criterion_id``.

    Registered gatherers win; otherwise documentation criteria read the
    README and every other criterion reads the top-level repo listing.
    """

    gatherer = _GATHERERS.get(criterion_id)
    if gatherer is not None:
        return gatherer(ctx)
    if criterion_id.startswith("c.docs."):
        return read_readme(ctx.repo_root)
    return repo_listing(ctx.repo_root)


def read_readme(repo_root: Path) -> str:
    """Read the project README, trying common casings; empty string if absent."""

    for name in ("README.md", "README.rst", "README.txt", "README"):
        candidate = repo_root / name
        if candidate.is_file():
            return _read_text(candidate)
    return ""


def repo_listing(repo_root: Path) -> str:
    """Return a sorted, newline-joined listing of top-level repo entries.

    Deterministic (sorted) so the judge prompt is reproducible across runs.
    """

    try:
        entries = sorted(p.name for p in repo_root.iterdir())
    except OSError:
        return ""
    return "\n".join(entries)


# ---------------------------------------------------------------------------
# c.testing.test_quality — the evidence bundle.
# ---------------------------------------------------------------------------


def gather_test_quality(ctx: ArtifactContext) -> str:
    """Assemble the test-quality evidence bundle.

    Empty sections are omitted; a repository with no test signal at all
    degrades to the plain repo listing so the judge still sees (and can
    honestly fail) something.
    """

    test_files, capped = _discover_test_files(ctx.repo_root)
    sections: tuple[tuple[str, str, int], ...] = (
        ("Test framework configuration", _test_config_evidence(ctx.repo_root), _CONFIG_CHAR_LIMIT),
        (
            "Coverage configuration and latest measured result",
            _coverage_evidence(ctx),
            _COVERAGE_CHAR_LIMIT,
        ),
        (
            "Test inventory",
            _test_inventory_evidence(test_files, capped, ctx.repo_root),
            _INVENTORY_CHAR_LIMIT,
        ),
        (
            "Sample test files (deterministic spread across the suite)",
            _test_samples_evidence(ctx.repo_root, test_files),
            _SAMPLES_CHAR_LIMIT,
        ),
        (
            "Testing policy documentation",
            _testing_docs_evidence(ctx.repo_root),
            _POLICY_DOCS_CHAR_LIMIT,
        ),
    )
    rendered = [f"## {title}\n{_clip(body, limit)}" for title, body, limit in sections if body]
    if not rendered:
        return repo_listing(ctx.repo_root)
    header = (
        "Test-quality evidence bundle, auto-gathered from the repository. "
        "Long sections are truncated; absence of a section means no such "
        "evidence was found."
    )
    return _clip("\n\n".join([header, *rendered]), _TOTAL_CHAR_LIMIT)


# --- test-file discovery ----------------------------------------------------


def _is_python_test_file(name: str) -> bool:
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def _is_js_test_file(name: str) -> bool:
    if not name.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")):
        return False
    return ".test." in name or ".spec." in name


def _is_go_test_file(name: str) -> bool:
    return name.endswith("_test.go")


# ecosystem key -> (filename predicate, test-case pattern). Appending a row
# is the whole cost of supporting another ecosystem.
_ECOSYSTEMS: tuple[tuple[str, Callable[[str], bool], re.Pattern[str]], ...] = (
    ("python", _is_python_test_file, re.compile(r"^\s*(?:async\s+)?def\s+test_", re.M)),
    ("js/ts", _is_js_test_file, re.compile(r"^\s*(?:it|test)(?:\.\w+)?\s*\(", re.M)),
    ("go", _is_go_test_file, re.compile(r"^func\s+Test\w", re.M)),
)


def _ecosystem_for(filename: str) -> str | None:
    for key, predicate, _pattern in _ECOSYSTEMS:
        if predicate(filename):
            return key
    return None


def _keep_directory(name: str) -> bool:
    if name in DEFAULT_EXCLUDED_DIRS:
        return False
    return not name.startswith(".") or name == ".github"


def _discover_test_files(repo_root: Path) -> tuple[list[Path], bool]:
    """Return sorted repo-relative test-file paths, capped for pathology.

    The second element is True when the cap was hit (surfaced in the
    inventory section — bounded coverage is never silent).
    """

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(d for d in dirnames if _keep_directory(d))
        for name in sorted(filenames):
            if _ecosystem_for(name) is None:
                continue
            found.append(Path(dirpath, name).relative_to(repo_root))
            if len(found) >= _DISCOVERY_FILE_CAP:
                return sorted(found), True
    return sorted(found), False


# --- section builders ---------------------------------------------------------


def _manifest_dirs(repo_root: Path) -> list[Path]:
    """Root plus top-level dirs carrying a build manifest (monorepo apps)."""

    dirs = [repo_root]
    try:
        children = sorted(p for p in repo_root.iterdir() if p.is_dir())
    except OSError:
        return dirs
    for child in children:
        if not _keep_directory(child.name):
            continue
        if (child / "pyproject.toml").is_file() or (child / "package.json").is_file():
            dirs.append(child)
    return dirs


def _test_config_evidence(repo_root: Path) -> str:
    """Literal test-framework config from the root and top-level app dirs."""

    parts: list[str] = []
    for base in _manifest_dirs(repo_root):
        prefix = "" if base == repo_root else f"{base.name}/"
        pytest_section = _toml_section(
            _read_text(base / "pyproject.toml"), "[tool.pytest.ini_options]"
        )
        if pytest_section:
            parts.append(f"# {prefix}pyproject.toml\n{pytest_section}")
        for name in ("pytest.ini", "setup.cfg", "tox.ini"):
            text = _read_text(base / name)
            if text and "pytest" in text:
                parts.append(f"# {prefix}{name}\n{_clip(text, _PER_FILE_SNIPPET_LIMIT)}")
        for pattern in ("jest.config.*", "vitest.config.*", "playwright.config.*"):
            for path in sorted(base.glob(pattern)):
                parts.append(
                    f"# {prefix}{path.name}\n{_clip(_read_text(path), _PER_FILE_SNIPPET_LIMIT)}"
                )
        scripts = _package_json_test_scripts(base / "package.json")
        if scripts:
            parts.append(f"# {prefix}package.json test scripts\n{scripts}")
    return "\n\n".join(parts)


def _package_json_test_scripts(path: Path) -> str:
    text = _read_text(path)
    if not text:
        return ""
    try:
        scripts = json.loads(text).get("scripts", {})
    except (json.JSONDecodeError, AttributeError):
        return ""
    if not isinstance(scripts, dict):
        return ""
    rows = [
        f"{key}: {value}"
        for key, value in sorted(scripts.items())
        if isinstance(value, str) and "test" in key
    ]
    return "\n".join(rows)


def _coverage_evidence(ctx: ArtifactContext) -> str:
    """Coverage config (literal) plus the coverage collector's parsed result."""

    parts: list[str] = []
    pyproject = _read_text(ctx.repo_root / "pyproject.toml")
    for header in ("[tool.coverage.run]", "[tool.coverage.report]"):
        section = _toml_section(pyproject, header)
        if section:
            parts.append(f"# pyproject.toml\n{section}")
    coveragerc = _read_text(ctx.repo_root / ".coveragerc")
    if coveragerc:
        parts.append(f"# .coveragerc\n{_clip(coveragerc, _PER_FILE_SNIPPET_LIMIT)}")
    summary = _collected_coverage_summary(ctx.coverage)
    if summary:
        parts.append(summary)
    return "\n\n".join(parts)


def _collected_coverage_summary(coverage: Mapping[str, object] | None) -> str:
    if not isinstance(coverage, Mapping):
        return ""
    line_pct = coverage.get("line_pct")
    if not isinstance(line_pct, int | float):
        return ""
    lines = [
        "# Coverage measured this metrics run",
        (
            f"line coverage: {line_pct * 100:.1f}% "
            f"({coverage.get('artifact_format', 'unknown')} artifact at "
            f"{coverage.get('artifact_path', 'unknown')}, "
            f"freshness: {coverage.get('status', 'unknown')})"
        ),
    ]
    per_file = coverage.get("per_file")
    if isinstance(per_file, Mapping):
        lines.append(f"files measured: {len(per_file)}")
    return "\n".join(lines)


def _test_inventory_evidence(test_files: list[Path], capped: bool, repo_root: Path) -> str:
    """Counts of test files and test cases, per ecosystem and top-level dir."""

    if not test_files:
        return ""
    files_by_ecosystem: dict[str, int] = {}
    cases_by_ecosystem: dict[str, int] = {}
    files_by_top_dir: dict[str, int] = {}
    for rel in test_files:
        ecosystem = _ecosystem_for(rel.name) or "other"
        files_by_ecosystem[ecosystem] = files_by_ecosystem.get(ecosystem, 0) + 1
        cases_by_ecosystem[ecosystem] = cases_by_ecosystem.get(ecosystem, 0) + _count_test_cases(
            repo_root / rel, ecosystem
        )
        top = rel.parts[0] if len(rel.parts) > 1 else "."
        files_by_top_dir[top] = files_by_top_dir.get(top, 0) + 1

    cap_note = f" (discovery capped at {_DISCOVERY_FILE_CAP} files)" if capped else ""
    lines = [f"Discovered {len(test_files)} test files{cap_note}."]
    lines.extend(
        f"{eco}: {count} files, {cases_by_ecosystem[eco]} test cases"
        for eco, count in sorted(files_by_ecosystem.items())
    )
    lines.append("By top-level directory:")
    lines.extend(f"  {top}: {count} files" for top, count in sorted(files_by_top_dir.items()))
    return "\n".join(lines)


def _count_test_cases(path: Path, ecosystem: str) -> int:
    text = _read_text(path)[:_MAX_COUNT_READ_BYTES]
    if not text:
        return 0
    for key, _predicate, pattern in _ECOSYSTEMS:
        if key == ecosystem:
            return len(pattern.findall(text))
    return 0


def _test_samples_evidence(repo_root: Path, test_files: list[Path]) -> str:
    """Excerpts of a deterministic spread of test files across the suite."""

    parts: list[str] = []
    for rel in _spread_sample(test_files, _SAMPLE_FILE_COUNT):
        head = _file_head(repo_root / rel, _SAMPLE_LINE_COUNT)
        if head:
            parts.append(f"### {rel}\n{_clip(head, _PER_SAMPLE_CHAR_LIMIT)}")
    return "\n\n".join(parts)


def _spread_sample(items: list[Path], count: int) -> list[Path]:
    """Up to ``count`` items evenly spread across the sorted list.

    Spreading (first / middle / last) samples different suites in a
    multi-package repository instead of clustering in one directory.
    """

    if len(items) <= count:
        return list(items)
    step = (len(items) - 1) / (count - 1)
    indices = sorted({round(index * step) for index in range(count)})
    return [items[i] for i in indices]


_POLICY_DOC_CANDIDATES: tuple[str, ...] = (
    "TESTING.md",
    "docs/testing.md",
    "tests/README.md",
)
_POLICY_DOC_GLOBS: tuple[str, ...] = ("docs/*test*.md", "rules/**/*test*.md")
_TESTING_HEADING_PATTERN: re.Pattern[str] = re.compile(r"^(#{2,4})\s+.*test.*$", re.I | re.M)


def _testing_docs_evidence(repo_root: Path) -> str:
    """Testing-policy docs: dedicated files plus CONTRIBUTING's testing section."""

    parts: list[str] = []
    seen: set[str] = set()
    for rel in _POLICY_DOC_CANDIDATES:
        text = _read_text(repo_root / rel)
        if text:
            parts.append(f"# {rel}\n{_clip(text, _PER_FILE_SNIPPET_LIMIT)}")
            seen.add(rel)
    for glob_pattern in _POLICY_DOC_GLOBS:
        for path in sorted(repo_root.glob(glob_pattern)):
            rel = path.relative_to(repo_root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            parts.append(f"# {rel}\n{_clip(_read_text(path), _PER_FILE_SNIPPET_LIMIT)}")
    contributing_section = _heading_section(
        _read_text(repo_root / "CONTRIBUTING.md"), _TESTING_HEADING_PATTERN
    )
    if contributing_section:
        parts.append(
            f"# CONTRIBUTING.md (testing section)\n"
            f"{_clip(contributing_section, _PER_FILE_SNIPPET_LIMIT)}"
        )
    return "\n\n".join(parts)


# --- small text helpers -------------------------------------------------------


def _read_text(path: Path) -> str:
    """File text, or empty string on any I/O problem (never raises)."""

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER


def _file_head(path: Path, line_count: int) -> str:
    text = _read_text(path)
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= line_count:
        return text
    return "\n".join(lines[:line_count]) + _TRUNCATION_MARKER


def _toml_section(text: str, header: str) -> str:
    """Literal lines of one TOML table, from its header to the next table.

    Text extraction (not parsing) keeps comments — often the most
    informative part of a config — and needs no TOML writer.
    """

    if not text:
        return ""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        return ""
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("[") and lines[i].strip() != header
        ),
        len(lines),
    )
    return "\n".join(lines[start:end]).rstrip()


def _heading_section(text: str, heading_pattern: re.Pattern[str]) -> str:
    """The first markdown section whose heading matches, up to a peer heading."""

    if not text:
        return ""
    match = heading_pattern.search(text)
    if match is None:
        return ""
    level = len(match.group(1))
    tail = text[match.end() :]
    boundary = re.search(rf"^#{{1,{level}}}\s", tail, re.M)
    section_body = tail[: boundary.start()] if boundary else tail
    return (match.group(0) + section_body).rstrip()


# ---------------------------------------------------------------------------
# Registry — the extension seam. Add a criterion id -> gatherer entry to give
# any LLM criterion tailored evidence; unregistered ids keep the fallbacks.
# ---------------------------------------------------------------------------

_GATHERERS: dict[str, Gatherer] = {
    "c.testing.test_quality": gather_test_quality,
}
