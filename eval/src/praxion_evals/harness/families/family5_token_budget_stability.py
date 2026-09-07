"""Family 5 — token-budget surface stability collector (process-economy P0.7).

A *collector*, not a per-item family: there is exactly one always-loaded
surface to observe, so ``run()`` returns a single CheckResult rather than one
per artifact. It is entirely mechanical — it never calls ``judge.judge()``
and never reads ``ANTHROPIC_API_KEY``, so it runs identically regardless of
``mechanical_only`` and never makes a live token-count API call: it always
takes ``measure()``/``measure_listing()``'s graceful no-key fallback (a
labelled byte-based estimate), which is all the byte-trend half of the
verdict needs anyway (see ``scripts/measure_token_budget.py``'s own
docstring on why the trend compares bytes, not tokens).

Reuses ``scripts/measure_token_budget.py`` rather than re-deriving the
governed file set or the tokenizer/estimate fallback — that module is the
single source of truth for both (its own docstring exists precisely because
three inconsistent bases coexisted here before). ``scripts/`` sits outside
the ``praxion-evals`` package (a separate uv project), so it is loaded by
path rather than imported as a dependency; see ``_load_measure_token_budget``.

Unlike ``ratchet()`` in that module (which appends today's sample to the
committed baseline as a side effect — the correct behaviour for the daily
commit-gate hook it backs), this collector only *reads* the baseline file.
An eval report is an observation, not a bookkeeping step, and re-running
``/eval-praxion`` should never mutate committed state. The trailing-30-day
byte-delta and frozen-listing-ceiling comparisons are re-derived here,
read-only, against whatever the baseline already contains.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from praxion_evals.harness.families import Family
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.harness.schemas import CheckResult, Corpus

# eval/src/praxion_evals/harness/families/ -> eval/ -> repo root
_EVAL_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _EVAL_ROOT.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

_DEFAULT_BASELINE_RELATIVE_PATH = (".ai-state", "token_budget_baseline.json")

# Mirrors scripts/measure_token_budget.py's _RATCHET_WINDOW_DAYS. Kept as a
# local named constant rather than importing the private module constant --
# the window is a stable, documented contract (td-180), not an implementation
# detail this collector should follow silently if the source ever changes it.
_TRAILING_WINDOW_DAYS = 30

_WARN_UTILISATION = 0.90


def _load_measure_token_budget() -> Any:
    """Import ``scripts/measure_token_budget.py`` as a sibling-safe module.

    That script imports ``_repo_root`` as a same-directory sibling (the
    pattern its own docstring documents for every ``scripts/`` consumer), so
    ``scripts/`` must be on ``sys.path`` before the import. Only the module's
    own directory is added -- the eval project's package layout is untouched.
    """
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    return importlib.import_module("measure_token_budget")


# ---------------------------------------------------------------------------
# Read-only baseline helpers (deliberately not scripts/measure_token_budget's
# ratchet() -- see module docstring for why this collector never writes)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TrendCheck:
    """Result of comparing a live reading against the baseline file."""

    delta_bytes: int | None
    note: str | None


def _read_baseline(path: Path) -> dict[str, Any] | None:
    """The baseline dict, or None on absence/corruption -- both degrade the same way."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _trailing_byte_delta(
    baseline: dict[str, Any] | None, governed_bytes: int, today: date
) -> _TrendCheck:
    """Byte delta against the oldest byte-tracked sample >= the trailing window old."""
    if baseline is None:
        return _TrendCheck(None, "no baseline file — trailing-30-day delta unavailable")

    today_str = today.isoformat()
    byte_tracked_priors = sorted(
        (
            s
            for s in baseline.get("samples", [])
            if s.get("date") != today_str and "governed_bytes" in s
        ),
        key=lambda s: s["date"],
    )
    if not byte_tracked_priors:
        return _TrendCheck(
            None, "no byte-tracked prior sample in the baseline — trailing-30-day delta unavailable"
        )

    oldest = byte_tracked_priors[0]
    tracked_days = (today - date.fromisoformat(oldest["date"])).days
    if tracked_days < _TRAILING_WINDOW_DAYS:
        return _TrendCheck(
            None, f"only {tracked_days} day(s) of baseline history — need {_TRAILING_WINDOW_DAYS}"
        )
    return _TrendCheck(governed_bytes - oldest["governed_bytes"], None)


def _listing_ceiling_check(
    baseline: dict[str, Any] | None, listing: dict[str, Any]
) -> tuple[int | None, bool, str | None]:
    """(ceiling, is_over, note) — basis-guarded, mirrors ratchet()'s comparison."""
    if baseline is None:
        return None, False, "no baseline file — frozen listing ceiling unavailable"

    ceiling = baseline.get("listing_ceiling")
    if ceiling is None:
        return None, False, "no frozen listing ceiling recorded in the baseline"

    ceiling_basis = baseline.get("listing_ceiling_basis", "tokenizer")
    today_basis = "tokenizer" if listing.get("measured", True) else "estimate"
    if ceiling_basis != today_basis:
        return (
            ceiling,
            False,
            f"listing ceiling was frozen on basis {ceiling_basis!r} but today's listing "
            f"reading is basis {today_basis!r} — skipping the listing-ceiling check",
        )
    return ceiling, listing["tokens"] > ceiling, None


