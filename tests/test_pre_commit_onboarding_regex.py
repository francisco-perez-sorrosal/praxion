"""Canary for the canonical-block-sync and behavioral-contract gates' `files:` regexes.

The onboarding unification retires `commands/onboard-project.md` and
`commands/new-project.md` as canonical-block consumers in favor of the single
`skills/onboard-project/references/claude-md-blocks.md` file. If the
`canonical-block-sync` hook's `files:` regex in `.pre-commit-config.yaml`
still matched only the old paths -- or matched nothing at all -- the gate would
fail **open**: no file staged, no hook fires, and a canonical-block edit could
drift out of sync with the onboarding skill undetected.

Both hooks' regexes are read from `.pre-commit-config.yaml` at test runtime,
never transcribed here. A copy would pass because someone typed it correctly
once and then drift silently the moment the live regex changes -- exactly the
failure this canary exists to prevent. The consumer sets they must cover are
likewise imported from their owning registries (`sync_canonical_blocks.COMMAND_FILES`,
`check_behavioral_contract._BC05_CONSUMERS`) rather than hand-listed, so a
registry that gains a path the regex doesn't cover reddens the test instead of
shipping ungated.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
HOOK_ID = "canonical-block-sync"
BEHAVIORAL_CONTRACT_HOOK_ID = "behavioral-contract"

# scripts/ on sys.path so the registry modules below (check_behavioral_contract,
# sync_canonical_blocks) resolve without transcribing their consumer lists here.
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import check_behavioral_contract  # noqa: E402
import sync_canonical_blocks  # noqa: E402


def _files_regex_for(hook_id: str) -> str:
    """Return the live `files:` pattern for the hook named `hook_id`."""
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo["hooks"]:
            if hook["id"] == hook_id:
                return hook["files"]
    raise AssertionError(f"no hook named {hook_id!r} found in {PRE_COMMIT_CONFIG}")


def _canonical_block_sync_files_regex() -> str:
    """Return the live `files:` pattern for the `canonical-block-sync` hook."""
    return _files_regex_for(HOOK_ID)


def _behavioral_contract_files_regex() -> str:
    """Return the live `files:` pattern for the `behavioral-contract` hook."""
    return _files_regex_for(BEHAVIORAL_CONTRACT_HOOK_ID)


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


def test_matches_commands_co_and_cop() -> None:
    pattern = _canonical_block_sync_files_regex()
    for path in ("commands/co.md", "commands/cop.md"):
        assert re.match(pattern, path), (
            f"{HOOK_ID}'s files regex {pattern!r} does not match {path!r} -- the "
            "commit-process consumer pair can drift out of sync with the canonical "
            "block undetected."
        )


def test_canonical_block_sync_covers_every_registered_consumer() -> None:
    """Every consumer `sync_canonical_blocks.BLOCKS` names must fire the gate.

    `COMMAND_FILES` is derived from `BLOCKS` at import time, so a future block
    registering a new consumer widens this set automatically -- if the regex
    isn't widened to match, this test reddens instead of the drift shipping
    silently.
    """
    pattern = _canonical_block_sync_files_regex()
    for absolute_path in sync_canonical_blocks.COMMAND_FILES:
        relative_path = absolute_path.relative_to(REPO_ROOT).as_posix()
        assert re.match(pattern, relative_path), (
            f"{HOOK_ID}'s files regex {pattern!r} does not match registered consumer "
            f"{relative_path!r} -- an edit to it would never trigger the sync check."
        )


def test_behavioral_contract_covers_every_bc05_consumer() -> None:
    """Every BC05 registry path must fire the `behavioral-contract` gate.

    `_BC05_CONSUMERS` is the binding registry between the rule's four bullet
    lines and the files that restate them -- a path added there without
    widening this pattern would let a consumer drift edit land silently.
    """
    pattern = _behavioral_contract_files_regex()
    for relative_path in check_behavioral_contract._BC05_CONSUMERS:
        assert re.match(pattern, relative_path), (
            f"{BEHAVIORAL_CONTRACT_HOOK_ID}'s files regex {pattern!r} does not match "
            f"BC05 consumer {relative_path!r} -- an edit to it would never trigger the "
            "advisory check."
        )


def test_behavioral_contract_still_covers_its_pre_bc05_surfaces() -> None:
    """The four surfaces the hook covered before BC05 must keep matching."""
    pattern = _behavioral_contract_files_regex()
    pre_bc05_paths = (
        "rules/swe/agent-behavioral-contract.md",
        "agents/sentinel.md",
        "skills/code-review/references/report-template.md",
        "scripts/check_behavioral_contract.py",
    )
    for path in pre_bc05_paths:
        assert re.match(pattern, path), (
            f"{BEHAVIORAL_CONTRACT_HOOK_ID}'s files regex {pattern!r} no longer matches "
            f"pre-BC05 surface {path!r} -- widening the pattern for BC05 must not narrow "
            "its existing coverage."
        )
