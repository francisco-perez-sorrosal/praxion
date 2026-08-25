#!/usr/bin/env python3
"""Change-detection resolver for the test-topology protocol.

Turns `file_dependencies` from a declared-but-unread schema field into a live
input: given a set of changed paths, decide which test groups fire, apply the
execution tier's closure rule, and emit the concrete runner invocation(s).

    python3 scripts/resolve_test_scope.py [--changed PATH ...] [--changed-from GITREF]
                                          [--tier step|phase|pipeline] [--json]
                                          [--non-source GLOB ...]
                                          [--topology PATH] [--repo-root PATH]

Contract source: `skills/testing-strategy/references/test-topology.md` (§"Test
Group Schema", §"Selector Strategy Registry", §"integration_boundaries Closure
Semantics", §"parallel_safe Semantics"). That file is authoritative; this script
implements the mechanically decidable half of it.

Two tiers share the word "tier" and are NOT the same axis. The *execution* tier
(`--tier`: step / phase / pipeline) selects the closure radius. The group's own
`tier:` field (unit / integration / contract / e2e) names a pyramid level and is
not consumed here.


The safety property
-------------------
**An unmatched changed path must WIDEN the radius, never narrow it.**

If a changed path matches no group's `file_dependencies` and is not classified
non-source, the resolver escalates to the full suite and names the offending
paths. Returning "no tests to run" for an unmapped source file is a false
all-clear -- `rules/swe/gate-liveness.md`: *"a gate that correctly flags every
violation inside a narrower-than-documented scope still returns a false all-clear
for everything outside it."*

Every design choice below is resolved in the direction of that property:

- **Precise-or-narrow glob matching.** Over-matching is the dangerous direction,
  not under-matching. A path matched too eagerly stops escalating; a path matched
  too reluctantly escalates to the full suite, which is a superset of any group
  selection. So ambiguous glob shapes take the *narrower* reading (see below).
- **Untracked files count as changed.** A brand-new source file is invisible to
  `git diff HEAD`; omitting it would under-select exactly when the blast radius
  is least known.
- **Fail loudly, never skip.** A topology construct the parser does not
  recognize raises with file and line. A parser that silently dropped a group
  would under-select, and the omission would be invisible.
- **A dangling `integration_boundaries` id is an error**, not a silent drop --
  silently ignoring it narrows phase-tier closure.


The non-source predicate (and why it is this narrow)
----------------------------------------------------
Not every changed path is a source path; a commit touching only narrative files
should not pay for a full suite. But "is this file source?" is a project-specific
question, so this predicate is deliberately minimal and every exclusion is
reported in the output (`ignored_non_source`) rather than applied invisibly.

Two rules, applied *only* to paths that matched no group:

1. `git-ignored` -- the path is inside `.git/`, or `git check-ignore` says the
   project ignores it. This rule involves no taste at all: the project already
   declared these paths are not part of its tracked source. Ignored paths cannot
   appear in `git diff <ref>...HEAD` (which reports tracked files only), and in
   the working-tree default they are build output, caches, or ephemeral agent
   state. Nothing under test reads them as source.

2. `root-narrative` -- a repo-root-level file (no directory component) whose
   name matches one of a closed set of conventional community-health files:
   `README*`, `CHANGELOG*`, `CONTRIBUTING*`, `CODE_OF_CONDUCT*`, `SECURITY*`,
   `LICENSE*`, `NOTICE*`, `AUTHORS*`. These are first-contact narrative by
   universal convention: no test framework, build step, or packaging tool in
   common use treats them as input, and they carry no executable or declarative
   content. The set is closed and root-scoped on purpose -- `docs/adr/README.md`
   is not covered, because a nested prose file may well be a fixture.

**Deliberately NOT excluded: `docs/` and `.ai-state/`.** Excluding them is the
intuitive move and it is wrong at least some of the time. In this repository,
`tests/test_adr_frontmatter_parseable.py` parses every file under
`.ai-state/decisions/`, and `scripts/check_architecture_projection.py` reconciles
`docs/architecture.md` against `.ai-state/DESIGN.md`. A change to either
directory can turn a test red, so a blanket prefix exclusion would return the
precise false all-clear this tool exists to prevent. Nor is a root-level `*.md`
rule safe: `CLAUDE.md` is measured by the always-loaded token-budget gate.

Two escapes exist for a project whose `docs/` really is inert, and both keep the
decision visible and attributable:

- Declare `docs/**` in a doc-lint group's `file_dependencies`. This is the better
  answer: the path then *matches*, selecting the group that actually covers it,
  instead of being dropped.
- Pass `--non-source 'docs/**'` at the call site. The widening is then explicit,
  per-invocation, and reported under the `caller-declared` rule.

Residual risk, stated plainly: rule 2 assumes no project wires a test to its own
root `README`. That is a convention, not a proof. It is the one place this tool
trades a sliver of safety for not paying a full suite on a typo fix.


Glob semantics
--------------
`fnmatch` is not used for path matching: its `*` compiles to `.*`, which crosses
`/`, so `scripts/*.py` would match `scripts/sub/deep.py`. `PurePath.match` has
the opposite problem -- `**` is only given segment-crossing meaning by
`full_match`, which is 3.13+, and this script must run under a 3.11 floor. So
globs are translated to regexes here, segment by segment:

- `**` as a whole segment matches zero or more path segments; as the final
  segment it matches everything below (`scripts/**` covers `scripts/a/b.py`).
- `*` and `?` match within one segment and never cross `/`.
- `[...]` is a character class; an unterminated `[` is a literal.
- A pattern with no wildcards matches that exact path only. A bare directory
  name is NOT expanded to its subtree -- write `scripts/**`. The narrow reading
  is chosen deliberately: an unexpanded directory under-matches, which escalates,
  which is safe.
- An absolute pattern is a schema violation (trunk: "Absolute path semantics are
  not allowed") and raises.


Stdlib-only, and specifically so. Agent prose and hooks invoke this through a
bare `python3`, which is whatever the shell resolves -- routinely an interpreter
holding none of the project's declared dependencies. A third-party import would
make this a finding of `check_gate_liveness.py`'s `ambient-import` check (GL05),
which follows sibling imports transitively -- so the constraint binds the private
sibling `_topology_yaml.py` (topology text -> dicts) just as hard as this file.

Exit codes: 0 resolved (including "nothing to run"), 2 usage or topology error.
Tests and canaries: `scripts/test_resolve_test_scope.py`.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _repo_root import resolve_repo_root  # noqa: E402
from _topology_yaml import (  # noqa: E402
    TopologyError,
    iter_yaml_blocks,
    parse_yaml_subset,
)

SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_TOPOLOGY = ".ai-state/TEST_TOPOLOGY.md"

EXECUTION_TIERS = ("step", "phase", "pipeline")

# Trunk §"Test Group Schema". Structural validation only -- semantic validation
# of values (tier vocabulary, reserved ids, subsystem binding) belongs to the
# sentinel's TT checks, not here.
REQUIRED_GROUP_KEYS = frozenset(
    {
        "id",
        "title",
        "subsystems",
        "tier",
        "selectors",
        "file_dependencies",
        "parallel_safe",
        "shared_fixture_scope",
    }
)
OPTIONAL_GROUP_KEYS = frozenset(
    {"integration_boundaries", "expected_runtime_envelope", "shared_state", "notes"}
)
KNOWN_GROUP_KEYS = REQUIRED_GROUP_KEYS | OPTIONAL_GROUP_KEYS

# Registry 1 strategies this resolver can materialize. `manual` is registered in
# the trunk but has no mechanical invocation, so it is rejected loudly rather
# than guessed at -- a wrong guess would emit a run that skips real tests.
PYTEST_RUNNER = "pytest"
STRATEGY_GLOBS = "pytest-globs"
STRATEGY_MARKERS = "pytest-markers"
STRATEGY_KEYWORDS = "pytest-keywords"
SUPPORTED_STRATEGIES = (STRATEGY_GLOBS, STRATEGY_MARKERS, STRATEGY_KEYWORDS)

# Closed set, root-level only. See the module docstring for the justification of
# each name and for the two prefixes deliberately left out.
ROOT_NARRATIVE_GLOBS = (
    "README*",
    "CHANGELOG*",
    "CONTRIBUTING*",
    "CODE_OF_CONDUCT*",
    "SECURITY*",
    "LICENSE*",
    "NOTICE*",
    "AUTHORS*",
)

RULE_GIT_IGNORED = "git-ignored"
RULE_ROOT_NARRATIVE = "root-narrative"
RULE_CALLER_DECLARED = "caller-declared"

REASON_UNMAPPED = "unmapped-changed-paths"

EXIT_OK = 0
EXIT_ERROR = 2


# --- Topology loading --------------------------------------------------------


@dataclass(frozen=True)
class Selector:
    strategy: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class TestGroup:
    id: str
    selectors: tuple[Selector, ...]
    file_dependencies: tuple[str, ...]
    integration_boundaries: tuple[str, ...]
    parallel_safe: bool


def _require_str_list(
    value: object, key: str, group_id: str, source: str, lineno: int
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise TopologyError(source, lineno, f"group {group_id!r}: {key} must be a non-empty list")
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise TopologyError(
                source, lineno, f"group {group_id!r}: {key} entry {entry!r} is not a string"
            )
    return tuple(str(entry) for entry in value)


def _build_selectors(raw: object, group_id: str, source: str, lineno: int) -> tuple[Selector, ...]:
    if not isinstance(raw, list) or not raw:
        raise TopologyError(
            source, lineno, f"group {group_id!r}: selectors must be a non-empty list"
        )
    selectors: list[Selector] = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"strategy", "arg"}:
            raise TopologyError(
                source,
                lineno,
                f"group {group_id!r}: each selector needs exactly `strategy` and `arg`",
            )
        strategy = entry["strategy"]
        if strategy not in SUPPORTED_STRATEGIES:
            raise TopologyError(
                source,
                lineno,
                f"group {group_id!r}: selector strategy {strategy!r} is not one of "
                f"{', '.join(SUPPORTED_STRATEGIES)} -- this resolver cannot materialize it",
            )
        arg = entry["arg"]
        if strategy == STRATEGY_KEYWORDS:
            if not isinstance(arg, str) or not arg.strip():
                raise TopologyError(
                    source, lineno, f"group {group_id!r}: {strategy} arg must be a non-empty string"
                )
            selectors.append(Selector(strategy, (arg,)))
        else:
            selectors.append(
                Selector(strategy, _require_str_list(arg, "arg", group_id, source, lineno))
            )
    return tuple(selectors)


def _build_group(block: dict[str, object], source: str, lineno: int) -> TestGroup:
    group_id = block.get("id")
    if not isinstance(group_id, str) or not group_id.strip():
        raise TopologyError(
            source, lineno, "yaml block has no string `id` -- not a valid test group"
        )
    unknown = sorted(set(block) - KNOWN_GROUP_KEYS)
    if unknown:
        raise TopologyError(
            source, lineno, f"group {group_id!r}: unknown key(s) {', '.join(unknown)}"
        )
    missing = sorted(REQUIRED_GROUP_KEYS - set(block))
    if missing:
        raise TopologyError(
            source, lineno, f"group {group_id!r}: missing required key(s) {', '.join(missing)}"
        )
    parallel_safe = block["parallel_safe"]
    if not isinstance(parallel_safe, bool):
        raise TopologyError(
            source, lineno, f"group {group_id!r}: parallel_safe must be true or false"
        )
    deps = _require_str_list(
        block["file_dependencies"], "file_dependencies", group_id, source, lineno
    )
    for dep in deps:
        if dep.startswith("/"):
            raise TopologyError(
                source, lineno, f"group {group_id!r}: absolute file_dependencies path {dep!r}"
            )
    boundaries = block.get("integration_boundaries") or []
    if boundaries:
        boundaries = _require_str_list(
            boundaries, "integration_boundaries", group_id, source, lineno
        )
    return TestGroup(
        id=group_id,
        selectors=_build_selectors(block["selectors"], group_id, source, lineno),
        file_dependencies=deps,
        integration_boundaries=tuple(boundaries),
        parallel_safe=parallel_safe,
    )


def load_topology(path: Path, source: str | None = None) -> tuple[TestGroup, ...]:
    """Every group declared in a `TEST_TOPOLOGY.md`, or a loud failure."""
    label = source or path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TopologyError(label, 1, f"cannot read topology: {exc}") from exc
    groups: list[TestGroup] = []
    seen: set[str] = set()
    for body, lineno in iter_yaml_blocks(text, label):
        group = _build_group(parse_yaml_subset(body, label, lineno), label, lineno)
        if group.id in seen:
            raise TopologyError(label, lineno, f"duplicate group id {group.id!r}")
        seen.add(group.id)
        groups.append(group)
    if not groups:
        raise TopologyError(label, 1, "no test groups found -- topology declares nothing to run")
    return tuple(groups)


# --- Glob matching -----------------------------------------------------------


def _segment_regex(segment: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(segment):
        char = segment[index]
        if char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        elif char == "[":
            end = index + 1
            if end < len(segment) and segment[end] in "!^":
                end += 1
            if end < len(segment) and segment[end] == "]":
                end += 1
            while end < len(segment) and segment[end] != "]":
                end += 1
            if end >= len(segment):
                out.append(re.escape("["))
                index += 1
                continue
            body = segment[index + 1 : end]
            out.append("[" + ("^" + body[1:] if body[:1] in ("!", "^") else body) + "]")
            index = end + 1
        else:
            out.append(re.escape(char))
            index += 1
    return "".join(out)


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a project-root-relative glob to a full-match path regex.

    `fnmatch` is unusable here (its `*` crosses `/`) and `PurePath.full_match` is
    3.13+; see the module docstring. `**` is only special as a whole segment.
    """
    segments = pattern.strip("/").split("/")
    parts: list[str] = []
    for position, segment in enumerate(segments):
        last = position == len(segments) - 1
        if segment == "**":
            parts.append(".+" if last else "(?:[^/]+/)*")
            continue
        parts.append(_segment_regex(segment))
        if not last:
            parts.append("/")
    return re.compile("".join(parts) + r"\Z")


