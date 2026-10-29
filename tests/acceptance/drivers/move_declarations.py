"""A move's declaration as a file: read the kit's own, and write its known-bad variants.

A declaration is JSON in a kit directory under the move subpackage (`kits/<move>/`), with the
files its arms write beside it. Every known-bad variant is that declaration edited as data: the
kit's directory is copied into the scenario's workspace and the copy changed, so a variant
differs from the kit in the one defect it names and in nothing else. A variant that edits the
lean arm's rules manifest is written from the manifest the kit's own lean copy holds once built
(`write_lean_manifest_variant`), so it too differs from the kit in its one named defect.

A rule file's *section* is one of its headings and every line after it up to the next heading
of the same or a higher level, sub-headings included (`section_text`).

The module speaks plain JSON values and file paths. `move_eval` turns them into its own
declaration values and `Declared` handles, so this module imports nothing from it.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

Payload = dict[str, Any]

REPO_ROOT = Path(__file__).resolve().parents[3]
KITS_ROOT = REPO_ROOT / "eval" / "src" / "praxion_evals" / "adherence" / "moves" / "kits"
DECLARATION_FILE = "declaration.json"
SCHEMA = "move-declaration/1"
MANIFEST = "rules/_manifest.yaml"
LEAN_ONLY_NOTE = "docs/lean-arm-only-note.md"
FLOOR_ONLY_NOTE = "docs/floor-arm-only-note.md"
EMBEDDED_HOOK = "hooks/embedded_rule_text.py"
SCOPED_PATHS = ("  - src/**",)
ARMS = ("full", "lean", "floor")


# -- Reading ----------------------------------------------------------------------------------


def kit_directory(move: str) -> Path:
    return KITS_ROOT / move


def kit_payload(move: str) -> Payload:
    """The kit's own declaration; a move with no kit yet declares nothing to read."""
    return read_payload(kit_directory(move) / DECLARATION_FILE)


def read_payload(path: Path) -> Payload:
    if not path.is_file():
        raise FileNotFoundError(f"no move declaration at {path}: the kit does not declare it yet")
    return json.loads(path.read_text(encoding="utf-8"))


def declared_payload(move: str, path: Path | None) -> Payload:
    """The declaration a scenario hands the runner: the written variant at `path`, or the kit's."""
    return kit_payload(move) if path is None else read_payload(path)


def resident_kernel(payload: Payload) -> str:
    """The moved rule's lines the lean arm keeps resident, in the rule's own order."""
    prefixes = _kernel_prefixes(payload)
    rule_lines = _moved_rule_text(payload).splitlines()
    return "\n".join(line for line in rule_lines if prefixes and line.startswith(prefixes))


# -- Writing ----------------------------------------------------------------------------------


def write_variant(move: str, variant: str, workspace: Path) -> Path | None:
    """Write `variant` of `move`'s declaration into `workspace`; None for the kit's own."""
    if variant == "as declared":
        return None
    here = workspace / f"{move}-{re.sub(r'[^a-z0-9]+', '-', variant.lower()).strip('-')}"
    shutil.rmtree(here, ignore_errors=True)
    shutil.copytree(kit_directory(move), here)
    payload = read_payload(here / DECLARATION_FILE)
    _EDITS[variant](payload, here)
    path = here / DECLARATION_FILE
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _default_launch() -> Payload:
    return {"model": None, "effort": None, "attribution": None, "user_instructions": None}


# -- The known-bad variants, each one edit ----------------------------------------------------


def _cut_a_rule_line(payload: Payload, here: Path) -> None:
    """Deliver the rule from a copy lacking one line the kernel does not keep resident."""
    prefixes = _kernel_prefixes(payload)
    resident = {line for d in payload["deliveries"] for line in d.get("lines", ())}
    cut = next(
        line
        for line in _body_lines(_moved_rule_text(payload))
        if _is_prose(line) and not line.startswith(prefixes) and line not in resident
    )
    rule = _moved_rule_text(payload)
    shortened = rule.replace(cut + "\n", "", 1)
    path = payload["moved_rule"].replace(".md", "-cut.md")
    _replace_lean(payload, _written_file(here, path, shortened))
    for delivery in payload["deliveries"]:
        if delivery["channel"] in ("hook_context", "gate_refusal"):
            delivery["reads"] = path
        elif delivery["channel"] == "path_matched":
            delivery["file"] = path


def _no_governed_check(payload: Payload, here: Path) -> None:
    payload["checks"] = []


def _three_governed_checks(payload: Payload, here: Path) -> None:
    template = payload["checks"][0]
    while len(payload["checks"]) < 3:
        payload["checks"].append(
            {**template, "name": f"extra governed check {len(payload['checks'])}"}
        )


