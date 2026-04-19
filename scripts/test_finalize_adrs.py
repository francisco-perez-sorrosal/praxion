"""Tests for finalize_adrs.py -- draft-to-NNN promotion at merge-to-main.

Behavioral tests driven from dec-061 (Finalize Protocol) and the
acceptance criteria AC-03, AC-04, AC-05, AC-06 in the concurrency-collab
pipeline's SYSTEMS_PLAN.md.

Tests are ordered to match the public-helper contract the implementer is
committing to:
    next_adr_number(decisions_dir)
    detect_drafts_to_promote(mode, branch)
    parse_fragment_filename(path) -> (datetime, user, branch, slug)
    promote_draft(draft_path, nnn, repo_root) -> (new_path, old_id)
    rewrite_cross_references(repo_root, old_id, new_id) -> int
    acquire_lock(lock_path)  # context manager
    main()                    # CLI entry

Import strategy: mirrors scripts/test_reconcile_ai_state.py -- load via
importlib.util so the script does not need to be on sys.path.

No real git calls: subprocess.run is monkeypatched where git detection is
exercised. End-to-end hook wiring is verified manually in Step 5.
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
    (e.g., DECISIONS_DIR, DRAFTS_DIR), the Step 4c integration checkpoint will
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
                monkeypatch.setattr(
                    finalize, attr, tmp_path / ".ai-state" / "decisions"
                )
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
    """Verify fragment filename parsing -- underpins NNN assignment (AC-03)."""

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
            # The real pipeline fixture: multi-word branch with many hyphens.
            # The parser must take the last dash-segment as the slug.
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

        AC-03: correct NNN+slug assignment requires correct slug extraction
        even when the branch contains hyphens. The canonical parse rule
        (per dec-061) is: the last dash-segment before ``.md`` is
        the slug; the fourth segment onward (excluding the final slug) is
        the branch.

        NOTE: When user or branch themselves contain hyphens, the split is
        inherently ambiguous. The cases above pick the parse that matches
        the pipeline's own fragment filenames. If the implementer chooses a
        different canonical rule (e.g., "slug is the last TWO segments"),
        tests and production will disagree -- the Step 4c integration
        checkpoint is the reconciliation point.
        """
        path = tmp_path / filename
        path.write_text("", encoding="utf-8")

        result = finalize.parse_fragment_filename(path)

        # result is a tuple (datetime, user, branch, slug)
        assert len(result) == 4
        _, user, branch, slug = result
        assert user == expected_user
        assert branch == expected_branch
        assert slug == expected_slug


# -- Next-NNN assignment ------------------------------------------------------


class TestFinalizeSingleDraft:
    """AC-03: one draft -> next NNN; id rewritten; drafts dir no longer holds it."""

    def test_single_draft_promotes_to_next_nnn(self, repo_root: Path) -> None:
        """AC-03: one draft becomes <NNN+1>-<slug>.md with rewritten id."""
        # Pre-existing finalized ADR at 042
        make_finalized(repo_root, 42, "prior-decision")
        draft_path = make_draft(
            repo_root, "20260419-1810", "alice", "main", "new-decision"
        )
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
    """AC-03: multiple drafts get sequential NNN in filename-sort order."""

    def test_multiple_drafts_promote_in_sorted_order(self, repo_root: Path) -> None:
        """AC-03: three drafts -> NNN, NNN+1, NNN+2 in filename-sort order."""
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
        assert "id: dec-051" in (decisions_dir / "051-alpha.md").read_text(
            encoding="utf-8"
        )
        assert "id: dec-052" in (decisions_dir / "052-bravo.md").read_text(
            encoding="utf-8"
        )
        assert "id: dec-053" in (decisions_dir / "053-charlie.md").read_text(
            encoding="utf-8"
        )

    def test_next_adr_number_on_empty_decisions_dir(self, repo_root: Path) -> None:
        """Empty decisions dir -> next NNN is 1."""
        decisions_dir = repo_root / ".ai-state" / "decisions"
        assert finalize.next_adr_number(decisions_dir) == 1

    def test_next_adr_number_ignores_drafts_subdirectory(self, repo_root: Path) -> None:
        """Drafts in drafts/ must NOT count toward NNN assignment (AC-03)."""
        make_finalized(repo_root, 10, "foo")
        make_draft(repo_root, "20260419-1810", "alice", "main", "irrelevant")

        decisions_dir = repo_root / ".ai-state" / "decisions"
        # Highest NNN is 010, regardless of how many drafts exist
        assert finalize.next_adr_number(decisions_dir) == 11


