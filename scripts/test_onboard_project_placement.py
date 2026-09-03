"""Behavioral tests for `scripts/onboard-project`'s placement surface.

RED-first (BDD/TDD): `scripts/onboard-project` does not yet parse `--placement`/
`--shadow`/`--share` as of this test's authoring. Every test below is expected
to fail -- most with `unrecognized option '--placement'` (a *wrong-reason* RED,
since the bash argument parser's `-*)` catch-all already exits 2 for any
unknown flag) until the placement flags land DS-1's gate for real. Message-content
assertions (not just exit codes) are what turns this into a *right-reason* RED
that must go GREEN for the specific behavior DS-1 and `INTERFACE_DESIGN.md`
sec. 5 describe, not merely "some flag was rejected".

Drives `scripts/onboard-project` (bash) as a real subprocess, mirroring
`tests/onboard_project_test.sh`'s sandbox pattern (stub `claude`, isolated
`HOME`/git config) translated into pytest so it participates in the
`onboarding-contract` topology group and the Integration Checkpoint's
`pytest scripts tests hooks -q` run -- a bash harness would be invisible to
both. `git` and `python3` are left un-stubbed (resolved from the real host
PATH): the sidecar CLI they delegate to (`scripts/praxion-sidecar`, DS-2's
manifest constructor, DS-10's mount lifecycle) is Praxion's own already-built,
already-tested collaborator, not an external boundary -- exercising it for
real is what "mock at boundaries only" recommends, and it is what proves
`onboard-project`'s own delegation is *correct*, not merely *attempted*.
`PRAXION_SIDECAR_ROOT` isolates every sidecar under `tmp_path`; only `claude`
is stubbed, since actually launching a session is out of scope here and
belongs to the pre-existing hand-off tests in `tests/onboard_project_test.sh`.
"""

from __future__ import annotations

import json
import os
import pty
import re
import select
import shlex
import subprocess
import time
from pathlib import Path
from typing import NamedTuple

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
SCRIPT_UNDER_TEST = SCRIPTS_DIR / "onboard-project"
SIDECAR_CLI = SCRIPTS_DIR / "praxion-sidecar"

# Isolate git from this machine's global/system config -- the same isolation
# `tests/consumer_layout/contract.py` uses, for the same reason: a developer
# with a merge driver or user.name registered at global scope must not change
# what these tests observe.
_ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

# The four section headers `INTERFACE_DESIGN.md` sec. 5.3's confirmation block
# mockup names verbatim -- the implementer may reword prose freely, but these
# are the anchors this test suite pins.
_SHADOWED = "Shadowed"
_SHARED = "Shared"
_UNTOUCHED = "Untouched"
_UNAVAILABLE = "Unavailable under sidecar placement:"
_PROCEED = "Proceed? [y/N]"
_SECTION_HEADERS = (_SHADOWED, _SHARED, _UNTOUCHED, _UNAVAILABLE, _PROCEED)


class Sandbox(NamedTuple):
    bin_dir: Path
    home_dir: Path
    claude_log: Path
    sidecar_root: Path


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    bin_dir = tmp_path / "bin"
    home_dir = tmp_path / "home"
    bin_dir.mkdir()
    (home_dir / ".claude" / "plugins").mkdir(parents=True)
    sidecar_root = tmp_path / "sidecars"
    sidecar_root.mkdir()

    claude_log = tmp_path / "claude.log"
    stub = bin_dir / "claude"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "{\n"
        "  printf 'cwd=%s\\n' \"$(pwd)\"\n"
        '  for a in "$@"; do printf \'arg=%s\\n\' "$a"; done\n'
        f"}} > {shlex.quote(str(claude_log))}\n"
        "exit 0\n"
    )
    stub.chmod(0o755)

    (home_dir / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"praxion@bit-agora": {"version": "test"}}), encoding="utf-8"
    )
    return Sandbox(
        bin_dir=bin_dir, home_dir=home_dir, claude_log=claude_log, sidecar_root=sidecar_root
    )


def _env(sandbox: Sandbox) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(sandbox.home_dir)
    env["PATH"] = f"{sandbox.bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["PRAXION_SIDECAR_ROOT"] = str(sandbox.sidecar_root)
    env.update(_ISOLATED_GIT_ENV)
    return env


