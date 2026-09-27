"""RED-first skeleton: the private-reader test (REQ-19).

DS-3's second invariant: the set of code consumers of the log equals the set
of non-test modules importing `_observation_log.reader`. This test scans the
repo for any `.py` file -- outside the owner package and a named allowlist --
whose source references the log filename literal
(`reader.LOG_FILENAME`) directly, which is exactly how a reader could bypass
the owner package undetected.

Import target does not exist yet: `hooks._observation_log.reader`. This file
is RED by ModuleNotFoundError until Step 3 lands the owner package. Note that
even after Step 3 lands, the real assertion stays red until Steps 4-5
migrate every private reader listed in `SYSTEMS_PLAN.md`'s per-reader
migration map -- that transition (ImportError -> real findings -> clean) is
expected and is not a defect in this test.
"""

from __future__ import annotations

import re
from pathlib import Path

from hooks._observation_log import reader

REPO_ROOT = Path(__file__).resolve().parent.parent

OWNER_PACKAGE_PREFIX = "hooks/_observation_log/"

# Per SYSTEMS_PLAN.md § Architecture "Not migrated" list -- each has its own
# named reason there (whole-file rewrite with a dedup key, a .gitattributes
# string, a hook-byproduct file list, and the liveness checker itself).
ALLOWLIST = frozenset(
    {
        "scripts/merge_driver_observations.py",
        "scripts/reconcile_ai_state.py",
        "scripts/_sidecar_init.py",
        "eval/src/praxion_evals/live/scenarios.py",
        "scripts/check_gate_liveness.py",
    }
)

_TEST_FILE_RE = re.compile(r"(^|/)test_[^/]+\.py$")
_EXCLUDED_DIR_MARKERS = (".venv/", "/plugins/cache/", "/.claude/worktrees/", "/node_modules/")


def _referencing_modules(root: Path) -> list[str]:
    """Repo-relative paths of non-test .py files (outside the owner package
    and the allowlist) whose source references the log filename literal."""
    findings = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(OWNER_PACKAGE_PREFIX):
            continue
        if rel in ALLOWLIST or _TEST_FILE_RE.search(rel):
            continue
        if any(marker in f"/{rel}" for marker in _EXCLUDED_DIR_MARKERS):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if reader.LOG_FILENAME in text:
            findings.append(rel)
    return findings


def test_no_undeclared_module_references_the_log_filename_directly() -> None:
    findings = _referencing_modules(REPO_ROOT)

    assert findings == [], (
        "these modules reference the log filename outside the owner package "
        f"and its allowlist: {findings}"
    )


def test_canary_a_synthetic_undeclared_reader_is_caught(tmp_path: Path) -> None:
    """Gate-liveness canary: a module outside the owner package and the
    allowlist that references the log filename directly must be flagged.
    """
    rogue = tmp_path / "scripts" / "rogue_reader.py"
    rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.write_text(f'path = "{reader.LOG_FILENAME}"\n', encoding="utf-8")

    findings = _referencing_modules(tmp_path)

    assert findings == ["scripts/rogue_reader.py"]
