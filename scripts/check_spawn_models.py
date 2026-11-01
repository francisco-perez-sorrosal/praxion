#!/usr/bin/env python3
"""Check from recorded transcripts that each subagent spawn ran where its definition routes it.

A spawn that passes no ``model`` runs at its definition's ``model:`` floor, which the parity gate
holds equal to the routing rule's tier table. This reads Claude Code's recorded transcripts and
classifies every ``praxion:`` spawn:

- ``floor``: it ran on its floor's model family and nothing in its request contradicts that.
- ``override``: it ran on a sanctioned deviation the routing rule's directive lists, or the whole
  session ran on one model while its spawns' floors differ (the operator kill switch).
- ``unexplained``: it ran off its floor with no sanctioned reason; the check fails on these.
- ``unknown``: the transcripts cannot say (no recorded model, an unknown role, or the lone spawn
  of its session off its floor, where the kill switch cannot be told apart); reported, not failed.

Advisory and re-runnable, not a commit gate (transcripts are local and unversioned). Its readers
are the verifier of any routing change and the sentinel's routing audit. It starts no model
session.

Usage: python3 scripts/check_spawn_models.py <transcripts-dir> [--repo-root DIR] [--json]
Exit codes: 0 no spawn unexplained, 1 some spawn unexplained, 2 input error (the transcripts
directory or the agent definitions cannot be read).
Stdlib-only and Python 3.9-safe, since it runs under the ambient interpreter.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _repo_root import resolve_repo_root  # noqa: E402
from spawn_transcripts import Spawn, read_floors, read_spawns  # noqa: E402

Verdict = Literal["floor", "override", "unexplained", "unknown"]
VERDICTS: tuple[str, ...] = get_args(Verdict)
SCHEMA_VERSION = 1
INPUT_ERROR = 2

LOW_TIER_PIN = "claude-haiku-4-5"
# The bare `haiku` alias resolves to Haiku 3.5, a different family from the pin, so the two never
# match each other.
_ALIAS_FAMILIES = {"opus": "opus", "sonnet": "sonnet", "haiku": "haiku-3.5"}
_FAMILY_PREFIXES = (
    ("claude-opus-", "opus"),
    ("claude-sonnet-", "sonnet"),
    (f"{LOW_TIER_PIN}-", LOW_TIER_PIN),
    ("claude-3-5-haiku-", "haiku-3.5"),
)


@dataclass(frozen=True)
class Deviation:
    """One per-spawn model the routing directive lists. ``model`` None means any model. The
    prompt marker ``requires`` must be present and ``forbids`` absent."""

    model: str | None
    requires: str | None = None
    forbids: str | None = None


# The directive's closed deviation list, by role. A new deviation lands here AND in the bullet list
# of the Orchestrator directive in rules/swe/agent-model-routing-resident.md (and in its parent
# rule's directive paragraph); a deviation in one place only reads as unexplained here or as
# unlisted there. The consultant's `sonnet` floor needs no entry: running on it reads as `floor`.
SANCTIONED: dict[str, tuple[Deviation, ...]] = {
    "researcher": (Deviation(model=None),),
    "discipline-consultant": (Deviation("opus", forbids="routine"),),
    "test-engineer": (Deviation("opus", requires="Mode: acceptance-design"),),
    "verifier": (Deviation("sonnet", requires="Mode: light-review"),),
    "implementer": (
        Deviation("opus", requires="tier: H"),
        Deviation(LOW_TIER_PIN, requires="tier: L"),
    ),
}


def model_family(model: str) -> str:
    """The family a model name belongs to; a name of no known family stands for itself."""
    name = model.strip().lower()
    if name in _ALIAS_FAMILIES:
        return _ALIAS_FAMILIES[name]
    if name == LOW_TIER_PIN:
        return LOW_TIER_PIN
    for prefix, family in _FAMILY_PREFIXES:
        if name.startswith(prefix):
            return family
    return name


def classify(
    spawn: Spawn, session_spawns: list[Spawn], floors: dict[str, str]
) -> tuple[Verdict, str]:
    """The verdict on one spawn and the reason, from the spawn, its session's spawns (itself
    included) and the definitions' floors."""
    floor = floors.get(spawn.role)
    if spawn.ran_model is None:
        return "unknown", "no model recorded for the spawn"
    if floor is None:
        return "unknown", f"no definition declares a model for role {spawn.role}"
    ran = model_family(spawn.ran_model)
    if _runs_under_kill_switch(session_spawns, floors):
        return "override", f"every spawn of the session ran on {ran} (operator kill switch)"
    if ran == model_family(floor) and not _requested_other_than(spawn, floor):
        return "floor", f"ran on {spawn.ran_model}, the {floor} floor"
    if _sanctioned(spawn):
        return "override", f"ran on {spawn.ran_model}, a listed deviation"
    if len(session_spawns) == 1:
        return (
            "unknown",
            f"ran on {spawn.ran_model}, off the {floor} floor; kill switch not excluded",
        )
    return (
        "unexplained",
        f"ran on {spawn.ran_model}, off the {floor} floor, with no listed deviation",
    )


