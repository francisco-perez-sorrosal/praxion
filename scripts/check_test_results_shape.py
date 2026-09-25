#!/usr/bin/env python3
"""TEST_RESULTS.md fixed-shape checker.

Enforces the fixed green-step shape from
``skills/software-planning/references/agent-pipeline-details.md §
TEST_RESULTS.md Reconciliation``: a green step section (``fail=0``, no
``error=``>0) carries nothing beyond the command/result/duration/topology
lines -- no notes field, no pasted output. Measured cost: test output read
back is ~1.5% of what implementers read; the rest is free-form prose this
gate exists to bound.

A file is split into step blocks through the shared ``_step_schema`` module
-- only a ``#{2,4} Step <id>`` heading opens a block, so a sub-heading (e.g.
``### Failures``) stays attributed to its parent step, not misread as its own
section. Each block is classified over **every** ``Result:`` line it
contains, not just the first: ``empty`` (heading-only, no finding), ``red``
(any counted line reads red -- exempt from the ceiling, since failure detail
belongs there), ``green`` (subject to the byte ceiling), ``no-run`` (a
declared ``Result: none`` -- still ceiling-bounded, but never a
``missing-result-line`` finding), or ``missing-result-line`` (no ``Result:``
line at all, or only a malformed one -- the malformation is named in the
finding detail).

Exit codes: 0 clean, 1 findings found, 2 script error.

Usage:
    python3 scripts/check_test_results_shape.py FILE [FILE ...]
    python3 scripts/check_test_results_shape.py --ceiling 2048 FILE
    python3 scripts/check_test_results_shape.py --json FILE
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from _step_schema import RED as _RED
from _step_schema import Counts, Malformed, NoRun, StepBlock, split_step_blocks

DEFAULT_CEILING_BYTES = 1024


@dataclass(frozen=True)
class Finding:
    file: str
    section: str
    kind: str  # "green-over-ceiling" | "no-run-over-ceiling" | "missing-result-line"
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


def _classify_block(block: StepBlock) -> tuple[str, str | None]:
    """Classify a block over every ``Result:`` line it holds.

    Returns ``(kind, detail)`` where ``kind`` is one of ``empty``, ``red``,
    ``green``, ``no-run``, ``missing-result-line``; ``detail`` names the
    malformation when one is what produced ``missing-result-line``, else
    None. Any counted line reading red wins over a green one in the same
    block -- td-214's guard against a step reading green from a stale line
    while a later, red one sits unread.
    """
    counts = [line for _, line in block.results if isinstance(line, Counts)]
    if any(c.status == _RED for c in counts):
        return "red", None
    if counts:
        return "green", None

    noruns = [line for _, line in block.results if isinstance(line, NoRun)]
    if noruns:
        return "no-run", None

    malformed = [line for _, line in block.results if isinstance(line, Malformed)]
    if malformed:
        return "missing-result-line", malformed[0].reason
    if _is_heading_only(block):
        return "empty", None
    return "missing-result-line", None


def _is_heading_only(block: StepBlock) -> bool:
    """True when a step block is nothing but its own heading line."""
    return "\n" not in block.text


def find_findings(path: Path, ceiling: int) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    display = str(path)
    findings: list[Finding] = []

    for block in split_step_blocks(text):
        kind, detail = _classify_block(block)

        if kind in ("empty", "red"):
            continue  # heading-only and red blocks are never flagged for size

        if kind == "missing-result-line":
            findings.append(
                Finding(
                    file=display,
                    section=block.title,
                    kind="missing-result-line",
                    detail=detail or "no parseable `Result: pass=<n> fail=<n> skip=<n>` line",
                )
            )
            continue

        byte_count = len(block.text.encode("utf-8"))
        if byte_count <= ceiling:
            continue
        finding_kind = "green-over-ceiling" if kind == "green" else "no-run-over-ceiling"
        findings.append(
            Finding(
                file=display,
                section=block.title,
                kind=finding_kind,
                detail=f"{kind} section is {byte_count} bytes, exceeds ceiling of {ceiling} bytes",
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
