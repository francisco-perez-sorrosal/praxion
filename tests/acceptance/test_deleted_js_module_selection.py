"""A deleted JavaScript/TypeScript module never gets a silent all-clear.

vitest and jest pockets select by following imports out of the named files.
Hand them a module that no longer exists and they find no related tests and
exit 0, while the tests that imported it are exactly the ones that would now
fail. So a deleted module must run its pocket's full suite, and only that
pocket's; an edit to modules that still exist keeps the narrow related-tests
run.

The scratch repository has three pockets: a Python pocket at the root, a
vitest pocket under `web/` and a jest pocket under `api/`, each with the same
set of modules. Both tools are stubbed on `PATH` (see the driver).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.scope_resolver import (
    ScratchRepo,
    all_argv_args,
    args_after,
    new_scratch_repo,
    pocket,
    resolve,
    unmapped_paths,
    widen_entries,
)

JS_POCKETS = {
    "vitest": {
        "root": "web",
        "package_json": (
            '{"name": "web", "private": true, "scripts": {"test": "vitest run"},'
            ' "devDependencies": {"vitest": "^2.0.0"}}\n'
        ),
        "config": ("vitest.config.ts", "export default {}\n"),
        "related": ("vitest", "related"),
    },
    "jest": {
        "root": "api",
        "package_json": (
            '{"name": "api", "private": true, "scripts": {"test": "jest"},'
            ' "devDependencies": {"jest": "^29.0.0"}}\n'
        ),
        "config": ("jest.config.js", "module.exports = {}\n"),
        "related": ("jest", "--findRelatedTests"),
    },
}

MODULE_EXTENSIONS = [".ts", ".tsx", ".js", ".mjs", ".jsx", ".cjs", ".mts", ".cts"]

SURVIVING_MODULES = ["src/keep.ts", "src/widget.tsx", "src/util.js", "src/esm.mjs"]


@pytest.fixture
def repo(tmp_path: Path) -> ScratchRepo:
    scratch = new_scratch_repo(tmp_path)
    scratch.write("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    scratch.write("tests/test_smoke.py", "def test_smoke():\n    assert True\n")
    for spec in JS_POCKETS.values():
        root = spec["root"]
        config_name, config_text = spec["config"]
        scratch.write(f"{root}/package.json", spec["package_json"])
        scratch.write(f"{root}/{config_name}", config_text)
        for module in SURVIVING_MODULES:
            scratch.write(f"{root}/{module}", "export const value = 1\n")
        for extension in MODULE_EXTENSIONS:
            scratch.write(f"{root}/src/retired{extension}", "export const gone = 1\n")
        scratch.write(
            f"{root}/src/keep.test.ts",
            'import { value } from "./keep"\ntest("value", () => expect(value).toBe(1))\n',
        )
    scratch.commit_all("seed three pockets")
    scratch.provide_tools(["vitest", "jest"])
    return scratch


def _assert_pocket_ran_in_full(payload: dict, full_payload: dict, adapter: str, deleted: str):
    """The deleted module's pocket runs its full suite and says why."""
    root = JS_POCKETS[adapter]["root"]
    served = pocket(payload, root)
    assert served["adapter"] == adapter, f"fixture pocket {root} is not a {adapter} pocket"
    assert served["selection"] == "full", (
        f"a deleted module left the {adapter} pocket at selection "
        f"{served['selection']!r}: {served['invocations']}"
    )
    assert served["invocations"] == pocket(full_payload, root)["invocations"]
    assert payload["decision"] == "widened"
    assert deleted in unmapped_paths(payload), (
        f"{deleted} is not named by any unmapped-path widen: {payload['widen']}"
    )


# -- The deleted module widens its own pocket --------------------------------


@pytest.mark.parametrize("extension", MODULE_EXTENSIONS)
@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_an_explicitly_named_module_that_no_longer_exists_runs_its_pocket_in_full(
    repo: ScratchRepo, adapter: str, extension: str
) -> None:
    deleted = f"{JS_POCKETS[adapter]['root']}/src/retired{extension}"
    repo.remove(deleted)

    payload = resolve(repo, "--changed", deleted)

    _assert_pocket_ran_in_full(payload, resolve(repo, "--full"), adapter, deleted)


@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_a_module_deleted_in_the_working_tree_diff_runs_its_pocket_in_full(
    repo: ScratchRepo, adapter: str
) -> None:
    deleted = f"{JS_POCKETS[adapter]['root']}/src/retired.ts"
    repo.git("rm", "-q", deleted)

    payload = resolve(repo)

    _assert_pocket_ran_in_full(payload, resolve(repo, "--full"), adapter, deleted)


