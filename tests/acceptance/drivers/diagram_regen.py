"""Driver that runs Praxion's diagram regeneration gates in a scratch checkout.

A scratch checkout is a fresh git repository holding a copy of every file of this
repository that git tracks or would track (working-tree contents, ignored files left
out), committed once. Scenarios act on that copy, never on the repository itself.

Two gates are driven through their declared entry points:

* the pre-commit regeneration: the `entry` of the hook whose id is `diagram-regen` in
  `.pre-commit-config.yaml`, run from the checkout root the way pre-commit runs a
  `language: system` hook with `pass_filenames: false`;
* the CI drift gate: the `run` steps of the `regenerate-and-diff` job in
  `.github/workflows/architecture.yml`, in order, minus the steps that install the
  toolchain (the scenarios use the locally installed toolchain and require it to be
  the version those install steps pin).

Isolation: git runs with no inherited `GIT_*`, `CLAUDE*` or `PRAXION_*` variables, no
system configuration, a fixed identity and no signing; every gate runs with proxies
pointing at a closed local port, so no step can reach the network.
"""

from __future__ import annotations

import atexit
import functools
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from tests.acceptance.drivers.architecture_model import REPO_ROOT, offline_env

WORKFLOW = Path(".github/workflows/architecture.yml")
PRECOMMIT_CONFIG = Path(".pre-commit-config.yaml")
HOOK_ID = "diagram-regen"
DRIFT_JOB = "regenerate-and-diff"
RENDER_DIR = Path("docs/diagrams/architecture/rendered")
MODEL_SOURCE = Path("docs/diagrams/architecture/src/architecture.c4")
_IDENTITY = (
    "-c",
    "user.name=Diagram Acceptance",
    "-c",
    "user.email=diagram@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


@dataclass(frozen=True)
class StepRun:
    returncode: int
    output: str
    failed_step: str | None


@dataclass(frozen=True)
class Pins:
    likec4: str | None
    d2: str | None


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "PRAXION_"))}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    result = subprocess.run(
        ["git", *_IDENTITY, "-c", "core.hooksPath=/dev/null", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {repo}: {result.stderr[-1200:]}")
    return result


def scratch_checkout(destination: Path) -> Path:
    """A committed copy of the repository at `destination`."""
    shutil.copytree(_template(), destination, symlinks=True)
    return destination


@functools.cache
def _template() -> Path:
    root = Path(tempfile.mkdtemp(prefix="diagram-acceptance-")) / "repo"
    atexit.register(shutil.rmtree, root.parent, True)
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    for rel in filter(None, listed):
        source = REPO_ROOT / rel
        if not source.exists() and not source.is_symlink():
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        elif source.is_file():
            shutil.copy2(source, target)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-verify", "-m", "scratch checkout")
    return root


# ── toolchain ──────────────────────────────────────────────────────────────────


def drift_gate_pins(repo: Path = REPO_ROOT) -> Pins:
    return pins_in_workflow(repo / WORKFLOW, DRIFT_JOB)


def pins_in_workflow(workflow: Path, job: str) -> Pins:
    likec4 = d2 = None
    for step in _steps(workflow, job):
        run = step.get("run") or ""
        found = re.search(r"likec4@v?([\d][\w.\-]*)", run)
        likec4 = likec4 or (found.group(1) if found else None)
        if "d2" in run and ("install" in run or "d2lang" in run):
            found = re.search(r"v?(\d+\.\d+\.\d+)", run)
            d2 = d2 or (found.group(1) if found else None)
    return Pins(likec4, d2)


def local_versions() -> Pins:
    return Pins(_version("likec4"), _version("d2"))


def require_pinned_toolchain() -> None:
    pins, local = drift_gate_pins(), local_versions()
    if local.likec4 is None or local.d2 is None:
        pytest.skip("likec4 or d2 is not installed; regeneration cannot be judged here")
    if (pins.likec4, pins.d2) != (local.likec4, local.d2):
        pytest.skip(
            f"installed toolchain {local} is not the pinned one {pins}; regeneration cannot be judged here"
        )


def _version(binary: str) -> str | None:
    path = shutil.which(binary)
    if path is None:
        return None
    result = subprocess.run(
        [path, "--version"], capture_output=True, text=True, env=offline_env(), timeout=60
    )
    found = re.findall(r"\bv?(\d+\.\d+\.\d+)\b", result.stdout + result.stderr)
    return found[-1] if found else None


# ── gates ──────────────────────────────────────────────────────────────────────


def _steps(workflow: Path, job: str) -> list[dict]:
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    return list(data["jobs"][job]["steps"])


def _installs_toolchain(step: dict) -> bool:
    run = step.get("run") or ""
    return bool(
        re.search(r"npm (install|i) |install\.sh|brew install|apt-get install|pnpm add", run)
    )


def drift_gate_steps(repo: Path) -> list[dict]:
    return [
        s for s in _steps(repo / WORKFLOW, DRIFT_JOB) if s.get("run") and not _installs_toolchain(s)
    ]


def run_steps(repo: Path, steps: list[dict]) -> StepRun:
    output = []
    for step in steps:
        result = subprocess.run(
            ["bash", "-eo", "pipefail", "-c", step["run"]],
            cwd=repo,
            env=offline_env(),
            capture_output=True,
            text=True,
            timeout=600,
        )
        output.append(result.stdout + result.stderr)
        if result.returncode != 0:
            return StepRun(
                result.returncode, "\n".join(output), step.get("name") or step["run"][:60]
            )
    return StepRun(0, "\n".join(output), None)


def run_drift_gate(repo: Path) -> StepRun:
    return run_steps(repo, drift_gate_steps(repo))


def run_drift_gate_regeneration(repo: Path) -> StepRun:
    """The drift gate's steps up to, not including, its comparison with the committed renders."""
    steps = [s for s in drift_gate_steps(repo) if not _compares_with_committed(s)]
    return run_steps(repo, steps)


def _compares_with_committed(step: dict) -> bool:
    code = "\n".join(line for line in step["run"].splitlines() if not line.strip().startswith("#"))
    return bool(re.search(r"git (diff|status)\b", code))


def changed_renders(repo: Path) -> list[str]:
    status = git(
        repo, "status", "--porcelain", "--untracked-files=all", "--", RENDER_DIR.as_posix()
    ).stdout
    return [line[3:] for line in status.splitlines()]


def precommit_entry(repo: Path) -> str:
    config = yaml.safe_load((repo / PRECOMMIT_CONFIG).read_text(encoding="utf-8"))
    for block in config.get("repos", []):
        for hook in block.get("hooks", []):
            if hook.get("id") == HOOK_ID:
                return str(hook["entry"])
    raise AssertionError(f"no `{HOOK_ID}` hook in {PRECOMMIT_CONFIG}")


def run_precommit_regeneration(
    repo: Path, path_override: str | None = None, path_prefix: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = offline_env(str(path_prefix) if path_prefix else None)
    if path_override is not None:
        env["PATH"] = path_override
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return subprocess.run(
        ["bash", "-c", precommit_entry(repo)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def staged_paths(repo: Path) -> list[str]:
    return git(repo, "diff", "--cached", "--name-only").stdout.split()


def unstaged_render_changes(repo: Path) -> list[str]:
    return git(repo, "diff", "--name-only", "--", RENDER_DIR.as_posix()).stdout.split()


def rename_developer(repo: Path, new_name: str) -> None:
    """Change the name the model gives the developer element, keeping its identity."""
    source = repo / MODEL_SOURCE
    text = source.read_text(encoding="utf-8")
    changed, count = re.subn(
        r"(\bdeveloper\s*=\s*[\w.]+\s+)(['\"])(.*?)\2", rf"\g<1>\g<2>{new_name}\g<2>", text, count=1
    )
    assert count == 1, (
        "the model no longer declares the developer element as `developer = <kind> '<name>'`"
    )
    source.write_text(changed, encoding="utf-8")
