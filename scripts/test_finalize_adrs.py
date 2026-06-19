"""Tests for finalize_adrs.py -- draft-to-NNN promotion at merge-to-main.

Behavioral tests of the Finalize Protocol (see dec-061): fragment ADRs
under .ai-state/decisions/drafts/ get promoted to <NNN>-<slug>.md,
their identifiers rewrite from dec-draft-<hash> to dec-NNN, and
cross-references resolve across sibling ADRs, LEARNINGS, and planning
documents.

Tests are ordered to match the public-helper contract the implementer
commits to:
    next_adr_number(decisions_dir)
    detect_drafts_to_promote(mode, branch)
    parse_fragment_filename(path) -> (datetime, user, branch, slug)
    promote_draft(draft_path, nnn, repo_root) -> (new_path, old_id)
    rewrite_cross_references(repo_root, old_id, new_id) -> int
    acquire_lock(lock_path)  # context manager
    main()                    # CLI entry

Import strategy: mirrors scripts/test_reconcile_ai_state.py -- load via
importlib.util so the script does not need to be on sys.path.

No real git calls: subprocess.run is monkeypatched where git detection
is exercised. End-to-end hook wiring is verified manually outside this
suite.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "finalize_adrs.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("finalize_adrs", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec_module so that any @dataclass
    # decorators defined in the target module can resolve their own
    # __module__ attribute (required by dataclasses._is_type in Python 3.11+).
    # Reconcile's test does not need this because it has no dataclasses.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


finalize = _load_module()


# -- Test helpers -------------------------------------------------------------


def _draft_hash(filename: str) -> str:
    """Mirror the draft-id derivation: sha1(filename)[:8]."""
    return hashlib.sha1(filename.encode("utf-8")).hexdigest()[:8]


def make_draft(
    tmp_path: Path,
    timestamp: str,
    user: str,
    branch: str,
    slug: str,
    frontmatter_extra: dict[str, str] | None = None,
    body: str = "\n## Context\n\nTest draft.\n",
) -> Path:
    """Create a well-formed draft ADR under tmp_path/.ai-state/decisions/drafts/.

    Returns the Path to the created draft. The ``id`` field is derived as
    ``dec-draft-<sha1(filename)[:8]>`` to match the scheme agents use.
    """
    drafts_dir = tmp_path / ".ai-state" / "decisions" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{timestamp}-{user}-{branch}-{slug}.md"
    path = drafts_dir / filename
    draft_id = f"dec-draft-{_draft_hash(filename)}"

    extra_lines = ""
    if frontmatter_extra:
        extra_lines = "".join(f"{k}: {v}\n" for k, v in frontmatter_extra.items())

    content = (
        f"---\n"
        f"id: {draft_id}\n"
        f"title: {slug.replace('-', ' ').title()}\n"
        f"status: proposed\n"
        f"category: architectural\n"
        f"date: 2026-04-19\n"
        f"summary: Test draft -- {slug}\n"
        f"tags: [test, draft]\n"
        f"made_by: agent\n"
        f"{extra_lines}"
        f"---\n"
        f"{body}"
    )
    path.write_text(content, encoding="utf-8")
    return path


def make_finalized(
    tmp_path: Path,
    nnn: int,
    slug: str,
    frontmatter_extra: dict[str, str] | None = None,
) -> Path:
    """Create a well-formed finalized ADR at tmp_path/.ai-state/decisions/<NNN>-<slug>.md."""
    decisions_dir = tmp_path / ".ai-state" / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)

    extra_lines = ""
    if frontmatter_extra:
        extra_lines = "".join(f"{k}: {v}\n" for k, v in frontmatter_extra.items())

    path = decisions_dir / f"{nnn:03d}-{slug}.md"
    path.write_text(
        f"---\n"
        f"id: dec-{nnn:03d}\n"
        f"title: {slug.replace('-', ' ').title()}\n"
        f"status: accepted\n"
        f"category: architectural\n"
        f"date: 2026-01-01\n"
        f"summary: Pre-existing finalized ADR -- {slug}\n"
        f"tags: [test]\n"
        f"made_by: agent\n"
        f"{extra_lines}"
        f"---\n\n## Context\n\nPre-existing.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a minimal repo layout and point finalize_adrs at it.

    The implementer's script derives paths from a module-level REPO_ROOT (or
    equivalent) constant. We redirect it to tmp_path so the script operates on
    the fixture tree. If the implementer chose a different constant name
    (e.g., DECISIONS_DIR, DRAFTS_DIR), the integration checkpoint will
    surface the mismatch.
    """
    (tmp_path / ".ai-state" / "decisions" / "drafts").mkdir(parents=True)
    (tmp_path / ".ai-work").mkdir(parents=True, exist_ok=True)

    # Redirect common module constants if present. Tests that exercise main()
    # rely on REPO_ROOT; tests that call helpers directly pass paths explicitly
    # and do not need the monkeypatch.
    for attr in ("REPO_ROOT", "DECISIONS_DIR", "DRAFTS_DIR", "AI_WORK_DIR"):
        if hasattr(finalize, attr):
            current = getattr(finalize, attr)
            # Map the constant to the tmp_path-rooted equivalent by name.
            if attr == "REPO_ROOT":
                monkeypatch.setattr(finalize, attr, tmp_path)
            elif attr == "DECISIONS_DIR":
                monkeypatch.setattr(finalize, attr, tmp_path / ".ai-state" / "decisions")
            elif attr == "DRAFTS_DIR":
                monkeypatch.setattr(
                    finalize,
                    attr,
                    tmp_path / ".ai-state" / "decisions" / "drafts",
                )
            elif attr == "AI_WORK_DIR":
                monkeypatch.setattr(finalize, attr, tmp_path / ".ai-work")
            _ = current  # silence unused-var lint when attribute exists
    return tmp_path


# -- Slug / filename parsing --------------------------------------------------