@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_a_module_deleted_in_a_committed_diff_runs_its_pocket_in_full(
    repo: ScratchRepo, adapter: str
) -> None:
    base = repo.head()
    deleted = f"{JS_POCKETS[adapter]['root']}/src/retired.ts"
    repo.git("rm", "-q", deleted)
    repo.commit_all("delete a module")

    payload = resolve(repo, "--changed-from", base)

    _assert_pocket_ran_in_full(payload, resolve(repo, "--full"), adapter, deleted)


@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_the_old_path_of_a_renamed_module_runs_its_pocket_in_full(
    repo: ScratchRepo, adapter: str
) -> None:
    root = JS_POCKETS[adapter]["root"]
    base = repo.head()
    old_path = f"{root}/src/retired.ts"
    repo.git("mv", old_path, f"{root}/src/renamed.ts")
    repo.commit_all("rename a module")

    payload = resolve(repo, "--changed-from", base)

    _assert_pocket_ran_in_full(payload, resolve(repo, "--full"), adapter, old_path)


@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_a_deleted_module_widens_its_pocket_even_beside_surviving_changed_modules(
    repo: ScratchRepo, adapter: str
) -> None:
    root = JS_POCKETS[adapter]["root"]
    deleted = f"{root}/src/retired.ts"
    repo.remove(deleted)
    repo.write(f"{root}/src/keep.ts", "export const value = 2\n")

    payload = resolve(repo, "--changed", f"{root}/src/keep.ts", deleted)

    _assert_pocket_ran_in_full(payload, resolve(repo, "--full"), adapter, deleted)


@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_a_deleted_module_is_never_handed_to_the_related_tests_run(
    repo: ScratchRepo, adapter: str
) -> None:
    root = JS_POCKETS[adapter]["root"]
    deleted = f"{root}/src/retired.ts"
    repo.remove(deleted)

    payload = resolve(repo, "--changed", f"{root}/src/keep.ts", deleted)

    handed_over = [arg for arg in all_argv_args(payload) if "retired" in arg]
    assert handed_over == [], f"the deleted module reached an invocation: {handed_over}"


@pytest.mark.parametrize(("adapter", "other"), [("vitest", "jest"), ("jest", "vitest")])
def test_a_deleted_module_widens_no_other_pocket(
    repo: ScratchRepo, adapter: str, other: str
) -> None:
    deleted = f"{JS_POCKETS[adapter]['root']}/src/retired.ts"
    repo.remove(deleted)

    payload = resolve(repo, "--changed", deleted)

    assert pocket(payload, JS_POCKETS[adapter]["root"])["selection"] == "full"
    other_roots = [JS_POCKETS[other]["root"], "."]
    widened_elsewhere = [
        root for root in other_roots if pocket(payload, root)["selection"] == "full"
    ]
    assert widened_elsewhere == [], (
        f"deleting {deleted} widened pockets it does not belong to: {widened_elsewhere}"
    )


# -- Modules that still exist keep the narrow run ----------------------------


@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_changed_modules_that_still_exist_keep_the_narrow_related_tests_run(
    repo: ScratchRepo, adapter: str
) -> None:
    spec = JS_POCKETS[adapter]
    root = spec["root"]
    for module in SURVIVING_MODULES:
        repo.write(f"{root}/{module}", "export const value = 2\n")

    payload = resolve(repo, "--changed", *(f"{root}/{module}" for module in SURVIVING_MODULES))

    served = pocket(payload, root)
    assert served["adapter"] == adapter
    assert served["selection"] == "native"
    assert len(served["invocations"]) == 1, served["invocations"]
    handed_over = args_after(served["invocations"][0]["argv"], *spec["related"])
    assert set(SURVIVING_MODULES) <= set(handed_over), (
        f"{' '.join(spec['related'])} was not handed every changed module "
        f"relative to the pocket root: {served['invocations'][0]['argv']}"
    )
    assert payload["widen"] == []


# -- No other narrowing ------------------------------------------------------


@pytest.mark.parametrize("adapter", ["vitest", "jest"])
def test_a_changed_non_module_file_in_the_pocket_still_runs_it_in_full(
    repo: ScratchRepo, adapter: str
) -> None:
    root = JS_POCKETS[adapter]["root"]
    fixture = f"{root}/test/fixtures/data.json"
    repo.write(fixture, '{"rows": []}\n')
    repo.commit_all("add a fixture read through the filesystem")
    repo.write(fixture, '{"rows": [1]}\n')

    payload = resolve(repo, "--changed", fixture)

    assert pocket(payload, root)["selection"] == "full"
    assert any(fixture in entry["paths"] for entry in widen_entries(payload, "unmapped-path")), (
        payload["widen"]
    )
