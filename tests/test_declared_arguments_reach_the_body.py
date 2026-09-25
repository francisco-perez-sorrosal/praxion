"""Corpus guard: a skill or command that declares `arguments:` must receive them.

Claude Code appends `ARGUMENTS: <input>` to a skill body only when nothing else
receives the typed input -- and declaring an `arguments:` frontmatter field
switches that append off even when the body names none of the declared
placeholders. Measured 2026-09-24 with three headless probes over the same body:
no `arguments:` field -> the input arrived; the documented list form and the
mapping form both -> nothing arrived; the mapping form plus an explicit
`$ARGUMENTS` line -> the input arrived. The documentation says only a
placeholder in the content counts, so this guard pins the observed behaviour,
not the documented one.

A body receives its input through `$ARGUMENTS`, an indexed `$N` /
`$ARGUMENTS[N]`, or a `$<name>` for a declared name.

Test strategy: static analysis of the shipped corpus plus an in-memory canary.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _split(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    block, _, body = text[3:].partition("\n---")
    loaded = yaml.safe_load(block) or {}
    return (loaded if isinstance(loaded, dict) else {}), body


def _declared_names(arguments: object) -> list[str]:
    if isinstance(arguments, str):
        return arguments.split()
    if isinstance(arguments, (list, dict)):
        return [str(name) for name in arguments]
    return []


def undelivered_arguments(text: str) -> bool:
    """True when the frontmatter declares arguments that no body placeholder receives."""
    frontmatter, body = _split(text)
    if "arguments" not in frontmatter:
        return False
    placeholders = [r"\$ARGUMENTS\b", r"\$\d+\b"]
    placeholders += [
        rf"\${re.escape(name)}\b" for name in _declared_names(frontmatter["arguments"])
    ]
    return not any(re.search(pattern, body) for pattern in placeholders)


def _corpus() -> list[Path]:
    return sorted(
        [*REPO_ROOT.glob("skills/*/SKILL.md"), *REPO_ROOT.glob("commands/*.md")],
    )


def _declaring_files() -> list[Path]:
    return [path for path in _corpus() if "arguments" in _split(path.read_text())[0]]


def test_the_corpus_scan_sees_the_declaring_artifacts() -> None:
    """Guards against a broken glob producing a vacuous pass."""
    names = {path.parent.name for path in _declaring_files()}

    assert {"lens-fanout", "onboard-project"} <= names, names


@pytest.mark.parametrize("path", _declaring_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_declared_arguments_reach_the_body(path: Path) -> None:
    assert not undelivered_arguments(path.read_text()), (
        f"{path.relative_to(REPO_ROOT)} declares `arguments:` but its body has no "
        "$ARGUMENTS / $N / $<name> placeholder, so the typed input never arrives"
    )


def test_canary_mapping_form_without_a_placeholder_is_flagged() -> None:
    probe = (
        "---\nname: probe\narguments:\n  question:\n    description: q\n    required: true\n"
        "---\n\nAnswer the question.\n"
    )

    assert undelivered_arguments(probe)


def test_a_declared_name_placeholder_counts_as_delivery() -> None:
    probe = "---\nname: probe\narguments: [issue, branch]\n---\n\nFix $issue on $branch.\n"

    assert not undelivered_arguments(probe)


def test_no_declaration_needs_no_placeholder() -> None:
    """Without `arguments:` the harness appends the input on its own."""
    assert not undelivered_arguments("---\nname: probe\n---\n\nAnswer the question.\n")
