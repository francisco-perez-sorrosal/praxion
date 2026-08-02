#!/usr/bin/env python3
"""Enforce the AaC golden rule: generated artifacts cannot drift from their sources.

A staged change that touches a generated artifact (rendered diagram outputs in
docs/diagrams/<name>/<view>.{d2,svg}, or content inside an <!-- aac:generated -->
fence in markdown) must EITHER include a corresponding source change (the .c4
file driving the rendered output, or the source file declared in the fence's
source= attribute) OR carry a line-adjacent `aac-override: <reason>` comment.

Two modes:
- --mode=gate (default): inspect staged changes (`git diff --cached`); exit 1 on
  unjustified drift, exit 0 on clean or overridden.
- --mode=audit: scan the last N commits (--horizon, default 10) and emit findings
  for sentinel; exits 0 always.

Graceful degradation: when AAC_GOLDEN_RULE_VALIDATOR_LIKEC4=disabled is set in
the environment, drift checks that would require invoking likec4 are skipped
with a per-finding WARN; the gate does not FAIL on missing likec4.

See rules/writing/aac-dac-conventions.md for the override-comment convention.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex constants — reuse aac_fence_validator patterns when importable.
# ---------------------------------------------------------------------------

try:
    from aac_fence_validator import _CLOSER_PATTERN, _GENERATED_PATTERN
except ImportError:
    _GENERATED_PATTERN = re.compile(r"<!--\s*aac:generated(.*?)-->")
    _CLOSER_PATTERN = re.compile(r"<!--\s*aac:end\s*-->")

_ATTR_PATTERN = re.compile(r"(\w[\w-]*)=(\S+)")
_DIAGRAM_OUTPUT_RE = re.compile(r"^docs/diagrams/(?P<name>[^/]+)/(?P<view>[^/]+)\.(?:d2|svg)$")
_ARCH_DOC_RE = re.compile(r"(?:^|/)(?:ARCHITECTURE\.md|docs/architecture\.md)$")
_OVERRIDE_CODE_RE = re.compile(r"^\s*#\s*aac-override:\s+(\S.*)$")
_OVERRIDE_HTML_RE = re.compile(r"<!--\s*aac-override:\s+(\S.*?)\s*-->")
_HUNK_HEADER_RE = re.compile(r"\+(\d+)(?:,\d+)?")

CODE_PATH_PAIR = "aac-golden-rule-path-pair"
CODE_FENCE_INTERIOR = "aac-golden-rule-fence-interior"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single drift finding."""

    severity: str  # "FAIL" or "WARN"
    code: str
    path: str
    line: int | None
    message: str
    commit: str | None = None


@dataclass
class FenceRegion:
    """Line range of an aac:generated fence and its source= attribute."""

    source: str | None
    opener_line: int
    closer_line: int | None


@dataclass
class DiffHunk:
    """A contiguous range of added lines from a unified diff."""

    start: int  # first new-file line (1-based)
    lines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _is_likec4_available() -> bool:
    if os.environ.get("AAC_GOLDEN_RULE_VALIDATOR_LIKEC4") == "disabled":
        return False
    return shutil.which("likec4") is not None


