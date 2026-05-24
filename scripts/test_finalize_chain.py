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


def _run_state_driven(*, on_main: bool, drafts_present: bool) -> list[str]:
    """Source the chain, stub the predicates, and return finalizers that fired.

    Stubs ``_finalize_chain_run_script`` to echo each finalizer's label instead
    of invoking the real python scripts, so the test observes the gate decision
    without side effects.
    """

    on_main_rc = 0 if on_main else 1
    drafts_rc = 0 if drafts_present else 1
    snippet = f"""
        source {CHAIN_PATH}
        _finalize_chain_run_script() {{ echo "RAN:$1"; }}
        _finalize_chain_repo_root() {{ echo /fake/repo; }}
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
    return [
        line.split(":", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("RAN:")
    ]


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
