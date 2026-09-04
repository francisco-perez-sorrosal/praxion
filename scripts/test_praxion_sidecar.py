"""Behavioral tests for `praxion-sidecar` -- the CLI face of sidecar
placement (`INTERFACE_DESIGN.md` sec. 2-4, 7; `ARCH_WT_RULING.md` sec. 5-6).

`scripts/praxion-sidecar` does not exist yet (concurrent BDD/TDD with its
implementation) -- this is the RED skeleton, confirmed to fail because the
file is absent before the CLI lands (recorded in `TEST_RESULTS.md`).

This is a pure black-box suite: every test drives the CLI as a real
subprocess (`sys.executable`, the script's path, `capture_output=True`)
against real `tmp_path` git repositories, and asserts on exit codes,
stdout/stderr text, and on-disk state -- never on the internal
`_sidecar_manifest.py` / `_sidecar_mount.py` / `_sidecar_link.py` /
`_sidecar_commit.py` / `_sidecar_checks.py` APIs those modules already
cover from the inside (`scripts/test_sidecar_*.py`). Fixtures build up
state through the CLI itself (`init` then a later verb), matching how an
operator actually uses it.

This section covers the five core verbs: `init`, `link`, `status`,
`doctor`, `commit`. `merge-back` / `publish` / `absorb` / `remote` are out
of scope here -- see the second section below.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_CLI = Path(__file__).resolve().parent / "praxion-sidecar"

_ORIGIN_ID = "github.com--acme--billing"

# Isolate git from this machine's global/system config for the identity
# tests below -- the same isolation `test_onboard_project_placement.py` uses,
# for the same reason: a developer with `user.name` registered at global
# scope must not change what those tests observe.
_ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}
_IDENTITY_ENV_VARS = (
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
)


# --- git plumbing ------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _configure_identity(repo: Path) -> None:
    _git_ok(repo, "config", "user.email", "test@example.com")
    _git_ok(repo, "config", "user.name", "Test")


def _init_project_repo(root: Path, *, origin: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git_ok(root, "init", "-q", "-b", "main")
    _configure_identity(root)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    _git_ok(root, "add", "README.md")
    _git_ok(root, "commit", "-q", "-m", "seed")
    if origin is not None:
        _git_ok(root, "remote", "add", "origin", origin)


def _fs_snapshot(root: Path) -> dict[str, tuple[str, ...]]:
    """A structural snapshot of every path under `root`, excluding the
    project's own `.git` and the sidecar mount `.praxion-state` (whose *internal*
    git bookkeeping is not this suite's concern). Real files/dirs are keyed
    by `(mtime_ns, inode)`; symlinks by their raw target -- so a `link()`
    re-run that reads-then-no-ops is distinguishable from one that
    unlinks-and-relinks to the same target.
    """
    snapshot: dict[str, tuple[str, ...]] = {}
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if parts[0] in (".git", ".praxion-state"):
            continue
        rel = str(path.relative_to(root))
        if path.is_symlink():
            snapshot[rel] = ("symlink", os.readlink(path))
        else:
            st = path.lstat()
            snapshot[rel] = ("real", str(st.st_mtime_ns), str(st.st_ino))
    return snapshot


# --- CLI invocation ------------------------------------------------------------


def run_cli(
    args: list[str], cwd: Path, env: dict[str, str], extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = dict(env)
    if extra_env:
        full_env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(_CLI), *args],
        cwd=str(cwd),
        env=full_env,
        capture_output=True,
        text=True,
    )


def _init_ok(
    project: Path, env: dict[str, str], *extra_args: str
) -> subprocess.CompletedProcess[str]:
    result = run_cli(["init", *extra_args], project, env)
    assert result.returncode == 0, result.stderr
    return result


# --- fixtures ------------------------------------------------------------


@pytest.fixture
def sidecar_root(tmp_path: Path) -> Path:
    return tmp_path / "sidecars"


@pytest.fixture
def cli_env(sidecar_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PRAXION_SIDECAR_ROOT"] = str(sidecar_root)
    env["NO_COLOR"] = "1"
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        env[var] = "Test"
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        env[var] = "test@example.com"
    return env


@pytest.fixture
def origin_project(tmp_path: Path) -> Path:
    root = tmp_path / "billing"
    _init_project_repo(root, origin="https://github.com/acme/billing")
    return root


@pytest.fixture
def local_project(tmp_path: Path) -> Path:
    root = tmp_path / "scratch"
    _init_project_repo(root)
    return root


@pytest.fixture
def project_with_claude_md(tmp_path: Path) -> Path:
    root = tmp_path / "billing-team"
    _init_project_repo(root, origin="https://github.com/acme/billing-team")
    (root / "CLAUDE.md").write_text("# Team instructions\n", encoding="utf-8")
    _git_ok(root, "add", "CLAUDE.md")
    _git_ok(root, "commit", "-q", "-m", "add CLAUDE.md")
    return root


@pytest.fixture
def network_guarded_git(tmp_path: Path) -> tuple[Path, Path]:
    """A `git` shim on its own PATH entry that logs every invocation and
    refuses (exit 99, before delegating) any network subcommand -- proves
    `doctor` never reaches for the network rather than merely asserting the
    exit code came back clean, which a silently-swallowed failure could
    also produce.
    """
    real_git = shutil.which("git")
    assert real_git is not None, "git must be on PATH to build the guarded shim"
    bin_dir = tmp_path / "guarded-bin"
    bin_dir.mkdir()
    log_path = tmp_path / "git-calls.log"
    wrapper = bin_dir / "git"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "git $*" >> "{log_path}"\n'
        'case "$1" in\n'
        "  fetch|pull|ls-remote|push)\n"
        '    echo "REFUSED: network git command invoked: git $*" >&2\n'
        "    exit 99\n"
        "    ;;\n"
        "esac\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return bin_dir, log_path


def _manifest(sidecar_root: Path, sidecar_id: str) -> dict:
    path = sidecar_root / sidecar_id / ".git" / "praxion-sidecar.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --- --help / usage ------------------------------------------------------------


def test_help_exits_zero_and_lists_all_eight_verbs(tmp_path: Path, cli_env: dict[str, str]) -> None:
    result = run_cli(["--help"], tmp_path, cli_env)
    assert result.returncode == 0, result.stderr
    for verb in ("init", "link", "status", "doctor", "commit", "publish", "absorb", "remote"):
        assert verb in result.stdout


def test_help_includes_examples_section_and_exit_codes_block(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["--help"], tmp_path, cli_env)
    assert result.returncode == 0, result.stderr
    assert "EXAMPLES" in result.stdout
    assert "EXIT CODES" in result.stdout
    assert "refused on safety grounds" in result.stdout


def test_help_ends_with_the_truthful_autocommit_sentence(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    # `publish` really does commit to the project repo (its history import),
    # so the closing sentence names that one exception rather than denying it.
    result = run_cli(["--help"], tmp_path, cli_env)
    assert result.returncode == 0, result.stderr
    assert "Only the sidecar autocommits;" in result.stdout
    assert "the one project commit Praxion ever makes is publish's" in result.stdout
    assert "history import, and it asks first." in result.stdout


def test_unknown_verb_exits_usage_error_with_short_usage_on_stderr(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["frobnicate"], tmp_path, cli_env)
    assert result.returncode == 2
    assert (
        "Usage: praxion-sidecar {init|link|status|doctor|commit|merge-back|publish|absorb|remote}"
        in result.stderr
    )
    assert "Run 'praxion-sidecar --help' for examples and the full option reference." in (
        result.stderr
    )


def test_unknown_flag_exits_usage_error(tmp_path: Path, cli_env: dict[str, str]) -> None:
    result = run_cli(["status", "--bogus-flag"], tmp_path, cli_env)
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_json_flag_on_init_is_a_usage_error(origin_project: Path, cli_env: dict[str, str]) -> None:
    result = run_cli(["init", "--json"], origin_project, cli_env)
    assert result.returncode == 2
    assert "Usage:" in result.stderr


# --- init: happy path ------------------------------------------------------------


def test_init_creates_a_git_sidecar_with_seed_commit_and_detached_head(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = run_cli(["init"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    sidecar = sidecar_root / _ORIGIN_ID
    assert sidecar.is_dir()
    assert (sidecar / ".git").exists()

    log = _git_ok(sidecar, "log", "main", "--oneline").stdout
    assert log.strip() != ""

    head = _git_ok(sidecar, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert head == "HEAD"  # detached -- `main` is free for the mount to claim


def test_init_writes_manifest_with_schema_and_recorded_identity(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    manifest = _manifest(sidecar_root, _ORIGIN_ID)

    assert manifest["schema"] == 1
    assert manifest["project"]["origin"] == "https://github.com/acme/billing"
    assert manifest["project"]["id"] == _ORIGIN_ID
    assert str(origin_project.resolve()) in manifest["project"]["roots"]
    assert manifest["paths"][".ai-state"]["intent"] == "shadow"
    assert manifest["paths"]["CLAUDE.local.md"]["intent"] == "shadow"
    assert manifest["paths"][".claude/settings.local.json"]["intent"] == "shadow"
    assert manifest["paths"]["docs/architecture.md"]["intent"] == "share"


def test_init_shadows_claude_md_when_project_has_none(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    manifest = _manifest(sidecar_root, _ORIGIN_ID)
    assert manifest["paths"]["CLAUDE.md"]["intent"] == "shadow"


def test_init_leaves_a_preexisting_claude_md_untouched(
    project_with_claude_md: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = run_cli(["init"], project_with_claude_md, cli_env)
    assert result.returncode == 0, result.stderr

    manifest = _manifest(sidecar_root, "github.com--acme--billing-team")
    entry = manifest["paths"]["CLAUDE.md"]
    assert entry["intent"] == "untouched"
    assert entry["reason"] == "preexisting-team-file"

    # Never touched: the file's content and tracked status stay exactly
    # what the operator committed.
    assert (project_with_claude_md / "CLAUDE.md").read_text(encoding="utf-8") == (
        "# Team instructions\n"
    )
    tracked = _git_ok(project_with_claude_md, "ls-files", "CLAUDE.md").stdout.strip()
    assert tracked == "CLAUDE.md"


def test_init_creates_mount_and_shadow_symlinks_with_clean_project_status(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)

    mount = origin_project / ".praxion-state"
    assert mount.is_dir()
    assert (mount / ".git").exists()

    ai_state = origin_project / ".ai-state"
    assert ai_state.is_symlink()
    assert ai_state.resolve() == (mount / ".ai-state").resolve()

    claude_local = origin_project / "CLAUDE.local.md"
    assert claude_local.is_symlink()

    settings_local = origin_project / ".claude" / "settings.local.json"
    assert settings_local.is_symlink()

    exclude = (origin_project / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert ".praxion-state" in exclude
    assert ".ai-state" in exclude

    status = _git_ok(origin_project, "status", "--porcelain").stdout
    assert status == ""


def test_git_add_dash_a_stages_nothing_after_init(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    _git_ok(origin_project, "add", "-A")
    staged = _git_ok(origin_project, "diff", "--cached", "--name-only").stdout
    assert staged == ""


def test_init_reports_five_numbered_sections_and_ready_message(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["init"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    for marker in ("[1/5]", "[2/5]", "[3/5]", "[4/5]", "[5/5]"):
        assert marker in result.stdout
    assert "Sidecar ready. Project commits will never include Praxion state." in result.stdout


def test_init_with_custom_id_records_it_in_the_manifest(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = run_cli(["init", "--id", "custom-slug"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert (sidecar_root / "custom-slug").is_dir()
    manifest = _manifest(sidecar_root, "custom-slug")
    assert manifest["project"]["id"] == "custom-slug"


def test_init_on_remote_less_project_derives_a_local_prefixed_id(
    local_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = run_cli(["init"], local_project, cli_env)
    assert result.returncode == 0, result.stderr

    entries = [p.name for p in sidecar_root.iterdir()]
    assert len(entries) == 1
    sidecar_id = entries[0]
    assert sidecar_id.startswith("local--")
    suffix = sidecar_id.removeprefix("local--")
    assert re.fullmatch(r"[0-9a-f]{12}", suffix), suffix

    manifest = _manifest(sidecar_root, sidecar_id)
    assert manifest["project"]["origin"] is None
    assert str(local_project.resolve()) in manifest["project"]["roots"]


# --- init: refusals and options ------------------------------------------------------------


def test_init_refuses_when_ai_state_is_a_real_directory(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    (origin_project / ".ai-state").mkdir()
    (origin_project / ".ai-state" / "marker.txt").write_text("x", encoding="utf-8")

    result = run_cli(["init"], origin_project, cli_env)
    assert result.returncode == 3
    assert (
        "Refusing to init: .ai-state/ is a real directory in this repo, not a symlink."
        in result.stderr
    )
    assert "praxion-sidecar absorb" in result.stderr
    assert not (origin_project / ".praxion-state").exists()


def test_init_refuses_when_sidecar_already_belongs_to_a_different_origin(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    project_a = tmp_path / "repo-a"
    _init_project_repo(project_a, origin="https://github.com/acme/billing")
    _init_ok(project_a, cli_env)

    project_b = tmp_path / "repo-b"
    _init_project_repo(project_b, origin="https://github.com/other/repo")

    # Force a collision deterministically: point --id at repo-a's slug.
    result = run_cli(["init", "--id", _ORIGIN_ID], project_b, cli_env)
    assert result.returncode == 3
    assert "already belongs to" in result.stderr
    assert "praxion-sidecar init --id" in result.stderr
    assert not (project_b / ".praxion-state").exists()


def test_init_dry_run_mutates_nothing_and_prints_dry_run_trailer(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = run_cli(["init", "--dry-run"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "Dry run:" in result.stdout
    assert "Nothing was modified." in result.stdout
    assert not sidecar_root.exists()
    assert not (origin_project / ".praxion-state").exists()
    assert not (origin_project / ".ai-state").exists()


def test_init_share_claude_md_marks_it_shared_not_shadowed(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = run_cli(["init", "--share", "CLAUDE.md"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    manifest = _manifest(sidecar_root, _ORIGIN_ID)
    assert manifest["paths"]["CLAUDE.md"]["intent"] == "share"


def test_init_shadow_docs_architecture_flips_default_share_to_shadow(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = run_cli(["init", "--shadow", "docs/architecture.md"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    manifest = _manifest(sidecar_root, _ORIGIN_ID)
    assert manifest["paths"]["docs/architecture.md"]["intent"] == "shadow"


def test_init_shadow_path_not_on_allowlist_is_a_usage_error(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["init", "--shadow", "src/"], origin_project, cli_env)
    assert result.returncode == 2
    assert "not a shadowable path" in result.stderr
    assert "Run 'praxion-sidecar --help' for the placement options." in result.stderr


def test_init_shadow_dot_claude_is_refused_for_worktree_safety(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["init", "--shadow", ".claude"], origin_project, cli_env)
    assert result.returncode == 3
    assert (
        "Refusing to shadow .claude/: Claude Code refuses to create a worktree "
        "when .claude/ is a symlink." in result.stderr
    )
    assert "--shadow .claude/settings.local.json" in result.stderr


def test_init_refuses_same_path_in_both_shadow_and_share(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(
        ["init", "--shadow", "docs/architecture.md", "--share", "docs/architecture.md"],
        origin_project,
        cli_env,
    )
    assert result.returncode == 2
    assert "docs/architecture.md" in result.stderr


def test_init_refuses_to_shadow_a_tracked_path_and_writes_nothing(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    """Hiding a tracked file behind a symlink is a team-visible deletion, so
    the refusal is at the boundary -- before a sidecar exists to clean up."""
    docs = origin_project / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    _git_ok(origin_project, "add", "docs/architecture.md")
    _git_ok(origin_project, "commit", "-q", "-m", "add architecture")
    before = _fs_snapshot(origin_project)

    result = run_cli(["init", "--shadow", "docs/architecture.md"], origin_project, cli_env)

    assert result.returncode == 3, result.stdout
    assert "docs/architecture.md is tracked in this repository" in result.stderr
    assert "git rm --cached docs/architecture.md" in result.stderr
    assert not (sidecar_root / _ORIGIN_ID).exists()
    assert _fs_snapshot(origin_project) == before
    assert _git_ok(origin_project, "status", "--porcelain").stdout == ""


def test_init_still_shadows_an_untracked_existing_file(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    """The refusal is about *tracked*, not about *existing* -- an untracked
    file keeps the behaviour it had before the boundary check."""
    docs = origin_project / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("# Architecture\n", encoding="utf-8")

    result = run_cli(["init", "--shadow", "docs/architecture.md"], origin_project, cli_env)

    assert result.returncode == 0, result.stderr


def _identity_isolated_env(sidecar_root: Path, home: Path) -> dict[str, str]:
    """An environment with no global/system git config and no author-identity
    env vars, so a commit's author can only come from git config `init`
    itself sets -- never from ambient machine state or `cli_env`'s own fixed
    "Test" identity override.
    """
    env = {key: value for key, value in os.environ.items() if key not in _IDENTITY_ENV_VARS}
    env["HOME"] = str(home)
    env["PRAXION_SIDECAR_ROOT"] = str(sidecar_root)
    env["NO_COLOR"] = "1"
    env.update(_ISOLATED_GIT_ENV)
    return env


def _sidecar_first_commit_author(sidecar_root: Path, project_id: str) -> str:
    sidecar = sidecar_root / project_id
    return _git_ok(sidecar, "log", "-1", "--format=%an <%ae>", "main").stdout.strip()


def test_init_inherits_the_projects_own_identity_for_the_sidecars_first_commit(
    origin_project: Path, sidecar_root: Path, tmp_path: Path
) -> None:
    """The project already carries its own local identity (`_init_project_repo`
    configures it for the seed commit) -- the sidecar's first commit must
    carry the same one, not a fixed Praxion identity, so `publish` later
    grafts attributable history into the team repo."""
    env = _identity_isolated_env(sidecar_root, tmp_path / "empty-home")

    result = run_cli(["init"], origin_project, env)

    assert result.returncode == 0, result.stderr
    assert _sidecar_first_commit_author(sidecar_root, _ORIGIN_ID) == "Test <test@example.com>"


def test_init_falls_back_to_the_fixed_identity_when_the_project_has_none_either(
    tmp_path: Path, sidecar_root: Path
) -> None:
    """With no project identity and no global git config to inherit, the
    fixed Praxion identity is the only one available -- and the sidecar's
    first commit must still succeed."""
    project = tmp_path / "no-identity-project"
    project.mkdir()
    isolated_env = {**os.environ, **_ISOLATED_GIT_ENV}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=project, check=True, env=isolated_env)
    (project / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True, env=isolated_env)
    # A one-off identity, supplied only via env vars, produces the seed commit
    # without leaving any local git config behind for `init` to inherit.
    seed_env = {
        **isolated_env,
        "GIT_AUTHOR_NAME": "Seed",
        "GIT_AUTHOR_EMAIL": "seed@example.com",
        "GIT_COMMITTER_NAME": "Seed",
        "GIT_COMMITTER_EMAIL": "seed@example.com",
    }
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=project, check=True, env=seed_env)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/no-identity"],
        cwd=project,
        check=True,
        env=isolated_env,
    )

    env = _identity_isolated_env(sidecar_root, tmp_path / "empty-home")

    result = run_cli(["init"], project, env)

    assert result.returncode == 0, result.stderr
    assert (
        _sidecar_first_commit_author(sidecar_root, "github.com--acme--no-identity")
        == "Praxion <praxion@localhost>"
    )


# --- link ------------------------------------------------------------


def test_link_on_already_linked_project_reports_no_changes_and_writes_nothing(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    before = _fs_snapshot(origin_project)

    result = run_cli(["link"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "Already linked — no changes." in result.stdout

    after = _fs_snapshot(origin_project)
    assert before == after


def test_link_recreates_a_deleted_shadow_symlink(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    claude_local = origin_project / "CLAUDE.local.md"
    claude_local.unlink()

    result = run_cli(["link"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "Linked 1 surface(s) into" in result.stdout
    assert claude_local.is_symlink()


def test_link_excludes_the_rules_example_inject_rules_seeds_into_every_project(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    """`inject_rules.py`'s SessionStart hook seeds this file into every
    project, sidecar-placed or not -- it has no placement awareness and none
    is owed here. The exclude block, not the hook, is what keeps the seeded
    file invisible to the team repo's `git status`."""
    _init_ok(origin_project, cli_env)
    example = origin_project / ".claude" / "praxion-rules.yaml.example"
    example.parent.mkdir(parents=True, exist_ok=True)
    example.write_text("# seeded by inject_rules.py\n", encoding="utf-8")

    assert _git_ok(origin_project, "status", "--porcelain").stdout == ""


