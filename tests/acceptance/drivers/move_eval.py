"""Driver for the main-session half of the adherence eval: moves, their arms and their kits.

A *move* is a declared relocation of one rule's text out of session-start residency into
other channels. Its arms are `full` (today's delivery), `lean` (the move) and `floor` (no line
of the rule in any channel). The operator runs a move through the same console entry that
measures a spawned role, `praxion-evals-adherence`; each task is one headless main session in
a scratch fixture repository.

Bound here, because the specification or the base commit fixes them:

- the console entry and its existing options `--dry-run`, `--report`, `--continue`,
  `--close`, `--reason`, `--reindex`, `--max-tasks` and `--stop-count`, reached as the
  adherence driver reaches it (`adherence_eval`), with a `claude` stand-in first on `PATH`;
- the first move's name, `git-conventions`, its rule `rules/swe/vcs/git-conventions.md`, the
  second move's name, `adr-conventions`, and the arm names `full`, `lean` and `floor`;
- the defaults a dry run prices: 24 tasks paired (48 sessions) and 8 floor sessions;
- what the Cursor rule export and the Codex rules bridge reach of a rule, measured by running
  each exporter (`cursor/config/export-cursor-rules.py ROOT OUT`,
  `codex/config/export-codex-rules-bridge.py --repo-root ROOT --out-dir OUT`) over a tree;
- a narrowed checkout: only the files a move run and these tests read, built once per
  process from a declared read set and copied for each scenario.

Unbound until a binding step ties them to the designed surface (each raises
`UnboundDriverError` with the assumption's words): how the operator names a move, picks its
floor or paired run and cites a floor run; the dry run's printed form for a move; the move
results file's fields; building and checking a move's arms; the move declarations and their
known-bad variants; and the generated task list and its fixtures.
"""

from __future__ import annotations

import atexit
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import (
    DUMMY_CREDENTIAL,
    EVAL_PROJECT,
    EVAL_PYTHON,
    SEED,
    CliResult,
)

REPO_ROOT = adherence_eval.REPO_ROOT
FIRST_MOVE = "git-conventions"
SECOND_MOVE = "adr-conventions"
MOVED_RULES = {
    FIRST_MOVE: "rules/swe/vcs/git-conventions.md",
    SECOND_MOVE: "rules/swe/adr-conventions.md",
}
CURSOR_RULE_EXPORT = {
    FIRST_MOVE: "swe/vcs/git-conventions.md",
    SECOND_MOVE: "swe/adr-conventions.md",
}
CODEX_RULE_ID = {
    FIRST_MOVE: "rules::swe::vcs::git-conventions",
    SECOND_MOVE: "rules::swe::adr-conventions",
}
Arm = Literal["full", "lean", "floor"]
MOVE_ARMS: tuple[Arm, ...] = ("full", "lean", "floor")
PAIRED_ARMS: tuple[Arm, ...] = ("full", "lean")
FixtureKind = Literal["managed", "unmanaged"]
FIXTURE_KINDS: tuple[FixtureKind, ...] = ("managed", "unmanaged")
RunKind = Literal["floor", "paired"]
Host = Literal["cursor", "codex"]
HOSTS: tuple[Host, ...] = ("cursor", "codex")

DEFAULT_PAIRED_TASKS = 24
DEFAULT_FLOOR_SESSIONS = 8
DEFAULT_TOTAL_SESSIONS = 56
FLOOR_MINIMUM = 6
TARGET_PAIRS = 20
MINIMUM_SLACK = 4
GOVERNED_CHECKS = ("commit-message form", "staging by name")


class UnboundDriverError(NotImplementedError):
    """Raised by a driver hook not yet bound to the designed surface."""


def unbound(assumption: str) -> NoReturn:
    raise UnboundDriverError(f"driver unbound: {assumption}")


# -- The narrowed checkout --------------------------------------------------------------------

# Beyond what an adherence run reads (`adherence_eval.CHECKOUT_FILES` and `CHECKOUT_TREES`), a
# move run and these tests read:
#   - `claude/canonical-blocks`: the managed fixture's project `CLAUDE.md` carries the shipped
#     blocks, which the kit takes from the checkout;
#   - `claude/kernels`: `scripts/check_kernel_manifest.py`, run over the checkout before and
#     after a move run is recorded, reads the committed kernels.
# A binding step that finds the runner reading another path adds it here, naming the reader.
MOVE_CHECKOUT_FILES = adherence_eval.CHECKOUT_FILES
MOVE_CHECKOUT_TREES = (
    *adherence_eval.CHECKOUT_TREES,
    "claude/canonical-blocks",
    "claude/kernels",
)
_TEMPLATE: dict[str, Path] = {}


