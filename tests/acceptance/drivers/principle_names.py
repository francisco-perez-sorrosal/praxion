"""Driver for the principle names the kernels' principles pointer carries, read from outside.

The oracle is the philosophy template itself: its principle headings are the level-3 headings
of its `## Principles` section, in file order. What is compared with them is the generated
text every spawn reads: the principles pointer in the committed kernels.

Bound here, because the specification or the base commit fixes them:

- the pointer is the paragraph of a committed kernel file that points at the full principles
  text, `claude/kernels/principles.md` (the base's pointer does; the specification keeps that
  file as the full principles text);
- the pointer states how many principles there are, as an English number word ("eight") or as
  digits, and names each one by its heading text;
- a scenario that adds, removes or renames a principle heading classifies it in the audience
  manifest the way an existing principle is classified, since the manifest must classify every
  heading of the template; it never edits the pointer's own source.

The sandboxes, the generator and the freshness check are `kernel_sandbox`'s.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

from tests.acceptance.drivers import audience_manifest
from tests.acceptance.drivers.kernel_sandbox import (
    GENERATOR,
    USER_TEMPLATE,
    RunResult,
    Sandbox,
    _run,
    isolated_env,
    kernel_files,
    markdown_sections,
    paragraphs,
)

PRINCIPLES_SECTION = "Principles"
FULL_TEXT_PATH = "claude/kernels/principles.md"
# An existing principle whose classification a probe principle borrows, and which the removal
# and rename scenarios act on: delivered verbatim to two roles, cited by no gate by name.
EXEMPLAR = "Structural Beauty"

_NUMBER_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty"
).split()


# -- The oracle: the template's principle headings -------------------------------------------


def principle_headings(template_text: str) -> list[str]:
    """The level-3 headings of the template's `## Principles` section, in file order."""
    headings: list[str] = []
    inside = False
    for section in markdown_sections(template_text):
        if section.level <= 2:
            inside = section.heading == PRINCIPLES_SECTION
        elif inside and section.level == 3:
            headings.append(section.heading)
    assert headings, f"the template has no principle headings under ## {PRINCIPLES_SECTION}"
    return headings


def template_headings(root: Path) -> list[str]:
    return principle_headings((root / USER_TEMPLATE).read_text(encoding="utf-8"))


# -- What the kernels carry ---------------------------------------------------------------------


def pointers(root: Path) -> dict[str, str]:
    """Every committed kernel's principles pointer paragraph, by kernel file name."""
    found = {
        name: paragraph
        for name, text in kernel_files(root).items()
        for paragraph in paragraphs(text)
        if FULL_TEXT_PATH in paragraph
    }
    assert found, f"no committed kernel carries a pointer to {FULL_TEXT_PATH}"
    return found


def names_in_order(pointer: str, names: list[str]) -> list[str]:
    """The `names` the pointer mentions, in the order it mentions them; absent ones dropped."""
    positions = {name: pointer.find(name) for name in names}
    return sorted((n for n, at in positions.items() if at >= 0), key=positions.__getitem__)


def states_count(pointer: str, count: int) -> bool:
    words = [str(count)] + ([_NUMBER_WORDS[count]] if count < len(_NUMBER_WORDS) else [])
    return any(re.search(rf"\b{w}\b", pointer, re.IGNORECASE) for w in words)


def disagreements(root: Path) -> dict[str, str]:
    """Each pointer that does not name the template's principles, in order, with their count."""
    headings = template_headings(root)
    problems = {}
    for name, pointer in pointers(root).items():
        named = names_in_order(pointer, headings)
        if named != headings:
            problems[name] = f"names {named}, the template's headings are {headings}"
        elif not states_count(pointer, len(headings)):
            problems[name] = f"does not state the count {len(headings)}: {pointer!r}"
    return problems


# -- Editing a sandbox's principles ---------------------------------------------------------------


def _exemplar_entry(root: Path) -> audience_manifest.AudienceEntry:
    found = [
        e
        for e in audience_manifest.entries(root)
        if e.source == USER_TEMPLATE and e.heading == EXEMPLAR
    ]
    assert len(found) == 1, f"the audience manifest classifies {EXEMPLAR!r} {len(found)} times"
    return found[0]


def add_principle(sandbox: Sandbox, name: str, before: str) -> None:
    """A new principle heading and paragraph right before `before`, classified as the exemplar."""
    body = f"{name} probe: a paragraph long enough to stand as a principle of its own here."
    sandbox.replace(USER_TEMPLATE, f"### {before}\n", f"### {name}\n\n{body}\n\n### {before}\n")
    entry = dataclasses.replace(_exemplar_entry(sandbox.root), heading=name)
    audience_manifest.add_entry(sandbox.root, entry)


def remove_principle(sandbox: Sandbox, name: str) -> None:
    """The principle's heading and text gone from the template, and its classification with it."""
    text = sandbox.read(USER_TEMPLATE)
    match = re.search(rf"^### {re.escape(name)}\n.*?(?=^#{{2,3}} )", text, re.M | re.S)
    assert match, f"the template has no principle headed {name!r}"
    sandbox.write(USER_TEMPLATE, text[: match.start()] + text[match.end() :])
    audience_manifest.remove_entries(sandbox.root, USER_TEMPLATE, name)


def rename_principle(sandbox: Sandbox, old: str, new: str) -> None:
    """The principle's heading renamed in the template and in its classification, text kept."""
    assert old == EXEMPLAR, f"only the exemplar {EXEMPLAR!r} is renamed by this driver"
    entry = _exemplar_entry(sandbox.root)
    sandbox.replace(USER_TEMPLATE, f"### {old}\n", f"### {new}\n")
    audience_manifest.remove_entries(sandbox.root, USER_TEMPLATE, old)
    audience_manifest.add_entry(sandbox.root, dataclasses.replace(entry, heading=new))


# -- The freshness check ----------------------------------------------------------------------


def freshness_check(root: Path) -> RunResult:
    """`generate_kernels.py --check`, run the way a maintainer or the commit gate runs it."""
    scratch = root.parent / f".{root.name}-check"
    return _run([sys.executable, GENERATOR, "--check"], root, isolated_env(scratch))
