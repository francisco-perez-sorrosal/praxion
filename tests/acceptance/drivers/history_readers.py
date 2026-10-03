"""Driver for the log's readers that are reached as commands: lifecycle pairing and recovery.

Each runs as a subprocess against an explicit repository root, with no inherited
`CLAUDE_*`, `PRAXION_*`, `GIT_*` or `ANTHROPIC_*` variables; the driver never
imports either script. The spawn tally has its own driver (`spawn_tally.py`).

Recovery needs a pipeline to reconcile: `pipeline_checkout` builds a git
repository with a plan whose one step declares three files, a branch that
changed two of them, and an unchecked step in `WIP.md` -- a partially done step,
so recovery consults the log to localize it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.repository import commit_file, git, new_repository

REPO_ROOT = Path(__file__).resolve().parents[3]
LIFECYCLE_PAIRING = REPO_ROOT / "scripts" / "check_agent_lifecycle_pairing.py"
RECOVERY = REPO_ROOT / "scripts" / "reconcile_pipeline_state.py"

STEP_FILES = ("src/a.py", "src/b.py", "src/c.py")
_PLAN = "### Step 1: Build the thing\n**Files**: src/a.py, src/b.py, src/c.py\n"  # id-citation-discipline:ignore -- fixture mimics a plan document's own shape
_WIP = "- [ ] Step 1: build\n"  # id-citation-discipline:ignore -- fixture mimics a plan document's own shape


def _env() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_"))
    }


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *argv], capture_output=True, text=True, env=_env(), timeout=120
    )


def lifecycle_pairing(checkout: Path) -> dict:
    """The lifecycle-pairing check's JSON verdict over `checkout`'s log."""
    result = _run([str(LIFECYCLE_PAIRING), "--repo-root", str(checkout), "--json"])
    assert result.stdout.strip(), f"lifecycle pairing printed nothing: {result.stderr}"
    return json.loads(result.stdout)


def comparable_pairing(verdict: dict) -> dict:
    """The verdict without the path it was read from."""
    skipped = verdict.get("skipped")
    if isinstance(skipped, dict):
        skipped = {k: v for k, v in skipped.items() if k != "path"}
    return {**verdict, "skipped": skipped}


@dataclass(frozen=True)
class Pipeline:
    checkout: Path
    slug: str
    base_ref: str

    def file(self, relpath: str) -> str:
        """The absolute path a writer records for a step file."""
        return str(self.checkout / relpath)


def pipeline_checkout(path: Path, slug: str = "demo") -> Pipeline:
    checkout = new_repository(path)
    for relpath in STEP_FILES:
        commit_file(checkout, relpath, f"{relpath}\n", f"base {relpath}")
    base = git(checkout, "rev-parse", "HEAD").stdout.strip()
    commit_file(checkout, "src/a.py", "changed a\n", "work on a")
    commit_file(checkout, "src/b.py", "changed b\n", "work on b")
    task = checkout / ".ai-work" / slug
    task.mkdir(parents=True)
    (task / "WIP.md").write_text(_WIP, encoding="utf-8")
    (task / "IMPLEMENTATION_PLAN.md").write_text(_PLAN, encoding="utf-8")
    return Pipeline(checkout, slug, base)


def recovery(pipeline: Pipeline, *, max_age_days: int | None = None) -> list[dict]:
    """Recovery's per-step verdicts for the pipeline, as `/resume-pipeline` reads them."""
    argv = [
        str(RECOVERY),
        pipeline.slug,
        "--repo-root",
        str(pipeline.checkout),
        "--base-ref",
        pipeline.base_ref,
        "--json",
        "--quiet",
    ]
    if max_age_days is not None:
        argv += ["--max-age-days", str(max_age_days)]
    result = _run(argv)
    assert result.stdout.strip(), (
        f"recovery printed nothing (exit {result.returncode}): {result.stderr}"
    )
    return json.loads(result.stdout)


def localization(verdicts: list[dict]) -> dict:
    """What the log told recovery about the step: correlated agents and whether one stopped."""
    tier2 = verdicts[0]["tier2"]
    return {
        "correlated_agent_ids": sorted(tier2.get("correlated_agent_ids", [])),
        "agent_stop_seen": tier2.get("agent_stop_seen"),
    }
