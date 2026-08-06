"""Tests for check_template_mirrors.py -- the shipped-template mirror gate.

A file under ``claude/aac-templates/`` that ``/onboard-project`` copies verbatim
into a managed project, and whose installed counterpart this repo also carries,
must stay byte-identical to that counterpart.  This file is the gate's canary set
(rules/swe/gate-liveness.md: a CODE gate ships proof it *fails* on a known-bad
input, not merely that it passes on the current good state).

Behavioral tests:

1. The real repo's registered mirror pairs are in sync (the no-op control --
   without it, a gate that flags nothing would pass every canary below).
2. CANARY: a template diverged from its source is flagged, with both paths and a
   diff naming the change.
3. CANARY: a registered mirror file that does not exist is a *script error*
   (exit 2), not a silent skip -- an un-shipped template must not read as "in
   sync", and ``--write`` must not paper over it by recreating the file.
4. ``--write`` propagates source -> template and leaves the source untouched.
   The direction is the safety property: the source is the copy pytest actually
   loads, the template is inert text.
5. CANARY: the CLI surface exits non-zero on a diverged tree and zero on a clean
   one -- the exit code is what the pre-commit hook reads.
6. The ``.pre-commit-config.yaml`` hook's ``files:`` pattern matches *every*
   registered path, both halves of every pair.  Drift is created by editing
   either side, so a pattern covering only one is a blind gate.
7. CANARY: a ``files:`` pattern that misses one half is reported -- the proof
   that test 6 is capable of failing.
8. The ``files:`` pattern does not match the non-mirror templates alongside it
   (scope fidelity: an over-broad pattern would run the gate on files it has no
   claim over, and each spurious run trains a reader to ignore it).

Every mutating test builds its tree under ``tmp_path``; the real repo is only
ever read.
"""

from __future__ import annotations

import functools
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_template_mirrors.py"
_REPO_ROOT = Path(__file__).resolve().parent.parent


@functools.lru_cache(maxsize=1)
def _gate() -> Any:
    """Load the gate module under test, caching it across tests."""
    spec = importlib.util.spec_from_file_location("check_template_mirrors", _SCRIPT_PATH)
    assert spec is not None, f"gate module not importable at {_SCRIPT_PATH}"
    assert spec.loader is not None, f"gate module has no loader at {_SCRIPT_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_tree(root: Path, *, source_body: str, template_body: str | None) -> None:
    """Materialize every registered mirror pair under root with the given bodies.

    ``template_body=None`` omits the template entirely, exercising the
    missing-file path.
    """
    for mirror in _gate().MIRRORS:
        source = root / mirror.source
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(source_body, encoding="utf-8")

        if template_body is None:
            continue
        template = root / mirror.template
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text(template_body, encoding="utf-8")


_GOOD = '"""Shared fixtures."""\n\nFIXTURE = 1\n'
_DIVERGED = '"""Shared fixtures."""\n\nFIXTURE = 2\n'


# ---------------------------------------------------------------------------
# 1. Control: the real repo is clean
# ---------------------------------------------------------------------------


def test_real_repo_mirror_pairs_are_in_sync() -> None:
    """Every registered pair in this repo is byte-identical right now."""
    drifted = _gate().check_mirrors(_REPO_ROOT)
    assert drifted == [], "registered mirror pairs have diverged: " + ", ".join(
        f"{d.mirror.template} != {d.mirror.source}" for d in drifted
    )


# ---------------------------------------------------------------------------
# 2-3. Canaries: the gate bites
# ---------------------------------------------------------------------------


def test_flags_template_diverged_from_its_source(tmp_path: Path) -> None:
    """Canary: a template whose bytes differ from its source is reported."""
    _build_tree(tmp_path, source_body=_GOOD, template_body=_DIVERGED)

    drifted = _gate().check_mirrors(tmp_path)

    assert len(drifted) == len(_gate().MIRRORS), f"every pair must be flagged; got: {drifted}"
    diff_text = "".join(drifted[0].diff)
    assert "FIXTURE = 1" in diff_text, f"the diff must show the source side; got:\n{diff_text}"
    assert "FIXTURE = 2" in diff_text, f"the diff must show the template side; got:\n{diff_text}"
    assert drifted[0].mirror.source in diff_text, "the diff must name the source path"
    assert drifted[0].mirror.template in diff_text, "the diff must name the template path"


def test_flags_missing_template_as_a_script_error(tmp_path: Path) -> None:
    """Canary: an absent template exits 2 rather than reading as in-sync."""
    _build_tree(tmp_path, source_body=_GOOD, template_body=None)

    with pytest.raises(SystemExit) as excinfo:
        _gate().check_mirrors(tmp_path)

    assert excinfo.value.code == 2, f"a missing mirror file must exit 2; got {excinfo.value.code}"


