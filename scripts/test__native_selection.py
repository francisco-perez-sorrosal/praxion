"""Tests for `_native_selection` -- thin argv builders for non-Python pockets.

Cargo and go are not on this machine's `PATH` by assumption, and nx/turbo/pants
are npm/Python tools Praxion does not run live either (per `SYSTEMS_PLAN.md`'s
Risk Assessment: "native adapters are not dogfoodable in Praxion"). So every
adapter is exercised against a **stub executable** placed at the front of
`PATH` -- a tiny shell script that prints canned JSON (cargo, go) or simply
exits 0 (every argv-only builder, which never actually invokes its tool). The
canary is `tool-unavailable`: an empty `PATH` must widen, never raise.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


native = _load("_native_selection")


def _stub(bin_dir: Path, name: str, stdout: str = "") -> None:
    """Put `name` on `PATH` ahead of everything else, echoing `stdout` and exiting 0."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{stdout}\nEOF\n", encoding="utf-8")
    script.chmod(0o755)


def _prepend_path(monkeypatch: pytest.MonkeyPatch, bin_dir: Path) -> None:
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


# --- no-adapter / tool-unavailable -------------------------------------------


def test_an_unrecognized_framework_has_no_adapter(tmp_path: Path) -> None:
    result = native.select("bazel", tmp_path, (), ("BUILD",))
    assert result == native.Widen(
        native.REASON_NO_ADAPTER, "no selection adapter for the bazel framework"
    )


def test_a_missing_tool_widens_instead_of_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    result = native.select("cargo", tmp_path, (), ("src/lib.rs",))
    assert isinstance(result, native.Widen)
    assert result.reason == native.REASON_TOOL_UNAVAILABLE


def test_a_local_node_modules_binary_counts_as_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """vitest/jest are ordinary devDependencies -- never on the global PATH."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    local_bin = tmp_path / "node_modules" / ".bin"
    local_bin.mkdir(parents=True)
    (local_bin / "vitest").write_text("#!/bin/sh\n", encoding="utf-8")
    (local_bin / "vitest").chmod(0o755)
    result = native.select("vitest", tmp_path, ("pnpm", "exec"), ("src/foo.ts",))
    assert result == native.Selected(("pnpm", "exec", "vitest", "related", "src/foo.ts", "--run"))


# --- self-computing adapters: pure argv builders -----------------------------


def test_vitest_related_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(tmp_path / "bin", "vitest")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("vitest", tmp_path, ("pnpm", "exec"), ("src/foo.ts",))
    assert result == native.Selected(("pnpm", "exec", "vitest", "related", "src/foo.ts", "--run"))


def test_jest_find_related_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(tmp_path / "bin", "jest")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("jest", tmp_path, ("npx",), ("src/foo.ts",))
    assert result == native.Selected(("npx", "jest", "--findRelatedTests", "src/foo.ts"))


def test_maven_module_selection_with_amd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(tmp_path / "bin", "mvn")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("maven", tmp_path, (), ("module-a/src/Foo.java", "pom.xml"))
    assert result == native.Selected(("mvn", "test", "-pl", ".,module-a", "-amd"))


def test_gradle_project_build_dependents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(tmp_path / "bin", "gradle")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("gradle", tmp_path, (), ("moduleA/src/Foo.kt",))
    assert result == native.Selected(("gradle", ":moduleA:buildDependents"))


def test_gradle_root_project_build_dependents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(tmp_path / "bin", "gradle")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("gradle", tmp_path, (), ("build.gradle.kts",))
    assert result == native.Selected(("gradle", "buildDependents"))


def test_nx_affected_with_files_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(tmp_path / "bin", "nx")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("nx", tmp_path, ("npx",), ("libs/a/index.ts", "libs/b/index.ts"))
    assert result == native.Selected(
        ("npx", "nx", "affected", "--target=test", "--files=libs/a/index.ts,libs/b/index.ts")
    )


def test_turbo_affected_flag_ignores_the_file_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Turbo has no per-file flag; the path list only confirms the pocket was touched."""
    _stub(tmp_path / "bin", "turbo")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("turbo", tmp_path, (), ("apps/web/index.ts",))
    assert result == native.Selected(("turbo", "run", "test", "--affected"))


def test_pants_receives_the_changed_paths_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(tmp_path / "bin", "pants")
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("pants", tmp_path, (), ("src/foo.py", "src/bar.py"))
    assert result == native.Selected(("pants", "test", "src/foo.py", "src/bar.py"))


# --- metadata-driven adapters: cargo and go read a canned graph --------------

_CARGO_METADATA = """{
  "packages": [
    {"id": "crate-a", "name": "crate-a", "manifest_path": "%(root)s/crate-a/Cargo.toml"},
    {"id": "crate-b", "name": "crate-b", "manifest_path": "%(root)s/crate-b/Cargo.toml"}
  ],
  "workspace_members": ["crate-a", "crate-b"],
  "resolve": {"nodes": [
    {"id": "crate-a", "dependencies": []},
    {"id": "crate-b", "dependencies": ["crate-a"]}
  ]}
}"""


