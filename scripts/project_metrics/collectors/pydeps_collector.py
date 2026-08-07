"""PydepsCollector — Tier 1 Python coupling + cyclic SCC detection via ``uvx pydeps``.

Pydeps is a Python-only collector that traces the static import graph of a
Python package and surfaces three module-level signals plus one repo-wide
aggregate:

* Afferent coupling (Ca) -- number of modules importing a given module.
* Efferent coupling (Ce) -- number of modules a given module imports.
* Instability I = Ce / (Ca + Ce), conventionally clamped to ``[0.0, 1.0]``.
  Fully-isolated modules (Ca = Ce = 0) yield ``None`` rather than forcing a
  ``ZeroDivisionError`` or a misleading ``0.0``; "undefined" is the honest
  signal for a module with no import edges in either direction.
* Cyclic SCCs -- strongly-connected components of the import graph with size
  greater than one. A non-trivial SCC is a structural defect: every module in
  the cycle depends on every other, making isolated change impossible. The
  count of non-trivial SCCs feeds the repo-level aggregate ``cyclic_deps``.

Invocation shape:

* ``resolve()`` performs three gated checks in strict order:

  1. ``shutil.which("uvx")`` -- PATH lookup. Absent → ``Unavailable``.
  2. ``git ls-files`` in the repo root, scanning for ``__init__.py``. None →
     ``NotApplicable``. This distinguishes Pydeps from the Complexipy
     collector: Complexipy triggers ``NotApplicable`` when there are no
     ``.py`` files at all; Pydeps triggers when there are ``.py`` files but
     no importable packages, i.e., no ``__init__.py`` anywhere.
  3. ``uvx pydeps --version`` with a 120s deadline -- cache-fill probe.
     Non-zero exit, timeout, or ``FileNotFoundError`` → ``Unavailable``.

  A one-line first-run hint lands on stderr immediately before the version
  probe so users see progress while uvx populates its cache.

* ``collect()`` discovers **every** import root in the repository (see
  "Scope fidelity" below), runs ``uvx pydeps <root> --show-deps --no-output
  --max-bacon 0`` per root under a per-root deadline, merges the resulting
  JSON graphs into one payload, then computes per-module Ca/Ce/I over the
  internal-only import graph and runs an iterative Tarjan-style SCC sweep to
  find non-trivial cycles.

Internal-edges-only policy: only imports whose targets appear as keys in the
pydeps JSON contribute to Ca/Ce. External imports (``os``, ``typing``, third
parties) are infrastructure, not first-party coupling, and should not inflate
the signal. This matches the canonical Ca/Ce definitions used in Martin's
package-metrics literature.

Scope fidelity
--------------

``cyclic_deps == 0`` is only meaningful against a stated denominator. Three
properties of this collector exist to keep that number an honest, *bounded*
claim rather than a repo-wide all-clear:

1. **Every import root, not one.** A single package root cannot represent a
   repository with several independent package trees. Roots are derived from
   the tracked ``__init__.py`` set: ascend each package directory through its
   contiguous package ancestors, then take one further hop to a depth-1
   parent whose name is a valid Python identifier — a depth-1 directory *is*
   the repo's import root, because the repo root is what sits on ``sys.path``
   (``from scripts.project_metrics... import``). Deeper namespace directories
   (``src/``) are packaging layout, not import roots, so the ascent stops
   below them and targets the package itself.

2. **Unlimited traversal.** pydeps defaults to ``--max-bacon 2``, which
   truncates the walk so far that the emitted graph is nearly edge-free —
   every module ends up with the synthetic entry node as its only neighbour.
   SCC detection over such a graph is *structurally incapable* of reporting a
   cycle, so the zero it returns says nothing about the code. ``--max-bacon 0``
   removes the limit.

3. **The denominator is published.** The aggregate block carries
   ``package_roots``, ``repo_python_files``, ``analyzed_python_files`` and
   ``python_file_coverage_pct`` alongside ``cyclic_deps``, so a reader (and
   the sentinel's tech-debt dimension) sees the coverage next to the count.

pydeps is a *package* analyser: a directory of loose ``.py`` files with no
``__init__.py`` anywhere beneath it yields an empty graph. Such directories
are therefore outside this collector's reach by construction, and the
published coverage percentage is what makes that boundary visible.

The synthetic bare ``__main__`` node pydeps emits per invocation is dropped
before analysis: it is an artifact of the traversal (it "imports" every
module, inflating every module's Ca by one), and N roots would otherwise
contribute N colliding copies of it. A genuine ``pkg/__main__.py`` is
unaffected — it appears dotted, as ``pkg.__main__``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    NotApplicable,
    ResolutionEnv,
    ResolutionResult,
    Unavailable,
)

__all__ = ["PydepsCollector"]


# ---------------------------------------------------------------------------
# Tunables.
# ---------------------------------------------------------------------------

_RESOLVE_TIMEOUT_SECONDS: float = 120.0
_COLLECT_TIMEOUT_SECONDS: float = 60.0
_LS_FILES_TIMEOUT_SECONDS: float = 30.0
# pydeps' own default is 2, which truncates traversal so aggressively that the
# emitted graph carries almost no module-to-module edges. Zero means "no limit".
_MAX_BACON_UNLIMITED: str = "0"
# The bare entry node pydeps synthesises per invocation — not a real module.
_SYNTHETIC_ENTRY_MODULE: str = "__main__"
_PY_SUFFIX: str = ".py"
_REPO_ROOT_TARGET: str = "."
_FIRST_RUN_HINT: str = (
    "project-metrics: resolving Tier 1 tools (first-run uvx cache fill, may take up to 120s)"
)
_UVX_INSTALL_HINT: str = "install uv: https://docs.astral.sh/uv/"
_UVX_NOT_FOUND_REASON: str = "uvx not found on PATH (pydeps requires uvx to resolve)"
_NOT_APPLICABLE_REASON: str = "No importable Python packages detected — no __init__.py files found"
_INIT_PY_FILENAME: str = "__init__.py"


class PydepsCollector(Collector):
    """Python coupling (Ca/Ce/I) + cyclic SCC detection via ``uvx pydeps``."""

    name = "pydeps"
    tier = 1
    required = False
    languages: frozenset[str] = frozenset({"python"})

    def __init__(self, repo_root: Path | str | None = None) -> None:
        """Store the optional repo root; collection time uses ``ctx.repo_root``.

        Kept for parity with ``GitCollector`` and ``LizardCollector``. The
        runner threads the authoritative repo root through the
        ``CollectionContext`` regardless of what the constructor received.
        """

        self._configured_repo_root: Path | None = Path(repo_root) if repo_root is not None else None

    # ------------------------------------------------------------------ resolve

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Three-gate probe: uvx on PATH, __init__.py present, pydeps runs.

        Order matters. Checking ``shutil.which`` first avoids a wasted
        ``git ls-files`` invocation when uvx is missing. Checking ``__init__.py``
        before the ``--version`` probe avoids a wasted 120s uvx cache fill
        on a repo where pydeps would have nothing to analyze anyway.
        """

        if shutil.which("uvx") is None:
            return Unavailable(
                reason=_UVX_NOT_FOUND_REASON,
                install_hint=_UVX_INSTALL_HINT,
            )

        if not _has_init_py_in_repo():
            return NotApplicable(reason=_NOT_APPLICABLE_REASON)

        print(_FIRST_RUN_HINT, file=sys.stderr)

        try:
            completed = subprocess.run(
                ["uvx", "pydeps", "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=_RESOLVE_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return Unavailable(
                reason=_UVX_NOT_FOUND_REASON,
                install_hint=_UVX_INSTALL_HINT,
            )
        except subprocess.TimeoutExpired:
            return Unavailable(
                reason="uvx pydeps first-run cache fill timed out after 120s",
                install_hint=_UVX_INSTALL_HINT,
            )
        except subprocess.CalledProcessError as exc:
            return Unavailable(
                reason=f"uvx pydeps --version exited with status {exc.returncode}",
                install_hint=_UVX_INSTALL_HINT,
            )

        return Available(version=completed.stdout.strip())

    # ------------------------------------------------------------------ collect

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Sweep every import root with pydeps, merge the graphs, roll up metrics.

        ``--show-deps`` writes a JSON-shaped dependency dict to stdout
        natively — current pydeps has no ``--json`` flag, and adding one
        is a hard error (``unrecognized arguments: --json``). The
        ``--no-output`` flag prevents pydeps from generating an .svg/.png
        file as a side effect; it also implies ``--no-show`` (no display
        program invocation). Together they keep the run silent and side-
        effect-free while preserving the JSON-on-stdout the parser
        depends on.
        """

        tracked_files = _list_tracked_files(ctx.repo_root)
        if tracked_files is None:
            return CollectorResult(
                status="error",
                data={},
                issues=["git ls-files failed during collect; cannot enumerate package roots."],
            )

        candidates = _discover_package_roots(tracked_files)
        if not candidates:
            return CollectorResult(
                status="error",
                data={},
                issues=[
                    "No __init__.py found via git ls-files during collect; "
                    "cannot locate a package root for pydeps."
                ],
            )

        targets, shadowed = _partition_by_namespace(candidates)
        sweep = _sweep_package_roots(targets, ctx.repo_root)
        issues = _shadowed_root_issues(shadowed) + sweep.issues

        if not sweep.analyzed_roots:
            return CollectorResult(
                status="timeout" if sweep.timed_out else "error",
                data={},
                issues=issues,
            )

        coverage = _coverage_block(tracked_files, sweep.analyzed_roots)
        return CollectorResult(
            status="partial" if issues else "ok",
            data=_analyze_payload(sweep.payload, coverage),
            issues=issues,
        )


# ---------------------------------------------------------------------------
# NotApplicable probe — git ls-files scan for any ``__init__.py``.
# ---------------------------------------------------------------------------


def _has_init_py_in_repo() -> bool:
    """Return True when ``git ls-files`` lists at least one ``__init__.py``.

    Runs ``git ls-files`` with no explicit ``cwd``; the ambient working
    directory is expected to be inside the target repo when ``resolve()`` is
    called during a real run. Any invocation error (not-a-repo, timeout,
    missing git binary) is treated as "no packages detected" — Unavailable
    would be a stronger claim than the evidence supports, and the pydeps
    run would fail downstream anyway, so ``NotApplicable`` is the conservative
    outcome here.
    """

    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_LS_FILES_TIMEOUT_SECONDS,
        )
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
    ):
        return False

    return _contains_init_py(completed.stdout)


def _contains_init_py(ls_files_output: str) -> bool:
    """Return True when any line of ``git ls-files`` output ends in ``__init__.py``."""

    return any(_is_init_py(raw_line.strip()) for raw_line in ls_files_output.splitlines())


# ---------------------------------------------------------------------------
# Import-root discovery — every root, not one. See "Scope fidelity" above.
# ---------------------------------------------------------------------------


def _list_tracked_files(repo_root: str) -> list[str] | None:
    """Return every path ``git ls-files`` reports under ``repo_root``.

    One probe serves both root discovery and the coverage denominator, so the
    two can never disagree about what the repository contains. ``None`` marks
    an unusable probe (not-a-repo, timeout, missing git) — distinct from an
    empty repository, which is an empty list.
    """

    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_LS_FILES_TIMEOUT_SECONDS,
            cwd=repo_root,
        )
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
    ):
        return None

    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _is_init_py(path: str) -> bool:
    """Return True when ``path`` names an ``__init__.py`` at any depth."""

    return path.endswith("/" + _INIT_PY_FILENAME) or path == _INIT_PY_FILENAME


def _parent_dir(path: str) -> str:
    """Return the parent directory of a repo-relative path (``""`` at the root)."""

    return path.rsplit("/", 1)[0] if "/" in path else ""


def _discover_package_roots(tracked_files: Iterable[str]) -> list[str]:
    """Return every import root pydeps should be pointed at, deepest-last.

    Each tracked ``__init__.py`` contributes its directory; that directory is
    then ascended to the import root that owns it (see ``_ascend_to_import_root``)
    and the results are de-duplicated. Ordering is (depth, path) so a run is
    reproducible and the shallowest root wins any namespace contest.
    """

    package_dirs = {_parent_dir(path) for path in tracked_files if _is_init_py(path)}
    roots = {_ascend_to_import_root(directory, package_dirs) for directory in package_dirs}
    return sorted(roots, key=lambda root: (root.count("/"), root))


def _ascend_to_import_root(package_dir: str, package_dirs: set[str]) -> str:
    """Walk ``package_dir`` up to the directory that is actually on ``sys.path``.

    Two moves, in order. First, climb through *contiguous* package ancestors —
    ``a/b/c`` collapses to ``a/b`` when ``a/b`` also carries an ``__init__.py``,
    because pydeps names modules from the outermost package. Second, take at
    most one hop into a depth-1 parent whose basename is a valid Python
    identifier: the repository root is what sits on ``sys.path``, so ``scripts``
    is the import root of ``scripts/project_metrics`` (and yields the truer
    ``scripts.*`` module names plus any loose sibling modules). The hop is
    deliberately capped at depth 1 — climbing further would collapse a
    src-layout package such as ``eval/src/praxion_evals`` into ``eval``, where
    pydeps cannot see it at all.
    """

    current = package_dir
    while True:
        parent = _parent_dir(current)
        if not parent or parent not in package_dirs:
            break
        current = parent

    if not current:
        # An ``__init__.py`` at the repository root itself: unusual but valid.
        return _REPO_ROOT_TARGET

    parent = _parent_dir(current)
    if parent and "/" not in parent and parent.isidentifier():
        return parent
    return current


def _namespace_of(root: str) -> str:
    """Return the top-level module namespace pydeps will emit for ``root``."""

    return root.rsplit("/", 1)[-1]


def _partition_by_namespace(roots: Sequence[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Split roots into those safe to merge and those a shallower root shadows.

    Two roots with the same basename (``tests`` under two sub-projects) both
    emit a ``tests.*`` namespace, and merging them would silently attribute one
    project's modules to the other. The shallower root wins; the shadowed one is
    reported and excluded from the coverage denominator, so the loss is stated
    rather than absorbed.
    """

    kept: list[str] = []
    shadowed: list[tuple[str, str]] = []
    winner_by_namespace: dict[str, str] = {}
    for root in roots:
        namespace = _namespace_of(root)
        winner = winner_by_namespace.get(namespace)
        if winner is None:
            winner_by_namespace[namespace] = root
            kept.append(root)
            continue
        shadowed.append((root, winner))
    return kept, shadowed


def _shadowed_root_issues(shadowed: Sequence[tuple[str, str]]) -> list[str]:
    """Render one issue line per root excluded by a namespace collision."""

    return [
        f"Package root '{root}' not analyzed: its '{_namespace_of(root)}' module "
        f"namespace collides with '{winner}'."
        for root, winner in shadowed
    ]


# ---------------------------------------------------------------------------
# Multi-root sweep — one pydeps invocation per import root, merged.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SweepOutcome:
    """What a full multi-root sweep produced: merged graph, roots, failures."""

    payload: dict[str, Any]
    analyzed_roots: list[str]
    issues: list[str]
    timed_out: bool


def _sweep_package_roots(roots: Sequence[str], repo_root: str) -> _SweepOutcome:
    """Invoke pydeps once per root and merge every well-formed graph.

    A root that fails contributes an issue and is left out of
    ``analyzed_roots``, so the coverage denominator counts only what was
    genuinely analysed. The sweep continues past a failure: a partial graph
    with a stated scope beats an all-or-nothing error.
    """

    merged: dict[str, Any] = {}
    analyzed_roots: list[str] = []
    issues: list[str] = []
    timed_out = False

    for root in roots:
        raw_json, failure, root_timed_out = _run_pydeps(root, repo_root)
        timed_out = timed_out or root_timed_out
        if raw_json is None:
            issues.append(f"Package root '{root}' not analyzed: {failure}")
            continue
        payload, decode_failure = _decode_pydeps_payload(raw_json)
        if payload is None:
            issues.append(f"Package root '{root}' not analyzed: {decode_failure}")
            continue
        analyzed_roots.append(root)
        _merge_payload(merged, payload)

    return _SweepOutcome(
        payload=merged,
        analyzed_roots=analyzed_roots,
        issues=issues,
        timed_out=timed_out,
    )


def _run_pydeps(root: str, repo_root: str) -> tuple[str | None, str | None, bool]:
    """Run pydeps against one root; return ``(stdout, failure_reason, timed_out)``."""

    argv = [
        "uvx",
        "pydeps",
        root,
        "--show-deps",
        "--no-output",
        "--max-bacon",
        _MAX_BACON_UNLIMITED,
    ]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=True,
            timeout=_COLLECT_TIMEOUT_SECONDS,
            cwd=repo_root,
        )
    except subprocess.TimeoutExpired:
        return None, f"uvx pydeps timed out after {int(_COLLECT_TIMEOUT_SECONDS)}s.", True
    except subprocess.CalledProcessError as exc:
        return None, f"uvx pydeps exited with status {exc.returncode}.", False
    except FileNotFoundError:
        return None, "uvx not found on PATH during collect.", False

    return completed.stdout, None, False


