#!/usr/bin/env python3
"""TEST_RESULTS.md fixed-shape checker.

Enforces the fixed green-step shape from
``skills/software-planning/references/agent-pipeline-details.md §
TEST_RESULTS.md Reconciliation``: a green step section (``fail=0``, no
``error=``>0) carries nothing beyond the command/result/duration/topology
lines -- no notes field, no pasted output. Measured cost: test output read
back is ~1.5% of what implementers read; the rest is free-form prose this
gate exists to bound.

A file is split into ``## Step N`` sections. Each section is classified from
its ``Result:`` line: **red** if ``fail=`` or ``error=`` is greater than
zero, **green** otherwise. A red section is never flagged for size -- failure
detail (log pointer, ``### Failures`` blocks) is expected there. A green
section over the byte ceiling, or a section with no parseable ``Result:``
line, is a finding.

Exit codes: 0 clean, 1 findings found, 2 script error.

Usage:
    python3 scripts/check_test_results_shape.py FILE [FILE ...]
    python3 scripts/check_test_results_shape.py --ceiling 2048 FILE
    python3 scripts/check_test_results_shape.py --json FILE
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CEILING_BYTES = 1024

_SECTION_HEADER_RE = re.compile(r"^## .*$", re.MULTILINE)
_RESULT_LINE_RE = re.compile(r"^Result:.*$", re.MULTILINE)
_FAIL_RE = re.compile(r"\bfail=(\d+)")
_ERROR_RE = re.compile(r"\berror=(\d+)")


@dataclass(frozen=True)
class Finding:
    file: str
    section: str
    kind: str  # "green-over-ceiling" | "missing-result-line"
    detail: str
    byte_count: int | None = None
    ceiling: int | None = None

    def as_dict(self) -> dict:
        d = {"file": self.file, "section": self.section, "kind": self.kind, "detail": self.detail}
        if self.byte_count is not None:
            d["bytes"] = self.byte_count
        if self.ceiling is not None:
            d["ceiling"] = self.ceiling
        return d


def split_sections(text: str) -> list[str]:
    """Split on ``^## `` headers; each section runs to the next header or EOF."""
    starts = [m.start() for m in _SECTION_HEADER_RE.finditer(text)]
    if not starts:
        return []
    boundaries = [*starts, len(text)]
    return [text[boundaries[i] : boundaries[i + 1]].rstrip() for i in range(len(starts))]


def section_title(section: str) -> str:
    header_line = section.splitlines()[0]
    return header_line[len("## ") :].strip()


def classify_result(section: str) -> tuple[str, int | None]:
    """Return (kind, fail_count) where kind is "red", "green", or "missing-result-line"."""
    result_match = _RESULT_LINE_RE.search(section)
    if result_match is None:
        return "missing-result-line", None

    line = result_match.group(0)
    fail_match = _FAIL_RE.search(line)
    if fail_match is None:
        return "missing-result-line", None

    fail_count = int(fail_match.group(1))
    error_match = _ERROR_RE.search(line)
    error_count = int(error_match.group(1)) if error_match else 0
    return ("red" if fail_count > 0 or error_count > 0 else "green"), fail_count


def find_findings(path: Path, ceiling: int) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    display = str(path)
    findings: list[Finding] = []

    for section in split_sections(text):
        title = section_title(section)
        kind, _fail_count = classify_result(section)

        if kind == "missing-result-line":
            findings.append(
                Finding(
                    file=display,
                    section=title,
                    kind="missing-result-line",
                    detail="no parseable `Result: pass=<n> fail=<n> skip=<n>` line",
                )
            )
            continue

        if kind == "red":
            continue  # red sections carry failure detail; never flagged for size

        byte_count = len(section.encode("utf-8"))
        if byte_count > ceiling:
            findings.append(
                Finding(
                    file=display,
                    section=title,
                    kind="green-over-ceiling",
                    detail=f"green section is {byte_count} bytes, exceeds ceiling of {ceiling} bytes",
                    byte_count=byte_count,
                    ceiling=ceiling,
                )
            )

    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("files", nargs="+", metavar="FILE", type=Path)
    parser.add_argument(
        "--ceiling",
        type=int,
        default=DEFAULT_CEILING_BYTES,
        help=f"byte ceiling for a green section (default: {DEFAULT_CEILING_BYTES})",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    all_findings: list[Finding] = []
    for file_path in args.files:
        try:
            all_findings.extend(find_findings(file_path, args.ceiling))
        except OSError as exc:
            print(f"error reading {file_path}: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps({"findings": [f.as_dict() for f in all_findings]}, indent=2))
    elif all_findings:
        for finding in all_findings:
            print(f"[{finding.kind}] {finding.file}: {finding.section}: {finding.detail}")
        print(f"{len(all_findings)} finding(s)")
    else:
        print(f"scanned {len(args.files)} file(s); 0 findings.")

    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
