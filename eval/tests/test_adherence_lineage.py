"""How a run ended: the ending's wire form round-trips, only a both-arms stop or a spend refusal
is continuable, a file without an ending is legacy, and the runner records the ending it had.
What it was measured on: the tree digest counts what a role runs on and nothing else, a legacy
file's roles are derived from its commit, `diff` names every difference, and the runner records
the identity it began with."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import tests.test_adherence_cli as cli_tests
from praxion_evals.adherence import report, results
from praxion_evals.adherence.infra_stop import EvidenceTail, Launched, StopReason, StopRule
from praxion_evals.adherence.lineage import (
    Closed,
    Finished,
    InfraStopped,
    Interrupted,
    Legacy,
    Lineage,
    MeasuredIdentity,
    PartRef,
    RoleIdentity,
    RunEnding,
    SpendRefused,
    UnknownIdentity,
    at_commit,
    continuable,
    current_identity,
    diff,
    ending_from_json,
    ending_of,
    ending_to_json,
    measured_identity,
    never_launched,
    relaunch_tasks,
    role_identity,
    tree_digest,
    working_tree,
)
from praxion_evals.adherence.model import Errored
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.test_adherence_report import results_of
from tests.test_adherence_results import pair_of_sessions, run_results, session

# The fixtures that stand a scripted `claude` in for the paid sessions and keep the live checkout's
# role unswitched, shared with the paid-loop tests of the command line.
paid = cli_tests.paid
full_first = cli_tests.full_first  # every task launches full first, as these runs end mid-task
unswitched_checkout = cli_tests.unswitched_checkout

pytestmark = pytest.mark.usefixtures("full_first")

CREDIT_TAIL = "\nCredit balance is too low"


def _stop(scope: str = "both-arms") -> InfraStopped:
    sessions = tuple(Launched(f"task-{n}", "lean", 1) for n in range(3))
    reason = StopReason("result_error", CREDIT_TAIL, "researcher", "lean", sessions, scope)  # type: ignore[arg-type]
    return InfraStopped(reason)


def _closed(stopped: Any = None) -> Closed:
    return Closed("no credit left", "2026-10-17T09:00:00Z", {"C1": "clear"}, stopped or _stop())


ROUND_TRIPPING: dict[str, RunEnding] = {
    "finished": Finished(),
    "infrastructure stop": _stop(),
    "one-arm infrastructure stop": _stop("one-arm"),
    "spend refusal": SpendRefused(("task-001", "task-002")),
    "interrupt": Interrupted(),
    "closed run": _closed(),
}


@pytest.mark.parametrize("ending", ROUND_TRIPPING.values(), ids=ROUND_TRIPPING.keys())
def test_every_ending_survives_its_wire_form(ending: RunEnding) -> None:
    assert ending_from_json(ending_to_json(ending)) == ending


def test_an_infrastructure_stop_is_written_with_the_pinned_field_names() -> None:
    assert ending_to_json(_stop()) == {
        "kind": "infra_stopped",
        "error_kind": "result_error",
        "masked_tail": CREDIT_TAIL,
        "role": "researcher",
        "arm": "lean",
        "sessions": [{"task_id": f"task-{n}", "arm": "lean", "attempt": 1} for n in range(3)],
        "scope": "both-arms",
    }


def test_a_closed_ending_keeps_the_stop_it_closed() -> None:
    wire = ending_to_json(_closed(SpendRefused(("task-001",))))

    assert wire["stopped"] == {"kind": "spend_refused", "tasks": ["task-001"]}


def test_a_spend_refusal_written_without_tasks_reads_as_naming_none() -> None:
    assert ending_from_json({"kind": "spend_refused"}) == SpendRefused()


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        (_stop("both-arms"), True),
        (SpendRefused(), True),
        (_stop("one-arm"), False),
        (Finished(), False),
        (Interrupted(), False),
        (_closed(), False),
        (Legacy(), False),
    ],
    ids=[
        "both-arms stop",
        "spend refusal",
        "one-arm stop",
        "finished",
        "interrupt",
        "closed",
        "legacy",
    ],
)
def test_only_a_both_arms_stop_or_a_spend_refusal_can_be_continued(
    ending: RunEnding, expected: bool
) -> None:
    assert continuable(ending) is expected


def test_a_file_with_no_ending_is_legacy_and_legacy_has_no_wire_form() -> None:
    legacy = results_of([])

    assert ending_of(legacy) == Legacy()
    with pytest.raises(ValueError, match="never written"):
        ending_to_json(Legacy())


def test_the_ending_is_read_from_the_run_record() -> None:
    loaded = results_of([])
    recorded = replace(loaded.run, extra={"ending": ending_to_json(_stop())})

    assert ending_of(replace(loaded, run=recorded)) == _stop()


@pytest.mark.parametrize(
    ("wire", "complaint"),
    [
        ({"kind": "exploded"}, "unknown run ending"),
        ({}, "lacks 'kind'"),
        ({**ending_to_json(_stop()), "arm": "middle"}, "unknown arm"),
        ({**ending_to_json(_stop()), "scope": "some-arms"}, "unknown scope"),
        ({"kind": "infra_stopped"}, "lacks 'error_kind'"),
        ({**ending_to_json(_closed()), "stopped": {"kind": "finished"}}, "closes a stopped run"),
    ],
    ids=[
        "unknown kind",
        "no kind",
        "unknown arm",
        "unknown scope",
        "missing field",
        "closed finish",
    ],
)
def test_a_malformed_ending_is_refused_with_what_was_wrong(
    wire: dict[str, Any], complaint: str
) -> None:
    with pytest.raises(ValueError, match=complaint):
        ending_from_json(wire)


def test_a_run_cannot_be_closed_without_a_reason() -> None:
    with pytest.raises(ValueError, match="needs a reason"):
        Closed("  ", "2026-10-17T09:00:00Z", {}, Interrupted())


# ---------------------------------------------------------------------------
# What the runner records
# ---------------------------------------------------------------------------


class Interrupts(cli_tests.Script):
    """Answers like the stand-in until its Nth launch, where the operator presses Ctrl-C."""

    def __init__(self, at_launch: int) -> None:
        super().__init__()
        self.at_launch = at_launch

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        run = super().__call__(spec, env)
        if len(self.specs) == self.at_launch:
            raise KeyboardInterrupt
        return run


def test_a_run_that_reaches_the_end_of_its_plan_records_that_it_finished(
    paid: Any, tmp_path: Path
) -> None:
    paid(cli_tests.Script())

    code, loaded = cli_tests._run(tmp_path)

    assert (code, ending_of(loaded)) == (0, Finished())


def test_a_launch_refused_by_the_spend_cap_is_recorded_as_a_continuable_spend_refusal(
    paid: Any, tmp_path: Path
) -> None:
    paid(cli_tests.Script(cost=None))

    code, loaded = cli_tests._run(tmp_path, "--max-total-usd", "2")

    ending = ending_of(loaded)
    assert (code, loaded.run.complete) == (1, False)
    assert ending == SpendRefused((loaded.sessions[0].setup.task_id,))
    assert continuable(ending)


def test_an_interrupt_still_writes_the_file_with_every_session_that_had_ended(
    paid: Any, tmp_path: Path
) -> None:
    paid(Interrupts(at_launch=4))  # the proofs, then the full arm's session, then Ctrl-C

    code, loaded = cli_tests._run(tmp_path)

    assert (code, loaded.run.complete) == (1, False)
    assert ending_of(loaded) == Interrupted()
    assert [(r.setup.arm, type(r.status).__name__) for r in loaded.sessions] == [
        ("full", "Measured")
    ]
    assert not continuable(ending_of(loaded))


def test_an_interrupt_keeps_the_spend_the_run_had_settled(paid: Any, tmp_path: Path) -> None:
    paid(Interrupts(at_launch=4))

    loaded = cli_tests._run(tmp_path)[1]

    assert loaded.run.extra["spend"]["spent_usd"] == pytest.approx(3 * 0.01)


# ---------------------------------------------------------------------------
# What the report says
# ---------------------------------------------------------------------------


def _rendered(ending: RunEnding | None) -> str:
    loaded = results_of([])
    extra = {} if ending is None else {"ending": ending_to_json(ending)}
    return report.render(replace(loaded, run=replace(loaded.run, extra=extra)))


@pytest.mark.parametrize("ending", [Finished(), None], ids=["finished", "recorded before endings"])
def test_a_run_that_finished_or_predates_endings_renders_without_an_ending_line(
    ending: RunEnding | None,
) -> None:
    assert _rendered(ending) == _rendered(None)
    assert "stopped" not in _rendered(ending).split("Declared at")[0]


def test_an_infrastructure_stop_is_reported_with_its_count_kind_evidence_and_continuability() -> (
    None
):
    assert (
        "The run stopped itself: 3 lean sessions in a row ended in result_error with the same"
        " evidence Credit balance is too low; continuable."
    ) in _rendered(_stop())


def test_a_one_arm_stop_is_reported_as_not_continuable() -> None:
    assert "; not continuable." in _rendered(_stop("one-arm"))


def test_an_interrupt_and_a_closed_run_are_reported_on_their_own_line() -> None:
    assert "The operator interrupted the run; not continuable." in _rendered(Interrupted())
    assert (
        "The run was closed on 2026-10-17T09:00:00Z without being continued: no credit left."
        in (_rendered(_closed()))
    )


def test_a_spend_refusal_is_reported_with_the_tasks_it_refused() -> None:
    assert "The spend cap refused launches (tasks task-001); continuable." in _rendered(
        SpendRefused(("task-001",))
    )


def test_the_results_loader_keeps_the_ending_it_was_given(tmp_path: Path) -> None:
    loaded = results_of([])
    recorded = replace(loaded.run, extra={"ending": ending_to_json(Interrupted())})
    path = tmp_path / "out.json"
    results.write_atomic(path, replace(loaded, run=recorded))

    assert ending_of(results.load(path)) == Interrupted()


# ---------------------------------------------------------------------------
# What the run was measured on: the tree digest
# ---------------------------------------------------------------------------

DEFINITION = "---\nname: researcher\n---\nthe definition, version one\n"
ADOPTION = ".ai-state/kernel_adoption.yaml"
RESULTS_FILE = ".ai-state/eval_ledger/adherence/run-a.json"
KERNEL_INDEX = "claude/kernels/index.json"
KERNEL_VERSION = "c89f2d7799c59943f33f4d160d4764a74e1cc491"
NON_ASCII_PATH = "naïve/résumé.txt"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _put(repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _checkout_at(root: Path) -> Path:
    """A committed repository holding a role definition, an adoption ledger, a results file and
    a file with a non-ASCII path, with `scratch/` ignored."""
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _put(root, "agents/researcher.md", DEFINITION)
    _put(root, ADOPTION, "version: 1\nroles: {}\n")
    _put(root, RESULTS_FILE, "{}")
    _put(root, NON_ASCII_PATH, "a path outside ASCII\n")
    _put(root, ".gitignore", "scratch/\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return _checkout_at(tmp_path / "checkout")


def test_a_change_inside_the_results_directory_leaves_the_tree_digest(checkout: Path) -> None:
    before = tree_digest(checkout)

    _put(checkout, RESULTS_FILE, '{"a": "recorded run"}')
    _put(checkout, ".ai-state/eval_ledger/adherence/index.json", "{}")

    assert tree_digest(checkout) == before


@pytest.mark.parametrize(
    "path",
    ["agents/researcher.md", ADOPTION, NON_ASCII_PATH],
    ids=["definition", "adoption ledger", "non-ASCII path"],
)
def test_a_change_to_a_tracked_file_anywhere_else_changes_the_tree_digest(
    checkout: Path, path: str
) -> None:
    before = tree_digest(checkout)

    _put(checkout, path, "changed\n")

    assert tree_digest(checkout) != before


def test_a_new_file_nothing_ignores_changes_the_tree_digest_before_it_is_committed(
    checkout: Path,
) -> None:
    before = tree_digest(checkout)

    _put(checkout, "notes.md", "not committed yet\n")

    assert tree_digest(checkout) != before


def test_a_tracked_file_deleted_from_the_tree_changes_the_tree_digest(checkout: Path) -> None:
    before = tree_digest(checkout)

    (checkout / NON_ASCII_PATH).unlink()

    assert tree_digest(checkout) != before


def test_an_ignored_file_is_outside_the_identity(checkout: Path) -> None:
    before = tree_digest(checkout)

    _put(checkout, "scratch/output.log", "build output\n")

    assert tree_digest(checkout) == before


def test_committing_what_the_tree_already_holds_leaves_the_tree_digest(checkout: Path) -> None:
    _put(checkout, "notes.md", "to be committed\n")
    before = tree_digest(checkout)

    _git(checkout, "add", "notes.md")
    _git(checkout, "commit", "-q", "-m", "notes")

    assert tree_digest(checkout) == before


def test_the_tree_digest_is_the_same_wherever_the_same_files_are_checked_out(
    checkout: Path, tmp_path: Path
) -> None:
    elsewhere = _checkout_at(tmp_path / "elsewhere")

    assert tree_digest(elsewhere) == tree_digest(checkout)


def test_measuring_a_directory_that_is_not_a_repository_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="failed in"):
        tree_digest(tmp_path)


# ---------------------------------------------------------------------------
# What a role ran with
# ---------------------------------------------------------------------------


def _adopt(repo: Path, status: str = "switched", index: str | None = None) -> None:
    _put(repo, ADOPTION, f"version: 1\nroles:\n  researcher:\n    status: {status}\n")
    index = f'{{"schema": 1, "kernel_version": "{KERNEL_VERSION}"}}' if index is None else index
    _put(repo, KERNEL_INDEX, index)


def test_a_role_not_adopted_at_the_checkout_has_no_kernel(checkout: Path) -> None:
    assert role_identity(working_tree(checkout), "researcher") == RoleIdentity(
        hashlib.sha256(DEFINITION.encode()).hexdigest(), None
    )


def test_an_adopted_role_carries_the_kernel_version_it_receives(checkout: Path) -> None:
    _adopt(checkout)

    identity = role_identity(working_tree(checkout), "researcher")

    assert identity == RoleIdentity(hashlib.sha256(DEFINITION.encode()).hexdigest(), KERNEL_VERSION)


def test_a_role_that_is_held_receives_no_kernel(checkout: Path) -> None:
    _adopt(checkout, status="held")

    identity = role_identity(working_tree(checkout), "researcher")

    assert identity == RoleIdentity(hashlib.sha256(DEFINITION.encode()).hexdigest(), None)


def test_an_adopted_role_whose_kernel_index_cannot_be_read_is_unknown(checkout: Path) -> None:
    _adopt(checkout, index="not json")

    identity = role_identity(working_tree(checkout), "researcher")

    assert identity == UnknownIdentity(
        "researcher receives a kernel but claude/kernels/index.json cannot be read"
    )


def test_a_role_without_a_definition_is_unknown(checkout: Path) -> None:
    assert role_identity(working_tree(checkout), "verifier") == UnknownIdentity(
        "agents/verifier.md cannot be read"
    )


# ---------------------------------------------------------------------------
# A file written before identity was recorded
# ---------------------------------------------------------------------------


def _recorded(extra: dict[str, Any]) -> results.RunResults:
    loaded = results_of([])
    return replace(loaded, run=replace(loaded.run, extra=extra))


def _legacy_extra(commit: str) -> dict[str, Any]:
    return {
        "checkout": {"path": "/gone", "commit": commit, "dirty": False},
        "roles": ["researcher"],
        "seed": 7,
        "tasks": {"researcher": ["task-000"]},
    }


def test_a_legacy_files_roles_are_derived_from_the_commit_it_recorded(checkout: Path) -> None:
    commit = _git(checkout, "rev-parse", "HEAD")
    _put(checkout, "agents/researcher.md", "edited since\n")  # the working tree has moved on

    derived = measured_identity(_recorded(_legacy_extra(commit)), checkout)

    expected = RoleIdentity(hashlib.sha256(DEFINITION.encode()).hexdigest(), None)
    assert derived.roles == {"researcher": expected}
    assert (derived.tree, derived.model) == (None, None)


def test_a_legacy_files_role_is_unknown_when_its_commit_cannot_be_reached(checkout: Path) -> None:
    derived = measured_identity(_recorded(_legacy_extra("0" * 40)), checkout)

    assert derived.roles == {"researcher": UnknownIdentity("agents/researcher.md cannot be read")}


def test_a_commit_is_read_back_exactly_as_it_was_committed(checkout: Path) -> None:
    commit = _git(checkout, "rev-parse", "HEAD")

    assert at_commit(checkout, commit)("agents/researcher.md") == DEFINITION.encode()
    assert at_commit(checkout, commit)("agents/missing.md") is None


# ---------------------------------------------------------------------------
# What differs
# ---------------------------------------------------------------------------

RECORDED_ROLE = RoleIdentity("a" * 64, KERNEL_VERSION)
STOP_RULE = StopRule.parse(3, ["result_error"], 2000)


def _identity() -> MeasuredIdentity:
    base = measured_identity(
        _recorded(
            {
                **_legacy_extra("0" * 40),
                "launch_order": {"researcher": {"task-000": ["full", "lean"]}},
                "identity": {
                    "tree": "b" * 64,
                    "model": "claude-opus-5-5",
                    "roles": {"researcher": {"definition_sha": "a" * 64, "kernel": KERNEL_VERSION}},
                },
            }
        ),
        Path("/not-read"),
    )
    return replace(base, declared=replace(base.declared, stop_rule=STOP_RULE))


def _changed(**changes: Any) -> MeasuredIdentity:
    return replace(_identity(), **changes)


def _declared(**changes: Any) -> MeasuredIdentity:
    return _changed(declared=replace(_identity().declared, **changes))


def test_the_identity_a_file_recorded_is_read_back_whole() -> None:
    identity = _identity()

    assert (identity.tree, identity.model, identity.seed) == ("b" * 64, "claude-opus-5-5", 7)
    assert identity.roles == {"researcher": RECORDED_ROLE}
    assert identity.tasks == {"researcher": ("task-000",)}
    assert identity.launch_orders == {"researcher": {"task-000": ("full", "lean")}}


def test_identities_that_are_the_same_differ_in_nothing() -> None:
    assert diff(_identity(), _identity()) == ()


@pytest.mark.parametrize(
    ("other", "named"),
    [
        (_changed(model="claude-sonnet-5-5"), "model: claude-opus-5-5 -> claude-sonnet-5-5"),
        (_changed(seed=8), "seed: 7 -> 8"),
        (
            _changed(tasks={"researcher": ("task-000", "task-001")}),
            "tasks.researcher: [task-000] -> [task-000, task-001]",
        ),
        (_declared(margin_pp=12.0), "declared.margin_pp: 10.0 -> 12.0"),
        (_declared(stop_rule=replace(STOP_RULE, count=4)), "declared.stop_rule.count: 3 -> 4"),
        (
            _changed(launch_orders={"researcher": {"task-000": ("lean", "full")}}),
            "launch_orders.researcher.task-000: [full, lean] -> [lean, full]",
        ),
        (_changed(tree="c" * 64), "tree: bbbbbbbbbbbb -> cccccccccccc"),
        (
            _changed(roles={"researcher": RoleIdentity("d" * 64, KERNEL_VERSION)}),
            "roles.researcher.definition: aaaaaaaaaaaa -> dddddddddddd",
        ),
        (
            _changed(roles={"researcher": RoleIdentity("a" * 64, None)}),
            f"roles.researcher.kernel: {KERNEL_VERSION} -> None",
        ),
    ],
    ids=[
        "model",
        "seed",
        "task list",
        "margin",
        "stop count",
        "launch order",
        "tree",
        "role definition",
        "role kernel",
    ],
)
def test_diff_names_each_way_two_identities_differ(other: MeasuredIdentity, named: str) -> None:
    assert diff(_identity(), other) == (named,)


def test_diff_names_every_difference_not_only_the_first() -> None:
    other = replace(_declared(margin_pp=12.0), seed=8, model="claude-sonnet-5-5")

    assert len(diff(_identity(), other)) == 3


def test_a_model_not_yet_reported_is_not_a_difference() -> None:
    assert diff(_identity(), _changed(model=None)) == ()


def test_launch_orders_only_one_run_recorded_are_not_a_difference() -> None:
    later = _changed(
        launch_orders={"researcher": {"task-000": ("full", "lean"), "task-001": ("lean", "full")}}
    )

    assert diff(_identity(), later) == ()


def test_a_role_whose_identity_is_unknown_is_always_a_difference() -> None:
    unknown = _changed(roles={"researcher": UnknownIdentity("the commit is gone")})

    assert diff(unknown, unknown) == ("roles.researcher: identity unknown (the commit is gone)",)


# ---------------------------------------------------------------------------
# What the runner records
# ---------------------------------------------------------------------------

REPORTED = "claude-opus-5-5"


class Reports(cli_tests.Script):
    """Answers like the stand-in, with an init event that reports a model: the Nth launch
    reports `model-N` unless one name is fixed."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__()
        self.model = model

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        run = super().__call__(spec, env)
        model = self.model or f"model-{len(self.specs)}"
        init = '"subtype": "init"'
        return replace(run, stdout=run.stdout.replace(init, f'{init}, "model": "{model}"', 1))


