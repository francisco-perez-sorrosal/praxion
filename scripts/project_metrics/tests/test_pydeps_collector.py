"""Behavioral tests for the PydepsCollector -- Python coupling + cyclic SCCs via ``uvx pydeps``.

These tests encode the behavioral contract for a Tier-1 Python-only collector
that surfaces three module-level signals:

* Afferent coupling (Ca)  -- external modules depending on this module
* Efferent coupling (Ce)  -- modules this module depends on
* Instability I = Ce / (Ca + Ce), clamped to [0.0, 1.0]

and detects import cycles as strongly-connected components (SCCs) of the
import graph. The SCC count (non-trivial components, size > 1) feeds the
aggregate ``cyclic_deps`` column.

**Import strategy** -- every test imports ``PydepsCollector`` (and protocol
symbols) inside the test body. During the BDD/TDD RED handshake the
production module does not yet exist, so top-of-module imports would break
pytest collection for every test simultaneously. Deferred imports give
per-test RED/GREEN resolution and surface specific ``ModuleNotFoundError``
for each test rather than a single collection-time crash.

**Mock strategy** -- the collector shells out to ``uvx``, ``git`` (for the
``__init__.py`` probe), and ``shutil.which``. Tests patch at the production
module's namespace (``scripts.project_metrics.collectors.pydeps_collector``)
to intercept the collector's own lookups, matching the patch-where-used
precedent established by the lizard and scc tests.

**NotApplicable trigger** -- unlike the Complexipy collector (which is
NotApplicable when no ``.py`` files exist), the Pydeps collector is
NotApplicable when the repo has ``.py`` files but no ``__init__.py`` files.
A Python project with no importable packages has no import graph to analyze;
single-file scripts or namespace-package-only repos fall into this bucket.

**SCC assertion style** -- Tarjan's algorithm (and equivalents) can visit
SCCs in any traversal order. Canonical SCCs are sets, not sequences. Tests
assert ``len(cyclic_sccs)`` and membership (frozenset comparison) rather
than list order, so the implementer can choose any reasonable SCC-detection
implementation without churning tests.

**Canonical pydeps JSON shape** -- ``uvx pydeps <pkg> --show-deps --no-show
--json`` emits a dict mapping dotted module names to records containing at
least a ``name`` and an ``imports`` list. The canned JSON below carries
just enough structure to exercise the coupling + SCC pipelines; pydeps also
emits path and bacon-number fields in real output, which the collector may
ignore.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Canned pydeps JSON fixtures.
#
# _SAMPLE_PYDEPS_JSON_CYCLIC carries two independent cycles:
#
#   Cycle 1 (2-module):  pkg.module_a <-> pkg.module_b
#   Cycle 2 (3-module):  pkg.module_x -> pkg.module_y -> pkg.module_z -> pkg.module_x
#
# Plus two acyclic modules for coupling-metric sanity:
#   pkg.leaf_consumer  -> imports pkg.module_a       (afferent contributor to A)
#   pkg.isolated_root  -> (no imports, nobody imports it)
#
# The implementer's coupling pipeline must produce (for pkg.module_a):
#   Ce = 1 (module_a imports module_b)
#   Ca = 2 (module_b imports module_a; leaf_consumer imports module_a)
#   I  = 1 / (1 + 2) = 0.333...
#
# And cyclic_sccs must list exactly two SCCs of sizes 2 and 3.
#
# _SAMPLE_PYDEPS_JSON_ACYCLIC carries a tree-shaped graph with zero cycles.
# _SAMPLE_PYDEPS_JSON_EMPTY carries a package with __init__.py but zero
# inter-module imports (all imports lists empty).
# ---------------------------------------------------------------------------

_SAMPLE_PYDEPS_JSON_CYCLIC: dict[str, dict[str, Any]] = {
    "pkg.module_a": {
        "name": "pkg.module_a",
        "path": "pkg/module_a.py",
        "imports": ["pkg.module_b"],
    },
    "pkg.module_b": {
        "name": "pkg.module_b",
        "path": "pkg/module_b.py",
        "imports": ["pkg.module_a"],
    },
    "pkg.module_x": {
        "name": "pkg.module_x",
        "path": "pkg/module_x.py",
        "imports": ["pkg.module_y"],
    },
    "pkg.module_y": {
        "name": "pkg.module_y",
        "path": "pkg/module_y.py",
        "imports": ["pkg.module_z"],
    },
    "pkg.module_z": {
        "name": "pkg.module_z",
        "path": "pkg/module_z.py",
        "imports": ["pkg.module_x"],
    },
    "pkg.leaf_consumer": {
        "name": "pkg.leaf_consumer",
        "path": "pkg/leaf_consumer.py",
        "imports": ["pkg.module_a"],
    },
    "pkg.isolated_root": {
        "name": "pkg.isolated_root",
        "path": "pkg/isolated_root.py",
        "imports": [],
    },
}

_SAMPLE_PYDEPS_JSON_ACYCLIC: dict[str, dict[str, Any]] = {
    # Simple tree:  root -> {child_a, child_b};  child_a -> leaf
    "pkg.root": {
        "name": "pkg.root",
        "path": "pkg/root.py",
        "imports": ["pkg.child_a", "pkg.child_b"],
    },
    "pkg.child_a": {
        "name": "pkg.child_a",
        "path": "pkg/child_a.py",
        "imports": ["pkg.leaf"],
    },
    "pkg.child_b": {
        "name": "pkg.child_b",
        "path": "pkg/child_b.py",
        "imports": [],
    },
    "pkg.leaf": {
        "name": "pkg.leaf",
        "path": "pkg/leaf.py",
        "imports": [],
    },
}

_SAMPLE_PYDEPS_JSON_EMPTY: dict[str, dict[str, Any]] = {
    # A package with modules but zero inter-module imports (e.g., a
    # collection of independent utilities that never import each other).
    "pkg.utility_one": {
        "name": "pkg.utility_one",
        "path": "pkg/utility_one.py",
        "imports": [],
    },
    "pkg.utility_two": {
        "name": "pkg.utility_two",
        "path": "pkg/utility_two.py",
        "imports": [],
    },
    "pkg.utility_three": {
        "name": "pkg.utility_three",
        "path": "pkg/utility_three.py",
        "imports": [],
    },
}


# Expected SCCs in the cyclic fixture (as frozensets so order is irrelevant).
_EXPECTED_CYCLIC_SCCS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"pkg.module_a", "pkg.module_b"}),
        frozenset({"pkg.module_x", "pkg.module_y", "pkg.module_z"}),
    }
)

# Git ls-files outputs for the NotApplicable probe. A repo with .py files but
# no __init__.py files is "Python source present, but no importable packages"
# -- the trigger for Pydeps NotApplicable (distinct from Complexipy, which
# triggers on zero .py files period).
_GIT_LS_FILES_NO_INIT: str = (
    "\n".join(
        [
            "README.md",
            "scripts/one_off.py",
            "scripts/another_script.py",
            "docs/index.md",
        ]
    )
    + "\n"
)

# A repo that DOES have __init__.py -- should NOT trigger NotApplicable.
_GIT_LS_FILES_WITH_INIT: str = (
    "\n".join(
        [
            "README.md",
            "pkg/__init__.py",
            "pkg/module_a.py",
            "pkg/module_b.py",
        ]
    )
    + "\n"
)


# ---------------------------------------------------------------------------
# Shared helpers.
# ---------------------------------------------------------------------------


def _make_completed_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    argv: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess for mocked ``subprocess.run`` return values."""

    return subprocess.CompletedProcess(
        args=argv or ["uvx", "pydeps"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _make_context(repo_root: Path) -> Any:
    """Build a CollectionContext from the protocol base module.

    Deferred import so the helper doesn't break collection during the RED
    handshake. ``git_sha`` is a fixed placeholder -- the pydeps collector
    does not depend on SHA content, only on repo_root for the package probe.
    """

    from scripts.project_metrics.collectors.base import CollectionContext

    return CollectionContext(
        repo_root=str(repo_root),
        window_days=90,
        git_sha="0" * 40,
    )


def _make_env() -> Any:
    """Build a default ResolutionEnv -- tests needing path injection override."""

    from scripts.project_metrics.collectors.base import ResolutionEnv

    return ResolutionEnv()


def _subprocess_dispatcher(
    version_stdout: str = "3.0.2\n",
    ls_files_stdout: str = _GIT_LS_FILES_WITH_INIT,
    pydeps_stdout: str | None = None,
    version_side_effect: Exception | None = None,
    ls_files_side_effect: Exception | None = None,
    pydeps_side_effect: Exception | None = None,
) -> Any:
    """Build a side_effect callable that dispatches by argv inspection.

    The pydeps collector invokes subprocess.run for three distinct commands:

      * ``uvx pydeps --version`` (or ``pydeps --version``) during resolve()
      * ``git ls-files`` during resolve() for the __init__.py probe
      * ``uvx pydeps <pkg> --show-deps --no-show --json`` during collect()

    A single patched subprocess.run must serve all three. This helper
    inspects the argv of each call and returns the appropriate stubbed
    result (or raises the requested exception).
    """

    def _dispatch(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = args[0] if args else kwargs.get("args") or []
        argv_str = (
            " ".join(str(x) for x in argv)
            if isinstance(argv, (list, tuple))
            else str(argv)
        )

        if "ls-files" in argv_str:
            if ls_files_side_effect is not None:
                raise ls_files_side_effect
            return _make_completed_process(stdout=ls_files_stdout, argv=list(argv))

        if "--version" in argv_str:
            if version_side_effect is not None:
                raise version_side_effect
            return _make_completed_process(stdout=version_stdout, argv=list(argv))

        # Otherwise assume it's the pydeps collect invocation.
        if pydeps_side_effect is not None:
            raise pydeps_side_effect
        return _make_completed_process(
            stdout=pydeps_stdout if pydeps_stdout is not None else "{}",
            argv=list(argv),
        )

    return _dispatch


# ---------------------------------------------------------------------------
# Static metadata -- attributes every collector advertises to the runner.
# ---------------------------------------------------------------------------


class TestPydepsStaticMetadata:
    """Class-level attributes that the runner and schema layer depend on."""

    def test_collector_name_is_pydeps(self) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        # Name becomes the JSON namespace key. Aggregate pipeline reads
        # ``pydeps.<...>`` to populate cyclic_deps; renaming silently breaks
        # the aggregate column wiring.
        assert PydepsCollector.name == "pydeps"

    def test_collector_is_not_required(self) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        # Only GitCollector is required=True per the collector-protocol ADR.
        # Pydeps is a soft dependency; its absence must not fail the run.
        assert PydepsCollector.required is False

    def test_collector_declares_python_only_language_scope(self) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        # Pydeps is a Python-specific AST-based import tracer; it advertises
        # exactly {"python"} so the runner can filter it off on non-Python
        # repositories at registration time.
        assert isinstance(PydepsCollector.languages, frozenset)
        assert PydepsCollector.languages == frozenset({"python"})


# ---------------------------------------------------------------------------
# Resolve-phase tests -- Available when uvx is on PATH and pydeps responds.
# ---------------------------------------------------------------------------


class TestPydepsResolveAvailable:
    """``resolve()`` returns Available when uvx + pydeps version probe succeeds."""

    def test_resolve_returns_available_when_uvx_and_pydeps_respond(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"

        # uvx on PATH + ``uvx pydeps --version`` returns "3.0.2" + repo has
        # __init__.py files so NotApplicable is not triggered.
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                side_effect=_subprocess_dispatcher(
                    version_stdout="pydeps, version 3.0.2\n",
                    ls_files_stdout=_GIT_LS_FILES_WITH_INIT,
                ),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Available), (
            f"Expected Available when uvx + pydeps + __init__.py are all present; "
            f"got {type(result).__name__}"
        )
        # Version must surface "3.0.2" somewhere -- some implementations strip
        # leading text ("pydeps, version 3.0.2"), others trust the pipe
        # verbatim. Substring containment is robust across both.
        assert "3.0.2" in result.version


# ---------------------------------------------------------------------------
# Resolve-phase tests -- Unavailable when uvx is absent or pydeps errors.
# ---------------------------------------------------------------------------


class TestPydepsResolveUnavailable:
    """``resolve()`` returns Unavailable when uvx is missing or pydeps errors."""

    def test_resolve_returns_unavailable_when_uvx_missing(self) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(f"{target}.shutil.which", return_value=None):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when uvx is off PATH; got {type(result).__name__}"
        )
        # Reason should mention uvx (or an equivalent marker) so the
        # "Install to improve" section can render an actionable message.
        assert "uvx" in result.reason.lower()
        # Install hint should point at installing uv (the uvx provider) or
        # pydeps itself -- either is an actionable path for the user.
        hint = result.install_hint.lower()
        assert "uv" in hint or "pydeps" in hint, (
            f"Expected install hint to reference uv or pydeps; got {result.install_hint!r}"
        )

    def test_resolve_returns_unavailable_when_pydeps_version_call_fails(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        # uvx is present, but ``uvx pydeps --version`` exits non-zero
        # (e.g., uvx cannot fetch the pydeps package for any reason).
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                side_effect=_subprocess_dispatcher(
                    version_side_effect=subprocess.CalledProcessError(
                        returncode=1, cmd=["uvx", "pydeps", "--version"]
                    ),
                ),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when pydeps --version fails; got "
            f"{type(result).__name__}"
        )

    def test_resolve_returns_unavailable_when_version_probe_times_out(
        self,
    ) -> None:
        from scripts.project_metrics.collectors.base import Unavailable
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                side_effect=_subprocess_dispatcher(
                    version_side_effect=subprocess.TimeoutExpired(
                        cmd=["uvx", "pydeps", "--version"], timeout=120
                    ),
                ),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, Unavailable), (
            f"Expected Unavailable when the version probe times out "
            f"(first-run cache fill exceeded budget); got {type(result).__name__}"
        )


# ---------------------------------------------------------------------------
# Resolve-phase tests -- NotApplicable when repo has no importable packages.
# ---------------------------------------------------------------------------


class TestPydepsResolveNotApplicable:
    """``resolve()`` returns NotApplicable on a repo with .py but no __init__.py.

    Distinct trigger from the Complexipy collector (which is NotApplicable
    on zero ``.py`` files). Pydeps requires an importable package graph to
    analyze -- a collection of single-file scripts has no import structure
    worth tracing.
    """

    def test_resolve_returns_not_applicable_when_repo_has_no_init_py(
        self,
    ) -> None:
        from scripts.project_metrics.collectors.base import NotApplicable
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        # uvx + pydeps are present, but ``git ls-files`` shows .py files
        # without any __init__.py. The NotApplicable branch must fire BEFORE
        # invoking pydeps itself -- no point running an import-graph analyzer
        # on a repo with no importable packages.
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                side_effect=_subprocess_dispatcher(
                    ls_files_stdout=_GIT_LS_FILES_NO_INIT,
                ),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, NotApplicable), (
            f"Expected NotApplicable when .py files are present but no "
            f"__init__.py is in the repo; got {type(result).__name__}"
        )

    def test_not_applicable_reason_mentions_importable_packages(self) -> None:
        from scripts.project_metrics.collectors.base import NotApplicable
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with (
            patch(f"{target}.shutil.which", return_value="/usr/local/bin/uvx"),
            patch(
                f"{target}.subprocess.run",
                side_effect=_subprocess_dispatcher(
                    ls_files_stdout=_GIT_LS_FILES_NO_INIT,
                ),
            ),
        ):
            result = collector.resolve(_make_env())

        assert isinstance(result, NotApplicable)
        # The reason must communicate WHY the collector is skipped -- the
        # MD renderer surfaces this into the namespace block, and the user
        # needs to know "no importable packages" so they don't think the
        # tool is broken.
        reason_lower = result.reason.lower()
        assert (
            "importable" in reason_lower
            or "__init__" in reason_lower
            or "package" in reason_lower
        ), (
            "Expected NotApplicable reason to mention importable packages, "
            f"__init__.py, or 'package'; got {result.reason!r}"
        )


