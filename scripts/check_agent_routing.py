#!/usr/bin/env python3
"""Does a request still route to the agent or skill that should handle it?

Delegation in Claude Code is decided from the agent listing (every agent's
`description`, rendered into the Agent tool) and the skill listing. Both are
text Praxion ships, and both are candidates for the startup-context diet, so
a description change needs a routing check before it lands: the saving is a
few hundred tokens, a misroute costs a pipeline. This is that check.

Method: one headless, single-turn ``claude -p`` session per case, carrying
the real listings, asked which agent or skill handles a request. The model
answers in text (``agent:<type>``, ``skill:<name>`` or ``none``); if it
reaches for the Agent or Skill tool instead, the call is denied by a
session-scoped permission rule and the denied call's target is read as the
answer. The reading is the model's *stated* route, a proxy for what it would
spawn; it moves with the listing text, which is what a description change
touches. Repeating a case (``--repeat``) shows how stable a route is.

Cases live in ``scripts/agent_routing_cases.json``: a request a user might
type, the expected route, and optional near-miss routes whose hit is reported
as a confusion rather than a plain miss. Expected routes compare by kind and
final name, so ``agent:praxion:verifier`` and ``agent:verifier`` agree.

``--record`` writes every case's route into ``.ai-state/agent_routing_baseline.json``;
``--compare`` reports the cases whose route differs from that record, which is
the before/after a description change wants. ``--plugin-dir`` measures a
checkout (the marketplace copy is disabled for the session).

``--session-oauth-token-file FILE`` bills every session to a subscription, as
``measure_startup_payload.py`` does: the file's ``claude setup-token`` token is
each session's only credential (no API key reaches it). It is read once, refused
before any session when the file is missing, unreadable or blank, and redacted
from everything printed.

``--max-total-usd X`` caps the whole run: each session's result carries
``total_cost_usd``, the run adds them up and starts no further session once the
sum has reached X. A case that did not get all of its ``--repeat`` askings is
reported as not asked and is not judged, so a capped run is never read as a pass
for cases it did not ask, nor as a regression. The cap is checked before each
session, so the last session can overshoot it by that session's own cost.

Every run reports its total spend: the sum of ``total_cost_usd`` over the sessions
it started. A session whose result states no cost counts as unknown, and the
total is then a lower bound; the summary and ``--json`` say how many.

Exit codes: 0 no miss, no unreadable answer and no route moved / 1 a miss, an
unreadable answer or (with ``--compare``) a moved route; a near-miss confusion is
reported, not failed / 2 usage error (including a non-positive cap or an unusable
token file), unreadable cases, missing CLI or a plugin-cache root / 3 the run
stopped at the ``--max-total-usd`` cap with cases not asked and nothing it did ask
failed. 3 is its own code because 1 means a routing regression and 2 means the
check could not run; a capped run is neither, and a pipeline that treats any
non-zero as red must still be able to tell an incomplete reading from a bad one.
A failure among the cases it did ask keeps the exit code 1.
Cost: one short request per case per repeat; the session prefix caches after
the first. Stdlib-only and 3.9-safe, as is the sibling ``measure_startup_payload``
it imports for the token and environment handling.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from measure_startup_payload import (
    MARKETPLACE_PLUGIN_KEY,
    TokenFileError,
    read_session_token,
    redact,
    session_environment,
)

SCRIPT_DIR = Path(__file__).resolve().parent
CASES_RELATIVE_PATH = ("scripts", "agent_routing_cases.json")
BASELINE_RELATIVE_PATH = (".ai-state", "agent_routing_baseline.json")
BASELINE_SCHEMA = 1
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_SECONDS = 120
NONE_ROUTE = "none"
CAPPED_EXIT_CODE = 3

FRAME = (
    "You are deciding how Praxion would handle the request below, using the agents and "
    "skills available to you in this session. Reply with exactly one line and nothing "
    "else: `agent:<subagent_type>` for the agent you would delegate to, `skill:<name>` "
    "for the skill you would invoke, or `none` if you would do it directly. Do not call "
    "any tool.\n\nRequest: "
)
_ANSWER_RE = re.compile(
    r"^\s*`?(?P<kind>agent|skill|none)(?::(?P<name>[A-Za-z0-9:_-]+))?`?\s*$", re.I
)


@dataclass(frozen=True)
class Route:
    """A normalised route: kind and final name (`agent`/`verifier`, `skill`/`roadmap-planning`, `none`)."""

    kind: str
    name: str = ""

    @classmethod
    def parse(cls, text: str) -> Route | None:
        for line in text.strip().splitlines():
            match = _ANSWER_RE.match(line)
            if match:
                kind = match.group("kind").lower()
                if kind == NONE_ROUTE:
                    return cls(NONE_ROUTE)
                name = (match.group("name") or "").lower().split(":")[-1]
                return cls(kind, name) if name else None
        return None

    def __str__(self) -> str:
        return self.kind if self.kind == NONE_ROUTE else f"{self.kind}:{self.name}"


@dataclass(frozen=True)
class Case:
    id: str
    request: str
    expect: Route
    near_miss: tuple = ()


def load_cases(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for raw in data:
        expect = Route.parse(raw["expect"])
        if expect is None:
            raise ValueError(
                f"{path}: case {raw.get('id')!r} has an unreadable expect {raw['expect']!r}"
            )
        near = []
        for item in raw.get("near_miss", []):
            route = Route.parse(item)
            if route is None:
                raise ValueError(
                    f"{path}: case {raw.get('id')!r} has an unreadable near_miss {item!r}"
                )
            near.append(route)
        cases.append(Case(str(raw["id"]), str(raw["request"]), expect, tuple(near)))
    ids = Counter(c.id for c in cases)
    dupes = sorted(i for i, n in ids.items() if n > 1)
    if dupes:
        raise ValueError(f"{path}: duplicate case ids {dupes}")
    return cases


# ---------------------------------------------------------------------------
# Pure: reading an answer, judging a case
# ---------------------------------------------------------------------------


def route_from_result(result: dict) -> Route | None:
    """The route a `--output-format json` result states, or the tool it tried to call."""
    stated = Route.parse(str(result.get("result") or ""))
    if stated is not None:
        return stated
    for denial in result.get("permission_denials") or []:
        tool = denial.get("tool_name")
        tool_input = denial.get("tool_input") or {}
        if tool == "Agent" and tool_input.get("subagent_type"):
            return Route("agent", str(tool_input["subagent_type"]).lower().split(":")[-1])
        if tool == "Skill" and tool_input.get("skill"):
            return Route("skill", str(tool_input["skill"]).lower().split(":")[-1])
    return None


def judge(case: Case, routes: list) -> dict:
    """Majority route across repeats, against the expectation."""
    answered = [r for r in routes if r is not None]
    if not answered:
        return {
            "id": case.id,
            "verdict": "unreadable",
            "route": None,
            "expect": str(case.expect),
            "agreement": 0.0,
        }
    majority, count = Counter(answered).most_common(1)[0]
    agreement = count / len(routes)
    if majority == case.expect:
        verdict = "pass"
    elif majority in case.near_miss:
        verdict = "confusion"
    else:
        verdict = "miss"
    return {
        "id": case.id,
        "verdict": verdict,
        "route": str(majority),
        "expect": str(case.expect),
        "agreement": round(agreement, 2),
        "routes": [str(r) if r else None for r in routes],
    }


def compare(baseline_routes: dict, today: list) -> list:
    """Cases whose majority route differs from the recorded one."""
    changed = []
    for row in today:
        before = baseline_routes.get(row["id"])
        if before is not None and before != row["route"]:
            changed.append(
                {"id": row["id"], "before": before, "now": row["route"], "verdict": row["verdict"]}
            )
    return changed


def build_invocation(case: Case, model: str, plugin_dir: str | None) -> list:
    settings = {"permissions": {"deny": ["Agent", "Skill", "Task"]}}
    if plugin_dir:
        settings["enabledPlugins"] = {MARKETPLACE_PLUGIN_KEY: False}
    argv = [
        "claude",
        "-p",
        FRAME + case.request,
        "--output-format",
        "json",
        "--model",
        model,
        "--max-turns",
        "1",
        "--settings",
        json.dumps(settings),
    ]
    if plugin_dir:
        argv += ["--plugin-dir", plugin_dir]
    return argv


# ---------------------------------------------------------------------------
# Impure: one session per case per repeat
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Answer:
    """What one session gave back: the route it stated and what it cost (None: not stated)."""

    route: Route | None
    cost_usd: float | None = None


@dataclass(frozen=True)
class RunResult:
    """Judged rows for the cases fully asked, the ids not, and what the sessions cost."""

    rows: list
    not_asked: list
    spent_usd: float
    sessions: int
    unknown_cost_sessions: int
    cap_usd: float | None

    @property
    def stopped_at_cap(self) -> bool:
        return bool(self.not_asked)

    def spend(self) -> dict:
        return {
            "total_usd": round(self.spent_usd, 6),
            "sessions": self.sessions,
            "unknown_cost_sessions": self.unknown_cost_sessions,
            "cap_usd": self.cap_usd,
        }


def cost_from_result(result: dict) -> float | None:
    cost = result.get("total_cost_usd")
    is_number = isinstance(cost, (int, float)) and not isinstance(cost, bool)
    return float(cost) if is_number and math.isfinite(cost) and cost >= 0 else None


def ask(
    case: Case, model: str, plugin_dir: str | None, cwd: Path, timeout: int, env: dict
) -> Answer:
    try:
        completed = subprocess.run(
            build_invocation(case, model, plugin_dir),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Answer(None)
    try:
        result = json.loads(completed.stdout)
    except ValueError:
        return Answer(None)
    result = result if isinstance(result, dict) else {}
    return Answer(route_from_result(result), cost_from_result(result))


def run(
    cases: list,
    *,
    model: str,
    plugin_dir: str | None,
    cwd: Path,
    timeout: int,
    repeat: int,
    env: dict,
    max_total_usd: float | None = None,
) -> RunResult:
    rows, not_asked = [], []
    spent, sessions, unknown = 0.0, 0, 0
    for case in cases:
        routes = []
        for _ in range(repeat):
            if max_total_usd is not None and spent >= max_total_usd:
                break
            answer = ask(case, model, plugin_dir, cwd, timeout, env)
            routes.append(answer.route)
            sessions += 1
            if answer.cost_usd is None:
                unknown += 1
            else:
                spent += answer.cost_usd
        if len(routes) == repeat:
            rows.append(judge(case, routes))
        else:
            not_asked.append(case.id)
    return RunResult(rows, not_asked, spent, sessions, unknown, max_total_usd)


def describe_spend(outcome: RunResult) -> list:
    """The summary lines about money: the total, what is unknown about it, and a stop at the cap."""
    line = f"spend: ${outcome.spent_usd:.4f} over {outcome.sessions} sessions"
    if outcome.unknown_cost_sessions:
        line += f" ({outcome.unknown_cost_sessions} reported no cost: the total is a lower bound)"
    lines = [line]
    if outcome.stopped_at_cap:
        lines.append(
            f"stopped at the --max-total-usd cap of ${outcome.cap_usd:g}; "
            f"not asked ({len(outcome.not_asked)}): {', '.join(outcome.not_asked)}"
        )
    return lines


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _parse_args(argv: list | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cases", help="case file (default scripts/agent_routing_cases.json)")
    parser.add_argument("--only", nargs="*", help="run only these case ids")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--repeat", type=int, default=1, help="askings per case; majority wins")
    parser.add_argument("--plugin-dir", help="route against this plugin checkout")
    parser.add_argument("--cwd", help="directory to ask from (default: the repo root)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--record", action="store_true", help="write routes into the baseline")
    parser.add_argument(
        "--compare", action="store_true", help="report routes that changed since the baseline"
    )
    parser.add_argument(
        "--baseline", help="baseline path (default .ai-state/agent_routing_baseline.json)"
    )
    parser.add_argument(
        "--session-oauth-token-file",
        type=Path,
        help="a `claude setup-token` file: every session bills its subscription, with no API key",
    )
    parser.add_argument(
        "--max-total-usd",
        type=float,
        help="start no further session once the sessions' total cost has reached this",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo-root")
    return parser.parse_args(argv)


def main(argv: list | None = None) -> int:
    args = _parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if repo_root is None or is_plugin_cache_path(repo_root):
        print(
            "check_agent_routing: no usable repository root (a plugin-cache root is refused)",
            file=sys.stderr,
        )
        return 2
    if shutil.which("claude") is None:
        print("check_agent_routing: the `claude` CLI is not on PATH", file=sys.stderr)
        return 2
    cases_path = Path(args.cases) if args.cases else repo_root.joinpath(*CASES_RELATIVE_PATH)
    try:
        cases = load_cases(cases_path)
    except (OSError, ValueError, KeyError) as error:
        print(f"check_agent_routing: {error}", file=sys.stderr)
        return 2
    if args.only:
        wanted = set(args.only)
        cases = [c for c in cases if c.id in wanted]
    if args.repeat < 1:
        print("check_agent_routing: --repeat must be at least 1", file=sys.stderr)
        return 2
    if args.max_total_usd is not None and not (
        math.isfinite(args.max_total_usd) and args.max_total_usd > 0
    ):
        print("check_agent_routing: --max-total-usd must be a positive number", file=sys.stderr)
        return 2
    token = None
    if args.session_oauth_token_file is not None:
        try:
            token = read_session_token(args.session_oauth_token_file)
        except TokenFileError as error:
            print(f"check_agent_routing: {error}", file=sys.stderr)
            return 2

    cwd = Path(args.cwd).resolve() if args.cwd else repo_root
    plugin_dir = str(Path(args.plugin_dir).resolve()) if args.plugin_dir else None
    outcome = run(
        cases,
        model=args.model,
        plugin_dir=plugin_dir,
        cwd=cwd,
        timeout=args.timeout,
        repeat=args.repeat,
        env=session_environment(os.environ, token),
        max_total_usd=args.max_total_usd,
    )
    rows = outcome.rows

    baseline_path = (
        Path(args.baseline) if args.baseline else repo_root.joinpath(*BASELINE_RELATIVE_PATH)
    )
    baseline = _load_baseline(baseline_path)
    changed = compare(baseline.get("routes", {}), rows) if args.compare else None
    if args.record:
        routes = dict(baseline.get("routes", {}))
        routes.update({row["id"]: row["route"] for row in rows if row["route"] is not None})
        baseline.update(
            {
                "schema": BASELINE_SCHEMA,
                "recorded": date.today().isoformat(),
                "model": args.model,
                "routes": routes,
            }
        )
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(redact(_render(outcome, changed, as_json=args.json), token))
    # A confusion is a known near miss, reported and tracked; what fails the check
    # is a plain miss, an unreadable answer, or a route that moved since the baseline.
    # A cap that left cases unasked is a third thing, so it never shares code 1 or 2.
    failing = any(row["verdict"] in {"miss", "unreadable"} for row in rows)
    if failing or changed:
        return 1
    return CAPPED_EXIT_CODE if outcome.stopped_at_cap else 0


def _render(outcome: RunResult, changed: list | None, *, as_json: bool) -> str:
    rows = outcome.rows
    if as_json:
        return json.dumps(
            {
                "cases": rows,
                "changed": changed,
                "spend": outcome.spend(),
                "stopped_at_cap": outcome.stopped_at_cap,
                "not_asked": outcome.not_asked,
            },
            indent=2,
        )
    lines = [
        f"  {row['verdict']:<10} {row['id']:<34} {str(row['route']):<40} expected {row['expect']}  ({row['agreement']:.0%})"
        for row in rows
    ]
    counts = Counter(row["verdict"] for row in rows)
    lines.append("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    lines += describe_spend(outcome)
    if changed is not None:
        lines.append(
            "changed since the baseline:" if changed else "no route changed since the baseline"
        )
        lines += [
            f"  {row['id']:<34} {row['before']} -> {row['now']}  ({row['verdict']})"
            for row in changed
        ]
    return "\n".join(lines)


def _load_baseline(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    sys.exit(main())
