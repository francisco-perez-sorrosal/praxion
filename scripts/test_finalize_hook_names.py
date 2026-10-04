"""The finalize hook names agree across every surface that installs or records them.

`install_git_hooks.FINALIZE_HOOK_NAMES` is the one declaration. Five surfaces
repeat the names as text, because a shell script or a Markdown example cannot
import a Python tuple: the dispatcher's case arms, the pin upgrade's
`FINALIZE_HOOKS` array and manifest `hooks` list, Praxion's own installer, and
the onboarding manifest example. Each mirror is parsed with an anchored
pattern, and a mirror whose structure the pattern cannot find fails here,
never passes: a reformatted mirror costs a pattern edit, not a silent gap.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import install_git_hooks
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FINALIZE = install_git_hooks.FINALIZE_HOOK_NAMES
ALL = install_git_hooks.ALL_HOOK_NAMES


class MirrorNotFoundError(AssertionError):
    """A mirror's anchored structure is absent or ambiguous in its text."""


def _only_match(pattern: re.Pattern[str], text: str, mirror: str) -> re.Match[str]:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise MirrorNotFoundError(f"{mirror}: {len(matches)} matches of {pattern.pattern!r}, not 1")
    return matches[0]


def _all_matches(pattern: re.Pattern[str], text: str, mirror: str) -> list[re.Match[str]]:
    matches = list(pattern.finditer(text))
    if not matches:
        raise MirrorNotFoundError(f"{mirror}: no match of {pattern.pattern!r}")
    return matches


# -- One parser per mirror -------------------------------------------------------------------

DISPATCH_CASE = re.compile(r'^case "\$\(basename "\$0"\)" in$(.*?)^esac$', re.MULTILINE | re.DOTALL)
DISPATCH_ARM = re.compile(r'^\s*(post-[a-z]+)\)\s+(finalize_chain_[a-z_]+) "\$@" ;;$', re.MULTILINE)
SHELL_ARRAY = re.compile(r"^FINALIZE_HOOKS=\(([^)\n]*)\)$", re.MULTILINE)
INSTALL_LINE = re.compile(
    r'^\s+install_finalize_hook "\$repo_root" "\$finalize_hook_target" ([a-z-]+)$', re.MULTILINE
)
EXPECTED_ARTIFACTS = re.compile(r"^\s+expected_artifacts='(\{.*\})'$", re.MULTILINE)
MANIFEST_EXAMPLE_HOOKS = re.compile(r'^\s*"hooks": (\[[^\]\n]*\]),$', re.MULTILINE)


def dispatcher_arms(text: str) -> tuple[tuple[str, str], ...]:
    """(hook name, entry point it calls) for each `post-*)` arm of the dispatch."""
    block = _only_match(DISPATCH_CASE, text, "dispatcher case").group(1)
    arms = _all_matches(DISPATCH_ARM, block, "dispatcher arms")
    return tuple((arm.group(1), arm.group(2)) for arm in arms)


def dispatcher_hooks(text: str) -> tuple[str, ...]:
    return tuple(hook for hook, _ in dispatcher_arms(text))


def upgrade_finalize_array(text: str) -> tuple[str, ...]:
    body = _only_match(SHELL_ARRAY, text, "FINALIZE_HOOKS array").group(1)
    return tuple(re.findall(r'"([^"]+)"', body))


def installer_lines(text: str) -> tuple[str, ...]:
    return tuple(
        m.group(1) for m in _all_matches(INSTALL_LINE, text, "install_finalize_hook lines")
    )


def _hooks_list(document: str, mirror: str) -> tuple[str, ...]:
    hooks = json.loads(document)
    if isinstance(hooks, dict):
        hooks = hooks.get("hooks")
    if not isinstance(hooks, list):
        raise MirrorNotFoundError(f"{mirror}: no hooks list in {document!r}")
    return tuple(hooks)


def upgrade_manifest_hooks(text: str) -> tuple[str, ...]:
    document = _only_match(EXPECTED_ARTIFACTS, text, "expected_artifacts").group(1)
    return _hooks_list(document, "expected_artifacts")


def manifest_example_hooks(text: str) -> tuple[str, ...]:
    document = _only_match(MANIFEST_EXAMPLE_HOOKS, text, "manifest example").group(1)
    return _hooks_list(document, "manifest example")


# -- The mirrors, and the parity each must keep ----------------------------------------------


class Mirror(NamedTuple):
    path: str
    parse: Callable[[str], tuple[str, ...]]
    declared: tuple[str, ...]
    # Only the manifest lists are order-exact: the pin upgrade compares JSON
    # arrays as written. The other mirrors are sets spelled in some order.
    ordered: bool