def test_cargo_selects_the_changed_crate_and_its_dependents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`crate-b` depends on `crate-a`; a `crate-a` change must also select `crate-b`."""
    canned = _CARGO_METADATA % {"root": tmp_path}
    _stub(tmp_path / "bin", "cargo", stdout=canned)
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("cargo", tmp_path, (), ("crate-a/src/lib.rs",))
    assert result == native.Selected(("cargo", "test", "-p", "crate-a", "-p", "crate-b"))


def test_cargo_a_leaf_crate_change_selects_only_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canned = _CARGO_METADATA % {"root": tmp_path}
    _stub(tmp_path / "bin", "cargo", stdout=canned)
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("cargo", tmp_path, (), ("crate-b/src/lib.rs",))
    assert result == native.Selected(("cargo", "test", "-p", "crate-b"))


_GO_LIST = """{"ImportPath": "example.com/a", "Dir": "%(root)s/a", "Deps": []}
{"ImportPath": "example.com/b", "Dir": "%(root)s/b", "Deps": ["example.com/a"]}"""


def test_go_selects_the_changed_package_and_its_dependents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Deps` is already transitive, so package `b` (which imports `a`) is found in one pass."""
    canned = _GO_LIST % {"root": tmp_path}
    _stub(tmp_path / "bin", "go", stdout=canned)
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("go", tmp_path, (), ("a/main.go",))
    assert isinstance(result, native.Selected)
    assert result.argv[:2] == ("go", "test")
    assert set(result.argv[2:]) == {"example.com/a", "example.com/b"}


@pytest.mark.parametrize("framework", ["vitest", "jest"])
def test_a_changed_non_module_widens_a_module_graph_pocket(
    framework: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A canary: a fixture read through `fs` is outside the module graph, so a
    related-tests run would find nothing and exit 0 -- a silent all-clear."""
    _stub(tmp_path / "bin", framework)
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select(framework, tmp_path, (), ("src/foo.ts", "test/fixtures/data.json"))
    assert isinstance(result, native.Widen)
    assert result.reason == native.REASON_UNMAPPED
    assert "test/fixtures/data.json" in result.detail


def _go_select(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing: str, *paths: str):
    _stub(tmp_path / "bin", "go", stdout=listing % {"root": tmp_path})
    _prepend_path(monkeypatch, tmp_path / "bin")
    return native.select("go", tmp_path, (), paths)


_GO_LIST_WITH_TEST_IMPORT = (
    _GO_LIST
    + """
{"ImportPath": "example.com/c", "Dir": "%(root)s/c", "Deps": [],
 "TestImports": ["example.com/b"]}
{"ImportPath": "example.com/d", "Dir": "%(root)s/d", "Deps": [],
 "XTestImports": ["example.com/a"]}"""
)


def test_go_selects_a_package_whose_tests_alone_import_the_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A canary: `Deps` omits test-only imports, so `c` (its `_test.go` imports
    `b`, which depends on `a`) and `d` (an external test importing `a`) would be missed."""
    result = _go_select(tmp_path, monkeypatch, _GO_LIST_WITH_TEST_IMPORT, "a/main.go")
    assert isinstance(result, native.Selected)
    assert set(result.argv[2:]) == {f"example.com/{name}" for name in "abcd"}


def test_go_a_testdata_change_selects_its_enclosing_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _go_select(tmp_path, monkeypatch, _GO_LIST, "a/testdata/case.json")
    assert isinstance(result, native.Selected)
    assert set(result.argv[2:]) == {"example.com/a", "example.com/b"}


def test_go_a_change_outside_every_package_widens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A canary: an empty seed would hand `go test` no package, and it would test
    only the current directory's."""
    result = _go_select(tmp_path, monkeypatch, _GO_LIST, "a/main.go", "tools/gen.sh")
    assert isinstance(result, native.Widen)
    assert result.reason == native.REASON_UNMAPPED
    assert "tools/gen.sh" in result.detail


def test_cargo_a_change_outside_every_crate_widens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(tmp_path / "bin", "cargo", stdout=_CARGO_METADATA % {"root": tmp_path})
    _prepend_path(monkeypatch, tmp_path / "bin")
    result = native.select("cargo", tmp_path, (), ("crate-b/src/lib.rs", "scripts/release.sh"))
    assert isinstance(result, native.Widen)
    assert result.reason == native.REASON_UNMAPPED
    assert "scripts/release.sh" in result.detail


def test_go_tool_failure_widens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "go"
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    script.chmod(0o755)
    _prepend_path(monkeypatch, bin_dir)
    result = native.select("go", tmp_path, (), ("a/main.go",))
    assert result == native.Widen(native.REASON_TOOL_UNAVAILABLE, "`go list` failed")


def test_go_a_nested_package_owns_its_files_over_a_root_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = """{"ImportPath": "example.com", "Dir": "%(root)s", "Deps": []}
{"ImportPath": "example.com/a", "Dir": "%(root)s/a", "Deps": []}"""
    result = _go_select(tmp_path, monkeypatch, listing, "a/testdata/case.json")
    assert result == native.Selected(("go", "test", "example.com/a"))
