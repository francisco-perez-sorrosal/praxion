"""Tests for check_kernel_manifest.py -- the commit gate holding the kernels to their sources.

Each invariant has a canary: a known-bad input that makes the checker report its kind, shown
here over a copy of the live inputs (the rules, the template, the agents, the kernels, the
manifest, the preamble) with one thing broken. A clean copy is the inverse guard: it must
report nothing, so a canary that fails does so for the break and not for the fixture.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
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