def match_groups(
    paths: tuple[str, ...], groups: tuple[TestGroup, ...]
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Map each changed path to the group ids claiming it; return unmatched too."""
    compiled = {
        group.id: [glob_to_regex(dep) for dep in group.file_dependencies] for group in groups
    }
    by_path: dict[str, tuple[str, ...]] = {}
    unmatched: list[str] = []
    for path in paths:
        hits = tuple(
            group.id for group in groups if any(rx.match(path) for rx in compiled[group.id])
        )
        by_path[path] = hits
        if not hits:
            unmatched.append(path)
    return by_path, tuple(unmatched)


# --- Changed set -------------------------------------------------------------


@dataclass(frozen=True)
class ChangedSet:
    paths: tuple[str, ...]
    source: str


def _git(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )


def _git_lines(args: list[str], repo_root: Path) -> list[str]:
    result = _git(args, repo_root)
    if result.returncode != 0:
        raise TopologyError(
            "git", 1, f"`git {' '.join(args)}` failed: {result.stderr.strip() or 'unknown error'}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def normalize_path(raw: str, repo_root: Path) -> str:
    """Repo-relative POSIX form. An out-of-tree path is an error, not a silent drop."""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(repo_root.resolve())
        except ValueError as exc:
            raise TopologyError("--changed", 1, f"path {raw!r} is outside the repo root") from exc
    return candidate.as_posix().removeprefix("./")


def changed_paths(explicit: list[str] | None, from_ref: str | None, repo_root: Path) -> ChangedSet:
    """Explicit paths, a git range, or the working tree (staged + unstaged + untracked)."""
    if explicit:
        return ChangedSet(
            tuple(sorted({normalize_path(p, repo_root) for p in explicit})), "explicit"
        )
    if from_ref:
        raw = _git_lines(["diff", "--name-only", f"{from_ref}...HEAD"], repo_root)
        return ChangedSet(tuple(sorted(set(raw))), f"git-diff:{from_ref}...HEAD")
    # Untracked files are included deliberately: a new source file is absent from
    # `git diff HEAD`, and omitting it would under-select exactly when the blast
    # radius is least known.
    tracked = _git_lines(["diff", "--name-only", "HEAD"], repo_root)
    untracked = _git_lines(["ls-files", "--others", "--exclude-standard"], repo_root)
    return ChangedSet(tuple(sorted(set(tracked) | set(untracked))), "working-tree")


# --- Non-source classification ----------------------------------------------


_ROOT_NARRATIVE = tuple(glob_to_regex(pattern) for pattern in ROOT_NARRATIVE_GLOBS)


def _is_root_narrative(path: str) -> bool:
    if "/" in path:
        return False
    return any(rx.match(path) for rx in _ROOT_NARRATIVE)


def classify_non_source(
    paths: tuple[str, ...], repo_root: Path, extra_globs: tuple[str, ...] = ()
) -> dict[str, str]:
    """Which unmatched paths are provably not source, and under which rule.

    Applied *only* to paths no group claimed. Every exclusion is returned so the
    caller can report it -- nothing is dropped invisibly.
    """
    declared = [glob_to_regex(pattern) for pattern in extra_globs]
    ignored: dict[str, str] = {}
    undecided: list[str] = []
    for path in paths:
        if path == ".git" or path.startswith(".git/"):
            ignored[path] = RULE_GIT_IGNORED
        elif any(rx.match(path) for rx in declared):
            ignored[path] = RULE_CALLER_DECLARED
        elif _is_root_narrative(path):
            ignored[path] = RULE_ROOT_NARRATIVE
        else:
            undecided.append(path)
    for path in _git_ignored(tuple(undecided), repo_root):
        ignored[path] = RULE_GIT_IGNORED
    return ignored


def _git_ignored(paths: tuple[str, ...], repo_root: Path) -> tuple[str, ...]:
    """Paths the project's own `.gitignore` excludes. Unavailable git => none."""
    if not paths:
        return ()
    # Paths go on stdin rather than argv: the changed set is unbounded, and
    # `check-ignore` reports "none ignored" with exit 1, which is not a failure.
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=repo_root,
        input="\n".join(paths),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):  # 1 == "none ignored"; anything else is a failure
        return ()
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


