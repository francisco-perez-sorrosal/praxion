"""Orchestrator — wires Daytona sandbox lifecycle, Cognee writes, and the three
role scripts (run_review.py, rewrite_skill.py, fix.py) into a 2-round demo.

Usage:
    python hackathon/demo.py --warm          # pre-warm image cache + Cognee init
    python hackathon/demo.py --round 1       # run Round 1 (miss)
    python hackathon/demo.py --round 2       # run Round 2 (catch)
    python hackathon/demo.py --reset         # restore SKILL.md and clear artifacts
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path for `hackathon.*` imports.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / "hackathon" / ".env")
except ImportError:
    pass

from hackathon.fix import propose_fix  # noqa: E402
from hackathon.models import SkillRunEntry  # noqa: E402
from hackathon.score import score  # noqa: E402

# ---------------------------------------------------------------------------
# Paths — all absolute from repo root so CWD does not matter.
# ---------------------------------------------------------------------------

SKILL_PATH = _REPO_ROOT / "hackathon" / "SKILL_DEMO.md"
RULE_PATH = _REPO_ROOT / "rules" / "swe" / "coding-style.md"
ARTIFACTS = _REPO_ROOT / "hackathon" / "artifacts"
FIXTURES = _REPO_ROOT / "hackathon" / "fixtures"
BACKUP_PATH = ARTIFACTS / "SKILL_v1.md.bak"
SKILL_V2_BACKUP = ARTIFACTS / "SKILL_v2.md.bak"
TIMELINE_PATH = ARTIFACTS / "timeline.json"

SCRIPT_DIR = _REPO_ROOT / "hackathon"

# Round configuration — 4 rounds across 2 improvement cycles.
# Cycle 1 (rounds 1+2): mutable-default-argument defect class.
# Cycle 2 (rounds 3+4): overly-broad-exception-handler defect class.
# Each cycle: odd round = baseline (skill misses); even round = improved (Fixer fires).
_ROUND_CONFIG: dict[int, dict[str, object]] = {
    1: {
        "patch": "pr_A.patch",
        "ground_truth": "ground_truth_A.json",
        "run_id": "praxion:r1:code-review",
        "skill_id": "code-review@v1",
        "cognee_dataset": "praxion-code-review-v1",
        "defect_label": "mutable defaults — baseline",
    },
    2: {
        "patch": "pr_B.patch",
        "ground_truth": "ground_truth_B.json",
        "run_id": "praxion:r2:code-review",
        "skill_id": "code-review@v2",
        "cognee_dataset": "praxion-code-review-v2",
        "defect_label": "mutable defaults — improved",
    },
    3: {
        "patch": "pr_C.patch",
        "ground_truth": "ground_truth_C.json",
        "run_id": "praxion:r3:code-review",
        "skill_id": "code-review@v2",
        "cognee_dataset": "praxion-code-review-v2",
        "defect_label": "broad except — baseline",
    },
    4: {
        "patch": "pr_D.patch",
        "ground_truth": "ground_truth_D.json",
        "run_id": "praxion:r4:code-review",
        "skill_id": "code-review@v3",
        "cognee_dataset": "praxion-code-review-v3",
        "defect_label": "broad except — improved",
    },
}

# Custom sandbox image spec — pinned to match hackathon/requirements.txt.
# Constructed inside functions (deferred import) to avoid failing at module level
# when daytona is not installed in the host venv.
_SANDBOX_IMAGE_PACKAGES = ["anthropic==0.97.0", "pydantic", "pytest"]


def _sandbox_image() -> object:
    """Return the custom sandbox image object (deferred to avoid import-time failure)."""
    from daytona import Image  # noqa: PLC0415

    return Image.debian_slim("3.12").pip_install(_SANDBOX_IMAGE_PACKAGES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_timeline(record: dict) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if TIMELINE_PATH.exists():
        existing = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    existing.append(record)
    TIMELINE_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def backup_or_restore() -> str:
    """Round 1 entry — first call backs up v1; re-runs restore v1 from backup.

    Re-runs of Round 1 also invalidate `SKILL_v2.md.bak` since the v2 snapshot
    will be regenerated when Round 1's Editor fires again.
    """
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if BACKUP_PATH.exists():
        SKILL_PATH.write_text(BACKUP_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        BACKUP_PATH.write_text(SKILL_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    SKILL_V2_BACKUP.unlink(missing_ok=True)
    return SKILL_PATH.read_text(encoding="utf-8")


def backup_or_restore_v2() -> str:
    """Round 3 entry — snapshot the post-Round-1 skill (v2) before second rewrite."""
    SKILL_V2_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if SKILL_V2_BACKUP.exists():
        SKILL_PATH.write_text(
            SKILL_V2_BACKUP.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        SKILL_V2_BACKUP.write_text(
            SKILL_PATH.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return SKILL_PATH.read_text(encoding="utf-8")


def _make_daytona_client() -> object:
    """Construct a Daytona sync client from env vars (deferred import)."""
    from daytona import Daytona, DaytonaConfig  # noqa: PLC0415

    config = DaytonaConfig(
        api_key=os.environ["DAYTONA_API_KEY"],
        api_url=os.environ["DAYTONA_API_URL"],
    )
    return Daytona(config)


# ---------------------------------------------------------------------------
# --warm
# ---------------------------------------------------------------------------


async def _cognee_warmup() -> None:
    import cognee  # noqa: PLC0415

    await cognee.add("warmup", dataset_name="skill-runs-warmup")


def warm() -> int:
    import time

    start = time.monotonic()
    print("Warming Daytona image cache...")
    daytona = _make_daytona_client()
    from daytona import CreateSandboxFromImageParams  # noqa: PLC0415

    sandbox = daytona.create(
        CreateSandboxFromImageParams(
            image=_sandbox_image(),
            auto_stop_interval=10,
        ),
        timeout=120.0,
    )
    print(f"Sandbox {sandbox.id} created — image cached")

    # Daytona's image cache lives on the image layer, not on running sandboxes.
    # Delete the warm-up sandbox immediately so disk-quota does not accumulate.
    try:
        sandbox.delete()
        print(f"Sandbox {sandbox.id} deleted (image stays cached)")
    except Exception as exc:
        print(f"warm: sandbox delete returned {exc!r} (continuing)", file=sys.stderr)

    print("Initializing Cognee (one-time SQLite/LanceDB/Kuzu setup)...")
    asyncio.run(_cognee_warmup())
    print("Cognee initialized")

    elapsed = time.monotonic() - start
    print(f"warm complete in {elapsed:.1f}s")
    return 0


# ---------------------------------------------------------------------------
# --round N
# ---------------------------------------------------------------------------


async def _cognee_write_entry(entry: SkillRunEntry, skill_text: str, n: int) -> None:
    import cognee  # noqa: PLC0415

    dataset = str(_ROUND_CONFIG[n]["cognee_dataset"])
    await cognee.add(entry.model_dump_json(), dataset_name="skill-runs")
    await cognee.add(skill_text, dataset_name=dataset)


def _run_sandbox_review(n: int, patch_path: Path) -> Path:
    """Create sandbox, upload inputs, execute reviewer, download outputs.

    Returns the local path to the downloaded findings.json.
    Cleans up the sandbox (best-effort) before returning.
    """
    from daytona import CreateSandboxFromImageParams  # noqa: PLC0415

    daytona = _make_daytona_client()
    print(f"[Round {n}] Creating sandbox...")
    sandbox = daytona.create(
        CreateSandboxFromImageParams(
            image=_sandbox_image(),
            env_vars={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
            auto_stop_interval=10,
        ),
        timeout=120.0,
    )
    print(f"[Round {n}] Sandbox {sandbox.id} ready")

    sandbox.fs.upload_file(SKILL_PATH.read_bytes(), "SKILL.md")
    sandbox.fs.upload_file(RULE_PATH.read_bytes(), "coding-style.md")
    sandbox.fs.upload_file(patch_path.read_bytes(), "pr.patch")
    sandbox.fs.upload_file((SCRIPT_DIR / "run_review.py").read_bytes(), "run_review.py")
    sandbox.fs.upload_file((SCRIPT_DIR / "models.py").read_bytes(), "models.py")
    sandbox.fs.upload_file(b"", "__init__.py")  # flat-package marker

    print(f"[Round {n}] Running reviewer...")
    resp = sandbox.process.exec(
        "python run_review.py --skill SKILL.md --rule coding-style.md "
        "--diff pr.patch --out findings.json",
        timeout=180,
    )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"daytona_round{n}.log").write_text(
        resp.result or "", encoding="utf-8"
    )
    print(f"[Round {n}] Reviewer exit_code={resp.exit_code}")

    findings_path = ARTIFACTS / f"findings_r{n}.json"
    findings_path.write_bytes(sandbox.fs.download_file("findings.json"))
    try:
        (ARTIFACTS / f"report_r{n}.md").write_bytes(
            sandbox.fs.download_file("report.md")
        )
    except Exception:
        pass  # report.md is optional; findings.json is the critical artifact

    try:
        daytona.delete(sandbox, timeout=60.0)
    except Exception as exc:
        print(f"[Round {n}] sandbox delete warning: {exc}", file=sys.stderr)

    return findings_path


async def _cognee_add_skill_version(version: int) -> None:
    """Persist the current SKILL.md text as the post-rewrite version in Cognee."""
    import cognee  # noqa: PLC0415

    await cognee.add(
        SKILL_PATH.read_text(encoding="utf-8"),
        dataset_name=f"praxion-code-review-v{version}",
    )


def _persist_run_record(entry: SkillRunEntry) -> None:
    """Append SkillRunEntry to a local JSONL mirror so dashboard + rewrite avoid Cognee search."""
    runs_path = ARTIFACTS / "skill_runs.jsonl"
    with runs_path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def _trigger_rewrite(n: int, entry: SkillRunEntry) -> None:
    """Invoke rewrite_skill.py as a subprocess, passing the run record via temp file."""
    print(f"[Round {n}] Triggering rewrite_skill.py on host...")
    record_path = ARTIFACTS / f"run_record_r{n}.json"
    record_path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "rewrite_skill.py"),
            "--skill-path",
            str(SKILL_PATH),
            "--backup-dir",
            str(ARTIFACTS),
            "--rewrite-log",
            str(ARTIFACTS / "rewrite_log.md"),
            "--rule",
            str(RULE_PATH),
            "--run-record-json",
            str(record_path),
        ],
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
    # Round 1's rewrite produces v2; Round 3's rewrite produces v3.
    new_version = 2 if n == 1 else 3
    asyncio.run(_cognee_add_skill_version(new_version))


def _trigger_fixer(n: int, findings_list: list, patch_path: Path) -> None:
    """Invoke fix.py logic on host; write per-round artifacts so each cycle's fix survives."""
    print(f"[Round {n}] Triggering fix.py on host...")
    rule_text = RULE_PATH.read_text(encoding="utf-8")
    diff_text = patch_path.read_text(encoding="utf-8")
    patch_text, test_text = propose_fix(findings_list, diff_text, rule_text)
    if patch_text:
        (ARTIFACTS / f"proposed_fix_r{n}.patch").write_text(
            patch_text, encoding="utf-8"
        )
        (ARTIFACTS / f"missing_test_r{n}.py").write_text(test_text, encoding="utf-8")
        # Mirror the latest cycle's outputs as canonical names for backwards compatibility
        # with any tooling that read the unsuffixed paths.
        (ARTIFACTS / "proposed_fix.patch").write_text(patch_text, encoding="utf-8")
        (ARTIFACTS / "missing_test.py").write_text(test_text, encoding="utf-8")
        print(f"[Round {n}] Fixer: wrote artifacts to {ARTIFACTS}")


