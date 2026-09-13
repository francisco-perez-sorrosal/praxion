"""Tests for check_behavioral_contract.py -- BC01/BC03/BC04/BC05 canary.

Every golden bad-case builds a minimal substrate tree under `tmp_path`
(rules/swe/, agents/, skills/code-review/references/) rather than pointing at
the live repo -- it constructs the exact drifted shape each check exists to
detect, which a live-corpus assertion can never do because the live corpus is
(and must stay) clean.

BC05 adds a second, deliberately small family of tests that *do* read the live
repository, grouped under their own banner at the end: a single-sourcing guard
whose whole claim is "one wording, repo-wide" is only proven by the repository
it governs, and a floor on the number of sites it examines is what keeps a
predicate that stopped matching from reporting a clean corpus over nothing.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_behavioral_contract import (  # noqa: E402
    _BC05_ALLOWLIST,
    _BC05_CONSUMERS,
    _BC05_UNREGISTERED_THRESHOLD,
    _BC_RULE_REL,
    CHECK_IDS,
    _bc05_scan,
    _definition_lines,
    classify,
)

_RULE_TEXT = (
    "## Agent Behavioral Contract\n\n"
    "Four non-negotiable behaviors: Surface Assumptions, Register Objection, "
    "Stay Surgical, Simplicity First.\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_check_ids_declares_every_family_check() -> None:
    assert CHECK_IDS == ("BC01", "BC03", "BC04", "BC05")


# -- BC01 -----------------------------------------------------------------------


@pytest.mark.parametrize("spelling", ["\"paths\": '*.py'", "paths : '*.py'", "'paths': x"])
def test_bc01_flags_every_yaml_spelling_of_the_paths_key(tmp_path: Path, spelling: str) -> None:
    """Light-review F1, W-1: a quoted or space-before-colon `paths` key is the same key to a
    YAML parser; the line-prefix match missed it."""
    _write(
        tmp_path / "rules" / "swe" / "agent-behavioral-contract.md",
        f"---\n{spelling}\n---\n\n" + _RULE_TEXT,
    )
    findings = [f for f in classify(tmp_path)["findings"] if f["check"] == "BC01"]
    assert any("paths:" in f["message"] for f in findings), spelling


def test_bc01_ignores_a_nested_paths_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "rules" / "swe" / "agent-behavioral-contract.md",
        "---\nmeta:\n  paths: nested\n---\n\n" + _RULE_TEXT,
    )
    assert [
        f
        for f in classify(tmp_path)["findings"]
        if f["check"] == "BC01" and "paths:" in f["message"]
    ] == []


def test_bc01_flags_paths_frontmatter_and_missing_behavior(tmp_path: Path) -> None:
    """A `paths:`-scoped rule that also drops one behavior should be caught
    by both clauses at once."""
    _write(
        tmp_path / "rules" / "swe" / "agent-behavioral-contract.md",
        "---\npaths: '*.py'\n---\n\n## Contract\n\nSurface Assumptions, "
        "Register Objection, Stay Surgical.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC01"]
    assert any("paths:" in f["message"] for f in findings)
    assert any("Simplicity First" in f["entity"] for f in findings)
    assert all(f["severity"] == "fail" for f in findings)


def test_bc01_detects_missing_rule_file(tmp_path: Path) -> None:
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC01"]
    assert any("does not exist" in f["message"] for f in findings)


# -- BC03 -----------------------------------------------------------------------


def test_bc03_flags_missing_and_extra_citer(tmp_path: Path) -> None:
    _write(tmp_path / "rules" / "swe" / "agent-behavioral-contract.md", _RULE_TEXT)
    _write(
        tmp_path / "agents" / "researcher.md",
        "See `rules/swe/agent-behavioral-contract.md` for the contract.\n",
    )
    # "verifier" is contract-bound but does not cite the rule -- missing.
    _write(tmp_path / "agents" / "verifier.md", "No citation here.\n")
    # "promethean" is not contract-bound but cites the rule anyway -- extra.
    _write(
        tmp_path / "agents" / "promethean.md",
        "See `rules/swe/agent-behavioral-contract.md` for the contract.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC03"]
    entities = {f["entity"] for f in findings}
    assert "verifier" in entities
    assert "promethean" in entities
    assert all(f["severity"] == "fail" for f in findings)


# -- BC04 -----------------------------------------------------------------------


def test_bc04_flags_missing_tag_in_subsection(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "code-review" / "references" / "report-template.md",
        "## Report\n\n"
        "### Behavioral Contract Findings\n\n"
        "Tags: [UNSURFACED-ASSUMPTION], [MISSING-OBJECTION], [NON-SURGICAL], "
        "[SCOPE-CREEP], [BLOAT].\n\n"
        "### Next Section\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC04"]
    assert findings == [
        {
            "check": "BC04",
            "severity": "fail",
            "entity": "[DEAD-CODE-UNREMOVED]",
            "message": "'[DEAD-CODE-UNREMOVED]' missing from the Behavioral Contract "
            "Findings subsection of skills/code-review/references/report-template.md",
        }
    ]


def test_bc04_rejects_missing_heading(tmp_path: Path) -> None:
    _write(
        tmp_path / "skills" / "code-review" / "references" / "report-template.md",
        "## Report\n\nNo such subsection here.\n",
    )
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "BC04"]
    assert any("heading not found" in f["message"] for f in findings)


# -- BC05 -----------------------------------------------------------------------

_BC05_BULLETS: tuple[str, ...] = (
    "- **Surface Assumptions** — state your interpretation upfront, unconditionally.",
    "- **Register Objection** — state the conflict with a reason before complying.",
    "- **Stay Surgical** — touch only what the change requires.",
    "- **Simplicity First** — prefer the smallest solution that meets the behavior.",
)
_BC05_RULE_TEXT = (
    "## Agent Behavioral Contract\n\nFour non-negotiable behaviors:\n\n"
    + "\n".join(_BC05_BULLETS)
    + "\n"
)
# A full four-behavior copy in definition shape -- the text whose *placement* the
# planted-copy probe varies, so the probe tests the scope mechanism rather than the
# current contents of any one registry entry.
_BC05_PLANTED_COPY = "# planted\n\n" + "\n".join(_BC05_BULLETS) + "\n"


def _conforming_tree(tmp_path: Path) -> None:
    """The minimal clean substrate: the source rule, plus every registered consumer
    carrying the source's four lines verbatim."""
    _write(tmp_path / _BC_RULE_REL, _BC05_RULE_TEXT)
    for rel in sorted(_BC05_CONSUMERS):
        _write(tmp_path / rel, f"# {rel}\n\n" + "\n".join(_BC05_BULLETS) + "\n")


