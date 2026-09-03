"""Behavioral tests for `_sidecar_manifest.py` -- the sidecar manifest smart
constructor (`praxion-sidecar.yaml`).

`load_manifest(path)` is the *only* full-YAML reader in the codebase --
`_state_repo.py`'s stdlib reader reads only the frozen triple. Fixtures write
the manifest at `<sidecar_root>/.git/praxion-sidecar.yaml` (the sidecar's git
**common** dir, per `SYSTEMS_PLAN.md` DS-2's location amendment) -- never
inside a mount's tracked tree. Most tests use a *plain* sidecar directory (a
`.git/` subdirectory, no real git repository) since the loader only ever
touches the manifest file and, for the on-disk `kind` cross-check, plain
filesystem entries beside it -- no git plumbing is exercised there. Two
tests need a real mounted checkout (`git worktree add`) and build one with a
self-contained local fixture -- this file does not import `_state_repo`'s
private fixture helpers, matching this file set's disjointness contract; the
one test that needs `_state_repo` itself imports it via
`pytest.importorskip("_state_repo")`, so it skips cleanly until that module
exists.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`, so
pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_state_repo.py`.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import _sidecar_manifest
import pytest

# --- Fixture builders --------------------------------------------------------


def _plain_sidecar(tmp_path: Path) -> Path:
    """A sidecar directory with a `.git/` subdirectory, no real git repo.

    Sufficient for every test below except the two that need a real `git
    worktree` mount: the manifest loader/writer only ever touch the
    manifest file path and, for the on-disk `kind` cross-check, plain
    filesystem entries beside it.
    """
    sidecar_root = tmp_path / "sidecar"
    (sidecar_root / ".git").mkdir(parents=True)
    return sidecar_root


def _write_manifest_yaml(sidecar_root: Path, yaml_text: str) -> Path:
    manifest_path = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest_path.write_text(yaml_text)
    return manifest_path


def _manifest_yaml(
    *,
    schema: str = "1",
    origin: str = '"https://github.com/acme/billing"',
    project_id: str = '"local--abc123def456"',
    roots: str = '["/tmp/example-root"]',
    paths_section: str = "paths: {}\n",
    excludes: str = "[]",
    autocommit: str = "on-finalize-and-stop",
    remote: str = "null",
) -> str:
    """A minimal, valid manifest with every field overridable.

    `paths_section` carries its own trailing `paths:` header -- pass either
    `"paths: {}\\n"` (the default, empty map) or a multi-line block starting
    `"paths:\\n"` with quoted `"<relpath>": { ... }` entries.
    """
    return (
        f"schema: {schema}\n"
        "project:\n"
        f"  origin: {origin}\n"
        f"  id: {project_id}\n"
        f"  roots: {roots}\n"
        f"{paths_section}"
        f"excludes: {excludes}\n"
        f"autocommit: {autocommit}\n"
        f"remote: {remote}\n"
    )


_CANONICAL_MANIFEST_TEMPLATE = """\
schema: 1
project:
  origin: "https://github.com/acme/billing"
  id: "github.com--acme--billing"
  roots: ["__ROOTS__"]
paths:
  ".ai-state":                   { intent: shadow,    kind: dir }
  "CLAUDE.local.md":             { intent: shadow,    kind: file }
  ".claude/settings.local.json": { intent: shadow,    kind: file }
  "CLAUDE.md":                   { intent: untouched, reason: preexisting-team-file }
  "docs/architecture.md":        { intent: share }
