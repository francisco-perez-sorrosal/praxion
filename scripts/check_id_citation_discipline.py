#!/usr/bin/env python3
"""ID citation discipline checker (inbound isolation).

Scans code files (Python, TS, JS, Rust, Go, etc.) for references to ephemeral
pipeline identifiers — REQ-*, AC-*, EC-X.X.X, Step N, test_req{NN}_* /
test_ac{NN}_* function naming, class Test*Req{NN}* / class Test*Ac{NN}*
class naming, and dec-draft-<hash> citations. Those identifiers live in
documents that get deleted with .ai-work/ or renamed at ADR finalize, so
in-code citations dangle the moment the pipeline cleans up or promotes.

This is the inbound counterpart to
``scripts/check_shipped_artifact_isolation.py``: that script prevents shipped
artifacts from citing ``.ai-state/`` entries; this script prevents code from
citing ephemeral ``.ai-work/`` entries.

Rationale lives in ``rules/swe/id-citation-discipline.md``.

Escape hatch: add ``id-citation-discipline:ignore`` on the same line as an
intentional reference (comment syntax varies by language — the check only
requires the literal substring to be present on the line).

Exempt paths (teaching materials handled by shipped-artifact-isolation):
  rules/, skills/, agents/, commands/, claude/config/
Exempt paths (pipeline/history/docs state):
  .ai-work/, .ai-state/, docs/, CHANGELOG.md, ROADMAP.md
Exempt paths (test fixtures/data):
  **/tests/fixtures/**, **/testdata/**

Exit codes: 0 clean, 1 violations found, 2 script error.

Usage:
    python3 scripts/check_id_citation_discipline.py
    python3 scripts/check_id_citation_discipline.py --files FILE [FILE ...]
    python3 scripts/check_id_citation_discipline.py --repo-root PATH
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from _git_runner import run_git

CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".rb",
        ".sh",
        ".swift",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
    }
)

EXEMPT_PATH_PREFIXES = (
    ".ai-work/",
    ".ai-state/",
    "docs/",
    "rules/",
    "skills/",
    "agents/",
    "commands/",
    "claude/config/",
    "cursor/config/",
)

EXEMPT_FILENAMES = frozenset(
    {
        "CHANGELOG.md",
        "ROADMAP.md",
        # Installer scripts use "Step N — <phase>" as user-facing progress
        # UI labels; those are not pipeline-citation metadata.
        "install.sh",
        "install_claude.sh",
        "install_cursor.sh",
    }
)

# Specific files exempted because they describe the forbidden patterns as
# part of their own documentation (detector scripts). Without this, each
# detector would flag its own pattern strings and block every commit.
EXEMPT_EXACT_PATHS = frozenset(
    {
        "scripts/check_id_citation_discipline.py",
        "scripts/check_shipped_artifact_isolation.py",
        # Test fixtures for the detectors themselves necessarily contain the
        # forbidden patterns as test inputs — same self-referential exemption
        # logic as the detector scripts above.
        "tests/test_check_id_citation_discipline.py",
        # The pipeline-recovery reconciler PARSES "Step N" labels out of WIP.md /
        # IMPLEMENTATION_PLAN.md — the step number is its input grammar, not a
        # citation to an ephemeral spec — and its tests use "Step 1" as fixture
        # data. Same self-referential exemption as the detector scripts above.
        "scripts/reconcile_pipeline_state.py",
        "scripts/test_reconcile_pipeline_state.py",
    }
)

EXCLUDED_PATH_FRAGMENTS = (
    "/tests/fixtures/",
    "/testdata/",
    "/test_fixtures/",
    "/__pycache__/",
    "/.git/",
    # Sibling git worktrees. `.claude/worktrees/<name>/` holds a SEPARATE
    # checkout of this same repository, usually at a different commit. Scanning
    # it reports violations that are not in this checkout's tree, vanish when
    # the worktree is removed, and never appear in CI (a fresh clone has no
    # worktrees) — so the gate's result would depend on how many worktrees the
    # operator happens to have open. Each worktree is scanned by its own run.
    "/.claude/worktrees/",
    # Vendored dependency trees — never scan third-party library code.
    "/.venv/",
    "/venv/",
    "/vendor/",
    "/node_modules/",
    "/.tox/",
    "/dist/",
    "/build/",
    "/.cache/",
    "/htmlcov/",
    "/.mypy_cache/",
    "/.pytest_cache/",
    "/.ruff_cache/",
    "/site-packages/",
)

IGNORE_MARKER = "id-citation-discipline:ignore"

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "req-id",
        re.compile(r"\bREQ-[A-Z0-9][A-Z0-9\-]*\b"),
        "REQ identifier (e.g., REQ-SG-01) — describe behavior inline; "
        "REQ→test mapping belongs in .ai-work/<slug>/traceability.yml",
    ),
    (
        "ac-id",
        re.compile(r"\bAC-\d+\b"),
        "AC identifier (e.g., AC-14) — acceptance criteria live only in "
        "ephemeral SYSTEMS_PLAN.md; describe behavior inline",
    ),
    (
        "ec-id",
        re.compile(r"\bEC-\d+\.\d+(?:\.\d+)*\b"),
        "EC identifier (e.g., EC-3.2.4) — ephemeral criterion from "
        "SYSTEMS_PLAN.md; describe behavior inline",
    ),
    (
        "step-ref",
        re.compile(r"\bStep \d+[a-z]?\b"),
        "Step reference (e.g., Step 4c) — pipeline-local, deleted with "
        ".ai-work/; remove or rephrase without the step number",
    ),
    (
        "test-req-name",
        re.compile(r"\bdef test_req\d+"),
        "test function name with REQ prefix — name after the behavior "
        "(e.g., test_expired_token_returns_401)",
    ),
    (
        "test-ac-name",
        re.compile(r"\bdef test_ac\d+"),
        "test function name with AC prefix — name after the behavior",
    ),
    (
        "class-req-name",
        re.compile(r"\bclass Test\w*Req\d+\w*"),
        "test class name with Req{NN} in the identifier — name after the behavioral "
        "concept (e.g., TestSecretRedaction)",
    ),
    (
        "class-ac-name",
        re.compile(r"\bclass Test\w*Ac\d+\w*"),
        "test class name with Ac{NN} in the identifier — name after the behavioral concept",
    ),
    (
        "draft-adr-id",
        re.compile(r"\bdec-draft-[0-9a-f]{8}\b"),
        "draft ADR id — drafts/ fragments are renamed at finalize; cite the "
        "finalized dec-NNN instead, or mark a fixture literal with the ignore marker",
    ),
)


_SHEBANG_INTERPRETERS = ("bash", "sh", "zsh", "dash", "ksh")
_SHEBANG_PATTERNS = (
    *(re.compile(rf"\b{shell}\b") for shell in _SHEBANG_INTERPRETERS),
    # `python`, `python3`, `python3.11` -- an extensionless Python executable
    # carries exactly the same citation obligations as its `.py` siblings, but
    # a shell-only interpreter list skipped every one of them silently.
    re.compile(r"\bpython[0-9.]*"),
)


def is_script_shebang(path: Path) -> bool:
    """Return True if `path`'s first line is a recognized script shebang.

    Extensionless executable scripts (e.g., `scripts/dispatch-reworks`) escape
    the extension-based corpus selection. Shebang detection brings them back
    into scope so id-citation violations in them are not silently skipped on
    commit -- for the Python executables in `scripts/` as much as the shell
    ones.
    """
    try:
        with path.open("rb") as f:
            first_line = f.readline(256)
    except OSError:
        return False
    try:
        text = first_line.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return False
    if not text.startswith("#!"):
        return False
    return any(pattern.search(text) for pattern in _SHEBANG_PATTERNS)


def is_excluded_path(rel_path: Path) -> bool:
    """Exclude by location *inside the repository*, never by absolute path.

    Every fragment in EXCLUDED_PATH_FRAGMENTS describes a directory nested in
    the repo being scanned. Matching them against the absolute path silently
    inverts the `/.claude/worktrees/` intent: when the scan runs from inside a
    worktree, every file's absolute path contains that fragment, so the whole
    checkout is dropped and the gate reports `scanned 0 code file(s)` while
    exiting 0. Matching against the repo-root-relative path keeps sibling
    worktrees out of a canonical-checkout scan and keeps a worktree's own run
    scanning its own files.
    """
    rel_str = "/" + str(rel_path).replace("\\", "/")
    return any(fragment in rel_str for fragment in EXCLUDED_PATH_FRAGMENTS)


def is_exempt_by_path(rel_path: Path) -> bool:
    rel_str = str(rel_path).replace("\\", "/")
    if rel_str in EXEMPT_EXACT_PATHS:
        return True
    if rel_str in EXEMPT_FILENAMES:
        return True
    for prefix in EXEMPT_PATH_PREFIXES:
        if rel_str == prefix.rstrip("/") or rel_str.startswith(prefix):
            return True
    return False


def iter_code_files(repo_root: Path) -> list[Path]:
    """Full-repo corpus: code files by extension plus extensionless bash scripts.

    Walks with ``os.walk`` and prunes excluded directories *before* descending
    into them. The earlier ``rglob`` enumeration filtered ``node_modules``,
    sibling worktrees and the like only after visiting every file inside them,
    which on a checkout with an installed dashboard took longer than the
    PreToolUse hook budget — so the commit gate timed out and failed open on
    the main checkout while a fresh worktree (no ``node_modules``) finished in
    time and blocked. Pruning makes the walk cost proportional to the corpus.
    """
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        rel_dir = Path(dirpath).relative_to(repo_root)
        # Prune by repo-relative location so the walk never enters an excluded
        # subtree; `is_excluded_path` matches directory fragments, so probe
        # with a placeholder child name.
        dirnames[:] = sorted(d for d in dirnames if not is_excluded_path(rel_dir / d / "_probe_"))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = rel_dir / name
            if is_exempt_by_path(rel) or is_excluded_path(rel):
                continue
            if path.suffix in CODE_EXTENSIONS:
                if path.is_file():
                    files.append(path)
                continue
            # Extensionless executable scripts identified by shebang.
            # Heuristic: only executable files are scanned in full-repo mode to
            # keep false positives down (most extensionless text files are not
            # scripts).
            if path.suffix or not path.is_file():
                continue
            if not os.access(path, os.X_OK):
                continue
            if not is_script_shebang(path):
                continue
            files.append(path)
    return files


_COMMIT_ALL_FLAG = re.compile(r"(?:^|\s)(?:-a|--all|-[a-zA-Z]*a[a-zA-Z]*)(?:\s|$)")


_GIT_RETRIES = 3
_GIT_RETRY_SLEEP = 0.1


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run a git command, retrying transient failures (index-lock contention).

    Concurrent git activity in the same worktree — a sibling agent committing,
    a finalize hook firing — can make an index-reading command fail for a
    moment. Retrying a few times absorbs that; a persistent failure returns
    ``None`` so the caller can choose a safe response rather than misread it.
    """
    for attempt in range(_GIT_RETRIES):
        try:
            # Through the shared runner: this gate fires on every `git commit`,
            # so it always runs with git's repository-scoping variables in the
            # environment -- exported *relative*, which silently re-targets any
            # call naming a different repository than the firing hook's.
            result = run_git(cwd, *args)
        except OSError:
            # git could not be run to completion (resource pressure, transient
            # exec failure, the runner's timeout -- GitUnavailableError is an
            # OSError). Treat as a failed call so the caller falls to its
            # pass-safe path rather than crashing the gate.
            result = None
        if result is not None and result.returncode == 0:
            return result
        if attempt + 1 < _GIT_RETRIES:
            time.sleep(_GIT_RETRY_SLEEP)
    return None