def _bc05_findings(tmp_path: Path) -> list[dict]:
    return [f for f in classify(tmp_path)["findings"] if f["check"] == "BC05"]


def test_bc05_registry_sets_are_pairwise_disjoint() -> None:
    """Every in-scope path occupies exactly one of source / consumer / allowlisted /
    unregistered -- a `frozenset` cannot self-check, so the disjointness is asserted here."""
    assert not (_BC05_CONSUMERS & _BC05_ALLOWLIST)
    assert _BC_RULE_REL not in _BC05_CONSUMERS
    assert _BC_RULE_REL not in _BC05_ALLOWLIST


def test_bc05_is_clean_on_a_conforming_tree(tmp_path: Path) -> None:
    _conforming_tree(tmp_path)
    assert _bc05_findings(tmp_path) == []


def test_bc05_flags_a_consumer_carrying_a_previous_wording(tmp_path: Path) -> None:
    _conforming_tree(tmp_path)
    stale = list(_BC05_BULLETS)
    stale[2] = "- **Stay Surgical** — touch only what you must; never expand scope."
    _write(tmp_path / "README.md", "# README.md\n\n" + "\n".join(stale) + "\n")
    findings = _bc05_findings(tmp_path)
    assert len(findings) == 1, findings
    assert findings[0]["entity"] == "README.md"
    assert "Stay Surgical" in findings[0]["message"]
    assert findings[0]["severity"] == "fail"


