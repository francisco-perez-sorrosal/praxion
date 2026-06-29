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
