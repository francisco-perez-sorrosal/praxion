#!/usr/bin/env python3
"""Gate Liveness detector — the mechanically decidable clauses.

Cites: rules/swe/gate-liveness.md — a gate is a claim that it catches a defect
class and must be proven to bite. This detector is itself a gate, so it ships with
canaries (scripts/test_check_gate_liveness.py).

Four checks from one `--json` run, three of them routed to sentinel dimensions:

    forbidden-pattern  GL02  a scan for a pattern another rule forbids there,
                             so it can never match
    uninvoked-gate     GL04  a gate nothing calls
    ambient-import     GL05  a gate something calls with an interpreter that
                             cannot load it
    discarded-verdict   --   a gate whose findings exit code the surface it is
                             registered on structurally cannot transmit

The last three are the same clause — *existence is not operation* — asked three
ways: is it called, can it load, is its verdict read? Each failure is invisible
from the gate's own passing tests, because each lives in the wiring rather than
in the gate.

`discarded-verdict` has **no sentinel dimension id yet**, so its named consumer
(the rule's clause-6 requirement, which this detector is not exempt from) is
`test_check_gate_liveness.py::test_the_live_repo_discards_no_gate_verdict` — a
real-repo assertion that reddens the root suite. Allocating a GL row in
`agents/sentinel.md` would add a second reader; until then the test is the one
that decides, and it is deliberately not optional.

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
# (the defining rules, this detector's own docs/tests). Matched against the
# **repo-relative** path, never an absolute one: an absolute match makes the
# verdict a function of where the checkout happens to sit on disk, so identical
# bytes at identical repository positions yield a finding under one clone path
# and silence under another — and a managed project's path differs by
# definition. A canary pins the relocation invariant.
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
#
# Inflected forms are matched because prose writes the directive both ways: a
# checklist says "scan test files for req33_" and the row documenting it says
# "a checkpoint that *searches* test names for req33_". Bare-stem-only matching
# saw the first and missed the second, so the documented bad-case a reader is
# told the gate catches went uncaught. `look` still requires its `for`, since
# the bare verb carries no scanning sense.
_SCAN_VERB = re.compile(
    r"\b(?:grep|scan|search|match)(?:s|es|ed|ing|ned|ning|ped|ping)?\b"
    r"|\blook(?:s|ed|ing)?\s+for\b",
    re.IGNORECASE,
)
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
            relative = path.relative_to(root).as_posix()
            if any(sub in relative for sub in _EXCLUDE_SUBSTRINGS):
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

# Hook guards and gates are gates by every reading of the rule, and were absent
# from this inventory purely because `hooks/` is excluded from `ambient-import`.
# Those are two different scopes: `ambient-import` excludes hooks as *call
# sites* (correctly — a hook resolves its own interpreter through
# `$PRAXION_PYTHON`), while this check needs them as *candidate gates*. One
# exclusion was standing in for both, so an orphaned hook guard was unreportable.
_HOOK_GATE_GLOBS = ("*_gate.py", "*_guard.py", "*_gate.sh")

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
    gates += [
        p
        for pattern in _HOOK_GATE_GLOBS
        for p in sorted((root / "hooks").glob(pattern))
        if not p.name.startswith("test_")
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
        # A gate's own tests are matched on the *stem*, not the filename: a
        # shell gate's test is `test_<stem>.py`, so the filename form
        # (`test_foo.sh`) matches nothing and the gate is excused by its own
        # test — the exact false-negative the exclusion exists to prevent.
        own_test = f"test_{gate.stem}"
        invoked = any(
            site.name != gate.name
            and not site.stem.startswith(own_test)
            and site.name != "CLAUDE.md"
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


# Claude Code's hook contract treats exit **2** as "blocking error" — the only
# code that reaches a decision. Every other non-zero is a non-blocking error the
# model never sees. A gate that returns the POSIX-natural 1-on-findings through
# such a registration therefore computes a correct verdict that nothing can act
# on. `hooks/commit_gate.sh --blocking` exists to translate 1 -> 2, and its own
# header records the live instance: a citation gate detecting violations
# perfectly while the rule calling it "the primary enforcement layer" was
# unenforced.
_HOOK_BLOCKING_EXIT = 2
_HOOK_FINDINGS_EXIT = 1
_BLOCKING_FLAG = "--blocking"
_HOOK_COMMAND_SCRIPT = re.compile(r"((?:hooks|scripts)/[A-Za-z0-9_]+\.py)")

# Events whose contract gives exit 2 a decision to reach. SessionStart and the
# rest have no blocking path at all, so a findings exit there is unfixable
# rather than defective — flagging it would be a finding with no remedy.
_BLOCKING_HOOK_EVENTS = frozenset(
    {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop", "SubagentStop", "PreCompact"}
)


def _findings_exit_codes(path: Path) -> set[int]:
    """Integer codes `path` can hand its caller, resolved through `sys.exit(main())`.

    A literals-only scan reads the repo's dominant gate shape -- `sys.exit(main())`
    over a `main()` returning 0/1 -- as having no exit codes at all, which reports
    every such gate as carrying no verdict: a silent pass exactly where the check
    matters. So a non-literal argument widens the search to the module's own
    `return <int>` statements.

    `bool` is excluded deliberately: `isinstance(True, int)` holds in Python, and
    a `sys.exit(flag)` would otherwise be read as the findings exit 1.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()

    def literal(node: ast.expr | None) -> int | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return None if isinstance(node.value, bool) else node.value
        return None

    codes: set[int] = set()
    indirect = False
    for node in ast.walk(tree):
        argument: ast.expr | None = None
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in ("exit", "SystemExit") and node.args:
                argument = node.args[0]
        elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if getattr(node.exc.func, "id", "") == "SystemExit" and node.exc.args:
                argument = node.exc.args[0]
        if argument is None:
            continue
        value = literal(argument)
        if value is None:
            indirect = True
        else:
            codes.add(value)

    if indirect:
        codes |= {
            value
            for node in ast.walk(tree)
            if isinstance(node, ast.Return) and (value := literal(node.value)) is not None
        }
    return codes


