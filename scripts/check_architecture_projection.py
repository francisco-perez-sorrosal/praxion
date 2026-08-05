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

Exit 1 when findings exist, so this doubles as a commit gate. Reports; never
edits either side.

Cites: rules/writing/aac-dac-conventions.md (model is the structural
authority, prose is authored); CLAUDE.md§Context Engineering.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

_MODEL = Path("docs/diagrams/architecture/src/architecture.c4")
_DESIGN = Path(".ai-state/DESIGN.md")

# `name = kind "Title"` -- the only element-declaration form LikeC4 uses here.
_ELEMENT = re.compile(
    r"^\s*(?P<name>[a-zA-Z_][\w]*)\s*=\s*"
    r"(?P<kind>component|agent|document|system|external|person|container)\s+"
    r'"(?P<title>[^"]*)"'
)
_SECTION_3A = re.compile(r"^###\s*3a\b")
_SECTION_NEXT = re.compile(r"^###?\s")


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


# -- Reconciliation -----------------------------------------------------------


def reconcile(repo_root: Path) -> dict:
    model_path, design_path = repo_root / _MODEL, repo_root / _DESIGN
    if not model_path.is_file() or not design_path.is_file():
        return {
            "findings": [],
            "skipped": f"substrate absent ({_MODEL} or {_DESIGN})",
            "rows": 0,
            "elements": 0,
        }

    elements = parse_model(model_path.read_text(encoding="utf-8"))
    structural = structural_components(elements)
    rows = parse_section_3a(design_path.read_text(encoding="utf-8"))

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

    return {
        "findings": findings,
        "skipped": None,
        "rows": len(rows),
        "elements": len(structural),
    }


# -- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the LikeC4 model against DESIGN.md section 3a."
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)

    report = reconcile(resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR))

    if args.json:
        print(json.dumps(report, indent=2))
    elif report["skipped"]:
        print(f"skipped: {report['skipped']}")
    else:
        print(
            f"{report['elements']} structural component(s) in the model, "
            f"{report['rows']} row(s) in section 3a"
        )
        for finding in report["findings"]:
            print(f"  {finding['kind']}: {finding['subject']}\n    {finding['detail']}")
        if not report["findings"]:
            print("  model and section 3a agree")

    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