# ---------------------------------------------------------------------------
# Collect-phase tests -- cyclic SCC detection over canned JSON.
# ---------------------------------------------------------------------------


class TestPydepsCollectCyclic:
    """``collect()`` finds all non-trivial SCCs in the import graph."""

    def test_collect_returns_ok_status_on_well_formed_cyclic_json(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        assert result.status == "ok", (
            f"Expected status='ok' on well-formed pydeps JSON; got "
            f"status={result.status!r}, issues={result.issues!r}"
        )

    def test_collect_finds_exactly_two_cyclic_sccs(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        cyclic_sccs = result.data.get("cyclic_sccs")
        assert cyclic_sccs is not None, (
            f"Expected 'cyclic_sccs' key populated in collector data; got "
            f"data keys = {list(result.data.keys())}"
        )
        assert len(cyclic_sccs) == 2, (
            f"Expected exactly two non-trivial SCCs in the fixture (2-module "
            f"cycle + 3-module cycle); got {len(cyclic_sccs)} components: "
            f"{cyclic_sccs!r}"
        )

    def test_cyclic_sccs_membership_matches_expected_sets(self, tmp_path: Path) -> None:
        """SCC traversal order is unspecified; compare as frozensets of frozensets."""

        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        cyclic_sccs = result.data.get("cyclic_sccs") or []
        # Each SCC is a list of module names; normalize to a frozenset of
        # frozensets so list-ordering + SCC-ordering variation are both
        # factored out.
        actual = frozenset(frozenset(scc) for scc in cyclic_sccs)
        assert actual == _EXPECTED_CYCLIC_SCCS, (
            f"SCC membership mismatch.\n"
            f"Expected (as frozensets): {_EXPECTED_CYCLIC_SCCS!r}\n"
            f"Actual   (as frozensets): {actual!r}\n"
            f"Raw cyclic_sccs from collector: {cyclic_sccs!r}"
        )

    def test_aggregate_cyclic_deps_equals_two_for_cyclic_fixture(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        # The aggregate block is populated by this collector and read by the
        # top-level aggregate composer. cyclic_deps counts non-trivial SCCs
        # (components of size > 1); the fixture has exactly two such SCCs.
        aggregate = result.data.get("aggregate") or result.data
        cyclic_deps = aggregate.get("cyclic_deps")
        assert cyclic_deps == 2, (
            f"Expected aggregate.cyclic_deps == 2 (one 2-module cycle + one "
            f"3-module cycle); got {cyclic_deps!r}. Full data keys: "
            f"{list(result.data.keys())}"
        )


# ---------------------------------------------------------------------------
# Collect-phase tests -- acyclic (tree-shaped) graph produces zero SCCs.
# ---------------------------------------------------------------------------


class TestPydepsCollectAcyclic:
    """A strictly-acyclic import graph produces zero cycles."""

    def test_tree_graph_produces_empty_cyclic_sccs_list(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_ACYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        cyclic_sccs = result.data.get("cyclic_sccs")
        assert cyclic_sccs == [], (
            f"Expected empty cyclic_sccs on a tree-shaped dep graph; got "
            f"{cyclic_sccs!r}"
        )

    def test_tree_graph_aggregate_cyclic_deps_is_zero(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_ACYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        aggregate = result.data.get("aggregate") or result.data
        assert aggregate.get("cyclic_deps") == 0, (
            f"Expected aggregate.cyclic_deps == 0 on acyclic graph; got "
            f"{aggregate.get('cyclic_deps')!r}"
        )

    def test_empty_import_graph_has_zero_cycles_and_matches_module_count(
        self, tmp_path: Path
    ) -> None:
        """A package with __init__.py but no inter-module imports still collects."""

        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_EMPTY),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        aggregate = result.data.get("aggregate") or result.data
        assert aggregate.get("cyclic_deps") == 0, (
            f"Expected cyclic_deps == 0 on graph with zero edges; got "
            f"{aggregate.get('cyclic_deps')!r}"
        )
        assert aggregate.get("total_modules") == 3, (
            f"Expected total_modules == 3 (three independent utility modules "
            f"in fixture); got {aggregate.get('total_modules')!r}"
        )


# ---------------------------------------------------------------------------
# Collect-phase tests -- per-module Ca/Ce/instability coupling metrics.
# ---------------------------------------------------------------------------


class TestPydepsCouplingMetrics:
    """Per-module afferent/efferent/instability rollups match canned JSON."""

    def test_modules_block_contains_every_module_from_fixture(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        modules_block = result.data.get("modules")
        assert modules_block, (
            f"Expected 'modules' block populated in collector data; keys: "
            f"{list(result.data.keys())}"
        )
        # Every module from the canned JSON must surface in the per-module
        # rollup, including the isolated root with (Ca, Ce) = (0, 0).
        for expected_module in _SAMPLE_PYDEPS_JSON_CYCLIC:
            assert expected_module in modules_block, (
                f"Expected per-module entry for {expected_module!r}; got "
                f"{list(modules_block.keys())!r}"
            )

    def test_module_a_efferent_coupling_counts_outgoing_imports(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        modules_block = result.data.get("modules") or {}
        module_a = modules_block.get("pkg.module_a", {})
        # pkg.module_a imports exactly one module (pkg.module_b) -- Ce = 1.
        assert module_a.get("efferent_coupling") == 1, (
            f"Expected efferent_coupling == 1 for pkg.module_a (imports "
            f"only pkg.module_b); got {module_a.get('efferent_coupling')!r}. "
            f"Full module entry: {module_a!r}"
        )

    def test_module_a_afferent_coupling_counts_incoming_imports(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        modules_block = result.data.get("modules") or {}
        module_a = modules_block.get("pkg.module_a", {})
        # Two modules import pkg.module_a: pkg.module_b (cycle back-edge) and
        # pkg.leaf_consumer. So Ca = 2.
        assert module_a.get("afferent_coupling") == 2, (
            f"Expected afferent_coupling == 2 for pkg.module_a (imported by "
            f"pkg.module_b and pkg.leaf_consumer); got "
            f"{module_a.get('afferent_coupling')!r}. Full module entry: "
            f"{module_a!r}"
        )

    def test_module_a_instability_equals_ce_over_ca_plus_ce(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        modules_block = result.data.get("modules") or {}
        module_a = modules_block.get("pkg.module_a", {})
        # I = Ce / (Ca + Ce) = 1 / (2 + 1) = 0.3333...
        instability = module_a.get("instability")
        assert instability is not None, (
            f"Expected 'instability' populated for pkg.module_a; got None. "
            f"Module entry: {module_a!r}"
        )
        assert abs(instability - (1 / 3)) < 1e-6, (
            f"Expected instability ~= 1/3 (0.3333...) for pkg.module_a "
            f"(Ce=1, Ca=2); got {instability!r}"
        )
        # Instability is defined on [0.0, 1.0] -- a value outside that range
        # is a computation bug regardless of how the fraction rolled out.
        assert 0.0 <= instability <= 1.0

    def test_isolated_module_with_no_edges_has_instability_defined(
        self, tmp_path: Path
    ) -> None:
        """An unconnected module (Ca = Ce = 0) must not crash the instability rollup.

        Division by zero is the real hazard here. Common conventions pin the
        instability of a fully-isolated module at 0.0 (maximally stable) or
        leave it None; the test accepts either, but a NaN or ZeroDivisionError
        would be a contract violation.
        """

        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_CYCLIC),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        modules_block = result.data.get("modules") or {}
        isolated = modules_block.get("pkg.isolated_root", {})
        # Zero edges: Ca = 0, Ce = 0.
        assert isolated.get("afferent_coupling") == 0
        assert isolated.get("efferent_coupling") == 0
        instability = isolated.get("instability")
        # Accept None (sentinel) or 0.0 (conventional "maximally stable"); a
        # float that isn't either is suspect, and NaN / ZeroDivisionError
        # are contract violations.
        assert instability is None or instability == 0.0, (
            f"Expected instability of fully-isolated module to be None or 0.0 "
            f"(safe handling of 0/0); got {instability!r}"
        )


# ---------------------------------------------------------------------------
# Skip-marker shape -- delegates to the shared helper.
# ---------------------------------------------------------------------------


class TestPydepsSkipMarker:
    """When pydeps is Unavailable/NotApplicable, the namespace carries the uniform marker."""

    def test_skip_marker_for_pydeps_has_uniform_three_key_shape(self) -> None:
        from scripts.project_metrics.collectors.base import (
            skip_marker_for_namespace,
        )

        marker = skip_marker_for_namespace("pydeps")

        # Three-key shape pinned by the graceful-degradation ADR: the MD
        # renderer consumes this exact shape across every collector's
        # namespace when it's skipped, regardless of WHY it was skipped.
        assert marker == {
            "status": "skipped",
            "reason": "tool_unavailable",
            "tool": "pydeps",
        }


# ---------------------------------------------------------------------------
# Collect-phase timeout handling -- graceful downgrade rather than propagation.
# ---------------------------------------------------------------------------


class TestPydepsCollectTimeout:
    """A TimeoutExpired during collect() downgrades cleanly, never raises uncaught.

    Per the collector-protocol ADR, collect() must downgrade analysis-level
    errors to status='error'/'timeout' rather than propagating. The runner's
    try/except is a safety net for bugs, not the primary error path.
    """

    def test_collect_downgrades_on_timeout_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.pydeps_collector import (
            PydepsCollector,
        )

        collector = PydepsCollector()
        target = "scripts.project_metrics.collectors.pydeps_collector"
        with patch(
            f"{target}.subprocess.run",
            side_effect=_subprocess_dispatcher(
                pydeps_side_effect=subprocess.TimeoutExpired(
                    cmd=["uvx", "pydeps", "pkg"], timeout=120
                ),
            ),
        ):
            result = collector.collect(_make_context(tmp_path))

        assert result.status in ("timeout", "error"), (
            f"Expected graceful downgrade to status='timeout' or 'error' on "
            f"subprocess timeout; got status={result.status!r}"
        )


# ---------------------------------------------------------------------------
# Guard against silent flag drift in the pydeps invocation.
# ---------------------------------------------------------------------------


def test_collect_invokes_pydeps_with_json_and_show_deps_flags(tmp_path: Path) -> None:
    """The collect() invocation must ask pydeps for JSON dep output.

    The JSON parser is tuned to the shape pydeps emits under
    ``--show-deps --no-show --json``. A silent switch to the default output
    format (SVG/DOT) would yield parse errors; worse, a silent switch to
    ``--only`` or ``--externals`` would change the result shape in a way
    the parser might still accept, silently producing wrong metrics. This
    defensive test pins the argv shape at the subprocess boundary.
    """

    from scripts.project_metrics.collectors.pydeps_collector import (
        PydepsCollector,
    )

    collector = PydepsCollector()
    target = "scripts.project_metrics.collectors.pydeps_collector"
    mock_run = MagicMock(
        side_effect=_subprocess_dispatcher(
            pydeps_stdout=json.dumps(_SAMPLE_PYDEPS_JSON_ACYCLIC),
        )
    )
    with patch(f"{target}.subprocess.run", mock_run):
        collector.collect(_make_context(tmp_path))

    # At least one invocation must carry --json and --show-deps in its argv.
    # Accept either positional (args[0]) or kwarg (args=) forms to stay
    # robust across subprocess.run invocation styles.
    found_json_flag = False
    found_show_deps_flag = False
    for call in mock_run.call_args_list:
        argv_candidate = call.args[0] if call.args else call.kwargs.get("args", [])
        if isinstance(argv_candidate, (list, tuple)):
            if "--json" in argv_candidate:
                found_json_flag = True
            if "--show-deps" in argv_candidate:
                found_show_deps_flag = True
    assert found_json_flag, (
        "Expected collect() to invoke pydeps with --json; none of the "
        f"observed subprocess.run calls carried that flag. Calls: "
        f"{mock_run.call_args_list!r}"
    )
    assert found_show_deps_flag, (
        "Expected collect() to invoke pydeps with --show-deps; none of the "
        f"observed subprocess.run calls carried that flag. Calls: "
        f"{mock_run.call_args_list!r}"
    )