def test_link_in_a_project_worktree_creates_a_worktree_scoped_mount(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    worktree_dir = origin_project / ".claude" / "worktrees" / "wt1"
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(origin_project, "worktree", "add", str(worktree_dir), "-b", "feat")

    result = run_cli(["link"], worktree_dir, cli_env)
    assert result.returncode == 0, result.stderr

    mount = worktree_dir / ".praxion-state"
    assert mount.is_dir()
    branch = _git_ok(mount, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert branch == "wt/wt1"

    ai_state = worktree_dir / ".ai-state"
    assert ai_state.is_symlink()
    assert not Path(os.readlink(ai_state)).is_absolute()


def test_link_refuses_when_ai_state_points_at_a_different_sidecar(
    tmp_path: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    project_a = tmp_path / "repo-a"
    _init_project_repo(project_a, origin="https://github.com/acme/billing")
    _init_ok(project_a, cli_env)

    project_b = tmp_path / "repo-b"
    _init_project_repo(project_b, origin="https://github.com/acme/other")
    _init_ok(project_b, cli_env)

    stale = project_b / ".ai-state"
    stale.unlink()
    stale.symlink_to(project_a / ".praxion-state" / ".ai-state", target_is_directory=True)

    result = run_cli(["link"], project_b, cli_env)
    assert result.returncode == 3
    assert "Refusing to link: .ai-state points at a different sidecar." in result.stderr
    assert "rm .ai-state && praxion-sidecar link" in result.stderr


def test_link_prune_removes_a_stale_worktree_entry_after_removal(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    worktree_dir = origin_project / ".claude" / "worktrees" / "wt1"
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(origin_project, "worktree", "add", str(worktree_dir), "-b", "feat")
    result = run_cli(["link"], worktree_dir, cli_env)
    assert result.returncode == 0, result.stderr

    # Remove the project worktree out from under the sidecar mount --
    # exactly the "worktree gone" half of an orphaned-mount scenario.
    shutil.rmtree(worktree_dir)

    sidecar = sidecar_root / _ORIGIN_ID
    before = _git_ok(sidecar, "worktree", "list", "--porcelain").stdout
    assert "wt1" in before

    prune_result = run_cli(["link", "--prune"], origin_project, cli_env)
    assert prune_result.returncode == 0, prune_result.stderr

    after = _git_ok(sidecar, "worktree", "list", "--porcelain").stdout
    assert "wt1" not in after


def test_link_dry_run_mutates_nothing(origin_project: Path, cli_env: dict[str, str]) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / "CLAUDE.local.md").unlink()
    before = _fs_snapshot(origin_project)

    result = run_cli(["link", "--dry-run"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    after = _fs_snapshot(origin_project)
    assert before == after


# --- environment refusals (R8/R9/R10) ------------------------------------------------------------


def test_running_from_a_non_git_directory_exits_environment_error(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    scratch = tmp_path / "not-a-repo"
    scratch.mkdir()
    result = run_cli(["status"], scratch, cli_env)
    assert result.returncode == 4
    assert "Cannot run here:" in result.stderr
    assert "is not a git repository." in result.stderr


def test_link_with_no_sidecar_for_this_project_exits_environment_error(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["link"], local_project, cli_env)
    assert result.returncode == 4
    assert "No sidecar for this project." in result.stderr
    assert "praxion-sidecar absorb" in result.stderr


def test_link_when_sidecar_dir_is_not_a_git_repo_exits_environment_error(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    sidecar = sidecar_root / _ORIGIN_ID
    sidecar.mkdir(parents=True)
    (sidecar / "somefile.txt").write_text("not a git repo", encoding="utf-8")

    result = run_cli(["link"], origin_project, cli_env)
    assert result.returncode == 4
    assert "Sidecar at" in result.stderr
    assert "is not a git repository." in result.stderr


# --- sidecar discovery (DS-3: from the mount, not from the environment) ---------------


def _relocated_root(tmp_path: Path) -> dict[str, str]:
    """A `PRAXION_SIDECAR_ROOT` pointing at an empty directory.

    Every verb that re-derives `<root>/<identity>` breaks under this; every
    verb that discovers the sidecar through its mount is unaffected. That is
    the whole distinction these tests exist to hold.
    """
    return {"PRAXION_SIDECAR_ROOT": str(tmp_path / "somewhere-else")}


def test_read_verbs_find_the_sidecar_through_the_mount_after_the_root_env_moves(
    origin_project: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    _init_ok(origin_project, cli_env)
    elsewhere = _relocated_root(tmp_path)

    for argv in (["status"], ["doctor"], ["commit"], ["link"], ["merge-back", "--auto"]):
        result = run_cli(argv, origin_project, cli_env, elsewhere)
        assert result.returncode == 0, f"{argv}: {result.stderr}"
        assert "No sidecar for this project." not in result.stderr, argv

    status = run_cli(["status", "--json"], origin_project, cli_env, elsewhere)
    assert json.loads(status.stdout)["placement"] == "sidecar"


def test_commit_through_the_mount_still_advances_the_sidecar_after_the_root_env_moves(
    origin_project: Path, cli_env: dict[str, str], tmp_path: Path, sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    sidecar = sidecar_root / _ORIGIN_ID
    before = _git_ok(sidecar, "rev-parse", "main").stdout.strip()
    (origin_project / ".ai-state" / "note.md").write_text("written\n", encoding="utf-8")

    result = run_cli(["commit"], origin_project, cli_env, _relocated_root(tmp_path))
    assert result.returncode == 0, result.stderr

    assert _git_ok(sidecar, "rev-parse", "main").stdout.strip() != before


def test_link_in_a_fresh_worktree_finds_the_sidecar_through_the_main_checkouts_mount(
    origin_project: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    # The one checkout with no mount of its own to discover from: `link` is
    # what is about to create it. It resolves through the project's main
    # worktree, which is mounted -- not through the environment.
    _init_ok(origin_project, cli_env)
    worktree = origin_project / ".claude" / "worktrees" / "fresh"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(origin_project, "worktree", "add", str(worktree), "-b", "feat/fresh")

    result = run_cli(["link"], worktree, cli_env, _relocated_root(tmp_path))
    assert result.returncode == 0, result.stderr

    assert (worktree / ".praxion-state").is_dir()
    assert (worktree / ".ai-state").is_symlink()


def test_a_foreign_mount_is_refused_rather_than_reported_as_no_sidecar(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    # With the environment pointing elsewhere there is no derived sidecar to
    # fall back to, so this pins the refusal on the foreign mount itself (3)
    # rather than on the absent derived one (4).
    project_a = tmp_path / "repo-a"
    _init_project_repo(project_a, origin="https://github.com/acme/billing")
    _init_ok(project_a, cli_env)

    project_b = tmp_path / "repo-b"
    _init_project_repo(project_b, origin="https://github.com/acme/other")
    (project_b / ".ai-state").symlink_to(project_a / ".praxion-state" / ".ai-state", True)

    result = run_cli(["link"], project_b, cli_env, _relocated_root(tmp_path))
    assert result.returncode == 3
    assert "Refusing to link: .ai-state points at a different sidecar." in result.stderr
    assert "rm .ai-state && praxion-sidecar link" in result.stderr


# --- status ------------------------------------------------------------


def test_status_text_reports_sidecar_placement_healthy(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(["status"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "Placement   sidecar" in result.stdout
    assert "github.com/acme/billing" in result.stdout
    assert "Healthy." in result.stdout


def test_status_text_reports_in_repo_placement_with_exit_zero(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["status"], local_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "Placement   in-repo" in result.stdout
    assert "Healthy." in result.stdout


def test_status_in_an_unlinked_worktree_refuses_and_names_link(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    """A worktree created but never linked has no state mount to report on.

    It is not `in-repo` (the project's state lives in a sidecar) and not
    reportable (there is nothing here yet), so `status` refuses with the
    remedy rather than rendering a report about a mount that does not exist.
    """
    _init_ok(origin_project, cli_env)
    worktree = _create_project_worktree(origin_project, "unlinked")

    result = run_cli(["status"], worktree, cli_env)

    assert result.returncode == 3, result.stderr  # refusal
    assert "no .ai-state yet" in result.stderr
    assert "praxion-sidecar link" in result.stderr


def test_status_exits_zero_even_when_unhealthy_and_points_at_doctor(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / "CLAUDE.local.md").unlink()

    result = run_cli(["status"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "problem(s) found. Run: praxion-sidecar doctor" in result.stdout


def test_status_json_matches_schema_with_all_keys_for_sidecar_placement(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(["status", "--json"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["schema"] == 1
    assert payload["placement"] == "sidecar"
    assert payload["project"]["origin"] == "https://github.com/acme/billing"
    assert payload["project"]["id"] == _ORIGIN_ID
    assert payload["project"]["root"] == str(origin_project.resolve())
    assert payload["checkout"]["kind"] == "main"
    assert payload["sidecar"]["branch"] == "main"
    assert payload["sidecar"]["dirty_files"] == 0
    assert isinstance(payload["sidecar"]["unpushed_commits"], int)
    assert payload["remote"] is None
    assert payload["autocommit"] in ("on-finalize-and-stop", "on-finalize", "manual")
    intents = {row["path"]: row["intent"] for row in payload["paths"]}
    assert intents[".ai-state"] == "shadow"
    assert intents["docs/architecture.md"] == "share"
    assert payload["healthy"] is True
    assert payload["failed_checks"] == []


def test_status_json_omits_sidecar_keys_under_in_repo_placement(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["status", "--json"], local_project, cli_env)
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["placement"] == "in-repo"
    for key in ("sidecar", "remote", "autocommit", "paths"):
        assert key not in payload


def test_status_json_output_is_valid_json_on_stdout_with_warnings_on_stderr(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / "CLAUDE.local.md").unlink()

    result = run_cli(["status", "--json"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)  # must parse cleanly with a warning present
    assert payload["healthy"] is False


# --- doctor ------------------------------------------------------------


def test_doctor_healthy_reports_zero_failed_zero_warnings_and_exits_zero(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(["doctor"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert re.search(r"0 failed . 0 warnings . \d+ passed\.", result.stdout)
    assert "Healthy." in result.stdout


def test_doctor_reports_warn_row_after_shadow_removed_and_exits_one(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / "CLAUDE.local.md").unlink()

    result = run_cli(["doctor"], origin_project, cli_env)
    assert result.returncode == 1
    assert "WARN" in result.stdout
    assert "missing" in result.stdout
    assert "praxion-sidecar link" in result.stdout


def test_doctor_json_matches_schema_with_stable_check_ids(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / "CLAUDE.local.md").unlink()

    result = run_cli(["doctor", "--json"], origin_project, cli_env)
    assert result.returncode == 1, result.stderr

    payload = json.loads(result.stdout)
    assert payload["schema"] == 1
    assert payload["verdict"] in ("pass", "warn", "fail")
    assert set(payload["counts"]) == {"pass", "warn", "fail"}

    ids = {row["id"] for row in payload["checks"]}
    assert "exclude-block" in ids
    assert any(check_id.startswith("shadow:") for check_id in ids)

    for row in payload["checks"]:
        assert row["verdict"] in ("pass", "warn", "fail")
        if row["verdict"] == "pass":
            assert "why" not in row
            assert "fix" not in row
        else:
            assert "fix" in row


def test_doctor_performs_no_network_git_calls(
    origin_project: Path, cli_env: dict[str, str], network_guarded_git: tuple[Path, Path]
) -> None:
    _init_ok(origin_project, cli_env)
    bin_dir, log_path = network_guarded_git
    guarded_env = dict(cli_env)
    guarded_env["PATH"] = f"{bin_dir}{os.pathsep}{cli_env['PATH']}"

    result = run_cli(["doctor"], origin_project, guarded_env)
    assert result.returncode in (0, 1), result.stderr

    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    assert "REFUSED" not in log_text
    for forbidden in ("fetch", "pull", "ls-remote", "push"):
        assert not re.search(rf"\bgit {forbidden}\b", log_text), log_text


def test_doctor_on_in_repo_project_reports_only_hook_rows_and_exits_zero(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    result = run_cli(["doctor"], local_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "hooks-path" in result.stdout
    # The chain row exists only where a wrapper is installed to inspect; a
    # plain-symlink install has no chain call whose presence could be judged.
    assert "hooks-chained" not in result.stdout
    assert "sidecar repo" not in result.stdout


# --- doctor is total over placements ----------------------------------------


def _doctor_json(project: Path, env: dict[str, str]) -> tuple[dict, int]:
    result = run_cli(["doctor", "--json"], project, env)
    return json.loads(result.stdout), result.returncode


def _placement_row(payload: dict) -> dict:
    rows = [row for row in payload["checks"] if row["id"] == "placement"]
    assert rows, f"no placement row in {[row['id'] for row in payload['checks']]}"
    return rows[0]


def test_doctor_reports_a_dangling_shadow_instead_of_refusing(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    shutil.rmtree(origin_project / ".praxion-state")
    before = _fs_snapshot(origin_project)

    payload, code = _doctor_json(origin_project, cli_env)

    row = _placement_row(payload)
    assert code == 1
    assert row["verdict"] == "fail"
    assert ".praxion-state" in row["detail"]
    assert row["fix"] == "praxion-sidecar link"
    assert _fs_snapshot(origin_project) == before


def test_doctor_reports_a_foreign_shadow_as_json_instead_of_refusing(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    project_a = tmp_path / "repo-a"
    _init_project_repo(project_a, origin="https://github.com/acme/billing")
    _init_ok(project_a, cli_env)

    project_b = tmp_path / "repo-b"
    _init_project_repo(project_b, origin="https://github.com/acme/other")
    _init_ok(project_b, cli_env)
    stale = project_b / ".ai-state"
    stale.unlink()
    stale.symlink_to(project_a / ".praxion-state" / ".ai-state", target_is_directory=True)
    before = _fs_snapshot(project_b)

    payload, code = _doctor_json(project_b, cli_env)

    row = _placement_row(payload)
    assert code == 1
    assert row["verdict"] == "fail"
    assert "identity-mismatch" in row["detail"] or "unrecognized-mount" in row["detail"]
    assert row["fix"] == "rm .ai-state && praxion-sidecar link"
    assert _fs_snapshot(project_b) == before


def test_doctor_warns_when_an_unlinked_checkout_has_a_sidecar_for_its_identity(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    """A `git clean -ffdx` takes the shadow and the mount with it, so the
    checkout reads as in-repo again while its sidecar (and every commit in
    it) is still on disk."""
    _init_ok(origin_project, cli_env)
    (origin_project / ".ai-state").unlink()
    shutil.rmtree(origin_project / ".praxion-state")

    payload, code = _doctor_json(origin_project, cli_env)

    row = _placement_row(payload)
    assert code == 1
    assert row["verdict"] == "warn"
    assert "reads as in-repo" in row["detail"]
    assert str(sidecar_root / _ORIGIN_ID) in row["detail"]
    assert row["fix"].startswith("praxion-sidecar link")
    assert "moved aside" in row["fix"]


def test_status_names_the_sidecar_rather_than_claiming_plain_in_repo(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / ".ai-state").unlink()
    shutil.rmtree(origin_project / ".praxion-state")

    result = run_cli(["status", "--json"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["placement"] == "in-repo"
    assert str(sidecar_root / _ORIGIN_ID) in payload["placement_note"]
    assert "placement" in payload["failed_checks"]


def test_doctor_on_a_plain_in_repo_project_emits_no_placement_row(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    """A row that cannot fail is noise: an unmanaged project has no sidecar
    anywhere, so there is nothing for the placement row to report."""
    payload, code = _doctor_json(local_project, cli_env)
    assert code == 0
    assert not [row for row in payload["checks"] if row["id"] == "placement"]


# --- commit ------------------------------------------------------------


def test_commit_after_writing_through_ai_state_advances_the_sidecar_branch(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    mount = origin_project / ".praxion-state"
    before_head = _git_ok(mount, "rev-parse", "HEAD").stdout.strip()

    (origin_project / ".ai-state" / "note.md").write_text("hello\n", encoding="utf-8")

    result = run_cli(["commit"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert re.search(r"Committed 1 file\(s\) to the sidecar \([0-9a-f]{7}\) — .+\.", result.stdout)

    after_head = _git_ok(mount, "rev-parse", "HEAD").stdout.strip()
    assert after_head != before_head


def test_commit_on_a_clean_sidecar_reports_nothing_to_commit(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(["commit"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "Nothing to commit." in result.stdout


def test_commit_paths_stages_only_the_named_path(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    ai_state = origin_project / ".ai-state"
    (ai_state / "keep.md").write_text("keep\n", encoding="utf-8")
    (ai_state / "skip.md").write_text("skip\n", encoding="utf-8")

    result = run_cli(["commit", "--paths", ".ai-state/keep.md"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    mount = origin_project / ".praxion-state"
    committed = _git_ok(mount, "show", "--stat", "--format=", "HEAD").stdout
    assert "keep.md" in committed
    assert "skip.md" not in committed

    still_dirty = _git_ok(mount, "status", "--porcelain").stdout
    assert "skip.md" in still_dirty


def _bare_remote(tmp_path: Path) -> Path:
    bare = tmp_path / "sidecar-remote.git"
    _git_ok(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    return bare


def _remote_head(bare: Path, branch: str) -> str | None:
    result = _git(bare, "rev-parse", branch)
    return result.stdout.strip() if result.returncode == 0 else None


def test_commit_pushes_when_the_policy_is_on_autocommit(
    origin_project: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    _init_ok(origin_project, cli_env)
    bare = _bare_remote(tmp_path)
    remote = run_cli(
        ["remote", f"file://{bare}", "--push", "on-autocommit", "--allow-foreign-host"],
        origin_project,
        cli_env,
    )
    assert remote.returncode == 0, remote.stderr
    assert _remote_head(bare, "main") is None

    (origin_project / ".ai-state" / "note.md").write_text("hello\n", encoding="utf-8")
    result = run_cli(["commit"], origin_project, cli_env)

    assert result.returncode == 0, result.stderr
    assert "Pushed main to origin." in result.stdout
    mount_head = _git_ok(origin_project / ".praxion-state", "rev-parse", "HEAD").stdout.strip()
    assert _remote_head(bare, "main") == mount_head


def test_commit_never_pushes_under_the_default_policy(
    origin_project: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
    network_guarded_git: tuple[Path, Path],
) -> None:
    """`--push never` is the default, and the manifest is read before any push
    plumbing -- so the guarded `git` shim never sees a network subcommand."""
    _init_ok(origin_project, cli_env)
    bare = _bare_remote(tmp_path)
    remote = run_cli(
        ["remote", f"file://{bare}", "--push", "never", "--allow-foreign-host"],
        origin_project,
        cli_env,
    )
    assert remote.returncode == 0, remote.stderr

    bin_dir, log_path = network_guarded_git
    guarded_env = dict(cli_env)
    guarded_env["PATH"] = f"{bin_dir}{os.pathsep}{cli_env['PATH']}"
    (origin_project / ".ai-state" / "note.md").write_text("hello\n", encoding="utf-8")

    result = run_cli(["commit"], origin_project, guarded_env)

    assert result.returncode == 0, result.stderr
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    assert "REFUSED" not in log_text
    assert not re.search(r"\bgit push\b", log_text), log_text
    assert _remote_head(bare, "main") is None


def test_a_failing_push_is_reported_without_changing_the_commit_exit_code(
    origin_project: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    """The commit is the contract; the push is best effort."""
    _init_ok(origin_project, cli_env)
    missing = tmp_path / "not-a-repo.git"
    remote = run_cli(
        ["remote", f"file://{missing}", "--push", "on-autocommit", "--allow-foreign-host"],
        origin_project,
        cli_env,
    )
    assert remote.returncode == 0, remote.stderr

    (origin_project / ".ai-state" / "note.md").write_text("hello\n", encoding="utf-8")
    result = run_cli(["commit"], origin_project, cli_env)

    assert result.returncode == 0
    assert "Committed 1 file(s) to the sidecar" in result.stdout
    assert "Sidecar push to origin failed" in result.stderr
    assert "The commit is safe in the sidecar" in result.stderr


def test_no_verb_ever_commits_to_the_project_repository(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    project_head_before = _git_ok(origin_project, "rev-parse", "HEAD").stdout.strip()

    _init_ok(origin_project, cli_env)
    (origin_project / ".ai-state" / "note.md").write_text("hello\n", encoding="utf-8")
    run_cli(["commit"], origin_project, cli_env)
    run_cli(["status"], origin_project, cli_env)
    run_cli(["doctor"], origin_project, cli_env)
    run_cli(["link"], origin_project, cli_env)

    project_head_after = _git_ok(origin_project, "rev-parse", "HEAD").stdout.strip()
    assert project_head_after == project_head_before
    assert _git_ok(origin_project, "status", "--porcelain").stdout == ""


# --- output discipline ------------------------------------------------------------


def test_no_ansi_escapes_when_stdout_is_not_a_tty(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    env = dict(cli_env)
    env.pop("NO_COLOR", None)  # isolate the "not a TTY" gate from the NO_COLOR gate

    result = run_cli(["doctor"], origin_project, env)
    assert "\x1b[" not in result.stdout


# --- merge drivers ------------------------------------------------------------

_OBSERVATIONS_ATTRIBUTE = ".ai-state/observations.jsonl merge=observations-jsonl"
_DRIVER_KEY = "merge.observations-jsonl.driver"


def _observation(timestamp: str, note: str) -> str:
    """One well-formed observations.jsonl record.

    The driver dedups on `timestamp|session_id|event_type|tool_name` and sorts
    by timestamp, so distinct timestamps are what make two records survive the
    merge as two records rather than one.
    """
    return json.dumps({"timestamp": timestamp, "session_id": "s1", "note": note})


def _append_observation(checkout: Path, timestamp: str, note: str) -> None:
    log = checkout / ".ai-state" / "observations.jsonl"
    existing = log.read_text(encoding="utf-8") if log.exists() else ""
    log.write_text(f"{existing}{_observation(timestamp, note)}\n", encoding="utf-8")


def test_init_routes_observations_through_the_semantic_merge_driver(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    sidecar = sidecar_root / _ORIGIN_ID

    attributes = (sidecar / ".gitattributes").read_text(encoding="utf-8")
    assert _OBSERVATIONS_ATTRIBUTE in attributes.splitlines()

    registered = _git_ok(sidecar, "config", "--get", _DRIVER_KEY).stdout.strip()
    assert registered != ""
    assert registered.endswith("%O %A %B")
    assert "merge_driver_observations.py" in registered

    # Tracked from the first revision, so every mount materialises it.
    tracked = _git_ok(sidecar, "ls-files", ".gitattributes").stdout.strip()
    assert tracked == ".gitattributes"


def test_link_re_registers_a_merge_driver_that_was_removed(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    sidecar = sidecar_root / _ORIGIN_ID
    _git_ok(sidecar, "config", "--unset", _DRIVER_KEY)
    assert _git(sidecar, "config", "--get", _DRIVER_KEY).stdout.strip() == ""

    result = run_cli(["link"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert _git_ok(sidecar, "config", "--get", _DRIVER_KEY).stdout.strip() != ""


def test_the_observations_merge_driver_fires_when_two_mounts_diverge(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    """The whole point of the routing: two checkouts appending to the event log
    must both survive a merge-back. Git's default line-based 3-way strategy
    conflicts here; the semantic driver reconciles at the JSONL level."""
    _init_ok(origin_project, cli_env)
    sidecar = sidecar_root / _ORIGIN_ID

    _append_observation(origin_project, "2026-09-03T00:00:00Z", "base")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0

    worktree_dir = origin_project / ".claude" / "worktrees" / "wt1"
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(origin_project, "worktree", "add", str(worktree_dir), "-b", "feat")
    assert run_cli(["link"], worktree_dir, cli_env).returncode == 0

    _append_observation(origin_project, "2026-09-03T00:00:01Z", "from-main")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0
    _append_observation(worktree_dir, "2026-09-03T00:00:02Z", "from-worktree")
    assert run_cli(["commit"], worktree_dir, cli_env).returncode == 0

    mount = origin_project / ".praxion-state"
    merge = _git(
        mount,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "merge",
        "--no-edit",
        "wt/wt1",
    )
    assert merge.returncode == 0, f"{merge.stdout}\n{merge.stderr}"

    merged = (mount / ".ai-state" / "observations.jsonl").read_text(encoding="utf-8")
    assert "from-main" in merged
    assert "from-worktree" in merged
    assert "base" in merged
    assert _git_ok(sidecar, "worktree", "list").returncode == 0


# --- second section (merge-back / publish / absorb / remote) ------------------------------------------------------------
#
# `merge-back` does not exist as a subcommand yet -- argparse's subparsers
# refuse any name outside {init, link, status, doctor, commit, publish,
# absorb, remote}, so every `merge-back` invocation below fails usage (exit
# 2) today, for the wrong reason, before it ever reaches the behaviour under
# test. `publish` / `absorb` / `remote` are registered verbs but every body
# is `verb_unimplemented` (environment error, exit 4) and their parsers carry
# none of the flags this section drives (`--yes`, `--allow-foreign-host`,
# `--push`, `--clear`, a `remote` positional URL) -- passing them is an
# argparse "unrecognized arguments" usage error. This is the RED skeleton for
# the merge-back/publish/absorb/remote extension (recorded in
# `TEST_RESULTS.md`).


def _run_cli_no_stdin(
    args: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Like `run_cli`, but with stdin explicitly closed and a hard timeout --
    the only way to prove a confirmation prompt *refuses* rather than blocks
    forever waiting on a TTY that will never answer (R12).
    """
    return subprocess.run(
        [sys.executable, str(_CLI), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=10,
    )


def _create_project_worktree(project: Path, name: str, *, base: str = "main") -> Path:
    """A project worktree at `.claude/worktrees/<name>` on a fresh branch
    `feat/<name>`, diverging with a real commit of its own -- the
    project-side half of a sidecar branch convergence can later classify.
    """
    worktree = project / ".claude" / "worktrees" / name
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(project, "worktree", "add", str(worktree), "-b", f"feat/{name}", base)
    (worktree / f"{name}.py").write_text(f"{name} feature\n", encoding="utf-8")
    _git_ok(worktree, "add", f"{name}.py")
    _git_ok(worktree, "commit", "-q", "-m", f"{name} feature work")
    return worktree


def _link_worktree(worktree: Path, cli_env: dict[str, str]) -> None:
    result = run_cli(["link"], worktree, cli_env)
    assert result.returncode == 0, result.stderr


def _write_draft_and_commit(worktree: Path, cli_env: dict[str, str], name: str) -> Path:
    """Write a draft ADR through the worktree's shadowed `.ai-state`, then
    commit it to the sidecar via the CLI -- the load-bearing "draft written
    from a linked worktree" scenario the whole plan hinges on.
    """
    drafts = worktree / ".ai-state" / "decisions" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    draft = drafts / f"{name}-decision.md"
    draft.write_text(f"# Draft decision: {name}\n", encoding="utf-8")
    result = run_cli(["commit"], worktree, cli_env)
    assert result.returncode == 0, result.stderr
    return draft


def _build_linked_worktree_with_draft(project: Path, cli_env: dict[str, str], name: str) -> Path:
    worktree = _create_project_worktree(project, name)
    _link_worktree(worktree, cli_env)
    _write_draft_and_commit(worktree, cli_env, name)
    return worktree


def _build_merged_worktree(project: Path, cli_env: dict[str, str], name: str) -> Path:
    """A linked worktree whose project branch is already merged into `main`
    by a real, direct `git merge` -- the `MergedLive` starting point.
    """
    worktree = _build_linked_worktree_with_draft(project, cli_env, name)
    _git_ok(project, "merge", "-q", "--no-ff", "--no-edit", f"feat/{name}")
    return worktree


def _sidecar_state_snapshot(sidecar_dir: Path, mounts: list[Path]) -> tuple:
    """Everything a no-op run must leave untouched: refs, the worktree list,
    and each mount's tree/HEAD.
    """
    refs = _git_ok(sidecar_dir, "for-each-ref").stdout
    worktree_list = _git_ok(sidecar_dir, "worktree", "list", "--porcelain").stdout
    mount_states = tuple(
        (
            _git_ok(mount, "status", "--porcelain").stdout,
            _git_ok(mount, "rev-parse", "HEAD").stdout.strip(),
        )
        for mount in mounts
    )
    return (refs, worktree_list, mount_states)


@pytest.fixture
def linked_worktree(origin_project: Path, cli_env: dict[str, str]) -> Path:
    """`origin_project`, initialized, with a linked project worktree `x`
    (sidecar branch `wt/x`) carrying one committed draft ADR -- the shared
    starting point for the merge-back visibility and lifecycle scenarios.
    """
    _init_ok(origin_project, cli_env)
    return _build_linked_worktree_with_draft(origin_project, cli_env, "x")


# --- merge-back --from: visibility ------------------------------------------------------------


def test_merge_back_from_makes_the_worktree_draft_visible_in_the_target_checkout(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str]
) -> None:
    draft = origin_project / ".ai-state" / "decisions" / "drafts" / "x-decision.md"
    assert not draft.exists()
    project_head_before = _git_ok(origin_project, "rev-parse", "HEAD").stdout.strip()
    main_mount = origin_project / ".praxion-state"
    mount_head_before = _git_ok(main_mount, "rev-parse", "HEAD").stdout.strip()

    result = run_cli(["merge-back", "--from", "wt/x"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    assert draft.exists()
    mount_head_after = _git_ok(main_mount, "rev-parse", "HEAD").stdout.strip()
    assert mount_head_after != mount_head_before
    parents = _git_ok(main_mount, "log", "-1", "--format=%P", mount_head_after).stdout.split()
    assert len(parents) == 2, "expected merge-back to land a merge commit, not a fast-forward"
    assert _git_ok(origin_project, "rev-parse", "HEAD").stdout.strip() == project_head_before


def test_merge_back_from_refuses_on_a_dirty_target_mount(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str]
) -> None:
    main_mount = origin_project / ".praxion-state"
    (main_mount / ".ai-state" / "scratch.md").write_text("dirty\n", encoding="utf-8")

    result = run_cli(["merge-back", "--from", "wt/x"], origin_project, cli_env)
    assert result.returncode == 3
    assert "uncommitted" in result.stderr.lower() or "dirty" in result.stderr.lower()

    draft = origin_project / ".ai-state" / "decisions" / "drafts" / "x-decision.md"
    assert not draft.exists()


def test_merge_back_from_dry_run_mutates_nothing(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    sidecar_dir = sidecar_root / _ORIGIN_ID
    main_mount = origin_project / ".praxion-state"
    before = _sidecar_state_snapshot(sidecar_dir, [main_mount, linked_worktree / ".praxion-state"])

    result = run_cli(["merge-back", "--from", "wt/x", "--dry-run"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    after = _sidecar_state_snapshot(sidecar_dir, [main_mount, linked_worktree / ".praxion-state"])
    assert before == after
    draft = origin_project / ".ai-state" / "decisions" / "drafts" / "x-decision.md"
    assert not draft.exists()


# --- merge-back --auto: convergence ------------------------------------------------------------


def test_merge_back_auto_skips_a_branch_whose_project_work_is_not_merged(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str]
) -> None:
    draft = origin_project / ".ai-state" / "decisions" / "drafts" / "x-decision.md"

    result = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "wt/x" in result.stdout
    assert "project branch not merged" in result.stdout
    assert not draft.exists()


def test_merge_back_auto_converges_after_the_project_branch_is_merged(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str]
) -> None:
    draft = origin_project / ".ai-state" / "decisions" / "drafts" / "x-decision.md"
    _git_ok(origin_project, "merge", "-q", "--no-ff", "--no-edit", "feat/x")

    result = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert draft.exists()


def test_merge_back_auto_is_a_no_op_once_the_tree_is_at_its_fixed_point(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str]
) -> None:
    _git_ok(origin_project, "merge", "-q", "--no-ff", "--no-edit", "feat/x")
    first = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert first.returncode == 0, first.stderr

    second = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert second.returncode == 0, second.stderr
    # Pinned string -- ARCH_WT_RULING.md sec. 13 does not name the exact
    # fixed-point line, only the property ("Nothing to converge." is this
    # suite's chosen oracle; see LEARNINGS.md).
    assert "Nothing to converge." in second.stdout


def test_merge_back_auto_converges_a_github_style_squash_merge(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    _build_linked_worktree_with_draft(origin_project, cli_env, "sq")
    draft = origin_project / ".ai-state" / "decisions" / "drafts" / "sq-decision.md"

    _git_ok(origin_project, "merge", "-q", "--squash", "feat/sq")
    _git_ok(origin_project, "commit", "-q", "-m", "squash-merge feat/sq")

    result = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert draft.exists()


def test_merge_back_auto_does_not_drop_a_merged_branch_while_its_mount_still_lives(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    _build_merged_worktree(origin_project, cli_env, "live")

    result = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    sidecar_dir = sidecar_root / _ORIGIN_ID
    assert _git_ok(sidecar_dir, "branch", "--list", "wt/live").stdout.strip() != ""


def test_merge_back_auto_drops_a_merged_branch_once_its_mount_is_gone(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    worktree = _build_merged_worktree(origin_project, cli_env, "orphan")
    sidecar_dir = sidecar_root / _ORIGIN_ID
    # Removed on the SIDECAR side directly (not via `link --prune`) so this
    # test isolates `--auto`'s own deletion behaviour from `link`'s own
    # embedded convergence call (ARCH_WT_RULING.md sec. 13.3, channel 2).
    _git_ok(sidecar_dir, "worktree", "remove", "--force", str(worktree / ".praxion-state"))

    result = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert _git_ok(sidecar_dir, "branch", "--list", "wt/orphan").stdout.strip() == ""


def test_merge_back_auto_dry_run_mutates_nothing(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    worktree = _build_linked_worktree_with_draft(origin_project, cli_env, "dr")
    _git_ok(origin_project, "merge", "-q", "--no-ff", "--no-edit", "feat/dr")

    sidecar_dir = sidecar_root / _ORIGIN_ID
    main_mount = origin_project / ".praxion-state"
    before = _sidecar_state_snapshot(sidecar_dir, [main_mount, worktree / ".praxion-state"])

    result = run_cli(["merge-back", "--auto", "--dry-run"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "wt/dr" in result.stdout

    after = _sidecar_state_snapshot(sidecar_dir, [main_mount, worktree / ".praxion-state"])
    assert before == after


# --- the settling test: --auto aborts, --from may leave markers -------------------------------


def test_merge_back_auto_aborts_a_conflict_cleanly_while_from_leaves_markers_for_the_same_one(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    """The one behavioural difference between the two forms (ARCH_WT_RULING.md
    sec. 13.4/13.5): an automatic run is never allowed to leave a mount
    mid-merge, while the explicit, operator-driven verb may. Both halves are
    exercised against the *same* underlying conflict, which is what makes
    this the settling test rather than two independent ones.
    """
    _init_ok(origin_project, cli_env)
    (origin_project / ".ai-state" / "DESIGN.md").write_text("base\n", encoding="utf-8")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0

    worktree = _create_project_worktree(origin_project, "c")
    _link_worktree(worktree, cli_env)
    (worktree / ".ai-state" / "DESIGN.md").write_text("worktree-change\n", encoding="utf-8")
    assert run_cli(["commit"], worktree, cli_env).returncode == 0

    (origin_project / ".ai-state" / "DESIGN.md").write_text("main-change\n", encoding="utf-8")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0

    _git_ok(origin_project, "merge", "-q", "--no-ff", "--no-edit", "feat/c")
    main_mount = origin_project / ".praxion-state"

    auto_result = run_cli(["merge-back", "--auto"], origin_project, cli_env)
    assert auto_result.returncode == 1
    auto_combined = auto_result.stdout + auto_result.stderr
    assert "wt/c" in auto_combined
    assert "praxion-sidecar merge-back --from wt/c" in auto_combined
    assert _git_ok(main_mount, "status", "--porcelain").stdout == ""
    assert _git(main_mount, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0

    # Pinned exit code: a conflict left with markers is actionable (D1's `1`),
    # not a safety refusal (`3`) -- the operator asked for exactly this via
    # `--from` (LEARNINGS.md notes this as an assumption for the implementer).
    explicit_result = run_cli(["merge-back", "--from", "wt/c"], origin_project, cli_env)
    assert explicit_result.returncode == 1
    explicit_combined = explicit_result.stdout + explicit_result.stderr
    assert "wt/c" in explicit_combined
    assert "abort" in explicit_combined.lower()

    assert _git(main_mount, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0
    design_text = (main_mount / ".ai-state" / "DESIGN.md").read_text(encoding="utf-8")
    assert "<<<<<<<" in design_text

    doctor = run_cli(["doctor", "--json"], origin_project, cli_env)
    assert doctor.returncode == 1, doctor.stderr
    payload = json.loads(doctor.stdout)
    rows = {row["id"]: row for row in payload["checks"]}
    assert rows["mount-conflict"]["verdict"] == "fail"
    # Non-accusatory wording (ARCH_WT_RULING.md sec. 13.6/14 objection 5): a
    # read-only doctor cannot tell in-progress resolution from an abandoned
    # mount, so the FAIL row must state the fact, not assert a rule broken.
    assert "violat" not in rows["mount-conflict"]["detail"].lower()
    assert "violat" not in rows["mount-conflict"].get("why", "").lower()

    assert _git_ok(main_mount, "merge", "--abort").returncode == 0
    assert _git_ok(main_mount, "status", "--porcelain").stdout == ""


# --- merge-back --drop: the two-step explicit path ------------------------------------------------------------


def test_merge_back_drop_without_yes_is_a_usage_error_and_does_not_hang(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str]
) -> None:
    result = _run_cli_no_stdin(["merge-back", "--from", "wt/x", "--drop"], origin_project, cli_env)
    assert result.returncode == 2


def test_merge_back_drop_refuses_while_the_branchs_mount_still_exists(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    result = _run_cli_no_stdin(
        ["merge-back", "--from", "wt/x", "--drop", "--yes"], origin_project, cli_env
    )
    assert result.returncode == 3
    assert "remove the mount first" in result.stderr
    assert "praxion-sidecar link --prune" in result.stderr

    sidecar_dir = sidecar_root / _ORIGIN_ID
    assert _git_ok(sidecar_dir, "branch", "--list", "wt/x").stdout.strip() != ""


def test_merge_back_drop_deletes_the_branch_once_the_mount_is_gone(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _git_ok(origin_project, "worktree", "remove", str(linked_worktree))
    prune = run_cli(["link", "--prune"], origin_project, cli_env)
    assert prune.returncode == 0, prune.stderr

    result = _run_cli_no_stdin(
        ["merge-back", "--from", "wt/x", "--drop", "--yes"], origin_project, cli_env
    )
    assert result.returncode == 0, result.stderr

    sidecar_dir = sidecar_root / _ORIGIN_ID
    assert _git_ok(sidecar_dir, "branch", "--list", "wt/x").stdout.strip() == ""


# --- doctor: DS-11 convergence rows ------------------------------------------------------------


def test_doctor_reports_state_unmerged_when_the_project_branch_is_deleted_and_unresolvable(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    # No remote fetch ever ran against the fake origin URL, so deleting the
    # local project branch leaves no remote-tracking ref behind either --
    # `MappingUnresolvable`, the "local branch deleted and the
    # remote-tracking ref pruned" case (ARCH_WT_RULING.md sec. 13.2).
    _init_ok(origin_project, cli_env)
    worktree = _build_linked_worktree_with_draft(origin_project, cli_env, "y")
    _git_ok(origin_project, "worktree", "remove", str(worktree))
    _git_ok(origin_project, "branch", "-D", "feat/y")

    result = run_cli(["doctor", "--json"], origin_project, cli_env)
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    rows = [row for row in payload["checks"] if row["id"] == "state-unmerged"]
    assert rows
    assert "wt/y" in rows[0]["detail"]
    assert "MappingUnresolvable" in rows[0]["detail"]
    assert rows[0]["fix"] == "praxion-sidecar merge-back --from wt/y"


def test_doctor_reports_state_eligible_for_a_merged_but_not_yet_converged_branch(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str]
) -> None:
    # Merged directly, deliberately bypassing every convergence channel
    # (`--auto`, `link`) so the branch sits at "eligible but not converged".
    _git_ok(origin_project, "merge", "-q", "--no-ff", "--no-edit", "feat/x")

    result = run_cli(["doctor", "--json"], origin_project, cli_env)
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    rows = [row for row in payload["checks"] if row["id"] == "state-eligible"]
    assert rows
    assert "wt/x" in rows[0]["detail"]
    assert rows[0]["fix"] == "praxion-sidecar link"


def test_doctor_reports_mount_orphaned_for_a_stale_sidecar_worktree_entry(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    shutil.rmtree(linked_worktree)

    result = run_cli(["doctor", "--json"], origin_project, cli_env)
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    rows = [row for row in payload["checks"] if row["id"] == "mount-orphaned"]
    assert rows
    assert rows[0]["fix"] == "praxion-sidecar link --prune"


# --- remote ------------------------------------------------------------


def test_remote_with_no_remote_configured_reports_the_never_push_policy(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(["remote"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr
    assert "No remote configured. Push policy: never." in result.stdout


def test_remote_refuses_a_foreign_host_without_the_override_flag(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(
        ["remote", "https://gitlab.com/acme/billing-praxion.git"], origin_project, cli_env
    )
    assert result.returncode == 3
    assert (
        "Refusing to set the sidecar remote: host gitlab.com does not match the project "
        "origin's host github.com." in result.stderr
    )
    assert "--allow-foreign-host" in result.stderr


def test_remote_allow_foreign_host_sets_it_and_records_the_acknowledgement(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(
        ["remote", "https://gitlab.com/acme/billing-praxion.git", "--allow-foreign-host"],
        origin_project,
        cli_env,
    )
    assert result.returncode == 0, result.stderr

    manifest = _manifest(sidecar_root, _ORIGIN_ID)
    assert manifest["remote"]["foreign_host_ack"] is True

    doctor = run_cli(["doctor", "--json"], origin_project, cli_env)
    payload = json.loads(doctor.stdout)
    rows = {row["id"]: row for row in payload["checks"]}
    assert rows["remote-policy"]["verdict"] == "pass"


def test_remote_matching_host_sets_url_and_push_policy(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(
        ["remote", "git@github.com:acme/billing-praxion.git", "--push", "on-autocommit"],
        origin_project,
        cli_env,
    )
    assert result.returncode == 0, result.stderr
    assert (
        "Remote set: git@github.com:acme/billing-praxion.git (host github.com matches the "
        "project origin). Push policy: on-autocommit."
    ) in result.stdout


def test_remote_clear_removes_a_configured_remote(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    set_result = run_cli(
        ["remote", "git@github.com:acme/billing-praxion.git"], origin_project, cli_env
    )
    assert set_result.returncode == 0, set_result.stderr

    result = run_cli(["remote", "--clear"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    manifest = _manifest(sidecar_root, _ORIGIN_ID)
    assert manifest["remote"] is None


def test_remote_invalid_push_policy_is_a_usage_error(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = run_cli(
        ["remote", "git@github.com:acme/billing-praxion.git", "--push", "always"],
        origin_project,
        cli_env,
    )
    assert result.returncode == 2


# --- publish ------------------------------------------------------------


def test_publish_refuses_on_a_dirty_project_working_tree(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / "dirty.py").write_text("dirty\n", encoding="utf-8")

    result = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)
    assert result.returncode == 3
    assert "Refusing to publish" in result.stderr
    assert (origin_project / ".praxion-state").is_dir()


def test_publish_without_yes_on_non_interactive_stdin_is_a_usage_error(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    result = _run_cli_no_stdin(["publish"], origin_project, cli_env)
    assert result.returncode == 2
    assert "Usage error: publish needs confirmation and stdin is not a terminal." in (result.stderr)
    assert "In non-interactive mode, pass --yes to confirm." in result.stderr


def test_publish_moves_sidecar_state_into_the_project_with_history_and_removes_every_mount(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / ".ai-state" / "note.md").write_text("published note\n", encoding="utf-8")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0

    # A second, unmerged mount -- proving "every mount", plural, without
    # coupling this test to merge-back's own (separately tested) behaviour.
    worktree = _create_project_worktree(origin_project, "pub")
    _link_worktree(worktree, cli_env)

    result = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    ai_state = origin_project / ".ai-state"
    assert ai_state.is_dir()
    assert not ai_state.is_symlink()
    assert (ai_state / "note.md").read_text(encoding="utf-8") == "published note\n"

    log = _git_ok(origin_project, "log", "--oneline", "--", ".ai-state").stdout
    assert "chore(sidecar): initialise" in log

    assert not (origin_project / ".praxion-state").exists()
    assert not (worktree / ".praxion-state").exists()

    sidecar_dir = sidecar_root / _ORIGIN_ID
    if sidecar_dir.exists():
        assert _git_ok(sidecar_dir, "branch", "--list", "wt/*").stdout.strip() == ""

    status = run_cli(["status", "--json"], origin_project, cli_env)
    payload = json.loads(status.stdout)
    assert payload["placement"] == "in-repo"


def _reject_commits(project: Path) -> Path:
    """A pre-commit hook that refuses every commit -- the realistic way the
    one project commit publish makes can fail on a real repository."""
    hook = project / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho 'policy: no commits today' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    return hook


def test_publish_refuses_while_a_state_branch_carries_work_main_does_not(
    linked_worktree: Path, origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    # `wt/x` has a committed draft and its project branch was never merged, so
    # publishing `main` would leave that state behind in a sidecar publish is
    # about to dismantle.
    result = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)
    assert result.returncode == 3
    assert "wt/x" in result.stderr
    assert "praxion-sidecar merge-back --auto" in result.stderr

    assert (origin_project / ".praxion-state").is_dir()
    sidecar_dir = sidecar_root / _ORIGIN_ID
    assert _git_ok(sidecar_dir, "branch", "--list", "wt/x").stdout.strip() != ""


def test_publish_rolls_back_completely_when_the_project_refuses_the_import_commit(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    """The failure the ordering exists for: the import commit is rejected, so
    *nothing* is published -- and, critically, nothing is dismantled either.
    """
    _init_ok(origin_project, cli_env)
    (origin_project / ".ai-state" / "note.md").write_text("published note\n", encoding="utf-8")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0
    hook = _reject_commits(origin_project)
    sidecar_dir = sidecar_root / _ORIGIN_ID
    exclude = origin_project / ".git" / "info" / "exclude"

    result = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)
    assert result.returncode != 0
    assert "nothing was published" in result.stderr

    assert (origin_project / ".praxion-state").is_dir()
    assert (origin_project / ".ai-state").is_symlink()
    assert (origin_project / "CLAUDE.local.md").is_symlink()
    assert ".praxion-state" in exclude.read_text(encoding="utf-8")
    assert _git_ok(origin_project, "status", "--porcelain").stdout == ""
    assert _git(origin_project, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0

    hook.unlink()
    retry = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)
    assert retry.returncode == 0, retry.stderr
    assert (origin_project / ".ai-state" / "note.md").read_text(encoding="utf-8") == (
        "published note\n"
    )
    assert not (origin_project / ".praxion-state").exists()
    # A successful publish retires the sidecar out of the identity slot (it is
    # kept as a backup under a `.published-<stamp>` name), so the branch check
    # follows it there.
    assert not sidecar_dir.exists()
    retired = next(p for p in sidecar_root.iterdir() if p.name.startswith(f"{_ORIGIN_ID}."))
    assert _git_ok(retired, "branch", "--list", "wt/*").stdout.strip() == ""


def test_publish_leaves_the_local_only_shadows_as_real_files(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    _init_ok(origin_project, cli_env)
    (origin_project / "CLAUDE.local.md").write_text("local guidance\n", encoding="utf-8")
    settings = origin_project / ".claude" / "settings.local.json"
    settings.write_text('{"local": true}\n', encoding="utf-8")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0

    result = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    kept = origin_project / "CLAUDE.local.md"
    assert kept.is_file()
    assert not kept.is_symlink()
    assert kept.read_text(encoding="utf-8") == "local guidance\n"
    assert settings.is_file()
    assert not settings.is_symlink()
    assert settings.read_text(encoding="utf-8") == '{"local": true}\n'
    assert "CLAUDE.local.md" in result.stdout


# --- absorb ------------------------------------------------------------


def test_absorb_refuses_without_yes_on_non_interactive_stdin(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    (local_project / ".ai-state").mkdir()
    (local_project / ".ai-state" / "note.md").write_text("existing\n", encoding="utf-8")
    _git_ok(local_project, "add", ".ai-state/note.md")
    _git_ok(local_project, "commit", "-q", "-m", "add project state")

    result = _run_cli_no_stdin(["absorb"], local_project, cli_env)
    assert result.returncode == 2


def test_absorb_refuses_when_the_project_has_no_committed_state_to_move(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    # No .ai-state/ at all: there is nothing to preserve, and `init` is the
    # verb that starts a sidecar from scratch.
    absent = _run_cli_no_stdin(["absorb", "--yes"], local_project, cli_env)
    assert absent.returncode == 3
    assert "praxion-sidecar init" in absent.stderr

    # Present but untracked: absorb's whole promise is history, and untracked
    # scratch state has none.
    (local_project / ".ai-state").mkdir()
    (local_project / ".ai-state" / "note.md").write_text("scratch\n", encoding="utf-8")
    untracked = _run_cli_no_stdin(["absorb", "--yes"], local_project, cli_env)
    assert untracked.returncode == 3
    assert "not committed" in untracked.stderr
    assert not (local_project / ".praxion-state").exists()


def test_absorb_moves_committed_project_state_into_a_new_sidecar_with_history(
    local_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    (local_project / ".ai-state").mkdir()
    (local_project / ".ai-state" / "note.md").write_text("existing\n", encoding="utf-8")
    _git_ok(local_project, "add", ".ai-state/note.md")
    _git_ok(local_project, "commit", "-q", "-m", "seed project state for absorb")
    head_before = _git_ok(local_project, "rev-parse", "HEAD").stdout.strip()

    result = _run_cli_no_stdin(["absorb", "--yes"], local_project, cli_env)
    assert result.returncode == 0, result.stderr

    assert (local_project / ".praxion-state").is_dir()
    head_after = _git_ok(local_project, "rev-parse", "HEAD").stdout.strip()
    assert head_after == head_before  # absorb never commits to the project (D1: sidecar-only)

    status_lines = [
        line
        for line in _git_ok(local_project, "status", "--porcelain").stdout.splitlines()
        if line.strip()
    ]
    assert status_lines, "absorb must leave the .ai-state removal for the operator to stage"
    assert all(".ai-state" in line for line in status_lines)

    status = run_cli(["status", "--json"], local_project, cli_env)
    payload = json.loads(status.stdout)
    assert payload["placement"] == "sidecar"

    sidecar_id = payload["project"]["id"]
    sidecar_dir = sidecar_root / sidecar_id
    log = _git_ok(sidecar_dir, "log", "--oneline", "--", ".ai-state").stdout
    assert "seed project state for absorb" in log


# --- publish atomicity, and the publish -> absorb round trip -----------------


def test_publish_refuses_before_touching_anything_when_a_mount_is_dirty(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    """Every refusal publish can raise is a *pre*-check.

    The teardown's own dirty-mount refusal fired after the import commit had
    already landed, leaving the project reporting `in-repo` beside a live
    `.praxion-state`, surviving `wt/*` branches and an intact exclude block -- a
    state neither placement describes and no verb can undo."""
    _init_ok(origin_project, cli_env)
    worktree = _create_project_worktree(origin_project, "dirtymount")
    _link_worktree(worktree, cli_env)
    (worktree / ".ai-state" / "scratch.md").write_text("unsaved work\n", encoding="utf-8")

    result = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)

    assert result.returncode == 3
    assert "not safe to remove" in result.stderr
    # Names the offending mount and how to clean it, not just a count.
    assert str(worktree / ".praxion-state") in result.stderr or ".praxion-state" in result.stderr
    assert "praxion-sidecar commit" in result.stderr
    # Nothing was touched: the project is still sidecar-placed, both mounts
    # stand, and no import commit exists.
    assert (origin_project / ".ai-state").is_symlink()
    assert (origin_project / ".praxion-state").is_dir()
    assert (worktree / ".praxion-state").is_dir()
    payload = json.loads(run_cli(["status", "--json"], origin_project, cli_env).stdout)
    assert payload["placement"] == "sidecar"


def test_publish_retires_the_old_sidecar_out_of_the_identity_slot(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    """The backup is kept -- renamed, so the canonical path is free again."""
    _init_ok(origin_project, cli_env)
    sidecar_dir = sidecar_root / _ORIGIN_ID

    result = _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env)
    assert result.returncode == 0, result.stderr

    assert not sidecar_dir.exists(), "the identity slot must be free after publish"
    retired = [p for p in sidecar_root.iterdir() if p.name.startswith(f"{_ORIGIN_ID}.published-")]
    assert len(retired) == 1, sorted(p.name for p in sidecar_root.iterdir())
    assert (retired[0] / ".git").exists()
    assert retired[0].name in result.stdout
    assert "backup" in result.stdout


def test_publish_then_absorb_is_a_round_trip(
    origin_project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    """`absorb` is documented as publish's inverse, so the pair must compose:
    publish, commit the adoption, absorb -- and land back on a sidecar whose
    history still carries the pre-publish commits."""
    _init_ok(origin_project, cli_env)
    (origin_project / ".ai-state" / "note.md").write_text("round trip\n", encoding="utf-8")
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0

    assert _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env).returncode == 0
    # publish leaves the machine-local shadows as untracked plain files; the
    # operator's own next step is to record the adoption.
    _git_ok(origin_project, "add", "-A")
    _git_ok(origin_project, "commit", "-q", "-m", "chore: adopt Praxion state")

    absorbed = _run_cli_no_stdin(["absorb", "--yes"], origin_project, cli_env)
    assert absorbed.returncode == 0, absorbed.stderr

    payload = json.loads(run_cli(["status", "--json"], origin_project, cli_env).stdout)
    assert payload["placement"] == "sidecar"
    sidecar_dir = sidecar_root / payload["project"]["id"]
    log = _git_ok(sidecar_dir, "log", "--oneline", "--", ".ai-state").stdout
    assert "chore(sidecar): initialise" in log, log
    # The backup from the publish leg is still on disk beside the new sidecar.
    retired = [p for p in sidecar_root.iterdir() if p.name.startswith(f"{_ORIGIN_ID}.published-")]
    assert len(retired) == 1


def test_publish_then_absorb_restores_every_shadow_not_only_the_state_directory(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    """publish turns every shadowed file back into a real one, so an absorb
    that re-shadowed only the state directory left the rest as real files
    `link` refuses to reclaim -- a round trip that ends unhealthy."""
    _init_ok(origin_project, cli_env)
    (origin_project / "CLAUDE.local.md").write_text("local guidance\n", encoding="utf-8")
    (origin_project / ".claude" / "settings.local.json").write_text(
        '{"local": true}\n', encoding="utf-8"
    )
    assert run_cli(["commit"], origin_project, cli_env).returncode == 0
    assert _run_cli_no_stdin(["publish", "--yes"], origin_project, cli_env).returncode == 0
    _git_ok(origin_project, "add", "-A")
    _git_ok(origin_project, "commit", "-q", "-m", "chore: adopt Praxion state")

    absorbed = _run_cli_no_stdin(["absorb", "--yes"], origin_project, cli_env)
    assert absorbed.returncode == 0, absorbed.stderr

    for relpath in (".ai-state", "CLAUDE.local.md", ".claude/settings.local.json"):
        assert (origin_project / relpath).is_symlink(), relpath
    assert (origin_project / "CLAUDE.local.md").read_text(encoding="utf-8") == "local guidance\n"
    doctor = run_cli(["doctor"], origin_project, cli_env)
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr


def test_link_from_a_second_clone_names_the_checkout_holding_the_sidecar_branch(
    origin_project: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    """Two clones of one origin derive the same sidecar identity and the same
    mount branch, and git allows a branch in one worktree only. Nothing
    occupies the second clone's own slot, so the refusal must name the
    collision rather than advise moving something aside."""
    _init_ok(origin_project, cli_env)
    second_clone = tmp_path / "billing-second"
    _init_project_repo(second_clone, origin="https://github.com/acme/billing")

    result = run_cli(["link"], second_clone, cli_env)

    assert result.returncode == 3
    assert "another checkout of this project already holds the sidecar branch 'main'" in (
        result.stderr
    )
    assert str(origin_project / ".praxion-state") in result.stderr
    assert "second clone on the same machine is not supported yet" in result.stderr
    assert not (second_clone / ".praxion-state").exists()


def test_absorb_on_a_staged_but_uncommitted_state_move_says_commit_the_adoption(
    local_project: Path, cli_env: dict[str, str]
) -> None:
    """The refusal is right; the advice was not. `git stash` would stash the
    state move itself -- exactly what the operator must commit -- so this
    operator hears the sentence the move already printed instead."""
    (local_project / ".ai-state").mkdir()
    (local_project / ".ai-state" / "note.md").write_text("existing\n", encoding="utf-8")
    _git_ok(local_project, "add", ".ai-state/note.md")
    _git_ok(local_project, "commit", "-q", "-m", "seed project state")
    # The adoption, staged and not yet recorded -- the shape publish leaves
    # behind and the one absorb must name precisely.
    (local_project / ".ai-state" / "note.md").write_text("adopted\n", encoding="utf-8")
    _git_ok(local_project, "add", ".ai-state/note.md")

    result = _run_cli_no_stdin(["absorb", "--yes"], local_project, cli_env)

    assert result.returncode == 3
    assert "Commit the adoption first" in result.stderr
    assert "git stash" not in result.stderr
    assert not (local_project / ".praxion-state").exists()


def test_merge_back_auto_reports_a_plumbing_failure_as_failed_not_as_a_conflict(
    origin_project: Path, cli_env: dict[str, str]
) -> None:
    """git failing *before* it merges anything is not a conflict.

    Reported as one, the operator is sent to `merge-back --from`, which fails
    the same way for the same reason, and the advice never applies. The
    canonical trigger is the environment git itself exports to a commit hook:
    a relative `GIT_INDEX_FILE=.git/index`, which resolves under the state
    mount whose `.git` is a pointer file."""
    _init_ok(origin_project, cli_env)
    worktree = _build_merged_worktree(origin_project, cli_env, "envfail")

    result = run_cli(
        ["merge-back", "--auto"],
        origin_project,
        cli_env,
        extra_env={"GIT_INDEX_FILE": ".git/index", "GIT_DIR": ".git"},
    )

    # The scrub in `_git_runner` means the hook environment no longer reaches
    # git at all: the branch converges instead of being misdiagnosed.
    assert result.returncode == 0, result.stderr + result.stdout
    assert "converged wt/envfail" in result.stdout
    assert "aborted" not in result.stdout
    assert worktree.exists()


def test_commit_names_its_own_verb_when_the_mount_resolves_foreign(
    tmp_path: Path, cli_env: dict[str, str]
) -> None:
    project_a = tmp_path / "repo-a"
    _init_project_repo(project_a, origin="https://github.com/acme/billing")
    _init_ok(project_a, cli_env)

    project_b = tmp_path / "repo-b"
    _init_project_repo(project_b, origin="https://github.com/acme/other")
    (project_b / ".ai-state").symlink_to(project_a / ".praxion-state" / ".ai-state", True)

    result = run_cli(["commit"], project_b, cli_env, _relocated_root(tmp_path))
    assert result.returncode == 3
    assert "Refusing to commit: .ai-state points at a different sidecar." in result.stderr
    assert "Refusing to report" not in result.stderr
