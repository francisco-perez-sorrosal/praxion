"""A move's declaration as a file: read the kit's own, and write its known-bad variants.

A declaration is JSON in a kit directory under the move subpackage (`kits/<move>/`), with the
files its arms write beside it. Every known-bad variant is that declaration edited as data: the
kit's directory is copied into the scenario's workspace and the copy changed, so a variant
differs from the kit in the one defect it names and in nothing else. The second ranked move has
no kit to copy a task list from, so its declaration is written whole here, from the shape the
specification names: one resident line, and the rest of the rule delivered when a decision
record is written.

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

Payload = dict[str, Any]

REPO_ROOT = Path(__file__).resolve().parents[3]
KITS_ROOT = REPO_ROOT / "eval" / "src" / "praxion_evals" / "adherence" / "moves" / "kits"
DECLARATION_FILE = "declaration.json"
SCHEMA = "move-declaration/1"
MANIFEST = "rules/_manifest.yaml"
DECISION_RECORDS_MOVE = "adr-conventions"
DECISION_RECORDS_RULE = "rules/swe/adr-conventions.md"
DECISION_RECORDS_GLOB = ".ai-state/decisions/**"
DECISION_RECORDS_SHAPE = "a resident line and a path-matched rule for the decision records"
LEAN_ONLY_NOTE = "docs/lean-arm-only-note.md"
FLOOR_ONLY_NOTE = "docs/floor-arm-only-note.md"
EMBEDDED_HOOK = "hooks/embedded_rule_text.py"
SCOPED_PATHS = ("  - src/**",)
CODEX_STAYS_ALWAYS_ON = ("codex:", "  load: always_on")
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
    if variant == DECISION_RECORDS_SHAPE:
        here.mkdir(parents=True)
        payload = _decision_records_payload(here)
    else:
        shutil.copytree(kit_directory(move), here)
        payload = read_payload(here / DECLARATION_FILE)
        _EDITS[variant](payload, here)
    path = here / DECLARATION_FILE
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _decision_records_payload(here: Path) -> Payload:
    """The second move: one resident line, and the rule matched to writes of decision records.

    The rule's file gains a `paths:` list for Claude Code and says `codex: load: always_on`, so
    the Codex bridge keeps listing it always-on and the move leaves that host reaching what it
    reaches today.
    """
    rule_text = (REPO_ROOT / DECISION_RECORDS_RULE).read_text(encoding="utf-8")
    resident_line = next(line for line in _body_lines(rule_text) if _is_prose(line))
    kernel_file = "rules/swe/adr-conventions-resident.md"
    matched = _with_frontmatter(
        rule_text, ["paths:", f"  - {DECISION_RECORDS_GLOB}", *CODEX_STAYS_ALWAYS_ON]
    )
    return {
        "schema": SCHEMA,
        "move": DECISION_RECORDS_MOVE,
        "moved_rule": DECISION_RECORDS_RULE,
        "checks": [
            {
                "name": "decision draft placement",
                "rule_file": DECISION_RECORDS_RULE,
                "section": "File Format",
                "phrases": ["drafts directory"],
            }
        ],
        "fixture_scope": "managed",
        "arms": {
            "full": [],
            "lean": [
                {"op": "derive", "path": MANIFEST, "kind": "manifest_row_removed"},
                {"op": "derive", "path": kernel_file, "kind": "kernel", "lines": [resident_line]},
                _written_file(here, DECISION_RECORDS_RULE, matched),
            ],
            "floor": [
                {"op": "remove", "path": DECISION_RECORDS_RULE},
                {"op": "derive", "path": MANIFEST, "kind": "manifest_row_removed"},
            ],
        },
        "deliveries": [
            {"channel": "session_start", "file": kernel_file, "lines": [resident_line]},
            {
                "channel": "path_matched",
                "file": DECISION_RECORDS_RULE,
                "globs": [DECISION_RECORDS_GLOB],
            },
        ],
        "launch": {arm: _default_launch() for arm in ARMS},
    }


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
}


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
