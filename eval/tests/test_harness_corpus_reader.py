"""Behavioral tests for CorpusReader — the 4-path arg-resolver contract.

All production imports are deferred inside each test body so pytest collection
succeeds before the harness package exists (RED-state handshake).

Resolver order under test:
  1. Existing filesystem path inside the repo -> filesystem read, target_kind="path"
  2. Known worktree name under .claude/worktrees/<name>/ -> expands to fs path
  3. Valid git ref via git rev-parse -> git-show read, target_kind="ref"
  4. Invalid target -> three-part error message (what tried / what failed / what to try)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolver case 1: existing filesystem path
# ---------------------------------------------------------------------------


def test_existing_path_resolves_to_corpus_with_path_kind(tmp_path: Path):
    """An existing directory path returns a Corpus with target_kind='path'."""
    # Seed a minimal .ai-state/ tree so CorpusReader has something to read
    ai_state = tmp_path / ".ai-state"
    (ai_state / "decisions").mkdir(parents=True)
    (ai_state / "specs").mkdir(parents=True)

    from praxion_evals.harness.corpus_reader import CorpusReader
    from praxion_evals.harness.schemas import Corpus

    reader = CorpusReader(repo_root=tmp_path)
    corpus = reader.resolve(str(tmp_path))

    assert isinstance(corpus, Corpus)
    assert corpus.target_kind == "path"


def test_existing_path_corpus_label_reflects_the_path(tmp_path: Path):
    """Corpus.target_label captures the resolved target for display in reports."""
    (tmp_path / ".ai-state" / "decisions").mkdir(parents=True)
    (tmp_path / ".ai-state" / "specs").mkdir(parents=True)

    from praxion_evals.harness.corpus_reader import CorpusReader

    reader = CorpusReader(repo_root=tmp_path)
    corpus = reader.resolve(str(tmp_path))

    # The label must reference the path in some identifiable way
    assert tmp_path.name in corpus.target_label or str(tmp_path) in corpus.target_label


# ---------------------------------------------------------------------------
# Resolver case 2: known worktree name
# ---------------------------------------------------------------------------


def test_known_worktree_name_resolves_to_its_filesystem_path(tmp_path: Path):
    """A worktree name under .claude/worktrees/<name>/ expands to that directory."""
    # Create a fake worktree directory
    worktree_dir = tmp_path / ".claude" / "worktrees" / "my-feature"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / ".ai-state" / "decisions").mkdir(parents=True)
    (worktree_dir / ".ai-state" / "specs").mkdir(parents=True)

    from praxion_evals.harness.corpus_reader import CorpusReader
    from praxion_evals.harness.schemas import Corpus

    reader = CorpusReader(repo_root=tmp_path)
    corpus = reader.resolve("my-feature")

    assert isinstance(corpus, Corpus)
    assert corpus.target_kind in ("path", "worktree")


def test_known_worktree_corpus_label_names_the_worktree(tmp_path: Path):
    """Corpus label identifies the worktree name for report traceability."""
    worktree_dir = tmp_path / ".claude" / "worktrees" / "sprint-99"
    worktree_dir.mkdir(parents=True)
    (worktree_dir / ".ai-state" / "decisions").mkdir(parents=True)
    (worktree_dir / ".ai-state" / "specs").mkdir(parents=True)

    from praxion_evals.harness.corpus_reader import CorpusReader

    reader = CorpusReader(repo_root=tmp_path)
    corpus = reader.resolve("sprint-99")

    assert "sprint-99" in corpus.target_label


# ---------------------------------------------------------------------------
# Resolver case 3: valid git ref
# ---------------------------------------------------------------------------


def _init_git_repo_with_ai_state(repo: Path) -> str:
    """Seed a minimal git repo with .ai-state/ content and return the HEAD SHA."""
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    ai_decisions = repo / ".ai-state" / "decisions"
    ai_decisions.mkdir(parents=True)
    (ai_decisions / "001-example.md").write_text(
        "---\nid: dec-001\ntitle: Example\nstatus: accepted\n---\n\n## Context\n\nN/A\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_valid_git_ref_resolves_to_corpus_with_ref_kind(tmp_path: Path):
    """A valid git SHA returns a Corpus with target_kind='ref'."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_git_repo_with_ai_state(repo)

    from praxion_evals.harness.corpus_reader import CorpusReader
    from praxion_evals.harness.schemas import Corpus

    reader = CorpusReader(repo_root=repo)
    corpus = reader.resolve(sha)

    assert isinstance(corpus, Corpus)
    assert corpus.target_kind == "ref"