def test_bc05_flags_one_flipped_byte_in_one_consumer_line(tmp_path: Path) -> None:
    """The mutation canary: one byte, one finding, naming the file and the behavior --
    and no collateral finding against the four consumers that did not change."""
    _conforming_tree(tmp_path)
    rel = "claude/canonical-blocks/behavioral-contract.md"
    mutated = list(_BC05_BULLETS)
    mutated[1] = mutated[1][:-1] + "!"
    _write(tmp_path / rel, f"# {rel}\n\n" + "\n".join(mutated) + "\n")
    findings = _bc05_findings(tmp_path)
    assert len(findings) == 1, findings
    assert findings[0]["entity"] == rel
    assert "Register Objection" in findings[0]["message"]


def test_bc05_flags_reordered_definition_lines(tmp_path: Path) -> None:
    _conforming_tree(tmp_path)
    swapped = [_BC05_BULLETS[1], _BC05_BULLETS[0], *_BC05_BULLETS[2:]]
    _write(tmp_path / "AGENTS.md", "# AGENTS.md\n\n" + "\n".join(swapped) + "\n")
    findings = _bc05_findings(tmp_path)
    assert {f["entity"] for f in findings} == {"AGENTS.md"}
    assert any("order" in f["message"] for f in findings)


def test_bc05_flags_a_consumer_missing_one_definition_line(tmp_path: Path) -> None:
    _conforming_tree(tmp_path)
    _write(tmp_path / "AGENTS.md", "# AGENTS.md\n\n" + "\n".join(_BC05_BULLETS[:3]) + "\n")
    findings = _bc05_findings(tmp_path)
    assert len(findings) == 1, findings
    assert findings[0]["entity"] == "AGENTS.md"
    assert "carries 3 definition-shape behavior lines" in findings[0]["message"]


def test_bc05_flags_a_registered_consumer_missing_from_disk(tmp_path: Path) -> None:
    """A broken registry contract is louder than a silent skip."""
    _conforming_tree(tmp_path)
    (tmp_path / "README.md").unlink()
    findings = _bc05_findings(tmp_path)
    assert len(findings) == 1, findings
    assert findings[0]["entity"] == "README.md"
    assert "does not exist" in findings[0]["message"]


def test_bc05_reports_an_unparseable_source_once(tmp_path: Path) -> None:
    """No source, no binding: one finding against the rule, not five derived ones."""
    _conforming_tree(tmp_path)
    _write(tmp_path / _BC_RULE_REL, "## Agent Behavioral Contract\n\nProse only.\n")
    findings = _bc05_findings(tmp_path)
    assert len(findings) == 1, findings
    assert findings[0]["entity"] == _BC_RULE_REL
    assert "no source to bind" in findings[0]["message"]


def test_bc05_flags_a_planted_copy_at_an_unregistered_in_scope_path(tmp_path: Path) -> None:
    _conforming_tree(tmp_path)
    _write(tmp_path / "docs" / "planted-contract.md", _BC05_PLANTED_COPY)
    findings = _bc05_findings(tmp_path)
    assert len(findings) == 1, findings
    assert findings[0]["entity"] == "docs/planted-contract.md"
    assert "neither the canonical rule" in findings[0]["message"]


@pytest.mark.parametrize("rel", sorted(_BC05_ALLOWLIST))
def test_bc05_is_silent_for_a_planted_copy_at_an_allowlisted_path(tmp_path: Path, rel: str) -> None:
    """The other direction of the same probe: the allowlist mechanism is proven by a
    copy that would otherwise fire, not by its live entries (which score zero today)."""
    _conforming_tree(tmp_path)
    _write(tmp_path / rel, _BC05_PLANTED_COPY)
    assert _bc05_findings(tmp_path) == []


@pytest.mark.parametrize(
    "rel",
    [
        ".ai-state/sentinel_reports/planted.md",
        ".ai-work/slug/planted.md",
        "eval/fixtures/planted.md",
        "docs/independent-analysis/planted.md",
        "docs/context-prj-comparison-x/planted.md",
        "tmp/planted.md",
        ".claude/worktrees/other/README.md",
    ],
)
def test_bc05_is_silent_for_a_planted_copy_out_of_scope(tmp_path: Path, rel: str) -> None:
    _conforming_tree(tmp_path)
    _write(tmp_path / rel, _BC05_PLANTED_COPY)
    assert _bc05_findings(tmp_path) == []


