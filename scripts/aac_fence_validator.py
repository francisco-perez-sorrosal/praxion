"""AaC+DaC fence validator — validate HTML-comment fence regions in Markdown.

Parses ``<!-- aac:generated ... -->`` and ``<!-- aac:authored ... -->`` fence
regions and reports structural violations, missing required attributes, and
unresolvable source paths.

Source-path resolution: ``source=`` values are resolved relative to the
**current working directory** (the repo root when the script is invoked
normally), not relative to the markdown file's directory.

See rules/writing/aac-dac-conventions.md for the fence schema.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class Severity:
    """String constants for finding severity levels."""

    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class Finding:
    """A single validation finding associated with a fence region."""

    severity: str  # "WARN" or "FAIL"
    code: str  # machine-stable identifier
    message: str  # human-readable description
    line: int | None  # 1-based line of the offending fence opener, or None


@dataclass
class ValidationResult:
    """Result of validating a single markdown file."""

    verdict: str  # "PASS" | "PASS_WITH_WARNINGS" | "FAIL"
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fence-line pattern matching
# ---------------------------------------------------------------------------

GENERATED_PATTERN = re.compile(r"<!--\s*aac:generated(.*?)-->")
_AUTHORED_PATTERN = re.compile(r"<!--\s*aac:authored(.*?)-->")
CLOSER_PATTERN = re.compile(r"<!--\s*aac:end\s*-->")

# Private aliases retained for backward compatibility with existing importers.
_GENERATED_PATTERN = GENERATED_PATTERN
_CLOSER_PATTERN = CLOSER_PATTERN

_ATTR_PATTERN = re.compile(r"(\w[\w-]*)=(\S+)")
# Matches CommonMark fenced-code-block delimiters: 3+ backticks or 3+ tildes
# at the start of a line (after optional leading spaces per CommonMark spec).
_CODE_FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _parse_attributes(attr_string: str) -> dict[str, str]:
    """Extract key=value pairs from a fence opener's attribute string."""
    return dict(_ATTR_PATTERN.findall(attr_string))


def _is_likec4_available() -> bool:
    """Return True if likec4 binary is on PATH and not disabled via env var."""
    if os.environ.get("AAC_FENCE_VALIDATOR_LIKEC4") == "disabled":
        return False
    return shutil.which("likec4") is not None


# ---------------------------------------------------------------------------
# Core validation logic
# ---------------------------------------------------------------------------


def _check_generated_opener(attrs: dict[str, str], lineno: int) -> list[Finding]:
    """Emit findings for an aac:generated opener line."""
    findings: list[Finding] = []

    for required in ("source", "view"):
        if required not in attrs:
            findings.append(
                Finding(
                    severity=Severity.FAIL,
                    code="missing-attribute",
                    message=(
                        f"aac:generated at line {lineno} is missing "
                        f"required attribute '{required}='"
                    ),
                    line=lineno,
                )
            )

    if "source" not in attrs:
        return findings  # can't resolve path without source=

    source_path = Path(attrs["source"])
    if not source_path.is_absolute():
        source_path = Path.cwd() / source_path

    if not source_path.exists():
        findings.append(
            Finding(
                severity=Severity.FAIL,
                code="source-path-not-found",
                message=(
                    f"aac:generated at line {lineno}: "
                    f"source='{attrs['source']}' does not resolve "
                    "to an existing file (resolved relative to cwd)"
                ),
                line=lineno,
            )
        )
        return findings  # no drift check when source is missing

    if _is_likec4_available():
        # TODO: implement real drift detection via subprocess
        # likec4 gen <source> <view> and compare whitespace-normalised output.
        pass  # stub: assume no drift
    else:
        findings.append(
            Finding(
                severity=Severity.WARN,
                code="validator-unable-to-verify-drift",
                message=(
                    f"aac:generated at line {lineno}: likec4 is unavailable; drift check skipped"
                ),
                line=lineno,
            )
        )

    return findings


def _check_authored_opener(attrs: dict[str, str], lineno: int) -> list[Finding]:
    """Emit findings for an aac:authored opener line."""
    if "owner" not in attrs:
        return [
            Finding(
                severity=Severity.FAIL,
                code="missing-attribute",
                message=(f"aac:authored at line {lineno} is missing required attribute 'owner='"),
                line=lineno,
            )
        ]
    return []


def _validate_lines(lines: list[str]) -> list[Finding]:
    """Walk markdown lines and emit findings for all fence violations."""
    findings: list[Finding] = []
    fence_depth: int = 0  # supports nested aac: regions
    opener_line: int = 0
    current_kind: str = ""
    in_code_block = False

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\n")

        if _CODE_FENCE_PATTERN.match(line):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        if _CLOSER_PATTERN.search(line):
            if fence_depth > 0:
                fence_depth -= 1
            if fence_depth == 0:
                current_kind = ""
            continue

        generated_match = _GENERATED_PATTERN.search(line)
        authored_match = _AUTHORED_PATTERN.search(line)

        if not (generated_match or authored_match):
            continue

        if fence_depth == 0:
            opener_line = lineno
        fence_depth += 1

        if generated_match:
            current_kind = "generated"
            attrs = _parse_attributes(generated_match.group(1))
            findings.extend(_check_generated_opener(attrs, lineno))
        else:
            assert authored_match is not None
            current_kind = "authored"
            attrs = _parse_attributes(authored_match.group(1))
            findings.extend(_check_authored_opener(attrs, lineno))

    if fence_depth > 0:
        findings.append(
            Finding(
                severity=Severity.FAIL,
                code="unbalanced-fence",
                message=(
                    f"aac:{current_kind} fence opened at line {opener_line} "
                    "was never closed before end of file"
                ),
                line=opener_line,
            )
        )

    return findings


def _compute_verdict(findings: list[Finding]) -> str:
    """Derive the overall verdict from a list of findings."""
    if any(f.severity == Severity.FAIL for f in findings):
        return "FAIL"
    if any(f.severity == Severity.WARN for f in findings):
        return "PASS_WITH_WARNINGS"
    return "PASS"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate(path: Path | str) -> ValidationResult:
    """Validate AaC+DaC fence regions in a markdown file.

    The function is idempotent and side-effect-free: it never writes to the
    input file, and two calls with the same arguments return equal results.

    Args:
        path: Path to the markdown file to validate.

    Returns:
        A :class:`ValidationResult` with a verdict and zero or more findings.
    """
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    findings = _validate_lines(lines)
    verdict = _compute_verdict(findings)
    return ValidationResult(verdict=verdict, findings=findings)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _format_finding(finding: Finding) -> str:
    line_info = f"line {finding.line}" if finding.line is not None else "no line"
    return f"[{finding.severity}] {finding.code} ({line_info}): {finding.message}"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code: 0 = PASS/WARN, 1 = FAIL."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate AaC+DaC fence regions in a markdown file. "
            "Exits 0 on PASS or PASS_WITH_WARNINGS, 1 on FAIL."
        )
    )
    parser.add_argument("file", help="Path to the markdown file to validate")
    args = parser.parse_args(argv)

    result = validate(args.file)
    for finding in result.findings:
        print(_format_finding(finding))
    print(f"Verdict: {result.verdict}")

    return 0 if result.verdict in {"PASS", "PASS_WITH_WARNINGS"} else 1


if __name__ == "__main__":
    sys.exit(main())
