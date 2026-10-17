"""The flip gate reads `omitClaudeMd` one way, pins eligibility apart, and never calls a lost log clean.

`omitClaudeMd` is accepted only as a literal true. The eligible roles live apart from the
adoption records and the definitions; a commit that changes them together with a record
or a flag is refused, naming both. The implementer is eligible, at no status, and ready
for a trial: under a ledger holding it at trial its spawn receives its kernel and the
project's instruction file and leaves one row the liveness check judges clean. A
missing or unreadable log segment inside the judged window makes the liveness result
unknown; the same segment outside the window changes nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.acceptance.drivers import flip_gate, kernel_adoption, kernel_sandbox, kernel_spawn
from tests.acceptance.drivers import log_segments as segments
from tests.acceptance.drivers.flip_gate import OMIT, cited_switch_record, switch_with_flag, utc
from tests.acceptance.drivers.kernel_sandbox import (
    ADOPTION_LEDGER,
    PILOT_ROLES,
    REPO_ROOT,
    Sandbox,
    agent_path,
    commit_gate,
    commit_paths,
    frontmatter,
    regenerate,
)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return kernel_sandbox.build_template(tmp_path_factory.mktemp("plugin") / "checkout")


@pytest.fixture
def sandbox(template: Path, tmp_path: Path) -> Sandbox:
    return kernel_sandbox.new_sandbox(template, tmp_path / "plugin")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return kernel_spawn.project_checkout(
        tmp_path / "project", instructions="Project convention: keep fixtures under data/.\n"
    )


# -- omitClaudeMd only as a literal true ---------------------------------------------------------

NOT_LITERAL_TRUE = ["false", "yes", "no", "on", "off", '"true"', "1", "null", ""]


@pytest.mark.parametrize("value", NOT_LITERAL_TRUE, ids=lambda v: v or "empty")
def test_omit_claude_md_set_to_anything_but_a_literal_true_is_refused_naming_it(
    sandbox: Sandbox, value: str
) -> None:
    sandbox.replace(agent_path("researcher"), f"{OMIT}\n", f"omitClaudeMd: {value}".rstrip() + "\n")

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, f"omitClaudeMd: {value!r} was let through"
    assert "researcher" in verdict.output, verdict.output
    assert value.strip('"') in verdict.output, f"the refusal does not name the value {value!r}"


def test_omit_claude_md_as_a_literal_true_with_a_switched_record_passes(sandbox: Sandbox) -> None:
    verdict = commit_gate(sandbox.root)

    assert "omitClaudeMd: true" in sandbox.read(agent_path("researcher"))
    assert not verdict.refused, verdict.output


# -- Eligibility, pinned apart from the flip --------------------------------------------------------


def test_a_commit_changing_the_eligible_roles_and_an_adoption_record_is_refused_naming_both(
    sandbox: Sandbox,
) -> None:
    flip_gate.set_eligible_roles(
        sandbox.root, flip_gate.eligible_roles(sandbox.root) | {"sentinel"}
    )
    kernel_adoption.rewrite(sandbox.root, kernel_adoption.at_trial("verifier"))

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "eligibility and an adoption record changed in one commit"
    assert "eligib" in verdict.output.lower(), verdict.output
    assert "verifier" in verdict.output, verdict.output


def test_a_commit_changing_the_eligible_roles_and_a_flag_is_refused_naming_both(
    sandbox: Sandbox,
) -> None:
    flip_gate.set_eligible_roles(
        sandbox.root, flip_gate.eligible_roles(sandbox.root) | {"sentinel"}
    )
    sandbox.replace(agent_path("researcher"), f"{OMIT}\n", "")

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, "eligibility and a definition's flag changed in one commit"
    assert "eligib" in verdict.output.lower(), verdict.output
    assert "researcher" in verdict.output, verdict.output


def test_a_move_to_switched_of_a_role_eligible_only_from_that_commit_is_refused(
    sandbox: Sandbox,
) -> None:
    role = "systems-architect"
    flip_gate.set_eligible_roles(sandbox.root, flip_gate.eligible_roles(sandbox.root) | {role})
    switch_with_flag(sandbox, cited_switch_record(sandbox.root, role))
    regenerate(sandbox.root)

    verdict = commit_gate(sandbox.root)

    assert verdict.refused, f"{role} was made eligible and switched in one commit"
    assert role in verdict.output, verdict.output


def test_a_commit_changing_only_the_eligible_roles_passes(sandbox: Sandbox) -> None:
    flip_gate.set_eligible_roles(
        sandbox.root, flip_gate.eligible_roles(sandbox.root) | {"sentinel"}
    )

    verdict = commit_gate(sandbox.root)

    assert not verdict.refused, verdict.output


def test_a_flip_commit_edits_nothing_that_holds_the_eligible_roles() -> None:
    held_in = flip_gate.paths_holding_eligible_roles(REPO_ROOT)

    assert held_in, "the eligible roles are pinned nowhere"
    assert ADOPTION_LEDGER not in held_in
    assert not any(path.startswith("agents/") for path in held_in)


def test_the_implementer_is_eligible_beside_the_five_pilot_roles_and_no_other(
    sandbox: Sandbox,
) -> None:
    assert flip_gate.eligible_roles(REPO_ROOT) == {*PILOT_ROLES, "implementer"}


# -- The implementer, ready for a trial ---------------------------------------------------------------


def test_the_committed_adoption_ledger_records_no_status_for_the_implementer() -> None:
    ledger = yaml.safe_load((REPO_ROOT / ADOPTION_LEDGER).read_text(encoding="utf-8"))

    assert "implementer" not in (ledger.get("roles") or {})


def test_the_implementers_definition_still_inherits_its_instruction_files() -> None:
    definition = frontmatter((REPO_ROOT / agent_path("implementer")).read_text(encoding="utf-8"))

    assert "omitClaudeMd" not in definition


def test_an_implementer_at_trial_receives_its_kernel_and_the_projects_instructions_in_one_row(
    sandbox: Sandbox, project: Path
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("implementer"))

    injection = kernel_spawn.spawn(sandbox.root, project, "praxion:implementer")
    rows = kernel_spawn.kernel_rows(project)
    report = flip_gate.liveness(project, sandbox.root)

    assert injection.strings, "the implementer at trial received no kernel"
    assert any("keep fixtures under data/" in s for s in injection.strings)
    assert [kernel_spawn.describe_kernel_row(r).role for r in rows] == ["implementer"]
    assert report.clean, report.output


def test_an_implementer_spawn_at_trial_without_its_row_is_reported_missing(
    sandbox: Sandbox, project: Path
) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("implementer"))
    kernel_spawn.unregister_kernel_hooks(sandbox.root)

    kernel_spawn.spawn(sandbox.root, project, "praxion:implementer")

    assert "implementer" in flip_gate.liveness(project, sandbox.root).output


# -- Liveness over a log it cannot read whole ------------------------------------------------------


def archived(project: Path, position: int, when) -> Path:
    state_dir = segments.state_dir_of(project)
    path = segments.archive_position_path(state_dir, position)
    segments.append_rows(
        state_dir,
        [{"timestamp": when.isoformat(), "event_type": "padding", "session_id": "old"}],
        segment=path,
    )
    flip_gate.set_segment_time(path, when)
    return path


def researcher_at_trial_spawned(sandbox: Sandbox, project: Path, *, hook: bool) -> None:
    kernel_adoption.record(sandbox.root, kernel_adoption.at_trial("researcher"))
    commit_paths(sandbox.root, "ledger: researcher at trial", ADOPTION_LEDGER)
    if not hook:
        kernel_spawn.unregister_kernel_hooks(sandbox.root)
    kernel_spawn.spawn(sandbox.root, project, "praxion:researcher")


@pytest.mark.skipif(segments.running_as_root(), reason="root reads a file whatever its mode")
def test_an_unreadable_segment_inside_the_window_makes_liveness_unknown_naming_it(
    sandbox: Sandbox, project: Path
) -> None:
    segments.require_archive_positions(2)
    researcher_at_trial_spawned(sandbox, project, hook=False)
    archived(project, 2, utc(2026, 9, 1))
    lost = archived(project, 1, utc(2026, 10, 14))
    segments.make_unreadable(lost)

    report = flip_gate.liveness(project, sandbox.root)
    segments.make_readable(lost)

    assert not report.clean, "liveness exited clean over a segment it could not read"
    assert "unknown" in report.output.lower(), report.output
    assert lost.name in report.output, report.output
    assert "researcher" in report.output, "a finding from a readable segment was dropped"


def test_a_missing_segment_inside_the_window_makes_liveness_unknown(
    sandbox: Sandbox, project: Path
) -> None:
    segments.require_archive_positions(3)
    researcher_at_trial_spawned(sandbox, project, hook=True)
    archived(project, 3, utc(2026, 9, 1))
    archived(project, 1, utc(2026, 10, 15))

    report = flip_gate.liveness(project, sandbox.root)

    assert not report.clean, "liveness exited clean over a gap in its segments"
    assert "unknown" in report.output.lower(), report.output


@pytest.mark.skipif(segments.running_as_root(), reason="root reads a file whatever its mode")
def test_an_unreadable_segment_wholly_before_the_window_changes_nothing(
    sandbox: Sandbox, project: Path
) -> None:
    segments.require_archive_positions(2)
    researcher_at_trial_spawned(sandbox, project, hook=True)
    archived(project, 2, utc(2026, 8, 1))
    old = archived(project, 1, utc(2026, 9, 1))
    segments.make_unreadable(old)

    report = flip_gate.liveness(project, sandbox.root)
    segments.make_readable(old)

    assert report.clean, report.output
