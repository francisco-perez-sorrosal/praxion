"""A paid adherence run, end to end, that spends nothing.

The operator's journey crosses three boundaries: the console entry, the `claude`
binary it launches sessions through, and the results file it writes. This driver
points the eval at a clean copy of this repository as the checkout under test,
puts a stand-in `claude` first on PATH (it records each launch and answers with a
session in which the role is never spawned, so no arm proof can succeed and no
real session is ever started), runs the console entry, and hands back the
launches, the results file and the checkout's state before and after.

The console entry's options and the results file's fields are reached through
the acceptance driver's hooks, which raise until bound to the designed surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.adherence_eval import (
    CliResult,
    FakeClaude,
    Launch,
    RunRecord,
    RunRequest,
    checkout_under_test,
    install_fake_claude,
    omits_claude_md,
    read_results,
    run_adherence_eval,
    tracked_snapshot,
    working_state,
)

AMPLE_CAP_USD = 25.0
SESSION_BUDGET_USD = 1.0


@dataclass(frozen=True)
class Journey:
    request: RunRequest
    cli: CliResult
    fake: FakeClaude
    checkout_before: dict[str, str]
    checkout_after: dict[str, str]
    state_before: tuple[str, str]
    state_after: tuple[str, str]

    @property
    def launches(self) -> list[Launch]:
        return self.fake.launches()

    @property
    def results(self) -> RunRecord:
        return read_results(self.request.output)

    def files_in_results_dir(self) -> list[Path]:
        return sorted(p for p in self.request.output.parent.iterdir() if p.is_file())

    def describe(self) -> str:
        return f"exit {self.cli.exit_code}; stderr tail:\n{self.cli.stderr[-1500:]}"


def run_journey(
    workspace: Path,
    *,
    roles: tuple[str, ...],
    arms: tuple[str, ...],
    run_cap_usd: float = AMPLE_CAP_USD,
    session_budget_usd: float = SESSION_BUDGET_USD,
    sessions_report_cost: bool = True,
    margin_pp: float | None = None,
    required_pairs: int | None = None,
    existing_results: str | None = None,
    overwrite: bool = False,
    extra_env: dict[str, str] | None = None,
) -> Journey:
    checkout = checkout_under_test(workspace)
    output = workspace / "results" / "adherence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if existing_results is not None:
        output.write_text(existing_results, encoding="utf-8")
    fake = install_fake_claude(workspace, cost_usd=0.01 if sessions_report_cost else None)
    request = RunRequest(
        roles=roles,
        arms=arms,
        checkout=checkout,
        output=output,
        run_cap_usd=run_cap_usd,
        session_budget_usd=session_budget_usd,
        margin_pp=margin_pp,
        required_pairs=required_pairs,
        overwrite=overwrite,
    )
    before, state_before = tracked_snapshot(checkout), working_state(checkout)
    cli = run_adherence_eval(request, fake.bin_dir, extra_env=extra_env)
    return Journey(
        request,
        cli,
        fake,
        before,
        tracked_snapshot(checkout),
        state_before,
        working_state(checkout),
    )


def flagged_roles(launch: Launch) -> set[str]:
    """The roles whose definition in the launch's plugin copy carries `omitClaudeMd: true`."""
    return {
        name.removesuffix(".md")
        for name, text in launch.agent_texts.items()
        if text.startswith("---\n") and omits_claude_md(text)
    }
