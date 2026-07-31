#!/usr/bin/env python3
"""Tests for the API-spec discovery in ``scripts/build_doc_manifest.py``.

Covers the spec-discovery walk: OpenAPI (YAML + JSON), AsyncAPI, and GraphQL
SDL surfaces are emitted with ``renderer: api_reference`` / ``diataxis:
reference``, titles are derived from ``info.title`` (with filename fallback for
SDL), all spec surfaces land in a single ``api-reference`` group ordered before
``other``, and ``--check`` stays green against a freshly generated manifest.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import build_doc_manifest as bdm
import pytest
import yaml

OPENAPI_YAML = """\
openapi: 3.1.0
info:
  title: Orders API
  version: 2.3.0
paths: {}
"""

ASYNCAPI_YAML = """\
asyncapi: 3.0.0
info:
  title: Events API
  version: 1.0.0
channels: {}
"""

GRAPHQL_SDL = """\
type Query {
  hello: String
}
"""


@pytest.fixture
def spec_project(tmp_path: Path) -> Path:
    """A project carrying an OpenAPI YAML at root, an OpenAPI JSON under
    ``api/``, an AsyncAPI YAML under ``docs/``, and a GraphQL SDL under
    ``openapi/`` — exercising every recognized location and filename."""
    (tmp_path / "openapi.yaml").write_text(OPENAPI_YAML)

    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "openapi.json").write_text(
        json.dumps({"openapi": "3.1.0", "info": {"title": "Billing API"}, "paths": {}})
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "asyncapi.yaml").write_text(ASYNCAPI_YAML)

    spec_dir = tmp_path / "openapi"
    spec_dir.mkdir()
    (spec_dir / "schema.graphql").write_text(GRAPHQL_SDL)

    return tmp_path


def _surfaces_by_id(manifest: dict) -> dict[str, dict]:
    return {s["id"]: s for s in manifest["surfaces"]}


def _spec_surfaces(manifest: dict) -> list[dict]:
    return [s for s in manifest["surfaces"] if s.get("renderer") == "api_reference"]


def test_discovers_openapi_yaml(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    surfaces = _surfaces_by_id(manifest)
    surface = surfaces["openapi"]
    assert surface["path"] == "openapi.yaml"
    assert surface["type"] == "yaml"
    assert surface["renderer"] == "api_reference"
    assert surface["diataxis"] == "reference"


def test_discovers_openapi_json(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    surfaces = _surfaces_by_id(manifest)
    surface = surfaces["api-openapi"]
    assert surface["path"] == "api/openapi.json"
    assert surface["type"] == "json"
    assert surface["renderer"] == "api_reference"
    assert surface["diataxis"] == "reference"


def test_discovers_graphql_sdl(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    surfaces = _surfaces_by_id(manifest)
    surface = surfaces["openapi-schema"]
    assert surface["path"] == "openapi/schema.graphql"
    assert surface["type"] == "graphql"
    assert surface["renderer"] == "api_reference"
    assert surface["diataxis"] == "reference"


def test_discovers_asyncapi_under_docs(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    surfaces = _surfaces_by_id(manifest)
    surface = surfaces["docs-asyncapi"]
    assert surface["path"] == "docs/asyncapi.yaml"
    assert surface["renderer"] == "api_reference"


def test_title_from_info_title_and_version(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    surfaces = _surfaces_by_id(manifest)
    assert surfaces["openapi"]["title"] == "Orders API 2.3.0"


def test_title_from_info_title_without_version(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    surfaces = _surfaces_by_id(manifest)
    # api/openapi.json has info.title but no version
    assert surfaces["api-openapi"]["title"] == "Billing API"


def test_graphql_title_falls_back_to_filename(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    surfaces = _surfaces_by_id(manifest)
    assert surfaces["openapi-schema"]["title"] == "schema.graphql"


def test_all_spec_surfaces_grouped_under_api_reference(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    groups = {g["id"]: g for g in manifest["groups"]}
    assert "api-reference" in groups
    api_group = groups["api-reference"]
    assert api_group["label"] == "API Reference"
    expected = {s["id"] for s in _spec_surfaces(manifest)}
    assert set(api_group["surface_ids"]) == expected


def test_api_reference_group_ordered_before_other(tmp_path: Path) -> None:
    # A non-spec, non-diataxis surface lands in `other`; the spec surface must
    # precede it in the group ordering.
    (tmp_path / "openapi.yaml").write_text(OPENAPI_YAML)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nStuff.\n")
    manifest = bdm.build_manifest(tmp_path)
    group_ids = [g["id"] for g in manifest["groups"]]
    assert "api-reference" in group_ids
    assert "other" in group_ids
    assert group_ids.index("api-reference") < group_ids.index("other")


def test_unparseable_spec_falls_back_to_filename(tmp_path: Path) -> None:
    (tmp_path / "openapi.yaml").write_text("{ this is : not : valid : yaml")
    manifest = bdm.build_manifest(tmp_path)
    surfaces = _surfaces_by_id(manifest)
    assert surfaces["openapi"]["title"] == "openapi.yaml"


def test_check_stays_green_after_generation(spec_project: Path) -> None:
    # Generate the manifest, then assert --check finds it in sync.
    assert bdm.main(["--root", str(spec_project)]) == 0
    assert bdm.main(["--root", str(spec_project), "--check"]) == 0


def test_no_spec_files_emits_no_api_reference_group(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Readme\n\nNo specs here.\n")
    manifest = bdm.build_manifest(tmp_path)
    group_ids = [g["id"] for g in manifest["groups"]]
    assert "api-reference" not in group_ids
    assert _spec_surfaces(manifest) == []


def test_generated_yaml_round_trips(spec_project: Path) -> None:
    manifest = bdm.build_manifest(spec_project)
    dumped = yaml.safe_dump(manifest, sort_keys=False)
    reloaded = yaml.safe_load(dumped)
    assert reloaded["groups"] == manifest["groups"]


# ---------------------------------------------------------------------------
# New behavioral tests: .ai-work/ exclusion + content-aware write
# ---------------------------------------------------------------------------


def test_excludes_ai_work_surfaces(tmp_path: Path) -> None:
    """build_manifest emits zero surfaces under .ai-work/ and no transient group."""
    (tmp_path / ".ai-work" / "slug1").mkdir(parents=True)
    (tmp_path / ".ai-work" / "slug1" / "WIP.md").write_text("# WIP\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("# Doc X\n")

    manifest = bdm.build_manifest(tmp_path)

    ai_work_surfaces = [s for s in manifest["surfaces"] if s["path"].startswith(".ai-work/")]
    assert ai_work_surfaces == [], f"unexpected .ai-work/ surfaces: {ai_work_surfaces}"

    transient_groups = [g for g in manifest["groups"] if g.get("transient")]
    assert transient_groups == [], f"unexpected transient groups: {transient_groups}"


def test_content_aware_write_skips_when_unchanged(tmp_path: Path) -> None:
    """Second write is skipped when durable surfaces are unchanged."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("# Doc X\n")

    # First write — creates the manifest
    assert bdm.main(["--root", str(tmp_path)]) == 0
    manifest_path = tmp_path / ".ai-state" / "doc_manifest.yaml"
    assert manifest_path.is_file()
    first_bytes = manifest_path.read_bytes()
    first_mtime = manifest_path.stat().st_mtime

    # Second write — content unchanged; write must be skipped
    assert bdm.main(["--root", str(tmp_path)]) == 0
    assert manifest_path.read_bytes() == first_bytes, "write was not skipped: file bytes changed"
    assert manifest_path.stat().st_mtime == first_mtime, "write was not skipped: mtime changed"

    # Mutate a durable surface — write must now fire
    (tmp_path / "docs" / "y.md").write_text("# Doc Y\n")
    assert bdm.main(["--root", str(tmp_path)]) == 0
    assert (
        manifest_path.read_bytes() != first_bytes
    ), "write did not fire after durable surface changed"


