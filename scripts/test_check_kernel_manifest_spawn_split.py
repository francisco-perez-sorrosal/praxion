"""Canaries for I11: a split recipient receives exactly the split its sources give it now.

Each canary breaks one thing in a copy of the live inputs, shows the checker refuses it naming
the unit (or exits non-zero when the artifact cannot be read), restores the copy and shows it
passes again.
"""

from __future__ import annotations

import hashlib
import json
import shutil
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


def garbage(root: Path) -> None:
    (root / rd.SPAWN_SPLIT_PATH).write_bytes(b"\x00\xff not what was written here {[\n")


def missing(root: Path) -> None:
    (root / rd.SPAWN_SPLIT_PATH).unlink()


NAMED_PLANTS = {
    "stale-protocol": (stale_source(PROTOCOL), [PROTOCOL]),
    "stale-intermediate-documents": (stale_source(INTERMEDIATE), [INTERMEDIATE]),
    "reclassified": (reclassified, SPLIT_UNITS),
    "split-text-edited": (edit_split(text_edited), [INTERMEDIATE]),
    "split-text-and-digest-edited": (edit_split(text_and_digest_edited), [INTERMEDIATE]),
}
UNREADABLE_PLANTS = {"garbage": garbage, "missing": missing}
ALL_PLANTS = {**{name: plant for name, (plant, _) in NAMED_PLANTS.items()}, **UNREADABLE_PLANTS}


# -- The verdicts --------------------------------------------------------------------------------


def test_the_live_checkout_delivers_its_split_as_its_sources_give_it(repo: Path) -> None:
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


@pytest.mark.parametrize("name", ALL_PLANTS)
def test_a_checkout_restored_after_a_plant_passes(repo: Path, tmp_path: Path, name: str) -> None:
    before = tmp_path / "before"
    shutil.copytree(repo, before)
    ALL_PLANTS[name](repo)
    shutil.rmtree(repo)
    shutil.copytree(before, repo)

    assert (cb.check(repo), kit.run_checker(repo).returncode) == ((), 0)
