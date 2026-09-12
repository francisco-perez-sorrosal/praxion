#!/usr/bin/env python3
"""Reconcile the LikeC4 model against DESIGN.md's structural-component table.

Three descriptions of Praxion's structure coexisted and disagreed: the design
doc's component table, the developer-facing architecture doc, and the `.c4`
model that CI actually enforces and that renders the diagram embedded in both.
The doc table listed 46 rows against a 14-element model, so most documented
components carried no structural enforcement at all -- and the rendered diagram
sat directly above a table that contradicted it.

Splitting the table into structural components and capabilities framed the
problem. This closes it: every structural row must name a model element and
every model component must have a row, asserted mechanically.

**The binding is explicit, not inferred.** Row titles and element titles differ
by design -- a row reads "Agent runtime / Pipeline" where the element reads
"Agent Pipeline" -- so matching on titles would either miss real drift or
invent false drift on a rename. Each row carries the element's id instead, in
its own column, which also puts the binding in front of a human reading the
doc rather than hiding it in a script.

*Structural* components are those with no child component. Layer containers
(Knowledge, Orchestration, Persistence, Tooling) group components and get no
row; a component whose only children are agents or documents is still
structural and does get one.

A second reconciliation covers the *published* half. The Interfaces section
documents the canonical blocks installed into every managed project's own
`CLAUDE.md`, where the shipped-block registry is the authority and the table
is a projection of it. Those rows carry the highest blast radius in the repo
-- a break costs N repositories rather than this one -- so a block shipping
undocumented, or a documented block the registry does not declare, is drift on
the same footing as a missing component row.

**Six finding kinds, one per drift shape.** Structural half (model <-> 3a):
`element-without-row` (a modelled component the doc never documents),
`row-without-element` (a documented component carrying no structural
enforcement -- the shape that let most of the table drift), `unknown-element`
(the doc names an element the model does not declare, typically a rename the
doc did not follow), `not-structural` (a row for a layer container, which
double-counts its children). Published half (registry <-> section 4):
`block-without-row` (a block installed into every managed project's
`CLAUDE.md` that the doc does not record -- the highest blast radius finding
this dimension produces, since it costs N repositories rather than one),
`row-without-block` (a retired block still advertised as part of the
contract). Resolving one is a judgment about which side is right: the model
wins when its edges encode enforced structure, the doc wins when the model is
over-granular.

Exit 1 when findings exist, so this doubles as a commit gate. Reports; never
edits either side.

**AC04/AC05 ride the same substrate gate, at a different severity.** AC13 (this
script's original scope) is the exit-code-bearing check; `check_projection()`
returns its own pre-existing flat envelope (`findings`/`skipped`/`withheld`/
`rows`/`elements`) unchanged, so callers of that function see byte-identical
behavior. `classify()` is the wider envelope `main()` and sentinel actually
consume: it wraps AC13's findings (adding `check`/`severity` to a copy, never
mutating the originals) alongside two new checks -- AC04 (every inline
`dec-NNN` in `.ai-state/DESIGN.md` or `docs/architecture.md` resolves to a
finalized ADR) and AC05 (`docs/architecture.md` exists and is non-empty) --
sharing AC13's own substrate trigger (`.c4` model and `.ai-state/DESIGN.md`
both present; all three skip together otherwise). `skipped` and `examined`
are keyed by check id in this envelope; AC13's own `rows`/`elements` land
under `examined["AC13"]`. AC04 and AC05 findings always carry
`severity: "warn"` and never affect the exit code -- both are advisory
findings living inside a script that otherwise blocks the commit, because a
stale decision reference or an empty developer guide is real drift but not
worth reddening every commit over (measured against the live corpus before
shipping; see `LEARNINGS.md § Step F2`).

Cites: rules/writing/aac-dac-conventions.md (model is the structural
authority, prose is authored); CLAUDE.md§Context Engineering.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

# The check ids this script's row surface declares -- a literal tuple so the row/registry/
# script Triangle in `tests/test_sentinel_check_triangle.py` can read it via AST without
# importing this module. Additive only: a new id lands here in the same commit that
# writes its row. Registry-facing only: unlike CHECK_ID in the flat-declaration pilot
# scripts (`check_agent_prompt_size.py`, `check_adr_reciprocity.py`,
# `check_agent_lifecycle_pairing.py`, `check_doc_manifest_freshness.py`), this script
# never emits a `"check"` key -- there is no runtime id for this declaration to drift
# from, only Leg 3's static one.
CHECK_IDS: tuple[str, ...] = ("AC04", "AC05", "AC13")

SCRIPT_NAME = "check_architecture_projection"

_MODEL = Path("docs/diagrams/architecture/src/architecture.c4")
_DESIGN = Path(".ai-state/DESIGN.md")
_ARCH_DOC = Path("docs/architecture.md")
_DECISIONS_DIR = Path(".ai-state/decisions")

# AC04/AC05 findings are always advisory: unlike AC13's exit-code-bearing findings,
# a broken `dec-NNN` reference or a missing developer guide must not flip the
# `architecture-projection` pre-commit gate red -- see `classify()`.
_AC04_SEVERITY = "warn"
_AC05_SEVERITY = "warn"

# Three digits by construction: finalized files are `<NNN>-<slug>.md` and finalize_adrs.py
# assigns `\d{3}` ids, so a 4-digit id is not a finalized ADR here. Declared limit: if the
# corpus ever passes dec-999 the filename schema changes first and this pattern with it.
_DEC_ID_RE = re.compile(r"\bdec-(\d{3})\b")
# Fenced code is illustrative, not a reference: an ADR id inside ``` ... ``` is dropped
# before scanning (light-review F2, F3).
_FENCED_BLOCK_RE = re.compile(r"```.*?```", re.S)
# The shipped-block registry, read from the tree under inspection. Both this and
# the two paths above resolve against `repo_root`, so every authority the check
# compares comes from the same tree.
_REGISTRY = Path("scripts/sync_canonical_blocks.py")
_REGISTRY_SYMBOL = "BLOCKS"

# `name = kind "Title"` -- the only element-declaration form LikeC4 uses here.
_ELEMENT = re.compile(
    r"^\s*(?P<name>[a-zA-Z_][\w]*)\s*=\s*"
    r"(?P<kind>component|agent|document|system|external|person|container)\s+"
    r'"(?P<title>[^"]*)"'
)
_SECTION_3A = re.compile(r"^###\s*3a\b")
_SECTION_NEXT = re.compile(r"^###?\s")
_SECTION_4 = re.compile(r"^##\s*4\.\s")
_BLOCK_ROW = re.compile(r"^\|\s*Canonical block:\s*`([a-z0-9-]+)`\s*\|")

# Distinct from both None (registry unreadable -> withhold) and () (registry
# read, no blocks ship). Overloading the empty tuple for "look it up" would make
# a caller asking about an empty registry silently trigger a live import.
_AUTO: tuple[str, ...] = ("\0auto",)


# -- Model side ---------------------------------------------------------------


def parse_model(text: str) -> dict[str, str]:
    """Map element id -> kind, ids qualified the way the DSL references them.

    The enclosing `system` is omitted from the id path because relationships in
    the model are written `knowledge.skills`, not `praxion.knowledge.skills`;
    the doc should name elements the same way the model does.
    """
    elements: dict[str, str] = {}
    stack: list[tuple[int, str]] = []  # (depth at which pushed, name)
    depth = 0
    for line in text.splitlines():
        stripped = line.split("//")[0]
        match = _ELEMENT.match(stripped)
        opens = stripped.count("{") - stripped.count("}")
        if match:
            name, kind = match["name"], match["kind"]
            elements[".".join([n for _, n in stack] + [name])] = kind
            if opens > 0 and kind != "system":
                stack.append((depth, name))
            elif opens > 0:
                # A system opens a block but contributes no id segment.
                stack.append((depth, ""))
        depth += opens
        while stack and depth <= stack[-1][0]:
            stack.pop()
    return {".".join(p for p in eid.split(".") if p): k for eid, k in elements.items()}


def structural_components(elements: dict[str, str]) -> set[str]:
    """Components with no child *component* -- layers group, they do not count."""
    components = {eid for eid, kind in elements.items() if kind == "component"}
    return {
        eid for eid in components if not any(other.startswith(f"{eid}.") for other in components)
    }


# -- Document side ------------------------------------------------------------


def parse_section_3a(text: str) -> list[dict[str, str]]:
    """Rows of the structural-component table, as {component, element}."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _SECTION_3A.match(line))
    except StopIteration:
        return []
    rows, header = [], None
    for line in lines[start + 1 :]:
        if _SECTION_NEXT.match(line):
            break
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        row = dict(zip(header, cells, strict=False))
        rows.append(
            {
                "component": row.get("component", "").strip("`"),
                "element": row.get("element", "").strip("`").strip(),
            }
        )
    return rows


