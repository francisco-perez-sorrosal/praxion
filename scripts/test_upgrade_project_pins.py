"""Tests for upgrade_project_pins.sh -- post-upgrade drift reconciliation.

The script re-points a managed project's four version-pinned Praxion surfaces
(finalize-hook symlinks, the observations merge driver, retired merge drivers,
and the onboard-manifest version stamp) to the live plugin install after a
plugin upgrade. These tests drive the real bash script via subprocess against a
synthetic managed project, asserting on observable end state rather than
internals.

Key cases:
  - stale /praxion/<old>/ pins are re-pointed to the live path
  - --check reports drift (exit 1) and mutates nothing
  - a second apply is idempotent (no further changes, --check exits 0)
  - a retired merge driver is unset and dropped from .gitattributes + manifest
  - a dev/self-host symlink (resolves to a real file outside the cache) is left
    untouched -- the self-host safety guard
  - a non-Praxion merge driver is never overwritten

Caller-reconcile cases (--hub-sha; not-yet-implemented op, see scripts/CLAUDE.md
and the upgrade-caller-sha-rewrite ADR):
  - a Praxion-authored, SHA-pinned ci-autofix.yml caller's `uses:` SHA token is
    rewritten in place with everything else byte-preserved, and a second run
    with the same --hub-sha is a no-op
  - a foreign-hub, mutable-ref, self-host (local `./`), or hand-renamed caller
    is left byte-for-byte untouched
  - the cross-model-review.yml caller is added when absent and the policy gate
    is on, and left alone when the gate is off or the caller already exists
  - --hub-sha absent skips the caller surfaces entirely; the four pre-existing
    surfaces still reconcile unchanged
  - the manifest shallow-merge preserves a conditional caller-set key while
    still pruning a retired driver
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "upgrade_project_pins.sh"


def _run(repo: Path, plugin: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_SCRIPT), "--repo-root", str(repo), "--plugin-path", str(plugin), *args],
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def project(tmp_path: Path) -> dict:
    """A managed project with stale 0.8.0 pins and a live 0.9.0 install."""
    repo = tmp_path / "proj"
    (repo / ".ai-state").mkdir(parents=True)
    (repo / ".git" / "hooks").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)

    live = repo / "cache" / "praxion" / "0.9.0"
    stale = repo / "cache" / "praxion" / "0.8.0"
    (live / "scripts").mkdir(parents=True)
    (stale / "scripts").mkdir(parents=True)
    (live / "scripts" / "git-finalize-hook.sh").write_text("#!/usr/bin/env bash\n")

    # stale finalize-hook symlinks, then GC the old cache -> dangling
    for h in ("post-merge", "post-commit", "post-checkout"):
        (repo / ".git" / "hooks" / h).symlink_to(stale / "scripts" / "git-finalize-hook.sh")
    shutil.rmtree(stale)

    _git(
        repo,
        "config",
        "merge.observations-jsonl.driver",
        f"python3 {stale}/scripts/merge_driver_observations.py %O %A %B",
    )
    _git(
        repo,
        "config",
        "merge.memory-json.driver",
        f"python3 {stale}/scripts/merge_driver_memory.py %O %A %B",
    )
    (repo / ".gitattributes").write_text(
        ".ai-state/observations.jsonl merge=observations-jsonl\n"
        ".ai-state/memory.json merge=memory-json\n"
    )
    (repo / ".ai-state" / ".praxion-onboard.json").write_text(
        json.dumps(
            {
                "plugin": "praxion@bit-agora",
                "onboarded_with_version": "0.8.0",
                "onboarded_at": "2026-01-01T00:00:00Z",
                "scope": "user",
                "artifacts": {
                    "hooks": ["pre-commit", "post-merge", "post-commit", "post-checkout"],
                    "merge_drivers": ["observations-jsonl", "memory-json"],
                    "gitattributes": [
                        ".ai-state/observations.jsonl merge=observations-jsonl",
                        ".ai-state/memory.json merge=memory-json",
                    ],
                },
            }
        )
    )
    return {"repo": repo, "live": live}


def _manifest(repo: Path) -> dict:
    return json.loads((repo / ".ai-state" / ".praxion-onboard.json").read_text())


# ---------------------------------------------------------------------------
# Caller-reconcile fixtures (--hub-sha) -- see module docstring.
# ---------------------------------------------------------------------------

_PRAXION_HUB = "francisco-perez-sorrosal/praxion"
_OLD_SHA = "1" * 36 + "abcd"  # 40 hex chars -- the "currently pinned" hub SHA
_NEW_SHA = "2" * 36 + "dcba"  # 40 hex chars -- the "current tip" hub SHA to re-point to

# The real, shipped cross-model-review.yml.tmpl -- used both to mirror into the
# fake plugin install (covers a plugin-path-relative template lookup) and to
# assert the doc-comment header gets stripped on render.
_CROSS_MODEL_TEMPLATE_SRC = (
    Path(__file__).resolve().parent.parent
    / "claude"
    / "project-baseline"
    / "ci-autofix"
    / "cross-model-review.yml.tmpl"
)
_CROSS_MODEL_TEMPLATE_HEADER_MARKER = "Delete this comment after tailoring."

# A rendered ci-autofix.yml caller shape, with a placeholder `uses:` line and
# an operator customization (the extra "Lint" watched workflow) that a naive
# whole-file regenerate would clobber but an edit-only-the-SHA-token rewrite
# must preserve byte-for-byte.
_CALLER_BODY = """name: CI Autofix

