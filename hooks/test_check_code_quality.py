"""Gate-liveness canaries for the commit-gate's future Rust branch.

Cites: `rules/swe/gate-liveness.md` -- every CODE gate ships a sibling canary
proving it fails on a known-bad input, not merely passes on the current good
state. `hooks/check_code_quality.py` has no prior test file (verified: only
`test_commit_gate.py` exists, which tests the `commit_gate.sh` shell wrapper,
a different surface).

Per PM-3 (`WIP.md` Pre-Mortem, binding, deviates from the original plan
deliberately): the Rust branch runs `rustfmt --edition <resolved> --check
<staged .rs files>` via the `_lang_tools` registry -- staged-file-scoped,
never `cargo fmt --all` -- and must exit 0 (never block) when `rustfmt` is
unresolvable, in parity with the existing ruff-absent behavior. Both canaries
below are expected RED until Step 4 wires the branch: today the gate only
ever looks at staged `.py` files, so an all-Rust commit is never even
inspected.

Drives the fake `rustfmt` via a PATH shim (PM-2) rather than a real Rust
toolchain, so these canaries run -- and bite -- on any machine. Staging
happens in a throwaway git repo built at runtime under `tmp_path`, never
this repo's own index.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_PATH = HOOKS_DIR / "check_code_quality.py"

BADLY_FORMATTED_RUST = "fn foo(x:i32,y:i32)->i32{x+y}\n"

# A fake `rustfmt --check` that always reports a formatting violation,
# regardless of file content -- this canary only needs to prove the gate
# reacts to a nonzero rustfmt exit, not to actually parse Rust source.
FAKE_RUSTFMT_CHECK_REJECTS_SCRIPT = """#!/usr/bin/env python3
import sys

sys.exit(1)
"""


def _write_fake_rustfmt(bin_dir: Path, *, script: str) -> None:
    """Stage an executable fake `rustfmt` at `bin_dir/rustfmt`."""
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "rustfmt"
    fake.write_text(script, encoding="utf-8")
    fake.chmod(0o755)


def _controlled_path(*extra_dirs: Path) -> str:
    """Build a minimal, deterministic PATH: `extra_dirs` + git + python3.

    Excludes every other PATH entry -- including any real `rustfmt` the host
    machine happens to have installed -- so "rustfmt is unresolvable" is
    guaranteed by construction, not by hoping the test runner has no Rust
    toolchain.
    """
    git_path = shutil.which("git")
    python_path = shutil.which("python3") or sys.executable
    assert git_path, "git must be on PATH to run this test suite"
    dirs = [str(d) for d in extra_dirs]
    dirs.append(str(Path(git_path).parent))
    dirs.append(str(Path(python_path).parent))
    return os.pathsep.join(dirs)


def _init_repo(repo_dir: Path) -> None:
    """Initialize a throwaway git repo with local (not global) identity."""
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)


def _stage_file(repo_dir: Path, relative_path: str, content: str) -> Path:
    """Write `relative_path` under `repo_dir` and stage it (`git add`)."""
    target = repo_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relative_path], cwd=repo_dir, check=True)
    return target


def _commit_payload(message: str = "test commit") -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": f"git commit -m '{message}'"}}


def _run_hook(payload: dict, *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Invoke the commit-quality-gate hook as a subprocess, staged repo as cwd."""
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=15,
    )


def test_rejects_a_staged_badly_formatted_rust_file(tmp_path: Path) -> None:
    """A staged, badly-formatted `.rs` file blocks the commit (exit 2).

    Expected RED until Step 4 lands: today the gate only scans staged `.py`
    files, so a Rust-only staged commit passes with exit 0, never reaching
    the `rustfmt --check` invocation this canary drives via a fake binary.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    _stage_file(repo_dir, "src/lib.rs", BADLY_FORMATTED_RUST)

    bin_dir = tmp_path / "bin"
    _write_fake_rustfmt(bin_dir, script=FAKE_RUSTFMT_CHECK_REJECTS_SCRIPT)
    env = {"PATH": _controlled_path(bin_dir)}

    result = _run_hook(_commit_payload(), cwd=repo_dir, env=env)

    assert result.returncode == 2, (
        "a staged badly-formatted .rs file must block the commit once the "
        f"Rust branch lands; stdout={result.stdout!r}, stderr={result.stderr!r}"
    )


def _fake_rustfmt_record_argv_script(log_path: Path) -> str:
    """A fake `rustfmt` that appends its argv (minus argv[0]) to `log_path` and exits 0."""
    return f"""#!/usr/bin/env python3
import sys
from pathlib import Path

Path({str(log_path)!r}).open("a", encoding="utf-8").write(" ".join(sys.argv[1:]) + "\\n")
sys.exit(0)
"""


def test_groups_staged_rust_files_by_resolved_edition(tmp_path: Path) -> None:
    """Staged files from crates on different editions are checked in separate groups.

    Expected RED before the mixed-edition fix: the gate resolved `--edition`
    from `rs_files[0]` alone and applied that single edition to every staged
    file, so one of the two crates below would have been checked under the
    other's edition.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)

    _stage_file(
        repo_dir,
        "crates/legacy/Cargo.toml",
        '[package]\nname = "legacy"\nedition = "2021"\n',
    )
    _stage_file(repo_dir, "crates/legacy/src/lib.rs", BADLY_FORMATTED_RUST)
    _stage_file(
        repo_dir,
        "crates/new/Cargo.toml",
        '[package]\nname = "new"\nedition = "2024"\n',
    )
    _stage_file(repo_dir, "crates/new/src/lib.rs", BADLY_FORMATTED_RUST)

    bin_dir = tmp_path / "bin"
    log_path = tmp_path / "rustfmt-invocations.log"
    _write_fake_rustfmt(bin_dir, script=_fake_rustfmt_record_argv_script(log_path))
    env = {"PATH": _controlled_path(bin_dir)}

    result = _run_hook(_commit_payload(), cwd=repo_dir, env=env)

    assert result.returncode == 0, (
        "the fake rustfmt always exits 0, so the gate must never block; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )

    invocations = log_path.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 2, (
        f"expected one rustfmt invocation per resolved edition group; got {invocations!r}"
    )

    def _edition_for(file_suffix: str) -> str:
        for line in invocations:
            if file_suffix in line:
                args = line.split()
                return args[args.index("--edition") + 1]
        raise AssertionError(f"no invocation checked {file_suffix}; invocations={invocations!r}")

    assert _edition_for("crates/legacy/src/lib.rs") == "2021"
    assert _edition_for("crates/new/src/lib.rs") == "2024"


def test_silently_passes_when_rustfmt_is_unresolvable(tmp_path: Path) -> None:
    """A staged `.rs` file with no `rustfmt` on PATH never blocks the commit.

    Parity with the existing ruff-absent behavior (PM-3): the gate must
    still surface that it attempted (and skipped) the Rust check -- a bare
    "exit 0" is also true of today's code, which never looks at `.rs` files
    at all, so the stderr assertion is what makes this canary RED rather
    than vacuously green before Step 4 lands.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    _stage_file(repo_dir, "src/lib.rs", BADLY_FORMATTED_RUST)

    env = {"PATH": _controlled_path()}

    result = _run_hook(_commit_payload(), cwd=repo_dir, env=env)

    assert result.returncode == 0, "an unresolvable rustfmt must never block the commit"
    assert "rustfmt" in result.stderr.lower(), (
        "the gate must report that it checked for (and could not resolve) "
        f"rustfmt, parity with the ruff-absent log; stderr={result.stderr!r}"
    )
