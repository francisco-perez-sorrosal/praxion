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


@pytest.fixture
def plugin_inventory_absent(tmp_path: Path, monkeypatch) -> None:
    """Remove the plugin-relative half of the lifecycle-oracle lookup.

    The oracle resolves from the project root first and the plugin's own tree
    second, so a test exercising oracle-*un*availability has to remove both.
    Without this the fallback finds this repository's real table, the oracle is
    available after all, and the test silently stops testing what it is named
    for -- passing for a reason unrelated to its assertion.
    """
    empty = tmp_path / "no-plugin"
    (empty / "scripts").mkdir(parents=True)
    monkeypatch.setattr(adr_health, "SCRIPT_DIR", empty / "scripts")


def _inventory(path: Path, *, lazy_artifact: str) -> None:
    """Write a lifecycle table declaring one artifact's absence expected."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| `filler{i}.md` | active | w | n |" for i in range(10))
    path.write_text(
        "| Artifact | State | Writer | Notes |\n|---|---|---|---|\n"
        f"{rows}\n| `{lazy_artifact}` | threshold-lazy | architect | n |\n",
        encoding="utf-8",
    )


def _classes(report):
    return {f["path"]: f["decay_class"] for f in report["findings"]}


def _dispositions(report):
    return {f["path"]: f["disposition"] for f in report["findings"]}


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
    _inventory(repo / adr_health._INVENTORY, lazy_artifact=".ai-state/TEST_TOPOLOGY.md")
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


def test_canary_renamed_by_self_is_the_decision_working(repo: Path) -> None:
    """The decision that performed a rename cites the old path by design."""
    (repo / "ARCHITECTURE.md").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "mv", "ARCHITECTURE.md", "DESIGN.md")
    _git(repo, "commit", "-qm", "rename")
    _adr(
        repo,
        1,
        title="Rename ARCHITECTURE.md to DESIGN.md",
        files=["ARCHITECTURE.md", "DESIGN.md"],
    )
    finding = next(
        f for f in adr_health.classify(repo)["findings"] if f["path"] == "ARCHITECTURE.md"
    )
    assert finding["decay_class"] == "renamed-by-self"
    assert finding["disposition"] == "none"


def test_rename_intent_without_citing_the_target_stays_repairable(repo: Path) -> None:
    """Intent alone must not silence a finding.

    `_REMOVAL_INTENT` matches verbs like `replac` and `migrat`, so decisions
    with nothing to do with a rename land in the same index. Two real ones did.
    The discriminating evidence is whether the decision names the rename
    *target* among its own `affected_files`; without it the finding must stay
    `renamed`/`update-path`, because this verdict silences rather than ranks.
    """
    (repo / "ARCHITECTURE.md").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "mv", "ARCHITECTURE.md", "DESIGN.md")
    _git(repo, "commit", "-qm", "rename")
    _adr(
        repo,
        1,
        title="Replace the hardcoded lens set",
        summary="migrate the derivation methodology",
        files=["ARCHITECTURE.md"],
    )
    finding = next(
        f for f in adr_health.classify(repo)["findings"] if f["path"] == "ARCHITECTURE.md"
    )
    assert finding["decay_class"] == "renamed"
    assert finding["disposition"] == "update-path"


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


# -- Directory-shaped references ----------------------------------------------
#
# Git names files, never directories, so a directory reference is never a key in
# the deletion or rename index. Every canary above uses a file-shaped path, and
# that shared assumption -- not any one class -- is what let directory
# references fall through to `vanished` on the live corpus, mislabelling five
# "remove X" decisions as retirement candidates and losing one supersession
# edge. These canaries vary the shape, holding each class fixed.


def test_canary_removed_directory_is_the_decision_working_not_a_candidate(repo: Path) -> None:
    """The live regression: `dec-225` -> `skills/memory/` read as `retire-candidate`."""
    subsystem = repo / "subsystem"
    subsystem.mkdir()
    (subsystem / "a.py").write_text("x", encoding="utf-8")
    (subsystem / "b.py").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-qr", "subsystem")
    _git(repo, "commit", "-qm", "remove")
    _adr(repo, 1, title="Remove the subsystem", files=["subsystem/"])
    finding = next(f for f in adr_health.classify(repo)["findings"] if f["path"] == "subsystem/")
    assert finding["decay_class"] == "removed-by-self"
    assert finding["disposition"] == "none"


def test_canary_directory_removed_by_later_yields_a_supersession_link(repo: Path) -> None:
    """The lost edge: a directory another decision deleted still owes a link."""
    app = repo / "old_app"
    app.mkdir()
    (app / "main.py").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-qr", "old_app")
    _git(repo, "commit", "-qm", "remove")
    _adr(repo, 1, title="Build the old app", date="2026-01-01", files=["old_app/"])
    _adr(repo, 2, title="Replace the old app", date="2026-02-01", files=["old_app/"])
    findings = {f["adr"]: f for f in adr_health.classify(repo)["findings"]}
    assert findings["001-slug.md"]["decay_class"] == "removed-by-later"
    assert findings["001-slug.md"]["disposition"] == "link-supersession"
    assert "002-slug.md" in findings["001-slug.md"]["detail"]


def test_canary_directory_reference_without_a_trailing_slash_still_resolves(repo: Path) -> None:
    """Authors omit the slash; the subtree is the evidence, not the punctuation."""
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "mod.py").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-qr", "pkg")
    _git(repo, "commit", "-qm", "remove")
    _adr(repo, 1, title="Drop the package", files=["pkg"])
    assert _classes(adr_health.classify(repo))["pkg"] == "removed-by-self"


def test_canary_moved_directory_is_renamed_not_removed(repo: Path) -> None:
    """`--no-renames` puts a move in the deletion index too; renames must win."""
    src = repo / "old_dir"
    src.mkdir()
    (src / "a.py").write_text("x" * 200, encoding="utf-8")
    (src / "b.py").write_text("y" * 200, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "mv", "old_dir", "new_dir")
    _git(repo, "commit", "-qm", "move")
    _adr(repo, 1, title="Some decision", files=["old_dir/"])
    finding = next(f for f in adr_health.classify(repo)["findings"] if f["path"] == "old_dir/")
    assert finding["decay_class"] == "renamed"
    assert finding["disposition"] == "update-path"
    assert "new_dir/" in finding["detail"]


def test_canary_remover_citing_the_parent_directory_owns_the_deletion(repo: Path) -> None:
    """The live regression: the remover names the directory, not the files in it.

    The memory-subsystem removal cites `memory-mcp/` and never
    `memory-mcp/pyproject.toml`, so ownership of that file fell to a decision
    that merely listed it and happened to carry a removal verb in its title.
    """
    pkg = repo / "subsystem"
    pkg.mkdir()
    (pkg / "config.toml").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-qr", "subsystem")
    _git(repo, "commit", "-qm", "remove")
    _adr(repo, 1, title="Use the subsystem", date="2026-01-01", files=["subsystem/config.toml"])
    _adr(repo, 2, title="Remove the subsystem", date="2026-02-01", files=["subsystem/"])
    finding = next(f for f in adr_health.classify(repo)["findings"] if f["adr"] == "001-slug.md")
    assert finding["decay_class"] == "removed-by-later"
    assert "002-slug.md" in finding["detail"]


def test_surviving_directory_does_not_claim_deletions_beneath_it(repo: Path) -> None:
    """The decision that *created* a tree must not own every later deletion in it."""
    app = repo / "app"
    app.mkdir()
    (app / "keep.py").write_text("x", encoding="utf-8")
    (app / "drop.py").write_text("x", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    _git(repo, "rm", "-q", "app/drop.py")
    _git(repo, "commit", "-qm", "drop one file")
    _adr(repo, 1, title="Some decision", date="2026-01-01", files=["app/drop.py"])
    _adr(repo, 2, title="Replace the app runtime", date="2026-02-01", files=["app/"])
    finding = next(f for f in adr_health.classify(repo)["findings"] if f["path"] == "app/drop.py")
    assert finding["decay_class"] == "vanished"


def test_canary_terminal_status_decisions_are_skipped(repo: Path) -> None:
    """A superseded decision no longer constrains work; its decay is history.

    This is the exclusion the dimension already specifies -- flag only pairs
    with no supersession link between them. The protocol flips `status` at the
    same moment it writes the field, so status subsumes the link check.
    """
    path = _adr(repo, 1, title="Some decision", files=["never_existed.py"])
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: accepted", "status: superseded"),
        encoding="utf-8",
    )
    report = adr_health.classify(repo)
    assert report["findings"] == []
    assert report["skipped_terminal"] == ["001-slug.md"]


def _retire(path: Path, by: str = "dec-999") -> None:
    """Flip a fixture ADR to the terminal retired status."""
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "status: accepted", f"status: retired\nretired_by:\n  - {by}"
        ),
        encoding="utf-8",
    )


def test_canary_retired_decision_whose_subject_returned_is_a_reopen_candidate(repo: Path) -> None:
    """Retirement is reversible: architecture that comes back finds its reasoning waiting."""
    (repo / "revived.py").write_text("x", encoding="utf-8")
    _retire(_adr(repo, 1, title="Some decision", files=["revived.py"]))
    report = adr_health.classify(repo)
    assert report["reopen_candidates"] == [{"adr": "001-slug.md", "paths_returned": ["revived.py"]}]


def test_retired_decision_whose_subject_is_still_gone_is_not_a_reopen_candidate(
    repo: Path,
) -> None:
    """Retirement is the normal resting state -- it must not nag."""
    _retire(_adr(repo, 1, title="Some decision", files=["still_gone.py"]))
    report = adr_health.classify(repo)
    assert report["reopen_candidates"] == []
    assert report["skipped_terminal"] == ["001-slug.md"]


def test_superseded_decision_is_not_probed_for_reopen(repo: Path) -> None:
    """Only `retired` re-opens: a superseded decision was replaced, not orphaned.

    Its replacement still stands, so a resolving path says nothing about
    whether the old answer should return.
    """
    (repo / "present.py").write_text("x", encoding="utf-8")
    path = _adr(repo, 1, title="Some decision", files=["present.py"])
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: accepted", "status: superseded"),
        encoding="utf-8",
    )
    assert adr_health.classify(repo)["reopen_candidates"] == []


def test_category_mix_reports_corpus_and_recent_window(repo: Path) -> None:
    """A measurement, not a gate -- the recent window is what shows movement."""
    for n in range(1, 5):
        path = _adr(repo, n, files=["present.py"])
        if n > 2:
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "category: architectural", "category: implementation"
                ),
                encoding="utf-8",
            )
    (repo / "present.py").write_text("x", encoding="utf-8")
    mix = adr_health.classify(repo)["category_mix"]
    assert mix["corpus"] == {"architectural": 2, "implementation": 2}
    assert mix["architectural_share_recent"] == 0.5


def test_category_mix_counts_terminal_decisions_too(repo: Path) -> None:
    """Categorisation is an authoring question, so retiring one cannot flatter the ratio.

    The decay classes deliberately skip terminal records; this measurement must
    not, or the share could be improved by retiring decisions rather than by
    categorising new ones correctly.
    """
    _adr(repo, 1, files=["present.py"])
    path = _adr(repo, 2, files=["present.py"])
    path.write_text(
        path.read_text(encoding="utf-8").replace("status: accepted", "status: superseded"),
        encoding="utf-8",
    )
    (repo / "present.py").write_text("x", encoding="utf-8")
    report = adr_health.classify(repo)
    assert report["skipped_terminal"] == ["002-slug.md"]
    assert report["category_mix"]["corpus"] == {"architectural": 2}


def test_directory_that_never_existed_is_still_vanished(repo: Path) -> None:
    """Prefix matching must not manufacture a removal for an empty subtree."""
    _adr(repo, 1, title="Some decision", files=["never_existed/"])
    assert _classes(adr_health.classify(repo))["never_existed/"] == "vanished"


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


def test_canary_unparseable_inventory_withholds_the_lazy_class(
    repo: Path, plugin_inventory_absent: None
) -> None:
    """A lifecycle-table format change must not silently retire lazy artifacts.

    Asserts the *disposition*, not merely that the class changed. Asserting only
    `!= "lazy-artifact"` passes the instant the finding becomes
    `vanished`/`retire-candidate` -- which is the defect this canary is named
    for, not the fix. A canary that cannot fail on the behaviour in its own
    docstring is indistinguishable from no canary.
    """
    inv = repo / adr_health._INVENTORY
    inv.parent.mkdir(parents=True, exist_ok=True)
    inv.write_text("the table format changed and no rows parse\n", encoding="utf-8")
    _adr(repo, 1, files=[".ai-state/TEST_TOPOLOGY.md"])
    report = adr_health.classify(repo)
    assert any("could not parse" in w for w in report["withheld"])
    assert _classes(report)[".ai-state/TEST_TOPOLOGY.md"] == "unclassified"
    assert _dispositions(report)[".ai-state/TEST_TOPOLOGY.md"] == "none"


def test_canary_a_withheld_class_never_re_emerges_as_a_retirement_candidate(
    repo: Path, plugin_inventory_absent: None
) -> None:
    """Withheld has to mean withheld, for the whole report.

    Suppressing a class in `withheld` while re-emitting its members under
    `retire-candidate` -- the one disposition that removes a decision's standing
    -- warns the reader in exactly the wrong direction. Stated as an invariant
    over every finding rather than one path, because the leak was in the shared
    residual and a per-path assertion would miss the next one.
    """
    inv = repo / adr_health._INVENTORY
    inv.parent.mkdir(parents=True, exist_ok=True)
    inv.write_text("no rows parse\n", encoding="utf-8")
    _adr(repo, 1, files=[".ai-state/TEST_TOPOLOGY.md", "never-existed.py"])
    report = adr_health.classify(repo)
    assert report["withheld"], "precondition: the oracle must be unavailable"
    assert [f for f in report["findings"] if f["disposition"] == "retire-candidate"] == []


def test_lifecycle_oracle_resolves_from_the_plugin_when_the_project_has_none(
    repo: Path, tmp_path: Path, monkeypatch
) -> None:
    """The oracle is plugin reference data, so it must resolve from the plugin.

    No onboarding phase writes the lifecycle table into a managed project.
    Resolving it from the project root alone left this oracle permanently
    unavailable for every project except this repository -- the one environment
    where that is invisible.
    """
    plugin = tmp_path / "plugin"
    _inventory(plugin / adr_health._INVENTORY, lazy_artifact=".ai-state/TEST_TOPOLOGY.md")
    monkeypatch.setattr(adr_health, "SCRIPT_DIR", plugin / "scripts")
    _adr(repo, 1, files=[".ai-state/TEST_TOPOLOGY.md"])

    report = adr_health.classify(repo)

    assert report["withheld"] == []
    assert _classes(report)[".ai-state/TEST_TOPOLOGY.md"] == "lazy-artifact"


def test_a_project_table_wins_over_the_plugin_copy(repo: Path, tmp_path: Path, monkeypatch) -> None:
    """The inverse guard: the fallback must not override a project's own table."""
    plugin = tmp_path / "plugin"
    _inventory(plugin / adr_health._INVENTORY, lazy_artifact="plugin-only.md")
    monkeypatch.setattr(adr_health, "SCRIPT_DIR", plugin / "scripts")
    _inventory(repo / adr_health._INVENTORY, lazy_artifact="project-only.md")
    _adr(repo, 1, files=["project-only.md", "plugin-only.md"])

    classes = _classes(adr_health.classify(repo))

    assert classes["project-only.md"] == "lazy-artifact"
    assert classes["plugin-only.md"] != "lazy-artifact"


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


