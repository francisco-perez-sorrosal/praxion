"""The run index: what every results file in a directory says, with a digest to check it by.

``index.json`` sits beside the results files and names each one: its file, the sha256 of its
bytes, the root of its lineage, how it ended, and per role the complete pairs and the flip label
the lineage reached. A reader with no eval code (the adoption gate) trusts a file only while its
digest still matches and cites runs through the index instead of re-deriving verdicts.

The index is derived and has one writer, :func:`write_index`: the runner calls it when a run
finalizes, ``--close`` calls it, and ``--reindex`` rebuilds it from the files alone. Nothing reads
it back here, so it cannot drift from the evidence the way a hand-edited copy could.

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
from praxion_evals.adherence.results import RunResults

INDEX_SCHEMA = 1
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
    standing = _lineage_standing([file.results for file in files])
    return {
        "schema": INDEX_SCHEMA,
        "runs": {
            file.results.run.id: _entry_of(file, *standing[file.results.run.id]) for file in files
        },
        "skipped": list(skipped),
    }


def _entry_of(file: ResultsFile, lineage_root: str, roles: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": file.name,
        "sha256": file.sha256,
        "lineage_root": lineage_root,
        "ending": _ending_kind(file.results),
        "roles": roles,
    }


def _lineage_standing(runs: Sequence[RunResults]) -> dict[str, tuple[str, dict[str, Any]]]:
    """Each run id to the root of its lineage and what the lineage reached, read as one run."""
    standing: dict[str, tuple[str, dict[str, Any]]] = {}
    for parts in results.lineages(runs):
        ids = tuple(part.run.id for part in parts)
        whole = results.merged(parts)
        roles = {
            role: {
                "complete_pairs": sum(pair.complete for pair in results.pairs_of(whole, role)),
                "flip": results.draw_of(whole, ids, role).flip,
            }
            for role in whole.catalog
        }
        for run_id in ids:
            standing[run_id] = (ids[0], roles)
    return standing


def _ending_kind(run: RunResults) -> str:
    return (run.run.extra.get("ending") or {}).get("kind", LEGACY_ENDING)