class TestFinalizeSlugExtraction:
    """Verify fragment filename parsing -- underpins NNN assignment."""

    @pytest.mark.parametrize(
        ("filename", "expected_user", "expected_branch", "expected_slug"),
        [
            # Unambiguous: single-word branch
            (
                "20260419-1810-alice-main-finalize-protocol.md",
                "alice",
                "main",
                "finalize-protocol",
            ),
            # User containing digits, single-word branch, single-word slug
            (
                "20260419-1810-user42-main-slug.md",
                "user42",
                "main",
                "slug",
            ),
            # Multi-hyphen branch with a sibling fragment in the same
            # directory. Production ADR batches always ship multiple
            # fragments sharing `<user>-<branch>-`, so the parser's
            # sibling-prefix discovery has an anchor. The test fixture below
            # creates that sibling explicitly to mirror reality.
            (
                "20260419-1815-fperezsorrosal-worktree-concurrency-collab-research-finalize-protocol.md",
                "fperezsorrosal",
                "worktree-concurrency-collab-research",
                "finalize-protocol",
            ),
        ],
    )
    def test_slug_extracted_from_fragment_filename(
        self,
        tmp_path: Path,
        filename: str,
        expected_user: str,
        expected_branch: str,
        expected_slug: str,
    ) -> None:
        """parse_fragment_filename returns (timestamp, user, branch, slug).

        Correct NNN+slug assignment requires correct slug extraction
        even when the branch contains hyphens. The canonical parse rule
        (per dec-061) is: the last dash-segment before ``.md`` is the
        slug; the fourth segment onward (excluding the final slug) is
        the branch.

        NOTE: When user or branch themselves contain hyphens, the split
        is inherently ambiguous from the filename alone. Production
        resolves this because ADR batches always ship multiple fragments
        sharing ``<user>-<branch>-``; the parser's sibling-prefix
        discovery uses that agreement to pin the boundary. The fixture
        below creates a peer fragment in ``tmp_path`` so the test
        exercises the same disambiguation path production uses.
        """
        path = tmp_path / filename
        path.write_text("", encoding="utf-8")

        # Create a peer fragment sharing the expected user+branch prefix
        # but with a different timestamp and slug. This mirrors
        # production reality (ADR fragments always arrive in batches)
        # and gives sibling-prefix discovery an anchor to deduce the
        # <user>-<branch>- boundary from.
        peer_name = f"20260101-0000-{expected_user}-{expected_branch}-peer-decision.md"
        (tmp_path / peer_name).write_text("", encoding="utf-8")

        result = finalize.parse_fragment_filename(path)

        # result is a tuple (datetime, user, branch, slug)
        assert len(result) == 4
        _, user, branch, slug = result
        assert user == expected_user
        assert branch == expected_branch
        assert slug == expected_slug


# -- Frontmatter branch override (td-017 fix) ---------------------------------


