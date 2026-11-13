"""Driver for the artifact registry and its drift test, reached from outside.

The registry is read through its public functions (`by_name`, `cleanup_policy_for`), loaded
from the file in a fresh module so no scenario shares it with another. The drift test is run
as pytest runs it, over a copy of this checkout's files, so a scenario may make one consumer
drop an artifact without touching this checkout.

Bound here, because the specification or the base commit fixes them:

- the registry is `scripts/artifact_registry.py`; `by_name(name)` returns the registered
  artifact (with its `location` and `cleanup_policy`) or None, and `cleanup_policy_for(name)`
  returns its cleanup policy or None (their signatures and docstrings at the base commit);
- the drift test is `scripts/test_artifact_registry.py`, run with pytest from the checkout root;
- the consumers the drift test checks, each naming every artifact it lists on a line of its
  own: the dashboard's workshop list, the compaction snapshot's document list and the artifact
  inventory's tree (the specification names all three);
- the artifacts the cleanup check refuses to delete while live are `WIP.md` and
  `REWORK_MANIFEST.md` (the check's docstring at the base commit), so the policy they share is
  the one that agrees with a refusal.

Isolation: every process runs with `kernel_sandbox.isolated_env`.
"""

from __future__ import annotations

import atexit
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

from tests.acceptance.drivers.kernel_sandbox import REPO_ROOT, RunResult, _run, isolated_env

REGISTRY = "scripts/artifact_registry.py"
DRIFT_TEST = "scripts/test_artifact_registry.py"
REFUSED_WHILE_LIVE = ("WIP.md", "REWORK_MANIFEST.md")
CONSUMERS = {
    "dashboard workshop list": "dashboard_app/src/server/artifacts/files.ts",
    "compaction snapshot list": "hooks/precompact_state.py",
    "artifact inventory tree": "skills/software-planning/references/artifact-inventory.md",
}
# Trees the drift test has no reason to read; leaving them out keeps a copy fast.
_SKIPPED_TREES = ("tests", ".ai-state", "docs", "eval/tests", "task-chronograph-mcp")


def registry(root: Path = REPO_ROOT) -> ModuleType:
    """The checkout's artifact registry, loaded afresh."""
    path = root / REGISTRY
    spec = importlib.util.spec_from_file_location(f"artifact_registry_{id(path)}", path)
    assert spec is not None, f"cannot load {REGISTRY}"
    assert spec.loader is not None, f"cannot load {REGISTRY}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# -- A copy of the checkout -------------------------------------------------------------------


def _files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split("\0")
    return sorted(
        rel
        for rel in set(listed)
        if rel
        and not rel.startswith(tuple(f"{t}/" for t in _SKIPPED_TREES))
        and (REPO_ROOT / rel).is_file()
    )


_template: Path | None = None


def _checkout_template() -> Path:
    global _template
    if _template is None:
        parent = Path(tempfile.mkdtemp(prefix="registry-template-"))
        atexit.register(shutil.rmtree, parent, ignore_errors=True)
        dest = parent / "checkout"
        for rel in _files():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, dest / rel)
        _template = dest
    return _template


def checkout_copy(dest: Path) -> Path:
    shutil.copytree(_checkout_template(), dest, symlinks=True)
    return dest


def omit_from_consumer(root: Path, consumer: str, name: str) -> None:
    """Drop every line of `consumer` that names `name`, as an edit that forgets it would."""
    path = root / CONSUMERS[consumer]
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if name not in line]
    assert len(kept) < len(lines), f"the {consumer} ({CONSUMERS[consumer]}) does not list {name}"
    path.write_text("".join(kept), encoding="utf-8")


def drift_test(root: Path) -> RunResult:
    """The registry's drift test, run with pytest from `root`."""
    argv = [sys.executable, "-m", "pytest", DRIFT_TEST, "-q", "-p", "no:cacheprovider"]
    return _run(argv, root, isolated_env(root.parent / f".{root.name}-drift"), timeout=600)
