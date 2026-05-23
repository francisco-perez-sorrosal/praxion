"""Starter architectural invariant: pre-commit (check_*) scripts must not import post-merge (finalize_*) scripts.

Cites: CLAUDE.md§Structural Beauty (reliable systems are beautiful ones — well-organized code
with clean boundaries and cohesive modules signals structural soundness; mixing
pre-commit and post-merge execution contexts is a structural smell that this
invariant prevents).

This test runs the import-linter contract `check-scripts-precondition-boundary` declared
in `fitness/import-linter.cfg` and asserts it KEEPS (passes). The implementer of
Step 2.3 replaces the placeholder contract with this real invariant contract; this
test verifies the wiring holds end-to-end.
"""

import subprocess
import textwrap
from pathlib import Path


def test_starter_invariant_holds(project_root: Path, import_linter_cfg: Path) -> None:
    """The starter contract MUST pass — run import-linter via subprocess."""
    result = subprocess.run(
        ["uv", "run", "lint-imports", "--config", str(import_linter_cfg)],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    # exit 0 = all contracts KEPT; non-zero = at least one BROKEN or config error
    assert result.returncode == 0, (
        f"Fitness contract failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Canary: prove the import-linter contract fails on a violating fixture
# ---------------------------------------------------------------------------


def test_fails_contract_when_check_script_imports_finalize_script(
    tmp_path: Path, project_root: Path
) -> None:
    """Canary: lint-imports exits non-zero when the boundary invariant is violated.

    We build a minimal package under tmp_path where a check_* module imports
    from a finalize_* module, wire up a forbidden-import contract identical to
    the real one, and assert lint-imports detects the violation.

    This proves the gate bites: if someone adds `import finalize_adrs` inside
    a check_* script, the fitness suite catches it.

    NOTE: import-linter needs the package on sys.path. We write a pyproject.toml
    with the scripts package as a root package and run via `uv run` from
    project_root so the environment is consistent.
    """
    # -- Fixture mini-package (separate from the real scripts/ to avoid conflicts) --
    pkg = tmp_path / "scripts_fixture"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # A check_ module that illegally imports a finalize_ module
    (pkg / "check_bad.py").write_text(
        "from scripts_fixture import finalize_illegal\n",
        encoding="utf-8",
    )
    (pkg / "finalize_illegal.py").write_text(
        "# post-merge script\n",
        encoding="utf-8",
    )

    # import-linter config for the fixture
    cfg_text = textwrap.dedent("""\
        [importlinter]
        root_packages =
            scripts_fixture

        [importlinter:contract:boundary-violation]
        name = check_* must not import finalize_*
        type = forbidden
        description = CLAUDE.md§Structural Beauty: pre-commit scripts must not import post-merge scripts.
        source_modules =
            scripts_fixture.check_bad
        forbidden_modules =
            scripts_fixture.finalize_illegal
    """)
    cfg_file = tmp_path / "import-linter-fixture.cfg"
    cfg_file.write_text(cfg_text, encoding="utf-8")

    result = subprocess.run(
        [
            "uv",
            "run",
            "--with",
            "import-linter",
            "lint-imports",
            "--config",
            str(cfg_file),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(tmp_path),
        },
        check=False,
    )
    assert result.returncode != 0, (
        "import-linter must exit non-zero when a check_* script imports a finalize_* "
        f"script (the boundary invariant is violated).\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
