"""Tests for check_agent_shared_blocks.py -- the replicated-prose-block gate.

This file is the gate's canary set (rules/swe/gate-liveness.md: a CODE gate
ships proof it *fails* on a known-bad input, not merely that it passes on the
current good state).

The known-bad inputs are not invented. Four textually distinct variants of the
task-slug scoping sentence were in circulation across the fifteen agent
definitions before reconciliation, differing only in the tail:

    ... Use this path for all document reads and writes.   (six files)
    ... Use this path for reads.                           (one file)
    ... <no tail at all>                                   (one file)
    ... Use this path for all reads and writes.            (the survivor)

``test_canary_flags_the_historical_document_variant`` and its siblings
reconstruct those exact byte sequences.

The controls matter as much as the canaries here. Five agents open the line
with a per-agent lead-in clause and one continues past the sentence, so a gate
that compared whole lines would report six correct files as drifted -- and a
gate that reports correct work as drift teaches its reader to skip it.

Behavioral tests:

1. The live repo scans clean, and finds all fifteen carriers (the no-op
   control -- without it, a gate that detects nothing would pass every canary).
2. CANARY: the historical ``document reads and writes`` tail is flagged.
3. CANARY: the truncated ``for reads.`` tail is flagged.
4. CANARY: the no-tail variant is flagged.
5. CANARY: a drifted *head* (anchor reworded) is flagged ``anchor-missing``
   rather than passing undetected -- otherwise head drift makes a line
   invisible and the gate returns a false all-clear.
6. CONTROL: a per-agent lead-in clause plus the canonical sentence is NOT
   flagged.
7. CONTROL: trailing context after the canonical sentence is NOT flagged.
8. CONTROL: a lead-in AND trailing context together are NOT flagged.
9. CONTROL: an agent that never mentions the block is skipped, not flagged --
   the documented scope boundary (this gate checks agreement among carriers,
   not which agents ought to be carriers).
10. CONTROL: ``.ai-work/<task-slug>/`` path mentions elsewhere in an agent body
    are not mistaken for the block.
11. CANARY: the CLI exits non-zero on a drifted tree and zero on a clean one --
    the exit code is what the pre-commit hook reads.
12. ``--print-canonical`` emits the exact bytes every site must carry.
13. The ``.pre-commit-config.yaml`` ``files:`` pattern matches every path the
    scanner actually scans, plus the gate's own file (scope fidelity).
14. CANARY: an agent definition missing a universal block is flagged
    ``missing`` (one case per universal block).
15. CANARY: a drifted universal block is flagged ``drifted``.
16. CONTROL: the directory's guides (no frontmatter) are not definitions and
    are never asked for universal blocks.
17. ``--print-canonical <slug>`` emits each universal block's exact bytes.

Fixture agents carry the universal blocks unless a test removes one, so the
task-slug tests above keep testing only the task-slug block.

Every mutating test builds its tree under ``tmp_path``; the real repo is only
ever read.
"""

from __future__ import annotations

import functools
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_agent_shared_blocks.py"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRECOMMIT_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"
_HOOK_ID = "agent-shared-blocks"

# The number of agent definitions carrying the block at reconciliation. Asserted
# as a floor, never as an equality: a new agent legitimately adds a sixteenth
# copy, and a gate that reddens on correct work is a gate people route around.
_CARRIERS_AT_RECONCILIATION = 15

# Agent definitions when the universal blocks were adopted; a floor, as above.
_DEFINITIONS_AT_UNIVERSAL_ADOPTION = 17


@functools.lru_cache(maxsize=1)
def _gate() -> Any:
    """Load the gate module under test, caching it across tests."""
    spec = importlib.util.spec_from_file_location("check_agent_shared_blocks", _SCRIPT_PATH)
    assert spec is not None, f"gate module not importable at {_SCRIPT_PATH}"
    assert spec.loader is not None, f"gate module has no loader at {_SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _canonical() -> str:
    return _gate().SHARED_BLOCKS[0].canonical


# The four historical variants, reconstructed from the reconciliation diff.
_HEAD = (
    "The **task slug** (provided in your prompt as `Task slug: <slug>`) scopes all "
    "`.ai-work/` paths to `.ai-work/<task-slug>/`."
)
_VARIANT_DOCUMENT = f"{_HEAD} Use this path for all document reads and writes."
_VARIANT_READS_ONLY = f"{_HEAD} Use this path for reads."
_VARIANT_NO_TAIL = _HEAD


