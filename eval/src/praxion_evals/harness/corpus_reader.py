"""CorpusReader — resolves an invocation target to an immutable Corpus.

Resolver order (first match wins):
    1. Existing filesystem path that resolves inside the repo.
    2. Known worktree name under <repo_root>/.claude/worktrees/<name>/.
    3. Valid git ref (validated via ``git rev-parse --verify``).
    4. Else: raise ValueError with a three-part actionable error message.

For filesystem targets (cases 1 and 2), files are read directly from disk.
For git-ref targets (case 3), files are read via ``git show <ref>:<path>``.

Each subprocess call uses check=False and wraps failures in actionable messages.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from praxion_evals.harness.schemas import Corpus

# ---------------------------------------------------------------------------
# Paths within a corpus root that contain eval-relevant artifacts
# ---------------------------------------------------------------------------

_DECISIONS_DIR = ".ai-state/decisions"
_SPECS_DIR = ".ai-state/specs"
_AI_WORK_DIR = ".ai-work"

_VERIFICATION_REPORT_NAME = "VERIFICATION_REPORT.md"
_ADR_GLOB = "*.md"
_SPEC_GLOB = "SPEC_*.md"


# ---------------------------------------------------------------------------
# CorpusReader
# ---------------------------------------------------------------------------


class CorpusReader:
    """Resolves a target string to a Corpus of eval-relevant artifacts.

    Args:
        repo_root: Absolute path to the repository root. All worktree
                   expansions are relative to this root.
    """

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, target: str) -> Corpus:
        """Resolve *target* to an immutable Corpus.

        Resolution order: filesystem path → worktree name → git ref → error.

        Args:
            target: A filesystem path, worktree name, git ref, or 'main'/'HEAD'.

        Returns:
            A populated Corpus.

        Raises:
            ValueError: If the target cannot be resolved by any strategy,
                        with a three-part message (tried / failed / what to do).
        """
        # Case 1: existing filesystem path
        candidate_path = Path(target)
        if not candidate_path.is_absolute():
            candidate_path = self._root / target
        if candidate_path.exists():
            return self._read_from_filesystem(candidate_path, target_label=str(candidate_path))

        # Case 2: known worktree name
        worktree_path = self._root / ".claude" / "worktrees" / target
        if worktree_path.exists():
            return self._read_from_filesystem(
                worktree_path,
                target_label=f"worktree:{target}",
                target_kind="worktree",
            )

        # Case 3: valid git ref
        if self._is_valid_git_ref(target):
            return self._read_from_git_ref(target)

        # Case 4: unresolvable — three-part error
        raise ValueError(
            f"Cannot resolve target '{target}'. "
            f"Tried: filesystem path '{candidate_path}', "
            f"worktree '.claude/worktrees/{target}', "
            f"git ref '{target}' (git rev-parse returned non-zero). "
            f"To fix: pass an existing path, a worktree name under "
            f".claude/worktrees/, or a valid git ref (SHA, branch, tag)."
        )

    def read_file_at_ref(self, ref: str, relative_path: str) -> str:
        """Read a single file's content at a git ref.

        Args:
            ref: A git ref (SHA, branch name, tag, …).
            relative_path: Path relative to the repo root.

        Returns:
            File contents as a UTF-8 string.

        Raises:
            ValueError: If ``git show`` fails for this path.
        """
        result = subprocess.run(
            ["git", "show", f"{ref}:{relative_path}"],
            cwd=str(self._root),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ValueError(
                f"Could not read '{relative_path}' at ref '{ref}'. "
                f"git show exited {result.returncode}: {result.stderr.strip()}"
            )
        return result.stdout

    # ------------------------------------------------------------------
    # Filesystem reading (cases 1 and 2)
    # ------------------------------------------------------------------

    def _read_from_filesystem(
        self,
        root: Path,
        target_label: str,
        target_kind: str = "path",
    ) -> Corpus:
        decisions = self._scan_filesystem_dir(root / _DECISIONS_DIR, _ADR_GLOB, root)
        specs = self._scan_filesystem_dir(root / _SPECS_DIR, _SPEC_GLOB, root)
        verification_reports = self._scan_verification_reports_filesystem(root)

        return Corpus(
            target_kind=target_kind,  # type: ignore[arg-type]
            target_label=target_label,
            decisions=tuple(decisions),
            specs=tuple(specs),
            verification_reports=tuple(verification_reports),
        )

    def _scan_filesystem_dir(
        self,
        directory: Path,
        glob: str,
        root: Path,
    ) -> list[tuple[str, str]]:
        if not directory.exists():
            return []
        results = []
        for fpath in sorted(directory.glob(glob)):
            try:
                content = fpath.read_text(encoding="utf-8")
                rel = str(fpath.relative_to(root))
                results.append((rel, content))
            except OSError:
                # Non-fatal: skip unreadable files
                pass
        return results

    def _scan_verification_reports_filesystem(
        self,
        root: Path,
    ) -> list[tuple[str, str]]:
        ai_work = root / _AI_WORK_DIR
        if not ai_work.exists():
            return []
        results = []
        for report_file in sorted(ai_work.rglob(_VERIFICATION_REPORT_NAME)):
            try:
                content = report_file.read_text(encoding="utf-8")
                rel = str(report_file.relative_to(root))
                results.append((rel, content))
            except OSError:
                pass
        return results

    # ------------------------------------------------------------------
    # Git-ref reading (case 3)
    # ------------------------------------------------------------------

    def _is_valid_git_ref(self, ref: str) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=str(self._root),
            check=False,
            capture_output=True,
        )
        return result.returncode == 0

    def _read_from_git_ref(self, ref: str) -> Corpus:
        sha = self._resolve_sha(ref)
        short_sha = sha[:7]

        decisions = self._scan_git_ref_dir(ref, _DECISIONS_DIR, _ADR_GLOB)
        specs = self._scan_git_ref_dir(ref, _SPECS_DIR, _SPEC_GLOB)
        # .ai-work/ is gitignored by Praxion convention (always), so no git ref
        # ever contains VERIFICATION_REPORT.md files. Fall back to the repo's
        # working-tree .ai-work/ scan — that is the only place verification
        # reports physically exist.
        verification_reports = self._scan_verification_reports_filesystem(self._root)

        return Corpus(
            target_kind="ref",
            target_label=f"git:{ref} ({short_sha})",
            decisions=tuple(decisions),
            specs=tuple(specs),
            verification_reports=tuple(verification_reports),
        )

    def _resolve_sha(self, ref: str) -> str:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=str(self._root),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ref[:40] if len(ref) >= 7 else ref
        return result.stdout.strip()

    def _scan_git_ref_dir(
        self,
        ref: str,
        directory: str,
        glob_suffix: str,
    ) -> list[tuple[str, str]]:
        """List files in *directory* at *ref* and read matching ones."""
        ls_result = subprocess.run(
            ["git", "ls-tree", "--name-only", ref, f"{directory}/"],
            cwd=str(self._root),
            check=False,
            capture_output=True,
            text=True,
        )
        if ls_result.returncode != 0:
            return []

        results = []
        suffix = glob_suffix.lstrip("*")  # e.g. ".md"
        for filename in sorted(ls_result.stdout.splitlines()):
            filename = filename.strip()
            if not filename:
                continue
            if not filename.endswith(suffix):
                continue
            # filename from ls-tree is already the full relative path
            relative_path = filename
            content_result = subprocess.run(
                ["git", "show", f"{ref}:{relative_path}"],
                cwd=str(self._root),
                check=False,
                capture_output=True,
                text=True,
            )
            if content_result.returncode == 0:
                results.append((relative_path, content_result.stdout))
        return results