def run_onboard(
    sandbox: Sandbox, cwd: Path, args: list[str], *, stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run the script under test. `stdin=""` (a closed pipe) is never a TTY --
    every call here is non-interactive unless a test opens a real pty."""
    return subprocess.run(
        ["bash", str(SCRIPT_UNDER_TEST), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=90,
        env=_env(sandbox),
        input=stdin,
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, **_ISOLATED_GIT_ENV},
    )


def existing_repo(root: Path, *, with_claude_md: bool = False) -> Path:
    """A plain existing repo -- `detect_state` resolves this to
    `git-no-praxion` / mode `existing` with no `--mode` flag needed, so it
    is DS-1's one legal `--placement sidecar` fixture."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _git(root, "remote", "add", "origin", "https://github.com/acme/billing")
    if with_claude_md:
        (root / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
        _git(root, "add", "CLAUDE.md")
        _git(root, "commit", "-q", "-m", "seed")
    return root


def hackathon_managed_repo(root: Path) -> Path:
    """Mirrors `tests/onboard_project_test.sh`'s T10 fixture: a stamp with
    `mode: hackathon` is state `hackathon-managed` regardless of what else
    `.ai-state/` holds."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / ".ai-state").mkdir()
    (root / ".ai-state" / ".praxion-onboard.json").write_text(
        json.dumps({"onboarded_with_version": "test", "mode": "hackathon"}), encoding="utf-8"
    )
    return root


def _sidecar_root_untouched(sandbox: Sandbox) -> bool:
    """True when no delegation to `praxion-sidecar init` ever landed."""
    return not any(sandbox.sidecar_root.iterdir())


def _section_text(stdout: str, header: str) -> str:
    """The block's prose for one section, up to the next known header.

    A fixed heading-to-heading window (mirroring
    `tests/consumer_layout/contract.py`'s `section()`) keeps a path assertion
    scoped to the section that actually claims it, so it cannot pass because
    the path merely appears *somewhere* in the block.
    """
    others = [h for h in _SECTION_HEADERS if h != header]
    tail = "|".join(re.escape(h) for h in others)
    match = re.search(re.escape(header) + r"(.*?)(?:" + tail + r"|\Z)", stdout, re.DOTALL)
    return match.group(1) if match else ""


def _sidecar_status(sandbox: Sandbox, repo: Path) -> dict:
    result = subprocess.run(
        ["python3", str(SIDECAR_CLI), "status", "--json"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        env=_env(sandbox),
    )
    return json.loads(result.stdout)


def _find_json_object(stdout: str, required_key: str) -> dict | None:
    """The one line of possibly-several JSON lines that carries `required_key`.

    `--json` mode also emits `print_detection`'s own
    `{"directory":...,"state":...,"mode":...}` line -- this picks the sibling
    object the placement gate emits, not the detection one.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if required_key in payload:
            return payload
    return None


# -- DS-1: `--placement sidecar` is legal only when the resolved mode is
# `existing` -- every other mode exits 2 naming the legal combination -------


def test_placement_sidecar_with_mode_new_exits_usage_error(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    target_parent = tmp_path / "fresh"
    result = run_onboard(
        sandbox,
        tmp_path,
        ["my-app", str(target_parent), "--mode", "new", "--placement", "sidecar"],
    )
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "existing" in result.stderr.lower()
    assert "sidecar" in result.stderr.lower()
    assert _sidecar_root_untouched(sandbox)


def test_placement_sidecar_with_mode_hackathon_exits_usage_error(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    cwd = tmp_path / "any-dir"
    cwd.mkdir()
    result = run_onboard(sandbox, cwd, ["--hackathon", "--placement", "sidecar"])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "existing" in result.stderr.lower()
    assert _sidecar_root_untouched(sandbox)


def test_placement_sidecar_with_mode_promote_exits_usage_error(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    cwd = tmp_path / "any-dir"
    cwd.mkdir()
    result = run_onboard(sandbox, cwd, ["--mode", "promote", "--placement", "sidecar"])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "existing" in result.stderr.lower()
    assert _sidecar_root_untouched(sandbox)


def test_placement_sidecar_with_full_flag_resolving_to_promote_exits_usage_error(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """`--full` on a hackathon-managed project resolves to mode `promote` --
    the fourth illegal pair, reached through a different flag than `--mode
    promote` but the same resolved-mode outcome."""
    repo = hackathon_managed_repo(tmp_path / "hackathon-project")
    result = run_onboard(sandbox, repo, ["--full", "--placement", "sidecar"])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "existing" in result.stderr.lower()
    assert _sidecar_root_untouched(sandbox)


def test_placement_sidecar_with_default_existing_mode_is_legal(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """The one legal pair: no `--mode` needed, since a plain existing repo
    already resolves to mode `existing` by default."""
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--yes", "--no-launch"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert not _sidecar_root_untouched(sandbox), "praxion-sidecar init was never delegated to"
    assert (repo / ".praxion").is_dir()
    assert (repo / ".praxion" / ".git").exists()
    assert (repo / ".ai-state").is_symlink()


# -- Unrecognized placement value ---------------------------------------------


def test_unrecognized_placement_value_exits_usage_error(sandbox: Sandbox, tmp_path: Path) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--placement", "bogus"])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert _sidecar_root_untouched(sandbox)


# -- Composition rules (INTERFACE_DESIGN.md sec. 5.1) -------------------------


def test_shadow_without_placement_sidecar_exits_usage_error(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--shadow", ".ai-state"])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "no meaning" in result.stderr.lower()
    assert "--placement sidecar" in result.stderr
    assert _sidecar_root_untouched(sandbox)


def test_share_without_placement_sidecar_exits_usage_error(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--share", "docs/architecture.md"])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert _sidecar_root_untouched(sandbox)


def test_same_path_to_shadow_and_share_exits_usage_error_naming_the_path(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(
        sandbox,
        repo,
        [
            "--placement",
            "sidecar",
            "--shadow",
            "docs/architecture.md",
            "--share",
            "docs/architecture.md",
            "--yes",
            "--no-launch",
        ],
    )
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "docs/architecture.md" in result.stderr


def test_shadow_of_a_non_allowlisted_path_exits_usage_error_naming_the_path(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """D8's allowlist -- `_sidecar_manifest.py`'s smart constructor refuses a
    `--shadow` path that is not one of the shadowable defaults."""
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(
        sandbox, repo, ["--placement", "sidecar", "--shadow", "src/", "--yes", "--no-launch"]
    )
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "src/" in result.stderr


def test_shadow_of_dot_claude_is_refused_on_safety_grounds(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """Claude Code refuses to create a worktree when `.claude/` is a symlink --
    a distinct, safety-grounds refusal (exit 3) from the generic allowlist
    usage error (exit 2) above."""
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(
        sandbox, repo, ["--placement", "sidecar", "--shadow", ".claude", "--yes", "--no-launch"]
    )
    assert result.returncode == 3, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "worktree" in result.stderr.lower()


# -- Confirmation block (INTERFACE_DESIGN.md sec. 5.3) -------------------------


def test_confirmation_block_renders_on_non_tty_stdin_and_proceeds_without_hanging(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """D9: a non-TTY stdin prints the identical block and proceeds without
    the prompt -- never blocks a pipe."""
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--no-launch"], stdin="")
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    for header in (_SHADOWED, _SHARED, _UNAVAILABLE):
        assert header in result.stdout, f"missing section {header!r} in:\n{result.stdout}"
    assert "ci" in _section_text(result.stdout, _UNAVAILABLE)
    assert not _sidecar_root_untouched(sandbox)


def test_yes_flag_renders_the_same_block_and_proceeds(sandbox: Sandbox, tmp_path: Path) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--yes", "--no-launch"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert _SHADOWED in result.stdout
    assert not _sidecar_root_untouched(sandbox)


def test_quiet_suppresses_the_block_but_not_the_gate(sandbox: Sandbox, tmp_path: Path) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(
        sandbox, repo, ["--placement", "sidecar", "--yes", "--quiet", "--no-launch"]
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert _SHADOWED not in result.stdout
    assert not _sidecar_root_untouched(sandbox), "the gate itself must still run under --quiet"


def test_json_mode_emits_the_placement_object_and_implies_yes(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--json", "--no-launch"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    payload = _find_json_object(result.stdout, "placement")
    assert payload is not None, f"no placement JSON object found in:\n{result.stdout!r}"
    assert payload["placement"] == "sidecar"
    assert "ci" in payload["unavailable"]
    assert not _sidecar_root_untouched(sandbox), "--json must imply --yes, not just describe"


def test_confirmation_block_lists_a_preexisting_claude_md_as_untouched(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing", with_claude_md=True)
    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--yes", "--no-launch"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "CLAUDE.md" in _section_text(result.stdout, _UNTOUCHED)


def test_confirmation_block_shadows_claude_md_by_default_when_absent(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")  # no CLAUDE.md committed
    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--yes", "--no-launch"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    shadowed = _section_text(result.stdout, _SHADOWED)
    assert "CLAUDE.md" in shadowed
    assert "--share CLAUDE.md" in shadowed


def test_share_claude_md_flag_moves_it_to_the_shared_section(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")  # no CLAUDE.md committed
    result = run_onboard(
        sandbox,
        repo,
        ["--placement", "sidecar", "--share", "CLAUDE.md", "--yes", "--no-launch"],
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "CLAUDE.md" in _section_text(result.stdout, _SHARED)
    assert "CLAUDE.md" not in _section_text(result.stdout, _SHADOWED)


def test_shadow_docs_architecture_flips_it_out_of_the_default_shared_section(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(
        sandbox,
        repo,
        ["--placement", "sidecar", "--shadow", "docs/architecture.md", "--yes", "--no-launch"],
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "docs/architecture.md" in _section_text(result.stdout, _SHADOWED)
    assert "docs/architecture.md" not in _section_text(result.stdout, _SHARED)


def test_confirmation_block_renders_before_the_delegated_write_even_when_it_fails(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """A foreign real directory already occupying `.praxion` makes the
    delegated `praxion-sidecar init` refuse (DS-10's never-reclaim invariant).
    The block must still have printed -- proving it renders before, not as
    part of, the write it describes -- and nothing must have been committed
    to the sidecar root."""
    repo = existing_repo(tmp_path / "billing")
    (repo / ".praxion").mkdir()
    (repo / ".praxion" / "not-a-worktree.txt").write_text("occupied", encoding="utf-8")

    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--yes", "--no-launch"])

    assert result.returncode != 0, "a foreign .praxion must not be silently reclaimed"
    assert _SHADOWED in result.stdout, "the block must render even when delegation fails"
    assert _sidecar_root_untouched(sandbox), "a failed delegation must not leave sidecar state"


def test_confirmation_prompts_on_a_real_tty_and_proceeds_on_yes(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """On an actual terminal (not a pipe), the block ends with the literal
    `Proceed? [y/N]` prompt and answering `y` proceeds."""
    repo = existing_repo(tmp_path / "billing")
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        ["bash", str(SCRIPT_UNDER_TEST), "--placement", "sidecar", "--no-launch"],
        cwd=repo,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=_env(sandbox),
        close_fds=True,
    )
    os.close(slave_fd)
    output = b""
    sent = False
    deadline = time.time() + 60
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 1.0)
            if master_fd in ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
                if not sent and _PROCEED.encode() in output:
                    os.write(master_fd, b"y\n")
                    sent = True
            if proc.poll() is not None:
                break
    finally:
        os.close(master_fd)
    proc.wait(timeout=30)

    text = output.decode(errors="replace")
    assert sent, f"prompt {_PROCEED!r} never appeared in:\n{text}"
    assert proc.returncode == 0, f"exit={proc.returncode} output:\n{text}"


def test_quiet_still_prompts_on_a_real_tty_even_though_the_block_is_suppressed(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """`--quiet` on a real TTY without `--yes` must still print the literal
    `Proceed? [y/N]` prompt (INTERFACE_DESIGN.md sec 5.3: "--quiet suppresses
    the block but not the prompt") -- reuses the pty harness above, adding
    --quiet and omitting --yes, and asserts the descriptive block's own
    section headers never appear while the prompt still does."""
    repo = existing_repo(tmp_path / "billing")
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        ["bash", str(SCRIPT_UNDER_TEST), "--placement", "sidecar", "--quiet", "--no-launch"],
        cwd=repo,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=_env(sandbox),
        close_fds=True,
    )
    os.close(slave_fd)
    output = b""
    sent = False
    deadline = time.time() + 60
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 1.0)
            if master_fd in ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output += chunk
                if not sent and _PROCEED.encode() in output:
                    os.write(master_fd, b"y\n")
                    sent = True
            if proc.poll() is not None:
                break
    finally:
        os.close(master_fd)
    proc.wait(timeout=30)

    text = output.decode(errors="replace")
    assert sent, f"prompt {_PROCEED!r} never appeared under --quiet in:\n{text}"
    assert _SHADOWED not in text, f"--quiet must suppress the descriptive block:\n{text}"
    assert proc.returncode == 0, f"exit={proc.returncode} output:\n{text}"


# -- In-repo default (no `--placement`) ---------------------------------------


def test_no_placement_flag_never_touches_the_sidecar_or_renders_the_block(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    result = run_onboard(sandbox, repo, ["--yes", "--no-launch"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert _SHADOWED not in result.stdout
    assert _UNAVAILABLE not in result.stdout
    assert not (repo / ".praxion").exists()
    assert _sidecar_root_untouched(sandbox)


# -- Re-onboard: placement is read from the manifest, never re-asked ---------


def test_reonboard_reads_placement_from_the_manifest_and_refuses_a_contradiction(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    first = run_onboard(sandbox, repo, ["--placement", "sidecar", "--yes", "--no-launch"])
    assert first.returncode == 0, (
        f"setup run failed: stdout={first.stdout!r} stderr={first.stderr!r}"
    )

    contradicting = run_onboard(sandbox, repo, ["--placement", "in-repo"])
    assert contradicting.returncode == 3, (
        f"stdout={contradicting.stdout!r} stderr={contradicting.stderr!r}"
    )
    assert "praxion-sidecar publish" in contradicting.stderr

    silent = run_onboard(sandbox, repo, ["--yes", "--no-launch"])
    assert silent.returncode == 0, f"stdout={silent.stdout!r} stderr={silent.stderr!r}"
    assert _PROCEED not in silent.stdout, "an already-established placement must not re-prompt"


# -- IF-01: `--check` is a dry-run by contract -- prints the plan, delegates
# nothing (no `praxion-sidecar init`, no `.praxion`, `git status` unchanged) --


def test_placement_sidecar_check_prints_the_block_and_delegates_nothing(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")
    status_before = _git_status(repo)

    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--check"])

    assert result.returncode == 8, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    for header in (_SHADOWED, _SHARED, _UNAVAILABLE):
        assert header in result.stdout, f"missing section {header!r} in:\n{result.stdout}"
    assert _PROCEED not in result.stdout, "--check must never prompt for confirmation"
    assert _sidecar_root_untouched(sandbox), "--check must never delegate to praxion-sidecar init"
    assert not (repo / ".praxion").exists(), "--check must never materialize the mount"
    assert _git_status(repo) == status_before, "--check must never mutate the target repo"


def test_placement_sidecar_check_json_emits_the_plan_and_delegates_nothing(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = existing_repo(tmp_path / "billing")

    result = run_onboard(sandbox, repo, ["--placement", "sidecar", "--check", "--json"])

    assert result.returncode == 8, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    payload = _find_json_object(result.stdout, "placement")
    assert payload is not None, f"no placement JSON object found in:\n{result.stdout!r}"
    assert payload["placement"] == "sidecar"
    assert _sidecar_root_untouched(sandbox), "--check --json must never delegate"
    assert not (repo / ".praxion").exists()


def _git_status(repo: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, **_ISOLATED_GIT_ENV},
    )
    return result.stdout


# -- --help ---------------------------------------------------------------


def test_help_lists_the_three_placement_flags_under_a_placement_heading(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    result = run_onboard(sandbox, tmp_path, ["--help"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "PLACEMENT" in result.stdout
    section = result.stdout.split("PLACEMENT", 1)[1]
    assert "--placement" in section
    assert "--shadow" in section
    assert "--share" in section
