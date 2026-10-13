"""Tests for check_kernel_manifest.py -- the commit gate holding the kernels to their sources.

Each invariant has a canary: a known-bad input that makes the checker report its kind, shown
here over a copy of the live inputs (the rules, the template, the agents, the kernels, the
manifest, the preamble) with one thing broken. A clean copy is the inverse guard: it must
report nothing, so a canary that fails does so for the break and not for the fixture.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_kernel_manifest as cb  # noqa: E402
import generate_kernels as gk  # noqa: E402
import kernel_model as km  # noqa: E402
import kernel_sources as ks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_kernel_manifest.py"
CAP = km.MAX_STRING_CHARS

COPIED = (
    "rules",
    "agents",
    "claude/kernels",
    "claude/config/CLAUDE.md.tmpl",
    "CLAUDE.md",
    gk.PREAMBLE_PATH,
)
UNIFIED_RULE = "rules/swe/agent-intermediate-documents.md"
PROBE_HEADING = "Resident Probe Section"
PROBE_SECTION = f"\n## {PROBE_HEADING}\n\nA paragraph that no audience entry classifies yet.\n"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("kernel-inputs") / "checkout"
    for rel in COPIED:
        source, target = REPO_ROOT / rel, root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, target)
    return root


@pytest.fixture
def repo(template: Path, tmp_path: Path) -> Path:
    shutil.copytree(template, tmp_path / "checkout")
    return tmp_path / "checkout"


def kinds(root: Path) -> set[str]:
    return {finding.kind for finding in cb.check(root)}


def subjects(root: Path, kind: str) -> list[str]:
    return [finding.subject for finding in cb.check(root) if finding.kind == kind]


def edit_manifest(root: Path, change: Callable[[dict], None]) -> None:
    path = root / km.MANIFEST_PATH
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(manifest)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, width=100), encoding="utf-8")


def edit_index(root: Path, change: Callable[[dict], None]) -> None:
    path = root / km.INDEX_PATH
    index = json.loads(path.read_text(encoding="utf-8"))
    change(index)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


# -- The inverse guard ------------------------------------------------------------------


def test_the_live_inputs_hold_every_invariant(repo: Path) -> None:
    assert cb.check(repo) == ()


# -- I1: every section and part classified ---------------------------------------------


def test_a_new_heading_without_an_entry_is_reported_by_name(repo: Path) -> None:
    append(repo, UNIFIED_RULE, PROBE_SECTION)

    assert subjects(repo, "I1-unclassified") == [f"{UNIFIED_RULE} '{PROBE_HEADING}'"]


def test_a_renamed_heading_reports_the_new_section_and_the_orphaned_entry(repo: Path) -> None:
    path = repo / UNIFIED_RULE
    renamed = path.read_text(encoding="utf-8").replace(
        "### Version Control and Cleanup\n", "### Cleanup and Version Control\n"
    )
    path.write_text(renamed, encoding="utf-8")

    found = {(f.kind, f.subject) for f in cb.check(repo)}

    assert ("I1-unclassified", f"{UNIFIED_RULE} 'Cleanup and Version Control'") in found
    assert ("I1-orphan", f"{UNIFIED_RULE} 'Version Control and Cleanup'") in found


def test_a_new_rule_without_a_path_scope_is_covered_without_a_list(repo: Path) -> None:
    (repo / "rules/swe/resident-probe.md").write_text(
        f"## Resident Probe Rule\n\nAn always-loaded rule.\n{PROBE_SECTION}", encoding="utf-8"
    )

    assert subjects(repo, "I1-unclassified") == [
        "rules/swe/resident-probe.md 'Resident Probe Rule'",
        f"rules/swe/resident-probe.md '{PROBE_HEADING}'",
    ]


def test_a_new_heading_in_a_path_scoped_rule_needs_no_entry(repo: Path) -> None:
    append(repo, "rules/swe/testing-conventions.md", PROBE_SECTION)

    assert cb.check(repo) == ()


def test_the_leading_part_of_a_mixed_section_must_be_classified(repo: Path) -> None:
    append(
        repo,
        UNIFIED_RULE,
        f"\n## {PROBE_HEADING}\n\nAlpha part: orchestrator text.\n\nBeta part: role text.\n",
    )
    edit_manifest(
        repo,
        lambda m: m["entries"].append(
            {
                "source": UNIFIED_RULE,
                "heading": PROBE_HEADING,
                "part": "Beta part:",
                "scope": "no-actor",
                "reason": "probe text",
            }
        ),
    )

    found = [f for f in cb.check(repo) if f.kind == "I1-unclassified"]

    assert [f.subject for f in found] == [f"{UNIFIED_RULE} '{PROBE_HEADING}'"]
    assert "Alpha part" in found[0].detail


def test_two_sections_of_one_heading_are_reported_as_ambiguous(repo: Path) -> None:
    heading = "Version Control and Cleanup"
    append(repo, UNIFIED_RULE, f"\n### {heading}\n\nA second section of that heading.\n")

    assert subjects(repo, "I1-duplicate-heading") == [f"{UNIFIED_RULE} '{heading}'"]


# -- I2: a kernel core for every agent --------------------------------------------------


def test_an_agent_the_index_does_not_list_has_no_core(repo: Path) -> None:
    edit_index(repo, lambda index: index["roles"].pop("researcher"))

    assert subjects(repo, "I2-missing-core") == ["agent researcher"]


def test_an_agent_whose_strings_are_empty_has_no_core(repo: Path) -> None:
    edit_index(repo, lambda index: index["roles"]["verifier"].update(strings=[]))

    assert subjects(repo, "I2-missing-core") == ["agent verifier"]


def test_a_new_agent_definition_nobody_regenerated_has_no_core(repo: Path) -> None:
    text = (repo / "agents/doc-engineer.md").read_text(encoding="utf-8")
    (repo / "agents/probe-engineer.md").write_text(
        text.replace("name: doc-engineer\n", "name: probe-engineer\n", 1), encoding="utf-8"
    )

    assert subjects(repo, "I2-missing-core") == ["agent probe-engineer"]


def test_no_core_file_means_no_agent_has_a_core(repo: Path) -> None:
    (repo / gk.KERNELS_DIR / "core.md").unlink()

    assert "I2-missing-core" in kinds(repo)


def test_a_missing_index_is_reported_once_not_per_agent(repo: Path) -> None:
    (repo / km.INDEX_PATH).unlink()

    assert subjects(repo, "I2-missing-core") == [km.INDEX_PATH]


# -- I3: the core carries the contract rule's own text -------------------------------------


def test_a_contract_line_changed_in_the_rule_but_not_the_core_is_drift(repo: Path) -> None:
    path = repo / gk.CONTRACT_SOURCE
    path.write_text(
        path.read_text(encoding="utf-8").replace("**Stay Surgical**", "**Stay Precise**"),
        encoding="utf-8",
    )

    found = [f for f in cb.check(repo) if f.kind == "I3-contract-drift"]

    assert {f.subject for f in found} == {
        f"{gk.KERNELS_DIR}/{gk.BLOCKS_FILE}",
        f"{gk.KERNELS_DIR}/core.md",
        gk.PREAMBLE_PATH,
    }
    assert any("Stay Precise" in f.detail for f in found)


def test_a_core_whose_contract_entry_was_reclassified_is_drift(repo: Path) -> None:
    def withhold(manifest: dict) -> None:
        manifest["entries"] = [
            {**e, "scope": "no-actor", "form": None, "reason": "probe"}
            if (e["source"], e["heading"], e["scope"])
            == (gk.CONTRACT_SOURCE, gk.CONTRACT_HEADING, "core")
            else e
            for e in manifest["entries"]
        ]

    edit_manifest(repo, withhold)

    assert subjects(repo, "I3-contract-drift") == [f"{gk.CONTRACT_SOURCE} '{gk.CONTRACT_HEADING}'"]


def test_a_preamble_not_derived_from_the_contract_is_drift(repo: Path) -> None:
    append(repo, gk.PREAMBLE_PATH, "# an edit by hand\n")

    assert subjects(repo, "I3-contract-drift") == [gk.PREAMBLE_PATH]


def test_a_missing_preamble_is_drift(repo: Path) -> None:
    (repo / gk.PREAMBLE_PATH).unlink()

    assert subjects(repo, "I3-contract-drift") == [gk.PREAMBLE_PATH]


def test_a_missing_blocks_file_is_drift(repo: Path) -> None:
    (repo / gk.KERNELS_DIR / gk.BLOCKS_FILE).unlink()

    assert subjects(repo, "I3-contract-drift") == [f"{gk.KERNELS_DIR}/{gk.BLOCKS_FILE}"]


def test_the_contract_block_is_read_up_to_its_own_paragraph_end(repo: Path) -> None:
    blocks = repo / gk.KERNELS_DIR / gk.BLOCKS_FILE
    first, rest = blocks.read_text(encoding="utf-8").split("\n\n", 1)
    blocks.write_text(f"{first}\nAn extra line.\n\n{rest}", encoding="utf-8")

    found = [f for f in cb.check(repo) if f.kind == "I3-contract-drift"]

    assert [f.subject for f in found] == [f"{gk.KERNELS_DIR}/{gk.BLOCKS_FILE}"]
    assert "An extra line." in found[0].detail


# -- I4: nothing injected passes the cap ------------------------------------------------------


def test_a_module_over_the_cap_fed_directly_is_over_cap() -> None:
    found = cb.cap_findings({"claude/kernels/probe.md": "x" * (CAP + 1)})

    assert [(f.kind, f.subject) for f in found] == [("I4-over-cap", "claude/kernels/probe.md")]
    assert str(CAP + 1) in found[0].detail


def test_a_text_exactly_at_the_cap_fits() -> None:
    assert cb.cap_findings({"claude/kernels/probe.md": "x" * CAP}) == ()


def test_a_committed_kernel_file_over_the_cap_is_reported(repo: Path) -> None:
    append(repo, f"{gk.KERNELS_DIR}/core.md", "\n" + "padding " * (CAP // 8 + 1))

    assert subjects(repo, "I4-over-cap") == [f"{gk.KERNELS_DIR}/core.md"]


def test_an_injected_string_over_the_cap_is_reported_without_refusing_the_index(
    repo: Path,
) -> None:
    edit_index(repo, lambda index: index["roles"]["sentinel"]["strings"].append("x" * (CAP + 1)))

    assert subjects(repo, "I4-over-cap") == [f"{km.INDEX_PATH} sentinel string 2"]


# -- I5: the writer groups equal what the definitions write -----------------------------------


def test_an_adr_author_group_that_lists_an_agent_who_writes_no_draft_is_a_mismatch(
    repo: Path,
) -> None:
    edit_manifest(repo, lambda m: m["groups"][km.ADR_AUTHOR].append("researcher"))

    found = [f for f in cb.check(repo) if f.kind == "I5-group-mismatch"]

    assert [f.subject for f in found] == ["group adr-author"]
    assert "researcher" in found[0].detail


def test_a_ledger_writer_left_out_of_the_group_is_a_mismatch(repo: Path) -> None:
    edit_manifest(repo, lambda m: m["groups"][km.LEDGER_WRITER].remove("verifier"))

    found = [f for f in cb.check(repo) if f.kind == "I5-group-mismatch"]

    assert [f.subject for f in found] == ["group ledger-writer"]
    assert "verifier" in found[0].detail


def test_a_new_ledger_writing_agent_missing_from_the_group_is_a_mismatch(repo: Path) -> None:
    text = (repo / "agents/sentinel.md").read_text(encoding="utf-8")
    (repo / "agents/probe-sentinel.md").write_text(
        text.replace("name: sentinel\n", "name: probe-sentinel\n", 1), encoding="utf-8"
    )

    found = [f for f in cb.check(repo) if f.kind == "I5-group-mismatch"]

    assert any("probe-sentinel" in f.detail for f in found)


# -- I6: a condensed form's pin matches its source --------------------------------------------


def entry_where(
    root: Path, wanted: Callable[[km.AudienceEntry], bool]
) -> tuple[km.AudienceEntry, str]:
    """The first manifest entry `wanted` accepts, with the source bytes it covers."""
    evidence = cb.gather(root)
    texts = km.entry_texts(evidence.manifest, evidence.sections)
    entry = next(e for e in evidence.manifest.entries if e in texts and wanted(e))
    return entry, texts[entry]


def amend_source(root: Path, entry: km.AudienceEntry, covered: str) -> None:
    """Add a word to the last line of the source text `entry` covers."""
    path = root / entry.target.source
    stripped = covered.rstrip("\n")
    path.write_text(
        path.read_text(encoding="utf-8").replace(stripped, f"{stripped} Amended.", 1),
        encoding="utf-8",
    )


def is_authored_condensation(entry: km.AudienceEntry) -> bool:
    form = entry.form
    return isinstance(form, km.Condensed) and form.text_ref not in gk.BLOCK_TEXTS


def test_a_condensed_form_whose_source_changed_since_it_was_pinned_is_stale(repo: Path) -> None:
    entry, covered = entry_where(repo, is_authored_condensation)
    amend_source(repo, entry, covered)

    assert subjects(repo, "I6-stale-pin") == [f"{entry.target.source} '{entry.target.heading}'"]


def test_a_source_changed_where_the_form_is_verbatim_needs_no_pin(repo: Path) -> None:
    entry, covered = entry_where(repo, lambda e: isinstance(e.form, km.Verbatim))
    amend_source(repo, entry, covered)

    assert subjects(repo, "I6-stale-pin") == []


# -- I7: nothing the main session keeps resident reaches a spawn ---------------------------------


def resident_text(root: Path, scope: type) -> tuple[km.AudienceEntry, str]:
    return entry_where(root, lambda e: isinstance(e.scope, scope))


@pytest.mark.parametrize("scope", [km.OrchestratorOnly, km.NoActor])
def test_resident_text_added_to_a_committed_kernel_is_reported_with_its_section(
    repo: Path, scope: type
) -> None:
    entry, covered = resident_text(repo, scope)
    append(repo, f"{gk.KERNELS_DIR}/core.md", "\n" + covered)

    found = [f for f in cb.check(repo) if f.kind == "I7-resident-text-in-kernel"]

    assert [f.subject for f in found] == [f"{gk.KERNELS_DIR}/core.md"]
    assert entry.target.heading in found[0].detail


def test_resident_text_added_to_an_injected_string_is_reported_with_its_role(repo: Path) -> None:
    _, covered = resident_text(repo, km.OrchestratorOnly)

    def leak(index: dict) -> None:
        strings = index["roles"]["sentinel"]["strings"]
        strings[0] = strings[0] + "\n\n" + covered

    edit_index(repo, leak)

    assert f"{km.INDEX_PATH} sentinel string 1" in subjects(repo, "I7-resident-text-in-kernel")


def test_a_heading_shared_with_a_resident_section_is_not_its_text(repo: Path) -> None:
    entry, _ = resident_text(repo, km.OrchestratorOnly)
    append(repo, f"{gk.KERNELS_DIR}/core.md", f"\n## {entry.target.heading}\n")

    assert subjects(repo, "I7-resident-text-in-kernel") == []


# -- I8: no kernel is stale ----------------------------------------------------------------------


def test_a_rule_edit_nobody_regenerated_leaves_the_kernels_stale(repo: Path) -> None:
    entry, covered = entry_where(
        repo, lambda e: isinstance(e.scope, km.Role) and isinstance(e.form, km.Verbatim)
    )
    amend_source(repo, entry, covered)

    assert f"{gk.KERNELS_DIR}/{entry.scope.module}.md" in subjects(repo, "I8-stale-kernel")


def test_an_index_edited_by_hand_is_stale(repo: Path) -> None:
    edit_index(repo, lambda index: index["roles"]["sentinel"].update(status="trial"))

    assert subjects(repo, "I8-stale-kernel") == [km.INDEX_PATH]


def test_a_definition_whose_block_was_edited_by_hand_is_stale(repo: Path) -> None:
    path = repo / "agents/researcher.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "**Apply the behavioral contract**", "**Apply the behavioural contract**", 1
        ),
        encoding="utf-8",
    )

    assert subjects(repo, "I8-stale-kernel") == ["agents/researcher.md"]


def test_a_kernel_file_no_source_produces_is_stale(repo: Path) -> None:
    (repo / gk.KERNELS_DIR / "stray.md").write_text("A stray kernel.\n", encoding="utf-8")

    assert subjects(repo, "I8-stale-kernel") == [f"{gk.KERNELS_DIR}/stray.md"]


def test_sources_the_generator_cannot_assemble_are_reported_with_its_reason(repo: Path) -> None:
    authored = next(a for a in cb.gather(repo).manifest.authored if a.id == gk.RETURN_TEXT)
    (repo / authored.path).unlink()

    found = [f for f in cb.check(repo) if f.kind == "I8-stale-kernel"]

    assert [f.subject for f in found] == [gk.KERNELS_DIR]
    assert authored.path in found[0].detail


def test_sources_that_fail_the_totality_check_are_reported_once_not_twice(repo: Path) -> None:
    append(repo, UNIFIED_RULE, PROBE_SECTION)

    assert kinds(repo) == {"I1-unclassified"}


# -- I9: a role is flipped only with its record -------------------------------------------------

ADHERENCE = cb.ADHERENCE_ENTRY
PILOT = ["researcher", "verifier", "discipline-consultant", "skill-genesis", "context-engineer"]
RECORD_PIECES = [
    "passing_run",
    "probe_before_tokens",
    "probe_after_tokens",
    "flip_rule_ratified",
    "flip_ratified",
]


def run_row(pairs: int = 24, passes: bool = True, eval_entry: str = ADHERENCE) -> dict:
    return {"id": "r1", "complete_pairs": pairs, "passes_flip_rule": passes, "entry": eval_entry}


def switched_row(**fields: object) -> dict:
    row = {
        "status": "switched",
        "since": "2026-10-12",
        "runs": [run_row()],
        "passing_run": "r1",
        "probe_before_tokens": 31_000,
        "probe_after_tokens": 22_000,
        "flip_rule_ratified": True,
        "flip_ratified": True,
    }
    return {**row, **fields}


def trial_row() -> dict:
    return {"status": "trial", "since": "2026-10-12", "runs": []}


def write_ledger(root: Path, **roles: dict) -> None:
    path = root / km.LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = {"version": 1, "eligible": PILOT, "roles": roles}
    path.write_text(yaml.safe_dump(ledger, sort_keys=False), encoding="utf-8")


def omit_claude_md(root: Path, role: str, value: str = "true") -> None:
    path = root / f"agents/{role}.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f"name: {role}\n", f"name: {role}\nomitClaudeMd: {value}\n", 1
        ),
        encoding="utf-8",
    )


def regenerate(root: Path) -> None:
    gk.write_files(root, gk.plan_kernels(root).files)


def commit_all(root: Path, at: str = "2026-10-13T12:00:00+00:00") -> None:
    """Commit everything under `root` (a repository of its own) at the moment `at`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_DATE=at, GIT_COMMITTER_DATE=at)
    identity = ["-c", "user.name=Probe", "-c", "user.email=probe@example.invalid"]
    steps = (["init", "-q"], ["add", "-A"], [*identity, "commit", "-q", "--no-verify", "-m", "x"])
    for step in steps:
        subprocess.run(
            ["git", *step], cwd=root, env=env, check=True, capture_output=True, timeout=60
        )