MIRRORS = {
    "dispatcher case arms": Mirror(
        "scripts/git-finalize-hook.sh", dispatcher_hooks, FINALIZE, False
    ),
    "pin upgrade FINALIZE_HOOKS": Mirror(
        "scripts/upgrade_project_pins.sh", upgrade_finalize_array, FINALIZE, False
    ),
    "Praxion install lines": Mirror("install_claude.sh", installer_lines, FINALIZE, False),
    "pin upgrade manifest hooks": Mirror(
        "scripts/upgrade_project_pins.sh", upgrade_manifest_hooks, ALL, True
    ),
    "onboarding manifest example": Mirror(
        "skills/onboard-project/references/phases-core.md", manifest_example_hooks, ALL, True
    ),
}


def _comparable(names: tuple[str, ...], ordered: bool) -> tuple[str, ...]:
    return names if ordered else tuple(sorted(names))


@pytest.mark.parametrize("mirror", list(MIRRORS))
def test_each_mirror_lists_exactly_the_declared_hook_names(mirror: str) -> None:
    path, parse, declared, ordered = MIRRORS[mirror]

    listed = parse((REPO_ROOT / path).read_text())

    assert _comparable(listed, ordered) == _comparable(declared, ordered), (
        f"{mirror} in {path} is stale: lists {listed}, declared {declared}"
    )


def test_each_dispatcher_arm_calls_the_entry_point_its_hook_names() -> None:
    arms = dispatcher_arms((REPO_ROOT / "scripts/git-finalize-hook.sh").read_text())

    assert all(entry == f"finalize_chain_{hook.replace('-', '_')}" for hook, entry in arms), arms


# -- Each parser sees a lost hook and a lost structure ---------------------------------------
#
# The real files pass the parity test above only if the parsers can fail.
# Each parser gets a text in its mirror's real formatting with the rewrite hook
# removed (it must report the shorter list), and the same names in a shape its
# pattern does not anchor on (it must raise, never return an empty or partial list).

THREE_ARMS = (
    'case "$(basename "$0")" in\n'
    '    post-merge)    finalize_chain_post_merge "$@" ;;\n'
    '    post-commit)   finalize_chain_post_commit "$@" ;;\n'
    '    post-checkout) finalize_chain_post_checkout "$@" ;;\n'
    "    *) exit 0 ;;\n"
    "esac\n"
)
ARMS_AS_IF_CHAIN = (
    'if [ "$(basename "$0")" = post-merge ]; then finalize_chain_post_merge "$@"; fi\n'
    'if [ "$(basename "$0")" = post-rewrite ]; then finalize_chain_post_rewrite "$@"; fi\n'
)
INSTALL_PREFIX = '        install_finalize_hook "$repo_root" "$finalize_hook_target" '

PARSER_CASES = {
    "dispatcher case arms": (
        dispatcher_hooks,
        THREE_ARMS,
        ARMS_AS_IF_CHAIN,
    ),
    "pin upgrade FINALIZE_HOOKS": (
        upgrade_finalize_array,
        'FINALIZE_HOOKS=("post-merge" "post-commit" "post-checkout")\n',
        'FINALIZE_HOOKS=(\n    "post-merge"\n    "post-commit"\n    "post-checkout"\n    "post-rewrite"\n)\n',
    ),
    "Praxion install lines": (
        installer_lines,
        "".join(
            f"{INSTALL_PREFIX}{hook}\n" for hook in ("post-merge", "post-commit", "post-checkout")
        ),
        "for hook in post-merge post-commit post-checkout post-rewrite; do\n"
        '    install_finalize_hook "$repo_root" "$finalize_hook_target" "$hook"\ndone\n',
    ),
    "pin upgrade manifest hooks": (
        upgrade_manifest_hooks,
        '    expected_artifacts=\'{"hooks":["pre-commit","post-merge","post-commit",'
        '"post-checkout"],"merge_drivers":["observations-jsonl"]}\'\n',
        '    expected_artifacts="$(jq -nc --argjson h "$hooks" \'{hooks: $h}\')"\n',
    ),
    "onboarding manifest example": (
        manifest_example_hooks,
        '       "hooks": ["pre-commit", "post-merge", "post-commit", "post-checkout"],\n',
        '       "hooks": [\n         "pre-commit",\n         "post-rewrite"\n       ],\n',
    ),
}


def test_every_mirror_has_parser_cases() -> None:
    assert set(PARSER_CASES) == set(MIRRORS)


@pytest.mark.parametrize("mirror", list(PARSER_CASES))
def test_a_parser_reports_a_mirror_that_lost_the_rewrite_hook(mirror: str) -> None:
    parse, one_hook_removed, _ = PARSER_CASES[mirror]
    declared = MIRRORS[mirror].declared

    assert parse(one_hook_removed) == tuple(h for h in declared if h != "post-rewrite")


@pytest.mark.parametrize("mirror", list(PARSER_CASES))
def test_a_parser_fails_on_a_mirror_whose_structure_it_cannot_find(mirror: str) -> None:
    parse, _, structure_absent = PARSER_CASES[mirror]

    with pytest.raises(MirrorNotFoundError):
        parse(structure_absent)
