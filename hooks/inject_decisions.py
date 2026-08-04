"""SessionStart hook: inject Architecture Decision Record (ADR) context.

Reads ``.ai-state/decisions/DECISIONS_INDEX.md``, parses the markdown table,
filters to accepted/proposed ADRs, and injects the decisions most relevant to
this session as ``additionalContext`` at SessionStart. Architectural decisions
are hard constraints that should surface to every agent at the start of work.

Relevance is derived from the session's own git context (branch name, working
tree, recent commits) scored against each row's tags and title, with recency as
the tiebreak. Ranking by recency alone answers "what was decided last" when the
agent needs "what constrains this work" -- and on a corpus far larger than the
character cap it makes mid-life decisions permanently invisible. Every git
signal is advisory: when none is available the ordering collapses to pure
recency.

This logic previously lived inside ``inject_memory.py``, where it shared a
character budget with memory injection and was gated behind the memory
kill-switch. It now stands alone so decision context survives independently
of any memory backend.

Behavior contract:
- Fail-open: any error exits 0 with no output; never blocks SessionStart.
- Kill-switch: ``PRAXION_DISABLE_DECISION_INJECTION=1`` disables injection.
- Degrades silently when the index is missing or holds no injectable rows.

Synchronous hook (async: false). Exit 0 unconditionally -- must never
block session creation.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from _hook_utils import is_disabled

# -- Constants ----------------------------------------------------------------

DISABLE_FLAG = "PRAXION_DISABLE_DECISION_INJECTION"

ADR_SOFT_CAP = 4000  # char budget for injected decision context
_ADR_HEADER = "## Decision Context (auto-injected)\n\n"

# DECISIONS_INDEX.md table column positions (0-based, after splitting on "|")
_ADR_COL_ID = 0
_ADR_COL_TITLE = 1
_ADR_COL_STATUS = 2
_ADR_COL_CATEGORY = 3
_ADR_COL_DATE = 4
_ADR_COL_TAGS = 5
_ADR_COL_SUMMARY = 6
_ADR_EXPECTED_COLS = 7

_ADR_INJECTABLE_STATUSES = frozenset({"accepted", "proposed"})


def _read_decisions_index(index_path: Path) -> str | None:
    """Read DECISIONS_INDEX.md. Returns raw text or None on any error."""
    try:
        if not index_path.exists():
            return None
        text = index_path.read_text(encoding="utf-8")
        return text if text.strip() else None
    except OSError:
        return None


def _parse_index_rows(content: str) -> list[dict]:
    """Parse the markdown table in DECISIONS_INDEX.md into a list of ADR dicts.

    Skips header, separator, metadata, and malformed rows. Filters to
    accepted/proposed status only.
    """
    rows: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        # Skip header row and separator row
        if line.startswith("| ID") or line.startswith("|-"):
            continue

        # Split on "|", strip the empty first/last elements from leading/trailing "|"
        cols = [c.strip() for c in line.split("|")]
        # Remove empty strings from leading/trailing "|"
        if cols and cols[0] == "":
            cols = cols[1:]
        if cols and cols[-1] == "":
            cols = cols[:-1]

        if len(cols) < _ADR_EXPECTED_COLS:
            continue

        status = cols[_ADR_COL_STATUS].lower()
        if status not in _ADR_INJECTABLE_STATUSES:
            continue

        rows.append(
            {
                "id": cols[_ADR_COL_ID],
                "title": cols[_ADR_COL_TITLE],
                "status": status,
                "category": cols[_ADR_COL_CATEGORY],
                "date": cols[_ADR_COL_DATE],
                "tags": cols[_ADR_COL_TAGS],
                "summary": cols[_ADR_COL_SUMMARY],
            }
        )
    return rows


# -- Session-context relevance -------------------------------------------------

_GIT_TIMEOUT_SECONDS = 1  # per call; a timeout degrades to fewer tokens, never an error
_RECENT_COMMITS = 5
_MAX_QUERY_TOKENS = 60
_MIN_SUBSTRING_MATCH = 4  # below this, substring matching is noise ("ci" matches everything)

# Signal weights, by proximity to the work at hand. The working tree is what is
# being edited *now*; history is what the session may merely be adjacent to.
_WEIGHT_WORKTREE = 3
_WEIGHT_BRANCH = 2
_WEIGHT_HISTORY = 1

# A commit touching more files than this is mechanical -- a release bump, a
# bulk rename, a formatting sweep. It carries no topical signal and would
# otherwise flood the token set, drowning the few tokens describing the task.
_MAX_COMMIT_FILES = 25

_COMMIT_HASH = re.compile(r"[0-9a-f]{40}")

# Structural path noise with no topical meaning. Domain directories
# (`skills`, `hooks`, `agents`, ...) are deliberately NOT excluded: they double
# as real ADR tags, so editing under one is genuine evidence of topic.
_STOPWORDS = frozenset(
    {
        "src",
        "lib",
        "test",
        "tests",
        "main",
        "index",
        "init",
        "tmp",
        "new",
        "old",
        "py",
        "md",
        "ts",
        "tsx",
        "js",
        "jsx",
        "json",
        "yml",
        "yaml",
        "sh",
        "toml",
        "cfg",
        "txt",
        "lock",
        "svg",
        "png",
        "css",
        "html",
        "ini",
        "env",
    }
)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Split a path, branch name, tag list, or title into topical tokens."""
    return {
        part
        for part in _TOKEN_SPLIT.split(text.lower())
        if len(part) >= 3 and not part.isdigit() and part not in _STOPWORDS
    }