def check_discarded_verdict(root: Path) -> list[dict]:
    """A gate whose verdict the surface it is registered on cannot transmit.

    The third question in the *existence is not operation* family. `uninvoked-gate`
    asks whether a gate is called; `ambient-import` asks whether it can load; this
    asks whether the answer it computes reaches the decision it guards.

    Scope is `hooks/hooks.json` registrations, and narrowly so on purpose. Three
    wider formulations of "the exit code is swallowed" were measured against this
    repository first and every one of them fired only on correct code: a CI step
    under `continue-on-error` with no `steps.<id>.*` reader flagged two agent
    steps that hand their verdict to a downstream reader through a file; a
    "gate not last in a pipeline" scan flagged a `|| (echo ... && exit 1)` and an
    `xargs` whose gate *is* last. A check that fires on correct code is worse than
    no check, so they were dropped rather than patched.

    What survives is decidable with no false positives *by construction*: a hook
    with no exit-1 path has no verdict to discard, so a deliberately advisory
    reminder is silent because of what it is, not because of an exception carved
    for it.
    """
    registrations = root / "hooks" / "hooks.json"
    try:
        events = json.loads(registrations.read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError, AttributeError):
        return []  # no registrations here (the normal case in a managed project)

    findings: list[dict] = []
    for event, groups in sorted(events.items()):
        if event not in _BLOCKING_HOOK_EVENTS or not isinstance(groups, list):
            continue
        for group in groups:
            for entry in group.get("hooks", []) if isinstance(group, dict) else []:
                command = entry.get("command", "") if isinstance(entry, dict) else ""
                if _IGNORE in command or _BLOCKING_FLAG in command:
                    continue
                for relative in _HOOK_COMMAND_SCRIPT.findall(command):
                    script = root / relative
                    codes = _findings_exit_codes(script)
                    if _HOOK_FINDINGS_EXIT not in codes:
                        continue
                    findings.append(
                        {
                            "check": "discarded-verdict",
                            "severity": "fail",
                            "file": relative,
                            "line": 1,
                            "evidence": f"{event} registration: {command.strip()[:120]}",
                            "why": (
                                f"exits {_HOOK_FINDINGS_EXIT} on findings, but a {event} "
                                f"hook only reaches a decision at exit "
                                f"{_HOOK_BLOCKING_EXIT} — the verdict is computed and "
                                f"discarded. Route it through "
                                f"`commit_gate.sh {_BLOCKING_FLAG}`, or exit "
                                f"{_HOOK_BLOCKING_EXIT} directly"
                            ),
                        }
                    )
    return findings


_CHECKS = {
    "forbidden-pattern": check_forbidden_pattern,
    "uninvoked-gate": check_uninvoked_gate,
    "ambient-import": check_ambient_import,
    "discarded-verdict": check_discarded_verdict,
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
