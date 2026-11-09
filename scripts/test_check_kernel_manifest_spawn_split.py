"""Canaries for I11: a split recipient receives exactly the split its sources give it now.

Each canary breaks one thing in a copy of the live inputs, shows the checker refuses it naming
the unit (or exits non-zero when the artifact cannot be read), writes back the bytes it changed
and shows the copy passes again.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _kernel_checker_testkit as kit  # noqa: E402
import check_kernel_manifest as cb  # noqa: E402
import kernel_model as km  # noqa: E402
from _kernel_checker_testkit import kinds, subjects  # noqa: E402

rd = cb.rd  # the hook's pure module, as the checker imports it

# pytest finds a fixture by name in the module that uses it
repo = kit.repo
template = kit.template

PROTOCOL = "swe/swe-agent-coordination-protocol"
INTERMEDIATE = "swe/agent-intermediate-documents"
SPLIT_UNITS = [PROTOCOL, INTERMEDIATE]
SOURCES = {unit.unit_id: unit.path for unit in rd.MANAGED_CORE_UNITS}
# A section each split unit drops for a split recipient.
DROPPED_HEADINGS = {
    PROTOCOL: "### Available Agents\n",
    INTERMEDIATE: "### Document Lifecycle\n",
}
DRIFT = "I11-spawn-split-drift"
UNREADABLE = "I11-spawn-split-unreadable"
PLANTED_LINE = "A planted line nobody regenerated.\n"
# The files a plant may change: a restore writes each back to its bytes from before the plant.
PLANTABLE = (*SOURCES.values(), km.MANIFEST_PATH, rd.SPAWN_SPLIT_PATH)


# -- Plants: each leaves one kind of disagreement in the checkout --------------------------------


def stale_source(unit_id: str) -> Callable[[Path], None]:
    """A line added to a dropped section: the stored split no longer matches its source."""

    def plant(root: Path) -> None:
        path, heading = root / SOURCES[unit_id], DROPPED_HEADINGS[unit_id]
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(heading, f"{heading}\n{PLANTED_LINE}", 1), encoding="utf-8")

    return plant


def reclassified(root: Path) -> None:
    """A dropped section reclassified as kept: the split was cut under another manifest."""
    path = root / km.MANIFEST_PATH
    dropped = 'heading: "Available Agents"\n    scope: orchestrator-only'
    text = path.read_text(encoding="utf-8")
    assert dropped in text, "the manifest no longer drops Available Agents"
    path.write_text(text.replace(dropped, dropped.replace("orchestrator-only", "no-actor")))


def edit_split(change: Callable[[dict], None]) -> Callable[[Path], None]:
    def plant(root: Path) -> None:
        path = root / rd.SPAWN_SPLIT_PATH
        artifact = json.loads(path.read_text(encoding="utf-8"))
        change(artifact["units"][INTERMEDIATE])
        path.write_text(json.dumps(artifact), encoding="utf-8")

    return plant


def text_edited(entry: dict) -> None:
    """The stored text changed and its digest left: the hook distrusts it and falls back."""
    entry["text"] += PLANTED_LINE


def text_and_digest_edited(entry: dict) -> None:
    """The stored text and its digest both changed: the hook trusts a text no source gives."""
    text_edited(entry)
    entry["text_sha256"] = hashlib.sha256(entry["text"].encode("utf-8")).hexdigest()


def artifact_bytes(data: bytes) -> Callable[[Path], None]:
    def plant(root: Path) -> None:
        (root / rd.SPAWN_SPLIT_PATH).write_bytes(data)

    return plant


def missing(root: Path) -> None:
    (root / rd.SPAWN_SPLIT_PATH).unlink()


NAMED_PLANTS = {
    "stale-protocol": (stale_source(PROTOCOL), [PROTOCOL]),
    "stale-intermediate-documents": (stale_source(INTERMEDIATE), [INTERMEDIATE]),
    "reclassified": (reclassified, SPLIT_UNITS),
    "split-text-edited": (edit_split(text_edited), [INTERMEDIATE]),
    "split-text-and-digest-edited": (edit_split(text_and_digest_edited), [INTERMEDIATE]),
}
UNREADABLE_PLANTS = {
    "not-utf-8": artifact_bytes(b"\x00\xff not what was written here {[\n"),
    "text-not-json": artifact_bytes(b"not what was written here\n"),
    "wrong-schema": artifact_bytes(b'{"schema": 0, "units": {}}\n'),
    "nested-past-the-parser": artifact_bytes(b"[" * 100_000),
    "missing": missing,
}
ALL_PLANTS = {**{name: plant for name, (plant, _) in NAMED_PLANTS.items()}, **UNREADABLE_PLANTS}


# -- The verdicts --------------------------------------------------------------------------------


def test_the_live_checkout_delivers_its_split_as_its_sources_give_it(repo: Path) -> None:
    assert kinds(repo) & {DRIFT, UNREADABLE} == set()


def test_a_crlf_checkout_delivers_the_split_its_lf_sources_give(repo: Path) -> None:
    """The checker reads a source as the hook does, newlines translated, so the artifact
    generated from LF sources is current on a checkout with CRLF line endings."""
    for rel in (*SOURCES.values(), km.MANIFEST_PATH):
        path = repo / rel
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    assert kinds(repo) & {DRIFT, UNREADABLE} == set()


@pytest.mark.parametrize("name", NAMED_PLANTS)
def test_a_disagreeing_split_is_refused_naming_each_unit_it_reaches(repo: Path, name: str) -> None:
    plant, named = NAMED_PLANTS[name]
    plant(repo)

    assert subjects(repo, DRIFT) == named


def drift_detail(root: Path) -> str:
    (finding,) = [f for f in cb.check(root) if f.kind == DRIFT]
    return finding.detail


def test_a_fallback_is_reported_as_the_whole_unit_from_its_source(repo: Path) -> None:
    stale_source(PROTOCOL)(repo)

    assert drift_detail(repo).startswith(
        f"{SOURCES[PROTOCOL]}: a split recipient receives the whole"
    )


def test_a_trusted_wrong_split_is_reported_at_its_first_differing_line(repo: Path) -> None:
    edit_split(text_and_digest_edited)(repo)

    assert f"receives {PLANTED_LINE!r}, the split has ''" in drift_detail(repo)


@pytest.mark.parametrize("name", UNREADABLE_PLANTS)
def test_an_artifact_that_cannot_be_read_is_refused_without_naming_a_unit(
    repo: Path, name: str
) -> None:
    UNREADABLE_PLANTS[name](repo)

    found = [f for f in cb.check(repo) if f.kind.startswith("I11-")]

    assert [(f.kind, f.subject) for f in found] == [(UNREADABLE, rd.SPAWN_SPLIT_PATH)]


@pytest.mark.parametrize("name", UNREADABLE_PLANTS)
def test_the_command_exits_non_zero_on_an_artifact_that_cannot_be_read(
    repo: Path, name: str
) -> None:
    UNREADABLE_PLANTS[name](repo)

    assert kit.run_checker(repo).returncode == 1


def snapshot(root: Path) -> dict[str, bytes | None]:
    return {rel: (root / rel).read_bytes() if (root / rel).is_file() else None for rel in PLANTABLE}


def restore(root: Path, original: dict[str, bytes | None]) -> None:
    for rel, data in original.items():
        if data is None:
            (root / rel).unlink(missing_ok=True)
        else:
            (root / rel).write_bytes(data)


@pytest.mark.parametrize("name", ALL_PLANTS)
def test_a_plant_is_refused_and_its_restore_passes(repo: Path, name: str) -> None:
    original = snapshot(repo)
    ALL_PLANTS[name](repo)
    assert kinds(repo) & {DRIFT, UNREADABLE}, "the plant did not bite"

    restore(repo, original)

    assert (cb.check(repo), kit.run_checker(repo).returncode) == ((), 0)


def test_a_part_prefix_that_starts_no_line_is_i1s_finding_not_a_crash(repo: Path) -> None:
    path = repo / SOURCES[INTERMEDIATE]
    text = path.read_text(encoding="utf-8")
    assert "- **Lifecycle states**" in text, "the manifest's part no longer starts a line"
    path.write_text(text.replace("- **Lifecycle states**", "- **States of a life**"))

    found = kinds(repo)

    assert "I1-orphan" in found
    assert {DRIFT, UNREADABLE} & found == set()
    assert kit.run_checker(repo).returncode == 1
