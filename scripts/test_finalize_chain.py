"""Gate behavior for the finalize hook chain (`scripts/finalize_chain.sh`).

Cites: scripts/finalize_chain.sh — the bash library that decides which finalizers
fire on a given repo state. These tests pin the *decoupling* contract: ADR-draft
promotion is gated on drafts being present, but tech-debt ledger reconciliation
runs on any on-main commit (its byte-equivalent no-op contract makes that free).
Bundling the tech-debt finalizer behind the drafts gate previously stranded
tech-debt resolutions committed without a concurrent ADR draft.

The bash gate predicates have no other test coverage; these exercise the
state-driven entry point (shared by post-commit and post-checkout) by sourcing
the library and stubbing the script-runner plus the repo-state predicates.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

CHAIN_PATH = Path(__file__).parent / "finalize_chain.sh"


def _run_state_driven(
    *,
    on_main: bool,
    drafts_present: bool,
    repo_root: str = "/fake/repo",
) -> list[str]:
    """Source the chain, stub the predicates, and return finalizers that fired.

    Stubs ``_finalize_chain_run_script`` to echo each finalizer's label instead
    of invoking the real python scripts, so the test observes the gate decision
    without side effects.

    ``repo_root`` controls what ``_finalize_chain_repo_root`` returns, which in
    turn determines whether the doc-manifest existence gate fires.  The default
    ``/fake/repo`` has no manifest, so the gate keeps ``build_doc_manifest`` out
    of the existing four tests unchanged.
    """

    on_main_rc = 0 if on_main else 1
    drafts_rc = 0 if drafts_present else 1
    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        _finalize_chain_repo_root() {{ echo {repo_root!r}; }}
        _finalize_chain_on_main() {{ return {on_main_rc}; }}
        _finalize_chain_drafts_present() {{ return {drafts_rc}; }}
        _finalize_chain_state_driven
    """
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.split(":", 1)[1] for line in result.stdout.splitlines() if line.startswith("RAN:")]


def test_tech_debt_finalizer_runs_on_main_without_drafts() -> None:
    """The fix: a resolution committed to main with no ADR draft still finalizes."""
    fired = _run_state_driven(on_main=True, drafts_present=False)
    assert "finalize_tech_debt_ledger" in fired


def test_adr_finalizer_skipped_on_main_without_drafts() -> None:
    """ADR promotion keeps its genuine trigger — it does not fire without drafts."""
    fired = _run_state_driven(on_main=True, drafts_present=False)
    assert "finalize_adrs" not in fired


def test_both_finalizers_run_on_main_with_drafts() -> None:
    """With drafts present, both finalizers fire (ADR before ledger)."""
    fired = _run_state_driven(on_main=True, drafts_present=True)
    assert fired == ["finalize_adrs", "finalize_tech_debt_ledger"]


def test_nothing_runs_off_main_even_with_drafts() -> None:
    """Off main, the state-driven gate is a no-op regardless of drafts."""
    assert _run_state_driven(on_main=False, drafts_present=False) == []
    assert _run_state_driven(on_main=False, drafts_present=True) == []


def test_build_doc_manifest_fires_on_main_when_manifest_exists(tmp_path: Path) -> None:
    """build_doc_manifest fires on main and lands after finalize_tech_debt_ledger.

    The manifest must be present for the existence gate to open, and the step
    must come after the ledger finalizer so the committed index reflects the
    post-finalize dec-NNN renames and TECH_DEBT_RESOLVED migrations.
    """
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    (ai_state / "doc_manifest.yaml").write_text("generated_at: 2025-01-01\n")

    fired = _run_state_driven(on_main=True, drafts_present=False, repo_root=str(tmp_path))

    assert "build_doc_manifest" in fired
    assert fired.index("build_doc_manifest") > fired.index("finalize_tech_debt_ledger")


def test_build_doc_manifest_skipped_when_manifest_absent(tmp_path: Path) -> None:
    """Existence gate: build_doc_manifest is not invoked when doc_manifest.yaml is absent.

    Projects that never opted into the dashboard manifest must not gain a
    committed doc_manifest.yaml on the first on-main merge (pre-mortem #1).
    """
    # tmp_path has no .ai-state/doc_manifest.yaml — existence gate keeps it out
    fired = _run_state_driven(on_main=True, drafts_present=False, repo_root=str(tmp_path))

    assert "build_doc_manifest" not in fired


def test_all_three_finalizers_fire_on_main_with_drafts_and_manifest(tmp_path: Path) -> None:
    """With drafts + manifest present all three steps fire in order: ADR → ledger → manifest."""
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    (ai_state / "doc_manifest.yaml").write_text("generated_at: 2025-01-01\n")

    fired = _run_state_driven(on_main=True, drafts_present=True, repo_root=str(tmp_path))

    assert fired == ["finalize_adrs", "finalize_tech_debt_ledger", "build_doc_manifest"]


