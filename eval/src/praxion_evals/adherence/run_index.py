"""The run index: what every results file in a directory says, with a digest to check it by.

``index.json`` sits beside the results files and names each one: its file, the sha256 of its
bytes, the root of its lineage, how it ended, and per role the complete pairs, the flip label the
lineage reached and the checks its verdict scored (sorted; none without per-check verdicts). A
reader with no eval code (the adoption gate) trusts a file only while its digest still matches and
cites runs through the index instead of re-deriving verdicts.

The index is derived and has one writer, :func:`write_index`: the runner calls it when a run
finalizes, ``--close`` calls it, and ``--reindex`` rebuilds it from the files alone. Nothing reads
it back here, so it cannot drift from the evidence the way a hand-edited copy could.

:func:`standing_of` is the one place a lineage's per-role standing is built; the index entries and
the standing a finalized or closed run records in its own results file both come from it.

A continued run is one run: every part's entry carries the verdict of its whole lineage, and a
tip's recorded ``earlier`` listing (which holds its own predecessor parts) is never read.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from praxion_evals.adherence import results
from praxion_evals.adherence.model import Assessed, RoleVerdict
from praxion_evals.adherence.results import RoleStanding, RunResults

INDEX_SCHEMA = 2
LEGACY_ENDING = "legacy"  # a file written before runs recorded how they ended


@dataclass(frozen=True)
class ResultsFile:
    """A results file as the directory held it: its name, the digest of its bytes, what it says."""

    name: str
    sha256: str
    results: RunResults


def write_index(results_dir: Path) -> Path:
    """Rebuild the index of ``results_dir`` from the results files in it; atomically."""
    files, skipped = read_files(results_dir)
    path = results_dir / results.RUN_INDEX_NAME
    results.write_text_atomic(path, json.dumps(index_of(files, skipped), indent=2) + "\n")
    return path


def read_files(results_dir: Path) -> tuple[list[ResultsFile], list[str]]:
    """The results files of ``results_dir`` by name, and the names of the other JSON files.

    Refused: two files holding one run, because the index names a run once.
    """
    files: list[ResultsFile] = []
    skipped: list[str] = []
    for path in sorted(results_dir.glob("*.json")):
        if path.name == results.RUN_INDEX_NAME:
            continue
        try:
            raw = path.read_bytes()
            loaded = results.from_json(json.loads(raw))
        except (OSError, ValueError, KeyError, TypeError):  # whatever its shape, it is named
            skipped.append(path.name)
            continue
        files.append(ResultsFile(path.name, hashlib.sha256(raw).hexdigest(), loaded))
    _refuse_a_run_held_twice(files)
    return files, skipped


def _refuse_a_run_held_twice(files: Sequence[ResultsFile]) -> None:
    held: dict[str, str] = {}
    for file in files:
        run_id = file.results.run.id
        if run_id in held:
            raise ValueError(f"{held[run_id]} and {file.name} both hold run {run_id}")
        held[run_id] = file.name


def index_of(files: Sequence[ResultsFile], skipped: Sequence[str]) -> dict[str, Any]:
    """The index document (pin: ``runs`` by run id, ``skipped`` the JSON files that are no run)."""
    standing = _standing_by_run([file.results for file in files])
    return {
        "schema": INDEX_SCHEMA,
        "runs": {
            file.results.run.id: _entry_of(file, *standing[file.results.run.id]) for file in files
        },
        "skipped": list(skipped),
    }


def _entry_of(
    file: ResultsFile, lineage_root: str, roles: dict[str, RoleStanding]
) -> dict[str, Any]:
    return {
        "file": file.name,
        "sha256": file.sha256,
        "lineage_root": lineage_root,
        "ending": _ending_kind(file.results),
        "roles": {
            role: {
                "complete_pairs": s.complete_pairs,
                "flip": s.flip,
                "scored_checks": list(s.scored_checks),
            }
            for role, s in roles.items()
        },
    }


def _standing_by_run(
    runs: Sequence[RunResults],
) -> dict[str, tuple[str, dict[str, RoleStanding]]]:
    """Each run id to the root of its lineage and what the lineage stands on: one run."""
    standing: dict[str, tuple[str, dict[str, RoleStanding]]] = {}
    for parts in results.lineages(runs):
        roles = standing_of(parts)
        for part in parts:
            standing[part.run.id] = (parts[0].run.id, roles)
    return standing


def standing_of(parts: Sequence[RunResults]) -> dict[str, RoleStanding]:
    """What a lineage stands on for each role of its catalog, its ``parts`` (oldest first) read as
    one run: the complete pairs over their sessions, the flip they reached (a lineage closed on
    request reached none) and the checks the verdict scored."""
    ids = tuple(part.run.id for part in parts)
    whole = results.merged(parts)
    closed = _ending_kind(whole) == results.CLOSED_ENDING_KIND
    verdicts = results.role_verdicts(whole)
    return {
        role: RoleStanding.of(
            ids,
            sum(pair.complete for pair in results.pairs_of(whole, role)),
            results.draw_of(whole, ids, role).flip,
            _scored_checks(verdicts[role]),
            closed=closed,
        )
        for role in whole.catalog
    }


def standing_ending_at(results_dir: Path, written: RunResults) -> dict[str, RoleStanding]:
    """The standing of the lineage that ``written`` ends: the parts ``results_dir`` holds before it
    and ``written`` itself, which stands in for any file of the same run already there."""
    held = [run for run in results.read_directory(results_dir)[0] if run.run.id != written.run.id]
    lineage = next(
        parts
        for parts in results.lineages([*held, written])
        if any(part.run.id == written.run.id for part in parts)
    )
    ids = [part.run.id for part in lineage]
    return standing_of(lineage[: ids.index(written.run.id) + 1])


def _scored_checks(verdict: RoleVerdict) -> tuple[str, ...]:
    """The checks a verdict gives a per-check verdict and does not list as not covered."""
    if not isinstance(verdict, Assessed):
        return ()  # an underpowered role has no per-check verdicts
    return tuple(sorted(name for name in verdict.check_verdicts if name not in verdict.not_covered))


def _ending_kind(run: RunResults) -> str:
    return (run.run.extra.get("ending") or {}).get("kind", LEGACY_ENDING)