# --- Closure -----------------------------------------------------------------


def _one_hop(group: TestGroup, by_id: dict[str, TestGroup], source: str) -> set[str]:
    """`group`'s direct boundaries. An unknown id raises: dropping it narrows closure."""
    for boundary in group.integration_boundaries:
        if boundary not in by_id:
            raise TopologyError(
                source,
                1,
                f"group {group.id!r} lists unknown integration_boundaries id "
                f"{boundary!r} -- closure would silently narrow",
            )
    return set(group.integration_boundaries)


def apply_closure(
    matched: tuple[str, ...], groups: tuple[TestGroup, ...], tier: str, source: str
) -> tuple[str, ...]:
    """Trunk §"integration_boundaries Closure Semantics" -- exactly as tabulated.

    step: no closure. phase: one hop, boundaries-of-boundaries excluded.
    pipeline: every group, regardless of what matched.
    """
    if tier == "pipeline":
        return tuple(group.id for group in groups)
    by_id = {group.id: group for group in groups}
    selected = set(matched)
    if tier == "phase":
        for group_id in matched:
            selected |= _one_hop(by_id[group_id], by_id, source)
    return tuple(group.id for group in groups if group.id in selected)


# --- Invocation composition --------------------------------------------------


@dataclass(frozen=True)
class Invocation:
    argv: tuple[str, ...]
    strategy: str
    parallelism: str
    groups: tuple[str, ...] = field(default_factory=tuple)