def _requested_other_than(spawn: Spawn, floor: str) -> bool:
    requested = spawn.requested_model
    return requested is not None and model_family(requested) != model_family(floor)


def _runs_under_kill_switch(session_spawns: list[Spawn], floors: dict[str, str]) -> bool:
    """Two or more spawns whose floors differ that all ran on one family: no routing explains
    that, an operator pin does."""
    known = [s for s in session_spawns if s.ran_model is not None and s.role in floors]
    floor_families = {model_family(floors[s.role]) for s in known}
    ran_families = {model_family(s.ran_model) for s in known if s.ran_model is not None}
    return len(floor_families) >= 2 and len(ran_families) == 1


def _sanctioned(spawn: Spawn) -> bool:
    """Whether the spawn requested a listed deviation, and ran on what it requested."""
    requested, ran = spawn.requested_model, spawn.ran_model
    if requested is None or ran is None or model_family(requested) != model_family(ran):
        return False
    return any(
        (deviation.model is None or model_family(deviation.model) == model_family(requested))
        and (deviation.requires is None or deviation.requires in spawn.prompt_markers)
        and (deviation.forbids is None or deviation.forbids not in spawn.prompt_markers)
        for deviation in SANCTIONED.get(spawn.role, ())
    )


def judge(spawns: list[Spawn], floors: dict[str, str]) -> list[tuple[Spawn, Verdict, str]]:
    """Every spawn with its verdict and reason, in the order given."""
    by_session: dict[str, list[Spawn]] = {}
    for spawn in spawns:
        by_session.setdefault(spawn.session, []).append(spawn)
    return [(spawn, *classify(spawn, by_session[spawn.session], floors)) for spawn in spawns]


def count(judged: list[tuple[Spawn, Verdict, str]]) -> dict[str, int]:
    counts = dict.fromkeys(VERDICTS, 0)
    for _, verdict, _ in judged:
        counts[verdict] += 1
    return counts


def render_text(judged: list[tuple[Spawn, Verdict, str]]) -> str:
    lines = [f"{s.agent_id}  {s.role}  {verdict}  {reason}" for s, verdict, reason in judged]
    counts = count(judged)
    lines.append(f"{len(judged)} spawns: " + ", ".join(f"{v}={counts[v]}" for v in VERDICTS))
    return "\n".join(lines)


def render_json(judged: list[tuple[Spawn, Verdict, str]]) -> str:
    spawns = [
        {
            "session": s.session,
            "agent_id": s.agent_id,
            "role": s.role,
            "requested_model": s.requested_model,
            "ran_model": s.ran_model,
            "verdict": verdict,
            "reason": reason,
        }
        for s, verdict, reason in judged
    ]
    return json.dumps({"schema": SCHEMA_VERSION, "spawns": spawns, "counts": count(judged)})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("transcripts_dir", type=Path)
    parser.add_argument("--repo-root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    try:
        if not args.transcripts_dir.is_dir():
            raise OSError(f"{args.transcripts_dir} is not a directory")
        floors = read_floors(repo_root)
        if not floors:
            raise OSError(f"no agent definition with a model under {repo_root / 'agents'}")
        judged = judge(read_spawns(args.transcripts_dir), floors)
    except OSError as error:
        print(f"spawn models: cannot read the inputs: {error}", file=sys.stderr)
        return INPUT_ERROR
    print(render_json(judged) if args.json else render_text(judged))
    return 1 if count(judged)["unexplained"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