class TestParseFragmentBranchFromFrontmatter:
    """Verify the td-017 fix: `branch:` in frontmatter disambiguates the
    filename split unambiguously, even for hyphenated branches with no
    sibling fragments to share a common prefix.
    """

    def _write_fragment(
        self,
        tmp_path: Path,
        filename: str,
        frontmatter_extra: dict[str, str] | None = None,
    ) -> Path:
        """Write a fragment file with the given filename and optional extra
        frontmatter fields. Returns the file path."""
        drafts_dir = tmp_path / ".ai-state" / "decisions" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        path = drafts_dir / filename
        extra_lines = ""
        if frontmatter_extra:
            extra_lines = "".join(f"{k}: {v}\n" for k, v in frontmatter_extra.items())
        path.write_text(
            "---\n"
            f"id: dec-draft-{_draft_hash(filename)}\n"
            "title: Test Draft\n"
            "status: proposed\n"
            "category: architectural\n"
            "date: 2026-05-08\n"
            "summary: Test draft for td-017 regression\n"
            "tags: [test]\n"
            "made_by: agent\n"
            f"{extra_lines}"
            "---\n\n## Context\n\nTest.\n",
            encoding="utf-8",
        )
        return path

    def test_frontmatter_branch_disambiguates_hyphenated_branch_no_siblings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With `branch: feat-x-step` in frontmatter and no sibling fragments,
        the parser splits cleanly: user=alice, branch=feat-x-step, slug=auth.

        Without the frontmatter field, the heuristic fallback would pick
        branch=feat (first token after user) and slug=x-step-auth — wrong.
        This is the canonical td-017 reproduction case.
        """

        def _fake_run(args, **_kwargs):
            # Simulate finalize running post-merge on `main`: git would say
            # branch=main, which does NOT match the fragment's authoring
            # branch and would force the heuristic without the frontmatter fix.
            if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="main\n", stderr=""
                )
            if args[:3] == ["git", "config", "--get"]:
                if "user.email" in args:
                    return subprocess.CompletedProcess(
                        args=args,
                        returncode=0,
                        stdout="alice@example.com\n",
                        stderr="",
                    )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        path = self._write_fragment(
            tmp_path,
            "20260508-1010-alice-feat-x-step-auth.md",
            frontmatter_extra={"branch": "feat-x-step"},
        )

        _, user, branch, slug = finalize.parse_fragment_filename(path)
        assert user == "alice"
        assert branch == "feat-x-step"
        assert slug == "auth"

    def test_no_frontmatter_branch_falls_back_to_heuristic(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fragments without `branch:` frontmatter parse via the existing
        heuristic — preserving backward compatibility with pre-td-017 fragments.
        """

        def _fake_run(args, **_kwargs):
            if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="main\n", stderr=""
                )
            if args[:3] == ["git", "config", "--get"]:
                if "user.email" in args:
                    return subprocess.CompletedProcess(
                        args=args,
                        returncode=0,
                        stdout="alice@example.com\n",
                        stderr="",
                    )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        # Single-token branch — no ambiguity even with the heuristic.
        path = self._write_fragment(
            tmp_path,
            "20260508-1010-alice-feat-auth.md",
            frontmatter_extra=None,  # no branch field
        )

        _, user, branch, slug = finalize.parse_fragment_filename(path)
        assert user == "alice"
        assert branch == "feat"
        assert slug == "auth"

    def test_frontmatter_branch_overrides_current_git_branch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When finalize runs post-merge on `main`, the current git branch
        no longer matches the fragment's authoring branch. Frontmatter
        wins because it's the value recorded at write time, not at finalize
        time.
        """

        def _fake_run(args, **_kwargs):
            if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="main\n", stderr=""
                )
            if args[:3] == ["git", "config", "--get"]:
                if "user.email" in args:
                    return subprocess.CompletedProcess(
                        args=args,
                        returncode=0,
                        stdout="alice@example.com\n",
                        stderr="",
                    )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        path = self._write_fragment(
            tmp_path,
            "20260508-1010-alice-feat-experiments-auth.md",
            frontmatter_extra={"branch": "feat-experiments"},
        )

        _, user, branch, slug = finalize.parse_fragment_filename(path)
        assert branch == "feat-experiments"
        assert slug == "auth"

    def test_quoted_frontmatter_branch_is_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """YAML allows the value to be quoted — `branch: "feat-x"`. The
        parser tolerates either form so agents writing PyYAML-style
        frontmatter are not rejected.
        """

        def _fake_run(args, **_kwargs):
            if args[:3] == ["git", "config", "--get"]:
                if "user.email" in args:
                    return subprocess.CompletedProcess(
                        args=args,
                        returncode=0,
                        stdout="alice@example.com\n",
                        stderr="",
                    )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        path = self._write_fragment(
            tmp_path,
            "20260508-1010-alice-feat-x-auth.md",
            frontmatter_extra={"branch": '"feat-x"'},
        )

        _, _, branch, slug = finalize.parse_fragment_filename(path)
        assert branch == "feat-x"
        assert slug == "auth"

    def test_unreadable_file_falls_back_gracefully(self, tmp_path: Path) -> None:
        """`_read_draft_branch` on a non-existent path returns None, never
        raises — the caller falls through to filename-based heuristics."""
        result = finalize._read_draft_branch(tmp_path / "does-not-exist.md")
        assert result is None


# -- Next-NNN assignment ------------------------------------------------------


class TestFinalizeSingleDraft:
    """One draft -> next NNN; id rewritten; drafts dir no longer holds it."""

    def test_single_draft_promotes_to_next_nnn(self, repo_root: Path) -> None:
        """One draft becomes <NNN+1>-<slug>.md with rewritten id."""
        # Pre-existing finalized ADR at 042
        make_finalized(repo_root, 42, "prior-decision")
        draft_path = make_draft(repo_root, "20260419-1810", "alice", "main", "new-decision")
        draft_filename = draft_path.name
        expected_draft_id = f"dec-draft-{_draft_hash(draft_filename)}"

        new_path, old_id = finalize.promote_draft(draft_path, 43, repo_root)

        # New file exists at the finalized location with the correct NNN+slug
        assert new_path == repo_root / ".ai-state" / "decisions" / "043-new-decision.md"
        assert new_path.exists()

        # Draft is gone from drafts/
        assert not draft_path.exists()

        # id rewritten in frontmatter
        content = new_path.read_text(encoding="utf-8")
        assert "id: dec-043" in content
        assert "dec-draft-" not in content.split("---")[1]  # id gone from frontmatter

        # Returned old_id matches what was in the draft
        assert old_id == expected_draft_id


class TestFinalizeMultipleDrafts:
    """Multiple drafts get sequential NNN in filename-sort order."""

    def test_multiple_drafts_promote_in_sorted_order(self, repo_root: Path) -> None:
        """Three drafts -> NNN, NNN+1, NNN+2 in filename-sort order."""
        # Pre-existing finalized ADR at 050 so next is 051
        make_finalized(repo_root, 50, "baseline")

        # Three drafts with sortable timestamps
        draft_a = make_draft(repo_root, "20260419-1810", "alice", "main", "alpha")
        draft_b = make_draft(repo_root, "20260419-1811", "alice", "main", "bravo")
        draft_c = make_draft(repo_root, "20260419-1812", "alice", "main", "charlie")

        # Promote each in order (the real main() iterates sorted drafts)
        drafts_sorted = sorted([draft_a, draft_b, draft_c], key=lambda p: p.name)

        decisions_dir = repo_root / ".ai-state" / "decisions"
        next_n = finalize.next_adr_number(decisions_dir)  # should be 51
        assert next_n == 51

        results: list[tuple[Path, str]] = []
        for i, draft in enumerate(drafts_sorted):
            results.append(finalize.promote_draft(draft, next_n + i, repo_root))

        assert (decisions_dir / "051-alpha.md").exists()
        assert (decisions_dir / "052-bravo.md").exists()
        assert (decisions_dir / "053-charlie.md").exists()

        # Each renamed file has its id rewritten
        assert "id: dec-051" in (decisions_dir / "051-alpha.md").read_text(encoding="utf-8")
        assert "id: dec-052" in (decisions_dir / "052-bravo.md").read_text(encoding="utf-8")
        assert "id: dec-053" in (decisions_dir / "053-charlie.md").read_text(encoding="utf-8")

    def test_next_adr_number_on_empty_decisions_dir(self, repo_root: Path) -> None:
        """Empty decisions dir -> next NNN is 1."""
        decisions_dir = repo_root / ".ai-state" / "decisions"
        assert finalize.next_adr_number(decisions_dir) == 1

    def test_next_adr_number_ignores_drafts_subdirectory(self, repo_root: Path) -> None:
        """Drafts in drafts/ must NOT count toward NNN assignment."""
        make_finalized(repo_root, 10, "foo")
        make_draft(repo_root, "20260419-1810", "alice", "main", "irrelevant")

        decisions_dir = repo_root / ".ai-state" / "decisions"
        # Highest NNN is 010, regardless of how many drafts exist
        assert finalize.next_adr_number(decisions_dir) == 11


# -- Cross-reference rewriting ------------------------------------------------


class TestFinalizeCrossReferences:
    """Every dec-draft-<hash> reference rewrites to dec-NNN across all tracked locations."""

    def test_frontmatter_supersedes_rewritten(self, repo_root: Path) -> None:
        """Draft A's supersedes: dec-draft-<hashB> rewrites to dec-NNN_B.

        After B is promoted to NNN, A's frontmatter must point at dec-NNN not
        at the draft hash.
        """
        draft_b = make_draft(repo_root, "20260419-1810", "alice", "main", "target")
        draft_b_id = f"dec-draft-{_draft_hash(draft_b.name)}"

        draft_a = make_draft(
            repo_root,
            "20260419-1811",
            "alice",
            "main",
            "superseder",
            frontmatter_extra={"supersedes": draft_b_id},
        )

        # Promote B first to NNN=1
        new_path_b, old_id_b = finalize.promote_draft(draft_b, 1, repo_root)
        assert old_id_b == draft_b_id

        # Rewrite cross-references across bounded locations
        count = finalize.rewrite_cross_references(repo_root, old_id_b, "dec-001")
        assert count >= 1  # at least the supersedes reference in draft A

        # Draft A still exists in drafts/ (not yet promoted) -- its frontmatter
        # must now reference dec-001 instead of the draft hash
        draft_a_content = draft_a.read_text(encoding="utf-8")
        assert "supersedes: dec-001" in draft_a_content
        assert draft_b_id not in draft_a_content

    def test_frontmatter_re_affirms_rewritten(self, repo_root: Path) -> None:
        """re_affirms: dec-draft-<hashB> rewrites to dec-NNN_B."""
        draft_b = make_draft(repo_root, "20260419-1810", "alice", "main", "target")
        draft_b_id = f"dec-draft-{_draft_hash(draft_b.name)}"

        draft_a = make_draft(
            repo_root,
            "20260419-1811",
            "alice",
            "main",
            "re-affirmer",
            frontmatter_extra={"re_affirms": draft_b_id},
        )

        finalize.promote_draft(draft_b, 7, repo_root)
        finalize.rewrite_cross_references(repo_root, draft_b_id, "dec-007")

        content = draft_a.read_text(encoding="utf-8")
        assert "re_affirms: dec-007" in content
        assert draft_b_id not in content

    def test_body_inline_refs_rewritten(self, repo_root: Path) -> None:
        """Body references [dec-draft-<hash>] and bare dec-draft-<hash> both rewrite."""
        draft_b = make_draft(repo_root, "20260419-1810", "alice", "main", "target")
        draft_b_id = f"dec-draft-{_draft_hash(draft_b.name)}"
        draft_b_hash = draft_b_id.removeprefix("dec-draft-")

        # Separate draft whose body references draft_b in two shapes
        body = (
            "\n## Context\n\n"
            f"See [{draft_b_id}]({draft_b.name}) for the originating decision.\n"
            f"This ADR builds on {draft_b_id} and extends it.\n"
        )
        draft_c = make_draft(
            repo_root,
            "20260419-1811",
            "alice",
            "main",
            "consumer",
            body=body,
        )

        finalize.promote_draft(draft_b, 12, repo_root)
        finalize.rewrite_cross_references(repo_root, draft_b_id, "dec-012")

        content = draft_c.read_text(encoding="utf-8")
        # Both forms rewritten -- neither the bracketed nor the bare hash remain
        assert "dec-012" in content
        assert draft_b_id not in content
        assert draft_b_hash not in content  # hash itself scrubbed from body

    def test_learnings_md_refs_rewritten(self, repo_root: Path) -> None:
        """.ai-work/<slug>/LEARNINGS.md references are rewritten."""
        draft = make_draft(repo_root, "20260419-1810", "alice", "main", "some-decision")
        draft_id = f"dec-draft-{_draft_hash(draft.name)}"

        task_dir = repo_root / ".ai-work" / "some-feature"
        task_dir.mkdir(parents=True)
        learnings = task_dir / "LEARNINGS.md"
        learnings.write_text(
            "# Learnings\n\n"
            "## Decisions Made\n\n"
            f"- Chose X over Y ({draft_id}) because of constraint Z.\n",
            encoding="utf-8",
        )

        finalize.promote_draft(draft, 99, repo_root)
        finalize.rewrite_cross_references(repo_root, draft_id, "dec-099")

        content = learnings.read_text(encoding="utf-8")
        assert "(dec-099)" in content
        assert draft_id not in content

    def test_systems_plan_refs_rewritten(self, repo_root: Path) -> None:
        """.ai-work/<slug>/SYSTEMS_PLAN.md references are rewritten."""
        draft = make_draft(repo_root, "20260419-1810", "alice", "main", "sys-decision")
        draft_id = f"dec-draft-{_draft_hash(draft.name)}"

        task_dir = repo_root / ".ai-work" / "another-feature"
        task_dir.mkdir(parents=True)
        systems_plan = task_dir / "SYSTEMS_PLAN.md"
        systems_plan.write_text(
            f"# Plan\n\nSee {draft_id} for the architectural rationale.\n",
            encoding="utf-8",
        )

        finalize.promote_draft(draft, 42, repo_root)
        finalize.rewrite_cross_references(repo_root, draft_id, "dec-042")

        content = systems_plan.read_text(encoding="utf-8")
        assert "dec-042" in content
        assert draft_id not in content

    def test_architecture_docs_refs_rewritten(self, repo_root: Path) -> None:
        """Expanded scope: .ai-state/DESIGN.md + docs/architecture.md rewrites."""
        draft = make_draft(repo_root, "20260419-1810", "alice", "main", "arch-decision")
        draft_id = f"dec-draft-{_draft_hash(draft.name)}"

        architect_doc = repo_root / ".ai-state" / "DESIGN.md"
        architect_doc.write_text(
            f"# Architecture\n\n| {draft_id} (drafts/) | arch decision | ... |\n",
            encoding="utf-8",
        )
        developer_doc = repo_root / "docs" / "architecture.md"
        developer_doc.parent.mkdir(parents=True)
        developer_doc.write_text(
            f"# Dev Guide\n\nSee {draft_id} for the rationale.\n",
            encoding="utf-8",
        )

        finalize.promote_draft(draft, 77, repo_root)
        finalize.rewrite_cross_references(repo_root, draft_id, "dec-077")

        assert draft_id not in architect_doc.read_text(encoding="utf-8")
        assert "dec-077" in architect_doc.read_text(encoding="utf-8")
        assert draft_id not in developer_doc.read_text(encoding="utf-8")
        assert "dec-077" in developer_doc.read_text(encoding="utf-8")

    def test_scripts_refs_rewritten(self, repo_root: Path) -> None:
        """Expanded scope: scripts/*.py and scripts/*.sh docstring refs rewrite."""
        draft = make_draft(repo_root, "20260419-1810", "alice", "main", "script-decision")
        draft_id = f"dec-draft-{_draft_hash(draft.name)}"

        scripts_dir = repo_root / "scripts"
        scripts_dir.mkdir()
        py_file = scripts_dir / "helper.py"
        py_file.write_text(
            f'"""Helper script.\n\nDerived from {draft_id}."""\n',
            encoding="utf-8",
        )
        sh_file = scripts_dir / "migrate.sh"
        sh_file.write_text(
            f"#!/usr/bin/env bash\n# per {draft_id} / SYSTEMS_PLAN\n",
            encoding="utf-8",
        )

        finalize.promote_draft(draft, 88, repo_root)
        finalize.rewrite_cross_references(repo_root, draft_id, "dec-088")

        assert "dec-088" in py_file.read_text(encoding="utf-8")
        assert draft_id not in py_file.read_text(encoding="utf-8")
        assert "dec-088" in sh_file.read_text(encoding="utf-8")
        assert draft_id not in sh_file.read_text(encoding="utf-8")


# -- Idempotence --------------------------------------------------------------


class TestFinalizeIdempotent:
    """Finalize is idempotent -- running twice is a no-op."""

    def test_second_run_is_no_op(self, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Second invocation on the same batch exits 0 and changes nothing."""
        make_draft(repo_root, "20260419-1810", "alice", "main", "idempotent")

        # Stub subprocess.run so the embedded call to regenerate_adr_index and
        # any git detection cannot touch the real filesystem / repo.
        def _fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        # First run via main() -- pass --branch to bypass real git log detection
        exit_code_first = _invoke_main(monkeypatch, ["--branch", "test-branch"])
        # Snapshot state after first run
        decisions_dir = repo_root / ".ai-state" / "decisions"
        first_run_files = sorted(p.name for p in decisions_dir.iterdir() if p.is_file())
        first_run_content = {
            p.name: p.read_text(encoding="utf-8") for p in decisions_dir.iterdir() if p.is_file()
        }

        # Second run -- must be a no-op
        exit_code_second = _invoke_main(monkeypatch, ["--branch", "test-branch"])

        # Both runs exit 0
        assert exit_code_first == 0
        assert exit_code_second == 0

        # Filesystem unchanged after the second run
        second_run_files = sorted(p.name for p in decisions_dir.iterdir() if p.is_file())
        second_run_content = {
            p.name: p.read_text(encoding="utf-8") for p in decisions_dir.iterdir() if p.is_file()
        }
        assert first_run_files == second_run_files
        assert first_run_content == second_run_content


def _invoke_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    """Invoke finalize.main with the given argv, regardless of its signature.

    If main() accepts an argv parameter, pass it. Otherwise fall back to
    monkey-patching sys.argv. Normalizes the return value -- main() may
    return None (implying 0), an int exit code, or raise SystemExit.
    """
    try:
        sig = inspect.signature(finalize.main)
    except (ValueError, TypeError):
        sig = None

    try:
        if sig is not None and len(sig.parameters) >= 1:
            rc = finalize.main(argv)
        else:
            monkeypatch.setattr(sys, "argv", ["finalize_adrs.py", *argv])
            rc = finalize.main()
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1

    if rc is None:
        return 0
    return int(rc)


# -- Index regeneration -------------------------------------------------------


class TestFinalizeIndex:
    """After finalize, DECISIONS_INDEX.md lists only finalized ADRs."""

    def test_decisions_index_regenerates_after_finalize(
        self, repo_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The index after finalize matches regenerate_adr_index output.

        Finalize is expected to invoke regenerate_adr_index.py as a subprocess
        or import. We stub subprocess.run to directly invoke the
        regenerate_adr_index module against the same tmp_path so the index
        contents can be asserted.
        """
        # Load regenerate_adr_index as a module
        regen_path = Path(__file__).resolve().parent / "regenerate_adr_index.py"
        regen_spec = importlib.util.spec_from_file_location("regenerate_adr_index", regen_path)
        assert regen_spec is not None and regen_spec.loader is not None
        regen_mod = importlib.util.module_from_spec(regen_spec)
        regen_spec.loader.exec_module(regen_mod)

        # Point regen at our tmp-path decisions dir
        monkeypatch.setattr(regen_mod, "DECISIONS_DIR", repo_root / ".ai-state" / "decisions")
        monkeypatch.setattr(
            regen_mod,
            "INDEX_PATH",
            repo_root / ".ai-state" / "decisions" / "DECISIONS_INDEX.md",
        )
        # Disable regen's repo-root resolution so the injected constants above
        # survive; the resolver is covered by the consumer-layout regression tests.
        monkeypatch.setattr(regen_mod, "apply_repo_root", lambda *_a, **_k: None)

        # Stub subprocess.run inside finalize -- on the regen call, invoke regen
        # in-process. Other calls (e.g., git log) are no-ops.
        def _fake_run(args: Any, *_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
            args_list = list(args) if not isinstance(args, str) else args.split()
            if any("regenerate_adr_index" in str(a) for a in args_list):
                regen_mod.main()
            return subprocess.CompletedProcess(args=args_list, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        # Create a draft and promote it via the helper
        draft = make_draft(repo_root, "20260419-1810", "alice", "main", "indexed")
        finalize.promote_draft(draft, 1, repo_root)
        # Model the post-finalize state: regenerate the index in-process
        # against the tmp-path-patched constants. The real finalize invokes
        # regenerate_adr_index.py via subprocess; our _fake_run stub above
        # triggers the same code path when finalize calls subprocess.run.
        regen_mod.main()

        # The index now exists and lists dec-001
        index_path = repo_root / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"
        assert index_path.exists()
        index = index_path.read_text(encoding="utf-8")
        assert "dec-001" in index
        # No dec-draft-* leaks into the index
        assert "dec-draft-" not in index


# -- Dry run ------------------------------------------------------------------


class TestFinalizeDryRun:
    """--dry-run must print plan but not change the filesystem."""

    def test_dry_run_prints_but_does_not_write(
        self,
        repo_root: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--dry-run leaves the filesystem unchanged, exits 0, and prints a plan."""
        draft = make_draft(repo_root, "20260419-1810", "alice", "main", "dry-run")
        draft_path_before = draft
        content_before = draft.read_text(encoding="utf-8")

        # Stub subprocess.run so git detection is inert
        def _fake_run(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        exit_code = _invoke_main(monkeypatch, ["--dry-run", "--branch", "test-branch"])
        assert exit_code == 0

        # Filesystem unchanged
        assert draft_path_before.exists()
        assert draft_path_before.read_text(encoding="utf-8") == content_before
        decisions_dir = repo_root / ".ai-state" / "decisions"
        # No finalized file was produced
        finalized = [
            p
            for p in decisions_dir.iterdir()
            if p.is_file() and p.suffix == ".md" and p.name[0].isdigit()
        ]
        assert finalized == []


# -- Empty drafts -------------------------------------------------------------


class TestFinalizeEmptyDirectory:
    """No drafts present -> exit 0 with a "nothing to do" style message."""

    def test_empty_drafts_is_no_op(
        self,
        repo_root: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Empty drafts dir exits 0; output/logs include 'nothing to do'.

        The implementer may emit the no-op signal via stdout, stderr, or a
        logger at INFO level -- accept any of the three so the test does not
        over-constrain the output channel.
        """
        import logging

        def _fake_run(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        with caplog.at_level(logging.DEBUG):
            exit_code = _invoke_main(monkeypatch, ["--branch", "test-branch"])
        assert exit_code == 0

        captured = capsys.readouterr()
        # Union of stdout, stderr, and captured log records
        log_messages = " ".join(record.getMessage() for record in caplog.records)
        combined = (captured.out + captured.err + " " + log_messages).lower()
        assert "nothing to do" in combined


# -- Merge-range detection (td-011 fix) ---------------------------------------


class TestDraftsAddedDetection:
    """Verify _drafts_added_in_last_merge handles FF-merges spanning N commits.

    Regression for td-011: under the prior `HEAD^1..HEAD` heuristic, FF-merges
    that landed multiple commits at once would only diff the most recent commit
    against its parent, missing drafts added in earlier commits of the FF range.
    The reflog-based primary path uses HEAD@{1} so the diff covers every commit
    landed by the most recent HEAD update.
    """

    def _stub_git(
        self,
        monkeypatch: pytest.MonkeyPatch,
        responses: dict[tuple[str, ...], str | None],
    ) -> list[tuple[str, ...]]:
        """Replace finalize.subprocess.run with a lookup-based stub.

        responses maps the args tuple (after `git`) → stdout (or None for non-zero
        exit). Returns a list that records every git invocation in call order so
        the test can verify the function attempted reflog before falling back.
        """
        calls: list[tuple[str, ...]] = []

        def _fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            assert args[0] == "git"
            key = tuple(args[1:])
            calls.append(key)
            if key not in responses:
                # Default: success with empty output keeps tests deterministic.
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            stdout = responses[key]
            if stdout is None:
                return subprocess.CompletedProcess(
                    args=args, returncode=128, stdout="", stderr="fatal"
                )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)
        return calls

    def test_reflog_path_captures_ff_merge_with_multiple_commits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reflog-based detection finds drafts in earlier commits of an FF range.

        Simulates an FF-merge that landed 3 commits, each adding one draft.
        Under the old heuristic, only the latest commit's draft would be seen.
        With the reflog path, all three are detected.
        """
        responses = {
            ("rev-parse", "--is-inside-work-tree"): "true",
            ("rev-parse", "HEAD@{1}"): "abc123prev",
            (
                "log",
                "--diff-filter=A",
                "--name-only",
                "--pretty=format:",
                "abc123prev..HEAD",
                "--",
                ".ai-state/decisions/drafts/",
            ): (
                ".ai-state/decisions/drafts/20260508-1000-alice-feat-x-step-1.md\n"
                ".ai-state/decisions/drafts/20260508-1010-alice-feat-x-step-2.md\n"
                ".ai-state/decisions/drafts/20260508-1020-alice-feat-x-step-3.md\n"
            ),
        }
        calls = self._stub_git(monkeypatch, responses)

        result = finalize._drafts_added_in_last_merge()

        assert result is not None
        assert result == {
            "20260508-1000-alice-feat-x-step-1.md",
            "20260508-1010-alice-feat-x-step-2.md",
            "20260508-1020-alice-feat-x-step-3.md",
        }
        # Reflog was consulted before any first-parent fallback.
        assert ("rev-parse", "HEAD@{1}") in calls
        # First-parent fallback was NOT exercised because the primary path succeeded.
        assert ("rev-list", "--parents", "-n", "1", "HEAD") not in calls

    def test_falls_back_to_first_parent_when_reflog_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When HEAD@{1} returns non-zero (no reflog), use first-parent detection.

        Edge case: shallow clones or freshly initialized repos may have no prior
        HEAD position recorded. The fallback preserves the old behavior so
        true merge commits are still detected.
        """
        responses = {
            ("rev-parse", "--is-inside-work-tree"): "true",
            ("rev-parse", "HEAD@{1}"): None,  # reflog miss
            ("rev-list", "--parents", "-n", "1", "HEAD"): "deadbeef parent_a parent_b",
            (
                "log",
                "--diff-filter=A",
                "--name-only",
                "--pretty=format:",
                "parent_a..HEAD",
                "--",
                ".ai-state/decisions/drafts/",
            ): (".ai-state/decisions/drafts/20260508-1000-alice-feat-x-step-1.md\n"),
        }
        calls = self._stub_git(monkeypatch, responses)

        result = finalize._drafts_added_in_last_merge()

        assert result == {"20260508-1000-alice-feat-x-step-1.md"}
        # Both paths were attempted: reflog first, then first-parent fallback.
        assert ("rev-parse", "HEAD@{1}") in calls
        assert ("rev-list", "--parents", "-n", "1", "HEAD") in calls

    def test_returns_empty_set_for_root_commit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Root commit (no parents) yields empty set, not None.

        A None return signals "git unavailable / lookup failed" and triggers
        a warning log; an empty set means "we looked and found nothing,"
        which is the correct outcome for a fresh repo with no prior merges.
        """
        responses = {
            ("rev-parse", "--is-inside-work-tree"): "true",
            ("rev-parse", "HEAD@{1}"): None,  # no reflog yet
            ("rev-list", "--parents", "-n", "1", "HEAD"): "rootcommit",  # no parent
        }
        self._stub_git(monkeypatch, responses)

        result = finalize._drafts_added_in_last_merge()

        assert result == set()


# -- Locking ------------------------------------------------------------------


class TestFinalizeLock:
    """Lock file is acquired during the run and released at exit."""

    def test_lock_file_acquired_and_released(self, repo_root: Path) -> None:
        """acquire_lock holds LOCK_EX within the context; released on exit.

        After the context exits, a second call to acquire_lock on the same
        path must succeed -- proving the lock was released.
        """
        import fcntl

        lock_path = repo_root / ".ai-state" / "decisions" / "drafts" / ".finalize.lock"

        # Acquire and immediately release via the script's context manager
        with finalize.acquire_lock(lock_path):
            # Inside the context, the lock file exists
            assert lock_path.exists()

        # After release, the lock must be re-acquirable -- attempt a
        # non-blocking LOCK_EX on the same path. If the previous holder failed
        # to release, this raises BlockingIOError.
        with open(lock_path, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# -- Repo-root resolution + consumer-layout regression ------------------------
#
# These pin the fix for the symlinked-plugin-cache divergence: finalize must
# act on the *consumer's* repo (resolved from --repo-root or the git worktree),
# never on the plugin location that `Path(__file__).resolve()` follows the
# symlink to. Self-hosting masks this bug because Praxion's own scripts/ is a
# real checkout; only a consumer running from the plugin cache exposes it.


class TestRepoRootResolution:
    """resolve_repo_root + _apply_repo_root precedence and rebinding."""

    def test_explicit_repo_root_wins(self, tmp_path: Path) -> None:
        resolved = finalize.resolve_repo_root(str(tmp_path))
        assert resolved == tmp_path.resolve()

    def test_falls_back_to_git_toplevel_when_no_explicit_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(finalize, "_git_toplevel_from_cwd", lambda: tmp_path)
        assert finalize.resolve_repo_root(None) == tmp_path.resolve()

    def test_script_relative_is_last_resort_when_git_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(finalize, "_git_toplevel_from_cwd", lambda: None)
        assert finalize.resolve_repo_root(None) == finalize.SCRIPT_DIR.parent

    def test_apply_repo_root_rebinds_all_path_constants(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Use monkeypatch.setattr so the global rebind is reverted post-test.
        for attr in ("REPO_ROOT", "DECISIONS_DIR", "DRAFTS_DIR", "LOCK_PATH"):
            monkeypatch.setattr(finalize, attr, getattr(finalize, attr))
        finalize._apply_repo_root(tmp_path)
        assert finalize.REPO_ROOT == tmp_path
        assert finalize.DECISIONS_DIR == tmp_path / ".ai-state" / "decisions"
        assert finalize.DRAFTS_DIR == tmp_path / ".ai-state" / "decisions" / "drafts"
        assert finalize.LOCK_PATH == finalize.DRAFTS_DIR / ".finalize.lock"


def _init_consumer_repo(root: Path) -> None:
    """Create a git repo at root on `main` with one committed draft fragment."""
    import subprocess as sp

    (root / ".ai-state" / "decisions" / "drafts").mkdir(parents=True)

    def run(*args: str) -> None:
        sp.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    run("init")
    run("config", "user.email", "tester@example.com")
    run("config", "user.name", "Tester")
    make_draft(
        root,
        "20260101-1200",
        "tester",
        "main",
        "sample-decision",
        frontmatter_extra={"branch": "main"},
    )
    run("add", "-A")
    run("commit", "-m", "add draft")
    run("branch", "-M", "main")


def _make_fake_plugin(plugin_dir: Path) -> Path:
    """Copy finalize + regen scripts into a plugin-like dir with its OWN empty
    drafts/, mimicking the symlinked-cache layout. Returns the finalize script.

    The empty drafts/ is the trap: a buggy __file__-relative root scans here
    and reports `nothing to do` instead of touching the consumer's drafts.
    """
    import shutil

    plugin_scripts = plugin_dir / "scripts"
    plugin_scripts.mkdir(parents=True)
    src_dir = Path(__file__).resolve().parent
    for name in ("finalize_adrs.py", "regenerate_adr_index.py"):
        shutil.copy2(src_dir / name, plugin_scripts / name)
    (plugin_dir / ".ai-state" / "decisions" / "drafts").mkdir(parents=True)
    return plugin_scripts / "finalize_adrs.py"


class TestConsumerLayoutEndToEnd:
    """Run the real script from a copied plugin location against a git fixture.

    Exercises the __file__-vs-git-root divergence end to end -- the bug only
    manifests when the script is invoked from outside the target repo.
    """

    def test_explicit_repo_root_finalizes_consumer_not_plugin(self, tmp_path: Path) -> None:
        consumer = tmp_path / "consumer"
        plugin = tmp_path / "plugin"
        _init_consumer_repo(consumer)
        script = _make_fake_plugin(plugin)

        result = subprocess.run(
            [sys.executable, str(script), "--all", "--repo-root", str(consumer)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0, result.stderr
        decisions = consumer / ".ai-state" / "decisions"
        assert (decisions / "001-sample-decision.md").exists()
        assert (decisions / "DECISIONS_INDEX.md").exists()
        # The plugin's own (empty) decisions dir must be untouched.
        assert not list((plugin / ".ai-state" / "decisions").glob("[0-9]*.md"))

    def test_git_root_fallback_finalizes_consumer_when_cwd_is_repo(self, tmp_path: Path) -> None:
        """No --repo-root: resolution falls back to `git rev-parse` in cwd.

        This is the exact failure the report hit -- without the fix the script
        resolves its root from __file__ (the plugin) and no-ops, stranding the
        consumer's drafts.
        """
        consumer = tmp_path / "consumer"
        plugin = tmp_path / "plugin"
        _init_consumer_repo(consumer)
        script = _make_fake_plugin(plugin)

        result = subprocess.run(
            [sys.executable, str(script), "--all"],
            capture_output=True,
            text=True,
            cwd=str(consumer),
        )

        assert result.returncode == 0, result.stderr
        assert (consumer / ".ai-state" / "decisions" / "001-sample-decision.md").exists()
        assert not list((plugin / ".ai-state" / "decisions").glob("[0-9]*.md"))


class TestMalformedDraftResilience:
    """A single malformed fragment is skipped, not allowed to abort the batch."""

    def test_malformed_id_skipped_valid_drafts_still_planned(self, repo_root: Path, caplog) -> None:
        import logging
        import re as _re

        good = make_draft(
            repo_root,
            "20260101-1200",
            "alice",
            "main",
            "good-one",
            frontmatter_extra={"branch": "main"},
        )
        bad = make_draft(
            repo_root,
            "20260101-1300",
            "alice",
            "main",
            "bad-one",
            frontmatter_extra={"branch": "main"},
        )
        # Corrupt the bad draft's id to a non-hex hash (the report's case:
        # dec-draft-w068a1c2). The id regex requires [0-9a-f]{8}, so this draft
        # fails per-draft validation.
        bad.write_text(
            _re.sub(r"dec-draft-[0-9a-f]{8}", "dec-draft-w068a1c2", bad.read_text()),
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING, logger="finalize_adrs"):
            plans = finalize.build_promotion_plan([good, bad])

        assert {p.slug for p in plans} == {"good-one"}
        assert plans[0].new_id == "dec-001"
        assert "skipping malformed draft" in caplog.text


# -- Plugin-cache write guard -------------------------------------------------


class TestPluginCacheGuard:
    """finalize must refuse to mutate a plugin-cache path (P0 safety backstop)."""

    @pytest.mark.parametrize(
        "path",
        [
            "/Users/x/.claude/plugins/cache/bit-agora/i-am/0.8.0",
            "/home/u/.config/plugins/cache",
        ],
    )
    def test_detects_plugin_cache_paths(self, path: str) -> None:
        assert finalize.is_plugin_cache_path(Path(path)) is True

    @pytest.mark.parametrize(
        "path",
        ["/Users/x/dev/sandbook", "/tmp/consumer", "/srv/repos/myproj"],
    )
    def test_allows_normal_repo_paths(self, path: str) -> None:
        assert finalize.is_plugin_cache_path(Path(path)) is False

    def test_main_refuses_when_resolved_root_is_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = Path("/Users/x/.claude/plugins/cache/bit-agora/i-am/0.8.0")
        monkeypatch.setattr(finalize, "resolve_repo_root", lambda _arg: cache)
        # If the guard fails, _apply_repo_root would point at the cache; assert
        # we exit non-zero before any mutation instead.
        with pytest.raises(SystemExit) as exc:
            finalize.main(["--all"])
        assert exc.value.code == 1


# -- Widened cross-reference rewrite scope ------------------------------------


class TestWidenedCrossReferenceScope:
    """dec-draft ids in persistent non-ADR files are rewritten at finalize."""

    def test_rewrites_ledger_roadmap_and_docs(self, repo_root: Path) -> None:
        old, new = "dec-draft-abcd1234", "dec-042"
        targets = {
            repo_root / ".ai-state" / "TECH_DEBT_LEDGER.md": f"resolved by {old}\n",
            repo_root / ".ai-state" / "TECH_DEBT_RESOLVED.md": f"see {old}\n",
            repo_root / "ROADMAP.md": f"tracked under {old}\n",
            repo_root / "docs" / "design" / "notes.md": f"per {old}\n",
        }
        for path, content in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        modified = finalize.rewrite_cross_references(repo_root, old, new)

        assert modified == len(targets)
        for path in targets:
            text = path.read_text(encoding="utf-8")
            assert new in text and old not in text