# -- status_edge_conflicts: the five contradiction shapes (a)-(e) --------------
#
# `status_edge_conflicts` is a distinct, mechanical-only array in the report --
# every finding is derivable from frontmatter fields alone, never from prose.
# Each positive fixture below exercises exactly one shape and asserts exactly
# one finding: an over-firing detector is as wrong as a silent one (see the
# module docstring's canary discipline). PM-2 requires the mirror-image
# fixtures too -- legitimate composite histories the enforcer must NOT flag,
# so a false-positive-prone check does not get muted into ignored noise.

_CONFLICT_FRONTMATTER = """---
id: dec-{n:03d}
title: {title}
status: {status}
category: architectural
date: {date}
summary: s
tags: [t]
made_by: agent
affected_files:
  - noop
{extra}
---

# Body
"""


def _conflict_adr(
    root: Path,
    n: int,
    *,
    status="accepted",
    title="A decision",
    date="2026-01-01",
    extra_fields=None,
):
    """Write a finalized ADR carrying arbitrary edge-field frontmatter.

    Distinct from `_adr` above (which only varies `affected_files`) -- these
    fixtures need `supersedes`/`superseded_by`/`supersedes_in_part`/
    `superseded_in_part_by`/`re_affirmed_by`/`retired_by` combinations that the
    decay-class fixtures never touch.
    """
    d = root / ".ai-state" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for key, value in (extra_fields or {}).items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {v}" for v in value)
        else:
            lines.append(f"{key}: {value}")
    body = _CONFLICT_FRONTMATTER.format(
        n=n, title=title, status=status, date=date, extra="\n".join(lines)
    )
    path = d / f"{n:03d}-slug.md"
    path.write_text(body, encoding="utf-8")
    return path