def test_durable_surfaces_preserved_with_and_without_ai_work(tmp_path: Path) -> None:
    """Durable surface set is identical whether or not .ai-work/ is present."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n")

    manifest_without = bdm.build_manifest(tmp_path)
    durable_without = {s["path"] for s in manifest_without["surfaces"]}

    # Add a .ai-work/ tree — must not alter the durable surface set
    (tmp_path / ".ai-work" / "my-task").mkdir(parents=True)
    (tmp_path / ".ai-work" / "my-task" / "WIP.md").write_text("# WIP\n")
    (tmp_path / ".ai-work" / "my-task" / "LEARNINGS.md").write_text("# Learnings\n")

    manifest_with = bdm.build_manifest(tmp_path)
    durable_with = {s["path"] for s in manifest_with["surfaces"]}

    assert durable_with == durable_without, (
        f"durable set changed when .ai-work/ was added: "
        f"added={durable_with - durable_without}, removed={durable_without - durable_with}"
    )


def test_docs_indexed_when_root_lives_under_an_excluded_dir(tmp_path: Path) -> None:
    """A root nested under an excluded dir (e.g. a worktree under .claude/) must
    still index its docs.

    Regression: the markdown walk checked the absolute path parts, so a
    `.claude` component in the root *prefix* spuriously excluded every `docs/`
    surface — `build_doc_manifest` run from a worktree silently dropped all docs.
    The check must be relative to root (mirroring the api-spec walk).
    """
    root = tmp_path / ".claude" / "worktrees" / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    manifest = bdm.build_manifest(root)
    doc_paths = [s["path"] for s in manifest["surfaces"] if s["path"].startswith("docs/")]
    assert (
        "docs/guide.md" in doc_paths
    ), f"docs/ surface excluded when root is under an excluded dir; got {doc_paths}"


# ---------------------------------------------------------------------------
# last_modified determinism across checkouts
#
# A fresh clone or CI checkout sets mtime to checkout time for every file, so
# an mtime-derived `last_modified` makes the same tree produce a different
# manifest depending on where it is generated. The regenerate-in-place step
# then commits over whatever the other environment wrote, forever. These tests
# fail against an mtime-derived implementation.
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def committed_project(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\nBody.\n")
    (docs / "reference.md").write_text("# Reference\n\nBody.\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "seed")
    return tmp_path


def test_last_modified_survives_an_mtime_reset(committed_project: Path) -> None:
    """Resetting every mtime -- what a fresh checkout does -- must not change
    the manifest. Under an mtime-derived implementation every row changes."""
    before = bdm.build_manifest(committed_project)

    # Not `touch()` -- that sets mtime to now, which in a repo committed today
    # is indistinguishable from the commit date and makes this test vacuous.
    # Use a date that cannot coincide with any commit date.
    for path in committed_project.rglob("*.md"):
        os.utime(path, (86_400, 86_400))

    after = bdm.build_manifest(committed_project)

    before_dates = {s["id"]: s["last_modified"] for s in before["surfaces"]}
    after_dates = {s["id"]: s["last_modified"] for s in after["surfaces"]}
    assert before_dates == after_dates, (
        "last_modified changed when only mtime changed -- the manifest is "
        "checkout-dependent, so CI and local runs will commit over each other"
    )


def test_last_modified_uses_the_commit_date_not_the_mtime(
    committed_project: Path,
) -> None:
    """The recorded date is git's, not the filesystem's."""
    guide = committed_project / "docs" / "guide.md"
    os.utime(guide, (86_400, 86_400))  # 1970 on disk; git still says today

    expected = subprocess.run(
        ["git", "-C", str(committed_project), "log", "-1", "--format=%cs", "--", "docs/guide.md"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    surfaces = {s["id"]: s for s in bdm.build_manifest(committed_project)["surfaces"]}
    recorded = surfaces["docs-guide"]["last_modified"]

    # Asserted against git's own answer rather than a magic string: a negative
    # check like "not 1970" silently passes when the local timezone renders the
    # epoch as 1969.
    assert recorded == expected, (
        f"last_modified is {recorded!r}, expected the commit date {expected!r} "
        "-- it fell back to mtime for a tracked file"
    )


def test_untracked_surface_falls_back_to_mtime(committed_project: Path) -> None:
    """An authored-but-uncommitted surface has no commit date; mtime is the
    only signal, so the fallback must still produce a usable value."""
    (committed_project / "docs" / "draft.md").write_text("# Draft\n\nBody.\n")

    surfaces = {s["id"]: s for s in bdm.build_manifest(committed_project)["surfaces"]}
    assert "docs-draft" in surfaces, "an untracked surface must still be listed"
    assert surfaces["docs-draft"]["last_modified"], "fallback produced no date"
