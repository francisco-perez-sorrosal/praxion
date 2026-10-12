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

Exit codes: 0 no miss, no unreadable answer and no route moved / 1 a miss, an
unreadable answer or (with ``--compare``) a moved route; a near-miss confusion is
reported, not failed / 2 usage error, unreadable cases, missing CLI or a plugin-cache root.
Cost: one short request per case per repeat; the session prefix caches after
the first. Stdlib-only and 3.9-safe.
"""

from __future__ import annotations

import argparse
import json
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
from measure_startup_payload import MARKETPLACE_PLUGIN_KEY

SCRIPT_DIR = Path(__file__).resolve().parent
CASES_RELATIVE_PATH = ("scripts", "agent_routing_cases.json")
BASELINE_RELATIVE_PATH = (".ai-state", "agent_routing_baseline.json")
BASELINE_SCHEMA = 1
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_SECONDS = 120
NONE_ROUTE = "none"

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


def ask(case: Case, model: str, plugin_dir: str | None, cwd: Path, timeout: int) -> Route | None:
    try:
        completed = subprocess.run(
            build_invocation(case, model, plugin_dir),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=dict(os.environ),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    try:
        result = json.loads(completed.stdout)
    except ValueError:
        return None
    return route_from_result(result if isinstance(result, dict) else {})


def run(
    cases: list, *, model: str, plugin_dir: str | None, cwd: Path, timeout: int, repeat: int
) -> list:
    rows = []
    for case in cases:
        routes = [ask(case, model, plugin_dir, cwd, timeout) for _ in range(repeat)]
        rows.append(judge(case, routes))
    return rows


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

    cwd = Path(args.cwd).resolve() if args.cwd else repo_root
    plugin_dir = str(Path(args.plugin_dir).resolve()) if args.plugin_dir else None
    rows = run(
        cases,
        model=args.model,
        plugin_dir=plugin_dir,
        cwd=cwd,
        timeout=args.timeout,
        repeat=args.repeat,
    )

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

    if args.json:
        print(json.dumps({"cases": rows, "changed": changed}, indent=2))
    else:
        for row in rows:
            print(
                f"  {row['verdict']:<10} {row['id']:<34} {str(row['route']):<40} expected {row['expect']}  ({row['agreement']:.0%})"
            )
        counts = Counter(row["verdict"] for row in rows)
        print("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if changed is not None:
            print(
                "changed since the baseline:" if changed else "no route changed since the baseline"
            )
            for row in changed:
                print(f"  {row['id']:<34} {row['before']} -> {row['now']}  ({row['verdict']})")
    # A confusion is a known near miss, reported and tracked; what fails the check
    # is a plain miss, an unreadable answer, or a route that moved since the baseline.
    failing = any(row["verdict"] in {"miss", "unreadable"} for row in rows)
    return 1 if failing or changed else 0


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