def _argv_for(strategy: str, args: tuple[str, ...]) -> tuple[str, ...]:
    if strategy == STRATEGY_GLOBS:
        return (PYTEST_RUNNER, *args)
    if strategy == STRATEGY_MARKERS:
        return (PYTEST_RUNNER, "-m", " or ".join(args))
    return (PYTEST_RUNNER, "-k", " or ".join(f"({arg})" for arg in args))


def _bucket(selected: tuple[TestGroup, ...], parallelism: str) -> list[Invocation]:
    """One invocation per strategy: mixing `-m`/`-k`/paths in one call ANDs them."""
    merged: dict[str, list[str]] = {}
    owners: dict[str, list[str]] = {}
    for group in selected:
        for selector in group.selectors:
            args = merged.setdefault(selector.strategy, [])
            args.extend(arg for arg in selector.args if arg not in args)
            owner = owners.setdefault(selector.strategy, [])
            if group.id not in owner:
                owner.append(group.id)
    return [
        Invocation(_argv_for(strategy, tuple(args)), strategy, parallelism, tuple(owners[strategy]))
        for strategy, args in merged.items()
    ]


def build_invocations(selected: tuple[TestGroup, ...]) -> tuple[Invocation, ...]:
    """Fewest calls that honour §"parallel_safe Semantics".

    Safe groups merge into shared per-strategy calls. Each unsafe group gets its
    own sequential call -- never pooled with safe groups, and never pooled with
    another unsafe group, whose exclusive resource may be the same one.
    """
    safe = tuple(group for group in selected if group.parallel_safe)
    unsafe = tuple(group for group in selected if not group.parallel_safe)
    invocations = list(_bucket(safe, "parallel-safe"))
    for group in unsafe:
        invocations.extend(_bucket((group,), "sequential"))
    return tuple(invocations)