def _decode_pydeps_payload(raw_json: str) -> tuple[dict[str, Any] | None, str | None]:
    """Decode one pydeps stdout blob; return ``(payload, failure_reason)``."""

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, f"pydeps JSON is not well-formed: {exc}"
    if not isinstance(payload, dict):
        return None, f"pydeps JSON root is not an object; got {type(payload).__name__}."
    return payload, None


def _merge_payload(merged: dict[str, Any], payload: dict[str, Any]) -> None:
    """Fold one root's graph into the accumulator, dropping the synthetic entry.

    The bare ``__main__`` node is pydeps' traversal artifact, not a module —
    it claims to import everything it reached, which would add a phantom
    afferent edge to every module and collide across roots. Genuine
    ``pkg/__main__.py`` modules arrive dotted and are untouched. First writer
    wins on any residual key clash, which the namespace partition has already
    made unreachable in practice.
    """

    for name, record in payload.items():
        if name == _SYNTHETIC_ENTRY_MODULE or name in merged:
            continue
        merged[name] = record


# ---------------------------------------------------------------------------
# Coverage denominator + metric rollups.
# ---------------------------------------------------------------------------


def _coverage_block(tracked_files: Sequence[str], analyzed_roots: Sequence[str]) -> dict[str, Any]:
    """Describe how much of the repository's Python the merged graph covers.

    Published beside ``cyclic_deps`` so a zero reads as "no cycles in N of M
    files" rather than as a repo-wide all-clear. ``python_file_coverage_pct``
    is ``None`` for a repository with no tracked Python at all — a ratio with
    no denominator has no honest value.
    """

    python_files = [path for path in tracked_files if path.endswith(_PY_SUFFIX)]
    analyzed = [path for path in python_files if _is_under_any_root(path, analyzed_roots)]
    total = len(python_files)
    return {
        "package_roots": list(analyzed_roots),
        "repo_python_files": total,
        "analyzed_python_files": len(analyzed),
        "python_file_coverage_pct": round(100.0 * len(analyzed) / total, 1) if total else None,
    }