def test_a_new_run_records_what_it_was_measured_on_when_it_begins(
    paid: Any, tmp_path: Path
) -> None:
    paid(cli_tests.Script())

    loaded = cli_tests._run(tmp_path)[1]

    recorded = loaded.run.extra["identity"]
    definition = (cli_tests.REPO_ROOT / "agents" / f"{cli_tests.ROLE}.md").read_bytes()
    assert set(recorded) == {"tree", "model", "roles"}
    assert len(recorded["tree"]) == len(hashlib.sha256().hexdigest())
    assert (
        recorded["roles"][cli_tests.ROLE]["definition_sha"]
        == hashlib.sha256(definition).hexdigest()
    )


def test_a_run_whose_sessions_report_no_model_records_none(paid: Any, tmp_path: Path) -> None:
    paid(cli_tests.Script())

    assert cli_tests._run(tmp_path)[1].run.extra["identity"]["model"] is None


def test_a_run_records_the_model_its_first_session_reported_and_keeps_it(
    paid: Any, tmp_path: Path
) -> None:
    paid(Reports())

    loaded = cli_tests._run(tmp_path)[1]

    assert loaded.run.extra["identity"]["model"] == "model-1"


def test_the_identity_a_run_wrote_reads_back_as_the_one_it_began_with(
    paid: Any, tmp_path: Path
) -> None:
    paid(Reports(REPORTED))

    loaded = cli_tests._run(tmp_path)[1]

    identity = measured_identity(loaded, cli_tests.REPO_ROOT)
    assert (identity.model, identity.seed) == (REPORTED, loaded.run.extra["seed"])
    assert identity.roles == {
        cli_tests.ROLE: role_identity(working_tree(cli_tests.REPO_ROOT), cli_tests.ROLE)
    }