excludes: [".ai-work/", ".claude/worktrees/", "tmp/"]
autocommit: on-finalize-and-stop
remote: null
"""


def _canonical_manifest_yaml(roots_dir: Path) -> str:
    return _CANONICAL_MANIFEST_TEMPLATE.replace("__ROOTS__", str(roots_dir))


def _seed_on_disk_entries(
    sidecar_root: Path, *, dirs: list[str] = (), files: list[str] = ()
) -> None:
    """Seed plain filesystem entries in the sidecar's working tree, matching
    the `kind` the fixture's manifest declares -- for tests that would
    otherwise trip the on-disk `kind` cross-check."""
    for relpath in dirs:
        (sidecar_root / relpath).mkdir(parents=True, exist_ok=True)
    for relpath in files:
        target = sidecar_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n")


def _run_git(cwd: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")


@dataclasses.dataclass(frozen=True)
class _MountedFixture:
    project_root: Path
    sidecar_root: Path
    sidecar_common_dir: Path
    mount_dir: Path


def _mounted_sidecar_fixture(tmp_path: Path, *, manifest_yaml: str) -> _MountedFixture:
    """A real `git worktree`-mounted sidecar. Self-contained -- does not
    import `_state_repo`'s own fixture helpers (see module docstring)."""
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    sidecar_root.mkdir()
    _run_git(sidecar_root, "init", "-q", "-b", "main")
    _run_git(sidecar_root, "config", "user.email", "sidecar@example.com")
    _run_git(sidecar_root, "config", "user.name", "Sidecar Test")
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("# design\n")
    _run_git(sidecar_root, "add", "-A")
    _run_git(sidecar_root, "commit", "-q", "-m", "seed sidecar state")
    _run_git(sidecar_root, "checkout", "-q", "--detach")

    project_root.mkdir()
    _run_git(project_root, "init", "-q", "-b", "main")
    _run_git(project_root, "config", "user.email", "project@example.com")
    _run_git(project_root, "config", "user.name", "Project Test")
    mount_dir = project_root / ".praxion"
    _run_git(sidecar_root, "worktree", "add", "-q", str(mount_dir), "main")

    sidecar_common_dir = sidecar_root / ".git"
    (sidecar_common_dir / "praxion-sidecar.yaml").write_text(manifest_yaml)

    link_path = project_root / ".ai-state"
    link_path.symlink_to(Path(".praxion") / ".ai-state", target_is_directory=True)

    return _MountedFixture(
        project_root=project_root,
        sidecar_root=sidecar_root,
        sidecar_common_dir=sidecar_common_dir,
        mount_dir=mount_dir,
    )


def _load(sidecar_root: Path) -> _sidecar_manifest.Manifest:
    return _sidecar_manifest.load_manifest(_sidecar_manifest.manifest_path(sidecar_root / ".git"))


# --- Domain constants ---------------------------------------------------------


def test_never_shadow_constant_matches_the_closed_set() -> None:
    assert _sidecar_manifest.NEVER_SHADOW == frozenset({".claude", ".git", ".", ".praxion"})


def test_shadowable_paths_allowlist_matches_the_interface_designers_allowlist() -> None:
    assert _sidecar_manifest.SHADOWABLE_PATHS == frozenset(
        {
            ".ai-state",
            "CLAUDE.md",
            "CLAUDE.local.md",
            ".claude/settings.local.json",
            "docs/architecture.md",
            "architecture/",
            "fitness/",
        }
    )


# --- manifest_path() -----------------------------------------------------------


def test_manifest_path_targets_the_sidecar_git_common_dir(tmp_path: Path) -> None:
    sidecar_common_dir = tmp_path / "sidecar" / ".git"

    assert (
        _sidecar_manifest.manifest_path(sidecar_common_dir)
        == sidecar_common_dir / "praxion-sidecar.yaml"
    )


def test_manifest_path_never_resolves_inside_a_mounted_checkout(tmp_path: Path) -> None:
    manifest_yaml = _canonical_manifest_yaml(tmp_path / "project")
    fixture = _mounted_sidecar_fixture(tmp_path, manifest_yaml=manifest_yaml)

    resolved = _sidecar_manifest.manifest_path(fixture.sidecar_common_dir)

    assert fixture.mount_dir not in resolved.parents


# --- Happy path: every field typed --------------------------------------------


