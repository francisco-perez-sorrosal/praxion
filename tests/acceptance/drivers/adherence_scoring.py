"""Driver for how the adherence eval scores a run: allowances, forced stops, and reports.

The eval's pilot seams are reached through `adherence_eval`; this module adds what the
scoring scenarios need on top of them.

Bound here, because the specification or the base commit fixes them:

- a mechanical check's paired verdict, through `adherence_eval.role_verdict` (the
  pilot's verdict seam). A pair's discordance on one check is laid out as the
  specification counts it: `b` pairs where only the full arm passed, `c` where only
  the lean arm passed, every other pair passed by both; the net discordance is b - c;
- the oracle for an allowance: the exact one-sided quantile, at the declared
  confidence, of the net discordance b - c an exchangeable pair of arms shows at `d`
  discordant pairs, where b is binomial(d, 1/2). It is computed here from that
  definition, never read from the eval;
- a report, rendered by the console entry's own `--report FILE`, launching nothing;
- the flip verdict a report states for a role: its line `Role <role>: ...`, which at
  the base commit reads `flip verdict clear`, `flip verdict not clear` or
  `underpowered`; and a check's block of that role's section, which opens with the
  check's name and holds its `verdict:` line;
- the flip verdicts the committed results files showed before this change, frozen in
  `fixtures/recorded_adherence_verdicts.json`.

Unbound until a binding step names the designed surface (each raises with the
assumption it stands for):

- a recorded forced-stop session in which the harness stopped the role at its turn
  cap, one in which the role ended before its cap, and one whose record cannot tell;
- a results file whose forced-stop pairs carry the turns each role took, the cap it
  ran under and whether the harness stopped it there;
- the report's per-role, per-arm count of forced-stop sessions that ran out of turns
  and that ended before their cap, and its differential run-out rate;
- the report's statement of a mechanical check's discordant count and allowance, in
  pairs and in percentage points beside the margin.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from math import comb
from pathlib import Path

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import (
    DUMMY_CREDENTIAL,
    EVAL_PROJECT,
    EVAL_PYTHON,
    CheckSpec,
    FlipSettings,
    Pair,
    RoleVerdict,
    SessionEvidence,
    _guarded_path,
    _uv,
    adherence_console_entry,
    eval_env,
    install_tripwire,
)
from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RESULTS_DIR = adherence_eval.REPO_ROOT / ".ai-state" / "eval_ledger" / "adherence"
DECLARED_CONFIDENCE = 0.95
USABLE_PAIRS = 24
MARGIN_PP = 10


# -- The allowance oracle ------------------------------------------------------------


def exact_allowance(discordant: int, confidence: float = DECLARED_CONFIDENCE) -> int:
    """The smallest net discordance b - c that an exchangeable pair reaches with `confidence`."""
    if discordant == 0:
        return 0
    cumulative = 0.0
    for b in range(discordant + 1):
        cumulative += comb(discordant, b) / 2**discordant
        if cumulative >= confidence - 1e-12:
            return 2 * b - discordant
    return discordant


def discordant_pairs(
    check: str, discordant: int, net: int, total: int = USABLE_PAIRS
) -> list[Pair]:
    """`total` pairs on one check: `discordant` of them split so that b - c == `net`."""
    assert (discordant + net) % 2 == 0, (discordant, net)
    assert abs(net) <= discordant <= total, (discordant, net)
    full_only = (discordant + net) // 2
    lean_only = discordant - full_only
    concordant = total - discordant
    return (
        adherence_eval.repeated(full_only, {check: "passed"}, {check: "failed"})
        + adherence_eval.repeated(lean_only, {check: "failed"}, {check: "passed"})
        + adherence_eval.repeated(concordant, {check: "passed"}, {check: "passed"})
    )


def mechanical_verdict(
    discordance: dict[str, tuple[int, int]],
    *,
    calibrated_allowances: dict[str, int] | None = None,
) -> RoleVerdict:
    """A role's verdict over 24 pairs, each named check discordant as `{check: (d, net)}`.

    `calibrated_allowances` hands the verdict the allowances a same-arm calibration run
    yielded, the way the pilot did; the scenarios say the verdict must take none of them.
    """
    checks = [CheckSpec(name, "mechanical") for name in discordance]
    per_check = {name: discordant_pairs(name, d, net) for name, (d, net) in discordance.items()}
    pairs = [
        Pair(
            {name: per_check[name][i].full[name] for name in discordance},
            {name: per_check[name][i].lean[name] for name in discordance},
        )
        for i in range(USABLE_PAIRS)
    ]
    settings = FlipSettings(allowances=dict(calibrated_allowances or {}))
    return adherence_eval.role_verdict(checks, pairs, settings)


# -- Reports through the console entry --------------------------------------------------


@dataclass(frozen=True)
class Rendering:
    exit_code: int
    text: str
    stderr: str


def render(results_path: Path, workspace: Path) -> Rendering:
    """`praxion-evals-adherence --report FILE`, under a tripwire `claude` that refuses to run."""
    tripwire = install_tripwire(workspace / "report-tripwire")
    env = eval_env({"PATH": _guarded_path(tripwire.bin_dir), "ANTHROPIC_API_KEY": DUMMY_CREDENTIAL})
    entry = adherence_console_entry()
    proc = subprocess.run(
        [_uv(), "run", "--quiet", "--python", EVAL_PYTHON, "--project", str(EVAL_PROJECT)]
        + [entry.name, "--report", str(results_path)],
        capture_output=True,
        text=True,
        env=env,
        cwd=EVAL_PROJECT,
        timeout=300,
    )
    assert not tripwire.starts(), "rendering a report started claude"
    return Rendering(proc.returncode, proc.stdout, proc.stderr)


def flip_verdict_class(report: str, role: str) -> str:
    """`clear`, `not clear` or `underpowered`, as the report's line for `role` states it."""
    lines = [ln for ln in report.splitlines() if ln.startswith(f"Role {role}:")]
    assert len(lines) == 1, f"the report has {len(lines)} lines for role {role}:\n{report[:3000]}"
    line = lines[0]
    if "underpowered" in line:
        return "underpowered"
    if "flip verdict not clear" in line:
        return "not clear"
    if "flip verdict clear" in line:
        return "clear"
    raise AssertionError(f"the report's line for {role} states no verdict: {line}")


