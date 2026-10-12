"""Gate-liveness canaries for the commit-gate's Rust branch.

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
below prove that branch actually inspects staged `.rs` files rather than
only ever looking at staged `.py` files.

Drives the fake `rustfmt` via a PATH shim (PM-2) rather than a real Rust
toolchain, so these canaries run -- and bite -- on any machine. Staging
happens in a throwaway git repo built at runtime under `tmp_path`, never
this repo's own index.

The Python partial-staging tests at the end pin the other half of the gate: a
file staged only in part is never re-staged (which once swept its unstaged
changes into commits) and is judged by its staged blob. A fake `ruff` on the
same PATH shim drives them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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

    Proves the gate actually scans staged `.rs` files rather than only
    `.py` files, by driving the `rustfmt --check` invocation via a fake
    binary that always reports a formatting violation.
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
    "exit 0" alone would not distinguish a real skip from the gate never
    looking at `.rs` files at all, so the stderr assertion is what proves
    the skip was deliberate.
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


# ---------------------------------------------------------------------------
# gate_fire observations
#
# Requirement 2: one gate_fire row per commit, on both the pass and the block
# path. Requirement 1: a helper exception must never change the gate's own
# exit code, on either path.
# ---------------------------------------------------------------------------


def _read_gate_fire_rows(repo_dir: Path) -> list[dict]:
    obs_path = repo_dir / ".ai-state" / "observations.jsonl"
    if not obs_path.exists():
        return []
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]


def test_gate_fire_row_on_pass(tmp_path: Path) -> None:
    """A clean commit (no staged Python/Rust files) records outcome=pass.

    `.ai-state/` lives under the hermetic tmp_path repo used as the subprocess
    cwd -- never the live Praxion WAL.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    (repo_dir / ".ai-state").mkdir()
    _stage_file(repo_dir, "README.md", "hello\n")

    result = _run_hook(_commit_payload(), cwd=repo_dir, env={"PATH": _controlled_path()})

    assert result.returncode == 0
    rows = _read_gate_fire_rows(repo_dir)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "gate_fire"
    assert rows[0]["tool_name"] == "check_code_quality"
    assert rows[0]["outcome"] == "pass"