def _is_under_any_root(path: str, roots: Sequence[str]) -> bool:
    """Return True when ``path`` lives under one of the analysed roots."""

    return any(root == _REPO_ROOT_TARGET or path.startswith(root + "/") for root in roots)


def _analyze_payload(payload: dict[str, Any], coverage: dict[str, Any]) -> dict[str, Any]:
    """Turn a merged pydeps graph into per-module Ca/Ce/I, SCCs, and aggregate.

    A well-formed but empty payload yields zero modules, zero cycles, and an
    aggregate reading ``total_modules=0, cyclic_deps=0`` beside the coverage
    block that bounds those zeros.
    """

    module_names: set[str] = set(payload.keys())
    graph = _build_internal_graph(payload, module_names)

    modules_block = _rollup_coupling_metrics(module_names, graph)
    non_trivial_sccs = [scc for scc in _tarjan_sccs(module_names, graph) if len(scc) > 1]

    return {
        "modules": modules_block,
        "cyclic_sccs": non_trivial_sccs,
        "aggregate": {
            "cyclic_deps": len(non_trivial_sccs),
            "total_modules": len(module_names),
            **coverage,
        },
    }


def _build_internal_graph(
    payload: dict[str, Any],
    module_names: set[str],
) -> dict[str, list[str]]:
    """Extract an internal-only adjacency list from pydeps JSON.

    External imports (targets not present in ``module_names``) are dropped so
    Ca/Ce/I reflect first-party coupling only. Duplicate imports within a
    single record are de-duplicated so a module that imports another twice
    still contributes exactly one edge to the coupling counts.

    Two further edge classes are dropped because they are properties of
    Python's import machinery rather than design decisions, and both fabricate
    cycles that do not exist in the code:

    * **Ancestor-package edges.** ``import a.b.c`` binds ``a`` and ``a.b`` as
      well, so pydeps records ``a.b.c -> a.b``. Pair that implied edge with an
      ``a/b/__init__.py`` that re-exports ``a.b.c`` — the ordinary way to give
      a package a public surface — and every such package reports as a cycle.
    * **Self-edges.** A module never depends on itself; the entry is noise in
      the coupling counts.

    The residual blind spot is a genuine ``a.b -> a`` dependency (a submodule
    importing a name defined in its own package's ``__init__``). pydeps emits
    that identically to the implied edge, so it cannot be told apart; erring
    towards suppression costs one rare true cycle, while erring the other way
    reports a cycle for every package with a public surface — which is a
    louder falsehood than the one this collector exists to prevent.
    """

    graph: dict[str, list[str]] = {}
    for source, record in payload.items():
        imports_field = record.get("imports") if isinstance(record, dict) else None
        if not isinstance(imports_field, list):
            graph[source] = []
            continue
        seen: set[str] = set()
        edges: list[str] = []
        for target in imports_field:
            if not isinstance(target, str) or target not in module_names:
                continue
            if target in seen or not _is_design_edge(source, target):
                continue
            seen.add(target)
            edges.append(target)
        graph[source] = edges
    return graph