def _git_changed_names(repo_root: Path, *diff_args: str) -> list[str]:
    result = _git(repo_root, "diff", "--name-only", "--diff-filter=ACMR", "-z", *diff_args)
    if result is None:
        return []
    return [name for name in result.stdout.split("\0") if name]


class _ScopeUnavailable:
    """Marker: hook mode is in effect but the commit scope could not be computed."""


def hook_scope_files(
    payload: dict, default_root: Path
) -> tuple[Path, list[Path]] | type[_ScopeUnavailable] | None:
    """Resolve the file set a ``git commit`` about to run would actually record.

    Invoked as a PreToolUse hook the script receives the tool payload on stdin
    and no ``--files``. The commit's scope is the staged set, plus the
    tracked-but-unstaged modifications when the command carries ``-a``/``--all``
    (``-am`` included). Three outcomes: the scoped file list; ``None`` when the
    payload's directory is not inside a git repository (a genuine non-hook
    caller — the full scan is right); and ``_ScopeUnavailable`` when we are in a
    git repo but scoping failed even after retries — the caller must pass rather
    than full-scan, because gating a commit on the whole tree's pre-existing
    violations is never the right hook behaviour.
    """
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command", ""))
    cwd = Path(str(payload.get("cwd") or default_root))
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if top is None:
        # The commit-gate wrapper only fires on a real `git commit`, so when its
        # env signal is present a git failure is never "not a repo" — it is
        # contention, and a whole-repo scan would wrongly gate the commit on
        # unrelated pre-existing violations. Return the pass-safe marker.
        if os.environ.get(_PAYLOAD_ENV):
            return _ScopeUnavailable
        # Direct CLI: distinguish "not a repo" (full scan is correct) from a
        # transient error inside a repo with one quick probe.
        try:
            probe = run_git(cwd, "rev-parse", "--is-inside-work-tree")
        except OSError:
            return None
        if probe.returncode != 0:
            return None
        return _ScopeUnavailable
    if not top.stdout.strip():
        return None
    repo_root = Path(top.stdout.strip()).resolve()
    names = _git_changed_names(repo_root, "--cached")
    if _COMMIT_ALL_FLAG.search(command):
        names.extend(_git_changed_names(repo_root))
    return repo_root, [repo_root / name for name in dict.fromkeys(names)]