def _run_on_main_real(
    *,
    repo_root: Path,
    finalize_dir: Path,
    strict: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Source the chain and run `_finalize_chain_run_on_main` end-to-end.

    Overrides ``FINALIZE_CHAIN_DIR`` to point at a fake finalizer directory so
    the REAL (non-stubbed) `_finalize_chain_run_script` executes an actual
    python script — this proves exit-code propagation rather than assuming it
    from a stubbed return value.
    """
    strict_line = "export FINALIZE_CHAIN_STRICT=1" if strict else ""
    snippet = f"""
        source {CHAIN_PATH}
        FINALIZE_CHAIN_DIR={str(finalize_dir)!r}
        {strict_line}
        _finalize_chain_run_on_main {str(repo_root)!r}
    """
    return subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)


def test_run_on_main_swallows_failing_finalizer_by_default(tmp_path: Path) -> None:
    """Characterization: non-strict on-main composition always exits 0, even when
    a finalizer fails. Pins the CURRENT hook semantics before the strict-mode
    refactor — a failing finalizer warns but never aborts the (already-completed)
    git operation.
    """
    finalize_dir = tmp_path / "scripts"
    finalize_dir.mkdir()
    (finalize_dir / "finalize_tech_debt_ledger.py").write_text("import sys\nsys.exit(1)\n")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = _run_on_main_real(repo_root=repo_root, finalize_dir=finalize_dir)

    assert result.returncode == 0
    assert "warned (non-blocking)" in result.stdout


def test_strict_mode_propagates_failing_finalizer_exit(tmp_path: Path) -> None:
    """New behavior: FINALIZE_CHAIN_STRICT=1 makes a failing finalizer abort loudly
    instead of warning-and-continuing — the server-side (CI) safety contract.
    """
    finalize_dir = tmp_path / "scripts"
    finalize_dir.mkdir()
    (finalize_dir / "finalize_tech_debt_ledger.py").write_text("import sys\nsys.exit(1)\n")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    result = _run_on_main_real(repo_root=repo_root, finalize_dir=finalize_dir, strict=True)

    assert result.returncode != 0


def test_finalize_chain_run_on_main_runs_full_composition_in_order(tmp_path: Path) -> None:
    """New public entry point: full composition fires in fixed order adr -> ledger -> manifest."""
    ai_state = tmp_path / ".ai-state"
    ai_state.mkdir()
    (ai_state / "doc_manifest.yaml").write_text("generated_at: 2025-01-01\n")
    drafts_dir = ai_state / "decisions" / "drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "20260101-0000-fake.md").write_text(
        "---\nid: dec-draft-aaaaaaaa\n---\n"  # id-citation-discipline:ignore
    )

    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        finalize_chain_run_on_main {str(tmp_path)!r}
    """
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=True)
    fired = [
        line.split(":", 1)[1] for line in result.stdout.splitlines() if line.startswith("RAN:")
    ]

    assert fired == ["finalize_adrs", "finalize_tech_debt_ledger", "build_doc_manifest"]


def test_finalize_chain_run_on_main_resolves_repo_root_when_omitted(tmp_path: Path) -> None:
    """When called with no argument, repo_root is resolved via `_finalize_chain_repo_root`."""
    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        _finalize_chain_repo_root() {{ echo {str(tmp_path)!r}; }}
        finalize_chain_run_on_main
    """
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=True)
    fired = [
        line.split(":", 1)[1] for line in result.stdout.splitlines() if line.startswith("RAN:")
    ]

    assert fired == ["finalize_tech_debt_ledger"]


# ---------------------------------------------------------------------------
# Interpreter resolution
#
# A bare `python3` is not necessarily an interpreter holding the project's
# declared dependencies. When it is not, any chain script needing a third-party
# package fails, the chain degrades to a non-blocking warning, and the state
# that script maintains drifts silently.
# ---------------------------------------------------------------------------


def _resolve_python(*, repo_root: str, env: dict[str, str] | None = None) -> str:
    """Source the chain and return the interpreter it would use."""
    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_repo_root() {{ echo {repo_root!r}; }}
        _finalize_chain_python
    """
    result = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **(env or {})},
    )
    return result.stdout.strip()


def _make_venv(root: Path) -> Path:
    """Create an executable stub at <root>/.venv/bin/python."""
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    return python


def test_project_venv_is_preferred_over_ambient_python(tmp_path: Path) -> None:
    """The regression: the ambient python3 lacked a declared dependency."""
    python = _make_venv(tmp_path)
    assert _resolve_python(repo_root=str(tmp_path)) == str(python)


def test_explicit_override_outranks_the_project_venv(tmp_path: Path) -> None:
    _make_venv(tmp_path)
    override = tmp_path / "override-python"
    override.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    override.chmod(0o755)
    resolved = _resolve_python(repo_root=str(tmp_path), env={"PRAXION_PYTHON": str(override)})
    assert resolved == str(override)


def test_falls_back_to_ambient_python_without_a_venv(tmp_path: Path) -> None:
    """Consumer projects have no venv; stdlib-only finalizers must still run."""
    resolved = _resolve_python(repo_root=str(tmp_path))
    assert resolved.endswith("python3")


def test_unusable_override_falls_through_rather_than_breaking(tmp_path: Path) -> None:
    """A stale PRAXION_PYTHON must not strand the chain."""
    python = _make_venv(tmp_path)
    resolved = _resolve_python(
        repo_root=str(tmp_path), env={"PRAXION_PYTHON": str(tmp_path / "gone")}
    )
    assert resolved == str(python)