def test_gate_fire_row_on_block(tmp_path: Path) -> None:
    """A staged badly-formatted .rs file (blocked commit) records outcome=block."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    (repo_dir / ".ai-state").mkdir()
    _stage_file(repo_dir, "src/lib.rs", BADLY_FORMATTED_RUST)

    bin_dir = tmp_path / "bin"
    _write_fake_rustfmt(bin_dir, script=FAKE_RUSTFMT_CHECK_REJECTS_SCRIPT)

    result = _run_hook(_commit_payload(), cwd=repo_dir, env={"PATH": _controlled_path(bin_dir)})

    assert result.returncode == 2
    rows = _read_gate_fire_rows(repo_dir)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "block"


def _load_gate_module():
    """Load check_code_quality.py fresh, for in-process exception-injection tests."""
    import importlib.util

    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location("check_code_quality", HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raise(*_args, **_kwargs):
    raise RuntimeError("boom")


def test_helper_exception_does_not_change_exit_code_on_pass(tmp_path: Path, monkeypatch) -> None:
    import io

    module = _load_gate_module()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    _stage_file(repo_dir, "README.md", "hello\n")
    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_commit_payload())))

    module.main()  # must not raise, and must not sys.exit (blocked=False)


def test_helper_exception_does_not_change_exit_code_on_block(tmp_path: Path, monkeypatch) -> None:
    import io

    module = _load_gate_module()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    _stage_file(repo_dir, "src/lib.rs", BADLY_FORMATTED_RUST)
    bin_dir = tmp_path / "bin"
    _write_fake_rustfmt(bin_dir, script=FAKE_RUSTFMT_CHECK_REJECTS_SCRIPT)
    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("PATH", _controlled_path(bin_dir))
    monkeypatch.setattr(module, "record_gate_fire", _raise)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_commit_payload())))

    with pytest.raises(SystemExit) as exc_info:
        module.main()
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Partially staged Python files: the gate never sweeps unstaged changes into
# the commit, and it judges the staged content -- the bytes being committed --
# rather than the working-tree copy.
# ---------------------------------------------------------------------------

# A fake `ruff` driven by content markers. `format <files>` rewrites each file
# (the auto-fix); any check -- on files or on stdin -- fails when the content it
# examines contains BAD. Every invocation is logged to $FAKE_RUFF_LOG.
FAKE_RUFF_SCRIPT = """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
log = os.environ.get("FAKE_RUFF_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args) + "\\n")
files = [a for a in args[1:] if not a.startswith("-")]
if "-" in args:
    sys.exit(1 if "BAD" in sys.stdin.read() else 0)
if args[:1] == ["format"] and "--check" not in args:
    for path in files:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("formatted = True\\n")
    sys.exit(0)
if args[:1] == ["check"] and "--fix" in args:
    sys.exit(0)
for path in files:
    with open(path, encoding="utf-8") as handle:
        if "BAD" in handle.read():
            sys.exit(1)
sys.exit(0)
"""


def _python_repo(tmp_path: Path, *, staged: str, working: str) -> tuple[Path, dict[str, str]]:
    """A repo where `a.py` is staged as `staged` while its working tree holds `working`."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_repo(repo_dir)
    _stage_file(repo_dir, "a.py", "x = 0\n")
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo_dir, check=True)
    _stage_file(repo_dir, "a.py", staged)
    (repo_dir / "a.py").write_text(working, encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "ruff"
    fake.write_text(FAKE_RUFF_SCRIPT, encoding="utf-8")
    fake.chmod(0o755)
    env = {"PATH": _controlled_path(bin_dir), "FAKE_RUFF_LOG": str(tmp_path / "ruff.log")}
    return repo_dir, env


def _staged_text(repo_dir: Path, path: str) -> str:
    return subprocess.run(
        ["git", "show", f":{path}"], cwd=repo_dir, capture_output=True, text=True, check=True
    ).stdout


def test_partially_staged_python_keeps_its_unstaged_changes_out_of_the_index(
    tmp_path: Path,
) -> None:
    """CANARY: the hook used to `git add` the working-tree copy of every staged file,
    committing a partially staged file's unstaged changes along with it."""
    repo_dir, env = _python_repo(tmp_path, staged="x = 1\n", working="x = 2\n")

    result = _run_hook(_commit_payload(), cwd=repo_dir, env=env)

    assert result.returncode == 0, result.stderr
    assert _staged_text(repo_dir, "a.py") == "x = 1\n", "unstaged changes were swept into the index"
    assert (repo_dir / "a.py").read_text(encoding="utf-8") == "x = 2\n", (
        "the working-tree copy of a partially staged file must not be rewritten"
    )


def test_partially_staged_python_is_judged_by_its_staged_content(tmp_path: Path) -> None:
    """Unformatted staged content blocks even when the working tree is clean."""
    repo_dir, env = _python_repo(tmp_path, staged="BAD = 1\n", working="x = 2\n")

    result = _run_hook(_commit_payload(), cwd=repo_dir, env=env)

    assert result.returncode == 2, result.stderr
    assert "a.py" in result.stderr


def test_partially_staged_python_ignores_problems_only_in_the_working_tree(
    tmp_path: Path,
) -> None:
    """An unformatted working-tree copy does not block a commit of clean staged content."""
    repo_dir, env = _python_repo(tmp_path, staged="x = 1\n", working="BAD = 2\n")

    result = _run_hook(_commit_payload(), cwd=repo_dir, env=env)

    assert result.returncode == 0, result.stderr


def test_fully_staged_python_is_still_auto_fixed_and_restaged(tmp_path: Path) -> None:
    """A file whose working tree matches the index keeps the auto-fix-and-restage path."""
    repo_dir, env = _python_repo(tmp_path, staged="x = 1\n", working="x = 1\n")

    result = _run_hook(_commit_payload(), cwd=repo_dir, env=env)

    assert result.returncode == 0, result.stderr
    assert _staged_text(repo_dir, "a.py") == "formatted = True\n", "the auto-fix was not re-staged"
