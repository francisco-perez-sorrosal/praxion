"""Shared builders for the kernel manifest checker's tests (not a test module).

A copy of the live inputs with one thing broken is each canary's subject: the fixtures,
the editors that break one thing, and the ledger and commit builders the flip and liveness
tests share.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_kernel_manifest as cb  # noqa: E402
import generate_kernels as gk  # noqa: E402
import kernel_model as km  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_kernel_manifest.py"
CAP = km.MAX_STRING_CHARS

COPIED = (
    "rules",
    "agents",
    "claude/kernels",
    "claude/config/CLAUDE.md.tmpl",
    "CLAUDE.md",
    gk.PREAMBLE_PATH,
    cb.HOOKS_PATH,
    km.LEDGER_PATH,  # live flags arrive with their records: a legitimate switch is a clean baseline
)
UNIFIED_RULE = "rules/swe/agent-intermediate-documents.md"
PROBE_HEADING = "Resident Probe Section"
PROBE_SECTION = f"\n## {PROBE_HEADING}\n\nA paragraph that no audience entry classifies yet.\n"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("kernel-inputs") / "checkout"
    for rel in COPIED:
        source, target = REPO_ROOT / rel, root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, target)
    return root


@pytest.fixture
def repo(template: Path, tmp_path: Path) -> Path:
    shutil.copytree(template, tmp_path / "checkout")
    return tmp_path / "checkout"


def unswitched(root: Path) -> None:
    """Back to a checkout where no role is switched: no ledger, no flag in any definition."""
    (root / km.LEDGER_PATH).unlink()
    for definition in (root / "agents").glob("*.md"):
        text = definition.read_text(encoding="utf-8")
        definition.write_text(
            "".join(ln for ln in text.splitlines(True) if not ln.startswith("omitClaudeMd:")),
            encoding="utf-8",
        )


def kinds(root: Path) -> set[str]:
    return {finding.kind for finding in cb.check(root)}


def subjects(root: Path, kind: str) -> list[str]:
    return [finding.subject for finding in cb.check(root) if finding.kind == kind]


def edit_manifest(root: Path, change: Callable[[dict], None]) -> None:
    path = root / km.MANIFEST_PATH
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, width=100), encoding="utf-8")


def edit_index(root: Path, change: Callable[[dict], None]) -> None:
    path = root / km.INDEX_PATH
    index = json.loads(path.read_text(encoding="utf-8"))
    change(index)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


ADHERENCE = cb.ADHERENCE_ENTRY
PILOT = ["researcher", "verifier", "discipline-consultant", "skill-genesis", "context-engineer"]


def run_row(pairs: int = 24, passes: bool = True, eval_entry: str = ADHERENCE) -> dict:
    return {"id": "r1", "complete_pairs": pairs, "passes_flip_rule": passes, "entry": eval_entry}


def switched_row(**fields: object) -> dict:
    row = {
        "status": "switched",
        "since": "2026-10-12",
        "runs": [run_row()],
        "passing_run": "r1",
        "probe_before_tokens": 31_000,
        "probe_after_tokens": 22_000,
        "flip_rule_ratified": True,
        "flip_ratified": True,
    }
    return {**row, **fields}


def trial_row() -> dict:
    return {"status": "trial", "since": "2026-10-12", "runs": []}


def held_row(**fields: object) -> dict:
    """A trial closed without a flip; `fields` alter it (`runs`, `since`, `reason`)."""
    row = {
        "status": "held",
        "since": "2026-10-12",
        "runs": [],
        "reason": "the flip rule did not pass",
    }
    return {**row, **fields}


def write_ledger(root: Path, eligible: list[str] | None = None, **roles: dict) -> None:
    path = root / km.LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = {"version": 1, "eligible": PILOT if eligible is None else eligible, "roles": roles}
    path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")


def frontmatter_line(root: Path, role: str, line: str) -> None:
    """Put `line`, verbatim, into the role's definition frontmatter after its name."""
    path = root / f"agents/{role}.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(f"name: {role}\n", f"name: {role}\n{line}\n", 1),
        encoding="utf-8",
    )


def omit_claude_md(root: Path, role: str, value: str = "true") -> None:
    frontmatter_line(root, role, f"omitClaudeMd: {value}")


def regenerate(root: Path) -> None:
    gk.write_files(root, gk.plan_kernels(root).files)


def commit_all(root: Path, at: str = "2026-10-13T12:00:00+00:00") -> None:
    """Commit everything under `root` (a repository of its own) at the moment `at`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_DATE=at, GIT_COMMITTER_DATE=at)
    identity = ["-c", "user.name=Probe", "-c", "user.email=probe@example.invalid"]
    steps = (["init", "-q"], ["add", "-A"], [*identity, "commit", "-q", "--no-verify", "-m", "x"])
    for step in steps:
        subprocess.run(
            ["git", *step], cwd=root, env=env, check=True, capture_output=True, timeout=60
        )


def flipped(root: Path, role: str = "researcher", **fields: object) -> None:
    """The role flipped with the record `fields` alter: ledger, flag and regenerated kernels."""
    write_ledger(root, **{role: switched_row(**fields)})
    omit_claude_md(root, role)
    regenerate(root)


def run_checker(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


AT = "2026-10-13T14:00:00+00:00"
NOON = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def started(agent_id: str, agent_type: str = "praxion:researcher", at: str = AT) -> dict:
    return {
        "timestamp": at,
        "session_id": "s1",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "event_type": "agent_start",
    }


def delivered(agent_id: str, role: str = "researcher") -> dict:
    return {
        "timestamp": AT,
        "session_id": "s1",
        "agent_id": agent_id,
        "agent_type": f"praxion:{role}",
        "event_type": "kernel_injected",
        "role": role,
    }


def write_log(project: Path, *rows: dict) -> None:
    state = project / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    cb.reader.log_path(state).write_text(  # the one reader names the file
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