# ---------------------------------------------------------------------------
# Family5TokenBudgetStability
# ---------------------------------------------------------------------------


class Family5TokenBudgetStability(Family):
    """Always-loaded token-budget surface, tracked against ceiling and trend.

    Args:
        repo_root: Filesystem root to measure. Defaults to this repo's own
            root (derived from this file's location) so the family works
            standalone; ``run_eval()`` overrides it with the resolved
            invocation root so a corpus pointed at a scratch directory
            (tests) never touches this repo's real committed state.
        baseline_path: Override for the baseline file location (tests point
            this at a scratch fixture). Defaults to
            ``<repo_root>/.ai-state/token_budget_baseline.json``.
        today: Override for "today" (tests need a fixed date to reason about
            the trailing window). Defaults to ``date.today()``.
        measure_module: Override for the dynamically-imported
            ``measure_token_budget`` module (tests inject a stub exposing
            ``measure``/``measure_listing`` so the collector's verdict logic
            can be exercised without touching this machine's real
            ``~/.claude/`` surface or the real committed baseline).
    """

    id = "family5-token-budget-stability"
    name = "Token-budget surface stability"
    corpus_paths = ()

    def __init__(
        self,
        repo_root: Path | None = None,
        baseline_path: Path | None = None,
        today: date | None = None,
        measure_module: Any | None = None,
    ) -> None:
        self._repo_root = repo_root if repo_root is not None else _REPO_ROOT
        self._baseline_path = (
            baseline_path
            if baseline_path is not None
            else self._repo_root.joinpath(*_DEFAULT_BASELINE_RELATIVE_PATH)
        )
        self._today = today if today is not None else date.today()
        self._measure_module = measure_module

    def run(
        self,
        corpus: Corpus,
        judge: JudgeClient,
        *,
        mechanical_only: bool = False,
    ) -> list[CheckResult]:
        """Measure the governed + listing surfaces and verdict against the baseline.

        Args:
            corpus: Unused — this collector measures the live filesystem
                surface at ``repo_root``, not per-artifact corpus content.
            judge: Unused — this family never calls the judge.
            mechanical_only: Unused — this family makes no LLM-judged check
                to begin with, so it runs identically either way.

        Returns:
            A single-element list containing the collector's CheckResult.
        """
        del corpus, judge, mechanical_only  # unused: pure mechanical collector
        mtb = self._measure_module or _load_measure_token_budget()

        # api_key=None unconditionally: this collector never spends a live
        # token-count call (see module docstring) -- both readings take the
        # graceful, labelled byte-based estimate rather than the tokenizer.
        governed = mtb.measure(self._repo_root, api_key=None)
        listing = mtb.measure_listing(self._repo_root, api_key=None)
        baseline = _read_baseline(self._baseline_path)

        trend = _trailing_byte_delta(baseline, governed["bytes"], self._today)
        listing_ceiling, listing_over, listing_note = _listing_ceiling_check(baseline, listing)

        fail_reasons: list[str] = []
        if governed["over_by"] > 0:
            fail_reasons.append(
                f"governed tokens {governed['tokens']:,} exceed the "
                f"{governed['budget']:,} ceiling by {governed['over_by']:,}"
            )
        if trend.delta_bytes is not None and trend.delta_bytes > 0:
            fail_reasons.append(
                f"governed surface grew by {trend.delta_bytes:,} bytes over the "
                f"trailing {_TRAILING_WINDOW_DAYS} days"
            )
        if listing_over:
            fail_reasons.append(
                f"listing tokens {listing['tokens']:,} exceed the frozen ceiling "
                f"{listing_ceiling:,}"
            )

        if fail_reasons:
            verdict = "FAIL"
        elif governed["utilisation"] >= _WARN_UTILISATION:
            verdict = "WARN"
        else:
            verdict = "PASS"

        findings = [
            f"governed: {governed['tokens']:,}/{governed['budget']:,} tokens "
            f"({governed['utilisation']:.1%}, basis={governed['basis']}, "
            f"{governed['bytes']:,} bytes over {len(governed['files'])} files)",
            f"listing: {listing['tokens']:,} tokens (basis={listing['basis']}, "
            f"ceiling={listing_ceiling}, {listing['bytes']:,} bytes over "
            f"{listing['file_count']} files)",
        ]
        findings.append(
            f"trailing-{_TRAILING_WINDOW_DAYS}-day governed byte delta: {trend.delta_bytes:+,}"
            if trend.delta_bytes is not None
            else trend.note or "trailing-window delta unavailable"
        )
        if listing_note:
            findings.append(listing_note)
        findings.extend(fail_reasons)
        if verdict == "PASS":
            findings.append("within budget, no adverse trend detected")
        elif verdict == "WARN":
            findings.append(
                f"utilisation {governed['utilisation']:.1%} at or above the "
                f"{_WARN_UTILISATION:.0%} warn threshold"
            )

        return [
            CheckResult(
                check_name="token_budget_stability",
                check_kind="mechanical",
                verdict=verdict,
                artifact_path="/".join(_DEFAULT_BASELINE_RELATIVE_PATH),
                findings=tuple(findings),
                score=-1,
            )
        ]