def test_canonical_manifest_loads_with_every_field_typed(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _seed_on_disk_entries(
        sidecar_root,
        dirs=[".ai-state"],
        files=["CLAUDE.local.md", ".claude/settings.local.json"],
    )
    roots_dir = tmp_path / "project"
    _write_manifest_yaml(sidecar_root, _canonical_manifest_yaml(roots_dir))

    manifest = _load(sidecar_root)

    assert manifest.schema == 1
    assert manifest.project.origin == "https://github.com/acme/billing"
    assert manifest.project.id == "github.com--acme--billing"
    assert manifest.project.roots == [Path(str(roots_dir))]
    assert manifest.excludes == [".ai-work/", ".claude/worktrees/", "tmp/"]
    assert manifest.autocommit == _sidecar_manifest.Autocommit.ON_FINALIZE_AND_STOP
    assert manifest.remote is None

    ai_state = manifest.paths[".ai-state"]
    assert isinstance(ai_state, _sidecar_manifest.ShadowEntry)
    assert ai_state.kind == _sidecar_manifest.ShadowKind.DIR

    claude_local = manifest.paths["CLAUDE.local.md"]
    assert isinstance(claude_local, _sidecar_manifest.ShadowEntry)
    assert claude_local.kind == _sidecar_manifest.ShadowKind.FILE

    claude_md = manifest.paths["CLAUDE.md"]
    assert isinstance(claude_md, _sidecar_manifest.UntouchedEntry)
    assert claude_md.reason == _sidecar_manifest.UntouchedReason.PREEXISTING_TEAM_FILE

    architecture_doc = manifest.paths["docs/architecture.md"]
    assert isinstance(architecture_doc, _sidecar_manifest.ShareEntry)


def test_manifest_is_frozen_against_mutation(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _seed_on_disk_entries(
        sidecar_root, dirs=[".ai-state"], files=["CLAUDE.local.md", ".claude/settings.local.json"]
    )
    _write_manifest_yaml(sidecar_root, _canonical_manifest_yaml(tmp_path / "project"))

    manifest = _load(sidecar_root)

    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.schema = 2  # type: ignore[misc]


# --- Illegal field combinations are unrepresentable at load -------------------


def test_share_intent_with_kind_field_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = 'paths:\n  "docs/architecture.md": { intent: share, kind: file }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "kind-not-allowed"


def test_untouched_intent_with_kind_field_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = 'paths:\n  "CLAUDE.md": { intent: untouched, kind: dir }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "kind-not-allowed"


def test_shadow_intent_without_kind_field_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = 'paths:\n  ".ai-state": { intent: shadow }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "kind-required"


# --- Closed enums refuse rather than default -----------------------------------


def test_unknown_autocommit_value_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(sidecar_root, _manifest_yaml(autocommit="sometimes"))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "unknown-enum-value"


def test_unknown_remote_push_value_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    remote = '{ url: "https://github.com/acme/billing", push: always }'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(remote=remote))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "unknown-enum-value"


def test_unknown_intent_value_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = 'paths:\n  "docs/policy.md": { intent: mirror }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "unknown-enum-value"


def test_unknown_shadow_kind_value_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = 'paths:\n  ".ai-state": { intent: shadow, kind: socket }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "unknown-enum-value"


def test_unknown_untouched_reason_value_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = 'paths:\n  "CLAUDE.md": { intent: untouched, reason: because }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "unknown-enum-value"


# --- `remote` is a nullable object, never a record with a nullable url --------


def test_remote_with_null_url_and_a_push_policy_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(sidecar_root, _manifest_yaml(remote="{ url: null, push: on-autocommit }"))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "remote-url-required"


def test_remote_null_is_accepted(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(sidecar_root, _manifest_yaml(remote="null"))

    manifest = _load(sidecar_root)

    assert manifest.remote is None


def test_remote_with_url_and_never_push_defaults_foreign_host_ack_false(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    remote = '{ url: "https://github.com/acme/billing", push: never }'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(remote=remote))

    manifest = _load(sidecar_root)

    assert manifest.remote == _sidecar_manifest.RemoteConfig(
        url="https://github.com/acme/billing",
        push=_sidecar_manifest.PushPolicy.NEVER,
        foreign_host_ack=False,
    )


# --- Evolution contract: schema-first, fail-closed -----------------------------


def test_missing_schema_key_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(
        sidecar_root,
        'project:\n  origin: null\n  id: "local--nopeschema"\n  roots: []\n'
        "paths: {}\nexcludes: []\nautocommit: manual\nremote: null\n",
    )

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "schema-missing"


def test_string_schema_value_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(sidecar_root, _manifest_yaml(schema='"1"'))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "schema-not-integer"


def test_schema_two_is_refused_with_upgrade_message(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(sidecar_root, _manifest_yaml(schema="2"))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "schema-unsupported"
    assert "upgrade" in str(exc_info.value).lower()


# --- `_NEVER_SHADOW`: illegal shadow paths are unrepresentable -----------------


@pytest.mark.parametrize(
    "illegal_path",
    [".claude", ".git", ".", ".praxion", ".git/hooks", ".praxion/.ai-state"],
)
def test_shadow_intent_on_a_never_shadow_path_is_refused(tmp_path: Path, illegal_path: str) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = f'paths:\n  "{illegal_path}": {{ intent: shadow, kind: dir }}\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "illegal-shadow-path"


# --- Excludes disjointness (CH-03) ---------------------------------------------


def test_excludes_overlapping_a_shadow_path_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _seed_on_disk_entries(sidecar_root, dirs=[".ai-state"])
    paths_section = 'paths:\n  ".ai-state": { intent: shadow, kind: dir }\n'
    _write_manifest_yaml(
        sidecar_root, _manifest_yaml(paths_section=paths_section, excludes='[".ai-state"]')
    )

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "excludes-overlap-shadow"


def test_excludes_overlapping_a_share_path_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    paths_section = 'paths:\n  "docs/architecture.md": { intent: share }\n'
    _write_manifest_yaml(
        sidecar_root,
        _manifest_yaml(paths_section=paths_section, excludes='["docs/architecture.md"]'),
    )

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "excludes-overlap-share"


def test_excludes_entry_disjoint_from_shadow_and_share_paths_is_accepted(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _seed_on_disk_entries(sidecar_root, dirs=[".ai-state"])
    paths_section = 'paths:\n  ".ai-state": { intent: shadow, kind: dir }\n  "docs/architecture.md": { intent: share }\n'
    _write_manifest_yaml(
        sidecar_root,
        _manifest_yaml(paths_section=paths_section, excludes='[".ai-work/", "tmp/"]'),
    )

    manifest = _load(sidecar_root)

    assert manifest.excludes == [".ai-work/", "tmp/"]


# --- `kind` is validated against the sidecar's on-disk entry -------------------


def test_declared_kind_conflicting_with_on_disk_entry_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    (sidecar_root / ".ai-state").write_text("a file, not a directory\n")
    paths_section = 'paths:\n  ".ai-state": { intent: shadow, kind: dir }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "kind-mismatch-on-disk"


def test_declared_kind_with_no_on_disk_entry_is_accepted(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    # `.ai-state` does not exist on disk yet -- a fresh sidecar before `link`
    # has ever materialized it. `kind` must still parse: `link` needs it
    # *before* the target exists, to know whether to create a dir or file
    # symlink.
    paths_section = 'paths:\n  ".ai-state": { intent: shadow, kind: dir }\n'
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))

    manifest = _load(sidecar_root)

    assert isinstance(manifest.paths[".ai-state"], _sidecar_manifest.ShadowEntry)


# --- `project.id` is recorded, never re-derived --------------------------------


def test_project_id_is_recorded_verbatim_never_rederived_from_origin(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(
        sidecar_root,
        _manifest_yaml(
            origin='"https://github.com/acme/billing"',
            project_id='"totally-unrelated-slug"',
        ),
    )

    manifest = _load(sidecar_root)

    assert manifest.project.id == "totally-unrelated-slug"


# --- `roots:` -------------------------------------------------------------------


def test_roots_parses_as_a_list_of_paths(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    root_dir = tmp_path / "project"
    _write_manifest_yaml(sidecar_root, _manifest_yaml(roots=f'["{root_dir}"]'))

    manifest = _load(sidecar_root)

    assert manifest.project.roots == [Path(str(root_dir))]


# --- write_manifest() / load_manifest() round trip -----------------------------


def test_write_then_load_round_trips_to_an_equal_manifest(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _seed_on_disk_entries(
        sidecar_root, dirs=[".ai-state"], files=["CLAUDE.local.md", ".claude/settings.local.json"]
    )
    _write_manifest_yaml(sidecar_root, _canonical_manifest_yaml(tmp_path / "project"))
    original = _load(sidecar_root)

    written_path = sidecar_root / ".git" / "praxion-sidecar-copy.yaml"
    _sidecar_manifest.write_manifest(written_path, original)
    round_tripped = _sidecar_manifest.load_manifest(written_path)

    assert round_tripped == original


def test_written_manifest_has_schema_as_first_key_and_project_fields_top_level(
    tmp_path: Path,
) -> None:
    yaml = pytest.importorskip("yaml")
    sidecar_root = _plain_sidecar(tmp_path)
    _seed_on_disk_entries(
        sidecar_root, dirs=[".ai-state"], files=["CLAUDE.local.md", ".claude/settings.local.json"]
    )
    _write_manifest_yaml(sidecar_root, _canonical_manifest_yaml(tmp_path / "project"))
    manifest = _load(sidecar_root)

    written_path = sidecar_root / ".git" / "praxion-sidecar-copy.yaml"
    _sidecar_manifest.write_manifest(written_path, manifest)

    raw_text = written_path.read_text()
    first_content_line = next(
        line for line in raw_text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    )
    assert first_content_line.startswith("schema:")

    parsed = yaml.safe_load(raw_text)
    assert set(parsed["project"].keys()) >= {"origin", "id", "roots"}


# --- `block_target()` (DS-8) -----------------------------------------------------


def _load_with_claude_md_intent(
    sidecar_root: Path, claude_entry: str, *, extra_paths: str = ""
) -> _sidecar_manifest.Manifest:
    paths_section = (
        "paths:\n"
        f'  "CLAUDE.md": {claude_entry}\n'
        '  "CLAUDE.local.md": { intent: shadow, kind: file }\n'
        f"{extra_paths}"
    )
    _write_manifest_yaml(sidecar_root, _manifest_yaml(paths_section=paths_section))
    return _load(sidecar_root)


def test_block_target_for_untouched_claude_md_redirects_to_shadowed_claude_local_md(
    tmp_path: Path,
) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    manifest = _load_with_claude_md_intent(
        sidecar_root, "{ intent: untouched, reason: preexisting-team-file }"
    )
    project_root = tmp_path / "project"

    target = _sidecar_manifest.block_target(manifest, project_root)

    assert target == project_root / "CLAUDE.local.md"


def test_block_target_for_shadowed_claude_md_targets_claude_md(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    manifest = _load_with_claude_md_intent(sidecar_root, "{ intent: shadow, kind: file }")
    project_root = tmp_path / "project"

    target = _sidecar_manifest.block_target(manifest, project_root)

    assert target == project_root / "CLAUDE.md"


def test_block_target_for_shared_claude_md_targets_claude_md(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    manifest = _load_with_claude_md_intent(sidecar_root, "{ intent: share }")
    project_root = tmp_path / "project"

    target = _sidecar_manifest.block_target(manifest, project_root)

    assert target == project_root / "CLAUDE.md"


def test_block_target_raises_for_a_non_claude_md_path_whose_intent_is_untouched(
    tmp_path: Path,
) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    extra_paths = '  "docs/policy.md": { intent: untouched, reason: operator-choice }\n'
    manifest = _load_with_claude_md_intent(
        sidecar_root, "{ intent: shadow, kind: file }", extra_paths=extra_paths
    )
    project_root = tmp_path / "project"

    with pytest.raises(_sidecar_manifest.ManifestError, match="(?i)untouched"):
        _sidecar_manifest.block_target(manifest, project_root, path="docs/policy.md")


# --- Two readers, two parsers, one owner (DS-2) ---------------------------------


def test_stdlib_and_full_readers_agree_on_the_frozen_triple(tmp_path: Path) -> None:
    """`_state_repo.py`'s stdlib reader and this module's full YAML reader
    must never disagree on `{schema, project.id, project.origin}` -- the
    frozen compatibility triple. Skips cleanly until `_state_repo` exists."""
    state_repo = pytest.importorskip("_state_repo")
    manifest_yaml = _manifest_yaml(
        origin='"https://github.com/acme/billing"',
        project_id='"github.com--acme--billing"',
        roots=f'["{tmp_path / "project"}"]',
    )
    fixture = _mounted_sidecar_fixture(tmp_path, manifest_yaml=manifest_yaml)
    _run_git(fixture.project_root, "remote", "add", "origin", "https://github.com/acme/billing")

    full = _sidecar_manifest.load_manifest(
        _sidecar_manifest.manifest_path(fixture.sidecar_common_dir)
    )
    placement = state_repo.resolve_placement(fixture.project_root)

    assert isinstance(placement, state_repo.SidecarOwned)
    assert placement.identity.schema == full.schema
    assert placement.identity.id == full.project.id
    assert placement.identity.origin == full.project.origin


def test_write_manifest_then_stdlib_reader_resolves_a_remote_less_project(
    tmp_path: Path,
) -> None:
    """The writer's actual on-disk bytes -- not a hand-rolled fixture string
    like the test above -- must stay parseable by `_state_repo.py`'s stdlib
    reader for the remote-less identity anchor (`roots:`), DS-7's only anchor
    for that population. This routes through `write_manifest()` itself, which
    `test_stdlib_and_full_readers_agree_on_the_frozen_triple` does not."""
    state_repo = pytest.importorskip("_state_repo")
    fixture = _mounted_sidecar_fixture(tmp_path, manifest_yaml="schema: 1\n")
    manifest = _sidecar_manifest.Manifest(
        schema=1,
        project=_sidecar_manifest.ProjectIdentity(
            origin=None, id="local--deadbeefcafe01", roots=[fixture.project_root]
        ),
        paths={},
        excludes=[],
        autocommit=_sidecar_manifest.Autocommit.ON_FINALIZE_AND_STOP,
        remote=None,
    )
    _sidecar_manifest.write_manifest(
        _sidecar_manifest.manifest_path(fixture.sidecar_common_dir), manifest
    )

    placement = state_repo.resolve_placement(fixture.project_root)

    assert isinstance(placement, state_repo.SidecarOwned)
    assert placement.identity.origin is None


# --- `project.id` symmetry with the stdlib reader --------------------------------


def test_missing_project_id_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(
        sidecar_root,
        "schema: 1\nproject:\n  origin: null\n  roots: []\n"
        "paths: {}\nexcludes: []\nautocommit: manual\nremote: null\n",
    )

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "project-id-missing"


def test_empty_project_id_is_refused(tmp_path: Path) -> None:
    sidecar_root = _plain_sidecar(tmp_path)
    _write_manifest_yaml(sidecar_root, _manifest_yaml(project_id='""'))

    with pytest.raises(_sidecar_manifest.ManifestError) as exc_info:
        _load(sidecar_root)

    assert exc_info.value.reason == "project-id-missing"