# --- Resolution --------------------------------------------------------------


def resolve(
    groups: tuple[TestGroup, ...],
    changed: ChangedSet,
    tier: str,
    repo_root: Path,
    source: str,
    non_source_globs: tuple[str, ...] = (),
) -> dict[str, object]:
    """The whole decision, as a plain dict -- the JSON payload and the print source."""
    by_path, unmatched = match_groups(changed.paths, groups)
    ignored = classify_non_source(unmatched, repo_root, non_source_globs)
    escalation_paths = tuple(path for path in unmatched if path not in ignored)
    matched_ids = tuple(
        group.id for group in groups if any(group.id in hits for hits in by_path.values())
    )
    escalated = bool(escalation_paths)
    if escalated:
        selected_ids = tuple(group.id for group in groups)
    else:
        selected_ids = apply_closure(matched_ids, groups, tier, source)
    selected = tuple(group for group in groups if group.id in selected_ids)
    return {
        "schema": 1,
        "topology": source,
        "execution_tier": tier,
        "changed": {"source": changed.source, "paths": list(changed.paths)},
        "matched_group_ids": list(matched_ids),
        "selected_group_ids": list(selected_ids),
        "escalated": escalated,
        "escalation_reason": REASON_UNMAPPED if escalated else None,
        "escalation_paths": list(escalation_paths),
        "ignored_non_source": [
            {"path": path, "rule": rule} for path, rule in sorted(ignored.items())
        ],
        "invocations": [
            {
                "argv": list(inv.argv),
                "strategy": inv.strategy,
                "parallelism": inv.parallelism,
                "groups": list(inv.groups),
            }
            for inv in build_invocations(selected)
        ],
    }


