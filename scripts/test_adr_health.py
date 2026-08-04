"""Tests for adr_health.py -- the ADR reference-decay classifier.

Cites: rules/swe/gate-liveness.md -- a CODE gate ships a canary proving it bites
on a known-bad input, not merely that it passes on the current good state. Here
"bites" means: each decay class is produced for an input that exhibits it, AND
the two oracle-unavailable paths withhold rather than defaulting to `vanished`.

The withholding canaries matter most. A classifier that silently promotes every
repairable finding to `retire-candidate` because git history or the lifecycle
table went missing is the worst failure this feature has, and it is invisible
from the happy path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import adr_health
import pytest

FRONTMATTER = """---
id: dec-{n:03d}
title: {title}
status: accepted
category: architectural
date: {date}
summary: {summary}
tags: [t]
made_by: agent
affected_files:
{files}
---

# Body
"""


def _adr(root: Path, n: int, *, title="A decision", date="2026-01-01", summary="s", files=()):
    """Write a finalized ADR carrying the given affected_files."""
    d = root / ".ai-state" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    body = FRONTMATTER.format(
        n=n,
        title=title,
        date=date,
        summary=summary,
        files="\n".join(f"  - {f}" for f in files) or "  - noop",
    )
    path = d / f"{n:03d}-slug.md"
    path.write_text(body, encoding="utf-8")
    return path


def _git(root: Path, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo -- history classes cannot be exercised without one."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "seed.txt").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "seed")
    return tmp_path


def _classes(report):
    return {f["path"]: f["decay_class"] for f in report["findings"]}


# -- Non-history classes -------------------------------------------------------


def test_canary_placeholder_shape_is_not_a_retirement_candidate(repo: Path) -> None:
    _adr(repo, 1, files=[".ai-work/<task-slug>/traceability.yml"])
    report = adr_health.classify(repo)
    assert _classes(report)[".ai-work/<task-slug>/traceability.yml"] == "placeholder-shape"


def test_canary_out_of_repo_path_is_not_a_retirement_candidate(repo: Path) -> None:
    _adr(repo, 1, files=["~/.claude/CLAUDE.md"])
    assert _classes(adr_health.classify(repo))["~/.claude/CLAUDE.md"] == "out-of-repo"


def test_canary_lazy_artifact_absence_is_expected(repo: Path) -> None:
    """The inventory declares absence expected; flagging it would be wrong.

    This is the class the user's own objection identified: Praxion has no
    deployments, managed projects do -- absence downstream proves nothing.
    """
    inv = repo / adr_health._INVENTORY
    inv.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| `filler{i}.md` | active | w | n |" for i in range(10))
    inv.write_text(
        "| Artifact | State | Writer | Notes |\n|---|---|---|---|\n"
        f"{rows}\n| `.ai-state/TEST_TOPOLOGY.md` | threshold-lazy | architect | n |\n",
        encoding="utf-8",
    )
    _adr(repo, 1, files=[".ai-state/TEST_TOPOLOGY.md"])
    assert _classes(adr_health.classify(repo))[".ai-state/TEST_TOPOLOGY.md"] == "lazy-artifact"


# -- History classes -----------------------------------------------------------


def test_canary_renamed_subject_is_repaired_not_retired(repo: Path) -> None:
    (repo / "ARCHITECTURE.md").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "mv", "ARCHITECTURE.md", "DESIGN.md")
    _git(repo, "commit", "-qm", "rename")
    _adr(repo, 1, files=["ARCHITECTURE.md"])
    report = adr_health.classify(repo)
    finding = next(f for f in report["findings"] if f["path"] == "ARCHITECTURE.md")
    assert finding["decay_class"] == "renamed"
    assert finding["disposition"] == "update-path"
    assert "DESIGN.md" in finding["detail"]


def test_canary_removed_by_self_is_the_decision_working(repo: Path) -> None:
    (repo / "old_module.py").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-q", "old_module.py")
    _git(repo, "commit", "-qm", "remove")
    _adr(repo, 1, title="Remove the old module", files=["old_module.py"])
    finding = next(f for f in adr_health.classify(repo)["findings"] if f["path"] == "old_module.py")
    assert finding["decay_class"] == "removed-by-self"
    assert finding["disposition"] == "none"


def test_canary_removed_by_later_yields_a_supersession_link(repo: Path) -> None:
    """The highest-value class: an edge that exists in reality but was never recorded."""
    (repo / "subsystem.py").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-q", "subsystem.py")
    _git(repo, "commit", "-qm", "remove")
    _adr(repo, 1, title="Design the subsystem", date="2026-01-01", files=["subsystem.py"])
    _adr(repo, 2, title="Remove the subsystem", date="2026-02-01", files=["subsystem.py"])
    findings = {f["adr"]: f for f in adr_health.classify(repo)["findings"]}
    assert findings["001-slug.md"]["decay_class"] == "removed-by-later"
    assert findings["001-slug.md"]["disposition"] == "link-supersession"
    assert "002-slug.md" in findings["001-slug.md"]["detail"]
    # The remover itself is not asked to supersede anything.
    assert findings["002-slug.md"]["decay_class"] == "removed-by-self"


def test_vanished_is_the_residual_not_the_default(repo: Path) -> None:
    _adr(repo, 1, title="Some decision", files=["never_existed.py"])
    finding = next(
        f for f in adr_health.classify(repo)["findings"] if f["path"] == "never_existed.py"
    )
    assert finding["decay_class"] == "vanished"
    assert finding["disposition"] == "retire-candidate"


# -- Oracle-unavailable withholding -------------------------------------------


def test_canary_missing_history_withholds_rather_than_defaulting(tmp_path: Path) -> None:
    """No git repo: history classes must be withheld, never collapsed to vanished."""
    _adr(tmp_path, 1, title="Remove the module", files=["gone.py"])
    report = adr_health.classify(tmp_path)
    assert _classes(report)["gone.py"] == "unclassified"
    assert any("history unavailable" in w for w in report["withheld"])


def test_canary_unparseable_inventory_withholds_the_lazy_class(repo: Path) -> None:
    """A lifecycle-table format change must not silently retire lazy artifacts."""
    inv = repo / adr_health._INVENTORY
    inv.parent.mkdir(parents=True, exist_ok=True)
    inv.write_text("the table format changed and no rows parse\n", encoding="utf-8")
    _adr(repo, 1, files=[".ai-state/TEST_TOPOLOGY.md"])
    report = adr_health.classify(repo)
    assert any("could not parse" in w for w in report["withheld"])
    assert _classes(report)[".ai-state/TEST_TOPOLOGY.md"] != "lazy-artifact"


def test_shallow_clone_is_treated_as_no_history(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        adr_health,
        "_git",
        lambda root, *a: "true\n" if a[:2] == ("rev-parse", "--is-shallow-repository") else "",
    )
    assert adr_health.history_available(repo) is False


# -- Contract ------------------------------------------------------------------


def test_resolving_references_produce_no_findings(repo: Path) -> None:
    (repo / "present.py").write_text("x", encoding="utf-8")
    _adr(repo, 1, files=["present.py"])
    assert adr_health.classify(repo)["findings"] == []


def test_exits_zero_even_with_findings(repo: Path) -> None:
    """Advisory by construction -- it reports, it does not gate."""
    _adr(repo, 1, files=["never_existed.py"])
    rc = subprocess.run(
        [sys.executable, str(Path(adr_health.__file__)), "--json", "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0
    assert '"vanished"' in rc.stdout


def test_never_mutates_an_adr(repo: Path) -> None:
    """C6: vitals produce candidates; only humans and agents change status."""
    path = _adr(repo, 1, files=["never_existed.py"])
    before = path.read_bytes()
    adr_health.classify(repo)
    assert path.read_bytes() == before