_STDIN_PROBE_SECONDS = 1.0
_PAYLOAD_ENV = "PRAXION_COMMIT_PAYLOAD"


def _stdin_has_payload() -> bool:
    """True when stdin should be read for a hook payload.

    The commit-gate wrapper exports ``PRAXION_COMMIT_PAYLOAD`` and pipes the
    payload with a closing writer, so that signal is authoritative and immune
    to load — a blocking read behind it always reaches EOF. Without the signal
    (a direct CLI or test invocation) we fall back to a readiness probe: a
    non-terminal stream with data waiting is a piped payload; an inherited
    *open* pipe that never writes is not, and a blind ``read()`` there would
    hang, so the probe consumes nothing and treats "not ready" as no payload.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return False
        if os.environ.get(_PAYLOAD_ENV):
            return True
        import select

        ready, _, _ = select.select([sys.stdin], [], [], _STDIN_PROBE_SECONDS)
        return bool(ready)
    except (OSError, ValueError, ImportError):
        return False


def _hook_scope_from_stdin(
    default_root: Path,
) -> tuple[Path, list[Path]] | type[_ScopeUnavailable] | None:
    """Return the hook-mode scope when stdin carries a tool payload.

    ``None`` means "not a hook payload" (the full scan is right); a
    ``_ScopeUnavailable`` marker means "a hook payload, but scoping failed" (the
    caller must pass, never full-scan).
    """
    if not _stdin_has_payload():
        return None
    # Under the commit-payload signal, any failure to read or parse the payload
    # must resolve pass-safe, never to a whole-repo scan that blocks the commit
    # — a truncated read under load is a transient, not a reason to gate on
    # unrelated pre-existing violations. Without the signal (direct CLI), a
    # non-payload stdin correctly falls through to the full scan.
    signalled = bool(os.environ.get(_PAYLOAD_ENV))
    on_failure: type[_ScopeUnavailable] | None = _ScopeUnavailable if signalled else None
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return on_failure
    if not raw.strip():
        return on_failure
    try:
        payload = json.loads(raw)
    except ValueError:
        return on_failure
    if not isinstance(payload, dict) or "tool_input" not in payload:
        return on_failure
    return hook_scope_files(payload, default_root)


def scan_file(path: Path) -> list[tuple[int, str, str, str]]:
    findings: list[tuple[int, str, str, str]] = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return findings

    for line_no, line in enumerate(content.splitlines(), start=1):
        if IGNORE_MARKER in line:
            continue
        for name, pattern, description in PATTERNS:
            if pattern.search(line):
                findings.append((line_no, name, description, line.rstrip()))
                break  # one pattern report per line keeps output readable
    return findings


def filter_files(explicit_files: list[Path], repo_root: Path) -> list[Path]:
    out: list[Path] = []
    for candidate in explicit_files:
        abs_path = candidate if candidate.is_absolute() else (repo_root / candidate).resolve()
        if not abs_path.is_file():
            continue
        # Accept recognized code extensions OR extensionless files with a
        # recognized script shebang. Explicit user-passed paths (e.g., from
        # pre-commit's staged-files list) override the executable-bit
        # heuristic used in full-repo scans.
        if abs_path.suffix not in CODE_EXTENSIONS and not is_script_shebang(abs_path):
            continue
        try:
            rel = abs_path.relative_to(repo_root)
        except ValueError:
            continue
        if is_exempt_by_path(rel) or is_excluded_path(rel):
            continue
        out.append(abs_path)
    return out


def format_findings(files: list[Path], repo_root: Path) -> tuple[int, list[str]]:
    lines: list[str] = []
    total = 0
    for path in sorted(files):
        findings = scan_file(path)
        if not findings:
            continue
        try:
            display = path.relative_to(repo_root)
        except ValueError:
            display = path
        lines.append("")
        lines.append(f"{display}:")
        for line_no, name, description, text in findings:
            snippet = text.strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            lines.append(f"  [{name}] line {line_no}: {description}")
            lines.append(f"    > {snippet}")
            total += 1
    return total, lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        type=Path,
        default=None,
        help="Explicit file list (e.g., from pre-commit). Filtered to code surfaces.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()

    if args.files:
        files = filter_files(list(args.files), repo_root)
    else:
        try:
            scope = _hook_scope_from_stdin(repo_root)
        except Exception:
            # A commit payload signal plus any unforeseen scoping failure must
            # never escalate to a whole-repo scan that blocks the commit.
            if os.environ.get(_PAYLOAD_ENV):
                print("hook mode: commit scope unavailable (transient); passing.")
                return 0
            raise
        if scope is _ScopeUnavailable:
            # A commit payload we could not scope (transient git failure). Pass
            # rather than gate the commit on the whole tree's pre-existing
            # violations — that is never the right hook behaviour.
            print("hook mode: commit scope unavailable (transient); passing.")
            return 0
        if scope is not None:
            repo_root, candidates = scope
            files = filter_files(candidates, repo_root)
            if not files:
                print("hook mode: no staged code files; 0 id-citation violations.")
                return 0
        else:
            files = iter_code_files(repo_root)

    total, detail_lines = format_findings(files, repo_root)

    if total == 0:
        print(f"scanned {len(files)} code file(s); 0 id-citation violations.")
        return 0

    print("\n".join(detail_lines))
    print(f"\nscanned {len(files)} code file(s); {total} violation(s).")
    print("")
    print("Rule:           rules/swe/id-citation-discipline.md")
    print("Remediation:    /decontaminate-ids  (or the id-decontamination skill)")
    print("Escape hatch:   add `id-citation-discipline:ignore` on the same line")
    print("                when the reference is truly intentional.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