_PR_LETTERS = {1: "A", 2: "B", 3: "C", 4: "D"}


def run_round(n: int) -> int:
    if n not in _ROUND_CONFIG:
        print(
            f"Error: --round must be one of {sorted(_ROUND_CONFIG)}, got {n}",
            file=sys.stderr,
        )
        return 1

    cfg = _ROUND_CONFIG[n]
    patch_path = FIXTURES / str(cfg["patch"])
    gt_path = FIXTURES / str(cfg["ground_truth"])

    # Snapshot the skill before each cycle's first round so the dashboard can
    # show v1 → v2 → v3 evolution. Cycle 1 starts at round 1 (v1 baseline);
    # cycle 2 starts at round 3 (v2 baseline = post-cycle-1 skill).
    if n == 1:
        skill_text = backup_or_restore()
    elif n == 3:
        skill_text = backup_or_restore_v2()
    else:
        skill_text = SKILL_PATH.read_text(encoding="utf-8")

    ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))

    findings_path = _run_sandbox_review(n, patch_path)

    findings_list = json.loads(findings_path.read_text(encoding="utf-8")).get(
        "findings", []
    )
    success_score, feedback, error_type, error_message = score(
        findings_list, ground_truth
    )
    print(f"[Round {n}] score={success_score} error_type={error_type!r}")

    entry = SkillRunEntry(
        run_id=str(cfg["run_id"]),
        selected_skill_id=str(cfg["skill_id"]),
        task_text=(
            f"Review PR-{_PR_LETTERS[n]} against code-review skill "
            f"({cfg['defect_label']})"
        ),
        result_summary=error_message or f"Round {n} complete; score={success_score}",
        success_score=success_score,
        feedback=feedback,
        error_type=error_type,
        error_message=error_message,
    )
    asyncio.run(_cognee_write_entry(entry, skill_text, n))
    print(f"[Round {n}] Cognee write complete")

    _append_timeline(
        {"round": n, "score": success_score, "error_type": error_type, "ts": _now_iso()}
    )

    _persist_run_record(entry)

    # Cycle's odd-numbered rounds (1, 3) trigger the Editor on a miss.
    # Cycle's even-numbered rounds (2, 4) trigger the Fixer on a catch.
    if n in (1, 3) and success_score < 1.0:
        _trigger_rewrite(n, entry)
    if n in (2, 4) and success_score >= 0.5:
        _trigger_fixer(n, findings_list, patch_path)

    return 0


