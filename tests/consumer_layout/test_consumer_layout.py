"""The consumer layout: what a project looks like after Praxion onboards it.

Seven recent defects shared one root cause -- **self-hosting masks them**.
Praxion works because it *is* Praxion: its `permissions.allow` already exists,
its ledgers are already on disk, its templates are the files it ships. Each
defect was invisible from inside this repo and unavoidable from outside it. The
only durable answer is a harness that reasons about a tree that is *not* this
one.

## Where this sits on the verification spectrum, and what it adds

`/onboard-project` is a slash command -- a Markdown body executed by a live
Claude Code session -- so it cannot be invoked from pytest. The existing
per-phase tests in `tests/commands/` therefore validate the *documented*
contract by parsing that Markdown structurally. That is a real technique with a
real limit: it proves the command **says** the right thing, never that executing
it **produces** the right tree.

This harness sits deliberately on both halves:

* **Contract extraction** -- the phase inventory, the write payloads, the
  predicates, and the plugin-side asset set are *derived from the command's own
  text*, never transcribed. A phase added tomorrow enters this harness the
  moment it enters the contract; a hand-written expectation would not.
* **Executable subset** -- every predicate that is a real shell fragment is
  **run for real** against scratch trees built in `tmp_path`: the `grep`s, the
  `test -e`s, the `readlink`s, the `git config` lookup, and the literal `jq`
  merges. Structural tests cannot catch "the documented `jq` is wrong". These
  can, because they execute it.

What that buys over the per-phase tests, concretely:

1. **Write/check closure.** A phase's payload and its idempotency predicate are
   authored independently in two different places, and nothing today proves they
   agree. Here, each payload is written into a scratch tree and its *own*
   predicate is executed against the result.
2. **No predicate is true before onboarding.** Every executable predicate is run
   against a bare `git init` tree and must report "not done". A predicate true on
   an un-onboarded project makes onboarding skip a phase it never performed --
   the exact silent-skip shape of the defects above.
3. **Merge algebra.** The `permissions.allow` and `permissions.deny` merges are
   run as literal `jq`, twice, and in both orders -- proving idempotence and the
   "compose in either order" claim that is otherwise only prose.
4. **Plugin-side asset closure.** Every source path the contract instructs a
   consumer to read must exist in the plugin tree, the same closure property
   `scripts/test_finalize_adrs.py` proves for the hook chain's dependency set.

## What this harness does NOT cover

An honest boundary is worth more than an implied one: a harness *believed* to
cover the whole contract while covering half of it is worse than none, because
it licenses the belief.

* **It does not run `/onboard-project`.** No test here proves the session
  actually performs a phase; they prove the contract it follows is coherent and
  that its mechanical parts work.
* **Prose actions are out of scope** -- the architecture-baseline delegation, the
  CLAUDE.md block refresh classification, and the code-quality phase's template
  rendering and placeholder filling have no extractable command to execute.
* **Host-probe predicates are excluded** (`command -v claude`, `claude plugin
  list`). They interrogate the machine, not the consumer tree, so their truth
  here would say nothing about a consumer.
* **Boolean structure within a predicate row is not modelled.** Fragments are
  evaluated individually. A row's internal AND/OR is not reconstructed, so this
  proves each fragment is false pre-onboarding, not that the row combines them
  correctly.
* **The skeleton write-set is derived from mentions, not from an inventory.**
  There is no external source of truth for which `.ai-state/` files onboarding
  must create, so the derived set is every path the phase names. It is therefore
  robust in the safe direction (a stray mention over-includes) but proves nothing
  about *completeness*: an artifact that was never in the contract cannot be
  detected as missing from it.
* **Payload *semantics* are not judged** -- that the ignore entries are the
  *right* entries, or the grants the *right* grants, is the per-phase tests'
  job. This asserts only that what is written satisfies what is checked.
* **Adjacent gates are not duplicated**: template-versus-live drift belongs to
  `scripts/check_template_mirrors.py`, canonical-block sync to
  `scripts/sync_canonical_blocks.py`, and the greenfield path to
  `tests/new_project_test.sh`.

Everything runs in `tmp_path`; nothing here reads or writes this repository's own
`.ai-state/`, `.claude/`, or `HOME`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from . import contract as c

# Phases that run per the flow table but carry no row in the per-phase predicate
# table. Asserted by *equality* below, so a fix must shrink this set and a
# regression cannot quietly grow it. Both have a predicate stated inline in
# their flow row, so the gap is table parity rather than an absent contract --
# but the predicate table is the document that claims to be the per-phase source
# of truth, and a reader consulting it finds nothing for either phase.
KNOWN_PREDICATE_TABLE_GAPS = ("0.5", "8e")

TREE_PREDICATES = [p for p in c.predicates() if p.kind == "tree"]
ELIDED_PREDICATES = [p for p in c.predicates() if p.kind == "elided"]

needs_jq = pytest.mark.skipif(not c.HAVE_JQ, reason="jq is not installed on this machine")


def _heading_predicates() -> list[tuple[str, str]]:
    """Pair each `CLAUDE.md` heading grep with the block payload that must carry it.

    Only the blocks whose idempotency check is a heading grep appear. The four
    core blocks are refreshed by a version-manifest script with its own
    absent/current/stale/modified classification and deliberately have no grep.
    """
    pairs = []
    for predicate in TREE_PREDICATES:
        match = re.match(r"grep -q '\^(## [^$']+)\$' CLAUDE\.md", predicate.snippet)
        if match:
            pairs.append((match.group(1), predicate.snippet))
    return pairs


HEADING_PREDICATES = _heading_predicates()


# -- Contract completeness ---------------------------------------------------


def test_every_running_phase_has_a_predicate_table_row() -> None:
    gaps = c.table_parity_gaps(c.flow_phases(), c.idempotency_phases())
    assert gaps == KNOWN_PREDICATE_TABLE_GAPS, (
        f"phases running without a predicate-table row changed: {gaps}. Add the row when a "
        "phase is added; shrink KNOWN_PREDICATE_TABLE_GAPS when one is fixed. A phase with no "
        "stated re-run contract either rewrites on every invocation or skips one it never ran."
    )


def test_every_running_phase_has_its_own_section() -> None:
    orphans = sorted(set(c.flow_phases()) - set(c.phase_headings()))
    assert not orphans, (
        f"phases listed in the flow table with no section of their own: {orphans}. The flow row "
        "is a one-line summary; the section is where the write-set and predicate live."
    )


@pytest.mark.parametrize("phase", list(c.idempotency_phases()))
def test_every_predicate_row_is_executable_or_says_it_is_advisory(phase: str) -> None:
    """A row that is neither runnable nor declared advisory is an inert contract."""
    row = c.predicate_row(phase)
    runnable = [p for p in c.predicates() if p.phase == phase]
    declared_advisory = "None —" in row or "None -" in row
    assert runnable or declared_advisory, (
        f"phase {phase}'s predicate row cites no runnable fragment and does not declare itself "
        f"advisory: {row.strip()!r}. Prose alone leaves nothing to check re-runs against."
    )


@pytest.mark.parametrize("predicate", ELIDED_PREDICATES, ids=lambda p: p.phase)
def test_every_elided_predicate_is_written_out_in_full_in_its_phase(predicate) -> None:
    """A table cell may elide a long argument; the phase body must still carry it.

    An elision with no complete counterpart is unrunnable in both places, so
    nothing states what the phase actually checks.
    """
    complete = [pair for pair in c.jq_pairs() if pair.predicate]
    assert complete, (
        f"phase {predicate.phase} elides its check as {predicate.snippet!r} and no phase body "
        "spells one out in full. Elide in the table, never in the phase."
    )


@pytest.mark.parametrize("asset", list(c.plugin_asset_paths()))
def test_every_plugin_side_source_the_contract_reads_exists(asset: str) -> None:
    missing = c.missing_assets((asset,), c.REPO_ROOT)
    assert not missing, (
        f"the contract instructs a consumer to read {asset} from the plugin install, but no such "
        "file ships. The read fails only in a consumer -- a session running inside this repo "
        "resolves it either way."
    )


def test_skeleton_omits_the_file_the_contract_forbids_creating() -> None:
    """The observability log must be absent until first use; pre-creating it confuses the merge driver."""
    skeleton = c.ai_state_skeleton()
    assert skeleton, "no skeleton files derived -- the phase-2 parser has lost its grip"
    assert ".ai-state/observations.jsonl" not in skeleton


# -- No predicate is true before onboarding ----------------------------------


@pytest.mark.parametrize("predicate", TREE_PREDICATES, ids=lambda p: p.label)
def test_no_predicate_reports_done_on_a_project_that_was_never_onboarded(
    predicate, tmp_path: Path
) -> None:
    if predicate.snippet.startswith("jq ") and not c.HAVE_JQ:
        pytest.skip("jq is not installed on this machine")
    tree = c.bare_repo(tmp_path / "consumer")
    assert not c.holds(predicate.snippet, tree), (
        f"{predicate.label} already reports 'already done' on a bare git repo. Onboarding would "
        "skip this phase on a project where it has never run."
    )


# -- Write/check closure -----------------------------------------------------


@pytest.mark.parametrize("phase", sorted(c.gitignore_payloads()))
def test_each_ignore_block_satisfies_the_predicate_that_detects_it(
    phase: str, tmp_path: Path
) -> None:
    tree = c.bare_repo(tmp_path / "consumer")
    (tree / ".gitignore").write_text(c.gitignore_payloads()[phase] + "\n", encoding="utf-8")
    checks = [p for p in TREE_PREDICATES if p.phase == phase and p.snippet.endswith(".gitignore")]
    assert len(checks) == 1, f"phase {phase} must own exactly one ignore-file predicate: {checks}"
    assert c.holds(checks[0].snippet, tree), (
        f"phase {phase} writes an ignore block that its own predicate "
        f"({checks[0].snippet}) does not detect -- the phase would re-append it on every run."
    )


def test_the_merge_driver_entry_satisfies_the_predicate_that_detects_it(tmp_path: Path) -> None:
    tree = c.bare_repo(tmp_path / "consumer")
    (tree / ".gitattributes").write_text(c.gitattributes_payload(), encoding="utf-8")
    check = next(p for p in TREE_PREDICATES if p.snippet.endswith(".gitattributes"))
    assert c.holds(check.snippet, tree), (
        "the merge-driver entry written into .gitattributes is not matched by the exact-line "
        f"predicate that detects it ({check.snippet})."
    )


@pytest.mark.parametrize(("heading", "snippet"), HEADING_PREDICATES, ids=lambda v: v)
def test_each_installed_block_carries_the_heading_its_predicate_greps_for(
    heading: str, snippet: str, tmp_path: Path
) -> None:
    blocks = c.claude_md_blocks()
    assert heading in blocks, (
        f"the predicate {snippet} greps for {heading!r}, but no shipped block section carries that "
        "heading -- the check can never fire and the block would be appended on every run."
    )
    tree = c.bare_repo(tmp_path / "consumer")
    (tree / "CLAUDE.md").write_text("# Project\n\n" + blocks[heading] + "\n", encoding="utf-8")
    assert c.holds(snippet, tree)


def test_the_declared_skeleton_satisfies_the_per_file_existence_check(tmp_path: Path) -> None:
    tree = c.bare_repo(tmp_path / "consumer")
    for entry in c.ai_state_skeleton():
        path = tree / entry
        if entry.endswith("/"):
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
    assert not c.missing_skeleton_files(c.ai_state_skeleton(), tree)


# -- Merge algebra -----------------------------------------------------------


@needs_jq
@pytest.mark.parametrize("pair", list(c.jq_pairs()), ids=lambda p: p.name)
def test_each_settings_merge_satisfies_its_own_check_and_re_runs_clean(
    pair, tmp_path: Path
) -> None:
    tree = c.bare_repo(tmp_path / "consumer")
    c.seed_settings(tree, {})

    assert not c.holds(pair.predicate, tree), f"{pair.name}: reports done on empty settings"
    assert c.run_shell(pair.action, tree).returncode == 0, f"{pair.name}: merge failed"
    assert c.holds(pair.predicate, tree), (
        f"{pair.name}: the documented merge runs, but the documented check still reports it "
        "undone -- the phase would rewrite settings on every re-run."
    )

    once = c.settings_of(tree)
    assert c.run_shell(pair.action, tree).returncode == 0
    assert c.settings_of(tree) == once, f"{pair.name}: the merge is not idempotent"


@needs_jq
def test_the_allow_and_deny_baselines_compose_in_either_order(tmp_path: Path) -> None:
    """Two phases write sibling arrays in one file; neither may clobber the other."""
    allow, deny = c.jq_pairs()

    results = []
    for order in ([allow, deny], [deny, allow]):
        tree = c.bare_repo(tmp_path / f"consumer-{len(results)}")
        c.seed_settings(tree, {"model": "opus"})
        for pair in order:
            assert c.run_shell(pair.action, tree).returncode == 0
        assert c.holds(allow.predicate, tree), "the allow check does not hold after both merges"
        assert c.holds(deny.predicate, tree), "the deny check does not hold after both merges"
        results.append(c.settings_of(tree))

    assert results[0] == results[1], (
        "the allow and deny merges do not commute; a project's final settings would depend on "
        "which optional phase the user happened to accept first."
    )
    assert results[0]["model"] == "opus", "an unrelated top-level key was not preserved"


@needs_jq
def test_the_allow_merge_preserves_an_entry_the_user_added(tmp_path: Path) -> None:
    allow = c.jq_pairs()[0]
    tree = c.bare_repo(tmp_path / "consumer")
    c.seed_settings(tree, {"permissions": {"allow": ["Read(//custom/**)"]}})

    assert c.run_shell(allow.action, tree).returncode == 0
    assert "Read(//custom/**)" in c.settings_of(tree)["permissions"]["allow"]


# -- Canaries: the harness must flag a known-bad consumer tree ---------------


def test_flags_a_skeleton_missing_one_of_its_ledgers(tmp_path: Path) -> None:
    """The exact shape of a project whose consult convener appends to a file that never existed."""
    skeleton = c.ai_state_skeleton()
    dropped = next(p for p in skeleton if p.endswith("CONSULT_LEDGER.md"))
    tree = c.bare_repo(tmp_path / "consumer")
    for entry in skeleton:
        if entry == dropped:
            continue
        path = tree / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir(exist_ok=True) if entry.endswith("/") else path.write_text("", encoding="utf-8")

    assert c.missing_skeleton_files(skeleton, tree) == (dropped,)


@needs_jq
def test_flags_settings_that_carry_deny_but_no_allow_baseline(tmp_path: Path) -> None:
    """A file with a populated sibling array reads as configured; the check must not agree."""
    allow, deny = c.jq_pairs()
    tree = c.bare_repo(tmp_path / "consumer")
    c.seed_settings(tree, {})
    assert c.run_shell(deny.action, tree).returncode == 0

    assert not c.holds(allow.predicate, tree)


@needs_jq
def test_flags_a_permissions_allow_array_missing_a_required_entry(tmp_path: Path) -> None:
    """A non-empty allow list must not pass -- the check is a subset test, not existence."""
    allow = c.jq_pairs()[0]
    tree = c.bare_repo(tmp_path / "consumer")
    c.seed_settings(tree, {"permissions": {"allow": ["Read(//somewhere/**)"]}})

    assert not c.holds(allow.predicate, tree)


def test_flags_an_ignore_block_whose_header_drifted_in_case(tmp_path: Path) -> None:
    """The header is matched anchored and case-sensitively; a re-cased copy is not the block."""
    tree = c.bare_repo(tmp_path / "consumer")
    drifted = c.gitignore_payloads()["1"].replace("# AI assistants", "# AI Assistants")
    (tree / ".gitignore").write_text(drifted + "\n", encoding="utf-8")
    check = next(p for p in TREE_PREDICATES if p.phase == "1")

    assert not c.holds(check.snippet, tree)


def test_flags_a_block_installed_below_its_own_heading_level(tmp_path: Path) -> None:
    """A demoted heading leaves the payload present and the predicate blind to it."""
    heading, snippet = HEADING_PREDICATES[0]
    tree = c.bare_repo(tmp_path / "consumer")
    demoted = c.claude_md_blocks()[heading].replace(heading, "#" + heading, 1)
    (tree / "CLAUDE.md").write_text(demoted, encoding="utf-8")

    assert not c.holds(snippet, tree)


def test_flags_a_plugin_side_source_that_does_not_ship(tmp_path: Path) -> None:
    real = c.plugin_asset_paths()
    assert real, "no plugin-side sources derived -- the asset parser has lost its grip"

    findings = c.missing_assets((*real, "claude/project-baseline/never-shipped.tmpl"), c.REPO_ROOT)

    assert findings == ("claude/project-baseline/never-shipped.tmpl",)


def test_flags_a_phase_that_runs_with_no_predicate_table_row() -> None:
    findings = c.table_parity_gaps(("1", "2", "3"), ("1", "3"))

    assert findings == ("2",)


def test_flags_a_settings_file_that_is_not_valid_json(tmp_path: Path) -> None:
    """The parser used by the merge tests must not silently accept a corrupt file."""
    tree = c.bare_repo(tmp_path / "consumer")
    path = tree / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        c.settings_of(tree)
