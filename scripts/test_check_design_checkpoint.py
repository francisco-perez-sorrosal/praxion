"""Behavioural tests for check_design_checkpoint.py -- the derived checkpoint validator.

Built from `SYSTEMS_PLAN.md`'s acceptance criteria and Data Structures / Interfaces
sections, not from the production script (which does not exist yet at the time
this file is written -- the first `pytest` run against this file is expected to
fail with `ModuleNotFoundError`, the correct RED state for the paired test/impl
step).

The single most important invariant under test (`DesignCheckpoint`'s sum type,
per SYSTEMS_PLAN Data Structures #1): an empty `unfolded` list must mean
*nothing is un-folded*, never *the checkpoint mark could not be read*. Several
tests below exist solely to catch a sum type collapsed into correlated
nullables -- the failure mode where `absent`/`malformed` silently produce the
same `unfolded: []` shape as a genuinely clean `present` checkpoint.

Everything runs against synthetic `tmp_path` fixtures (`.ai-state/DESIGN.md` +
`.ai-state/decisions/`) -- never the real corpus, whose content is not this
test's contract to pin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import check_design_checkpoint
import pytest

# -- Fixture builders ---------------------------------------------------------

FRONTMATTER = """---
id: {id}
title: {title}
status: {status}
category: {category}
date: "{date}"
summary: {summary}
tags: [{tags}]
made_by: agent
affected_files: [{affected_files}]
---

# Body
"""


def _write_adr(
    decisions_dir: Path,
    filename: str,
    *,
    adr_id: str,
    title: str = "A decision",
    status: str = "accepted",
    category: str = "architectural",
    date: str = "2026-09-01",
    summary: str = "a summary",
    tags: list[str] | None = None,
    affected_files: list[str] | None = None,
) -> Path:
    """Write one synthetic finalized ADR, mirroring query_adrs.py's own fixtures."""
    decisions_dir.mkdir(parents=True, exist_ok=True)
    body = FRONTMATTER.format(
        id=adr_id,
        title=title,
        status=status,
        category=category,
        date=date,
        summary=summary,
        tags=", ".join(tags or []),
        affected_files=", ".join(f'"{f}"' for f in (affected_files or [])),
    )
    path = decisions_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def _write_live_file(repo_root: Path, relative_path: str) -> None:
    """Create a real file at `relative_path` so an `affected_files` entry resolves."""
    target = repo_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# a real file\n", encoding="utf-8")


_DESIGN_TEMPLATE = """---
diataxis: explanation
audience: architect
---

# Architecture

## 1. Overview

| Attribute | Value |
|-----------|-------|
| **System** | Synthetic Test Project |
{current_as_of_row}| **Last verified** | 2026-09-01 -- synthetic fixture. |

Body text unrelated to the checkpoint.
"""


def _write_design(repo_root: Path, current_as_of_cell: str | None) -> Path:
    """Write a synthetic `.ai-state/DESIGN.md` §1.

    `current_as_of_cell=None` produces the **Absent** state (no such row at
    all). Any string is embedded verbatim as the table row's second cell --
    callers pass a well-formed `` `dec-NNN` (asserted ...) `` cell for the
    **Present** state, or a plain string with no backtick-wrapped id for the
    **Malformed** state.
    """
    design_dir = repo_root / ".ai-state"
    design_dir.mkdir(parents=True, exist_ok=True)
    if current_as_of_cell is None:
        row = ""
    else:
        row = f"| **Current as of** | {current_as_of_cell} |\n"
    path = design_dir / "DESIGN.md"
    path.write_text(_DESIGN_TEMPLATE.format(current_as_of_row=row), encoding="utf-8")
    return path


def _present_cell(adr_id: str, *, date: str = "2026-09-01") -> str:
    return f"`{adr_id}` (asserted {date} by systems-architect, task `test`)"


# -- Sum type: three checkpoint states, never collapsed into nullables --------