# ---------------------------------------------------------------------------
# --reset (optional utility)
# ---------------------------------------------------------------------------


def reset() -> int:
    if BACKUP_PATH.exists():
        SKILL_PATH.write_text(BACKUP_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Restored SKILL.md from {BACKUP_PATH}")
    else:
        print("No backup found — SKILL.md not changed")

    for item in ARTIFACTS.iterdir():
        if item.name != ".gitkeep":
            item.unlink() if item.is_file() else shutil.rmtree(item)
    print(f"Cleared {ARTIFACTS}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hackathon self-improving skill demo orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python hackathon/demo.py --warm      # pre-warm image cache\n"
            "  python hackathon/demo.py --round 1   # run Round 1\n"
            "  python hackathon/demo.py --round 2   # run Round 2\n"
            "  python hackathon/demo.py --reset      # restore SKILL.md + clear artifacts"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--warm", action="store_true", help="Pre-warm Daytona image cache"
    )
    group.add_argument("--round", type=int, metavar="N", help="Run round N (1 or 2)")
    group.add_argument(
        "--reset", action="store_true", help="Restore SKILL.md and clear artifacts"
    )
    args = parser.parse_args()

    if args.warm:
        return warm()
    if args.round is not None:
        return run_round(args.round)
    if args.reset:
        return reset()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
