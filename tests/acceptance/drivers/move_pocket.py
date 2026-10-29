"""The one seam from the root tests into the move subpackage of the eval pocket.

The subpackage lives in the evaluation project (Python 3.13), which this suite's interpreter
does not import. Each library call a scenario makes is a short code string run there through
`adherence_eval.run_in_eval` (`uv run --python 3.13 --project eval python -c`): a JSON request
in on stdin, one JSON document out on the last stdout line. Results are frozen dataclasses the
code serialises with `dataclasses.asdict`; the shapes the drivers read back are:

- `arms.build` returns an arm set `{"arms": {arm: {"copy", "changes"}}}`, each change a
  `{"path", "sha256"}` mapping or a `[path, sha256]` pair (a removal carries no digest), or an
  arm refusal `{"reason"}`; the two are told apart by `refused`. A declaration the loader
  refuses (`declaration.DeclarationError`, raised before `arms.build` runs) reads the same way:
  `{"refused": true, "reason": <the loader's message>}`.
- `arms.check_copy` returns the refusal's message or None.
- `kit_git.tasks` returns the tasks `{"task_id", "fixture", "fixture_kind", "wording_variant",
  "wording", "named_files", "planted_credential"}`; `kit_git.build_fixture` returns the
  repository's path.

A request names the declaration by `declaration` (a written file) or `move` (the kit's own).
`call_with_declaration` runs code against that declaration; `call_in_pocket` runs code that needs
none (the verdict and the report read a measurement alone). The shapes of the other calls the
drivers make (the take proof, the trigger record, the end-state grade, the verdict) are pinned
in the header of `move_scoring`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests.acceptance.drivers import adherence_eval, move_shared_runs

POCKET_TIMEOUT_SECONDS = 600  # a build runs both rules exports over the lean copy

_PRELUDE = """
import dataclasses, json, sys
from pathlib import Path
request = json.load(sys.stdin)
def emit(value):
    print(json.dumps(value, default=str))
"""

_LOAD = (
    _PRELUDE
    + """
from praxion_evals.adherence.moves import declaration
declared = (
    declaration.load(Path(request["declaration"]))
    if request["declaration"]
    else declaration.kit(request["move"])
)
"""
)

# A declaration the loader refuses is the arm build's refusal too (the boundary refuses it before
# `arms.build` runs). Only the declaration module's own error is caught: anything else raises.
_LOAD_REFUSING = (
    _PRELUDE
    + """
from praxion_evals.adherence.moves import declaration
try:
    declared = (
        declaration.load(Path(request["declaration"]))
        if request["declaration"]
        else declaration.kit(request["move"])
    )
except declaration.DeclarationError as refusal:
    emit({"refused": True, "reason": str(refusal)})
    sys.exit(0)
"""
)

_BUILD_ARMS = """
from praxion_evals.adherence.moves import arms
built = arms.build(declared, Path(request["checkout"]), Path(request["workspace"]))
emit({"refused": type(built).__name__ == "ArmRefusal", **dataclasses.asdict(built)})
"""

_CHECK_COPY = """
from praxion_evals.adherence.moves import arms
emit(arms.check_copy(declared, request["arm"], Path(request["copy"]), Path(request["checkout"])))
"""

_TASKS = """
from praxion_evals.adherence.moves import kit_git
emit([dataclasses.asdict(task) for task in kit_git.tasks(declared, request["seed"])])
"""

_BUILD_FIXTURE = """
from praxion_evals.adherence.moves import kit_git
task = next(t for t in kit_git.tasks(declared, request["seed"]) if t.task_id == request["task_id"])
emit(str(kit_git.build_fixture(declared, task, Path(request["where"]))))
"""


def build_arms(move: str, declaration: Path | None, checkout: Path, workspace: Path) -> Any:
    """Build the arms once per test session for these inputs; each caller gets its own copies.

    The build is keyed on the move, the declaration file's content, and the checkout's content and
    history; a caller that finds it built is handed copies of the arm trees under its own
    `workspace` and a result naming them.
    """
    request = {"checkout": str(checkout), "workspace": str(workspace)}

    def build() -> Any:
        return call_with_declaration(_BUILD_ARMS, move, declaration, request, load=_LOAD_REFUSING)

    identity = move_shared_runs.git_identity(checkout, adherence_eval._git)
    if identity is None:
        return build()
    paths = {"checkout": checkout, "workspace": workspace}
    if declaration is not None:
        paths["declaration"] = declaration
    declared = None if declaration is None else hashlib.sha256(declaration.read_bytes()).hexdigest()
    return move_shared_runs.share(
        checkout,
        {"build_arms": move, "declaration": declared, "repository": identity},
        move_shared_runs.Roles(paths),
        {
            "checkout": move_shared_runs.Watch(checkout, skip_git=True),
            "workspace": move_shared_runs.Watch(workspace, mirrors=checkout),
        },
        build,
        unshareable_if_changed=lambda: move_shared_runs.git_state(checkout, adherence_eval._git),
    )


def check_copy(
    move: str, declaration: Path | None, arm: str, copy: Path, checkout: Path
) -> str | None:
    request = {"arm": arm, "copy": str(copy), "checkout": str(checkout)}
    return call_with_declaration(_CHECK_COPY, move, declaration, request)


def tasks(move: str, declaration: Path | None, seed: int) -> list[Mapping[str, Any]]:
    return call_with_declaration(_TASKS, move, declaration, {"seed": seed})


def build_fixture(
    move: str, declaration: Path | None, seed: int, task_id: str, where: Path
) -> Path:
    request = {"seed": seed, "task_id": task_id, "where": str(where)}
    return Path(call_with_declaration(_BUILD_FIXTURE, move, declaration, request))


def call_with_declaration(
    code: str,
    move: str,
    declaration: Path | None,
    request: Mapping[str, Any],
    *,
    load: str = _LOAD,
) -> Any:
    """Run `code` with `declared` loaded: the file at `declaration`, or `move`'s own kit."""
    payload = {"move": move, "declaration": None if declaration is None else str(declaration)}
    return adherence_eval.run_in_eval(
        load + code, {**payload, **request}, timeout=POCKET_TIMEOUT_SECONDS
    )


def call_in_pocket(code: str, request: Mapping[str, Any]) -> Any:
    """Run `code` that needs no declaration; `request` and `emit` are in scope."""
    return adherence_eval.run_in_eval(_PRELUDE + code, request, timeout=POCKET_TIMEOUT_SECONDS)