def _hook_embedding_its_own_text(payload: Payload, here: Path) -> None:
    """A section leaves the carried rule file and reaches the session from text a hook embeds."""
    rule = _moved_rule_text(payload)
    lines = rule.splitlines()
    start, end = _section_span(lines, _kernel_prefixes(payload))
    section = "\n".join(lines[start:end]) + "\n"
    without = "\n".join([*lines[:start], *lines[end:]]) + "\n"
    script = (
        '"""Delivers a section of the moved rule from text embedded here, read from no rule file."""\n'
        "import json\n\n"
        f"TEXT = {json.dumps(section)}\n\n"
        'print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",'
        ' "additionalContext": TEXT}}))\n'
    )
    _replace_lean(payload, _written_file(here, payload["moved_rule"], without))
    _replace_lean(payload, _written_file(here, EMBEDDED_HOOK, script))
    payload["deliveries"].append(
        {"channel": "hook_context", "event": "PreToolUse", "matcher": "Bash",
         "reads": payload["moved_rule"], "repeat": "each"}
    )  # fmt: skip


def _rule_path_scoped(payload: Payload, here: Path) -> None:
    """The rule's file gains a `paths:` list, which Codex reads as path-scoped."""
    scoped = _with_frontmatter(_moved_rule_text(payload), ["paths:", *SCOPED_PATHS])
    _replace_lean(payload, _written_file(here, payload["moved_rule"], scoped))


def _managed_fixtures_only(payload: Payload, here: Path) -> None:
    payload["fixture_scope"] = "managed"


def _arms_differ_in(setting: str, value: str) -> Callable[[Payload, Path], None]:
    def edit(payload: Payload, here: Path) -> None:
        launch = payload.setdefault("launch", {})
        launch.setdefault("lean", _default_launch())[setting] = value

    return edit


def _arms_differ_in_user_instructions(payload: Payload, here: Path) -> None:
    (here / "lean-user-instructions.md").write_text("Answer in one line.\n", encoding="utf-8")
    _arms_differ_in("user_instructions", "lean-user-instructions.md")(payload, here)


def _lean_arm_only_note(payload: Payload, here: Path) -> None:
    _replace_lean(payload, _written_file(here, LEAN_ONLY_NOTE, "A note only the lean arm holds.\n"))


def _floor_arm_only_note(payload: Payload, here: Path) -> None:
    change = _written_file(here, FLOOR_ONLY_NOTE, "A note only the floor arm holds.\n")
    payload["arms"]["floor"].append(change)


UNHELD_PHRASE = "drafts directory"  # a phrase no section of either moved rule holds


def _phrase_its_section_does_not_hold(payload: Payload, here: Path) -> None:
    payload["checks"][0]["phrases"].append(UNHELD_PHRASE)


def _phrase_differing_only_in_letter_case(payload: Payload, here: Path) -> None:
    """A run of the named section's own words, in capitals."""
    check = payload["checks"][0]
    held = _word_runs(section_text(_rule_file_text(check), check["section"]))
    phrase = next(run.upper() for run in held if run.upper() != run)
    check["phrases"].append(phrase)


def _phrase_held_only_outside_the_section(payload: Payload, here: Path) -> None:
    """A run of the rule's words found in another section and nowhere in the named one."""
    check = payload["checks"][0]
    rule = _rule_file_text(check)
    inside = section_text(rule, check["section"]).casefold()
    outside = "\n".join(_body_lines(rule)).replace(section_text(rule, check["section"]), "")
    phrase = next(run for run in _word_runs(outside) if run.casefold() not in inside)
    check["phrases"].append(phrase)


def _rule_file_text(check: Payload) -> str:
    return (REPO_ROOT / check["rule_file"]).read_text(encoding="utf-8")


def _word_runs(text: str) -> list[str]:
    """Contiguous runs of three to six words of letters, exactly as the text holds them."""
    return re.findall(r"[A-Za-z]{3,}(?: [A-Za-z]{2,}){2,5}", text)


_EDITS: dict[str, Callable[[Payload, Path], None]] = {
    "a lean line neither resident nor delivered": _cut_a_rule_line,
    "no governed check": _no_governed_check,
    "three governed checks": _three_governed_checks,
    "a section delivered only by hook text read from no exported rule file": (
        _hook_embedding_its_own_text
    ),
    "a file holding a section turned from always-on to path-scoped on Codex": _rule_path_scoped,
    "delivery changed in the managed fixture kind only": _managed_fixtures_only,
    "the arms differ in the commit-attribution setting": _arms_differ_in(
        "attribution", "attribution-set-on-the-lean-arm-only"
    ),
    "the arms differ in the model": _arms_differ_in("model", "sonnet"),
    "the arms differ in the effort": _arms_differ_in("effort", "high"),
    "the arms differ in the user instruction file": _arms_differ_in_user_instructions,
    "a change confined to the lean arm": _lean_arm_only_note,
    "a change to the floor arm": _floor_arm_only_note,
    "a check phrase its section does not hold": _phrase_its_section_does_not_hold,
    "a check phrase differing only in letter case from its section": (
        _phrase_differing_only_in_letter_case
    ),
    "a check phrase its rule holds only outside the named section": (
        _phrase_held_only_outside_the_section
    ),
}