def _universal_blocks() -> list[Any]:
    return [block for block in _gate().SHARED_BLOCKS if block.universal]


def _universal_lines(skip: str = "") -> str:
    """The universal blocks every conforming definition carries, minus `skip`."""
    return "".join(f"{block.canonical}\n\n" for block in _universal_blocks() if block.slug != skip)


def _write_agent(root: Path, name: str, block_line: str, skip_universal: str = "") -> Path:
    """Materialize one conforming agent definition under `root` carrying `block_line`."""
    body = (
        "---\n"
        f"name: {name.removesuffix('.md')}\n"
        "description: A fixture agent.\n"
        "---\n"
        "\n"
        f"{_universal_lines(skip=skip_universal)}"
        "## Process\n"
        "\n"
        "### Phase 1 -- Scope\n"
        "\n"
        f"{block_line}\n"
        "\n"
        "Then do the work and write `.ai-work/<task-slug>/PROGRESS.md`.\n"
    )
    path = root / "agents" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _insert_after_frontmatter(path: Path, text: str) -> None:
    """Put `text` as the first paragraph of the body of the fixture definition at `path`."""
    head, body = path.read_text(encoding="utf-8").split("---\n\n", 1)
    path.write_text(f"{head}---\n\n{text}\n\n{body}", encoding="utf-8")


def _kinds(report: dict[str, Any]) -> list[str]:
    return [finding["kind"] for finding in report["findings"]]