on:
  workflow_run:
    workflows: ["Test", "Lint"]  # operator added Lint after onboarding
    types: [completed]

permissions: {}  # least-privilege; the job below grants only what the hub needs

jobs:
  autofix:
    permissions:
      contents: write
      pull-requests: write
      actions: read
      id-token: write
    uses: __USES__
    with:
      policy_path: .github/autofix-policy.yml
    secrets:
      CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
"""


def _render_caller(uses_line: str) -> str:
    return _CALLER_BODY.replace("__USES__", uses_line)


def _praxion_pinned(sha: str) -> str:
    return f"{_PRAXION_HUB}/.github/workflows/reusable-ci-autofix.yml@{sha}"


def _policy_yaml(cross_model_gate: str) -> str:
    return f"""surfaces:
  main_branch: fix-pr

review:
  cross_model_gate: {cross_model_gate}
  reviewer_family: gpt
  on_unavailable: fail-open
"""


def _install_ci_autofix_caller(repo: Path, *, uses_line: str) -> Path:
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    caller = workflows / "ci-autofix.yml"
    caller.write_text(_render_caller(uses_line))
    return caller


def _install_autofix_policy(repo: Path, *, cross_model_gate: str) -> Path:
    policy = repo / ".github" / "autofix-policy.yml"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(_policy_yaml(cross_model_gate))
    return policy


def _mirror_cross_model_template_into_plugin(live: Path) -> None:
    """Places a copy of the real template under the fake plugin install too --
    the reconciler's template-lookup strategy (self-relative to the script vs.
    relative to the resolved plugin path) is an implementation detail this
    plan leaves open; mirroring covers either choice without presuming one."""
    dest = live / "claude" / "project-baseline" / "ci-autofix" / "cross-model-review.yml.tmpl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_CROSS_MODEL_TEMPLATE_SRC.read_text())


@pytest.fixture
def project_with_caller(project) -> dict:
    """`project`, extended with a Praxion-authored, SHA-pinned ci-autofix.yml
    caller (old SHA, plus an operator customization) and an autofix-policy.yml
    with the cross-model review gate on -- the starting state shared by the
    caller-reconcile tests below."""
    repo, live = project["repo"], project["live"]
    _install_ci_autofix_caller(repo, uses_line=_praxion_pinned(_OLD_SHA))
    _install_autofix_policy(repo, cross_model_gate="agent-prs")
    _mirror_cross_model_template_into_plugin(live)
    return project


def test_check_reports_drift_without_mutating(project):
    repo, live = project["repo"], project["live"]
    before = os.readlink(repo / ".git" / "hooks" / "post-merge")
    r = _run(repo, live, "--check")
    assert r.returncode == 1, r.stderr
    # nothing mutated
    assert os.readlink(repo / ".git" / "hooks" / "post-merge") == before
    assert _manifest(repo)["onboarded_with_version"] == "0.8.0"


def test_apply_repoints_all_surfaces(project):
    repo, live = project["repo"], project["live"]
    r = _run(repo, live)
    assert r.returncode == 0, r.stderr
    live_hook = str(live / "scripts" / "git-finalize-hook.sh")
    for h in ("post-merge", "post-commit", "post-checkout"):
        assert os.readlink(repo / ".git" / "hooks" / h) == live_hook
    assert (
        _git(repo, "config", "--get", "merge.observations-jsonl.driver")
        == f"python3 {live}/scripts/merge_driver_observations.py %O %A %B"
    )
    assert _manifest(repo)["onboarded_with_version"] == "0.9.0"


def test_retired_driver_removed(project):
    repo, live = project["repo"], project["live"]
    _run(repo, live)
    # driver unset
    rc = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "merge.memory-json.driver"]
    ).returncode
    assert rc != 0
    # dropped from .gitattributes and manifest
    assert "memory-json" not in (repo / ".gitattributes").read_text()
    assert _manifest(repo)["artifacts"]["merge_drivers"] == ["observations-jsonl"]


def test_apply_is_idempotent(project):
    repo, live = project["repo"], project["live"]
    _run(repo, live)
    second = _run(repo, live)
    assert "Already current" in second.stdout, second.stdout
    assert _run(repo, live, "--check").returncode == 0


def test_dry_run_mutates_nothing(project):
    repo, live = project["repo"], project["live"]
    before = os.readlink(repo / ".git" / "hooks" / "post-merge")
    r = _run(repo, live, "--dry-run")
    assert r.returncode == 0
    assert "would change" in r.stdout
    assert os.readlink(repo / ".git" / "hooks" / "post-merge") == before
    assert _manifest(repo)["onboarded_with_version"] == "0.8.0"


# ---------------------------------------------------------------------------
# Hook-chain composition (P0) -- the [1b] block delegating to
# scripts/install_git_hooks.py, layered on top of the finalize-hook
# staleness loop above rather than replacing it (self-host/cache-path
# staleness detection has no equivalent in install_git_hooks.py, which
# knows nothing about plugin *versions* -- only about hooksPath/slot shape).
# ---------------------------------------------------------------------------


def test_foreign_hookspath_check_reports_drift_without_mutating(project):
    """core.hooksPath set to a directory Praxion does not own (husky-style):
    [1/4] must report the composition drift under --check and mutate
    nothing -- the exact defect this milestone exists to fix (a foreign
    hooksPath the pre-P0 readlink loop had no notion of at all)."""
    repo, live = project["repo"], project["live"]
    delegate_dir = repo / ".husky" / "_"
    delegate_dir.mkdir(parents=True)
    _git(repo, "config", "core.hooksPath", ".husky/_")

    r = _run(repo, live, "--check")
    assert r.returncode == 1
    assert "hook chain: drift" in r.stdout
    assert _git(repo, "config", "--get", "core.hooksPath") == ".husky/_"


def test_foreign_hookspath_apply_delegates_to_heal_and_converges(project):
    """Applying re-points core.hooksPath at a Praxion wrapper directory that
    delegates back to `.husky/_`; running apply twice more performs no
    further core.hooksPath writes (REQ-11's non-oscillation guarantee)."""
    repo, live = project["repo"], project["live"]
    delegate_dir = repo / ".husky" / "_"
    delegate_dir.mkdir(parents=True)
    _git(repo, "config", "core.hooksPath", ".husky/_")

    r = _run(repo, live)
    assert r.returncode == 0, r.stderr
    assert "hook chain:" in r.stdout
    wrapper_hooks_path = _git(repo, "config", "--get", "core.hooksPath")
    assert wrapper_hooks_path != ".husky/_"
    assert wrapper_hooks_path.endswith("praxion-hooks")

    # Two more runs: core.hooksPath must not oscillate back toward .husky/_,
    # and no further writes should occur.
    for _ in range(2):
        again = _run(repo, live)
        assert again.returncode == 0, again.stderr
        assert _git(repo, "config", "--get", "core.hooksPath") == wrapper_hooks_path


def test_dev_self_host_symlink_left_untouched(project):
    """A finalize hook that resolves to a real file outside the /praxion/ cache is
    a dev/self-host install and must not be re-pointed."""
    repo, live = project["repo"], project["live"]
    dev = repo / "devtree" / "scripts"
    dev.mkdir(parents=True)
    (dev / "git-finalize-hook.sh").write_text("#!/usr/bin/env bash\n")
    hp = repo / ".git" / "hooks" / "post-merge"
    hp.unlink()
    hp.symlink_to(dev / "git-finalize-hook.sh")
    _run(repo, live)
    # unchanged: still points at the dev tree, not the live cache
    assert os.readlink(hp) == str(dev / "git-finalize-hook.sh")


def test_non_praxion_driver_not_overwritten(project):
    repo, live = project["repo"], project["live"]
    _git(repo, "config", "merge.observations-jsonl.driver", "my-custom-driver %O")
    r = _run(repo, live)
    assert r.returncode == 0
    assert _git(repo, "config", "--get", "merge.observations-jsonl.driver") == "my-custom-driver %O"
    assert "refusing to overwrite" in r.stdout


# ---------------------------------------------------------------------------
# IF-02: under sidecar placement the merge driver that matters lives in the
# SIDECAR's own .git/config, not the project's -- `praxion-sidecar link` is
# the sole reconciler for that side.
# ---------------------------------------------------------------------------

# The real, working scripts/ tree -- used as the "live plugin install" for
# this fixture only, since the reconcile path under test shells out to the
# real `praxion-sidecar link`, whose sibling-module imports (`_sidecar_*`)
# a minimal fake plugin dir cannot cheaply reproduce.
_REAL_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent


def _build_sidecar_project(tmp_path: Path, *, stale_driver: str) -> Path:
    """A real, minimal sidecar-owned project: sidecar repo + `git worktree`
    mount + manifest + shadowed `.ai-state` -- mirrors `test_state_repo.py`'s
    own fixture pattern, rebuilt locally to keep this module import-
    independent. The SIDECAR's own merge driver (not the project's, which
    never gets one) starts stale."""
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "proj"

    sidecar_root.mkdir(parents=True)
    subprocess.run(["git", "-C", str(sidecar_root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(sidecar_root), "config", "user.email", "s@s.s"], check=True)
    subprocess.run(["git", "-C", str(sidecar_root), "config", "user.name", "s"], check=True)
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("# design\n")
    subprocess.run(["git", "-C", str(sidecar_root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(sidecar_root), "commit", "-q", "-m", "seed"], check=True)
    subprocess.run(["git", "-C", str(sidecar_root), "checkout", "-q", "--detach"], check=True)

    project_root.mkdir(parents=True)
    subprocess.run(["git", "-C", str(project_root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(project_root), "config", "user.email", "p@p.p"], check=True)
    subprocess.run(["git", "-C", str(project_root), "config", "user.name", "p"], check=True)

    mount_dir = project_root / ".praxion"
    subprocess.run(
        ["git", "-C", str(sidecar_root), "worktree", "add", "-q", str(mount_dir), "main"],
        check=True,
    )

    manifest_path = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest_path.write_text(
        "schema: 1\n"
        "project:\n"
        "  origin: null\n"
        '  id: "local--abc123def456"\n'
        f'  roots: ["{project_root.resolve()}"]\n'
        "paths: {}\n"
        "excludes: []\n"
        "autocommit: manual\n"
        "remote: null\n"
    )

    (project_root / ".ai-state").symlink_to(
        Path(".praxion") / ".ai-state", target_is_directory=True
    )

    subprocess.run(
        ["git", "-C", str(sidecar_root), "config", "merge.observations-jsonl.driver", stale_driver],
        check=True,
    )
    return project_root


def _sidecar_driver(project_root: Path) -> str:
    return _git(
        project_root / ".praxion",
        "config",
        "--get",
        "merge.observations-jsonl.driver",
    )


def test_sidecar_placement_apply_reconciles_the_sidecar_driver_via_link(tmp_path: Path) -> None:
    stale = f"python3 {tmp_path / 'gone' / 'scripts' / 'merge_driver_observations.py'} %O %A %B"
    project_root = _build_sidecar_project(tmp_path, stale_driver=stale)
    project_driver_before = subprocess.run(
        ["git", "-C", str(project_root), "config", "--get", "merge.observations-jsonl.driver"],
        capture_output=True,
        text=True,
    )

    r = _run(project_root, _REAL_SCRIPTS_ROOT)

    assert r.returncode == 0, r.stderr
    live_driver = f"python3 {_REAL_SCRIPTS_ROOT}/scripts/merge_driver_observations.py %O %A %B"
    assert _sidecar_driver(project_root) == live_driver, (
        "the sidecar's own driver was not re-pointed by the reconcile"
    )
    # the PROJECT repository never owns .ai-state/ under sidecar placement --
    # its own git config must stay untouched (empty: no driver was ever set
    # there).
    assert project_driver_before.returncode != 0, (
        "test setup bug: the project repo already had a driver configured"
    )
    project_driver_after = subprocess.run(
        ["git", "-C", str(project_root), "config", "--get", "merge.observations-jsonl.driver"],
        capture_output=True,
        text=True,
    )
    assert project_driver_after.returncode != 0, (
        "the project repository's own git config was mutated -- sidecar placement must "
        "reconcile the sidecar's config, never the project's"
    )


def test_sidecar_placement_check_reports_drift_without_mutating(tmp_path: Path) -> None:
    stale = f"python3 {tmp_path / 'gone' / 'scripts' / 'merge_driver_observations.py'} %O %A %B"
    project_root = _build_sidecar_project(tmp_path, stale_driver=stale)

    r = _run(project_root, _REAL_SCRIPTS_ROOT, "--check")

    assert r.returncode == 1, r.stdout
    assert _sidecar_driver(project_root) == stale, "--check must never mutate the sidecar's driver"


def test_upgrade_preserves_the_mode_stamp_field(project):
    """An upgrade run must rewrite only `onboarded_with_version` -- never `mode`.

    The onboarding skill's Sub-step 5b.t stamp addition (`"mode": "full" |
    "hackathon"`) records whether a project graduated from hackathon mode. A
    pins upgrade that clobbered this field on every run would silently
    un-promote every hackathon-graduated project the next time its plugin
    version bumped -- the single highest-impact unmitigated risk flagged for
    this reconciler.
    """
    repo, live = project["repo"], project["live"]
    manifest_path = repo / ".ai-state" / ".praxion-onboard.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["mode"] = "hackathon"
    manifest_path.write_text(json.dumps(manifest))

    r = _run(repo, live)

    assert r.returncode == 0, r.stderr
    after = _manifest(repo)
    assert after["mode"] == "hackathon"
    assert after["onboarded_with_version"] == "0.9.0"


def test_upgrade_leaves_an_absent_mode_field_absent(project):
    """Back-compat: a pre-mode manifest must not gain a fabricated `mode` key.

    Onboarding treats an absent `mode` as `"full"` by convention (additive,
    back-compat stamp schema) -- the reconciler must not itself write that
    default into the manifest, which would make a project's stamp diverge
    from what onboarding actually recorded.
    """
    repo, live = project["repo"], project["live"]
    assert "mode" not in _manifest(repo)

    r = _run(repo, live)

    assert r.returncode == 0, r.stderr
    assert "mode" not in _manifest(repo)


def test_refuses_non_onboarded_project(tmp_path: Path):
    repo = tmp_path / "bare"
    (repo / ".git").mkdir(parents=True)
    live = tmp_path / "cache" / "praxion" / "0.9.0" / "scripts"
    live.mkdir(parents=True)
    r = _run(repo, live.parent)
    assert r.returncode == 1
    assert "not a Praxion-onboarded project" in r.stderr


# ---------------------------------------------------------------------------
# --hub-sha caller-reconcile op (not yet implemented -- these are RED until
# the op lands; see the upgrade-caller-sha-rewrite ADR).
# ---------------------------------------------------------------------------


def test_praxion_caller_sha_token_rewrite_is_byte_scoped(project_with_caller):
    """The only byte difference in a re-pointed ci-autofix.yml caller is the
    40-hex SHA token itself -- every other line (including an operator's own
    customization) survives untouched."""
    repo, live = project_with_caller["repo"], project_with_caller["live"]
    caller = repo / ".github" / "workflows" / "ci-autofix.yml"
    before = caller.read_text()
    expected = before.replace(_OLD_SHA, _NEW_SHA)

    r = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert r.returncode == 0, r.stderr
    assert caller.read_text() == expected


def test_praxion_caller_sha_rewrite_is_idempotent(project_with_caller):
    repo, live = project_with_caller["repo"], project_with_caller["live"]
    caller = repo / ".github" / "workflows" / "ci-autofix.yml"

    _run(repo, live, "--hub-sha", _NEW_SHA)
    after_first = caller.read_text()
    second = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert "Already current" in second.stdout, second.stdout
    assert caller.read_text() == after_first


_NON_MATCHING_CALLER_SHAPES = [
    pytest.param(
        f"other-org/other-repo/.github/workflows/reusable-ci-autofix.yml@{_OLD_SHA}",
        id="foreign-hub",
    ),
    pytest.param(
        f"{_PRAXION_HUB}/.github/workflows/reusable-ci-autofix.yml@main",
        id="mutable-branch-ref",
    ),
    pytest.param(
        "./.github/workflows/reusable-ci-autofix.yml",
        id="self-host-local-ref",
    ),
    pytest.param(
        f"{_PRAXION_HUB}/.github/workflows/reusable-ci-autofix-custom.yml@{_OLD_SHA}",
        id="hand-renamed-workflow-file",
    ),
]


@pytest.mark.parametrize("uses_line", _NON_MATCHING_CALLER_SHAPES)
def test_non_praxion_caller_shapes_left_untouched(project, uses_line):
    """A caller whose `uses:` line does not match the Praxion-hub,
    40-hex-pinned shape is never rewritten -- foreign hub, mutable ref,
    self-host local ref, and a hand-renamed workflow file all fall out as
    'leave alone'."""
    repo, live = project["repo"], project["live"]
    caller = _install_ci_autofix_caller(repo, uses_line=uses_line)
    before = caller.read_text()

    r = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert r.returncode == 0, r.stderr
    assert caller.read_text() == before
    assert "ci-autofix.yml" in r.stdout, r.stdout


def test_multi_match_caller_left_untouched(project):
    """A caller with TWO Praxion-pinned reusable-ci-autofix refs (an operator
    matrix/canary job) is ambiguous: the shape match guarantees >=1, not exactly
    one, so a naive single-value extraction would yield a multi-line token and
    crash the rewrite (sed: unterminated substitute pattern) mid-apply. Instead
    the reconcile leaves the file byte-unchanged, reports it, and exits 0."""
    repo, live = project["repo"], project["live"]
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    caller = workflows / "ci-autofix.yml"
    caller.write_text(
        "name: CI Autofix\n"
        "jobs:\n"
        "  autofix:\n"
        f"    uses: {_praxion_pinned(_OLD_SHA)}\n"
        "  canary:\n"
        f"    uses: {_praxion_pinned('3' * 36 + 'beef')}\n"
    )
    before = caller.read_text()

    r = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert r.returncode == 0, r.stderr
    assert caller.read_text() == before
    assert "ambiguous" in r.stdout, r.stdout


def test_cross_model_caller_added_when_absent_and_gate_on(project_with_caller):
    repo, live = project_with_caller["repo"], project_with_caller["live"]
    cross_model = repo / ".github" / "workflows" / "cross-model-review.yml"

    r = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert r.returncode == 0, r.stderr
    assert cross_model.exists()
    content = cross_model.read_text()
    # Unrendered template placeholders must be gone; `${{ }}` GitHub Actions
    # expressions (e.g. `${{ secrets.CURSOR_API_KEY }}`) are legitimate and stay.
    assert "{{PRAXION_HUB}}" not in content
    assert "{{HUB_SHA}}" not in content
    assert _PRAXION_HUB in content
    assert _NEW_SHA in content
    assert _CROSS_MODEL_TEMPLATE_HEADER_MARKER not in content


def test_cross_model_caller_not_added_when_gate_off(project):
    repo, live = project["repo"], project["live"]
    _install_ci_autofix_caller(repo, uses_line=_praxion_pinned(_OLD_SHA))
    _install_autofix_policy(repo, cross_model_gate="off")
    _mirror_cross_model_template_into_plugin(live)
    cross_model = repo / ".github" / "workflows" / "cross-model-review.yml"

    r = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert r.returncode == 0, r.stderr
    assert not cross_model.exists()


def test_cross_model_caller_not_overwritten_when_already_present(project_with_caller):
    repo, live = project_with_caller["repo"], project_with_caller["live"]
    cross_model = repo / ".github" / "workflows" / "cross-model-review.yml"
    cross_model.write_text("# operator-tailored cross-model caller\nname: Custom\n")
    before = cross_model.read_text()

    r = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert r.returncode == 0, r.stderr
    assert cross_model.read_text() == before


def test_hub_sha_absent_skips_caller_surfaces_but_reconciles_existing_four(project_with_caller):
    """Backward compatibility: without --hub-sha, the caller surfaces are
    skipped entirely, and the four pre-existing version-pinned surfaces
    reconcile exactly as they did before this op existed."""
    repo, live = project_with_caller["repo"], project_with_caller["live"]
    caller = repo / ".github" / "workflows" / "ci-autofix.yml"
    cross_model = repo / ".github" / "workflows" / "cross-model-review.yml"
    before_caller = caller.read_text()

    r = _run(repo, live)

    assert r.returncode == 0, r.stderr
    assert caller.read_text() == before_caller
    assert not cross_model.exists()
    live_hook = str(live / "scripts" / "git-finalize-hook.sh")
    for h in ("post-merge", "post-commit", "post-checkout"):
        assert os.readlink(repo / ".git" / "hooks" / h) == live_hook
    assert _manifest(repo)["onboarded_with_version"] == "0.9.0"


def test_manifest_merge_preserves_caller_set_key_while_pruning_retired_driver(project_with_caller):
    """The manifest stamp shallow-merges: an onboard-recorded conditional
    caller-set key survives an upgrade, while a retired core driver is still
    pruned -- a wholesale overwrite would erase the former; this proves it
    doesn't."""
    repo, live = project_with_caller["repo"], project_with_caller["live"]
    manifest_path = repo / ".ai-state" / ".praxion-onboard.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"]["ci_autofix"] = ["ci-autofix.yml", "autofix-policy.yml"]
    manifest_path.write_text(json.dumps(manifest))

    r = _run(repo, live, "--hub-sha", _NEW_SHA)

    assert r.returncode == 0, r.stderr
    after = _manifest(repo)["artifacts"]
    assert after["ci_autofix"] == ["ci-autofix.yml", "autofix-policy.yml"]
    assert after["merge_drivers"] == ["observations-jsonl"]


# ---- labels-taxonomy baseline (surface 6, folded in from the command layer) --

_LABELS_TEMPLATE = (
    "# Praxion-owned baseline block\n"
    "baseline:\n"
    '  - { name: new-label, color: "5319e7" }\n'
    "additional: []\n"
)


def _install_labels_surface(live: Path, repo: Path, *, stale: bool) -> Path:
    tmpl = live / "claude" / "project-baseline" / "labels" / "labels.yml.tmpl"
    tmpl.parent.mkdir(parents=True, exist_ok=True)
    tmpl.write_text(_LABELS_TEMPLATE)
    manifest = repo / ".github" / "labels.yml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    baseline_item = "old-label" if stale else "new-label"
    manifest.write_text(
        "# Praxion-owned baseline block\n"
        "baseline:\n"
        f'  - {{ name: {baseline_item}, color: "5319e7" }}\n'
        "additional:\n"
        '  - { name: project-own-label, color: "ffffff" }\n'
    )
    return manifest


def test_labels_baseline_check_reports_stale_without_mutating(project):
    """--check on a stale labels baseline reports drift and mutates nothing --
    the mode-blindness the old command-layer step had (it refreshed even under
    --check) must not survive the fold into the script."""
    repo, live = project["repo"], project["live"]
    manifest = _install_labels_surface(live, repo, stale=True)
    before = manifest.read_text()

    r = _run(repo, live, "--check")

    assert r.returncode == 1
    assert "labels.yml: baseline STALE" in r.stdout
    assert manifest.read_text() == before


def test_labels_baseline_apply_refreshes_and_preserves_additional(project):
    repo, live = project["repo"], project["live"]
    manifest = _install_labels_surface(live, repo, stale=True)

    r = _run(repo, live)

    assert r.returncode == 0, r.stderr
    text = manifest.read_text()
    assert "new-label" in text
    assert "old-label" not in text
    assert "project-own-label" in text
    staged = _git(repo, "diff", "--cached", "--name-only")
    assert ".github/labels.yml" in staged


def test_labels_baseline_current_is_noop(project):
    repo, live = project["repo"], project["live"]
    manifest = _install_labels_surface(live, repo, stale=False)
    before = manifest.read_text()

    r = _run(repo, live)  # apply run also reconciles the fixture's stale core pins

    assert r.returncode == 0, r.stdout + r.stderr
    assert "labels.yml: baseline current" in r.stdout
    assert manifest.read_text() == before
    assert _run(repo, live, "--check").returncode == 0


def test_labels_manifest_absent_is_a_clean_skip(project):
    repo, live = project["repo"], project["live"]
    r = _run(repo, live)
    assert r.returncode == 0, r.stderr
    assert "labels.yml: absent" in r.stdout


# ---- AaC surfaces (surface 7, delegated to reconcile_aac_surfaces.py) -------


def test_aac_surfaces_reconciled_through_the_script(project):
    """End-to-end wiring: a stale-namespace architecture.yml is re-pointed by
    the [aac] section, the drift is folded into the change count (--check exits
    1), and a post-apply --check comes back clean."""
    repo, live = project["repo"], project["live"]
    wf = repo / ".github" / "workflows" / "architecture.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text("      Load the i-am:architect-validator agent. Run in --mode=pre-merge\n")

    check = _run(repo, live, "--check")
    assert check.returncode == 1
    assert "architecture.yml: STALE" in check.stdout

    apply = _run(repo, live)
    assert apply.returncode == 0, apply.stderr
    assert "Load the praxion:architect-validator agent" in wf.read_text()

    recheck = _run(repo, live, "--check")
    assert recheck.returncode == 0, recheck.stdout


# ---- self-host classification ordering --------------------------------------


def test_self_host_symlink_in_a_praxion_named_dir_left_untouched(project, tmp_path):
    """The real self-host shape: a checkout literally named `praxion`, so the
    broad */praxion/* glob matches. The dev/self-host branch must win -- before
    the ordering fix every self-host symlink was misclassified as stale (the
    original fixture path just happened not to contain /praxion/)."""
    repo, live = project["repo"], project["live"]
    selfhost = tmp_path / "dev" / "praxion" / "scripts"
    selfhost.mkdir(parents=True)
    target = selfhost / "git-finalize-hook.sh"
    target.write_text("#!/usr/bin/env bash\n")
    for h in ("post-merge", "post-commit", "post-checkout"):
        hook = repo / ".git" / "hooks" / h
        hook.unlink()
        hook.symlink_to(target)

    r = _run(repo, live)

    assert r.returncode == 0, r.stderr
    assert "skip (dev/self-host symlink" in r.stdout
    for h in ("post-merge", "post-commit", "post-checkout"):
        assert (repo / ".git" / "hooks" / h).readlink() == target


def test_live_but_old_plugin_cache_symlink_still_repointed(project, tmp_path):
    """The inverse guard for the ordering fix: an old cache install that has
    NOT been garbage-collected yet (target exists, basename matches) must not
    ride the self-host branch -- the /plugins/cache/ shape identifies it."""
    repo, live = project["repo"], project["live"]
    old_cache = tmp_path / "plugins" / "cache" / "bit-agora" / "praxion" / "0.8.0" / "scripts"
    old_cache.mkdir(parents=True)
    target = old_cache / "git-finalize-hook.sh"
    target.write_text("#!/usr/bin/env bash\n")
    for h in ("post-merge", "post-commit", "post-checkout"):
        hook = repo / ".git" / "hooks" / h
        hook.unlink()
        hook.symlink_to(target)

    r = _run(repo, live)

    assert r.returncode == 0, r.stderr
    for h in ("post-merge", "post-commit", "post-checkout"):
        resolved = (repo / ".git" / "hooks" / h).readlink()
        assert resolved == live / "scripts" / "git-finalize-hook.sh"


def test_i_am_era_driver_registration_is_repointed(project):
    """A merge driver registered by the pre-rename i-am plugin lives at a cache
    path with no /praxion/ token; the shape */plugins/cache/* must classify it
    as Praxion-managed and re-register -- 'refusing to overwrite' here left
    every pre-rename project's driver permanently stale."""
    repo, live = project["repo"], project["live"]
    _git(
        repo,
        "config",
        "merge.observations-jsonl.driver",
        "python3 /home/u/.claude/plugins/cache/bit-agora/i-am/0.5.0/scripts/merge_driver_observations.py %O %A %B",
    )

    r = _run(repo, live)

    assert r.returncode == 0, r.stderr
    current = _git(repo, "config", "--get", "merge.observations-jsonl.driver")
    assert str(live) in current
