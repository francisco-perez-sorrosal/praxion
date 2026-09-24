"""Run-level spend cap shared by every path that launches paid sessions.

Each launch first reserves its worst case — the session's own
``--max-budget-usd`` — and is refused once that reservation would cross the
cap, so the cap holds even with sessions in flight. A finished session settles
at the cost its envelope reports, or at its full budget when it reports none:
a timeout or crash may still have spent it, and charging $0 would let the cap
drift upward unseen.

The ledger is an immutable value; a caller running sessions concurrently must
serialize ``reserve``/``settle`` on its own lock.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from praxion_evals.live.results import Errored

RUNNER_SPEND_CAP_USD = 50.0
RECORDER_SPEND_CAP_USD = 10.0


@dataclass(frozen=True)
class SpendLedger:
    cap_usd: float
    spent_usd: float = 0.0
    reserved_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.cap_usd <= 0:
            raise ValueError(f"spend cap must be positive, got {self.cap_usd}")

    def reserve(self, budget_usd: float) -> SpendLedger | Errored:
        """Admit one launch at its worst case, or refuse it without launching."""
        committed = self.spent_usd + self.reserved_usd
        if committed + budget_usd > self.cap_usd:
            return Errored(
                kind="not_run_budget_exhausted",
                detail=(
                    f"launch budget ${budget_usd:.2f} on top of ${committed:.2f} committed "
                    f"would exceed the ${self.cap_usd:.2f} cap"
                ),
            )
        return replace(self, reserved_usd=self.reserved_usd + budget_usd)

    def settle(self, budget_usd: float, cost_usd: float | None) -> SpendLedger:
        charged = budget_usd if cost_usd is None else cost_usd
        return replace(
            self,
            spent_usd=self.spent_usd + charged,
            reserved_usd=self.reserved_usd - budget_usd,
        )