def _hook_files_pattern() -> str:
    """The `files:` regex the pre-commit hook filters staged paths with."""
    config = yaml.safe_load(_PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook.get("id") == _HOOK_ID:
                return hook["files"]
    raise AssertionError(f"hook id {_HOOK_ID!r} is not registered in {_PRECOMMIT_CONFIG}")


# --- 1. No-op control: the live repo ---------------------------------------


def test_live_repo_scans_clean_and_finds_every_carrier() -> None:
    """The real tree agrees, and the gate actually sees the copies it certifies.

    The carrier count is the half that matters: a gate that detected zero
    carriers would also report zero findings, and would pass every canary below
    while certifying nothing at all.
    """
    report = _gate().check_agent_shared_blocks(_REPO_ROOT)
    carriers = report["blocks"]["task-slug-scoping"]["carriers"]
    assert carriers >= _CARRIERS_AT_RECONCILIATION, (
        f"only {carriers} inline copies detected; the block was replicated across "
        f"{_CARRIERS_AT_RECONCILIATION} agents at reconciliation -- detection has regressed"
    )
    assert report["definitions"] >= _DEFINITIONS_AT_UNIVERSAL_ADOPTION, (
        f"only {report['definitions']} agent definitions recognized -- detection has regressed"
    )
    for block in _universal_blocks():
        assert report["blocks"][block.slug]["carriers"] == report["definitions"], (
            f"{block.slug} is universal but not carried once per definition"
        )
    assert report["findings"] == [], (
        "live agent definitions disagree on a shared block: "
        f"{[(f['file'], f['line'], f['kind']) for f in report['findings']]}"
    )


# --- 2-4. Canaries: the three historical drifted tails -----------------------


@pytest.mark.parametrize(
    ("label", "variant"),
    [
        ("document", _VARIANT_DOCUMENT),
        ("reads-only", _VARIANT_READS_ONLY),
        ("no-tail", _VARIANT_NO_TAIL),
    ],
)
def test_canary_flags_the_historical_tail_variants(
    tmp_path: Path, label: str, variant: str
) -> None:
    """Each tail that actually shipped is flagged `drifted`, with a diff."""
    _write_agent(tmp_path, "good.md", _canonical())
    _write_agent(tmp_path, f"bad-{label}.md", variant)

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert _kinds(report) == ["drifted"], f"{label} variant went undetected"
    finding = report["findings"][0]
    assert finding["file"] == f"agents/bad-{label}.md"
    assert finding["diff"], "a drift finding must carry a diff naming what changed"
    assert any(line.startswith("-") and "canonical" not in line for line in finding["diff"])


def test_canary_flags_the_historical_document_variant_by_column(tmp_path: Path) -> None:
    """The reported column lands inside the tail, where the two texts diverge.

    A gate that says only "these differ" makes the reader diff by eye; the
    column is what turns the finding into an edit.
    """
    _write_agent(tmp_path, "bad.md", _VARIANT_DOCUMENT)
    report = _gate().check_agent_shared_blocks(tmp_path)
    (finding,) = report["findings"]
    column = int(re.search(r"column (\d+)", finding["detail"]).group(1))
    assert column > len(_HEAD), "divergence reported before the tail, where the texts agree"


# --- 5. Canary: drift in the head, not the tail ------------------------------


def test_canary_flags_a_reworded_head_as_anchor_missing(tmp_path: Path) -> None:
    """Head drift must surface, not silently drop the line out of scope.

    This is the failure the tells exist to prevent: if detection keyed only on
    the anchor, un-bolding it would make the line invisible and the gate would
    return a clean verdict on a file it never examined.
    """
    unbolded = _canonical().replace("The **task slug**", "The task-slug value")
    _write_agent(tmp_path, "bad.md", unbolded)

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert _kinds(report) == ["anchor-missing"]
    assert "anchor" in report["findings"][0]["detail"]


# --- 6-8. Controls: lead-ins and trailing context are legitimate -------------


@pytest.mark.parametrize(
    ("label", "line_builder"),
    [
        ("lead-in", lambda c: f"Determine what you have to work with. {c}"),
        (
            "lead-in-long",
            lambda c: f"Before gathering information, clarify what needs to be researched. {c}",
        ),
        ("trailing", lambda c: f"{c} Read these at start:"),
        ("both", lambda c: f"Determine the ideation focus. {c} Read these at start:"),
    ],
)
def test_per_agent_context_is_not_flagged(tmp_path: Path, label: str, line_builder: Any) -> None:
    """Per-agent lead-in clauses and trailing context are context, not drift."""
    _write_agent(tmp_path, f"{label}.md", line_builder(_canonical()))
    report = _gate().check_agent_shared_blocks(tmp_path)
    assert report["findings"] == [], f"{label} shape reported as drift"
    assert report["blocks"]["task-slug-scoping"]["carriers"] == 1, (
        f"{label} shape was not recognized as a carrier at all"
    )


# --- 9-10. Controls: the documented scope boundary ---------------------------


def test_agent_without_the_block_is_skipped_not_flagged(tmp_path: Path) -> None:
    """Which agents *must* carry the block is out of documented scope.

    Asserting that would need a hardcoded roster, and a hardcoded roster is the
    same drift vector this gate closes. Carriers are detected, never enumerated.
    """
    agents = tmp_path / "agents"
    agents.mkdir(parents=True)
    (agents / "no-block.md").write_text(
        f"---\nname: no-block\n---\n\n{_universal_lines()}This agent never touches `.ai-work/`.\n",
        encoding="utf-8",
    )
    report = _gate().check_agent_shared_blocks(tmp_path)
    assert report["scanned"] == 1
    assert report["blocks"]["task-slug-scoping"]["carriers"] == 0
    assert report["findings"] == []


def test_scoped_path_mentions_are_not_mistaken_for_the_block(tmp_path: Path) -> None:
    """`.ai-work/<task-slug>/` appears dozens of times per agent; none is the block."""
    agents = tmp_path / "agents"
    agents.mkdir(parents=True)
    (agents / "pathy.md").write_text(
        f"---\nname: pathy\n---\n\n{_universal_lines()}"
        "Append to `.ai-work/<task-slug>/PROGRESS.md`.\n"
        "Read `.ai-work/<task-slug>/SYSTEMS_PLAN.md` first.\n"
        "The first non-flag token is the **task slug**.\n",
        encoding="utf-8",
    )
    report = _gate().check_agent_shared_blocks(tmp_path)
    assert report["blocks"]["task-slug-scoping"]["carriers"] == 0
    assert report["findings"] == []


# --- 14-17. Universal blocks: presence is checked, without a roster ----------


@pytest.mark.parametrize("slug", ["behavioral-contract", "praxion-links", "return-contract"])
def test_canary_flags_a_definition_missing_a_universal_block(tmp_path: Path, slug: str) -> None:
    """A definition without a universal block is `missing` -- the gap class that let three
    agents skip the contract and twelve skip a terminal marker while every copy agreed."""
    _write_agent(tmp_path, "good.md", _canonical())
    _write_agent(tmp_path, "bad.md", _canonical(), skip_universal=slug)

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert [(f["kind"], f["block"], f["file"]) for f in report["findings"]] == [
        ("missing", slug, "agents/bad.md")
    ]


@pytest.mark.parametrize("slug", ["behavioral-contract", "praxion-links", "return-contract"])
def test_canary_flags_a_drifted_universal_block(tmp_path: Path, slug: str) -> None:
    """A carried universal block is held byte-identical like any other shared block."""
    block = next(b for b in _universal_blocks() if b.slug == slug)
    _write_agent(tmp_path, "bad.md", block.canonical[:-1] + " (edited).", skip_universal=slug)

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert [(f["kind"], f["block"]) for f in report["findings"]] == [("drifted", slug)]


def test_guides_without_frontmatter_are_not_definitions(tmp_path: Path) -> None:
    """The directory's CLAUDE.md and README.md are guides: never asked for universal blocks."""
    agents = tmp_path / "agents"
    agents.mkdir(parents=True)
    (agents / "CLAUDE.md").write_text("# Agents\n\nHow agents are organized.\n", encoding="utf-8")
    (agents / "README.md").write_text("# Agent catalog\n", encoding="utf-8")

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert report["scanned"] == 2
    assert report["definitions"] == 0
    assert report["findings"] == []


@pytest.mark.parametrize("slug", ["behavioral-contract", "praxion-links", "return-contract"])
def test_print_canonical_emits_each_universal_block(slug: str) -> None:
    """Every block's bytes are obtainable by slug, not only the default block's."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--print-canonical", slug],
        capture_output=True,
        text=True,
        check=False,
    )
    block = next(b for b in _universal_blocks() if b.slug == slug)
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip("\n") == block.canonical


def test_contract_block_self_test_is_the_rules_own() -> None:
    """The agents' self-test question is the behavioral-contract rule's, byte for byte.

    The rule is the sole author of the contract's wording; the generator copies it, so a
    rewording of the rule fails here instead of leaving seventeen agents asking an older
    question.
    """
    block = next(b for b in _universal_blocks() if b.slug == "behavioral-contract")
    self_test = block.canonical.splitlines()[-1]
    rule = (_REPO_ROOT / "rules" / "swe" / "agent-behavioral-contract.md").read_text(
        encoding="utf-8"
    )
    assert self_test.startswith("Self-test: ")
    assert self_test in rule


# --- 18. The universal canonicals are the generator's, several lines for the contract ----


def test_universal_blocks_are_read_from_the_generated_file() -> None:
    """The gate holds no copy of the three texts: each is a paragraph of the generator's file."""
    generated = _gate().UNIVERSAL_BLOCKS_PATH.read_text(encoding="utf-8")

    absent = [b.slug for b in _universal_blocks() if b.canonical not in generated]

    assert absent == []
    assert len(_universal_blocks()) == 3


def test_the_contract_block_spans_several_lines() -> None:
    """The control for the next canaries: a one-line contract would make them vacuous."""
    contract = next(b for b in _universal_blocks() if b.slug == "behavioral-contract")

    assert len(contract.canonical.splitlines()) >= 5


@pytest.mark.parametrize("index", [0, 2, -1], ids=["first", "middle", "self-test"])
def test_canary_flags_a_reworded_line_of_the_contract_block(tmp_path: Path, index: int) -> None:
    """Every line of the contract is compared, not only the line its anchor sits on."""
    contract = next(b for b in _universal_blocks() if b.slug == "behavioral-contract")
    lines = contract.canonical.splitlines()
    lines[index] = lines[index][:-1] + "!"  # the anchor, at the head of line one, stays intact
    _write_agent(tmp_path, "bad.md", _canonical(), skip_universal=contract.slug)
    _insert_after_frontmatter(tmp_path / "agents" / "bad.md", "\n".join(lines))

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert [(f["kind"], f["block"]) for f in report["findings"]] == [("drifted", contract.slug)]


def test_canary_flags_a_contract_block_cut_short(tmp_path: Path) -> None:
    """The contract without its self-test line is a drifted copy, not a conforming prefix."""
    contract = next(b for b in _universal_blocks() if b.slug == "behavioral-contract")
    cut = "\n".join(contract.canonical.splitlines()[:-1])
    _write_agent(tmp_path, "bad.md", _canonical(), skip_universal=contract.slug)
    agent = tmp_path / "agents" / "bad.md"
    _insert_after_frontmatter(agent, cut)

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert [(f["kind"], f["block"]) for f in report["findings"]] == [("drifted", contract.slug)]


def test_a_sentence_after_the_contract_block_is_free(tmp_path: Path) -> None:
    """A definition may follow the contract with its own sentence; it is not drift."""
    contract = next(b for b in _universal_blocks() if b.slug == "behavioral-contract")
    _write_agent(tmp_path, "good.md", _canonical(), skip_universal=contract.slug)
    _insert_after_frontmatter(
        tmp_path / "agents" / "good.md", f"{contract.canonical}\nYour own sentence follows."
    )

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert report["findings"] == []


def test_a_reworded_contract_head_is_anchor_missing(tmp_path: Path) -> None:
    """Head drift on the contract is found through its tell, as for every other block."""
    contract = next(b for b in _universal_blocks() if b.slug == "behavioral-contract")
    head, *rest = contract.canonical.splitlines()
    reworded = head.replace(contract.anchor, "- **Surface Assumptions Quickly**")
    _write_agent(tmp_path, "bad.md", _canonical(), skip_universal=contract.slug)
    _insert_after_frontmatter(tmp_path / "agents" / "bad.md", "\n".join([reworded, *rest]))

    report = _gate().check_agent_shared_blocks(tmp_path)

    assert ("anchor-missing", contract.slug) in [
        (f["kind"], f["block"]) for f in report["findings"]
    ]


def test_a_generated_file_that_is_missing_or_malformed_stops_the_gate(tmp_path: Path) -> None:
    """No file, or not three paragraphs, is an error naming the file: never an empty comparison."""
    gate = _gate()
    with pytest.raises(gate.UniversalBlocksError, match="cannot read"):
        gate._read_universal_blocks(tmp_path / "absent.md")
    short = tmp_path / "core-blocks.md"
    short.write_text("**Praxion links.** Only one block.\n", encoding="utf-8")

    with pytest.raises(gate.UniversalBlocksError, match="expected 3"):
        gate._read_universal_blocks(short)


# --- 11. Canary: the CLI exit code the hook reads ----------------------------


def test_canary_cli_exits_nonzero_on_drift_and_zero_when_clean(tmp_path: Path) -> None:
    """The exit code -- the only thing pre-commit reads -- distinguishes the trees."""
    drifted = tmp_path / "drifted"
    clean = tmp_path / "clean"
    _write_agent(drifted, "a.md", _VARIANT_DOCUMENT)
    _write_agent(clean, "a.md", _canonical())

    def run(root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--repo-root", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    bad = run(drifted)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "drifted" in bad.stdout

    good = run(clean)
    assert good.returncode == 0, good.stdout + good.stderr


# --- 12. The source of truth is obtainable, not merely asserted --------------


def test_print_canonical_emits_the_exact_bytes() -> None:
    """An author updating the block copies the bytes rather than retyping them."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--print-canonical"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip("\n") == _canonical()


def test_unknown_block_slug_is_rejected() -> None:
    """A typo'd slug must not silently print the wrong block's text."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--print-canonical", "no-such-block"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unknown block" in result.stderr


# --- 13. Scope fidelity: the hook's filter vs. the scanner's real input ------


def test_precommit_pattern_covers_every_scanned_path() -> None:
    """The hook's `files:` filter must cover every path the scanner examines.

    A narrower pattern is a gate that never fires on the file that broke -- the
    scope-fidelity clause of gate-liveness.md. The gate's own file is in scope
    too: the canonical text lives inside it, so editing the source of truth must
    re-run the comparison against all fifteen sites.
    """
    pattern = re.compile(_hook_files_pattern())
    scanned = [
        p.relative_to(_REPO_ROOT).as_posix()
        for p in sorted(_REPO_ROOT.glob(_gate().SCAN_GLOB))
        if p.is_file()
    ]
    assert scanned, "the scanner examines nothing; the coverage claim is vacuous"
    uncovered = [path for path in scanned if not pattern.search(path)]
    assert not uncovered, (
        "the pre-commit `files:` pattern does not fire on these scanned agents, "
        f"so a drift landing there would never be gated: {uncovered}"
    )
    assert pattern.search("scripts/check_agent_shared_blocks.py"), (
        "editing the canonical constant must re-run the gate"
    )


def test_precommit_pattern_misses_unrelated_paths() -> None:
    """The filter is a filter: it must not fire on every commit in the repo."""
    pattern = re.compile(_hook_files_pattern())
    for unrelated in ("README.md", "skills/skill-crafting/SKILL.md", "skills/co/SKILL.md"):
        assert not pattern.search(unrelated), f"{unrelated} should not trigger this hook"
