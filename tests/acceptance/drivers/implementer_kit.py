"""Driver for the implementer's adherence eval kit: its tasks, fixtures and convention check.

Reached through the eval's existing seams (`adherence_eval.run_in_eval`, the pins of
`lean_scoring`): `tasks.task_ids`, `tasks.producible_task_count`, `tasks.generate(role,
seed, n)` whose specs carry `task_id`, `template_id`, `fixture_id`, `variant`, `slug`,
`main_prompt` and `project_convention` (`text`, `check`), `tasks.build_scratch_repo(spec,
dest, None)`, `catalog.check_catalog(role)`, and `grade.evidence_from_recording` with its
`forced_stop` fact.

Bound here, because the specification or the base commit fixes them:

- a project convention's observance is the line `Filed under the project house rules.`
  in a file the session wrote (the pilot roles' convention);
- the kit as it stood at the base commit is frozen in
  `tests/acceptance/fixtures/implementer_kit_before.json` (`snapshot()` at that commit):
  every task's identity, prompt, template, fixture and variant, each fixture file's
  digest, and the catalog's checks. The fixture's own `CLAUDE.md` is kept apart, since the
  convention is stated there.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import run_in_eval

ROLE = "implementer"
SEED = adherence_eval.SEED
OBSERVANCE_LINE = "Filed under the project house rules."
INSTRUCTION_FILE = "CLAUDE.md"
FROZEN = Path(__file__).resolve().parents[1] / "fixtures" / "implementer_kit_before.json"

_SNAPSHOT_CODE = """
import hashlib, json, sys
from pathlib import Path
from praxion_evals.adherence import catalog, tasks

p = json.load(sys.stdin)
role, seed = p["role"], p["seed"]
count = tasks.producible_task_count(role, seed)
out = {"task_ids": tasks.task_ids(role, seed), "producible": count, "tasks": [],
       "checks": [[c.name, c.kind] for c in catalog.check_catalog(role)]}
for i, spec in enumerate(tasks.generate(role, seed, count)):
    dest = Path(p["into"]) / f"{i:03d}"
    tasks.build_scratch_repo(spec, dest, None)
    files = {}
    for path in sorted(dest.rglob("*")):
        rel = path.relative_to(dest).as_posix()
        if path.is_file() and rel.split("/")[0] != ".git":
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    convention = spec.project_convention
    out["tasks"].append({
        "task_id": spec.task_id, "template_id": spec.template_id, "fixture_id": spec.fixture_id,
        "variant": repr(spec.variant), "slug": spec.slug, "main_prompt": spec.main_prompt,
        "files": files,
        "convention": None if convention is None else {"text": convention.text, "check": convention.check},
        "instructions": (dest / "CLAUDE.md").read_text() if (dest / "CLAUDE.md").is_file() else None,
        "texts": {rel: (dest / rel).read_text(errors="replace") for rel in files},
    })
print(json.dumps(out))
"""


def snapshot() -> dict:
    """The implementer's kit as the eval generates it now, for seed `SEED`."""
    with tempfile.TemporaryDirectory(prefix="implementer-kit-") as scratch:
        return run_in_eval(_SNAPSHOT_CODE, {"role": ROLE, "seed": SEED, "into": scratch})


def frozen() -> dict:
    return json.loads(FROZEN.read_text(encoding="utf-8"))


def without_instruction_file(task: dict) -> dict:
    """A task's identity and fixture with its `CLAUDE.md` and convention left out."""
    files = {k: v for k, v in task["files"].items() if k != INSTRUCTION_FILE}
    kept = ("task_id", "template_id", "fixture_id", "variant", "slug", "main_prompt")
    return {**{k: task[k] for k in kept}, "files": files}


def convention_check() -> str:
    """The implementer's convention check, as its first task's convention names it."""
    convention = snapshot()["tasks"][0]["convention"]
    assert convention is not None, "the implementer's first task states no project convention"
    return convention["check"]


_FIRST_FIXTURE_CODE = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import tasks

p = json.load(sys.stdin)
spec = tasks.generate(p["role"], p["seed"], 1)[0]
commit = tasks.build_scratch_repo(spec, Path(p["dest"]), None)
convention = spec.project_convention
print(json.dumps({"commit": commit, "slug": spec.slug,
                  "check": None if convention is None else convention.check}))
"""


def convention_outcome(*, wrote_line: bool, forced_stop: bool, role: str = ROLE) -> str:
    """The convention check's outcome on a session of `role`'s first task that wrote one
    document, holding the observance line or not, in a task that stopped the role early
    or not."""
    with tempfile.TemporaryDirectory(prefix="convention-session-") as scratch:
        root = Path(scratch)
        built = run_in_eval(
            _FIRST_FIXTURE_CODE, {"role": role, "seed": SEED, "dest": str(root / "repo")}
        )
        assert built["check"] is not None, f"the {role}'s task states no project convention"
        repo = adherence_eval.ScratchRepo(root / "repo", built["commit"])
        body = "# Notes\n\nThe step is done.\n" + (f"\n{OBSERVANCE_LINE}\n" if wrote_line else "")
        notes = repo.put(f".ai-work/{built['slug']}/STEP_NOTES.md", body)
        places = adherence_eval.session_places(root)
        envelope = adherence_eval.session_envelope(
            role=role,
            cwd=repo.root,
            plugin_copy=places.plugin_copy,
            actions=[adherence_eval.write(notes, body)],
            return_text="Done; notes in the task directory.\n[COMPLETE]",
        )
        evidence = adherence_eval.SessionEvidence(
            role, repo, envelope, places, slug=built["slug"], forced_stop=forced_stop
        )
        graded = adherence_eval.grade(evidence, [built["check"]])
    if graded.errored_kind is not None:
        return f"errored: {graded.errored_kind}"
    return graded.outcome(built["check"]).kind