def check_block(report: str, role: str, check: str) -> str:
    """The lines of `check`'s block inside `role`'s section of a report."""
    lines = report.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"Role {role}:"))
    section = lines[start + 1 :]
    end = next((i for i, ln in enumerate(section) if ln.startswith("Role ")), len(section))
    section = section[:end]
    opening = next((i for i, ln in enumerate(section) if ln.strip().startswith(f"{check} (")), None)
    assert opening is not None, f"the report shows no block for {check} under {role}"
    indent = len(section[opening]) - len(section[opening].lstrip())
    block = [section[opening]]
    for ln in section[opening + 1 :]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
            break
        block.append(ln)
    return "\n".join(block)


def recorded_verdicts() -> dict[str, dict[str, str]]:
    raw = json.loads((FIXTURES / "recorded_adherence_verdicts.json").read_text(encoding="utf-8"))
    return {run_id: roles for run_id, roles in raw.items() if not run_id.startswith("_")}


def recorded_results_file(run_id: str) -> Path:
    return RESULTS_DIR / f"{run_id}.json"


# -- Forced stops: unbound ---------------------------------------------------------------


def forced_stop_evidence(workspace: Path, role: str, ran_out: bool | None) -> SessionEvidence:
    """A forced-stop session's recorded evidence.

    `ran_out=True`: the harness stopped the role at its lowered turn cap; `False`: the
    role ended on its own before the cap and wrote its return; `None`: the record does
    not establish whether the cap was reached.
    """
    raise UnboundDriverError(
        "a recorded forced-stop session carrying the turns the role took, the cap it ran"
        " under and whether the harness stopped it at that cap"
    )


def forced_stop_results(
    workspace: Path,
    role: str,
    *,
    both_ran_out_pairs: int,
    ended_before_cap: dict[str, int] | None = None,
) -> Path:
    """A results file of 24 pairs, `both_ran_out_pairs` of them forced stops that ran out of
    turns in both arms, plus `ended_before_cap[arm]` forced-stop sessions of that arm that
    ended before their cap; every other pair is a clean measured pair."""
    raise UnboundDriverError(
        "a results file whose forced-stop sessions record the turns the role took, its cap"
        " and whether the harness stopped it at the cap"
    )


@dataclass(frozen=True)
class RunOutCounts:
    ran_out: int
    ended_before_cap: int


def forced_stop_counts(report: str, role: str, arm: str) -> RunOutCounts:
    """The report's count, for one role and arm, of forced-stop sessions by how they ended."""
    raise UnboundDriverError(
        "the report states, per role and arm, how many forced-stop sessions ran out of"
        " turns and how many ended before their cap"
    )


def differential_run_out_rate(report: str, role: str) -> float:
    """The report's differential run-out rate between the arms, in percentage points."""
    raise UnboundDriverError(
        "the report states the differential run-out rate between the arms of a role"
    )


# -- Allowance statements: unbound ---------------------------------------------------------


@dataclass(frozen=True)
class AllowanceStatement:
    discordant: int
    allowance_pairs: int
    allowance_points: float
    margin_points: float


def allowance_statement(report: str, role: str, check: str) -> AllowanceStatement:
    """What the report states beside a mechanical check: discordance, allowance, margin."""
    raise UnboundDriverError(
        "the report states, per mechanical check, its discordant count and its allowance"
        " in pairs and in percentage points beside the declared margin"
    )