def parse_canonical_block_rows(text: str) -> list[str]:
    """Slugs the Interfaces section claims are shipped canonical blocks."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _SECTION_4.match(line))
    except StopIteration:
        return []
    slugs = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if match := _BLOCK_ROW.match(line):
            slugs.append(match.group(1))
    return slugs


def canonical_block_slugs(repo_root: Path) -> tuple[str, ...] | None:
    """The shipped-block registry for *repo_root*, or None when it cannot be read.

    Read by parsing rather than importing, for two reasons. It resolves against
    `repo_root` like every other input, so `--repo-root` relocates *both*
    authorities instead of silently reconciling one tree's design doc against
    another tree's registry -- a wrong answer that looks like a clean run. And
    parsing executes nothing, so a checker can never be made to run code from
    the tree it is inspecting.

    None means *withhold*, never *empty*: reporting "no blocks ship" because the
    registry could not be read would turn a tooling problem into a claim that
    the entire published contract is undocumented. A non-literal key withholds
    for the same reason -- a partial read is a wrong answer, not a smaller one.
    """
    try:
        tree = ast.parse((repo_root / _REGISTRY).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            named = isinstance(node.target, ast.Name) and node.target.id == _REGISTRY_SYMBOL
        elif isinstance(node, ast.Assign):
            named = any(
                isinstance(target, ast.Name) and target.id == _REGISTRY_SYMBOL
                for target in node.targets
            )
        else:
            continue
        if not named or not isinstance(node.value, ast.Dict):
            continue
        slugs = [
            key.value
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        ]
        return tuple(slugs) if len(slugs) == len(node.value.keys) else None
    return None


# -- Reconciliation -----------------------------------------------------------


def check_projection(repo_root: Path, *, block_slugs: tuple[str, ...] | None = _AUTO) -> dict:
    model_path, design_path = repo_root / _MODEL, repo_root / _DESIGN
    if not model_path.is_file() or not design_path.is_file():
        return {
            "findings": [],
            "skipped": f"substrate absent ({_MODEL} or {_DESIGN})",
            "withheld": [],
            "rows": 0,
            "elements": 0,
        }

    design_text = design_path.read_text(encoding="utf-8")
    elements = parse_model(model_path.read_text(encoding="utf-8"))
    structural = structural_components(elements)
    rows = parse_section_3a(design_text)

    findings = []
    claimed = set()
    for row in rows:
        eid = row["element"]
        if not eid:
            findings.append(
                {
                    "kind": "row-without-element",
                    "subject": row["component"],
                    "detail": "row names no model element; add one or move it to 3b",
                }
            )
        elif eid not in elements:
            findings.append(
                {
                    "kind": "unknown-element",
                    "subject": row["component"],
                    "detail": f"names `{eid}`, which no element in the model declares",
                }
            )
        else:
            claimed.add(eid)
            if eid not in structural:
                findings.append(
                    {
                        "kind": "not-structural",
                        "subject": row["component"],
                        "detail": f"`{eid}` groups other components; layers get no row",
                    }
                )

    for eid in sorted(structural - claimed):
        findings.append(
            {
                "kind": "element-without-row",
                "subject": eid,
                "detail": "structural component absent from 3a; add a row or fold it into another element",
            }
        )

    # Section 4 carries the published half of the architecture -- the blocks
    # installed into every managed project's own CLAUDE.md. The shipped-block
    # registry is the authority; the table is a projection of it, and without
    # this a block added tomorrow leaves the contract silently undocumented.
    withheld = []
    slugs = canonical_block_slugs(repo_root) if block_slugs is _AUTO else block_slugs
    if slugs is None:
        withheld.append("canonical-block rows: the shipped-block registry could not be read")
    else:
        documented = parse_canonical_block_rows(design_text)
        for slug in sorted(set(slugs) - set(documented)):
            findings.append(
                {
                    "kind": "block-without-row",
                    "subject": slug,
                    "detail": "ships to managed projects but section 4 does not document it",
                }
            )
        for slug in sorted(set(documented) - set(slugs)):
            findings.append(
                {
                    "kind": "row-without-block",
                    "subject": slug,
                    "detail": "documented as shipped, but the registry declares no such block",
                }
            )

    return {
        "findings": findings,
        "skipped": None,
        "withheld": withheld,
        "rows": len(rows),
        "elements": len(structural),
    }


# -- AC04/AC05 (advisory, riding AC13's substrate gate) -----------------------


def _check_ac04(repo_root: Path, design_text: str) -> tuple[list[dict], dict]:
    """Every `dec-NNN` in DESIGN.md or the developer guide resolves to a finalized ADR."""
    arch_path = repo_root / _ARCH_DOC
    texts = [design_text]
    if arch_path.is_file():
        texts.append(arch_path.read_text(encoding="utf-8"))

    dec_ids = sorted(
        {m.group(1) for text in texts for m in _DEC_ID_RE.finditer(_FENCED_BLOCK_RE.sub("", text))}
    )
    decisions_dir = repo_root / _DECISIONS_DIR
    findings = [
        {
            "check": "AC04",
            "severity": _AC04_SEVERITY,
            "entity": f"dec-{dec_id}",
            "message": f"'dec-{dec_id}' referenced but has no finalized "
            f"{_DECISIONS_DIR}/{dec_id}-*.md file",
        }
        for dec_id in dec_ids
        if not decisions_dir.is_dir() or not any(decisions_dir.glob(f"{dec_id}-*.md"))
    ]
    return findings, {"dec_ids_examined": len(dec_ids)}


def _check_ac05(repo_root: Path) -> tuple[list[dict], dict]:
    """`docs/architecture.md` exists and carries content."""
    arch_path = repo_root / _ARCH_DOC
    if not arch_path.is_file():
        detail = "does not exist"
    elif not arch_path.read_text(encoding="utf-8").strip():
        detail = "exists but is empty"
    else:
        return [], {"checked": True}
    finding = {
        "check": "AC05",
        "severity": _AC05_SEVERITY,
        "entity": str(_ARCH_DOC),
        "message": f"'{_ARCH_DOC}' {detail} while {_DESIGN} is present",
    }
    return [finding], {"checked": True}


def classify(repo_root: Path) -> dict:
    """AC04 + AC05 + AC13 in one envelope -- see module docstring for the shape."""
    ac13 = check_projection(repo_root)
    skipped = ac13["skipped"]

    ac13_findings = [
        {
            "check": "AC13",
            "severity": "fail",
            "entity": f["subject"],
            "message": f"{f['kind']}: {f['detail']}",
        }
        for f in ac13["findings"]
    ]

    if skipped is not None:
        ac04_findings, ac04_examined = [], None
        ac05_findings, ac05_examined = [], None
    else:
        design_text = (repo_root / _DESIGN).read_text(encoding="utf-8")
        ac04_findings, ac04_examined = _check_ac04(repo_root, design_text)
        ac05_findings, ac05_examined = _check_ac05(repo_root)

    return {
        "script": SCRIPT_NAME,
        "checks": list(CHECK_IDS),
        "findings": ac13_findings + ac04_findings + ac05_findings,
        "skipped": {"AC04": skipped, "AC05": skipped, "AC13": skipped},
        "examined": {
            "AC04": ac04_examined,
            "AC05": ac05_examined,
            "AC13": None
            if skipped is not None
            else {"rows": ac13["rows"], "elements": ac13["elements"]},
        },
        "withheld": ac13["withheld"],
        "bound": {
            "AC04": "AC04 clean means every inline dec-NNN in DESIGN.md and the developer "
            "guide resolves to a finalized ADR file; fenced code is not scanned.",
            "AC05": "AC05 clean means docs/architecture.md exists with content whenever "
            ".ai-state/DESIGN.md exists; its substance is AC06-AC09's question.",
            "AC13": "AC13 clean means DESIGN.md projects both the architecture model and "
            "the shipped-block registry; read withheld before reading zero findings.",
        },
    }


# -- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the LikeC4 model + shipped blocks + dec-NNN refs against DESIGN.md."
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)

    report = classify(resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR))

    if args.json:
        print(json.dumps(report, indent=2))
    elif all(v is not None for v in report["skipped"].values()):
        print(f"skipped: {report['skipped']['AC13']}")
    else:
        ac13_meta = report["examined"]["AC13"] or {}
        if ac13_meta:
            print(
                f"{ac13_meta['elements']} structural component(s) in the model, "
                f"{ac13_meta['rows']} row(s) in section 3a"
            )
        for reason in report["withheld"]:
            print(f"  WITHHELD -- {reason}")
        for finding in report["findings"]:
            print(
                f"  {finding['check']} [{finding['severity']}] {finding['entity']}: "
                f"{finding['message']}"
            )
        if not report["findings"]:
            print("  AC04/AC05/AC13 agree")

    return 1 if any(f["severity"] == "fail" for f in report["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
