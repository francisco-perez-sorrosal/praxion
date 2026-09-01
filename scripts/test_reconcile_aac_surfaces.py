"""Tests for reconcile_aac_surfaces.py -- AaC instantiated-surface reconciliation.

Drives the real script via subprocess against a synthetic managed project,
asserting on observable end state. The legacy Block D fixture below is the
verbatim pre-fix template every onboarded project received: its PLUGIN_ROOT
resolution iterates the top level of installed_plugins.json (whose first entry
is the int `version`), swallows the AttributeError, and comes back empty -- so
the gate always skipped. These tests pin both the structural repair of that
shape and the live-fire behavior of the fixed fragment, which is the test that
was missing when the broken template shipped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent
_SCRIPT = _SCRIPTS / "reconcile_aac_surfaces.py"
_TEMPLATE = _SCRIPTS.parent / "claude" / "aac-templates" / "precommit-block-d.sh.frag"
_WORKFLOW_TEMPLATE = _SCRIPTS.parent / "claude" / "aac-templates" / "architecture.yml.tmpl"

# Verbatim pre-fix Block D as installed by onboarding before the resolution fix
# (both historical template variants share this structure; only the namespace
# token in the skip notice differed).
LEGACY_BLOCK_D = r"""# ---------------------------------------------------------------------------
# Block D: AaC golden-rule gate
#
# HOW TO USE: Append this fragment to your existing .git/hooks/pre-commit
# AFTER any prior blocks (Blocks A, B, C if present). Do not replace existing
# blocks. Installed by /onboard-project Phase 8b.
#
# Trigger: staged paths touch architectural surfaces (docs/diagrams/, *.c4,
# ARCHITECTURE.md, docs/architecture.md).
#
# Blocks the commit if a generated artifact was edited without staging the
# corresponding source change and without an adjacent override comment.
#
# Script resolution: ${PLUGIN_ROOT} is derived at hook-run time from
# ~/.claude/plugins/installed_plugins.json (same pattern as the id-citation
# block installed in Phase 4). If the plugin is not installed, Block D exits
# cleanly (skip-gracefully guard below).
# ---------------------------------------------------------------------------

STAGED_AAC="$(git diff --cached --name-only --diff-filter=ACMR \
    | grep -E '^(docs/diagrams/|.*\.c4$|.*ARCHITECTURE\.md$|docs/architecture\.md$)' \
    || true)"

if [ -n "$STAGED_AAC" ]; then
    # Resolve plugin install path from installed_plugins.json
    PLUGIN_ROOT=""
    PLUGINS_JSON="$HOME/.claude/plugins/installed_plugins.json"
    if [ -f "$PLUGINS_JSON" ]; then
        PLUGIN_ROOT="$(python3 -c "
import json, sys
try:
    data = json.load(open('$PLUGINS_JSON'))
    # installed_plugins.json is a dict keyed by plugin name;
    # value is the install path string or an object with 'path'
    for _name, entry in data.items():
        path = entry if isinstance(entry, str) else entry.get('path', '')
        if path:
            print(path)
            break
except Exception:
    pass
" 2>/dev/null || true)"
    fi

    # Skip-gracefully guard: if plugin root not found, exit 0 (non-blocking)
    if [ -z "$PLUGIN_ROOT" ]; then
        echo "info: praxion plugin not found in installed_plugins.json — skipping Block D golden-rule gate"
    else
        AAC_SCRIPT="${PLUGIN_ROOT}/scripts/check_aac_golden_rule.py"
        if [ ! -f "$AAC_SCRIPT" ]; then
            echo "info: check_aac_golden_rule.py not found in plugin — skipping Block D golden-rule gate"
        else
            AAC_EXIT=0
            python3 "$AAC_SCRIPT" --mode=gate || AAC_EXIT=$?
            if [ "$AAC_EXIT" -ne 0 ]; then
                cat >&2 <<'BLOCK_D_EOF'
error: AaC golden-rule violation(s) detected in staged files.
BLOCK_D_EOF
                exit 1
            fi
        fi
    fi
