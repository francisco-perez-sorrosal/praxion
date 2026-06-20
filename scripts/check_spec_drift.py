#!/usr/bin/env python3
"""SH07 sentinel check — archived spec drift detector.

Wraps ``detect_drift`` from scripts/spec_drift.py and emits sentinel-formatted
finding rows for any non-orphaned-edge drift found in archived specs under
``.ai-state/specs/``.

Invoked by the sentinel's SH07 dimension (``--repo-root``); also runnable
standalone.  Exit code: 1 when important/suggested findings exist, 0 otherwise.

Orphaned-edge findings are silently deferred to SH01/SH04 — they are not
emitted here to avoid duplication.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from scripts.spec_drift import detect_drift  # pytest / python -m mode
except ModuleNotFoundError:
    from spec_drift import detect_drift  # type: ignore[no-redef]  # standalone

_SPECS_SUBPATH = Path(".ai-state") / "specs"
_CHECK_ID = "SH07"
_ORPHANED_EDGE = "orphaned-edge"


def run_sh07(repo_root: Path) -> list[dict]:
    """Run the SH07 check over archived specs under *repo_root*.

    Returns a list of sentinel finding dicts, each with keys:
        ``check``, ``severity`` (info/important/suggested), ``message``.

    Returns an empty list when ``.ai-state/specs/`` is absent — the sentinel
    silently skips rather than erroring when there is nothing to scan.
    Orphaned-edge findings from ``detect_drift`` are filtered out (deferred to
    SH01/SH04).
    """
    specs_dir = repo_root / _SPECS_SUBPATH
    if not specs_dir.is_dir():
        return []

    findings: list[dict] = []
    for spec_file in sorted(specs_dir.glob("SPEC_*.md")):
        scope = f"archived:{spec_file.name}"
        raw = detect_drift(scope=scope, repo_root=repo_root, base_sha=None)
        for finding in raw:
            if finding.get("kind") == _ORPHANED_EDGE:
                continue  # deferred to SH01/SH04
            findings.append(
                {
                    "check": _CHECK_ID,
                    "severity": finding.get("severity", "suggested"),
                    "message": (
                        f"{finding.get('req', '?')} in {finding.get('pointer', scope)}: "
                        f"{finding.get('rationale', 'drift detected')}"
                    ),
                }
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SH07 sentinel check — archived spec drift.")
    parser.add_argument(
        "--repo-root",
        default=".",
        metavar="PATH",
        help="path to the repository root (default: current directory)",
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    findings = run_sh07(repo_root)

    if args.json:
        print(
            json.dumps({"check": _CHECK_ID, "findings": findings, "count": len(findings)}, indent=2)
        )
    else:
        for row in findings:
            print(f"[{row['severity'].upper()}] {row['check']} — {row['message']}")
        print(f"{len(findings)} SH07 finding(s)")

    has_actionable = any(r["severity"] in ("important", "suggested") for r in findings)
    return 1 if has_actionable else 0


if __name__ == "__main__":
    sys.exit(main())
