"""Driver for the main-session half of the adherence eval: moves, their arms and their kits.

A *move* is a declared relocation of one rule's text out of session-start residency into
other channels. Its arms are `full` (today's delivery), `lean` (the move) and `floor` (no line
of the rule in any channel). The operator runs a move through the same console entry that
measures a spawned role, `praxion-evals-adherence`; each task is one headless main session in
a scratch fixture repository.

Bound here, because the specification or the base commit fixes them:

- the console entry and its existing options `--dry-run`, `--report`, `--continue`,
  `--close`, `--reason`, `--reindex`, `--max-tasks` and `--stop-count`, reached as the
  adherence driver reaches it (`adherence_eval`), with a `claude` stand-in first on `PATH`, and
  the move options `--move`, `--run`, `--floor-run` and `--declaration`;
- the first move's name, `git-conventions`, its rule `rules/swe/vcs/git-conventions.md`, the
  second move's name, `adr-conventions`, and the arm names `full`, `lean` and `floor`;
- the defaults a dry run prices: 24 tasks paired (48 sessions) and 8 floor sessions;
- what the Cursor rule export and the Codex rules bridge reach of a rule, measured by running
  each exporter (`cursor/config/export-cursor-rules.py ROOT OUT`,
  `codex/config/export-codex-rules-bridge.py --repo-root ROOT --out-dir OUT`) over a tree;
- a narrowed checkout: only the files a move run and these tests read, built once per
  process from a declared read set and copied for each scenario.

Unbound until a binding step ties them to the designed surface (each raises
`UnboundDriverError` with the assumption's words): nothing remains in this module that is not
bound. A move's declaration and its known-bad variants (`move_declarations`), the dry run's
printed lines and the results file's keys, and the arm build, the arm-copy check, the task list
and the fixture builder (through `move_pocket`, the one seam into the eval pocket) are bound.
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
from typing import Any, Literal, NoReturn

from tests.acceptance.drivers import adherence_eval, move_declarations, move_pocket
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
#   - the hook, config and exporter files below, each named with its reader: found by running
#     the registered session-start and PreToolUse commands and both rules exports offline.
# A binding step that finds the runner reading another path adds it here, naming the reader.
MOVE_CHECKOUT_FILES = (
    *adherence_eval.CHECKOUT_FILES,
    "hooks/inject_rules.py",  # the registered session-start rule injection, run over an arm copy
    "claude/config/praxion-rules.yaml.example",  # read by inject_rules.py
    "hooks/_hook_utils.py",  # imported by inject_rules.py and remind_adr.py
    "hooks/commit_gate.sh",  # the wrapper the registered PreToolUse Bash commands run through
    "hooks/remind_adr.py",  # a registered PreToolUse hook on Bash, run on a commit command
    "cursor/config/export-cursor-rules.py",  # the Cursor rules export, run over each arm's tree
    "codex/config/export-codex-rules-bridge.py",  # the Codex rules bridge, run over each tree
    "codex/config/rules_bridge_delegate_hooks.py",  # imported by the bridge export
    "codex/config/rules_bridge_parsing.py",  # imported by the bridge export
    "codex/config/rules_bridge_registrations.py",  # imported by the bridge export
    "codex/config/rules_bridge_routing_hooks.py",  # imported by the bridge export
    "codex/config/rules_bridge_static_modules.py",  # imported by the bridge export
)
MOVE_CHECKOUT_TREES = (
    *adherence_eval.CHECKOUT_TREES,
    "claude/canonical-blocks",
    "claude/kernels",
    "hooks/_observation_log",  # imported by remind_adr.py
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
    """The entry's command line for `run`, after the checkout positional.

    A move run names its run kind and, for a paired run, the floor results file it cites; a dry
    run names neither, because it prices both runs.
    """
    if run.dry_run == (run.kind is not None):
        raise ValueError(f"a dry run names no run kind and any other run names one: {run}")
    args = ["--move", run.move, *_run_kind_arguments(run), "--seed", str(run.seed)]
    if run.floor_citation is not None:
        args += ["--floor-run", str(run.floor_citation)]
    if run.max_tasks is not None:
        args += ["--max-tasks", str(run.max_tasks)]
    if run.stop_count is not None:
        args += ["--stop-count", str(run.stop_count)]
    if run.declared is not None:
        args += declaration_arguments(run.declared)
    return args


def _run_kind_arguments(run: MoveRun) -> list[str]:
    return ["--dry-run"] if run.kind is None else ["--run", run.kind]


def run_move(run: MoveRun, claude_bin: Path, extra: Sequence[str] = ()) -> CliResult:
    return run_entry([str(run.checkout), *move_arguments(run), *extra], claude_bin)


def continue_run(
    checkout: Path, stopped: Path, claude_bin: Path, declared: Declared | None = None
) -> CliResult:
    extra = [] if declared is None else declaration_arguments(declared)
    return run_entry([str(checkout), "--continue", stopped.stem, *extra], claude_bin)


def declaration_arguments(declared: Declared) -> list[str]:
    """`--declaration FILE` for a written variant; the kit's own declaration needs no option."""
    return [] if declared.path is None else ["--declaration", str(declared.path)]


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
    """Parse the printed dry run: `session`, `task`, `total` and `calibration` lines.

    Lines of other shapes are ignored; a listing lacking its total or calibration line, or a
    line of a known shape that does not parse, raises with the line.
    """
    sessions: list[PlannedMoveSession] = []
    per_task: dict[tuple[RunKind, str], int] = {}
    totals: dict[str, int] | None = None
    calibration: int | None = None
    for line in stdout.splitlines():
        tokens = line.split()
        kind = tokens[0] if tokens else ""
        try:
            if kind == "session":
                _, run, task_id, fixture, fixture_kind, wording, arm = tokens
                sessions.append(
                    PlannedMoveSession(
                        _run_kind(run),
                        task_id,
                        fixture,
                        _fixture_kind(fixture_kind),
                        wording,
                        _arm(arm),
                    )
                )
            elif kind == "task":
                _, run, task_id, count = tokens
                per_task[(_run_kind(run), task_id)] = _session_count(count)
            elif kind == "total":
                totals = dict(_keyed(token) for token in tokens[1:])
                if set(totals) != {"floor", "paired", "all"}:
                    raise ValueError(f"expected floor, paired and all, found {sorted(totals)}")
            elif kind == "calibration":
                calibration = _session_count(tokens[1])
        except ValueError as error:
            raise ValueError(f"unreadable dry-run line {line!r}: {error}") from error
    if totals is None or calibration is None:
        raise ValueError("the dry run printed no `total` line or no `calibration` line")
    return MoveListing(tuple(sessions), per_task, totals, calibration)