def test_valid_git_ref_corpus_label_contains_sha(tmp_path: Path):
    """Corpus label for a git-ref target contains the SHA for report traceability."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_git_repo_with_ai_state(repo)

    from praxion_evals.harness.corpus_reader import CorpusReader

    reader = CorpusReader(repo_root=repo)
    corpus = reader.resolve(sha)

    # At minimum the short SHA (first 7 chars) appears in the label
    assert sha[:7] in corpus.target_label


# ---------------------------------------------------------------------------
# Resolver case 4: invalid target — three-part error message
# ---------------------------------------------------------------------------


def test_invalid_target_raises_with_three_part_error(tmp_path: Path):
    """An unresolvable target raises an error naming what was tried, what failed, what to try."""
    import pytest

    from praxion_evals.harness.corpus_reader import CorpusReader

    reader = CorpusReader(repo_root=tmp_path)

    # The acceptance contract for this case is a three-part error:
    # what was tried / what failed / what to try. The resolver raises
    # ValueError with an actionable message.
    with pytest.raises(ValueError, match=r"(?i)(tried|attempt|path|worktree|ref)") as exc_info:
        reader.resolve("xyzzy-not-a-ref-or-path-or-worktree-12345")

    msg = str(exc_info.value)
    # The three-part contract requires a substantive, actionable message.
    assert len(msg) > 50, f"Error message too short to be actionable: {msg!r}"


def test_invalid_target_error_message_names_the_target(tmp_path: Path):
    """The error message must name the failed target so the user can diagnose it."""
    import pytest

    from praxion_evals.harness.corpus_reader import CorpusReader

    bad_target = "completely-bogus-target-xyz"
    reader = CorpusReader(repo_root=tmp_path)

    with pytest.raises(ValueError, match=bad_target) as exc_info:
        reader.resolve(bad_target)

    assert bad_target in str(exc_info.value), (
        f"Error message should name the failing target '{bad_target}'"
    )


# ---------------------------------------------------------------------------
# git show fallback: per-file content retrieval
# ---------------------------------------------------------------------------


def test_git_show_retrieves_file_content_at_ref(tmp_path: Path):
    """CorpusReader reads individual file content via git-show at a git ref."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_git_repo_with_ai_state(repo)

    from praxion_evals.harness.corpus_reader import CorpusReader

    reader = CorpusReader(repo_root=repo)
    corpus = reader.resolve(sha)

    # The seeded ADR should appear in the decisions tuple
    assert len(corpus.decisions) > 0, "At least one decision should be read from the git ref"
    # Find the seeded file
    paths = [rel for rel, _content in corpus.decisions]
    assert any("001-example.md" in p for p in paths), (
        f"Expected 001-example.md in decisions; got paths: {paths}"
    )


def test_git_show_decision_content_matches_committed_text(tmp_path: Path):
    """Content retrieved via git-show matches the exact committed text."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_git_repo_with_ai_state(repo)

    from praxion_evals.harness.corpus_reader import CorpusReader

    reader = CorpusReader(repo_root=repo)
    corpus = reader.resolve(sha)

    content_map = dict(corpus.decisions)
    matching = {k: v for k, v in content_map.items() if "001-example.md" in k}
    assert matching, "001-example.md should be in corpus.decisions"
    content = next(iter(matching.values()))
    assert "dec-001" in content
    assert "## Context" in content