def test_present_checkpoint_reports_present_state_with_id_and_date(tmp_path, capsys):
    _write_design(tmp_path, _present_cell("dec-100", date="2026-09-01"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "present"
    assert payload["checkpoint"] == "dec-100"
    assert payload["asserted"] == "2026-09-01"


def test_absent_checkpoint_reports_absent_state_with_null_checkpoint(tmp_path, capsys):
    _write_design(tmp_path, None)

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "absent"
    assert payload["checkpoint"] is None


def test_malformed_checkpoint_reports_malformed_state_and_preserves_raw_value(tmp_path, capsys):
    _write_design(tmp_path, "TBD -- not yet asserted")

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "malformed"
    # The raw, unparseable text must survive somewhere in the payload -- a
    # malformed mark is a fact to report, not a fact to discard.
    assert "TBD" in json.dumps(payload)


def test_malformed_checkpoint_never_yields_empty_unfolded_list(tmp_path, capsys):
    """The critical sum-type invariant: malformed must not read as 'nothing un-folded'.

    A validator that coerces Malformed into `unfolded: []` is indistinguishable,
    from any consumer's perspective, from a project with a perfectly clean
    checkpoint -- exactly the silent failure `SYSTEMS_PLAN.md` names as the one
    invariant that matters most in this change.
    """
    _write_design(tmp_path, "not-a-valid-id")

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "malformed"
    assert payload.get("unfolded") != [], (
        "malformed checkpoint must not report an empty unfolded list -- "
        "it must be null/absent, distinguishable from a genuinely clean present state"
    )


def test_absent_checkpoint_never_yields_empty_unfolded_list(tmp_path, capsys):
    _write_design(tmp_path, None)

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "absent"
    assert payload.get("unfolded") != [], (
        "absent checkpoint must not report an empty unfolded list -- "
        "it must be null/absent, distinguishable from a genuinely clean present state"
    )


def test_draft_checkpoint_reports_draft_state_not_present(tmp_path, capsys):
    """AC-1 sanctions a `dec-draft-<hash>` mark as the normal in-flight state --
    it must surface as its own state, distinct from `present`, since a draft id
    has no numeric position to compare against the corpus."""
    _write_design(tmp_path, _present_cell("dec-draft-0abc1234", date="2026-08-30"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "draft"
    assert payload["checkpoint"] == "dec-draft-0abc1234"
    assert payload["asserted"] == "2026-08-30"


def test_draft_checkpoint_never_yields_empty_unfolded_list(tmp_path, capsys):
    """The FAIL-1 regression case: a draft mark must not silently coerce to
    `unfolded: [], count: 0` -- that shape is indistinguishable from a
    genuinely clean, comparable checkpoint (the exact failure the
    `DesignCheckpoint` sum type exists to prevent)."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "900-tip.md", adr_id="dec-900")
    _write_live_file(tmp_path, "src/module.py")
    _write_design(tmp_path, _present_cell("dec-draft-0abc1234"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "draft"
    assert payload.get("unfolded") != [], (
        "draft checkpoint must not report an empty unfolded list -- it must be "
        "null/absent, distinguishable from a genuinely clean present state"
    )
    assert payload["unfolded"] is None
    assert payload["count"] is None
    assert "message" in payload
    assert "dec-draft-0abc1234" in payload["message"]


def test_exits_zero_on_draft_checkpoint(tmp_path):
    _write_design(tmp_path, _present_cell("dec-draft-0abc1234"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])

    assert exit_code == 0


def test_present_checkpoint_with_no_post_checkpoint_adrs_yields_genuine_empty_list(
    tmp_path, capsys
):
    """Positive control for the invariant above: a real empty list IS legitimate
    when the checkpoint parses and nothing post-dates it -- proving the
    validator can express "clean" as distinct from "unreadable"."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["checkpoint_state"] == "present"
    assert payload["unfolded"] == []
    assert payload["count"] == 0


# -- Un-folded suffix: appears after the mark, disappears once advanced ------


def test_architecture_bearing_adr_after_checkpoint_appears_in_unfolded(tmp_path, capsys):
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_live_file(tmp_path, "src/module.py")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="accepted",
        category="architectural",
        affected_files=["src/module.py"],
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    ids = {entry["id"] for entry in payload["unfolded"]}
    assert "dec-101" in ids
    assert payload["count"] == 1


def test_advancing_checkpoint_past_adr_removes_it_from_unfolded(tmp_path, capsys):
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_live_file(tmp_path, "src/module.py")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="accepted",
        category="architectural",
        affected_files=["src/module.py"],
    )
    _write_design(tmp_path, _present_cell("dec-101"))  # mark advanced past dec-101

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    ids = {entry["id"] for entry in payload["unfolded"]}
    assert "dec-101" not in ids
    assert payload["count"] == 0


def test_merge_day_state_reports_unfolded_suffix_without_failing_exit(tmp_path, capsys):
    """PM-1: the moment a pipeline merges, its own finalized ADRs sit above the
    checkpoint mark. This must be reportable, never a failure exit -- the
    validator is advisory, and a red-on-day-one gate teaches consumers to
    ignore it (alarm fatigue)."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "347-checkpoint.md", adr_id="dec-347")
    _write_live_file(tmp_path, "scripts/a.py")
    _write_live_file(tmp_path, "scripts/b.py")
    _write_adr(
        decisions_dir,
        "348-a.md",
        adr_id="dec-348",
        status="accepted",
        category="architectural",
        affected_files=["scripts/a.py"],
    )
    _write_adr(
        decisions_dir,
        "349-b.md",
        adr_id="dec-349",
        status="accepted",
        category="architectural",
        affected_files=["scripts/b.py"],
    )
    _write_design(tmp_path, _present_cell("dec-347"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0, "an un-folded suffix must never produce a failure exit"
    assert payload["count"] == 2
    ids = {entry["id"] for entry in payload["unfolded"]}
    assert ids == {"dec-348", "dec-349"}


# -- Predicate: category exclusion --------------------------------------------


@pytest.mark.parametrize("excluded_category", ["implementation", "behavioral", "configuration"])
def test_non_architectural_category_excluded_from_unfolded(tmp_path, capsys, excluded_category):
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_live_file(tmp_path, "src/module.py")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="accepted",
        category=excluded_category,
        affected_files=["src/module.py"],
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    ids = {entry["id"] for entry in payload["unfolded"]}
    assert "dec-101" not in ids
    assert payload["count"] == 0


def test_non_streamline_status_excluded_from_unfolded(tmp_path, capsys):
    """The predicate is `status in {accepted, re-affirmation}` -- a superseded
    architectural decision post-checkpoint must not create a fold-in obligation
    against a document describing what currently exists."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_live_file(tmp_path, "src/module.py")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="superseded",
        category="architectural",
        affected_files=["src/module.py"],
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    ids = {entry["id"] for entry in payload["unfolded"]}
    assert "dec-101" not in ids


# -- Predicate: affected_files liveness ---------------------------------------


def test_adr_with_no_live_affected_files_excluded_from_unfolded(tmp_path, capsys):
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="accepted",
        category="architectural",
        affected_files=["this/path/does/not/exist.py"],
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    ids = {entry["id"] for entry in payload["unfolded"]}
    assert "dec-101" not in ids
    assert payload["count"] == 0


def test_adr_with_at_least_one_live_affected_file_included(tmp_path, capsys):
    """One live path among several dead ones is enough -- '>=1 live entry'."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_live_file(tmp_path, "src/still_here.py")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="accepted",
        category="architectural",
        affected_files=["gone/for/good.py", "src/still_here.py"],
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    ids = {entry["id"] for entry in payload["unfolded"]}
    assert "dec-101" in ids


# -- Exit codes -----------------------------------------------------------


def test_exits_zero_on_absent_checkpoint(tmp_path):
    _write_design(tmp_path, None)

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])

    assert exit_code == 0


def test_exits_zero_on_malformed_checkpoint(tmp_path):
    _write_design(tmp_path, "garbage")

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])

    assert exit_code == 0


def test_exits_two_on_unreadable_design_doc(tmp_path):
    """No `.ai-state/DESIGN.md` at all -- design doc missing/unreadable, exit 2.
    Distinct from Absent (doc readable, row missing), which exits 0.
    """
    (tmp_path / ".ai-state").mkdir(parents=True)
    # Deliberately no DESIGN.md written.

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])

    assert exit_code == 2


# -- PyYAML-optional parity ------------------------------------------------


def test_output_identical_with_pyyaml_forced_unavailable(tmp_path, capsys, monkeypatch):
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_live_file(tmp_path, "src/module.py")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="accepted",
        category="architectural",
        affected_files=["src/module.py"],
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code_with_yaml = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    with_yaml = json.loads(capsys.readouterr().out)

    # `sys.modules["yaml"] = None` makes every subsequent `import yaml`
    # statement raise ImportError, regardless of which module performs it --
    # a black-box way to force the stdlib fallback without assuming any
    # particular internal wiring between this script and query_adrs's loader.
    monkeypatch.setitem(sys.modules, "yaml", None)

    exit_code_without_yaml = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    without_yaml = json.loads(capsys.readouterr().out)

    assert exit_code_with_yaml == exit_code_without_yaml == 0
    assert with_yaml == without_yaml


def test_repeated_runs_produce_identical_output(tmp_path, capsys):
    """AC-5 (deletable and rebuildable): two consecutive runs against the same
    inputs must reproduce identical output -- no LLM synthesis, no hidden
    nondeterminism (ordering, timestamps)."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_live_file(tmp_path, "src/module.py")
    _write_adr(
        decisions_dir,
        "101-newer.md",
        adr_id="dec-101",
        status="accepted",
        category="architectural",
        affected_files=["src/module.py"],
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    first = capsys.readouterr().out

    check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    second = capsys.readouterr().out

    assert first == second


# -- Unparseable records surfaced, never silently dropped (WARN-1) -----------


def test_unparseable_adr_count_surfaces_in_json_payload(tmp_path, capsys):
    """A record `load_adr` cannot parse must not vanish from the un-folded
    computation without a trace -- the `--json` payload is the surface
    `check_design_checkpoint` consumers actually read, so the count belongs
    there, not only in a stderr warning."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    # Missing `title`/`status` -- `load_adr` returns None for this file
    # regardless of which parser (PyYAML or the stdlib fallback) reads it.
    decisions_dir.mkdir(parents=True, exist_ok=True)
    (decisions_dir / "101-broken.md").write_text(
        '---\nid: dec-101\ndate: "2026-09-01"\n---\n\n# Body\n', encoding="utf-8"
    )
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["unparseable"] == 1


def test_zero_unparseable_records_reports_zero_not_absent(tmp_path, capsys):
    """The positive control: a fully clean corpus reports `unparseable: 0`,
    proving the field is always present rather than only appearing when
    something goes wrong."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "100-checkpoint.md", adr_id="dec-100")
    _write_design(tmp_path, _present_cell("dec-100"))

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["unparseable"] == 0


# -- Checkpoint-ahead-of-corpus warning ---------------------------------------


def test_checkpoint_id_exceeding_corpus_tip_warns_but_does_not_fail(tmp_path, capsys):
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    _write_adr(decisions_dir, "005-only.md", adr_id="dec-005")
    _write_design(tmp_path, _present_cell("dec-999"))  # far past the real corpus tip

    exit_code = check_design_checkpoint.main(["--json", "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0, "an ahead-of-corpus checkpoint is advisory, never a failure"
    assert payload["corpus_tip"] == "dec-005"
    # The warning must be observable somewhere -- either a stderr message or a
    # truthy JSON field naming the discrepancy -- since a checkpoint asserting
    # more than the corpus contains is a fact worth surfacing, not swallowing.
    warned = "warn" in captured.err.lower() or bool(payload.get("warning"))
    assert warned, "checkpoint exceeding corpus_tip must surface a warning somewhere"