def test_bc05_flags_an_unregistered_file_at_three_of_the_four(tmp_path: Path) -> None:
    _conforming_tree(tmp_path)
    _write(tmp_path / "docs" / "partial.md", "# partial\n\n" + "\n".join(_BC05_BULLETS[:3]) + "\n")
    findings = _bc05_findings(tmp_path)
    assert len(findings) == 1, findings
    assert findings[0]["entity"] == "docs/partial.md"


def test_bc05_ignores_an_unregistered_file_at_two_of_the_four(tmp_path: Path) -> None:
    """Inverse guard on the threshold: two behaviors is a mention, not a restatement."""
    _conforming_tree(tmp_path)
    _write(tmp_path / "docs" / "mention.md", "# mention\n\n" + "\n".join(_BC05_BULLETS[:2]) + "\n")
    assert _bc05_findings(tmp_path) == []


@pytest.mark.parametrize(
    "line",
    [
        "- **Surface Assumptions.** state your interpretation upfront.",
        "1. **Surface Assumptions** — state your interpretation upfront.",
        "### Surface Assumptions",
        "- **Surface Assumptions** before acting on them",
        "         - **Surface Assumptions** — nine spaces of indent.",
    ],
)
def test_definition_shape_excludes_the_declared_limits(line: str) -> None:
    """Each case is a declared limit in the module docstring: the predicate is a precise
    extractor, so what it cannot see is named rather than discovered later."""
    assert _definition_lines(line + "\n") == ()


def test_definition_shape_accepts_every_documented_separator() -> None:
    accepted = [
        "- **Stay Surgical** — em-dash.",
        "- **Stay Surgical**: colon.",
        "- **Stay Surgical** - hyphen.",
        "- **Stay Surgical** (parenthesis).",
        "* **Stay Surgical** — an asterisk bullet.",
        "    - **Stay Surgical** — four spaces of indent.",
    ]
    for line in accepted:
        assert _definition_lines(line + "\n") == (("Stay Surgical", line),), line


# -- BC05 live corpus -----------------------------------------------------------
#
# These read the real repository rather than a tmp_path substrate, so they assert the
# end state of the single-sourcing pass itself: one wording repo-wide, a registry that
# totalises the corpus, and a floor on the number of sites found. The floor is the
# load-bearing one -- without it, a predicate that stopped matching after some future
# bullet reshape would report a clean corpus over zero examined sites, which is
# indistinguishable from success.


@lru_cache(maxsize=1)
def _live_report() -> dict:
    """Cached: the live scan reads ~1,400 files, and every live test wants the same one."""
    return classify(REPO_ROOT)


def test_bc05_examines_the_live_corpus_above_its_floor() -> None:
    """A floor, not an exact count: a predicate that stopped matching after a future
    bullet reshape must redden here rather than report a clean corpus."""
    examined = _live_report()["examined"]["BC05"]
    assert examined["definition_sites"] >= 20
    assert examined["files_scanned"] >= 100
    assert examined["consumers"] == len(_BC05_CONSUMERS)


def test_bc05_registry_paths_all_exist_in_the_live_corpus() -> None:
    registry = sorted(_BC05_CONSUMERS | _BC05_ALLOWLIST | {_BC_RULE_REL})
    assert [rel for rel in registry if not (REPO_ROOT / rel).is_file()] == []


def test_bc05_is_clean_on_the_live_corpus() -> None:
    assert [f for f in _live_report()["findings"] if f["check"] == "BC05"] == []


def test_bc05_reports_one_wording_across_the_live_corpus() -> None:
    assert _live_report()["examined"]["BC05"]["distinct_wordings"] == 1


def test_bc05_registry_totalises_the_live_corpus() -> None:
    """Set equality, so a seventh wording cannot appear without either a registry entry
    or a failing test -- the property the unregistered-path probe checks mechanically."""
    sites, _ = _bc05_scan(REPO_ROOT)
    carriers = {rel for rel, pairs in sites.items() if len(pairs) >= _BC05_UNREGISTERED_THRESHOLD}
    matching_allowlist = {
        rel for rel in _BC05_ALLOWLIST if len(sites.get(rel, ())) >= _BC05_UNREGISTERED_THRESHOLD
    }
    assert carriers == {_BC_RULE_REL} | _BC05_CONSUMERS | matching_allowlist