def flipped(root: Path, role: str = "researcher", **fields: object) -> None:
    """The role flipped with the record `fields` alter: ledger, flag and regenerated kernels."""
    write_ledger(root, **{role: switched_row(**fields)})
    omit_claude_md(root, role)
    regenerate(root)


def test_a_role_flipped_with_its_full_record_passes(repo: Path) -> None:
    flipped(repo)

    assert cb.check(repo) == ()


def test_the_flag_without_any_record_is_reported_by_role(repo: Path) -> None:
    omit_claude_md(repo, "researcher")

    found = [f for f in cb.check(repo) if f.kind == "I9-flip-without-record"]

    assert [f.subject for f in found] == ["role researcher"]
    assert "absent" in found[0].detail


def test_the_flag_on_a_role_still_at_trial_is_reported(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    omit_claude_md(repo, "researcher")
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-flip-without-record"]

    assert [(f.subject, "trial" in f.detail) for f in found] == [("role researcher", True)]


@pytest.mark.parametrize("value", ["false", "False", ""])
def test_a_flag_set_to_false_or_left_empty_does_not_switch_a_role(repo: Path, value: str) -> None:
    omit_claude_md(repo, "researcher", value)

    assert subjects(repo, "I9-flip-without-record") == []


@pytest.mark.parametrize("value", ["true", "True", "yes", "'true'"])
def test_any_value_but_false_counts_as_the_flag(repo: Path, value: str) -> None:
    omit_claude_md(repo, "researcher", value)

    assert subjects(repo, "I9-flip-without-record") == ["role researcher"]


def test_a_switched_record_without_the_flag_is_reported(repo: Path) -> None:
    write_ledger(repo, researcher=switched_row())
    regenerate(repo)

    assert subjects(repo, "I9-switch-without-flag") == ["role researcher"]


@pytest.mark.parametrize("missing", RECORD_PIECES)
def test_a_flip_missing_a_piece_of_its_record_is_reported_naming_role_and_piece(
    repo: Path, missing: str
) -> None:
    row = switched_row()
    del row[missing]
    write_ledger(repo, researcher=row)
    omit_claude_md(repo, "researcher")
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert len(found) == 1
    assert "researcher" in found[0].detail
    assert missing in found[0].detail


def test_a_flip_resting_on_a_run_of_fewer_than_twenty_pairs_is_reported(repo: Path) -> None:
    flipped(repo, runs=[run_row(pairs=19)])

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert [f.subject for f in found] == [km.LEDGER_PATH]
    assert "19 pairs" in found[0].detail


def test_a_flip_resting_on_a_run_that_fails_the_flip_rule_is_reported(repo: Path) -> None:
    flipped(repo, runs=[run_row(passes=False)])

    assert subjects(repo, "I9-record-incomplete") == [km.LEDGER_PATH]


def test_a_flip_resting_on_a_run_from_another_eval_is_reported_by_role(repo: Path) -> None:
    flipped(repo, runs=[run_row(eval_entry="praxion-evals-live")])

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert [f.subject for f in found] == ["role researcher"]
    assert ADHERENCE in found[0].detail


def test_a_role_outside_the_eligible_list_cannot_be_flipped(repo: Path) -> None:
    flipped(repo, role="implementer")

    found = [f for f in cb.check(repo) if f.kind == "I9-record-incomplete"]

    assert len(found) == 1
    assert "implementer" in found[0].detail


def test_a_ledger_that_is_not_yaml_is_an_input_error_not_a_finding(repo: Path) -> None:
    (repo / km.LEDGER_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / km.LEDGER_PATH).write_text("roles: [unclosed", encoding="utf-8")

    assert run_checker(repo).returncode == 2


def test_a_role_climbing_one_status_from_the_parent_commit_passes(repo: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    regenerate(repo)
    commit_all(repo)

    flipped(repo)

    assert cb.check(repo) == ()


def test_a_role_that_skips_trial_since_the_parent_commit_is_reported(repo: Path) -> None:
    write_ledger(repo)
    regenerate(repo)
    commit_all(repo)

    flipped(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-ledger-transition"]
    assert [(f.subject, f.detail) for f in found] == [("role researcher", "absent -> switched")]


def test_a_role_falling_back_since_the_parent_commit_is_reported(repo: Path) -> None:
    flipped(repo)
    commit_all(repo)

    write_ledger(repo, researcher=trial_row())
    regenerate(repo)

    found = [f for f in cb.check(repo) if f.kind == "I9-ledger-transition"]
    assert [(f.subject, f.detail) for f in found] == [("role researcher", "switched -> trial")]


def test_a_ledger_that_first_appears_in_this_commit_has_no_parent_to_climb_from(
    repo: Path,
) -> None:
    (repo / "README.probe").write_text("committed before the ledger existed\n", encoding="utf-8")
    commit_all(repo)

    flipped(repo)

    assert cb.check(repo) == ()


# -- Liveness: a spawn of an adopted role left its kernel row -----------------------------------

AT = "2026-10-13T14:00:00+00:00"
NOON = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def started(agent_id: str, agent_type: str = "praxion:researcher", at: str = AT) -> dict:
    return {
        "timestamp": at,
        "session_id": "s1",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "event_type": "agent_start",
    }


def delivered(agent_id: str, role: str = "researcher") -> dict:
    return {
        "timestamp": AT,
        "session_id": "s1",
        "agent_id": agent_id,
        "agent_type": f"praxion:{role}",
        "event_type": "kernel_injected",
        "role": role,
    }


def silent(statuses: dict[str, str], *rows: dict) -> list[tuple[str, str]]:
    return [(f.kind, f.subject) for f in cb.liveness_findings(statuses, rows)]


@pytest.mark.parametrize("status", ["trial", "switched"])
def test_a_spawn_of_an_adopted_role_with_no_kernel_row_is_reported_by_role(status: str) -> None:
    assert silent({"researcher": status}, started("a1")) == [
        ("liveness-no-kernel-row", "role researcher")
    ]


def test_a_spawn_that_left_its_kernel_row_is_not_reported() -> None:
    assert silent({"researcher": "switched"}, started("a1"), delivered("a1")) == []


def test_only_the_spawn_without_a_row_is_reported_among_several() -> None:
    rows = [started("a1"), delivered("a1"), started("a2")]

    found = cb.liveness_findings({"researcher": "trial"}, rows)

    assert len(found) == 1
    assert "a2" in found[0].detail


def test_a_spawn_of_a_role_not_adopted_is_not_reported() -> None:
    assert silent({"researcher": "trial"}, started("a1", "praxion:implementer")) == []


@pytest.mark.parametrize(
    "agent_type", ["researcher", "other:researcher", "main", "general-purpose"]
)
def test_a_spawn_that_is_not_an_agent_of_this_plugin_is_not_reported(agent_type: str) -> None:
    assert silent({"researcher": "switched"}, started("a1", agent_type)) == []


def test_a_resume_is_not_a_second_spawn() -> None:
    rows = [started("a1", at="2026-10-13T10:00:00+00:00"), delivered("a1"), started("a1")]

    assert silent({"researcher": "switched"}, *rows) == []


def test_a_resume_after_the_cutoff_does_not_make_an_earlier_spawn_one() -> None:
    rows = [started("a1", at="2026-10-13T10:00:00+00:00"), started("a1", at=AT)]

    assert cb.liveness_findings({"researcher": "switched"}, rows, NOON) == ()


def test_a_spawn_after_the_cutoff_is_reported() -> None:
    found = cb.liveness_findings({"researcher": "switched"}, [started("a1")], NOON)

    assert [f.subject for f in found] == ["role researcher"]


def write_log(project: Path, *rows: dict) -> None:
    state = project / ".ai-state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "observations.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def liveness(plugin: Path, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = ["--liveness", "--repo-root", str(project), "--plugin-root", str(plugin), *args]
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_the_liveness_command_names_the_role_that_left_no_row(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=switched_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))

    result = liveness(repo, project, "--json")

    assert result.returncode == 1
    assert [f["subject"] for f in json.loads(result.stdout)["findings"]] == ["role researcher"]


def test_the_liveness_command_is_clean_when_every_spawn_left_its_row(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"), delivered("a1"))

    result = liveness(repo, project)

    assert (result.returncode, result.stdout.strip()) == (0, "kernel liveness: clean")


def test_the_liveness_command_reads_only_spawns_since_a_revision(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1", at="2026-10-13T10:00:00+00:00"))
    commit_all(project, at="2026-10-13T12:00:00+00:00")

    everything = liveness(repo, project)
    since_head = liveness(repo, project, "--since", "HEAD")

    assert (everything.returncode, since_head.returncode) == (1, 0)


def test_check_liveness_flags_a_spawn_the_plugin_ledger_adopts_but_the_log_shows_no_row_for(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))

    found = cb.check_liveness(project, repo, None)

    assert [f.subject for f in found] == ["role researcher"]


def test_a_revision_that_does_not_exist_is_an_input_error(repo: Path, tmp_path: Path) -> None:
    write_ledger(repo, researcher=trial_row())
    project = tmp_path / "project"
    write_log(project, started("a1"))
    commit_all(project)

    result = liveness(repo, project, "--since", "no-such-revision")

    assert result.returncode == 2
    assert "no-such-revision" in result.stderr


def test_a_project_with_no_observation_log_is_an_input_error_not_a_pass(
    repo: Path, tmp_path: Path
) -> None:
    write_ledger(repo, researcher=switched_row())
    project = tmp_path / "project"
    (project / ".ai-state").mkdir(parents=True)

    result = liveness(repo, project)

    assert result.returncode == 2
    assert "observation log" in result.stderr


def test_since_without_liveness_is_a_usage_error(repo: Path) -> None:
    assert run_checker(repo, "--since", "HEAD").returncode == 2


# -- The command ----------------------------------------------------------------------------


def run_checker(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_a_clean_checkout_exits_zero(repo: Path) -> None:
    result = run_checker(repo)

    assert (result.returncode, result.stdout.strip()) == (0, "kernel manifest: clean")


def test_findings_exit_one_and_name_their_invariant(repo: Path) -> None:
    append(repo, UNIFIED_RULE, PROBE_SECTION)

    result = run_checker(repo)

    assert result.returncode == 1
    assert f"I1-unclassified: {UNIFIED_RULE} '{PROBE_HEADING}'" in result.stdout


def test_the_json_report_carries_each_finding(repo: Path) -> None:
    append(repo, UNIFIED_RULE, PROBE_SECTION)

    report = json.loads(run_checker(repo, "--json").stdout)

    assert report["schema"] == cb.REPORT_SCHEMA
    assert [(f["kind"], f["subject"]) for f in report["findings"]] == [
        ("I1-unclassified", f"{UNIFIED_RULE} '{PROBE_HEADING}'")
    ]


def test_no_manifest_is_an_input_error_not_a_pass(repo: Path) -> None:
    (repo / km.MANIFEST_PATH).unlink()

    result = run_checker(repo)

    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_a_checkout_without_the_user_template_is_an_input_error(repo: Path) -> None:
    (repo / ks.USER_TEMPLATE).unlink()

    result = run_checker(repo)

    assert result.returncode == 2
    assert "not a plugin checkout" in result.stderr


def test_an_unreadable_index_is_an_input_error(repo: Path) -> None:
    (repo / km.INDEX_PATH).write_text("{not json", encoding="utf-8")

    assert run_checker(repo).returncode == 2


# -- The registration -------------------------------------------------------------------------


def _kernel_hook() -> dict:
    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [h for r in config["repos"] for h in r["hooks"] if h["id"] == "kernel-manifest"]
    assert len(hooks) == 1, "the commit gate registers exactly one kernel-manifest hook"
    return hooks[0]


def test_the_commit_gate_runs_the_checker_with_pyyaml_over_the_whole_checkout() -> None:
    hook = _kernel_hook()

    assert "scripts/check_kernel_manifest.py" in hook["entry"]
    assert "pyyaml" in hook["additional_dependencies"]
    assert hook["pass_filenames"] is False


def test_the_hook_runs_for_every_input_the_invariants_read() -> None:
    pattern = re.compile(_kernel_hook()["files"])
    inputs = [
        *ks.always_loaded_sources(REPO_ROOT),
        km.MANIFEST_PATH,
        km.LEDGER_PATH,
        km.INDEX_PATH,
        gk.PREAMBLE_PATH,
        "claude/kernels/src/return-contract.md",
        "agents/researcher.md",
        "hooks/hooks.json",
        "scripts/check_kernel_manifest.py",
        "scripts/kernel_model.py",
        "scripts/kernel_sources.py",
        "scripts/generate_kernels.py",
    ]

    assert [path for path in inputs if not pattern.search(path)] == []