def _keyed(token: str) -> tuple[str, int]:
    name, separator, value = token.partition("=")
    if not separator:
        raise ValueError(f"expected <name>=<n>, found {token!r}")
    return name, int(value)


def _session_count(token: str) -> int:
    name, count = _keyed(token)
    if name != "sessions":
        raise ValueError(f"expected sessions=<n>, found {token!r}")
    return count


def _run_kind(value: str) -> RunKind:
    if value not in ("floor", "paired"):
        raise ValueError(f"run {value!r} is neither floor nor paired")
    return value


def _fixture_kind(value: str) -> FixtureKind:
    if value not in FIXTURE_KINDS:
        raise ValueError(f"fixture kind {value!r} is neither managed nor unmanaged")
    return value


def _arm(value: str) -> Arm:
    if value not in MOVE_ARMS:
        raise ValueError(f"arm {value!r} is not full, lean or floor")
    return value


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
    """Read a move results file; keys outside the format are ignored, a missing one raises."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not a JSON move results file: {error}") from error

    def need(*keys: str) -> Any:
        value = document
        for depth, key in enumerate(keys):
            if not isinstance(value, dict) or key not in value:
                raise ValueError(
                    f"{path}: the move results file lacks {'.'.join(keys[: depth + 1])!r}"
                )
            value = value[key]
        return value

    if need("schema") != "move-results/1":
        raise ValueError(f"{path}: schema {need('schema')!r} is not move-results/1")
    sessions = need("sessions")
    try:
        return MoveResults(
            subject_kind=need("subject", "kind"),
            subject=need("subject", "name"),
            run_kind=_run_kind(need("run_kind")),
            moved_rule_text=need("identity", "moved_rule_text"),
            declared_changes={
                _arm(arm): tuple(DeclaredChange(c["path"], c["sha256"]) for c in changes)
                for arm, changes in need("identity", "arms").items()
            },
            allowance_method=need("allowance_method"),
            pinned={
                _arm(arm): PinnedSettings(**_pinned(values))
                for arm, values in need("pinned").items()
            },
            declared_at=need("declared_at"),
            first_launch_at=need("first_launch_at"),
            checks_graded=frozenset(name for session in sessions for name in session["checks"]),
            complete_pairs=need("complete_pairs"),
            verdicts=need("verdicts"),
            launch_orders={
                task: (_arm(first), _arm(second))
                for task, (first, second) in need("launch_orders").items()
            },
            seed=need("seed"),
            cited_floor_lineage=tuple(need("cited_floor")),
            ending=need("ending", "kind"),
            refusal_reasons={
                session["session_id"]: session["reason"]
                for session in sessions
                if session["status"] == "refused"
            },
            earlier_floor_runs=tuple(need("earlier_runs", "floor")),
            earlier_paired_runs=tuple(need("earlier_runs", "paired")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"{path}: a malformed field in the move results file: {error!r}"
        ) from error


def _pinned(values: Mapping[str, str]) -> dict[str, str]:
    keys = ("commit_attribution", "model", "effort", "user_instructions")
    return {key: values[key] for key in keys}


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


_SCOPE_KINDS: dict[str, tuple[FixtureKind, ...]] = {
    "both": FIXTURE_KINDS,
    "managed": ("managed",),
    "unmanaged": ("unmanaged",),
}


def kit_declaration(move: str) -> MoveDeclaration:
    """The move's kit declaration, as its file at the base of the kit directory declares it."""
    return _parse_declaration(move_declarations.kit_payload(move))