def _git_lines(cwd: Path, *args: str) -> list[str]:
    """Run a git command and return its non-empty stdout lines.

    Returns [] on any failure -- missing git, not a repo, timeout, non-zero
    exit. Every caller treats an empty result as "no signal", so failure
    degrades the ranking to recency rather than breaking the hook.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _recent_commit_paths(cwd: Path) -> list[list[str]]:
    """Return per-commit file lists for recent commits, dropping mechanical ones.

    Grouping per commit (rather than flattening) is what makes the
    `_MAX_COMMIT_FILES` filter possible: a single release bump in the window
    would otherwise contribute more tokens than every real commit combined.
    """
    lines = _git_lines(cwd, "log", f"-n{_RECENT_COMMITS}", "--name-only", "--format=%H")
    commits: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _COMMIT_HASH.fullmatch(line.strip()):
            commits.append(current)
            current = []
        else:
            current.append(line)
    commits.append(current)
    return [paths for paths in commits if paths and len(paths) <= _MAX_COMMIT_FILES]


def _session_tokens(cwd: Path) -> dict[str, int]:
    """Map topical token -> weight, describing what this session is about.

    Three signals: the working tree (what is being edited right now), the
    branch name (strong on a feature branch, absent on the default branch), and
    recent commits (what the session is continuing -- the only signal available
    on a clean checkout, which is the common case at session start).

    Weighting matters as much as the tokens. Flat-weighted, a wide mechanical
    commit in the history window contributes dozens of tokens and outvotes the
    handful that describe the actual task; the observed failure was a version
    bump surfacing onboarding decisions during ADR-finalize work.

    Deterministically truncated (highest weight first) so a huge working tree
    cannot blow up scoring.
    """
    weighted: dict[str, int] = {}

    def add(tokens: set[str], weight: int) -> None:
        for token in tokens:
            weighted[token] = max(weighted.get(token, 0), weight)

    for line in _git_lines(cwd, "status", "--porcelain"):
        add(_tokenize(line[3:]), _WEIGHT_WORKTREE)  # strip the two-char XY prefix

    branch = _git_lines(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if branch and branch[0] not in ("HEAD", "main", "master"):
        add(_tokenize(branch[0]), _WEIGHT_BRANCH)

    for paths in _recent_commit_paths(cwd):
        add({token for path in paths for token in _tokenize(path)}, _WEIGHT_HISTORY)

    ranked = sorted(weighted.items(), key=lambda item: (-item[1], item[0]))
    return dict(ranked[:_MAX_QUERY_TOKENS])


def _singular(word: str) -> str:
    """Strip one plural `s` when doing so still leaves a meaningful stem.

    Deliberately cruder than a stemmer and deliberately narrower than lowering
    the containment threshold: many real tags are three characters (`adr`,
    `api`, `mcp`, `cli`), and admitting three-char containment would let `adr`
    match `quadrant`. Depluralizing catches the actual case (`adrs` -> `adr`)
    without widening containment at all.
    """
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _terms_match(token: str, term: str) -> bool:
    """Match on equality (plural-insensitive), or on meaningful containment.

    Equality handles `adrs` against the tag `adr`; containment lets the branch
    token `finalize` match the tag `adr-finalize`, without a stemmer.
    """
    if token == term or _singular(token) == _singular(term):
        return True
    if len(token) >= _MIN_SUBSTRING_MATCH and token in term:
        return True
    return len(term) >= _MIN_SUBSTRING_MATCH and term in token


def _relevance(row: dict, tokens: dict[str, int]) -> int:
    """Sum the weights of distinct session tokens matching this row.

    Scoring per *distinct token matched* rather than per match keeps one
    repeated term from dominating: breadth of topical overlap, weighted by how
    close each signal sits to the work at hand.
    """
    if not tokens:
        return 0
    terms = _tokenize(row["tags"]) | _tokenize(row["title"])
    return sum(
        weight
        for token, weight in tokens.items()
        if any(_terms_match(token, term) for term in terms)
    )


def _format_adr_line(row: dict) -> str:
    """Format a single ADR row in rich semantic format."""
    return f"- **{row['id']}** {row['title']} ({row['status']}): {row['summary']} [{row['tags']}]"


def _build_adr_output(rows: list[dict], budget: int, tokens: dict[str, int] | None = None) -> str:
    """Format ADR rows into injectable Markdown, respecting the character budget.

    Adds entries one by one until min(budget, ADR_SOFT_CAP) is reached.
    When budget is ample and total content fits under the soft cap, all entries
    are included without truncation.
    """
    if not rows:
        return ""

    # Rank by relevance to this session first, recency second. Recency alone
    # surfaces whatever was decided last, which is not the same as whatever
    # constrains the work at hand: architectural constraints decay by
    # supersession, not by age. With a corpus far larger than the cap, a
    # pure-recency order also makes mid-life decisions permanently invisible --
    # too old to inject, not yet consolidated into rules.
    #
    # With no session signal (clean tree on the default branch, git absent,
    # every call timed out) every score is 0 and the ordering collapses exactly
    # to the previous pure-recency behavior.
    rows = sorted(
        rows,
        key=lambda row: (_relevance(row, tokens or {}), row["date"], row["id"]),
        reverse=True,
    )

    effective_cap = min(budget, ADR_SOFT_CAP)
    footer_reserve = 60  # reserve for truncation footer if needed
    lines: list[str] = []
    char_count = 0
    included = 0

    for row in rows:
        line = _format_adr_line(row)
        line_cost = len(line) + 1  # +1 for newline
        if char_count + line_cost > effective_cap - footer_reserve:
            break
        lines.append(line)
        char_count += line_cost
        included += 1

    if not lines:
        return ""

    result = "\n".join(lines)

    omitted = len(rows) - included
    if omitted > 0:
        result += f"\n\n... and {omitted} more decisions (see .ai-state/decisions/)"

    return result


def _emit_additional_context(context: str) -> None:
    """Emit additionalContext for SessionStart.

    SubagentStart additionalContext is silently ignored by Claude Code --
    use PreToolUse(Agent) with updatedInput for subagent context injection.
    """
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


def main() -> None:
    # Drain stdin even when disabled -- stdin must be consumed or the hook
    # framework may SIGPIPE on its write end.
    try:
        raw = sys.stdin.read()
    except OSError:
        raw = ""

    if is_disabled(DISABLE_FLAG):
        return

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()

    index_path = Path(cwd) / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"
    index_content = _read_decisions_index(index_path)
    if index_content is None:
        return

    rows = _parse_index_rows(index_content)
    if not rows:
        return

    body = _build_adr_output(rows, budget=ADR_SOFT_CAP, tokens=_session_tokens(Path(cwd)))
    if not body:
        return

    _emit_additional_context(f"{_ADR_HEADER}{body}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