def _run_git(args: list[str]) -> tuple[int, str]:
    """Run a git subcommand; return (returncode, stdout). Never raises."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout
    except (FileNotFoundError, OSError):
        return 2, ""


def _parse_diff_into_per_file(diff_output: str) -> dict[str, list[str]]:
    """Split a unified diff by file; return {path: [raw diff lines]}."""
    result: dict[str, list[str]] = {}
    current: str | None = None
    for raw in diff_output.splitlines():
        if raw.startswith("+++ b/"):
            current = raw[6:].strip()
            result.setdefault(current, [])
        elif current is not None:
            result[current].append(raw)
    return result


def _is_relevant_path(path: str) -> bool:
    return bool(_DIAGRAM_OUTPUT_RE.match(path) or _ARCH_DOC_RE.search(path))


# ---------------------------------------------------------------------------
# Override detection
# ---------------------------------------------------------------------------


def _line_has_override(line: str) -> bool:
    return bool(_OVERRIDE_CODE_RE.search(line) or _OVERRIDE_HTML_RE.search(line))


def _diff_lines_have_override(diff_lines: list[str]) -> bool:
    """Return True if any added line in the diff contains an override comment."""
    return any(
        _line_has_override(raw[1:])
        for raw in diff_lines
        if raw.startswith("+") and not raw.startswith("+++")
    )


def _hunk_has_adjacent_override(hunk: DiffHunk) -> bool:
    """Return True if an added line in the hunk is or is preceded by an override."""
    added_with_lineno: list[tuple[int, str]] = []
    lineno = hunk.start
    for raw in hunk.lines:
        if raw.startswith("@@"):
            m = _HUNK_HEADER_RE.search(raw)
            lineno = int(m.group(1)) if m else lineno
        elif raw.startswith("+") and not raw.startswith("+++"):
            added_with_lineno.append((lineno, raw[1:]))
            lineno += 1
        elif not raw.startswith("-"):
            lineno += 1

    for i, (_, content) in enumerate(added_with_lineno):
        if _line_has_override(content):
            return True
        # Check line above (previous added line, as a proxy for adjacency)
        if i > 0 and _line_has_override(added_with_lineno[i - 1][1]):
            return True
    return False


# ---------------------------------------------------------------------------
# Fence-region parsing
# ---------------------------------------------------------------------------


def _parse_fence_regions(content: str) -> list[FenceRegion]:
    """Return all aac:generated fence regions found in markdown content."""
    regions: list[FenceRegion] = []
    open_region: FenceRegion | None = None
    for lineno, raw in enumerate(content.splitlines(), start=1):
        if _CLOSER_PATTERN.search(raw):
            if open_region is not None:
                open_region.closer_line = lineno
                regions.append(open_region)
                open_region = None
            continue
        m = _GENERATED_PATTERN.search(raw)
        if not m:
            continue
        if open_region is not None:
            regions.append(open_region)  # unclosed fence
        attrs = dict(_ATTR_PATTERN.findall(m.group(1)))
        open_region = FenceRegion(source=attrs.get("source"), opener_line=lineno, closer_line=None)
    if open_region is not None:
        regions.append(open_region)
    return regions


def _line_in_region(line: int, region: FenceRegion) -> bool:
    start = region.opener_line + 1
    end = region.closer_line - 1 if region.closer_line is not None else sys.maxsize
    return start <= line <= end


# ---------------------------------------------------------------------------
# Hunk parsing
# ---------------------------------------------------------------------------


def _parse_hunks(diff_lines: list[str]) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    for raw in diff_lines:
        if raw.startswith("@@"):
            if current is not None:
                hunks.append(current)
            m = _HUNK_HEADER_RE.search(raw)
            current = DiffHunk(start=int(m.group(1)) if m else 1, lines=[raw])
        elif current is not None:
            current.lines.append(raw)
    if current is not None:
        hunks.append(current)
    return hunks


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------


def _check_path_pair(staged_paths: set[str], diff_by_path: dict[str, list[str]]) -> list[Finding]:
    """Return FAIL findings for diagram outputs staged without their .c4 source."""
    findings: list[Finding] = []
    for path in sorted(staged_paths):
        m = _DIAGRAM_OUTPUT_RE.match(path)
        if not m:
            continue
        source = f"docs/diagrams/{m.group('name')}.c4"
        if source in staged_paths:
            continue
        diff_lines = diff_by_path.get(path, [])
        if _diff_lines_have_override(diff_lines):
            continue
        ext = Path(path).suffix
        hint = "<!-- aac-override: <reason> -->" if ext == ".svg" else "# aac-override: <reason>"
        findings.append(
            Finding(
                severity="FAIL",
                code=CODE_PATH_PAIR,
                path=path,
                line=None,
                message=(
                    f"[FAIL] {path}:<none> — staged generated output without "
                    f"staging its source '{source}'. "
                    f"Hint: stage {source} OR add `{hint}` on the line above."
                ),
            )
        )
    return findings


def _check_fence_interior(
    staged_paths: set[str],
    diff_by_path: dict[str, list[str]],
    repo_root: Path,
) -> list[Finding]:
    """Return FAIL findings for staged hunks inside aac:generated fences."""
    findings: list[Finding] = []
    for path in sorted(staged_paths):
        if not _ARCH_DOC_RE.search(path):
            continue
        try:
            content = (repo_root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        regions = _parse_fence_regions(content)
        if not regions:
            continue
        hunks = _parse_hunks(diff_by_path.get(path, []))
        for hunk in hunks:
            for region in regions:
                if not _line_in_region(hunk.start, region):
                    continue
                if region.source and region.source in staged_paths:
                    continue
                if _hunk_has_adjacent_override(hunk):
                    continue
                source_hint = region.source or "<source-file>"
                findings.append(
                    Finding(
                        severity="FAIL",
                        code=CODE_FENCE_INTERIOR,
                        path=path,
                        line=hunk.start,
                        message=(
                            f"[FAIL] {path}:{hunk.start} — staged change inside "
                            f"aac:generated fence (source={region.source!r}) "
                            f"without staging the source. "
                            f"Hint: stage {source_hint} OR add "
                            f"`<!-- aac-override: <reason> -->` on the line above."
                        ),
                    )
                )
    return findings


def _inspect(paths: set[str], diff_by_path: dict[str, list[str]], repo_root: Path) -> list[Finding]:
    """Run both detection checks; return combined findings."""
    findings = _check_path_pair(paths, diff_by_path)
    findings.extend(_check_fence_interior(paths, diff_by_path, repo_root))
    return findings


# ---------------------------------------------------------------------------
# Gate mode
# ---------------------------------------------------------------------------


def run_gate(repo_root: Path) -> int:
    """Inspect staged diff; return 1 on violation, 0 on clean."""
    if not _is_likec4_available():
        print(
            "INFO: likec4 unavailable or disabled; "
            "likec4-based drift checks skipped (not used in v1.1).",
            file=sys.stderr,
        )
    _, staged_out = _run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    staged_paths = {ln.strip() for ln in staged_out.splitlines() if ln.strip()}
    relevant = [p for p in staged_paths if _is_relevant_path(p)]
    if not relevant:
        return 0

    _, diff_out = _run_git(["diff", "--cached", "-U0", "--", *relevant])
    findings = _inspect(staged_paths, _parse_diff_into_per_file(diff_out), repo_root)

    for f in findings:
        print(f.message)
    return 1 if any(f.severity == "FAIL" for f in findings) else 0


# ---------------------------------------------------------------------------
# Audit mode
# ---------------------------------------------------------------------------


def _emit_audit_findings(findings: list[Finding], emit_json: bool) -> None:
    """Print audit findings in human or JSON format."""
    if emit_json:
        print(
            json.dumps(
                [
                    {
                        "commit": f.commit,
                        "path": f.path,
                        "line": f.line,
                        "severity": f.severity,
                        "code": f.code,
                        "message": f.message,
                    }
                    for f in findings
                ],
                indent=2,
            )
        )
    else:
        for f in findings:
            sha_prefix = f.commit[:7] if f.commit else "?"
            line_info = str(f.line) if f.line is not None else "<none>"
            print(f"[{f.severity}] {sha_prefix} {f.path}:{line_info} — {f.code}")


def run_audit(repo_root: Path, horizon: int, emit_json: bool) -> int:
    """Scan the last N commits; always exits 0."""
    if not _is_likec4_available():
        print(
            "INFO: likec4 unavailable or disabled; likec4-based drift checks skipped.",
            file=sys.stderr,
        )
    _, log_out = _run_git(["log", "--oneline", f"-n{horizon}"])
    commits = [ln.split(None, 1)[0] for ln in log_out.splitlines() if ln.strip()]

    all_findings: list[Finding] = []
    for sha in commits:
        _, paths_out = _run_git(["show", "--name-only", "--diff-filter=ACMR", "--format=", sha])
        commit_paths = {ln.strip() for ln in paths_out.splitlines() if ln.strip()}
        relevant = [p for p in commit_paths if _is_relevant_path(p)]
        if not relevant:
            continue
        _, diff_out = _run_git(["show", sha, "-U0", "--", *relevant])
        findings = _inspect(commit_paths, _parse_diff_into_per_file(diff_out), repo_root)
        for f in findings:
            f.commit = sha
            f.severity = "WARN"  # audit mode: sentinel decides escalation
        all_findings.extend(findings)

    _emit_audit_findings(all_findings, emit_json)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on clean/audit, 1 on gate violation."""
    parser = argparse.ArgumentParser(
        description=(
            "Enforce the AaC golden rule: generated artifacts cannot drift "
            "from their sources. See rules/writing/aac-dac-conventions.md."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["gate", "audit"],
        default="gate",
        help="gate (default): inspect staged diff; audit: scan recent commits.",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=10,
        metavar="N",
        help="Number of commits to scan in audit mode (default: 10).",
    )
    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        default=False,
        help="Emit JSON findings list to stdout (audit mode only).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root.resolve()
    if args.mode == "gate":
        return run_gate(repo_root)
    return run_audit(repo_root, args.horizon, args.emit_json)


if __name__ == "__main__":
    sys.exit(main())
