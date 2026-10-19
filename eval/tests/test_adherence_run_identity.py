"""What a run was measured on: the tree digest counts what a role runs on and nothing else, a
legacy file's roles are derived from its commit, `diff` names every difference, and the runner
records the identity it began with."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from praxion_evals.adherence import results
from praxion_evals.adherence.infra_stop import StopRule
from praxion_evals.adherence.run_identity import (
    MeasuredIdentity,
    RoleIdentity,
    UnknownIdentity,
    at_commit,
    current_identity,
    diff,
    measured_identity,
    role_identity,
    tree_digest,
    working_tree,
)
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.adherence_run_support import (
    REPO_ROOT,
    ROLE,
    Script,
    run_small,
)
from tests.test_adherence_report import results_of

pytestmark = pytest.mark.usefixtures("full_first", "unswitched_checkout")

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


class Reports(Script):
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
    paid(Script())

    loaded = run_small(tmp_path)[1]

    recorded = loaded.run.extra["identity"]
    definition = (REPO_ROOT / "agents" / f"{ROLE}.md").read_bytes()
    assert set(recorded) == {"tree", "model", "roles"}
    assert len(recorded["tree"]) == len(hashlib.sha256().hexdigest())
    assert recorded["roles"][ROLE]["definition_sha"] == hashlib.sha256(definition).hexdigest()


def test_a_run_whose_sessions_report_no_model_records_none(paid: Any, tmp_path: Path) -> None:
    paid(Script())

    assert run_small(tmp_path)[1].run.extra["identity"]["model"] is None


def test_a_run_records_the_model_its_first_session_reported_and_keeps_it(
    paid: Any, tmp_path: Path
) -> None:
    paid(Reports())

    loaded = run_small(tmp_path)[1]

    assert loaded.run.extra["identity"]["model"] == "model-1"


def test_the_identity_a_run_wrote_reads_back_as_the_one_it_began_with(
    paid: Any, tmp_path: Path
) -> None:
    paid(Reports(REPORTED))

    loaded = run_small(tmp_path)[1]

    identity = measured_identity(loaded, REPO_ROOT)
    assert (identity.model, identity.seed) == (REPORTED, loaded.run.extra["seed"])
    assert identity.roles == {ROLE: role_identity(working_tree(REPO_ROOT), ROLE)}


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