def _conflicts(report):
    return report["status_edge_conflicts"]


def test_shape_a_same_target_in_both_full_supersession_fields(repo: Path) -> None:
    """A record cannot both supersede and be superseded by the same id."""
    _conflict_adr(repo, 1, extra_fields={"supersedes": "dec-002", "superseded_by": "dec-002"})
    conflicts = _conflicts(adr_health.classify(repo))
    assert len(conflicts) == 1
    assert conflicts[0]["shape"] == "a"
    assert conflicts[0]["id"] == "dec-001"


def test_shape_b_partial_edge_on_terminal_status_record(repo: Path) -> None:
    """`supersedes_in_part`/`superseded_in_part_by` requires a non-terminal narrowed status."""
    _conflict_adr(
        repo,
        1,
        status="superseded",
        extra_fields={"superseded_in_part_by": ["dec-002"]},
    )
    conflicts = _conflicts(adr_health.classify(repo))
    assert len(conflicts) == 1
    assert conflicts[0]["shape"] == "b"
    assert conflicts[0]["id"] == "dec-001"


def test_shape_c_narrowing_record_itself_retired(repo: Path) -> None:
    """The record named as the narrowing target must itself be live, not retired/rejected."""
    _conflict_adr(repo, 1, extra_fields={"superseded_in_part_by": ["dec-002"]})
    _conflict_adr(repo, 2, status="retired", extra_fields={"retired_by": ["dec-999"]})
    conflicts = _conflicts(adr_health.classify(repo))
    assert len(conflicts) == 1
    assert conflicts[0]["shape"] == "c"
    assert conflicts[0]["id"] == "dec-001"
    assert "dec-002" in conflicts[0]["detail"]


