"""The readers behind the handoff composer: one question each, no rendering.

Split out of `compose_handoff.py` so the composer holds the document and this
module holds the world. Each function answers exactly one question a handoff
needs answered -- what did this pipeline fork from, what artifacts exist, is a
test log warm, which files should the readiness gate measure -- and none of
them knows what the answer will look like on the page. The dependency runs one
way: the composer imports these, never the reverse.

The clock is deliberately *not* here. `compose_handoff` reads it and passes it
down (see `recent_log`), so the whole time-dependent surface stays in one
module and one monkeypatch seam.

Stdlib-only and loadable under the ambient interpreter, because the composer
above it is invoked by a slash command with a bare `python3`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from _git_runner import git_output
from _step_verdict import HUMAN_VERDICTS


class HandoffError(Exception):
    """A refusal. The composer never writes over what it could not read."""


class HandoffBlockedError(HandoffError):
    """The readiness gate blocked the write; carries what the CLI reports."""

    def __init__(self, verdict: dict[str, Any], dirty_step_paths: Sequence[str]) -> None:
        super().__init__("not ready: " + ", ".join(verdict.get("reasons", [])))
        self.verdict = verdict
        self.dirty_step_paths = tuple(dirty_step_paths)


VERIFIED_COMPLETE = "verified-complete"
# The reconciler's own "unknown" verdict value -- claimed complete, no
# attributable ground truth. Named apart from a merely-unreadable world fact
# elsewhere in the handoff so "step unknown" and "field unreadable" never
# read as the same concern at a call site.
VERDICT_UNKNOWN = "unknown"
# A step that used its fresh attempts without verified completion: a person
# decides what happens next, so it is never the next step to run.
VERDICT_EXHAUSTED = "attempts-exhausted"
# Verdicts whose step is never the next to run: a person verifies or decides it.
# The reconciler's human set minus `blocked`, which names a move that comes before
# any later step (restore the sensor reading and re-run, or amend the plan), so
# the picker returns it as the next action.
HUMAN_OWED = tuple(verdict for verdict in HUMAN_VERDICTS if verdict != "blocked")

# Tried in order only when `refs/remotes/origin/HEAD` is unset (no remote, or a
# clone that never populated it) -- both conventional default-branch names,
# since guessing one and stopping is how a fixture or a `master` repo silently
# loses its diff base.
DEFAULT_BRANCH_FALLBACKS = ("main", "master")

RAW_LOG_GLOB = "step-*.log"
RECENT_LOG_WINDOW_SECONDS = 60

# Where the step-owned half of the `dirty-step-files` scope came from. Every
# uncommitted non-bookkeeping path is in scope regardless; these name what leads
# the list, and the composer surfaces the two widened cases -- a gate that
# quietly changed its own scope is a gate a reader cannot calibrate.
SCOPE_CURRENT_STEP = "current-step-files"
SCOPE_UNFINISHED_STEPS = "unfinished-steps-files"
SCOPE_DIRTY_SOURCE = "every-dirty-source-path"

# Written by the machinery itself and dirty almost always; blocking on them
# would block every handoff, so they are excluded from the widest scope rule.
BOOKKEEPING_PREFIXES = (".ai-state/", ".ai-work/")
BOOKKEEPING_PATHS = frozenset({"coverage.xml"})


def resolve_base_ref(repo_root: Path) -> str | None:
    """The pipeline's fork point: `git merge-base HEAD <default-branch>`.

    Without it the reconciler diffs the working tree alone, so every *committed*
    step reads as a disagreement -- and a resuming window would be told that
    finished work contradicts the record, which is worse than being told
    nothing. Returns None when no candidate resolves; the composer then says so
    rather than presenting the over-report as fact.
    """
    for candidate in _base_ref_candidates(repo_root):
        base_ref = git_output(repo_root, "merge-base", "HEAD", candidate)
        if base_ref:
            return base_ref
    return None


def _base_ref_candidates(repo_root: Path) -> tuple[str, ...]:
    """Default-branch refs to fork from, best first.

    `refs/remotes/origin/HEAD` is the ref a clone populates from the remote's
    own HEAD -- a local read, never a fetch -- and is what the finalize chain
    resolves the default branch from too. The remote-tracking ref is tried
    before the bare branch name because pipeline worktrees branch from
    `origin/<default>`, which is therefore the more recent common ancestor.
    """
    ref = git_output(repo_root, "symbolic-ref", "refs/remotes/origin/HEAD")
    if ref:
        return (ref, ref.rsplit("/", 1)[-1])
    return tuple(
        candidate for name in DEFAULT_BRANCH_FALLBACKS for candidate in (f"origin/{name}", name)
    )


def artifact_names(task_dir: Path) -> tuple[str, ...] | None:
    """The task directory's Markdown artifacts, or None when it cannot be read."""
    try:
        return tuple(
            sorted(p.name for p in task_dir.iterdir() if p.is_file() and p.suffix == ".md")
        )
    except OSError:
        return None