def move_checkout(workspace: Path) -> Path:
    """A small, clean, committed checkout a move run may be pointed at, copied from a template.

    The template is built once per process from the declared read set, as the adherence
    driver's narrowed checkout is; each scenario gets its own copy, which it may change.
    """
    if "root" not in _TEMPLATE:
        scratch = Path(tempfile.mkdtemp(prefix="move-checkout-template-"))
        atexit.register(shutil.rmtree, scratch, ignore_errors=True)
        _TEMPLATE["root"] = _build_template(scratch)
    target = workspace / "checkout"
    shutil.copytree(_TEMPLATE["root"], target, symlinks=True)
    return target


def _build_template(scratch: Path) -> Path:
    """The read set, as this working tree has it, in one commit of a repository of its own."""
    root = scratch / "checkout"
    root.mkdir(parents=True)
    listed = adherence_eval._git(
        REPO_ROOT,
        *("ls-files", "-z", "--cached", "--others", "--exclude-standard"),
        *("--", *MOVE_CHECKOUT_FILES, *MOVE_CHECKOUT_TREES),
    )
    for relpath in sorted(set(filter(None, listed.split("\0")))):
        source = REPO_ROOT / relpath
        if source.is_file():
            (root / relpath).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, root / relpath, follow_symlinks=False)
    adherence_eval._git(root, "init", "-q", "-b", "main")
    objects = adherence_eval._git(
        REPO_ROOT, "rev-parse", "--path-format=absolute", "--git-path", "objects"
    )
    (root / ".git" / "objects" / "info" / "alternates").write_text(objects, encoding="utf-8")
    adherence_eval._git(root, "add", "-A")
    adherence_eval._git(root, "commit", "-q", "-m", "a checkout of the files a move run reads")
    return root


def tracked_snapshot(root: Path) -> dict[str, str]:
    return adherence_eval.tracked_snapshot(root)


def working_state(root: Path) -> tuple[str, str]:
    return adherence_eval.working_state(root)


# -- The console entry ------------------------------------------------------------------------


@dataclass(frozen=True)
class MoveRun:
    """What an operator asks of the adherence entry for a move.

    `kind` is None only for a dry run, which prices the floor run and the paired run together.
    """

    move: str
    checkout: Path
    kind: RunKind | None = None
    seed: int = SEED
    max_tasks: int | None = None
    floor_citation: Path | None = None  # the floor results file a paired run cites
    stop_count: int | None = None
    dry_run: bool = False
    declared: Declared | None = None  # a written declaration; None: the kit's own


def move_arguments(run: MoveRun) -> list[str]:
    """The entry's command line for `run`, after the checkout positional."""
    unbound(
        "the operator names a move in place of a role, chooses its floor run or its paired run,"
        " and has a paired run cite a floor run's results file, by options of the adherence"
        " entry not yet designed; a dry run names the move alone and prices both runs"
    )


def run_move(run: MoveRun, claude_bin: Path, extra: Sequence[str] = ()) -> CliResult:
    return run_entry([str(run.checkout), *move_arguments(run), *extra], claude_bin)


def continue_run(
    checkout: Path, stopped: Path, claude_bin: Path, declared: Declared | None = None
) -> CliResult:
    extra = [] if declared is None else declaration_arguments(declared)
    return run_entry([str(checkout), "--continue", stopped.stem, *extra], claude_bin)


def declaration_arguments(declared: Declared) -> list[str]:
    unbound("the operator hands the entry a written move declaration in place of the kit's own")


def close_run(checkout: Path, stopped: Path, reason: str, claude_bin: Path) -> CliResult:
    return run_entry([str(checkout), "--close", stopped.stem, "--reason", reason], claude_bin)


def render_report(results: Path, claude_bin: Path) -> CliResult:
    return run_entry(["--report", str(results)], claude_bin)


