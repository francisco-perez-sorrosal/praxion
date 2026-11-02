#!/usr/bin/env python3
"""Check from recorded transcripts that each subagent spawn ran where its definition routes it.

A spawn that passes no ``model`` runs at its definition's ``model:`` floor, which the parity gate
holds equal to the routing rule's tier table. This reads Claude Code's recorded transcripts and
classifies every ``praxion:`` spawn:

- ``floor``: it ran on its floor's model family and nothing in its request contradicts that.
- ``override``: it ran on a sanctioned deviation the routing rule's directive lists, or the
  step-loop driver issued it.
- ``unexplained``: it ran off its floor with no sanctioned reason; the check fails on these.
- ``unknown``: the transcripts cannot say (no recorded model, an unknown role, or a spawn off its
  floor in a session whose recorded models leave a forced model possible); reported, not failed.

Rules that refine the reading of production transcripts:

- A spawn the step-loop driver issued is sanctioned. Its prompt's first line is ``Task slug:
  <slug>`` and a later line starts with ``Spawn request: <id>``; the driver applies the plan's
  routing (step tier hints, light review at ``sonnet``), so the spawn reads ``override`` with the
  reason "issued by the step-loop driver (<id>)".
- A prompt marker (``Mode: light-review``, ``tier: H``, ``routine``, ...) counts when it appears as
  a whole phrase anywhere in the prompt (mid-line, indented, negated or inside backticks); one held
  only inside a longer word (``tier: High``) never sanctions a deviation.
- The transcripts do not record whether ``CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`` was set, and under
  it Claude cannot pass a per-spawn ``model`` (code.claude.com/docs/en/sub-agents.md). So when no
  spawn of a session passed a ``model`` and the session is a lone spawn, or its spawns' floors
  differ while all ran on one family, a forced model cannot be excluded: a spawn off its floor
  reads ``unknown`` and one on its floor reads ``floor``. Any other session, including one where
  any spawn passed a ``model`` and one on a single model whose floors agree, is judged spawn by
  spawn.
- Aliases compare by family: ``haiku`` matches any ``claude-haiku-*``, ``sonnet`` any
  ``claude-sonnet-*``, ``opus`` any ``claude-opus-*`` and ``fable`` any ``claude-fable-*``. No alias
  maps to a single version: ``haiku`` is Haiku 5.5 on the Anthropic API and Haiku 4.5 elsewhere, and
  it is the model the L tier passes.

Each Agent call is one spawn, keyed on its ``tool_use`` id (``spawn_transcripts.py``).

Advisory and re-runnable, not a commit gate (transcripts are local and unversioned). Its reader is
the verifier of any routing change. It starts no model session.

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

# A family is an alias; its models are the `claude-<alias>-*` names.
FAMILIES = ("opus", "sonnet", "haiku", "fable")


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
        Deviation("haiku", requires="tier: L"),
    ),
}


def model_family(model: str) -> str:
    """The family a model name belongs to; a name of no known family stands for itself."""
    name = model.strip().lower()
    for family in FAMILIES:
        if name == family or name.startswith(f"claude-{family}-"):
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
    if ran == model_family(floor) and not _requested_other_than(spawn, floor):
        return "floor", f"ran on {spawn.ran_model}, the {floor} floor"
    if spawn.driver_request is not None:
        return "override", f"issued by the step-loop driver ({spawn.driver_request})"
    if _sanctioned(spawn):
        return "override", f"ran on {spawn.ran_model}, a listed deviation"
    if _forcing_cannot_be_excluded(session_spawns, floors):
        return (
            "unknown",
            f"ran on {spawn.ran_model}, off the {floor} floor; a forced model cannot be excluded",
        )
    return (
        "unexplained",
        f"ran on {spawn.ran_model}, off the {floor} floor, with no listed deviation",
    )


def _requested_other_than(spawn: Spawn, floor: str) -> bool:
    requested = spawn.requested_model
    return requested is not None and model_family(requested) != model_family(floor)


def _forcing_cannot_be_excluded(session_spawns: list[Spawn], floors: dict[str, str]) -> bool:
    """Whether the session's recorded models leave a forcing setting possible: no spawn passed a
    model, and either there is a lone spawn or the spawns' floors differ while all ran on one
    family."""
    if any(s.requested_model is not None for s in session_spawns):
        return False
    if len(session_spawns) == 1:
        return True
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