# -- Lean-manifest variants, written from a built lean copy -----------------------------------

MANIFEST_EDITS = ("removed", "repointed at the kernel")


def write_lean_manifest_variant(move: str, edit: str, lean_manifest: Path, workspace: Path) -> Path:
    """The kit's declaration whose lean arm writes `lean_manifest` with the moved rule's entry
    removed or repointed at the resident kernel, every other entry as the built copy holds it.
    """
    if edit not in MANIFEST_EDITS:
        raise ValueError(f"no manifest edit {edit!r}; known: {MANIFEST_EDITS}")
    here = workspace / f"{move}-manifest-entry-{edit.replace(' ', '-')}"
    shutil.rmtree(here, ignore_errors=True)
    shutil.copytree(kit_directory(move), here)
    payload = read_payload(here / DECLARATION_FILE)
    manifest = yaml.safe_load(lean_manifest.read_text(encoding="utf-8"))
    moved = payload["moved_rule"]
    if edit == "removed":
        manifest["rules"] = [row for row in manifest["rules"] if row.get("path") != moved]
    else:
        kernel = kernel_file(payload)
        for row in manifest["rules"]:
            if row.get("path") == moved:
                row["path"] = kernel
    text = yaml.safe_dump(manifest, sort_keys=False)
    _replace_lean(payload, _written_file(here, MANIFEST, text))
    path = here / DECLARATION_FILE
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def kernel_file(payload: Payload) -> str:
    """The file the lean arm delivers its resident kernel from at session start."""
    files = [d["file"] for d in payload["deliveries"] if d["channel"] == "session_start"]
    if len(files) != 1:
        raise AssertionError(f"the declaration delivers {len(files)} files at session start")
    return files[0]


def path_matched_globs(payload: Payload) -> tuple[str, ...]:
    """Every glob a path-matched delivery of the moved rule declares."""
    return tuple(
        glob
        for delivery in payload["deliveries"]
        if delivery["channel"] == "path_matched"
        for glob in delivery.get("globs", ())
    )


def section_text(rule_text: str, heading: str) -> str:
    """The section `heading` names: its heading line and every line up to the next heading of
    the same or a higher level, sub-headings included. Raises when no heading has that text.
    """
    lines = rule_text.splitlines()
    for start, line in enumerate(lines):
        level = _heading_level(line)
        if level and line.lstrip("#").strip() == heading:
            end = next(
                (j for j in range(start + 1, len(lines)) if 0 < _heading_level(lines[j]) <= level),
                len(lines),
            )
            return "\n".join(lines[start:end])
    raise AssertionError(f"no heading {heading!r} in the rule")


def _heading_level(line: str) -> int:
    match = re.match(r"(#{1,6}) ", line)
    return len(match.group(1)) if match else 0


# -- Shared helpers ---------------------------------------------------------------------------


def _moved_rule_text(payload: Payload) -> str:
    return (REPO_ROOT / payload["moved_rule"]).read_text(encoding="utf-8")


def _kernel_prefixes(payload: Payload) -> tuple[str, ...]:
    return tuple(
        prefix
        for change in payload["arms"]["lean"]
        if change["op"] == "derive" and change["kind"] == "kernel"
        for prefix in change["lines"]
    )


def _written_file(here: Path, path: str, text: str) -> Payload:
    """Write `text` beside the declaration and name it as the content of `path` in an arm."""
    source = path.replace("/", "__")
    (here / source).write_text(text, encoding="utf-8")
    return {"op": "write", "path": path, "source": source}


def _replace_lean(payload: Payload, change: Payload) -> None:
    lean = [c for c in payload["arms"]["lean"] if c["path"] != change["path"]]
    payload["arms"]["lean"] = [*lean, change]


def _split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    if lines and lines[0] == "---":
        end = lines.index("---", 1)
        return lines[1:end], lines[end + 1 :]
    return [], lines


def body_lines(text: str) -> list[str]:
    """A rule's lines below its frontmatter."""
    return _body_lines(text)


def _body_lines(text: str) -> list[str]:
    return _split_frontmatter(text)[1]


def _with_frontmatter(text: str, extra: list[str] | tuple[str, ...]) -> str:
    front, body = _split_frontmatter(text)
    return "\n".join(["---", *front, *extra, "---", *body]) + "\n"


def _is_prose(line: str) -> bool:
    return bool(line.strip()) and not line.startswith("#")


def _section_span(lines: list[str], resident_prefixes: tuple[str, ...]) -> tuple[int, int]:
    """The line range of a `###` section none of whose lines the kernel keeps resident."""
    starts = [i for i, line in enumerate(lines) if line.startswith("### ")]
    spans = [
        (i, next((j for j in range(i + 1, len(lines)) if lines[j].startswith("#")), len(lines)))
        for i in starts
    ]
    for start, end in spans:
        body = lines[start + 1 : end]
        if not any(line.startswith(resident_prefixes) for line in body if _is_prose(line)):
            return start, end
    return spans[-1]