def run_entry(args: Sequence[str], claude_bin: Path, *, timeout: int = 900) -> CliResult:
    """Invoke the adherence console entry with `claude_bin/claude` first on PATH."""
    entry = adherence_eval.adherence_console_entry()
    env = adherence_eval.eval_env(
        {"PATH": adherence_eval._guarded_path(claude_bin), "ANTHROPIC_API_KEY": DUMMY_CREDENTIAL}
    )
    result = subprocess.run(
        [adherence_eval._uv(), "run", "--quiet", "--python", EVAL_PYTHON]
        + ["--project", str(EVAL_PROJECT), entry.name, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=EVAL_PROJECT,
        timeout=timeout,
    )
    return CliResult(result.returncode, result.stdout, result.stderr)


# -- The dry run's listing --------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedMoveSession:
    run: RunKind
    task_id: str
    fixture: str
    fixture_kind: FixtureKind
    wording_variant: str
    arm: Arm


@dataclass(frozen=True)
class MoveListing:
    sessions: tuple[PlannedMoveSession, ...]
    per_task: Mapping[tuple[RunKind, str], int]  # the session count printed for each task
    totals: Mapping[str, int]  # printed totals: "floor", "paired", "all"
    calibration_sessions: int


def move_listing(stdout: str) -> MoveListing:
    unbound(
        "a move's dry run prints, for the floor run and the paired run, every session it would"
        " launch with its task, fixture kind, wording variant and arm, the session count per"
        " task and the totals, in a printed form not yet designed"
    )


# -- The move results file --------------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredChange:
    path: str
    sha256: str  # the digest of the change's content as declared


@dataclass(frozen=True)
class PinnedSettings:
    commit_attribution: str
    model: str
    effort: str
    user_instructions: str  # the identity of the user instruction file the arm rendered


@dataclass(frozen=True)
class MoveResults:
    subject_kind: str  # "move" for a move run
    subject: str
    run_kind: RunKind
    moved_rule_text: str
    declared_changes: Mapping[Arm, tuple[DeclaredChange, ...]]
    allowance_method: str
    pinned: Mapping[Arm, PinnedSettings]
    declared_at: str
    first_launch_at: str | None
    checks_graded: frozenset[str]  # every check name graded on any session of the run
    complete_pairs: int
    verdicts: Mapping[str, str]  # governed check -> verdict
    launch_orders: Mapping[str, tuple[Arm, Arm]]
    seed: int
    cited_floor_lineage: tuple[str, ...]  # run ids of every part of the cited floor lineage
    ending: str  # "finished", "stopped" or "closed"
    refusal_reasons: Mapping[str, str]  # session id -> why its take was refused scoring
    earlier_floor_runs: tuple[str, ...]  # listed apart from paired draws
    earlier_paired_runs: tuple[str, ...]


def read_move_results(path: Path) -> MoveResults:
    unbound(
        "a move run's results file names its subject as a move with the move's identity (the"
        " moved rule's text and every declared change with its content), its pinned settings per"
        " arm, its allowance method, launch orders, the cited floor lineage and each refused"
        " take's reason, in fields not yet designed"
    )


def role_index_entries(checkout: Path) -> dict[str, object]:
    """Every entry of the run index that records a role run, by run id."""
    index = checkout / ".ai-state" / "eval_ledger" / "adherence" / "index.json"
    runs = json.loads(index.read_text(encoding="utf-8"))["runs"]
    return {run_id: entry for run_id, entry in runs.items() if entry.get("roles")}


def kernel_manifest_findings(checkout: Path) -> str:
    """What `scripts/check_kernel_manifest.py --json` reports over the checkout's ledger."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_kernel_manifest.py")]
        + ["--json", "--repo-root", str(checkout)],
        capture_output=True,
        text=True,
        cwd=checkout,
        env=adherence_eval.eval_env({"HOME": str(checkout.parent / "home")}),
        timeout=300,
    )
    return f"exit={result.returncode}\n{result.stdout}"


# -- Declarations and arms --------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedCheck:
    name: str
    rule_file: str
    section: str
    phrases: tuple[str, ...]  # the declared phrases a task wording may not state or paraphrase


@dataclass(frozen=True)
class MoveDeclaration:
    move: str
    checks: tuple[GovernedCheck, ...]
    resident_kernel: str  # the lean arm's resident text
    fixture_kinds: tuple[FixtureKind, ...]  # one kind only when the move says so


def kit_declaration(move: str) -> MoveDeclaration:
    unbound(
        "a move's kit declares its arms' changes, its governed checks (each naming a rule file,"
        " a section and the phrases a task wording may not carry), the lean arm's resident"
        " kernel and the fixture kinds it changes delivery in, in a form not yet designed"
    )


Variant = Literal[
    "as declared",
    "a lean line neither resident nor delivered",
    "no governed check",
    "three governed checks",
    "a section delivered only by hook text read from no exported rule file",
    "delivery changed in the managed fixture kind only",
    "the arms differ in the commit-attribution setting",
    "the arms differ in the model",
    "the arms differ in the effort",
    "the arms differ in the user instruction file",
    "a change confined to the lean arm",
    "a change to the floor arm",
    "a resident line and a path-matched rule for the decision records",
]


@dataclass(frozen=True)
class Declared:
    """A declaration as the runner will read it: a kit's own, or a known-bad variant of it."""

    move: str
    variant: Variant
    path: Path | None = None  # where the variant was written, when it is not the kit's own


def declare(move: str, variant: Variant, workspace: Path) -> Declared:
    unbound(
        f"the runner reads a move declaration a scenario writes, and the driver can write the"
        f" {move} declaration with this variation: {variant}"
    )


@dataclass(frozen=True)
class BuiltArm:
    arm: Arm
    copy: Path
    declared: tuple[DeclaredChange, ...]


@dataclass(frozen=True)
class ArmBuild:
    """The outcome of building and checking a move's arms before any session."""

    arms: Mapping[Arm, BuiltArm]
    refusal: str | None  # the refusal's message, naming what it refuses


def build_arms(declared: Declared, checkout: Path, workspace: Path) -> ArmBuild:
    unbound(
        "the runner builds a declared move's full, lean and floor arms over its own copy of the"
        " checkout and runs every check it makes before any session, offline, reachable without"
        " launching a session"
    )


def check_arm_copy(declared: Declared, arm: Arm, copy: Path, checkout: Path) -> str | None:
    """The refusal the runner gives an arm copy as it stands (None: accepted)."""
    unbound(
        "the runner's check that an arm's copy differs from the checkout in exactly the arm's"
        " declared changes can be asked about a copy a scenario has altered"
    )


# -- Tasks and fixtures -----------------------------------------------------------------------


@dataclass(frozen=True)
class MoveTask:
    task_id: str
    fixture: str
    fixture_kind: FixtureKind
    wording_variant: str
    wording: str  # the request the session is given
    named_files: tuple[str, ...]  # the files the request asks the session to commit
    planted_credential: str | None  # the unnamed file holding a planted credential, if any


def move_tasks(declared: Declared, seed: int = SEED) -> tuple[MoveTask, ...]:
    unbound(
        "a move's generated task list can be read with each task's fixture, kind, wording"
        " and the files its request names"
    )


def build_task_fixture(declared: Declared, task: MoveTask, workspace: Path) -> Path:
    unbound("the kit builds one task's fixture repository where a scenario can inspect it")


# -- Reach on hosts without hooks -------------------------------------------------------------


def rule_sections(text: str) -> tuple[str, ...]:
    return tuple(line.lstrip("#").strip() for line in text.splitlines() if line.startswith("### "))


def sections_reached(root: Path, move: str, host: Host, scratch: Path) -> frozenset[str]:
    """The sections of the moved rule (as the checkout holds it) a host's export reaches in `root`."""
    sections = rule_sections((REPO_ROOT / MOVED_RULES[move]).read_text(encoding="utf-8"))
    out = scratch / f"{host}-export"
    if host == "cursor":
        _export(["cursor/config/export-cursor-rules.py", str(root), str(out)])
        exported = out / CURSOR_RULE_EXPORT[move]
        text = exported.read_text(encoding="utf-8") if exported.is_file() else ""
        return frozenset(s for s in sections if f"### {s}" in text)
    _export(
        [
            "codex/config/export-codex-rules-bridge.py",
            "--repo-root",
            str(root),
            "--out-dir",
            str(out),
        ]
    )
    manifest = json.loads((out / "praxion" / "rules_manifest.json").read_text(encoding="utf-8"))
    listed = {*manifest.get("always_on_rule_ids", ()), *manifest.get("path_scoped_rule_ids", ())}
    rule = root / MOVED_RULES[move]
    if CODEX_RULE_ID[move] not in listed or not rule.is_file():
        return frozenset()
    text = rule.read_text(encoding="utf-8")
    return frozenset(s for s in sections if f"### {s}" in text)


def _export(argv: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, *argv], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"the export {argv[0]} failed:\n{result.stderr[-2000:]}"
