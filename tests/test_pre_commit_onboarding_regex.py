"""Canary for the canonical-block-sync gate's re-anchored `files:` regex.

The onboarding unification retires `commands/onboard-project.md` and
`commands/new-project.md` as canonical-block consumers in favor of the single
`skills/onboard-project/references/claude-md-blocks.md` file. If the
`canonical-block-sync` hook's `files:` regex in `.pre-commit-config.yaml`
still matched only the old paths -- or matched nothing at all -- the gate would
fail **open**: no file staged, no hook fires, and a canonical-block edit could
drift out of sync with the onboarding skill undetected.

The regex is read from `.pre-commit-config.yaml` at test runtime, never
transcribed here. A copy would pass because someone typed it correctly once
and then drift silently the moment the live regex changes -- exactly the
failure this canary exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
HOOK_ID = "canonical-block-sync"


def _canonical_block_sync_files_regex() -> str:
    """Return the live `files:` pattern for the `canonical-block-sync` hook."""
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo["hooks"]:
            if hook["id"] == HOOK_ID:
                return hook["files"]
    raise AssertionError(f"no hook named {HOOK_ID!r} found in {PRE_COMMIT_CONFIG}")


def test_matches_the_new_consolidated_consumer_path() -> None:
    pattern = _canonical_block_sync_files_regex()
    assert re.match(pattern, "skills/onboard-project/references/claude-md-blocks.md"), (
        f"{HOOK_ID}'s files regex {pattern!r} does not match the new single consumer file -- "
        "an edit to it would never trigger the sync check."
    )


def test_does_not_match_the_retired_onboard_project_command() -> None:
    pattern = _canonical_block_sync_files_regex()
    assert not re.match(pattern, "commands/onboard-project.md"), (
        f"{HOOK_ID}'s files regex {pattern!r} still matches the retired command path -- the "
        "gate would fire on a file no longer read by anything."
    )


def test_does_not_match_the_retired_new_project_command() -> None:
    pattern = _canonical_block_sync_files_regex()
    assert not re.match(pattern, "commands/new-project.md"), (
        f"{HOOK_ID}'s files regex {pattern!r} still matches the retired command path -- the "
        "gate would fire on a file no longer read by anything."
    )
