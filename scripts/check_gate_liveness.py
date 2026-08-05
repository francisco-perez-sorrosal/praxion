#!/usr/bin/env python3
"""Gate Liveness detector — the mechanically decidable clauses.

Cites: rules/swe/gate-liveness.md — a gate is a claim that it catches a defect
class and must be proven to bite. This detector is itself a gate, so it ships with
canaries (scripts/test_check_gate_liveness.py).

Three checks, routed to three sentinel dimensions from one `--json` run:

    forbidden-pattern  GL02  a scan for a pattern another rule forbids there,
                             so it can never match
    uninvoked-gate     GL04  a gate nothing calls
    ambient-import     GL05  a gate something calls with an interpreter that
                             cannot load it

The last two are the two halves of the same clause — *existence is not
operation*. A gate must run at all, and it must run in the environment it
guards; each failure is invisible from the gate's own passing tests.

GL01 (orphaned-consumer) was prototyped here but moved to the sentinel's Pass-2
LLM judgment — "is this section produced anywhere?" is a semantic question a
regex answers with too many false positives, whereas a dead grep is a hard,
mechanically-detectable contradiction. Use the proof that matches the gate.

Stdlib-only, which this file has a specific reason to stay: it is itself
invoked through the ambient interpreter, so a third-party import here would make
it the first finding of its own `ambient-import` check.

Invoked by the sentinel's GL dimension (`--json`); also runnable standalone.
Exit code: 1 when findings exist, 0 when clean — so it doubles as a commit gate.
Honors an inline `gate-liveness:ignore` escape for deliberate references.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# Files that legitimately *describe* forbidden patterns as teaching material
# (the defining rules, this detector's own docs/tests). Path-substring excluded so
# the detector never flags its own vocabulary.
_EXCLUDE_SUBSTRINGS = (
    "gate-liveness",
    "gate-canaries",
    "check_gate_liveness",
    "id-citation-discipline",
    "shipped-artifact-isolation",
)
_IGNORE = "gate-liveness:ignore"
_SCAN_DIRS = ("agents", "rules", "skills", "commands")

# A grep/scan directive that targets a pattern id-citation-discipline forbids in
# test/code. Canonical dead-grep shape: "scan test files for req{NN}_".
_SCAN_VERB = re.compile(r"\b(grep|scan|search|match|look for)\b", re.IGNORECASE)
_TESTCODE = re.compile(r"\b(test|tests|code|source)\b|\.py|\.ts", re.IGNORECASE)
_FORBIDDEN_LITERALS = re.compile(
    r"req\{NN\}_|req\\d\+_|req\d+_|REQ-\d|AC-\d"  # id-citation-discipline:ignore
)


def _iter_files(root: Path):
    for directory in _SCAN_DIRS:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if any(sub in str(path) for sub in _EXCLUDE_SUBSTRINGS):
                continue
            yield path


def check_forbidden_pattern(root: Path) -> list[dict]:
    """GL02: instructions that grep/scan for a pattern forbidden in the target."""
    findings: list[dict] = []
    for path in _iter_files(root):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if _IGNORE in line:
                continue
            if (
                _FORBIDDEN_LITERALS.search(line)
                and _SCAN_VERB.search(line)
                and _TESTCODE.search(line)
            ):
                findings.append(
                    {
                        "check": "forbidden-pattern",
                        "severity": "fail",
                        "file": str(path.relative_to(root)),
                        "line": lineno,
                        "evidence": line.strip()[:200],
                        "why": (
                            "instruction greps/scans test or code for a pattern "
                            "id-citation-discipline forbids there — it can never "
                            "match, so the gate is dead"
                        ),
                    }
                )
    return findings


# A gate script is named for what it does; these prefixes are the rule's own
# enumeration for the script kind.
_GATE_NAME = re.compile(r"^(check|validate)_.+\.py$")

# Where an invocation can legitimately live. A gate's own tests are excluded on
# purpose: a test proves the gate *works*, never that anything *runs* it, and
# counting tests would make every orphan look wired. Catalog prose is excluded
# for the same reason -- describing a gate is not invoking it.
_INVOCATION_GLOBS = (
    ".pre-commit-config.yaml",
    "hooks/**/*",
    "agents/*.md",
    "commands/*.md",
    ".github/workflows/*.yml",
    "scripts/*.sh",
    "scripts/*.py",
    "fitness/**/*.py",
)


def check_uninvoked_gate(root: Path) -> list[dict]:
    """GL04: a gate nothing invokes catches nothing, however correct it is.

    Every other liveness check asks whether a gate runs *correctly*. This one
    asks whether it runs at all. The distinction matters because the failure is
    invisible from the inside: the file exists, its tests pass, its docstring
    may even name an invoker -- and the defect class it claims to catch goes
    uncaught forever, because nothing ever calls it.
    """
    gates = [
        p
        for p in sorted((root / "scripts").glob("*.py"))
        if _GATE_NAME.match(p.name) and not p.name.startswith("test_")
    ]
    sites = []
    for pattern in _INVOCATION_GLOBS:
        sites += [p for p in root.glob(pattern) if p.is_file()]

    findings: list[dict] = []
    for gate in gates:
        # Match the filename (shell, CI, prose invocation) or the bare module
        # stem (a Python import, which is how one gate legitimately drives
        # another). Missing the stem form reports wired gates as orphans.
        stem = re.compile(rf"\b{re.escape(gate.stem)}\b")
        invoked = any(
            site.name not in (gate.name, f"test_{gate.name}", "CLAUDE.md")
            and (gate.name in (text := site.read_text(errors="ignore")) or stem.search(text))
            for site in sites
        )
        if not invoked:
            findings.append(
                {
                    "check": "uninvoked-gate",
                    "severity": "fail",
                    "file": str(gate.relative_to(root)),
                    "line": 1,
                    "evidence": gate.name,
                    "why": (
                        "no hook, command, agent, workflow, or sibling script "
                        "invokes this gate — it catches nothing, and its own "
                        "tests cannot reveal that"
                    ),
                }
            )
    return findings


# Surfaces where a script runs under the *ambient* interpreter: an agent or
# command instructs a model to type `python3 <script>` into a shell, and nothing
# between the instruction and the process declares which interpreter that is.
#
# Everything else is excluded because it resolves its own interpreter and so
# cannot exhibit this failure: hooks and shell scripts go through
# `$PRAXION_PYTHON` -> `<repo>/.venv/bin/python` -> ambient; CI workflows install
# the project environment first; and `.pre-commit-config.yaml` names its
# interpreter in the `language:` key (`python` for a hook needing third-party
# packages, `system` for a stdlib-only one) -- a distinction this repo already
# draws correctly. Documented scope and computed scope are the same two globs,
# per the rule's own scope-fidelity clause.
_AMBIENT_INVOCATION_GLOBS = ("agents/*.md", "commands/*.md")
_AMBIENT_INVOCATION = re.compile(r"\bpython3?\s+(scripts/[A-Za-z0-9_]+\.py)")
_MISSING_MODULE_ERRORS = frozenset(
    {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
)
_STDLIB = frozenset(sys.stdlib_module_names)


def _handles_missing_module(handler: ast.ExceptHandler) -> bool:
    """True when this `except` clause would catch an absent package."""
    if handler.type is None:  # bare `except:` catches everything
        return True
    caught = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(node, ast.Name) and node.id in _MISSING_MODULE_ERRORS for node in caught)


def _guarded_imports(tree: ast.Module) -> set[int]:
    """Ids of import nodes inside a `try` that handles a missing package.

    A guarded import is not a liveness defect: the script has already decided
    what to do when the package is absent, which is this repo's documented
    remedy -- name the interpreter actually in use and say how to fix it --
    rather than a bare traceback a reader discards as noise.

    Only the `try` body is guarded, never the handler's. An import written in an
    `except ImportError` clause is a *fallback*, and a fallback can fail exactly
    like the import it replaces; nothing catches it. That is the shape of the
    live instance this check was written against.
    """
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(map(_handles_missing_module, node.handlers)):
            for statement in node.body:
                for inner in ast.walk(statement):
                    if isinstance(inner, ast.Import | ast.ImportFrom):
                        guarded.add(id(inner))
    return guarded


def _local_module(module: str, entry: Path, root: Path) -> Path | None:
    """Resolve a dotted module name to a file in this repo, or None."""
    relative = Path(*module.split("."))
    for base in (entry.parent, root):
        for candidate in (base / relative.with_suffix(".py"), base / relative / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def _third_party_imports(entry: Path, root: Path, seen: set[Path] | None = None) -> set[str]:
    """Packages `entry` needs that an interpreter may not have, following siblings.

    Transitive by necessity. The instance that motivated this check imported
    only stdlib plus one sibling module, and the third-party dependency lived in
    that sibling -- a direct-imports-only scan reports it clean, which is the
    scope-fidelity failure the rule warns about one clause earlier.

    An unparseable file yields nothing: this judges what it can read, and
    guessing from a failed parse would invent findings.
    """
    seen = set() if seen is None else seen
    if entry in seen or not entry.is_file():
        return set()
    seen.add(entry)
    try:
        tree = ast.parse(entry.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()

    guarded = _guarded_imports(tree)
    needed: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            modules = [node.module or ""]
        else:
            continue  # relative imports stay inside a package that ships together
        for module in filter(None, modules):
            local = _local_module(module, entry, root)
            if local is not None:
                needed |= _third_party_imports(local, root, seen)
            elif module.split(".")[0] not in _STDLIB:
                needed.add(module.split(".")[0])
    return needed


def check_ambient_import(root: Path) -> list[dict]:
    """GL05: a gate invoked through the ambient interpreter must be loadable by it.

    GL04 asks whether anything calls the gate. This asks the other half of the
    same clause: given that something calls it, can the interpreter it is called
    with actually load it? A bare `python3` is whatever the shell resolves --
    under a version manager's shim, routinely a build holding none of the
    project's declared dependencies. The gate then dies on import, and its own
    tests never reveal it because they run under the project interpreter.

    Reported once per script rather than once per call site: the fix belongs in
    one place, and a script named by several agents would otherwise produce a
    row per mention.
    """
    sites = [p for glob in _AMBIENT_INVOCATION_GLOBS for p in sorted(root.glob(glob))]
    first_use: dict[str, tuple[str, int]] = {}
    for site in sites:
        for lineno, line in enumerate(site.read_text(errors="ignore").splitlines(), start=1):
            if _IGNORE in line:
                continue
            for match in _AMBIENT_INVOCATION.finditer(line):
                first_use.setdefault(match.group(1), (str(site.relative_to(root)), lineno))

    findings: list[dict] = []
    for target, (caller, lineno) in sorted(first_use.items()):
        needed = _third_party_imports(root / target, root)
        if not needed:
            continue
        packages = ", ".join(sorted(needed))
        findings.append(
            {
                "check": "ambient-import",
                "severity": "fail",
                "file": target,
                "line": 1,
                "evidence": f"{caller}:{lineno} runs `python3 {target}` — needs {packages}",
                "why": (
                    f"invoked through the ambient interpreter, which is not "
                    f"guaranteed to have {packages}; the gate dies on import and "
                    f"catches nothing. Guard the import with a remedy message, "
                    f"drop the dependency, or resolve an interpreter that has it"
                ),
            }
        )
    return findings


_CHECKS = {
    "forbidden-pattern": check_forbidden_pattern,
    "uninvoked-gate": check_uninvoked_gate,
    "ambient-import": check_ambient_import,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate Liveness detector (GL02).")
    parser.add_argument(
        "--check",
        choices=[*_CHECKS, "all"],
        default="all",
        help="which liveness check to run (default: all)",
    )
    parser.add_argument("--root", default=".", help="repo root to scan")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    root = Path(args.root)
    selected = _CHECKS if args.check == "all" else {args.check: _CHECKS[args.check]}
    findings: list[dict] = []
    for fn in selected.values():
        findings.extend(fn(root))

    if args.json:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    else:
        for finding in findings:
            loc = f"{finding['file']}:{finding['line']}"
            print(f"[{finding['severity'].upper()}] {finding['check']} {loc} — {finding['why']}")
        print(f"{len(findings)} gate-liveness finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