def _print_human(payload: dict[str, object]) -> None:
    """Commands to stdout, context to stderr -- so the output stays pipe-safe."""

    def note(text: str) -> None:
        print(text, file=sys.stderr)

    changed = payload["changed"]
    note(f"# changed-set source: {changed['source']} ({len(changed['paths'])} path(s))")
    note(f"# execution tier: {payload['execution_tier']}")
    for entry in payload["ignored_non_source"]:
        note(f"# ignored (non-source, {entry['rule']}): {entry['path']}")
    if payload["escalated"]:
        note(f"# ESCALATED to full suite -- reason: {payload['escalation_reason']}")
        for path in payload["escalation_paths"]:
            note(f"#   unmapped changed path: {path}")
    note(f"# selected groups: {', '.join(payload['selected_group_ids']) or '(none)'}")
    if not payload["invocations"]:
        note("# nothing to run")
        return
    for inv in payload["invocations"]:
        note(f"# {inv['strategy']} [{inv['parallelism']}] groups: {', '.join(inv['groups'])}")
        print(" ".join(shlex.quote(part) for part in inv["argv"]))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve the test scope for a set of changed paths.",
        epilog="An unmapped changed path escalates to the full suite; it never narrows the run.",
    )
    parser.add_argument("--changed", action="append", metavar="PATH", help="explicit changed path")
    parser.add_argument(
        "--changed-from", metavar="GITREF", help="derive changes from GITREF...HEAD"
    )
    parser.add_argument("--tier", choices=EXECUTION_TIERS, default="step", help="closure radius")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable object")
    parser.add_argument(
        "--non-source",
        action="append",
        metavar="GLOB",
        default=[],
        help="treat unmatched paths matching GLOB as non-source (explicit, reported widening)",
    )
    parser.add_argument("--topology", help=f"topology file (default: {DEFAULT_TOPOLOGY})")
    parser.add_argument("--repo-root", help="repo root override")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.changed and args.changed_from:
        print("error: --changed and --changed-from are mutually exclusive", file=sys.stderr)
        return EXIT_ERROR
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    topology_path = Path(args.topology) if args.topology else repo_root / DEFAULT_TOPOLOGY
    label = args.topology or DEFAULT_TOPOLOGY
    try:
        groups = load_topology(topology_path, label)
        changed = changed_paths(args.changed, args.changed_from, repo_root)
        payload = resolve(groups, changed, args.tier, repo_root, label, tuple(args.non_source))
    except TopologyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_human(payload)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
