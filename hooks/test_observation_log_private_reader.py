"""The observation log has no private readers.

The registry's invariant: the set of code consumers of the log equals the set
of non-test modules importing `_observation_log.reader`. Two checks enforce it:

- the import check parses every candidate module and asserts its reader
  importers equal the `code` entries of `registry.CONSUMERS` -- a module
  calling `reader.read_rows` without being declared fails here;
- the filename check flags any `.py` file -- outside the owner package and a
  named allowlist -- whose source references the log filename literal
  (`reader.LOG_FILENAME`) directly, which is how a reader could bypass the
  owner package altogether.

Declared limit: an import built from a computed string (`importlib`,
`__import__`) is invisible to both checks; none exist today.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hooks._observation_log import reader, registry
from hooks._observation_log.modes import Mode
from hooks._observation_scan_testkit import candidate_modules, importers_of

REPO_ROOT = Path(__file__).resolve().parent.parent

# Modules that name the log file without reading its rows, so they
# legitimately stay outside the owner reader. Filename check only: a module
# that imports the reader is a reader and must be declared regardless.
ALLOWLIST = frozenset(
    {
        "scripts/merge_driver_observations.py",  # whole-file merge with a dedup key
        "scripts/reconcile_ai_state.py",  # whole-file merge with a dedup key
        "scripts/_sidecar_init.py",  # writes the .gitattributes string
        "eval/src/praxion_evals/live/scenarios.py",  # hook-byproduct file list
        "scripts/check_gate_liveness.py",  # the liveness checker itself
        # Acceptance driver: observes the log through the filesystem as a black
        # box, never through the package, so it reads no row via the reader.
        "tests/acceptance/drivers/observation_harness.py",
        # Acceptance driver: names the project log only to seed it and compare its
        # bytes from outside, through the filesystem; it reads no row via the reader.
        "tests/acceptance/drivers/gate_liveness.py",
        # Acceptance driver: writes an onboarded project's `.gitattributes` line
        # and merge-driver config as fixture text; it reads no row via the reader.
        "tests/acceptance/drivers/hook_installation.py",
    }
)

# Importer -> the declared consumer it belongs under. The cost collector's
# read pass (td-237) and the kernel checker's liveness mode were split out of
# their entry modules for size; the registry declares each component under the
# entry module.
_COMPANION_MODULES = {
    "scripts/project_metrics/collectors/cost_collector_read.py": (
        "scripts/project_metrics/collectors/cost_collector.py"
    ),
    "scripts/kernel_liveness.py": "scripts/check_kernel_manifest.py",
}


def _referencing_modules(root: Path) -> list[str]:
    """Candidate modules outside the allowlist whose source references the
    log filename literal."""
    return [
        rel
        for rel, path in candidate_modules(root)
        if rel not in ALLOWLIST
        and reader.LOG_FILENAME in path.read_text(encoding="utf-8", errors="replace")
    ]


def _declared_code_modules(consumers) -> frozenset[str]:
    """Module paths of the `code` consumers; the `#need` fragment drops
    because the registry is need-grain and this equality is file-grain."""
    return frozenset(c.name.partition("#")[0] for c in consumers if c.kind == "code")


def _consumer_equality_delta(importers, consumers, companions) -> tuple[list[str], list[str]]:
    """Pure: (undeclared importers, declared modules importing nothing), each
    sorted; both empty when the two sets are equal."""
    mapped = {companions.get(rel, rel) for rel in importers}
    declared = _declared_code_modules(consumers)
    return sorted(mapped - declared), sorted(declared - mapped)


def test_no_undeclared_module_references_the_log_filename_directly() -> None:
    findings = _referencing_modules(REPO_ROOT)

    assert findings == [], (
        "these modules reference the log filename outside the owner package "
        f"and its allowlist: {findings}"
    )


def test_canary_a_synthetic_undeclared_reader_is_caught(tmp_path: Path) -> None:
    """Gate-liveness canary: a module outside the owner package and the
    allowlist that references the log filename directly must be flagged.
    """
    rogue = tmp_path / "scripts" / "rogue_reader.py"
    rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.write_text(f'path = "{reader.LOG_FILENAME}"\n', encoding="utf-8")

    findings = _referencing_modules(tmp_path)

    assert findings == ["scripts/rogue_reader.py"]


def test_reader_importers_equal_declared_code_consumers() -> None:
    importers, unparseable = importers_of(REPO_ROOT, "reader")

    assert unparseable == (), f"candidate modules failed to parse: {unparseable}"
    assert set(_COMPANION_MODULES) <= importers, "a companion no longer imports the reader"
    assert set(_COMPANION_MODULES.values()) <= _declared_code_modules(registry.CONSUMERS), (
        "a companion maps to an undeclared module"
    )
    undeclared, unimported = _consumer_equality_delta(
        importers, registry.CONSUMERS, _COMPANION_MODULES
    )
    assert (undeclared, unimported) == ([], []), (
        f"reader importers not declared in registry.CONSUMERS: {undeclared}; "
        f"declared code consumers that do not import the reader: {unimported}"
    )


@pytest.mark.parametrize(
    "import_line",
    [
        "from _observation_log import reader",
        "from hooks._observation_log import reader as r",
        "from hooks._observation_log.reader import read_rows",
        "import _observation_log.reader",
        "def load():\n    from _observation_log import reader\n    return reader",
    ],
)
def test_canary_a_synthetic_undeclared_importer_is_caught(tmp_path: Path, import_line: str) -> None:
    """Gate-liveness canary: an undeclared module that imports the reader
    without naming the log filename must fail the equality check -- and slip
    past the filename check, which is the gap the import check closes.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("declared_reader.py", "rogue_reader.py"):
        (scripts / name).write_text(f"{import_line}\n", encoding="utf-8")
    declared = [registry.ConsumerSpec("scripts/declared_reader.py", "code", {}, Mode.STANDARD)]

    importers, unparseable = importers_of(tmp_path, "reader")

    assert unparseable == ()
    assert _consumer_equality_delta(importers, declared, {}) == (["scripts/rogue_reader.py"], [])
    assert _referencing_modules(tmp_path) == []