def test_shape_d_same_id_in_superseded_in_part_by_and_re_affirmed_by(repo: Path) -> None:
    """Migration residue: old-encoding `re_affirmed_by` coexisting with the new field, same target."""
    _conflict_adr(
        repo,
        1,
        extra_fields={"superseded_in_part_by": ["dec-002"], "re_affirmed_by": ["dec-002"]},
    )
    conflicts = _conflicts(adr_health.classify(repo))
    assert len(conflicts) == 1
    assert conflicts[0]["shape"] == "d"
    assert conflicts[0]["id"] == "dec-001"


def test_shape_e_superseded_by_on_non_terminal_record(repo: Path) -> None:
    """A full `superseded_by` edge implies a terminal status; `accepted` contradicts it."""
    _conflict_adr(repo, 1, status="accepted", extra_fields={"superseded_by": "dec-002"})
    conflicts = _conflicts(adr_health.classify(repo))
    assert len(conflicts) == 1
    assert conflicts[0]["shape"] == "e"
    assert conflicts[0]["id"] == "dec-001"


def test_every_conflict_finding_carries_a_disposition(repo: Path) -> None:
    """The conflict-classification protocol names a disposition per shape -- an empty one is not a finding."""
    _conflict_adr(repo, 1, extra_fields={"supersedes": "dec-002", "superseded_by": "dec-002"})
    conflicts = _conflicts(adr_health.classify(repo))
    assert conflicts[0]["disposition"]
    assert isinstance(conflicts[0]["disposition"], str)