def test_the_record_a_run_begins_with_names_the_tree_of_the_checkout(checkout: Path) -> None:
    record = current_identity(checkout, ["researcher"])

    assert record == {
        "tree": tree_digest(checkout),
        "model": None,
        "roles": {
            "researcher": {
                "definition_sha": hashlib.sha256(DEFINITION.encode()).hexdigest(),
                "kernel": None,
            }
        },
    }


# ---------------------------------------------------------------------------
# Hook-written telemetry is not part of what a run was measured on
# ---------------------------------------------------------------------------

TELEMETRY_SUMMARY = ".ai-state/observations_summary.jsonl"
TELEMETRY_SEGMENT = ".ai-state/observations-2026-10.jsonl"


def test_a_change_confined_to_hook_written_telemetry_leaves_the_tree_digest(
    checkout: Path,
) -> None:
    _put(checkout, TELEMETRY_SUMMARY, '{"sessions": 1}\n')
    _git(checkout, "add", ".")
    _git(checkout, "commit", "-q", "-m", "telemetry")
    before = tree_digest(checkout)

    _put(checkout, TELEMETRY_SUMMARY, '{"sessions": 2}\n')
    _put(checkout, TELEMETRY_SEGMENT, '{"event": "spawn"}\n')

    assert tree_digest(checkout) == before


