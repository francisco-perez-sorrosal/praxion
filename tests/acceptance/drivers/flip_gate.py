"""Driver for the commit gate's flip checks: cited runs, the parent ledger, eligibility, liveness.

Scenarios work on a kernel sandbox (`kernel_sandbox`) and judge it with the commit gate
as `.pre-commit-config.yaml` registers it (`kernel_sandbox.commit_gate`).

Bound here, because the specification or the base commit fixes them:

- a switched record's runs and `passing_run`, in the adoption ledger's wire shape
  (`kernel_adoption`), and the results file a cited run resolves to:
  `.ai-state/eval_ledger/adherence/<run id>.json`, whose `run.id` is that id;
- planted results files are copies of committed ones, so each is a real results file
  of the runner's own format: a clear run of 24 complete pairs (the researcher's
  `20261014T152926Z-723e7a`), a not-clear run of 24 (the verifier's
  `20261015T035717Z-03a785`), and an underpowered run of 13 (the researcher's
  `20261014T045733Z-7050ca`). A copy measures another role when every mention of the
  original role in it is rewritten to that role;
- a parent commit's ledger the gate cannot read is a ledger file that is not YAML;
- the liveness check, `scripts/check_kernel_manifest.py --liveness --repo-root PROJECT
  --json`, run from the plugin root; exit 0 is a clean report;
- the observation log's archives, at the positions the retention policy names
  (`log_segments.archive_position_path`), a segment's span closing at its last
  modification.

Unbound until a binding step names the designed surface: where the eligible roles are
pinned, how a commit changes them, and every path that holds them.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tests.acceptance.drivers import kernel_adoption
from tests.acceptance.drivers.kernel_adoption import AdherenceRun, AdoptionRecord
from tests.acceptance.drivers.kernel_sandbox import (
    ADOPTION_LEDGER,
    REPO_ROOT,
    Sandbox,
    UnboundDriverError,
    agent_path,
    commit_paths,
    isolated_env,
)

RESULTS_SUBDIR = ".ai-state/eval_ledger/adherence"
CLEAR_24 = ("20261014T152926Z-723e7a", "researcher", 24)
NOT_CLEAR_24 = ("20261015T035717Z-03a785", "verifier", 24)
UNDERPOWERED_13 = ("20261014T045733Z-7050ca", "researcher", 13)
OMIT = "omitClaudeMd: true"


# -- Results files a record cites ----------------------------------------------------------


def plant_results(root: Path, run_id: str, source: tuple[str, str, int], role: str) -> int:
    """Copy a committed results file into `root` as run `run_id` of `role`; its complete pairs."""
    source_id, source_role, pairs = source
    text = (REPO_ROOT / RESULTS_SUBDIR / f"{source_id}.json").read_text(encoding="utf-8")
    text = text.replace(source_id, run_id)
    if role != source_role:
        text = text.replace(source_role, role)
    document = json.loads(text)
    assert document["run"]["id"] == run_id, "the planted copy does not carry its own run id"
    target = root / RESULTS_SUBDIR / f"{run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return pairs


def _suffix(role: str, salt: str) -> str:
    return hashlib.sha1(f"{salt}:{role}".encode()).hexdigest()[:6]


def earlier_id(role: str) -> str:
    return f"20261101T000000Z-{_suffix(role, 'earlier')}"


def passing_id(role: str) -> str:
    return f"20261102T000000Z-{_suffix(role, 'passing')}"


def cited_switch_record(root: Path, role: str) -> AdoptionRecord:
    """A full switched record of `role` whose two cited runs resolve to planted results files:
    an underpowered earlier run, then a clear passing run of 24 complete pairs."""
    early = plant_results(root, earlier_id(role), UNDERPOWERED_13, role)
    passing = plant_results(root, passing_id(role), CLEAR_24, role)
    full = kernel_adoption.full_switch_record(role)
    return AdoptionRecord(
        role,
        "switched",
        runs=(
            AdherenceRun(earlier_id(role), early, False),
            AdherenceRun(passing_id(role), passing, True),
        ),
        probe_before_tokens=full.probe_before_tokens,
        probe_after_tokens=full.probe_after_tokens,
        flip_rule_ratified=True,
        flip_ratified=True,
    )


def switch_with_flag(sandbox: Sandbox, record: AdoptionRecord) -> None:
    """Record `record` (its trial committed first) and set the role's flag, as a flip does."""
    kernel_adoption.record(sandbox.root, record)
    text = sandbox.read(agent_path(record.role))
    if OMIT not in text:
        name_line = next(ln for ln in text.splitlines() if ln.startswith("name:"))
        sandbox.replace(agent_path(record.role), name_line + "\n", f"{name_line}\n{OMIT}\n")


def remove_results(root: Path, run_id: str) -> None:
    (root / RESULTS_SUBDIR / f"{run_id}.json").unlink()


# -- The parent commit's ledger ---------------------------------------------------------------


def commit_unreadable_parent_ledger(root: Path) -> str:
    """Commit a ledger the gate cannot read, then restore the readable one, uncommitted."""
    readable = (root / ADOPTION_LEDGER).read_text(encoding="utf-8")
    (root / ADOPTION_LEDGER).write_text("roles: [researcher\n  status: {switched\n")
    commit_paths(root, "ledger: an unreadable ledger", ADOPTION_LEDGER)
    (root / ADOPTION_LEDGER).write_text(readable, encoding="utf-8")
    return ADOPTION_LEDGER


def commit_without_ledger(sandbox: Sandbox) -> None:
    """A parent commit holding no ledger, and no role that relies on one."""
    (sandbox.root / ADOPTION_LEDGER).unlink()
    for name in ("researcher",):
        sandbox.replace(agent_path(name), f"{OMIT}\n", "")
    commit_paths(sandbox.root, "no ledger", ADOPTION_LEDGER, agent_path("researcher"))


# -- The eligible roles: unbound ------------------------------------------------------------------


def eligible_roles(root: Path) -> set[str]:
    raise UnboundDriverError(
        "the roles eligible to be switched, read from where they are pinned apart from the"
        " adoption records and the agent definitions"
    )


def set_eligible_roles(root: Path, roles: set[str]) -> None:
    raise UnboundDriverError("a commit's change to the pinned eligible roles")


def paths_holding_eligible_roles(root: Path) -> set[str]:
    raise UnboundDriverError("every repository path that holds the eligible roles")


# -- The liveness check ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LivenessReport:
    exit_code: int
    output: str

    @property
    def clean(self) -> bool:
        return self.exit_code == 0


def liveness(project: Path, plugin_root: Path) -> LivenessReport:
    scratch = project.parent / f".liveness-{project.name}"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/check_kernel_manifest.py",
            "--liveness",
            "--repo-root",
            str(project),
            "--json",
        ],
        cwd=plugin_root,
        env=isolated_env(scratch),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return LivenessReport(proc.returncode, proc.stdout + proc.stderr)


def set_segment_time(segment: Path, moment: datetime) -> None:
    stamp = moment.timestamp()
    os.utime(segment, (stamp, stamp))


def utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=UTC)