fi
"""

HOOK_PREFIX = "#!/usr/bin/env bash\n# Block A: something earlier\necho block-a-ran\n\n"
HOOK_SUFFIX = "\n# trailing content after Block D\necho after-block-d\n"


def _run(repo: Path, plugin: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "python3",
            str(_SCRIPT),
            "--plugin-root",
            str(plugin),
            "--repo-root",
            str(repo),
            *args,
        ],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    (repo / ".git" / "hooks").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    return repo


def _install_hook(repo: Path, block_d: str, *, suffix: str = HOOK_SUFFIX) -> Path:
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(HOOK_PREFIX + block_d + suffix)
    hook.chmod(0o755)
    return hook


def _fake_plugin(tmp_path: Path) -> Path:
    """A plugin dir with no templates, so the script falls back to the checkout."""
    plugin = tmp_path / "plugin"
    plugin.mkdir(exist_ok=True)
    return plugin


# ---- Block D structural repair ---------------------------------------------


def test_broken_block_d_is_repaired_in_place(repo, tmp_path):
    hook = _install_hook(repo, LEGACY_BLOCK_D)
    result = _run(repo, _fake_plugin(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "repaired" in result.stdout
    text = hook.read_text()
    assert "data.items()" not in text
    assert ".plugins[$k][0].installPath" in text
    # everything around the region is byte-preserved
    assert text.startswith(HOOK_PREFIX)
    assert text.endswith(HOOK_SUFFIX)
    # the repaired region now equals the shipped template
    assert _TEMPLATE.read_text().rstrip("\n") in text


def test_check_reports_broken_block_d_without_mutating(repo, tmp_path):
    hook = _install_hook(repo, LEGACY_BLOCK_D)
    before = hook.read_text()
    result = _run(repo, _fake_plugin(tmp_path), "--mode", "check")
    assert result.returncode == 1
    assert "BROKEN" in result.stdout
    assert hook.read_text() == before


def test_dry_run_mutates_nothing(repo, tmp_path):
    hook = _install_hook(repo, LEGACY_BLOCK_D)
    before = hook.read_text()
    result = _run(repo, _fake_plugin(tmp_path), "--mode", "dry-run")
    assert result.returncode == 0
    assert "would replace" in result.stdout
    assert hook.read_text() == before


def test_repair_is_idempotent(repo, tmp_path):
    _install_hook(repo, LEGACY_BLOCK_D)
    plugin = _fake_plugin(tmp_path)
    assert _run(repo, plugin).returncode == 0
    second = _run(repo, plugin, "--mode", "check")
    assert second.returncode == 0
    assert "pre-commit Block D: current" in second.stdout


def test_namespace_only_drift_patches_single_line(repo, tmp_path):
    # Simulate a future rename: current structure, stale namespace token.
    stale = _TEMPLATE.read_text().replace(
        "info: praxion plugin not found", "info: oldname plugin not found"
    )
    hook = _install_hook(repo, stale)
    result = _run(repo, _fake_plugin(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "re-pointed to 'praxion'" in result.stdout
    text = hook.read_text()
    assert "info: praxion plugin not found" in text
    assert "oldname" not in text
    # single-line patch, not a region replace: the rest of the block untouched
    assert text.startswith(HOOK_PREFIX)
    assert text.endswith(HOOK_SUFFIX)


def test_hand_edited_block_d_left_untouched(repo, tmp_path):
    edited = _TEMPLATE.read_text().replace("AAC_EXIT=0\n", "AAC_EXIT=0  # operator note\n")
    hook = _install_hook(repo, edited)
    before = hook.read_text()
    result = _run(repo, _fake_plugin(tmp_path))
    assert result.returncode == 0
    assert "left untouched" in result.stdout
    assert hook.read_text() == before


def test_no_block_d_is_a_clean_skip(repo, tmp_path):
    _install_hook(repo, "# just a plain hook\n", suffix="")
    result = _run(repo, _fake_plugin(tmp_path))
    assert result.returncode == 0
    assert "not installed" in result.stdout
    assert "aac-changes: 0" in result.stdout


# ---- architecture.yml namespace token --------------------------------------


def _install_workflow(repo: Path, namespace: str) -> Path:
    wf = repo / ".github" / "workflows" / "architecture.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        "name: Architecture\njobs:\n  sweep:\n    steps:\n"
        f"      - run: |\n          Load the {namespace}:architect-validator agent. Run in --mode=pre-merge\n"
    )
    return wf


def test_workflow_namespace_repointed_and_staged(repo, tmp_path):
    wf = _install_workflow(repo, "i-am")
    result = _run(repo, _fake_plugin(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "Load the praxion:architect-validator agent" in wf.read_text()
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    ).stdout
    assert ".github/workflows/architecture.yml" in staged


def test_workflow_no_stage_flag_skips_git_add(repo, tmp_path):
    _install_workflow(repo, "i-am")
    result = _run(repo, _fake_plugin(tmp_path), "--no-stage")
    assert result.returncode == 0
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    ).stdout
    assert ".github/workflows/architecture.yml" not in staged


def test_current_workflow_reports_current(repo, tmp_path):
    _install_workflow(repo, "praxion")
    result = _run(repo, _fake_plugin(tmp_path), "--mode", "check")
    assert result.returncode == 0
    assert "architecture.yml: current" in result.stdout


def test_changes_count_line_always_emitted(repo, tmp_path):
    result = _run(repo, _fake_plugin(tmp_path))
    assert "aac-changes: 0" in result.stdout


def test_plugin_root_templates_win_over_checkout_fallback(repo, tmp_path):
    plugin = _fake_plugin(tmp_path)
    tmpl_dir = plugin / "claude" / "aac-templates"
    tmpl_dir.mkdir(parents=True)
    shutil.copy(_WORKFLOW_TEMPLATE, tmpl_dir / "architecture.yml.tmpl")
    renamed = (
        (tmpl_dir / "architecture.yml.tmpl")
        .read_text()
        .replace("praxion:architect-validator", "nextname:architect-validator")
    )
    (tmpl_dir / "architecture.yml.tmpl").write_text(renamed)
    wf = _install_workflow(repo, "praxion")
    result = _run(repo, plugin)
    assert result.returncode == 0, result.stderr
    assert "Load the nextname:architect-validator agent" in wf.read_text()


# ---- live-fire: the fixed Block D actually gates ---------------------------


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not available")
def test_fixed_block_d_resolves_plugin_and_gates(repo, tmp_path):
    """The regression test the original template never had: with a real-shaped
    installed_plugins.json, the fixed fragment resolves PLUGIN_ROOT, invokes
    the gate script, and propagates its failure -- instead of skipping."""
    plugin = tmp_path / "installed-plugin"
    (plugin / "scripts").mkdir(parents=True)
    marker = tmp_path / "gate-ran"
    (plugin / "scripts" / "check_aac_golden_rule.py").write_text(
        f"import pathlib, sys\npathlib.Path({str(marker)!r}).write_text('ran')\nsys.exit(1)\n"
    )
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {"praxion@bit-agora": [{"installPath": str(plugin), "scope": "user"}]},
            }
        )
    )

    hook = _install_hook(repo, _TEMPLATE.read_text(), suffix="")
    (repo / "docs").mkdir()
    (repo / "docs" / "architecture.md").write_text("# arch\n")
    subprocess.run(["git", "-C", str(repo), "add", "docs/architecture.md"], check=True)

    env = dict(os.environ, HOME=str(home))
    result = subprocess.run(["bash", str(hook)], cwd=repo, capture_output=True, text=True, env=env)
    assert marker.exists(), "gate script was never invoked -- resolution failed"
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not available")
def test_legacy_block_d_demonstrates_the_silent_skip(repo, tmp_path):
    """Inverse guard: the legacy fragment run under the same conditions skips
    the gate (exit 0) -- proving the repair changes observable behavior."""
    plugin = tmp_path / "installed-plugin"
    (plugin / "scripts").mkdir(parents=True)
    (plugin / "scripts" / "check_aac_golden_rule.py").write_text("import sys; sys.exit(1)\n")
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {"praxion@bit-agora": [{"installPath": str(plugin), "scope": "user"}]},
            }
        )
    )
    hook = _install_hook(repo, LEGACY_BLOCK_D, suffix="")
    (repo / "docs").mkdir()
    (repo / "docs" / "architecture.md").write_text("# arch\n")
    subprocess.run(["git", "-C", str(repo), "add", "docs/architecture.md"], check=True)

    env = dict(os.environ, HOME=str(home))
    result = subprocess.run(["bash", str(hook)], cwd=repo, capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert "skipping Block D" in result.stdout
