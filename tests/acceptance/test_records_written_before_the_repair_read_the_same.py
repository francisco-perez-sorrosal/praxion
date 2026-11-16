"""Records the earlier driver wrote are read the same way, and none is rewritten.

The fixture freezes two task directories the Base commit's driver wrote, with their git
history (attempts lines, ledger lines, result blocks, a two-round review file, a handoff),
and what that driver's `status --json` and `next` printed over them. The driver of today,
run over the same records, prints the same and leaves every record byte for byte.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tests.acceptance.drivers.loop_repairs import without_location
from tests.acceptance.drivers.step_loop import (
    CONFIG_DIR_VARIABLE,
    END_WAIT_VARIABLE,
    STEP_LOOP,
    _clean_env,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "records_before_repair"
FROZEN = json.loads((FIXTURES / "read_by_the_base_driver.json").read_text(encoding="utf-8"))
CASES = sorted(FROZEN["cases"])
ROOT_MARK = "<ROOT>"


def _restore(tmp_path: Path, case: str) -> Path:
    with tarfile.open(FIXTURES / f"{case}.tar.gz") as tar:
        tar.extractall(tmp_path, filter="data")
    return (tmp_path / "project").resolve()


def _normalized(value, *roots: str):
    text = json.dumps(value, sort_keys=True)
    # Longest first: a resolved root holds its unresolved spelling as a suffix (macOS puts
    # `/private` before `/var`), so the shorter one replaced first would leave the prefix behind.
    for root in sorted(set(roots), key=len, reverse=True):
        text = text.replace(root, ROOT_MARK)
    return _without_echo(json.loads(text))


def _without_echo(value):
    """Printed commands are compared without the location options they end with: those are
    the caller's own words, echoed back, and say nothing of how a record was read."""
    if isinstance(value, dict):
        return {key: _without_echo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_without_echo(item) for item in value]
    if isinstance(value, str):
        return without_location(value)
    return value


def _read_back(tmp_path: Path, root: Path, case: str):
    frozen = FROZEN["cases"][case]
    env = {
        **_clean_env(),
        CONFIG_DIR_VARIABLE: str(tmp_path / "home" / ".claude"),
        END_WAIT_VARIABLE: "0",
    }
    location = ["--repo-root", str(root), "--base-ref", frozen["scratch_base"]]

    def run(*args: str) -> dict:
        done = subprocess.run(
            [sys.executable, str(STEP_LOOP), *args, FROZEN["slug"], *location],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        return json.loads(done.stdout)

    old_roots = (frozen["written_at"], str(Path(frozen["written_at"]).resolve()))
    roots = (str(root), *old_roots)
    return _normalized(run("status", "--json"), *roots), _normalized(run("next"), *roots)


def _records(root: Path) -> dict[str, bytes]:
    task = root / ".ai-work" / FROZEN["slug"]
    return {
        str(p.relative_to(task)): p.read_bytes() for p in sorted(task.rglob("*")) if p.is_file()
    }


def _frozen(case: str, key: str):
    frozen = FROZEN["cases"][case]
    old = frozen["written_at"]
    return _normalized(frozen[key], old, str(Path(old).resolve()))


@pytest.mark.parametrize("case", CASES)
def test_records_the_earlier_driver_wrote_read_as_they_did(tmp_path, case):
    root = _restore(tmp_path, case)

    state, envelope = _read_back(tmp_path, root, case)

    assert state == _frozen(case, "status"), json.dumps(state, indent=1)
    assert envelope == _frozen(case, "next"), json.dumps(envelope, indent=1)


@pytest.mark.parametrize("case", CASES)
def test_reading_the_earlier_records_rewrites_none_of_them(tmp_path, case):
    root = _restore(tmp_path, case)
    before = _records(root)

    _read_back(tmp_path, root, case)

    assert _records(root) == before