def _parse_declaration(payload: move_declarations.Payload) -> MoveDeclaration:
    return MoveDeclaration(
        move=payload["move"],
        checks=tuple(
            GovernedCheck(c["name"], c["rule_file"], c["section"], tuple(c["phrases"]))
            for c in payload["checks"]
        ),
        resident_kernel=move_declarations.resident_kernel(payload),
        fixture_kinds=_SCOPE_KINDS[payload["fixture_scope"]],
    )


Variant = Literal[
    "as declared",
    "a lean line neither resident nor delivered",
    "no governed check",
    "three governed checks",
    "a section delivered only by hook text read from no exported rule file",
    "a file holding a section turned from always-on to path-scoped on Codex",
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
    """The declaration the runner reads for `move` under `variant`, written under `workspace`."""
    return Declared(move, variant, move_declarations.write_variant(move, variant, workspace))


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
    """Build the three arms over the runner's own copy, with every check made before a session."""
    result = move_pocket.build_arms(declared.move, declared.path, checkout, workspace)
    if result["refused"]:
        return ArmBuild({}, result["reason"])
    return ArmBuild(
        {
            _arm(arm): BuiltArm(
                _arm(arm), Path(built["copy"]), tuple(_declared_change(c) for c in built["changes"])
            )
            for arm, built in result["arms"].items()
        },
        None,
    )


def _declared_change(change: Mapping[str, str] | Sequence[str | None]) -> DeclaredChange:
    if isinstance(change, Mapping):
        return DeclaredChange(change["path"], change.get("sha256") or "")
    path, digest = change
    return DeclaredChange(str(path), digest or "")


def check_arm_copy(declared: Declared, arm: Arm, copy: Path, checkout: Path) -> str | None:
    """The refusal the runner gives an arm copy as it stands (None: accepted)."""
    return move_pocket.check_copy(declared.move, declared.path, arm, copy, checkout)


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
    return tuple(
        MoveTask(
            task["task_id"],
            task["fixture"],
            _fixture_kind(task["fixture_kind"]),
            task["wording_variant"],
            task["wording"],
            tuple(task["named_files"]),
            task["planted_credential"],
        )
        for task in move_pocket.tasks(declared.move, declared.path, seed)
    )


def build_task_fixture(declared: Declared, task: MoveTask, workspace: Path) -> Path:
    """The task's fixture repository, built under `workspace` from the default seed's task list."""
    return move_pocket.build_fixture(declared.move, declared.path, SEED, task.task_id, workspace)


# -- Reach on hosts without hooks -------------------------------------------------------------


def rule_sections(text: str) -> tuple[str, ...]:
    return tuple(line.lstrip("#").strip() for line in text.splitlines() if line.startswith("### "))


def section_lines(text: str) -> dict[str, tuple[str, ...]]:
    """Each `###` section of a rule, by title: its non-blank lines, heading included."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("### "):
            current = sections.setdefault(line.lstrip("#").strip(), [])
        elif line.startswith(("# ", "## ")):
            current = None
        if current is not None and line.strip():
            current.append(line.rstrip())
    return {title: tuple(lines) for title, lines in sections.items()}


@dataclass(frozen=True)
class Reach:
    """What a host's export reaches of the moved rule, measured line by line over one tree."""

    sections: frozenset[str]  # every non-blank line unchanged in a file the export carries
    always_on: frozenset[str]  # Codex only: reached through files the bridge lists always-on


def reach(root: Path, checkout: Path, move: str, host: Host, scratch: Path) -> Reach:
    """Run `host`'s export over `root` and measure the moved rule's sections (as `checkout` holds them)."""
    sections = section_lines((checkout / MOVED_RULES[move]).read_text(encoding="utf-8"))
    out = scratch / f"{host}-export"
    if host == "cursor":
        _export(["cursor/config/export-cursor-rules.py", str(root), str(out)])
        carried = [path for path in out.rglob("*") if path.is_file()]
        return Reach(_reached(sections, carried), frozenset())
    argv = ["codex/config/export-codex-rules-bridge.py", "--repo-root", str(root)]
    _export([*argv, "--out-dir", str(out)])
    manifest = json.loads((out / "praxion" / "rules_manifest.json").read_text(encoding="utf-8"))
    always_on_ids = set(manifest.get("always_on_rule_ids", ()))
    listed = [rule for rule in manifest["rules"] if rule.get("codex_load") != "excluded"]
    carried = [root / rule["relpath"] for rule in listed]
    always_on = [root / rule["relpath"] for rule in listed if rule["id"] in always_on_ids]
    return Reach(_reached(sections, carried), _reached(sections, always_on))


def _reached(sections: Mapping[str, tuple[str, ...]], files: Sequence[Path]) -> frozenset[str]:
    lines = {
        line.rstrip()
        for path in files
        if path.is_file()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
    }
    return frozenset(title for title, held in sections.items() if set(held) <= lines)


def _export(argv: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, *argv], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"the export {argv[0]} failed:\n{result.stderr[-2000:]}"
