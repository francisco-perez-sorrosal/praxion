"""Eval family code reaches LLMs only through the JudgeClient adapter.

Cites: dec-204 (the adapter owns the auth seam: it selects the OAuth or API-key
route at runtime, refuses construction inside a nested Claude Code invocation
where the SDK deadlocks, and enforces a wall-clock ceiling on every judge call).
A family module importing an SDK directly bypasses all three protections while
still looking correct.

The invariant was stated three times in prose -- once in the adapter and once in
each family module -- and enforced nowhere, which is the condition this suite
exists to end.

`allow_indirect_imports = True` on the contract is load-bearing: reaching an SDK
*through* the adapter is the intended route, so a transitive ban would flag the
one path that is correct. The contract encodes the stated invariant -- no direct
import -- and nothing beyond it.
"""

import os
import subprocess
import textwrap
from pathlib import Path

CONTRACT = "eval family code must reach LLMs only through the JudgeClient adapter"

# praxion_evals lives in a sibling project the root environment does not
# install. The graph builder parses rather than executes, so only the source
# tree must be findable.
EVAL_SRC = "eval/src"


def test_judge_seam_invariant_holds(project_root: Path, import_linter_cfg: Path) -> None:
    """The real contract MUST pass against the live tree."""
    result = subprocess.run(
        ["uv", "run", "lint-imports", "--config", str(import_linter_cfg), "--no-cache"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": EVAL_SRC},
    )
    assert result.returncode == 0, (
        f"Fitness contract failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert CONTRACT in result.stdout, "contract missing from the run -- was it renamed?"


def test_canary_rejects_a_family_importing_an_sdk_directly(
    tmp_path: Path, project_root: Path
) -> None:
    """Canary: a family module importing an SDK directly breaks the contract.

    Mirrors the real contract against a fixture package, so the assertion is
    about the rule's shape rather than about the live tree happening to comply.
    """
    pkg = tmp_path / "evals_fixture"
    (pkg / "families").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "judge_client.py").write_text("import anthropic\n", encoding="utf-8")
    (pkg / "families" / "__init__.py").write_text("", encoding="utf-8")
    # The violation: straight past the adapter.
    (pkg / "families" / "family_bad.py").write_text("import anthropic\n", encoding="utf-8")

    cfg = tmp_path / "import-linter-fixture.cfg"
    cfg.write_text(
        textwrap.dedent(f"""\
            [importlinter]
            include_external_packages = True
            root_packages =
                evals_fixture

            [importlinter:contract:seam]
            name = {CONTRACT}
            type = forbidden
            allow_indirect_imports = True
            description = dec-204 the adapter owns the auth seam.
            source_modules =
                evals_fixture.families
            forbidden_modules =
                anthropic
        """),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["uv", "run", "--with", "import-linter", "lint-imports", "--config", str(cfg)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
    )
    assert result.returncode != 0, f"canary did not bite:\n{result.stdout}"
    assert "BROKEN" in result.stdout


def test_canary_reaching_the_sdk_through_the_adapter_is_allowed(
    tmp_path: Path, project_root: Path
) -> None:
    """The inverse guard: the intended route must NOT be flagged.

    Without `allow_indirect_imports`, this fixture fails -- which is exactly
    what the live contract did before that setting was added, flagging the one
    path the design requires.
    """
    pkg = tmp_path / "evals_ok"
    (pkg / "families").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "judge_client.py").write_text("import anthropic\n", encoding="utf-8")
    (pkg / "families" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "families" / "family_ok.py").write_text(
        "from evals_ok import judge_client\n", encoding="utf-8"
    )

    cfg = tmp_path / "import-linter-ok.cfg"
    cfg.write_text(
        textwrap.dedent("""\
            [importlinter]
            include_external_packages = True
            root_packages =
                evals_ok

            [importlinter:contract:seam]
            name = through the adapter is allowed
            type = forbidden
            allow_indirect_imports = True
            description = dec-204 the adapter owns the auth seam.
            source_modules =
                evals_ok.families
            forbidden_modules =
                anthropic
        """),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["uv", "run", "--with", "import-linter", "lint-imports", "--config", str(cfg)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
    )
    assert result.returncode == 0, f"the intended route was flagged:\n{result.stdout}"