def recent_log(task_dir: Path, now: float) -> tuple[str, int] | None:
    """The first raw step log touched inside the advisory window, with its age.

    `now` is passed in rather than read here so the composer owns the single
    clock read, and so this function is replayable against a fixed instant.
    """
    try:
        logs = sorted((task_dir / "logs").glob(RAW_LOG_GLOB))
    except OSError:
        return None
    for path in logs:
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age < RECENT_LOG_WINDOW_SECONDS:
            return path.name, int(age)
    return None


def step_file_scope(
    verdicts: Sequence[dict[str, Any]], dirty: Sequence[str]
) -> tuple[list[str], str]:
    """What `dirty-step-files` is measured against, and where its step half came from.

    **Any uncommitted path outside bookkeeping; step-owned paths named first.**
    The scope is a union, not a first-non-empty chain: the gate's own
    justification is that the next window inherits uncommitted work invisibly,
    and that is true of a dirty source file whichever step owns it -- including
    one owned by a step already verified-complete, which no step-scoped rule
    reaches. Step-owned paths lead the list so the refusal names what is most
    likely the operator's own work first; the remedy either way is a pathspec
    commit or `--force` with the override stamped into the artifact.

    Pipeline bookkeeping is excluded -- `.ai-state/`, `.ai-work/` and the
    coverage artifact are rewritten by the machinery itself and are dirty almost
    always, so blocking on them would block every handoff.
    """
    step_owned, rule = _step_owned_paths(verdicts)
    leading = set(step_owned)
    trailing = [
        path for path in dirty if not _is_pipeline_bookkeeping(path) and path not in leading
    ]
    return list(step_owned) + trailing, rule


def _step_owned_paths(verdicts: Sequence[dict[str, Any]]) -> tuple[list[str], str]:
    """The step-owned half of the scope, and which rule produced it.

    The current step's declared `Files:` when it declares any; otherwise the
    union across every unfinished step; otherwise nothing, which an integration
    checkpoint with no `Files:` legitimately yields.
    """
    current = declared_files(first_unfinished(verdicts))
    if current:
        return current, SCOPE_CURRENT_STEP
    union = sorted(
        {
            path
            for verdict in verdicts
            if verdict.get("verdict") != VERIFIED_COMPLETE
            for path in declared_files(verdict)
        }
    )
    if union:
        return union, SCOPE_UNFINISHED_STEPS
    return [], SCOPE_DIRTY_SOURCE