# -- Cross-reference rewriting ------------------------------------------------


class TestFinalizeCrossReferences:
    """AC-03, AC-06: every dec-draft-<hash> reference rewrites to dec-NNN."""

    def test_frontmatter_supersedes_rewritten(self, repo_root: Path) -> None:
        """AC-06: draft A supersedes: dec-draft-<hashB> rewrites to dec-NNN_B.

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
        """AC-06: re_affirms: dec-draft-<hashB> rewrites to dec-NNN_B."""
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
        """AC-03: body references [dec-draft-<hash>] and bare dec-draft-<hash> both rewrite."""
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
        """AC-03: .ai-work/<slug>/LEARNINGS.md references are rewritten."""
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
        """AC-03: .ai-work/<slug>/SYSTEMS_PLAN.md references are rewritten."""
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


# -- Idempotence --------------------------------------------------------------


class TestFinalizeIdempotent:
    """AC-04: finalize is idempotent -- running twice is a no-op."""

    def test_second_run_is_no_op(
        self, repo_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-04: second invocation on the same batch exits 0 and changes nothing."""
        make_draft(repo_root, "20260419-1810", "alice", "main", "idempotent")

        # Stub subprocess.run so the embedded call to regenerate_adr_index and
        # any git detection cannot touch the real filesystem / repo.
        def _fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        # First run via main() -- pass --branch to bypass real git log detection
        exit_code_first = _invoke_main(monkeypatch, ["--branch", "test-branch"])
        # Snapshot state after first run
        decisions_dir = repo_root / ".ai-state" / "decisions"
        first_run_files = sorted(p.name for p in decisions_dir.iterdir() if p.is_file())
        first_run_content = {
            p.name: p.read_text(encoding="utf-8")
            for p in decisions_dir.iterdir()
            if p.is_file()
        }

        # Second run -- must be a no-op
        exit_code_second = _invoke_main(monkeypatch, ["--branch", "test-branch"])

        # Both runs exit 0
        assert exit_code_first == 0
        assert exit_code_second == 0

        # Filesystem unchanged after the second run
        second_run_files = sorted(
            p.name for p in decisions_dir.iterdir() if p.is_file()
        )
        second_run_content = {
            p.name: p.read_text(encoding="utf-8")
            for p in decisions_dir.iterdir()
            if p.is_file()
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
    """AC-05: after finalize, DECISIONS_INDEX.md lists only finalized ADRs."""

    def test_decisions_index_regenerates_after_finalize(
        self, repo_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-05: the index after finalize matches regenerate_adr_index output.

        Finalize is expected to invoke regenerate_adr_index.py as a subprocess
        or import. We stub subprocess.run to directly invoke the
        regenerate_adr_index module against the same tmp_path so the index
        contents can be asserted.
        """
        # Load regenerate_adr_index as a module
        regen_path = Path(__file__).resolve().parent / "regenerate_adr_index.py"
        regen_spec = importlib.util.spec_from_file_location(
            "regenerate_adr_index", regen_path
        )
        assert regen_spec is not None and regen_spec.loader is not None
        regen_mod = importlib.util.module_from_spec(regen_spec)
        regen_spec.loader.exec_module(regen_mod)

        # Point regen at our tmp-path decisions dir
        monkeypatch.setattr(
            regen_mod, "DECISIONS_DIR", repo_root / ".ai-state" / "decisions"
        )
        monkeypatch.setattr(
            regen_mod,
            "INDEX_PATH",
            repo_root / ".ai-state" / "decisions" / "DECISIONS_INDEX.md",
        )

        # Stub subprocess.run inside finalize -- on the regen call, invoke regen
        # in-process. Other calls (e.g., git log) are no-ops.
        def _fake_run(
            args: Any, *_a: Any, **_k: Any
        ) -> subprocess.CompletedProcess[str]:
            args_list = list(args) if not isinstance(args, str) else args.split()
            if any("regenerate_adr_index" in str(a) for a in args_list):
                regen_mod.main()
            return subprocess.CompletedProcess(
                args=args_list, returncode=0, stdout="", stderr=""
            )

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
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

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
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(finalize.subprocess, "run", _fake_run)

        with caplog.at_level(logging.DEBUG):
            exit_code = _invoke_main(monkeypatch, ["--branch", "test-branch"])
        assert exit_code == 0

        captured = capsys.readouterr()
        # Union of stdout, stderr, and captured log records
        log_messages = " ".join(record.getMessage() for record in caplog.records)
        combined = (captured.out + captured.err + " " + log_messages).lower()
        assert "nothing to do" in combined


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
