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

* ``collect()`` picks a ``<package_root>`` (shallowest directory that contains
  an ``__init__.py`` per ``git ls-files`` output; lexicographic tie-break),
  then runs ``uvx pydeps <package_root> --show-deps --no-show --json`` with
  a 60s deadline. The resulting JSON maps dotted module names to records
  with at least ``name`` and ``imports``; the collector computes per-module
  Ca/Ce/I over the internal-only import graph and runs an iterative
  Tarjan-style SCC sweep to find non-trivial cycles.

Internal-edges-only policy: only imports whose targets appear as keys in the
pydeps JSON contribute to Ca/Ce. External imports (``os``, ``typing``, third
parties) are infrastructure, not first-party coupling, and should not inflate
the signal. This matches the canonical Ca/Ce definitions used in Martin's
package-metrics literature.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
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
_FIRST_RUN_HINT: str = (
    "project-metrics: resolving Tier 1 tools "
    "(first-run uvx cache fill, may take up to 120s)"
)
_UVX_INSTALL_HINT: str = "install uv: https://docs.astral.sh/uv/"
_UVX_NOT_FOUND_REASON: str = "uvx not found on PATH (pydeps requires uvx to resolve)"
_NOT_APPLICABLE_REASON: str = (
    "No importable Python packages detected — no __init__.py files found"
)
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

        self._configured_repo_root: Path | None = (
            Path(repo_root) if repo_root is not None else None
        )

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
        """Run ``uvx pydeps <pkg> --show-deps --no-show --json`` and roll up metrics."""

        package_root = _pick_package_root(ctx.repo_root)
        if package_root is None:
            return CollectorResult(
                status="error",
                data={},
                issues=[
                    "No __init__.py found via git ls-files during collect; "
                    "cannot locate a package root for pydeps."
                ],
            )

        try:
            completed = subprocess.run(
                [
                    "uvx",
                    "pydeps",
                    package_root,
                    "--show-deps",
                    "--no-show",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=_COLLECT_TIMEOUT_SECONDS,
                cwd=ctx.repo_root,
            )
        except subprocess.TimeoutExpired:
            return CollectorResult(
                status="timeout",
                data={},
                issues=[
                    f"uvx pydeps timed out after {int(_COLLECT_TIMEOUT_SECONDS)}s."
                ],
            )
        except subprocess.CalledProcessError as exc:
            return CollectorResult(
                status="error",
                data={},
                issues=[f"uvx pydeps exited with status {exc.returncode}."],
            )
        except FileNotFoundError:
            return CollectorResult(
                status="error",
                data={},
                issues=["uvx not found on PATH during collect."],
            )

        return _parse_pydeps_json(completed.stdout)


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

    for raw_line in ls_files_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith("/" + _INIT_PY_FILENAME) or line == _INIT_PY_FILENAME:
            return True
    return False


# ---------------------------------------------------------------------------
# Package-root picker — shallowest-depth __init__.py wins; lexicographic tie.
# ---------------------------------------------------------------------------


def _pick_package_root(repo_root: str) -> str | None:
    """Pick the shallowest ``__init__.py``-carrying directory as the package root.

    Runs ``git ls-files`` under ``repo_root``, collects every ``__init__.py``
    path, picks the shallowest (fewest path separators) with lexicographic
    tie-break, and returns the parent directory of the chosen ``__init__.py``
    as a repo-relative string. Returns ``None`` when the probe produces zero
    candidates — the caller surfaces this as ``status='error'``.
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

    init_paths: list[str] = []
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith("/" + _INIT_PY_FILENAME) or line == _INIT_PY_FILENAME:
            init_paths.append(line)

    if not init_paths:
        return None

    init_paths.sort(key=lambda p: (p.count("/"), p))
    chosen = init_paths[0]
    if chosen == _INIT_PY_FILENAME:
        # Package lives at the repo root itself (unusual but valid).
        return "."
    parent = chosen.rsplit("/", 1)[0]
    return parent


# ---------------------------------------------------------------------------
# Pydeps JSON parsing + metric rollups.
# ---------------------------------------------------------------------------


def _parse_pydeps_json(raw_json: str) -> CollectorResult:
    """Parse pydeps JSON into per-module Ca/Ce/I plus cyclic SCC list + aggregate.

    Returns ``status='error'`` on malformed JSON. Well-formed but empty input
    yields a populated result with zero modules, zero cycles, and an
    aggregate block reading ``total_modules=0, cyclic_deps=0``.
    """

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return CollectorResult(
            status="error",
            data={},
            issues=[f"pydeps JSON is not well-formed: {exc}"],
        )

    if not isinstance(payload, dict):
        return CollectorResult(
            status="error",
            data={},
            issues=[
                f"pydeps JSON root is not an object; got {type(payload).__name__}."
            ],
        )

    module_names: set[str] = set(payload.keys())
    graph = _build_internal_graph(payload, module_names)

    modules_block = _rollup_coupling_metrics(module_names, graph)
    sccs = _tarjan_sccs(module_names, graph)
    non_trivial_sccs = [scc for scc in sccs if len(scc) > 1]

    aggregate = {
        "cyclic_deps": len(non_trivial_sccs),
        "total_modules": len(module_names),
    }

    return CollectorResult(
        status="ok",
        data={
            "modules": modules_block,
            "cyclic_sccs": non_trivial_sccs,
            "aggregate": aggregate,
        },
    )


def _build_internal_graph(
    payload: dict[str, Any],
    module_names: set[str],
) -> dict[str, list[str]]:
    """Extract an internal-only adjacency list from pydeps JSON.

    External imports (targets not present in ``module_names``) are dropped so
    Ca/Ce/I reflect first-party coupling only. Duplicate imports within a
    single record are de-duplicated so a module that imports another twice
    still contributes exactly one edge to the coupling counts.
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
            if not isinstance(target, str):
                continue
            if target not in module_names:
                continue
            if target in seen:
                continue
            seen.add(target)
            edges.append(target)
        graph[source] = edges
    return graph


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

    afferent: dict[str, int] = {name: 0 for name in module_names}
    efferent: dict[str, int] = {name: 0 for name in module_names}

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