def first_unfinished(verdicts: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The first step ground truth has not confirmed, or None."""
    return next((v for v in verdicts if v.get("verdict") != VERIFIED_COMPLETE), None)


def pick_next_step(verdicts: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The shared next-action picker for the handoff composer's §2 body and
    its mid-phase boundary default.

    The first verdict that is neither `verified-complete` nor one a person
    owes a look (`unknown`, `attempts-exhausted`). `unknown` means "claimed
    complete, no attributable ground truth" -- the claimed work is not
    actionable, only verifiable -- and `attempts-exhausted` is never resumed
    automatically, so both are skipped here and the caller surfaces them
    separately. Falls back to the first of them only when every step is
    verified-complete or owed to a person -- nothing else is actionable, so
    naming that step beats naming nothing. Both callers
    share this function so a mid-phase boundary and the composer's own next
    action can never name two different steps for the same moment.
    """
    for verdict in verdicts:
        if verdict.get("verdict") not in (VERIFIED_COMPLETE, *HUMAN_OWED):
            return verdict
    return next((v for v in verdicts if v.get("verdict") in HUMAN_OWED), None)


def render_owed_verification(unknown_verdicts: Sequence[dict[str, Any]]) -> str:
    """One line naming every `unknown` step: claimed complete, verification owed."""
    steps = ", ".join(f"`{v.get('step', '?')}`" for v in unknown_verdicts)
    return (
        f"Human verification owed: {steps} — claimed complete, no attributable ground truth. "
        "Verify by hand before treating the claim as fact."
    )


def render_owed(verdicts: Sequence[dict[str, Any]]) -> str:
    """The lines for every step a person owes a look: the `unknown` ones in one line,
    then each `attempts-exhausted` step with its evidence (which carries the replan
    request); empty when there are none."""
    unknown = [v for v in verdicts if v.get("verdict") == VERDICT_UNKNOWN]
    lines = [render_owed_verification(unknown)] if unknown else []
    lines += [
        f"Human decision owed: `{v.get('step', '?')}` — {v.get('evidence', '')}. "
        "Do not resume it automatically."
        for v in verdicts
        if v.get("verdict") == VERDICT_EXHAUSTED
    ]
    return "\n".join(lines)


def declared_files(verdict: dict[str, Any] | None) -> list[str]:
    """A step's *attributable* `Files:` -- the subset no earlier step also
    declares -- split by change state (see the reconciler's `attributable`).
    A file shared with, and absorbed by, an earlier declarer never appears
    here for a later step, even though that step's plan text still names it.
    """
    tier1 = (verdict or {}).get("tier1", {})
    return list(tier1.get("files_changed", [])) + list(tier1.get("files_unchanged", []))


def _is_pipeline_bookkeeping(path: str) -> bool:
    return path.startswith(BOOKKEEPING_PREFIXES) or path in BOOKKEEPING_PATHS


def read_existing(path: Path) -> str | None:
    """The prior handoff's text, or None when there genuinely is none.

    Absence and unreadability are different answers and only one of them is
    safe to act on. A file that exists but cannot be read -- permissions, a bad
    mount -- would classify as `Absent` and be overwritten with a fresh
    skeleton, destroying carried instructions nobody ever saw. That is the same
    destruction the unparseable path refuses, so it takes the same exit.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise HandoffError(
            f"the existing {path} exists but could not be read ({exc.strerror or exc}); "
            "refusing to overwrite it"
        ) from exc


def _render_step_action(verdict: dict[str, Any]) -> str:
    files = verdict.get("resume_scope") or verdict.get("tier1", {}).get("files_unchanged", [])
    scope = ", ".join(f"`{path}`" for path in files) or "see the plan's `Files:` field"
    return (
        f"`{verdict.get('step', '?')}` — {verdict.get('verdict', '?')}. File scope: {scope}.\n"
        f"Evidence: {verdict.get('evidence', '')}"
    )


def render_next_action(verdicts: Sequence[dict[str, Any]]) -> str:
    if not verdicts:
        return "No tracked steps yet — read `WIP.md` § Next Action and start there."
    owed = render_owed(verdicts)
    nxt = pick_next_step(verdicts)
    if nxt is None:
        return (
            "Every tracked step is verified-complete against ground truth. The next action is "
            "the phase's own next move — see the plan's remaining steps."
        )
    if nxt.get("verdict") in HUMAN_OWED:
        return f"No step is actionable beyond human verification. {owed}"
    return "\n".join(filter(None, [_render_step_action(nxt), owed]))
