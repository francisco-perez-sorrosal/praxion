"""Driver for the spawn tally, reached only as the `spawn_count.py` command.

Runs the script as a subprocess with `--json`, against an explicit repository
root and an empty transcript directory with context sizing off, so a resume is
never sized from the operator's own transcripts. It never imports the script.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPAWN_COUNT = REPO_ROOT / "scripts" / "spawn_count.py"


@dataclass(frozen=True)
class Tally:
    slug: str
    exit_code: int
    report: dict | None  # the JSON on stdout, when any
    stderr: str

    @property
    def withheld(self) -> bool:
        return self.exit_code == 2

    @property
    def spawns(self) -> int:
        assert self.report is not None, f"no report for {self.slug!r}: {self.stderr}"
        return self.report["spawns"]

    @property
    def resumes(self) -> int:
        assert self.report is not None, f"no report for {self.slug!r}: {self.stderr}"
        return _how_many(self.report["resumes"])

    @property
    def charged(self) -> int:
        assert self.report is not None, f"no report for {self.slug!r}: {self.stderr}"
        return self.report["charged"]

    @property
    def verdict(self) -> str:
        assert self.report is not None, f"no report for {self.slug!r}: {self.stderr}"
        return self.report["verdict"]

    def agent_ids(self) -> list[str]:
        assert self.report is not None, f"no report for {self.slug!r}: {self.stderr}"
        return sorted(agent["agent_id"] for agent in self.report["agents"])

    def resumes_of(self, agent_id: str) -> int:
        assert self.report is not None, f"no report for {self.slug!r}: {self.stderr}"
        agent = next(a for a in self.report["agents"] if a["agent_id"] == agent_id)
        return _how_many(agent["resumes"])

    def withheld_as_unseen(self) -> bool:
        """Exit status 2, no report, and `slug-unseen` named on stderr."""
        return self.withheld and self.report is None and "slug-unseen" in self.stderr

    def describe(self) -> str:
        return f"exit={self.exit_code} report={self.report} stderr={self.stderr.strip()!r}"


def _how_many(resumes: object) -> int:
    """A resume count, whether reported as a number, a list of resumes, or counts by class."""
    if isinstance(resumes, dict):
        return sum(resumes.values())
    if isinstance(resumes, list):
        return len(resumes)
    return int(resumes)


def spawn_count(repo_root: Path, slug: str, *, scratch: Path, budget: int | None = None) -> Tally:
    projects_dir = scratch / "no-transcripts"
    projects_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        str(SPAWN_COUNT),
        "--slug",
        slug,
        "--repo-root",
        str(repo_root),
        "--projects-dir",
        str(projects_dir),
        "--no-context",
        "--json",
    ]
    if budget is not None:
        argv += ["--budget", str(budget)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    report = json.loads(result.stdout) if result.stdout.strip() else None
    return Tally(slug, result.returncode, report, result.stderr)