@pytest.mark.parametrize(
    "path",
    [ADOPTION, ".ai-state/observations.md", ".ai-state/notes/observations.jsonl"],
    ids=["adoption ledger", "observations in another format", "a telemetry name below a folder"],
)
def test_a_change_beside_the_telemetry_still_changes_the_tree_digest(
    checkout: Path, path: str
) -> None:
    before = tree_digest(checkout)

    _put(checkout, path, "changed\n")

    assert tree_digest(checkout) != before


# ---------------------------------------------------------------------------
# A run's lineage: the parts of one declared run
# ---------------------------------------------------------------------------


def _write_part(directory: Path, run_id: str, continues: str | None = None) -> None:
    extra = {} if continues is None else {"continues": continues}
    results.write_atomic(directory / f"{run_id}.json", run_results([], run_id=run_id, extra=extra))


def _ids(chain: Lineage) -> list[str]:
    return [part.run_id for part in chain.parts]


def test_a_run_nothing_continues_is_a_lineage_of_one_part(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")

    chain = Lineage.parse(tmp_path, "run-a")

    assert (_ids(chain), chain.tip.run_id) == (["run-a"], "run-a")


@pytest.mark.parametrize("named", ["run-a", "run-b", "run-c"])
def test_any_part_names_the_whole_lineage_oldest_first(tmp_path: Path, named: str) -> None:
    _write_part(tmp_path, "run-c", continues="run-b")
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")

    assert _ids(Lineage.parse(tmp_path, named)) == ["run-a", "run-b", "run-c"]


def test_only_the_latest_part_is_the_tip(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")

    assert Lineage.parse(tmp_path, "run-a").tip.run_id == "run-b"


def test_a_part_remembers_its_file_and_the_run_it_continues(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")

    first, second = Lineage.parse(tmp_path, "run-b").parts

    assert (first, second) == (
        PartRef("run-a", tmp_path / "run-a.json", None),
        PartRef("run-b", tmp_path / "run-b.json", "run-a"),
    )


def test_runs_that_are_not_in_the_lineage_are_left_out(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")
    _write_part(tmp_path, "run-elsewhere")

    assert _ids(Lineage.parse(tmp_path, "run-a")) == ["run-a", "run-b"]


def test_a_json_file_that_is_not_a_results_file_does_not_break_a_lineage(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    (tmp_path / "stray.json").write_text("[1, 2]", encoding="utf-8")

    assert _ids(Lineage.parse(tmp_path, "run-a")) == ["run-a"]


@pytest.mark.parametrize("named", ["run-a", "run-b", "run-c"])
def test_a_lineage_where_two_parts_continue_one_is_refused_whichever_part_is_named(
    tmp_path: Path, named: str
) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")
    _write_part(tmp_path, "run-c", continues="run-a")

    with pytest.raises(ValueError, match=r"forks: run-b, run-c all continue run-a"):
        Lineage.parse(tmp_path, named)


def test_a_part_continuing_a_run_no_file_holds_is_a_gap(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-b", continues="run-lost")

    with pytest.raises(ValueError, match=r"gap: run run-b continues run-lost"):
        Lineage.parse(tmp_path, "run-b")


def test_a_predecessor_that_cannot_be_read_is_a_gap(tmp_path: Path) -> None:
    (tmp_path / "run-a.json").write_text("{not json", encoding="utf-8")
    _write_part(tmp_path, "run-b", continues="run-a")

    with pytest.raises(ValueError, match=r"gap: run run-b continues run-a"):
        Lineage.parse(tmp_path, "run-b")


def test_parts_that_continue_each_other_are_refused_as_a_loop(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a", continues="run-b")
    _write_part(tmp_path, "run-b", continues="run-a")

    with pytest.raises(ValueError, match=r"loops"):
        Lineage.parse(tmp_path, "run-a")


def test_a_run_no_file_holds_has_no_lineage(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")

    with pytest.raises(ValueError, match=r"holds run run-missing"):
        Lineage.parse(tmp_path, "run-missing")


def test_two_files_holding_one_run_are_refused(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    (tmp_path / "copy.json").write_text((tmp_path / "run-a.json").read_text(), encoding="utf-8")

    with pytest.raises(ValueError, match=r"copy.json and run-a.json both hold run run-a"):
        Lineage.parse(tmp_path, "run-a")


def test_a_lineage_has_a_part() -> None:
    with pytest.raises(ValueError, match=r"at least one part"):
        Lineage(())


def test_a_lineage_built_out_of_order_is_refused() -> None:
    first = PartRef("run-a", Path("run-a.json"), None)
    second = PartRef("run-b", Path("run-b.json"), "run-a")

    with pytest.raises(ValueError, match=r"run run-b continues 'run-a', not its predecessor None"):
        Lineage((second, first))


# ---------------------------------------------------------------------------
# What a continuation launches again
# ---------------------------------------------------------------------------

STOPPING_TAIL = "fatal: the session channel closed unexpectedly"
STOPPING_KIND = "exit_nonzero"
COMPLETE_PAIR, LEAN_BEFORE_STREAK, LEAN_ONLY, FULL_ONLY = "task-1", "task-2", "task-3", "task-4"
LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NOT_REACHED = "task-5", "task-6", "task-7", "task-8"
PLANNED = (
    COMPLETE_PAIR,
    LEAN_BEFORE_STREAK,
    LEAN_ONLY,
    FULL_ONLY,
    LEAN_IN_STREAK,
    BOTH_IN_STREAK,
    REFUSED,
    NOT_REACHED,
)
EIGHT_SHAPES = {
    "a complete pair": COMPLETE_PAIR,
    "a lean session of the stopping kind and tail before the streak": LEAN_BEFORE_STREAK,
    "a lean-only error of another kind": LEAN_ONLY,
    "a full-only error of another kind": FULL_ONLY,
    "a full session complete and its lean session inside the streak": LEAN_IN_STREAK,
    "both sessions inside the streak": BOTH_IN_STREAK,
    "a launch the spend cap refused": REFUSED,
    "a task never launched": NOT_REACHED,
}
LAUNCHED_AGAIN = {LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NOT_REACHED}


def failed(task: str, arm: str, kind: str = STOPPING_KIND, tail: str = STOPPING_TAIL):
    status = Errored(kind, "the session failed", tails=EvidenceTail(tail, ""))  # type: ignore[arg-type]
    return session(task, arm, status)


def stopped_at(*streak: tuple[str, int], arm: str = "lean", tail: str = STOPPING_TAIL):
    sessions = tuple(Launched(task, arm, attempt) for task, attempt in streak)  # type: ignore[arg-type]
    masked = EvidenceTail(tail, "").masked()
    return InfraStopped(
        StopReason(STOPPING_KIND, masked, "researcher", arm, sessions, "both-arms")  # type: ignore[arg-type]
    )


def stopped_run(sessions, ending: RunEnding, planned=PLANNED) -> results.RunResults:
    extra = {"tasks": {"researcher": list(planned)}, "ending": ending_to_json(ending)}
    return run_results(sessions, extra=extra)


def eight_shapes_run() -> results.RunResults:
    """The streak is the last three lean sessions: the lean retry pair of one task, then one
    more; the full arm of the last streak task failed the same way inside the window."""
    sessions = [
        *pair_of_sessions(COMPLETE_PAIR),
        session(LEAN_BEFORE_STREAK, "full"),
        *[failed(LEAN_BEFORE_STREAK, "lean")] * 2,
        session(LEAN_ONLY, "full"),
        *[failed(LEAN_ONLY, "lean", "no_result_event", "")] * 2,
        *[failed(FULL_ONLY, "full", "envelope_unparseable", "")] * 2,
        session(FULL_ONLY, "lean"),
        failed(REFUSED, "full", "launch_refused", ""),
        failed(REFUSED, "lean", "launch_refused", ""),
        session(LEAN_IN_STREAK, "full"),
        *[failed(LEAN_IN_STREAK, "lean")] * 2,
        *[failed(BOTH_IN_STREAK, "full")] * 2,
        failed(BOTH_IN_STREAK, "lean"),
    ]
    streak = ((LEAN_IN_STREAK, 1), (LEAN_IN_STREAK, 2), (BOTH_IN_STREAK, 1))
    return stopped_run(sessions, stopped_at(*streak))


@pytest.mark.parametrize("task", EIGHT_SHAPES.values(), ids=EIGHT_SHAPES.keys())
def test_a_task_is_launched_again_only_when_nothing_finished_it(task: str) -> None:
    relaunched = relaunch_tasks(eight_shapes_run(), "researcher")

    assert (task in relaunched) == (task in LAUNCHED_AGAIN)


def test_the_tasks_launched_again_keep_the_order_the_run_planned_them_in() -> None:
    assert relaunch_tasks(eight_shapes_run(), "researcher") == (
        LEAN_IN_STREAK,
        BOTH_IN_STREAK,
        REFUSED,
        NOT_REACHED,
    )


def test_the_sessions_never_launched_are_the_refused_ones_and_those_in_the_streak() -> None:
    run = eight_shapes_run()

    ignored = [
        (r.setup.task_id, r.setup.arm)
        for i, r in enumerate(run.sessions)
        if i in never_launched(run)
    ]

    assert ignored == [
        (REFUSED, "full"),
        (REFUSED, "lean"),
        (LEAN_IN_STREAK, "lean"),
        (LEAN_IN_STREAK, "lean"),
        (BOTH_IN_STREAK, "full"),
        (BOTH_IN_STREAK, "full"),
        (BOTH_IN_STREAK, "lean"),
    ]


def test_a_full_session_of_the_stopping_kind_and_tail_before_the_streak_keeps_its_outcome() -> None:
    sessions = [
        *[failed("early", "full")] * 2,
        session("early", "lean"),
        session("late", "full"),
        *[failed("late", "lean")] * 3,
    ]
    streak = (("late", 1), ("late", 2), ("late", 3))
    run = stopped_run(sessions, stopped_at(*streak), ("early", "late"))

    assert relaunch_tasks(run, "researcher") == ("late",)


def test_a_full_session_of_another_tail_inside_the_streaks_window_keeps_its_outcome() -> None:
    other = "fatal: another channel failed"
    sessions = [
        session("b", "lean"),
        session("a", "full"),
        failed("a", "lean"),
        *[failed("b", "full", tail=other)] * 2,
        session("c", "full"),
        *[failed("c", "lean")] * 2,
    ]
    run = stopped_run(sessions, stopped_at(("a", 1), ("c", 1), ("c", 2)), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("a", "c")


def test_a_full_session_of_another_kind_inside_the_streaks_window_keeps_its_outcome() -> None:
    sessions = [
        session("b", "lean"),
        session("a", "full"),
        failed("a", "lean"),
        *[failed("b", "full", "no_result_event", STOPPING_TAIL)] * 2,
        session("c", "full"),
        *[failed("c", "lean")] * 2,
    ]
    run = stopped_run(sessions, stopped_at(("a", 1), ("c", 1), ("c", 2)), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("a", "c")


def test_a_lean_session_that_retried_into_a_measured_one_with_a_full_session_is_a_pair() -> None:
    sessions = [
        session("a", "full"),
        failed("a", "lean", "no_result_event", ""),
        session("a", "lean"),
    ]
    run = stopped_run(sessions, Interrupted(), ("a",))

    assert relaunch_tasks(run, "researcher") == ()


def test_an_interrupted_run_launches_again_the_tasks_it_never_finished() -> None:
    sessions = [*pair_of_sessions("a"), session("b", "full")]
    run = stopped_run(sessions, Interrupted(), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("b", "c")


def test_a_spend_refusal_launches_again_the_refused_tasks_and_the_unreached_ones() -> None:
    sessions = [
        *pair_of_sessions("a"),
        failed("b", "full", "launch_refused", ""),
        failed("b", "lean", "launch_refused", ""),
    ]
    run = stopped_run(sessions, SpendRefused(("b",)), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("b", "c")


def test_a_run_that_recorded_no_session_launches_every_planned_task() -> None:
    assert relaunch_tasks(stopped_run([], Interrupted(), ("a", "b")), "researcher") == ("a", "b")


def test_a_session_recorded_before_tails_were_kept_counts_as_one_with_an_empty_tail() -> None:
    old = session("b", "full", Errored(STOPPING_KIND, "the session failed"))  # type: ignore[arg-type]
    sessions = [
        session("b", "lean"),
        failed("a", "lean", tail=""),
        old,
        failed("c", "lean", tail=""),
    ]
    run = stopped_run(sessions, stopped_at(("a", 1), ("c", 1), tail=""), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("a", "b", "c")


def test_a_stop_naming_sessions_the_arm_did_not_end_on_is_refused() -> None:
    sessions = [failed("a", "lean"), session("b", "lean")]
    run = stopped_run(sessions, stopped_at(("a", 1)), ("a", "b"))

    with pytest.raises(ValueError, match=r"the stop names sessions that the researcher lean arm"):
        relaunch_tasks(run, "researcher")


def test_a_stop_naming_no_session_is_refused() -> None:
    run = stopped_run([failed("a", "lean")], stopped_at(), ("a",))

    with pytest.raises(ValueError, match=r"the stop names sessions"):
        relaunch_tasks(run, "researcher")


def test_a_run_that_planned_no_tasks_for_the_role_is_refused() -> None:
    run = run_results([], extra={"tasks": {}, "ending": ending_to_json(Interrupted())})

    with pytest.raises(ValueError, match=r"a run's planned tasks lacks 'researcher'"):
        relaunch_tasks(run, "researcher")
