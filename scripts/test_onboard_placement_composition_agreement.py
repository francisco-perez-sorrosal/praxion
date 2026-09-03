"""Cross-check: `onboard_placement.sh`'s `_placement_intent_of` (bash) agrees
with `_sidecar_init.build_manifest`'s own composition order (Python) on
every path, across the `--shadow`/`--share` flag matrix and both states of
a pre-existing `CLAUDE.md` (tracked vs. absent).

Why this exists (IF-29, audit § 1.10/1.11): `onboard_placement.sh` renders
the confirmation block *before* `praxion-sidecar init` runs, so it cannot
shell out to the real composer -- it re-implements the same DS-2 defaults ->
`--share` overrides -> `--shadow` overrides ("last write wins") order in
bash, and its own header says so ("mirroring `_sidecar_init.build_manifest`'s
own composition order exactly"). That claim previously had no automated
guard -- the two readers could silently drift. This test is the "two readers
agree" pattern DS-2's stdlib/YAML manifest-reader pair already carries,
applied to this second pair.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`, so
pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_state_repo.py`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import _sidecar_identity as identity
import _sidecar_init as initializer
import _sidecar_manifest as manifests
import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
ONBOARD_PLACEMENT_SH = SCRIPT_DIR / "onboard_placement.sh"

# The path set `_placement_all_paths` (bash) always renders: the four DS-2
# shadow/share defaults plus `CLAUDE.md` -- independent of what a given case
# also passes as `--shadow`/`--share`.
_BASE_PATHS = (
    ".ai-state",
    "CLAUDE.md",
    "CLAUDE.local.md",
    ".claude/settings.local.json",
    "docs/architecture.md",
)

_INTENT_BY_ENTRY_TYPE = {
    manifests.ShadowEntry: "shadow",
    manifests.ShareEntry: "share",
    manifests.UntouchedEntry: "untouched",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def _make_project(tmp_path: Path, *, with_tracked_claude_md: bool) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git(project_root, "init", "-q", "-b", "main")
    _git(project_root, "config", "user.email", "t@t.t")
    _git(project_root, "config", "user.name", "t")
    if with_tracked_claude_md:
        (project_root / "CLAUDE.md").write_text("# Team-owned\n")
        _git(project_root, "add", "CLAUDE.md")
        _git(project_root, "commit", "-q", "-m", "seed")
    return project_root


def _python_intents(
    project_root: Path, *, shadow_paths: list[str], share_paths: list[str]
) -> dict[str, str]:
    """The real composer's own answer, per path -- `_sidecar_init.build_manifest`."""
    project_id = identity.derive_project_id(project_root)
    manifest = initializer.build_manifest(
        checkout=project_root,
        project_id=project_id,
        slug=identity.slug(project_id),
        shadow_overrides=shadow_paths,
        share_overrides=share_paths,
    )
    all_paths = set(_BASE_PATHS) | set(shadow_paths) | set(share_paths)
    return {path: _INTENT_BY_ENTRY_TYPE[type(manifest.paths[path])] for path in all_paths}


def _bash_intents(
    project_root: Path, *, shadow_paths: list[str], share_paths: list[str]
) -> dict[str, str]:
    """`onboard_placement.sh`'s own answer, per path -- `_placement_intent_of`,
    driven directly (sourced in isolation; no other onboard-project global is
    touched since the function only reads `SHADOW_PATHS`/`SHARE_PATHS`)."""
    all_paths = sorted(set(_BASE_PATHS) | set(shadow_paths) | set(share_paths))
    shadow_array = " ".join(f'"{p}"' for p in shadow_paths)
    share_array = " ".join(f'"{p}"' for p in share_paths)
    paths_array = " ".join(f'"{p}"' for p in all_paths)
    script = f"""
set -euo pipefail
source {ONBOARD_PLACEMENT_SH!s}
SHADOW_PATHS=({shadow_array})
SHARE_PATHS=({share_array})
for path in {paths_array}; do
    printf '%s\\t%s\\n' "$path" "$(_placement_intent_of {project_root!s} "$path")"
done
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    intents: dict[str, str] = {}
    for line in result.stdout.splitlines():
        path, intent = line.split("\t")
        intents[path] = intent
    return intents


# --- the flag matrix (INTERFACE_DESIGN.md sec. 5.1's `--shadow`/`--share`
# composition, over both states of a pre-existing tracked CLAUDE.md) --------

_CASES = [
    pytest.param([], [], False, id="no-overrides--claude-md-absent"),
    pytest.param([], [], True, id="no-overrides--claude-md-tracked"),
    pytest.param([], ["CLAUDE.md"], False, id="share-claude-md--claude-md-absent"),
    pytest.param(["docs/architecture.md"], [], False, id="shadow-architecture-doc"),
    pytest.param(
        ["docs/architecture.md"], [], True, id="shadow-architecture-doc--claude-md-tracked"
    ),
    pytest.param([], ["docs/architecture.md"], False, id="share-architecture-doc-redundant"),
]


@pytest.mark.parametrize(("shadow_paths", "share_paths", "with_tracked_claude_md"), _CASES)
def test_bash_and_python_composers_agree_on_every_path(
    tmp_path: Path,
    shadow_paths: list[str],
    share_paths: list[str],
    with_tracked_claude_md: bool,
) -> None:
    project_root = _make_project(tmp_path, with_tracked_claude_md=with_tracked_claude_md)

    python_intents = _python_intents(
        project_root, shadow_paths=shadow_paths, share_paths=share_paths
    )
    bash_intents = _bash_intents(project_root, shadow_paths=shadow_paths, share_paths=share_paths)

    assert bash_intents == python_intents, (
        f"onboard_placement.sh's _placement_intent_of disagrees with "
        f"_sidecar_init.build_manifest's own composition order: "
        f"bash={bash_intents!r} python={python_intents!r}"
    )
