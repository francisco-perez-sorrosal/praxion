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
  `fixtures/recorded_adherence_verdicts.json`;
- a recorded forced-stop session, as the stream holds it: a role the harness stopped at
  its turn cap carries the harness's note (`NOTE: this agent stopped at its N-turn
  limit`, read from a recorded results file) ahead of its partial return in the spawn's
  tool result; a role that ended before its cap wrote a return and carries no note; a
  stream with neither a note, nor the role's requests, nor a return cannot tell;
- a results file of forced-stop sessions, each carrying the `role_ending` of the Seam
  Contract's pin W8; only a forced-stop session carries one, so the report finds them by
  it;
- the report lines of the Seam Contract: per role and arm
  `forced-stop sessions, <arm> arm: <n> ran out of turns, <m> ended before their cap`
  and `differential run-out rate (lean minus full): <x.x> pp`, and inside a mechanical
  check's block `allowance: <k> pairs (<pp> pp) at <d> discordant pairs; declared margin
  <M> pp`.

Pins the Seam Contract leaves open: the turn count and the stop reason of a role come
from the stream alone (the note, the role's own requests and its return); the cap is
not handed to the grader. A production step that finds one wrong stops with a plan
amendment; it never edits this driver.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from math import comb
from pathlib import Path

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import (
    DUMMY_CREDENTIAL,
    EVAL_PROJECT,
    EVAL_PYTHON,
    OWN_DISCORDANCE_EXACT,
    CheckSpec,
    FlipSettings,
    Pair,
    RoleMeasurement,
    RoleVerdict,
    SessionEvidence,
    _guarded_path,
    _uv,
    adherence_console_entry,
    eval_env,
    install_tripwire,
    scratch_repo,
    session_envelope,
    session_places,
)

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
    settings = FlipSettings(
        allowances=dict(calibrated_allowances or {}), allowance_method=OWN_DISCORDANCE_EXACT
    )
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


def role_section(report: str, role: str) -> str:
    """The text of `role`'s section of a report, from its `Role <role>:` line to the next role's."""
    lines = report.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"Role {role}:"))
    section = lines[start + 1 :]
    end = next((i for i, ln in enumerate(section) if ln.startswith("Role ")), len(section))
    return "\n".join(section[:end])


def check_block(report: str, role: str, check: str) -> str:
    """The lines of `check`'s block inside `role`'s section of a report."""
    section = role_section(report, role).splitlines()
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


# -- Forced stops ---------------------------------------------------------------------------

FORCED_STOP_CAP = 6
EARLY_ENDING_TURNS = 3
# The harness's own note, ahead of the role's partial return in the spawn's tool result.
TURN_LIMIT_NOTE = (
    f"NOTE: this agent stopped at its {FORCED_STOP_CAP}-turn limit before finishing. The text"
    " below is PARTIAL output; treat it as incomplete. Send the agent a message (SendMessage)"
    " to let it continue from where it stopped.\n\n"
)
RAN_OUT = {"C2": "not applicable", "C5": "passed"}
ENDED_BEFORE_CAP = {"C2": "passed", "C5": "not applicable"}
NOT_A_FORCED_STOP = {"C2": "passed", "C5": "not applicable"}
FORCED_STOP_CHECKS = (CheckSpec("C2", "mechanical"), CheckSpec("C5", "mechanical"))
FIRST_REQUEST_TOKENS = {"full": 40_000, "lean": 30_000}


def forced_stop_evidence(workspace: Path, role: str, ran_out: bool | None) -> SessionEvidence:
    """A forced-stop session's recorded evidence.

    `ran_out=True`: the harness stopped the role at its lowered turn cap, as its note in
    the spawn's tool result says; `False`: the role ended on its own before the cap and
    wrote its return; `None`: the stream holds neither a note, nor the role's requests,
    nor a return, so it cannot establish whether the cap was reached.
    """
    repo = scratch_repo(workspace)
    places = session_places(workspace)
    reads = [adherence_eval.read(repo.path("README.md"))]
    common = {"role": role, "cwd": repo.root, "plugin_copy": places.plugin_copy}
    if ran_out is True:
        envelope = session_envelope(
            **common,
            actions=reads * (FORCED_STOP_CAP - 1),
            return_text="This is my last turn. I am writing the final report now.",
            spawn_result_note=TURN_LIMIT_NOTE,
        )
    elif ran_out is False:
        envelope = session_envelope(
            **common,
            actions=reads * (EARLY_ENDING_TURNS - 1),
            return_text="The report is written.\n[COMPLETE]",
        )
    else:
        envelope = session_envelope(**common, return_text=None)
    return SessionEvidence(role, repo, envelope, places, forced_stop=True)


def forced_stop_results(
    workspace: Path,
    role: str,
    *,
    both_ran_out_pairs: int,
    ended_before_cap: dict[str, int] | None = None,
) -> Path:
    """A results file of 24 pairs, `both_ran_out_pairs` of them forced stops that ran out of
    turns in both arms, plus `ended_before_cap[arm]` forced-stop sessions of that arm that
    ended before their cap; every other pair is a clean measured pair.

    The sessions that ended before their cap stand alone, one task each with no session of
    the other arm, so they complete no pair and leave every pair's outcomes as they were.
    """
    ended = ended_before_cap or {}
    assert 0 <= both_ran_out_pairs <= USABLE_PAIRS, both_ran_out_pairs
    assert set(ended) <= set(adherence_eval.ARMS), ended
    ran_out_ending = {"kind": "stopped_at_cap", "turns": FORCED_STOP_CAP, "cap": FORCED_STOP_CAP}
    early_ending = {
        "kind": "ended_on_its_own",
        "turns": EARLY_ENDING_TURNS,
        "cap": FORCED_STOP_CAP,
    }

    def session(arm: str, task_id: str, outcomes: dict, ending: dict | None) -> dict:
        status = adherence_eval._side_json(outcomes, False, FIRST_REQUEST_TOKENS[arm])
        if ending is not None:
            status = {**status, "role_ending": ending}
        return adherence_eval._session_record(role, arm, task_id, status)

    sessions = []
    for i in range(USABLE_PAIRS):
        forced = i < both_ran_out_pairs
        task_id = (
            f"{role}.forced-stop.ran-out-{i:02d}.early-stop" if forced else f"{role}.clean-{i:02d}"
        )
        sessions += [
            session(
                arm,
                task_id,
                RAN_OUT if forced else NOT_A_FORCED_STOP,
                ran_out_ending if forced else None,
            )
            for arm in adherence_eval.ARMS
        ]
    for arm, count in ended.items():
        sessions += [
            session(
                arm,
                f"{role}.forced-stop.ended-{arm}-{j:02d}.early-stop",
                ENDED_BEFORE_CAP,
                early_ending,
            )
            for j in range(count)
        ]
    measurement = RoleMeasurement(FORCED_STOP_CHECKS, (), FIRST_REQUEST_TOKENS)
    document = adherence_eval._results_document({role: measurement}, FlipSettings(), None)
    document["sessions"] = sessions
    path = workspace / "forced-stop-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@dataclass(frozen=True)
class RunOutCounts:
    ran_out: int
    ended_before_cap: int


def forced_stop_counts(report: str, role: str, arm: str) -> RunOutCounts:
    """The report's count, for one role and arm, of forced-stop sessions by how they ended."""
    line = re.compile(
        rf"^\s*forced-stop sessions, {arm} arm: (\d+) ran out of turns,"
        r" (\d+) ended before their cap\s*$",
        re.MULTILINE,
    )
    found = line.search(role_section(report, role))
    assert found, f"the report states no forced-stop counts for the {arm} arm of {role}"
    return RunOutCounts(int(found[1]), int(found[2]))


def differential_run_out_rate(report: str, role: str) -> float:
    """The report's differential run-out rate between the arms, in percentage points."""
    line = re.compile(
        r"^\s*differential run-out rate \(lean minus full\): (-?\d+(?:\.\d+)?) pp\s*$",
        re.MULTILINE,
    )
    found = line.search(role_section(report, role))
    assert found, f"the report states no differential run-out rate for {role}"
    return float(found[1])


# -- Allowance statements ------------------------------------------------------------------


@dataclass(frozen=True)
class AllowanceStatement:
    discordant: int
    allowance_pairs: int
    allowance_points: float
    margin_points: float


def allowance_statement(report: str, role: str, check: str) -> AllowanceStatement:
    """What the report states beside a mechanical check: discordance, allowance, margin."""
    line = re.compile(
        r"^\s*allowance: (\d+) pairs \((-?\d+(?:\.\d+)?) pp\) at (\d+) discordant pairs;"
        r" declared margin (\d+(?:\.\d+)?) pp\s*$",
        re.MULTILINE,
    )
    found = line.search(check_block(report, role, check))
    assert found, f"the report states no allowance for {check} under {role}"
    return AllowanceStatement(int(found[3]), int(found[1]), float(found[2]), float(found[4]))
