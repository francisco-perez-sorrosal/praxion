"""Session handoffs: the cross-window handoff for work that ran outside a pipeline.

Direct, Lightweight and Spike work leaves no ``.ai-work/<slug>/WIP.md``, so the
reconciler has no step position to report -- yet the window still holds the
same things a pipeline handoff exists to save: the user's standing
instructions, the corrections in force, what was just decided. A session
handoff writes them to the same ``HANDOFF.md`` in the same eight-section wire
format, so parsing, byte-for-byte carry-forward and the refusal to overwrite an
unparseable file are the composer's own, imported rather than re-implemented.

What differs is the mechanical half. §0 and §1 state the repository's position
(branch, HEAD, upstream distance, dirty paths, worktrees, commits since the
prior handoff) instead of a step position, and §2 is judgement -- nothing
mechanical can name a session's next move. The boundary is ``session:<label>``:
a new label resets the per-window sections (§2, §3); recomposing under the same
label keeps them. Dirty paths are reported, never refused -- a session has no
step files to protect -- while a spawn still in flight refuses exactly as it
does for a pipeline.

The import runs one way: this module reads the composer's wire format, and the
composer reaches this module only through a deferred import on its
``--session`` path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _git_runner import git_output
from _handoff_prompt import continuation_prompt
from _handoff_readiness import BLOCKED, READY, dirty_paths, readiness, session_wal_rows
from compose_handoff import (
    BYTE_WARNING_THRESHOLD,
    COMPOSER_VERSION,
    HEADER_READINESS,
    ISO_SECONDS,
    JUDGEMENT_HEADINGS,
    PLACEHOLDER,
    SECTION_HEADINGS,
    SESSION_PREFIX,
    UNKNOWN,
    HandoffError,
    InputState,
    PriorHandoff,
    _boundary_history,
    _classify_input,
    _fail,
    _header_field,
    _judgement_bodies,
    _read_existing,
    _report,
    _report_refusal,
)

# With no prior handoff to measure from, §1 shows this many recent commits.
RECENT_COMMITS = 10
LOG_FORMAT = "--format=%h %s"
_NEXT_HEADING = SECTION_HEADINGS[2]


@dataclass(frozen=True)
class SessionContext:
    """Every repository fact a session handoff states, read once by `gather_session()`.

    ``commits`` is ``None`` when the range could not be read (a prior head this
    clone no longer has), distinct from ``()`` -- no commits since.
    """

    repo_root: str = UNKNOWN
    branch: str = UNKNOWN
    head_sha: str = UNKNOWN
    head_line: str = UNKNOWN
    upstream: str | None = None
    dirty: tuple[str, ...] = ()
    worktrees: tuple[str, ...] = ()
    since_sha: str | None = None
    commits: tuple[str, ...] | None = ()
    composed_at: str = UNKNOWN
    readiness_verdict: dict[str, Any] | None = None


def require_session_boundary(boundary: str) -> None:
    if not (boundary.startswith(SESSION_PREFIX) and len(boundary) > len(SESSION_PREFIX)):
        raise HandoffError(
            f"a session handoff's boundary must be {SESSION_PREFIX}<label>, got {boundary!r}"
        )


# ---------------------------------------------------------------------------
# Composing -- pure
# ---------------------------------------------------------------------------


def compose_session(
    slug: str, boundary: str, existing: str | None, context: SessionContext
) -> dict[str, Any]:
    """Render the session handoff; a function of its arguments alone."""
    require_session_boundary(boundary)
    state, prior = _classify_input(existing, boundary)
    if state is InputState.PRESENT_UNPARSEABLE:
        raise HandoffError(
            f"the existing .ai-work/{slug}/HANDOFF.md is missing required sections or a "
            "recognized boundary header; refusing to overwrite it"
        )
    bodies = {
        SECTION_HEADINGS[0]: _render_preflight(context),
        SECTION_HEADINGS[1]: _render_state(context),
        SECTION_HEADINGS[7]: _render_start_here(),
        _NEXT_HEADING: _carried_next(state, prior),
    }
    bodies.update(_judgement_bodies(state, prior))
    byte_count = sum(len(bodies[h].encode("utf-8")) for h in (_NEXT_HEADING, *JUDGEMENT_HEADINGS))
    return {
        "text": _render(slug, boundary, prior, context, bodies),
        "byte_count": byte_count,
        "over_8kib": byte_count > BYTE_WARNING_THRESHOLD,
        "conflicts": [],
        "input_state": state.value,
        "boundary": boundary,
        "continuation_prompt": continuation_prompt(slug, context.repo_root, session=True),
    }


def _carried_next(state: InputState, prior: PriorHandoff | None) -> str:
    """§2 is judgement here and per-window: kept on the same label, reset on a new one."""
    if prior is not None and state is InputState.PRESENT_SAME_BOUNDARY:
        return prior.sections[_NEXT_HEADING]
    return PLACEHOLDER


def _render_preflight(context: SessionContext) -> str:
    upstream = (
        f"read `{context.upstream}` (behind ahead) at composition"
        if context.upstream is not None
        else "no upstream was configured at composition"
    )
    if context.dirty:
        dirty = f"{len(context.dirty)} path(s) were dirty at composition (advisory): " + ", ".join(
            f"`{path}`" for path in context.dirty
        )
    else:
        dirty = "expect empty"
    lines = [
        "Run these first. Each line names the command and the value read at composition; "
        "report any line that differs before acting.",
        "",
        f"- `git rev-parse --abbrev-ref HEAD` — expect `{context.branch}`.",
        f"- `git log -1 --format='%h %s'` — expect `{context.head_line}` or a later commit.",
        f"- `git rev-list --left-right --count @{{u}}...HEAD` — {upstream}.",
        f"- `git status --porcelain` — {dirty}.",
        "- `git worktree list` — read at composition:",
    ]
    lines += [f"  - `{entry}`" for entry in context.worktrees] or ["  - unreadable"]
    return "\n".join(lines)


def _render_state(context: SessionContext) -> str:
    if context.since_sha is None:
        heading = f"The {RECENT_COMMITS} most recent commits (no prior handoff to measure from):"
    else:
        heading = f"Commits since the prior handoff (`{context.since_sha[:8]}..HEAD`):"
    if context.commits is None:
        lines = [heading, "", "- unreadable — the prior handoff's head is not in this clone."]
    else:
        lines = [heading, ""] + ([f"- {c}" for c in context.commits] or ["- none"])
    verdict = context.readiness_verdict or {}
    if verdict.get("reasons"):
        lines += ["", f"Readiness overridden with --force: {', '.join(verdict['reasons'])}."]
    return "\n".join(lines)


def _render_start_here() -> str:
    return "\n".join(
        [
            "1. Run §0 Preflight and report every line against the value it names.",
            "2. Read §4–§6 before acting — the user's standing instructions, carried unchanged.",
            "3. Continue with §2 Next action.",
        ]
    )


def _render(
    slug: str,
    boundary: str,
    prior: PriorHandoff | None,
    context: SessionContext,
    bodies: dict[str, str],
) -> str:
    verdict = context.readiness_verdict or {"state": READY}
    header = [f"# HANDOFF: {slug}", "", f"slug: {slug}", "mode: session", f"boundary: {boundary}"]
    history = _boundary_history(prior, boundary)
    if history:
        header.append(f"boundary_history: {history}")
    header += [
        f"branch: {context.branch}",
        f"head_sha: {context.head_sha}",
        f"worktree_path: {context.repo_root}",
        f"composed_at: {context.composed_at}",
        f"composer_version: {COMPOSER_VERSION}",
        f"readiness: {HEADER_READINESS.get(verdict.get('state', READY), READY)}",
        "",
    ]
    out = list(header)
    for heading in SECTION_HEADINGS:
        out += [f"## {heading}", "", bodies[heading], ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Reading the world, and the CLI path
# ---------------------------------------------------------------------------


def gather_session(repo_root: Path, existing: str | None, *, force: bool) -> SessionContext:
    """The one read pass: the repository position, the prior head, the gate."""
    dirty = tuple(dirty_paths(repo_root))
    since = _header_field(existing, "head_sha") if existing else None
    if since == UNKNOWN:
        since = None
    return SessionContext(
        repo_root=str(repo_root),
        branch=git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD") or UNKNOWN,
        head_sha=git_output(repo_root, "rev-parse", "HEAD") or UNKNOWN,
        head_line=git_output(repo_root, "log", "-1", LOG_FORMAT) or UNKNOWN,
        upstream=_upstream(repo_root),
        dirty=dirty,
        worktrees=tuple(_lines(git_output(repo_root, "worktree", "list"))),
        since_sha=since,
        commits=_commits(repo_root, since),
        composed_at=datetime.now(timezone.utc).strftime(ISO_SECONDS),
        readiness_verdict=readiness(session_wal_rows(repo_root), dirty, (), force),
    )


def _upstream(repo_root: Path) -> str | None:
    counts = git_output(repo_root, "rev-list", "--left-right", "--count", "@{u}...HEAD")
    return " ".join(counts.split()) if counts else None


def _commits(repo_root: Path, since: str | None) -> tuple[str, ...] | None:
    if since is None:
        return tuple(_lines(git_output(repo_root, "log", f"-{RECENT_COMMITS}", LOG_FORMAT)))
    # `git_output` reads empty stdout as no answer, so probe with a command that prints.
    if git_output(repo_root, "rev-parse", "--verify", "--quiet", f"{since}^{{commit}}") is None:
        return None
    return tuple(_lines(git_output(repo_root, "log", LOG_FORMAT, f"{since}..HEAD")))


def _lines(output: str | None) -> list[str]:
    return [line for line in (output or "").splitlines() if line.strip()]


def main_session(args: argparse.Namespace, repo_root: Path) -> int:
    """`compose_handoff.py <slug> --session`: compose, gate, write, report."""
    boundary = args.boundary or f"{SESSION_PREFIX}{datetime.now(timezone.utc):%Y-%m-%d}"
    handoff_path = repo_root / ".ai-work" / args.slug / "HANDOFF.md"
    try:
        require_session_boundary(boundary)
        existing = _read_existing(handoff_path)
    except HandoffError as exc:
        return _fail(str(exc))

    context = gather_session(repo_root, existing, force=args.force)
    verdict = context.readiness_verdict or {"state": READY, "reasons": []}
    if verdict["state"] == BLOCKED:
        _report_refusal(verdict, ())
        return 1

    try:
        result = compose_session(args.slug, boundary, existing, context)
    except HandoffError as exc:
        return _fail(str(exc))
    if not args.dry_run:
        handoff_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_path.write_text(result["text"], encoding="utf-8")
    _report(args, handoff_path, result)
    return 0