# ---------------------------------------------------------------------------
# 4. Direction: --write publishes the exercised copy outward, never inward
# ---------------------------------------------------------------------------


def test_write_overwrites_the_template_and_leaves_the_source_untouched(tmp_path: Path) -> None:
    """--write copies source -> template; the source is never the thing rewritten."""
    _build_tree(tmp_path, source_body=_GOOD, template_body=_DIVERGED)

    updated = _gate().write_mirrors(tmp_path)

    assert len(updated) == len(_gate().MIRRORS), f"every drifted pair must be rewritten: {updated}"
    for mirror in _gate().MIRRORS:
        assert (tmp_path / mirror.source).read_text(encoding="utf-8") == _GOOD, (
            f"--write must not modify the source {mirror.source}"
        )
        assert (tmp_path / mirror.template).read_text(encoding="utf-8") == _GOOD, (
            f"--write must rewrite the template {mirror.template} from its source"
        )
    assert _gate().check_mirrors(tmp_path) == [], "--write must leave the tree in sync"


def test_write_is_a_no_op_on_an_already_synced_tree(tmp_path: Path) -> None:
    """A clean tree reports nothing updated -- --write is idempotent."""
    _build_tree(tmp_path, source_body=_GOOD, template_body=_GOOD)

    assert _gate().write_mirrors(tmp_path) == []


# ---------------------------------------------------------------------------
# 5. Canary: the CLI exit code the pre-commit hook actually reads
# ---------------------------------------------------------------------------


def test_cli_exits_nonzero_on_a_diverged_tree(tmp_path: Path) -> None:
    """Canary: --check returns 1 on drift and 0 once the tree is repaired."""
    _build_tree(tmp_path, source_body=_GOOD, template_body=_DIVERGED)

    assert _gate().main(["--check", "--repo-root", str(tmp_path)]) == 1

    assert _gate().main(["--write", "--repo-root", str(tmp_path)]) == 0
    assert _gate().main(["--check", "--repo-root", str(tmp_path)]) == 0


# ---------------------------------------------------------------------------
# 6-8. Wiring: the pre-commit `files:` pattern must cover both halves
# ---------------------------------------------------------------------------


def _hook_files_pattern(repo_root: Path) -> str:
    """Return the `files:` regex of the mirror hook in .pre-commit-config.yaml."""
    config = yaml.safe_load((repo_root / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook.get("id") == _gate().HOOK_ID:
                return hook["files"]
    raise AssertionError(
        f"no hook with id {_gate().HOOK_ID!r} in .pre-commit-config.yaml -- "
        "the gate is not wired into the commit gate at all"
    )


def _uncovered_mirror_paths(pattern: str, mirrors: tuple[Any, ...]) -> list[str]:
    """Return every registered path the pattern fails to match.

    ``re.search`` mirrors how pre-commit applies `files:` to a repo-relative path.
    """
    compiled = re.compile(pattern)
    return [
        path
        for mirror in mirrors
        for path in (mirror.source, mirror.template)
        if not compiled.search(path)
    ]


def test_precommit_pattern_covers_both_halves_of_every_mirror_pair() -> None:
    """Drift is created by editing either side, so both must trigger the hook."""
    uncovered = _uncovered_mirror_paths(_hook_files_pattern(_REPO_ROOT), _gate().MIRRORS)
    assert uncovered == [], (
        "the template-mirror hook's `files:` pattern does not match: "
        + ", ".join(uncovered)
        + " -- editing those paths would not fire the gate"
    )


def test_flags_a_precommit_pattern_that_misses_one_half_of_a_pair() -> None:
    """Canary: a source-only pattern is reported, proving the coverage test bites."""
    source_only = "^" + re.escape(_gate().MIRRORS[0].source) + "$"

    uncovered = _uncovered_mirror_paths(source_only, _gate().MIRRORS)

    assert _gate().MIRRORS[0].template in uncovered, (
        f"a pattern covering only the source must report the template; got: {uncovered}"
    )


@pytest.mark.parametrize(
    "non_mirror",
    [
        "claude/aac-templates/fitness-README.md.tmpl",
        "claude/aac-templates/fitness-test-starter.py.tmpl",
        "fitness/tests/test_starter_rule.py",
    ],
)
def test_precommit_pattern_does_not_match_non_mirror_neighbours(non_mirror: str) -> None:
    """Scope fidelity: starters legitimately diverge and must not trigger the gate."""
    pattern = re.compile(_hook_files_pattern(_REPO_ROOT))
    assert not pattern.search(non_mirror), (
        f"{non_mirror} is a starter, not a mirror -- the hook pattern must not claim it"
    )
