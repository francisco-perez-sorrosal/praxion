"""Driver for the spec extract and its design-vocabulary lint, reached only as a CLI.

The pipeline runs `extract_spec.py <slug> --repo-root <root> --json` over a
task directory holding `SYSTEMS_PLAN.md` (and optionally `TASK_BRIEF.md`).
This driver does the same in a scratch project and nothing more: it never
imports the command.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRACT_SPEC = _REPO_ROOT / "scripts" / "extract_spec.py"

SLUG = "footprint-change"
EXTRACT_NAME = "SPEC_EXTRACT.md"


@dataclass(frozen=True)
class ExtractRun:
    exit_code: int
    findings: list[dict]
    extract: str | None
    stderr: str

    def blocking(self) -> list[dict]:
        return [f for f in self.findings if f.get("severity") == "blocking"]

    def extract_sha256(self) -> str | None:
        if self.extract is None:
            return None
        return hashlib.sha256(self.extract.encode("utf-8")).hexdigest()


def run_extract(root: Path, plan: str, brief: str | None = None) -> ExtractRun:
    """Write the spec into a fresh task directory under `root` and run the command on it."""
    task_dir = root / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "SYSTEMS_PLAN.md").write_text(plan, encoding="utf-8")
    if brief is not None:
        (task_dir / "TASK_BRIEF.md").write_text(brief, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(EXTRACT_SPEC), SLUG, "--repo-root", str(root), "--json"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    extract_file = task_dir / EXTRACT_NAME
    extract = extract_file.read_text(encoding="utf-8") if extract_file.exists() else None
    return ExtractRun(
        exit_code=proc.returncode,
        findings=list(payload.get("findings") or []),
        extract=extract,
        stderr=proc.stderr,
    )