# -- status_edge_conflicts: legitimate-negative shapes (PM-2) ------------------


def test_correctly_migrated_partial_pair_emits_zero_conflicts(repo: Path) -> None:
    """The post-migration steady state: reciprocal partial fields, non-terminal narrowed status."""
    _conflict_adr(repo, 1, status="accepted", extra_fields={"superseded_in_part_by": ["dec-002"]})
    _conflict_adr(repo, 2, status="accepted", extra_fields={"supersedes_in_part": ["dec-001"]})
    assert _conflicts(adr_health.classify(repo)) == []


def test_fully_superseded_then_separately_re_affirmed_is_not_a_conflict(repo: Path) -> None:
    """A composite history -- superseded by one record, re-affirmed by an unrelated one -- is legitimate.

    This is the dec-231 shape: `superseded_by` and `re_affirmed_by` name
    DIFFERENT ids. PM-2: an enforcer that fires here mutes itself into noise
    the first time a real composite history like this appears.
    """
    _conflict_adr(
        repo,
        1,
        status="superseded",
        extra_fields={"superseded_by": "dec-002", "re_affirmed_by": ["dec-003"]},
    )
    assert _conflicts(adr_health.classify(repo)) == []


def test_partial_narrowing_with_different_id_re_affirmed_by_is_not_shape_d(repo: Path) -> None:
    """Shape (d) requires the SAME id in both fields -- different ids must not trip it.

    Distinguishes the migration-residue contradiction from a record that
    legitimately carries both a partial narrowing and an unrelated re-affirmation.
    """
    _conflict_adr(
        repo,
        1,
        extra_fields={"superseded_in_part_by": ["dec-002"], "re_affirmed_by": ["dec-003"]},
    )
    assert _conflicts(adr_health.classify(repo)) == []


def test_full_supersession_of_a_different_id_than_the_partial_edge_is_not_a_conflict(
    repo: Path,
) -> None:
    """Shape (a) requires the SAME target in both full fields -- distinct targets are legitimate.

    A record can be fully superseded by one decision while separately having
    narrowed another (via `supersedes_in_part`) -- two unrelated edges, not a
    contradiction.
    """
    _conflict_adr(
        repo,
        1,
        status="superseded",
        extra_fields={"supersedes": "dec-002", "superseded_by": "dec-003"},
    )
    assert _conflicts(adr_health.classify(repo)) == []
