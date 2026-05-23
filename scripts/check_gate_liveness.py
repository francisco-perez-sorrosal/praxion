#!/usr/bin/env python3
"""Gate Liveness detector — GL02 (forbidden-pattern-contradiction).

Cites: rules/swe/gate-liveness.md — a gate is a claim that it catches a defect
class and must be proven to bite. This detector is itself a gate, so it ships with
a canary (scripts/test_check_gate_liveness.py).

Scope: GL02 only. The companion check GL01 (orphaned-consumer) was prototyped here
but moved to the sentinel's Pass-2 LLM judgment — "is this section produced
anywhere?" is a semantic question a regex answers with too many false positives,
whereas a dead grep (a scan for a pattern another rule forbids in the scanned
location) is a hard, mechanically-detectable contradiction. Use the proof that
matches the gate (D0 in the gate-liveness ADR).

Invoked by the sentinel's GL dimension (`--json`); also runnable standalone.
Exit code: 1 when findings exist, 0 when clean — so it doubles as a commit gate.
Honors an inline `gate-liveness:ignore` escape for deliberate references.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Files that legitimately *describe* forbidden patterns as teaching material
# (the defining rules, this detector's own docs/tests). Path-substring excluded so
# the detector never flags its own vocabulary.
_EXCLUDE_SUBSTRINGS = (
    "gate-liveness",
    "gate-canaries",
    "check_gate_liveness",
    "id-citation-discipline",
    "shipped-artifact-isolation",
)
_IGNORE = "gate-liveness:ignore"
_SCAN_DIRS = ("agents", "rules", "skills", "commands")

# A grep/scan directive that targets a pattern id-citation-discipline forbids in
# test/code. Canonical dead-grep shape: "scan test files for req{NN}_".
_SCAN_VERB = re.compile(r"\b(grep|scan|search|match|look for)\b", re.IGNORECASE)
_TESTCODE = re.compile(r"\b(test|tests|code|source)\b|\.py|\.ts", re.IGNORECASE)
_FORBIDDEN_LITERALS = re.compile(
    r"req\{NN\}_|req\\d\+_|req\d+_|REQ-\d|AC-\d"  # id-citation-discipline:ignore
)


def _iter_files(root: Path):
    for directory in _SCAN_DIRS:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if any(sub in str(path) for sub in _EXCLUDE_SUBSTRINGS):
                continue
            yield path


def check_forbidden_pattern(root: Path) -> list[dict]:
    """GL02: instructions that grep/scan for a pattern forbidden in the target."""
    findings: list[dict] = []
    for path in _iter_files(root):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if _IGNORE in line:
                continue
            if (
                _FORBIDDEN_LITERALS.search(line)
                and _SCAN_VERB.search(line)
                and _TESTCODE.search(line)
            ):
                findings.append(
                    {
                        "check": "forbidden-pattern",
                        "severity": "fail",
                        "file": str(path.relative_to(root)),
                        "line": lineno,
                        "evidence": line.strip()[:200],
                        "why": (
                            "instruction greps/scans test or code for a pattern "
                            "id-citation-discipline forbids there — it can never "
                            "match, so the gate is dead"
                        ),
                    }
                )
    return findings


_CHECKS = {"forbidden-pattern": check_forbidden_pattern}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate Liveness detector (GL02).")
    parser.add_argument(
        "--check",
        choices=[*_CHECKS, "all"],
        default="all",
        help="which liveness check to run (default: all)",
    )
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    root = Path(args.root)
    selected = _CHECKS if args.check == "all" else {args.check: _CHECKS[args.check]}
    findings: list[dict] = []
    for fn in selected.values():
        findings.extend(fn(root))

    if args.json:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    else:
        for finding in findings:
            loc = f"{finding['file']}:{finding['line']}"
            print(
                f"[{finding['severity'].upper()}] {finding['check']} {loc} — {finding['why']}"
            )
        print(f"{len(findings)} gate-liveness finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