def _is_design_edge(source: str, target: str) -> bool:
    """Return False for import edges implied by the language, not by the code."""

    return source != target and not source.startswith(target + ".")


def _rollup_coupling_metrics(
    module_names: set[str],
    graph: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Compute Ca/Ce/Instability for every module in ``module_names``.

    Efferent (Ce) is the outgoing-edge count in the internal graph. Afferent
    (Ca) is the in-degree, accumulated by scanning every source's edge list.
    Instability I = Ce / (Ca + Ce); the isolated (0/0) case returns ``None``
    so ``(instability is None) == "undefined"`` is a surfacable sentinel.
    """

    afferent: dict[str, int] = dict.fromkeys(module_names, 0)
    efferent: dict[str, int] = dict.fromkeys(module_names, 0)

    for source, targets in graph.items():
        efferent[source] = len(targets)
        for target in targets:
            afferent[target] = afferent.get(target, 0) + 1

    modules_block: dict[str, dict[str, Any]] = {}
    for name in module_names:
        ca = afferent[name]
        ce = efferent[name]
        total = ca + ce
        instability: float | None
        if total == 0:
            instability = None
        else:
            instability = ce / total
        modules_block[name] = {
            "afferent_coupling": ca,
            "efferent_coupling": ce,
            "instability": instability,
        }
    return modules_block


# ---------------------------------------------------------------------------
# Tarjan's SCC algorithm — iterative so deeply-nested import graphs (hundreds
# of thousands of modules) never trip Python's recursion limit. The fixture
# graphs are tiny, but production repos can be large; the iterative form
# adds ~15 lines over the textbook recursive sketch and is worth it.
# ---------------------------------------------------------------------------


def _tarjan_sccs(
    module_names: set[str],
    graph: dict[str, list[str]],
) -> list[list[str]]:
    """Return all strongly-connected components of the internal import graph.

    Iterative Tarjan's algorithm: each node acquires a depth-first ``index``
    and a ``lowlink`` (smallest index reachable from the node's subtree).
    When ``lowlink[v] == index[v]``, the stack is unwound down to ``v`` and
    the popped nodes form an SCC. Nodes are visited in sorted order so runs
    remain deterministic given the same input graph.
    """

    index_of: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[list[str]] = []
    next_index = 0

    # Sorted iteration order + sorted successor iteration keep traversal
    # deterministic across runs; SCC membership is unaffected, but the list
    # order within each SCC is stable and easier to debug.
    for start in sorted(module_names):
        if start in index_of:
            continue

        # Work items are (node, next_successor_idx, sorted_successors).
        work_stack: list[tuple[str, int, list[str]]] = []
        index_of[start] = next_index
        lowlink[start] = next_index
        next_index += 1
        stack.append(start)
        on_stack.add(start)
        work_stack.append((start, 0, sorted(graph.get(start, []))))

        while work_stack:
            node, successor_idx, successors = work_stack[-1]
            if successor_idx < len(successors):
                successor = successors[successor_idx]
                work_stack[-1] = (node, successor_idx + 1, successors)
                if successor not in index_of:
                    index_of[successor] = next_index
                    lowlink[successor] = next_index
                    next_index += 1
                    stack.append(successor)
                    on_stack.add(successor)
                    work_stack.append((successor, 0, sorted(graph.get(successor, []))))
                elif successor in on_stack:
                    lowlink[node] = min(lowlink[node], index_of[successor])
                continue

            # All successors processed: settle the SCC root, propagate lowlink.
            if lowlink[node] == index_of[node]:
                component: list[str] = []
                while True:
                    popped = stack.pop()
                    on_stack.discard(popped)
                    component.append(popped)
                    if popped == node:
                        break
                component.sort()
                sccs.append(component)

            work_stack.pop()
            if work_stack:
                parent = work_stack[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

    return sccs
