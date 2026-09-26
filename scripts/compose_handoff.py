#!/usr/bin/env python3
"""Compose `.ai-work/<slug>/HANDOFF.md` -- the cross-window pipeline handoff.

A pipeline that outlives one context window loses everything the orchestrator
held but never wrote down: the position it believed, the constraints the user
stated in conversation, the corrections already in force. The plan on disk
survives a lost orchestrator; those stitches do not. This composer writes them
into one artifact with a fixed eight-section wire format, so the next window
reads a document instead of reconstructing a guess.

Three functions, and the split between them is the design:

  ``gather(slug, repo_root, force=...)`` -- `main()`'s single read pass.
      Every fact about the world that a run needs is read here, once: the
      reconciler's verdicts, the task directory's contents, the raw-log mtimes,
      the branch and fork point, the WAL, the dirty paths, the clock. It
      returns a `ComposeContext` carrying the readiness verdict alongside the
      facts. The individual readers live in the sibling `_handoff_inputs.py`
      (one question each, no rendering); the clock stays here so the whole
      time-dependent surface is one module and one monkeypatch seam.

  ``readiness(wal_rows, git_status, step_files, force)`` -- pure, and defined
      in the sibling `_handoff_readiness.py`, re-exported here so this module
      stays the one entry point callers reach for. It decides whether this
      moment is a boundary at all, on three mechanically decidable reasons
      (``spawn-in-flight``, ``wal-unreadable``, ``dirty-step-files``); that
      module's docstring is the contract. What belongs here is the one thing
      the gate deliberately does *not* do: a recently-touched raw step log is
      rendered as an *advisory* in §1, never a reason, because a fresh mtime is
      evidence of activity rather than proof of it, and a block built on a
      heuristic teaches operators to reach for ``--force`` by reflex.

  ``compose(slug, repo_root, boundary, existing, context=...)`` -- a function
      of its arguments. Renders the eight sections. Given a `ComposeContext` it
      opens no file, runs no subprocess, asks no clock and calls no reconciler;
      without one it reads exactly the facts it renders, through the same
      `_read_render_context()` that `gather()` uses -- so those facts have one
      reader whichever entry point asked, and never the readiness gate's inputs.
      Either way two calls with equal arguments over an unchanged tree render
      byte-identical text. The mechanical half (0-2 and 7) is computed from
      verdicts the *reconciler* produced -- imported, never reimplemented, so
      the position in the handoff cannot drift from the reconciler's own. The
      judgement half (3-6) is the orchestrator's to fill; sections 4-6 carry
      forward byte-for-byte from a prior handoff, because a carried-forward
      instruction that was reflowed is a changed instruction.

`main()` is the only writer.

Exit codes: 0 written, 1 refused (not ready), 2 nothing to compose, 3 error.

Usage:
    python3 scripts/compose_handoff.py <slug> [--boundary <enum>]
                                       [--dry-run] [--force] [--json]
"""

from __future__ import annotations

import argparse
import json
import os.path
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from _git_runner import git_output

# The world-reading layer; the composer renders what these return and never
# reaches past them. One-way: nothing there imports from here.
from _handoff_inputs import (
    SCOPE_CURRENT_STEP,
    SCOPE_DIRTY_SOURCE,
    SCOPE_UNFINISHED_STEPS,
    VERDICT_UNKNOWN,
    artifact_names,
    pick_next_step,
    recent_log,
    render_owed_verification,
    resolve_base_ref,
    step_file_scope,
)
from _handoff_prompt import continuation_prompt

# The readiness gate lives in its own module; these names are re-exported here
# so `compose_handoff.readiness` stays the one public entry point callers and
# tests reach for, whichever file the decision itself is written in.
from _handoff_readiness import (
    BLOCKED,
    DIRTY_STEP_FILES,
    OVERRIDDEN,
    READY,
    REMEDIES,
    dirty_paths,
    readiness,
    session_wal_rows,
)
from _repo_root import is_plugin_cache_path, resolve_repo_root
from reconcile_pipeline_state import reconcile

SCRIPT_DIR = Path(__file__).resolve().parent

COMPOSER_VERSION = "1"
UNKNOWN = "unknown"
ISO_SECONDS = "%Y-%m-%dT%H:%M:%SZ"

# The wire format between two windows: fixed set, fixed order, fixed headings.
# Renaming or reordering any of these is a contract change that must move the
# composer, its tests, and the `/resume-pipeline` consumption step together.
SECTION_HEADINGS: tuple[str, ...] = (
    "§0 Preflight",
    "§1 State",
    "§2 Next action",
    "§3 Decisions & assumptions in force",
    "§4 Operating constraints from the user",
    "§5 Corrections in force",
    "§6 Do not re-inherit",
    "§7 Start here",
)
# The judgement range is contiguous on purpose: the carry-forward rule is then
# one slice rather than a list of exceptions. The digest heads it and is the
# one judgement section that resets, because it is a per-boundary delta.
_DIGEST_INDEX = 3
_CARRY_START, _CARRY_END = 4, 7
DIGEST_HEADING = SECTION_HEADINGS[_DIGEST_INDEX]
JUDGEMENT_HEADINGS = SECTION_HEADINGS[_DIGEST_INDEX:_CARRY_END]
CARRIED_HEADINGS = SECTION_HEADINGS[_CARRY_START:_CARRY_END]

PLACEHOLDER = "_[to fill at the checkpoint]_"

# A closed enum, not free text. The open-ended member carries its step id so a
# mid-phase position is self-describing rather than a bare "somewhere".
FIXED_BOUNDARIES: tuple[str, ...] = (
    "research-to-architecture",
    "architecture-to-planning",
    "planning-to-implementation",
    "implementation-to-verification",
)
MID_PHASE_PREFIX = "mid-phase:"
# Session handoffs (`--session`, `_handoff_session.py`) name their window with this prefix.
SESSION_PREFIX = "session:"

# `Ready` and `Overridden` are distinct states rather than a boolean plus a
# note, because the next window's correct behaviour differs between them.
HEADER_READINESS = {READY: "clean", OVERRIDDEN: "overridden"}

UNRESOLVED_BASE_ADVISORY = (
    "- Advisory: the pipeline's base ref could not be resolved, so the position above is diffed "
    "against the working tree alone — committed steps may over-report as disagreements."
)

# Keyed by the scope rule the input layer reports. Only the widened two appear:
# a gate that quietly changed its own scope is a gate a reader cannot calibrate.
WIDENED_SCOPE_ADVISORY = {
    SCOPE_UNFINISHED_STEPS: (
        "- Advisory: the current step declares no `Files:`, so the readiness gate's step-owned "
        "paths came from the union of every unfinished step's files. Every uncommitted path "
        "outside `.ai-state/`, `.ai-work/` and coverage output was in scope regardless."
    ),
    SCOPE_DIRTY_SOURCE: (
        "- Advisory: no unfinished step declares `Files:`, so the readiness gate had no "
        "step-owned paths to lead with. Every uncommitted path outside `.ai-state/`, "
        "`.ai-work/` and coverage output was in scope."
    ),
}

BYTE_WARNING_THRESHOLD = 8192
RECENT_LOG_ADVISORY = "a test run may still be in progress"

MISMATCH = "mismatch"


class HandoffError(Exception):
    """A refusal. The composer never writes over what it could not read."""


class InputState(Enum):
    """The four legal states of the composer's input, as a sum type.

    They are not a flag soup because each one has a different write rule, and
    the last one has no write rule at all -- an existing handoff that cannot be
    parsed is preserved, never rewritten from a partial read.
    """

    ABSENT = "absent"
    PRESENT_SAME_BOUNDARY = "present-same-boundary"
    PRESENT_EARLIER_BOUNDARY = "present-earlier-boundary"
    PRESENT_UNPARSEABLE = "present-unparseable"


@dataclass(frozen=True)
class PriorHandoff:
    """A parsed prior handoff: its boundary, its history chain, its sections."""

    boundary: str
    sections: dict[str, str]
    history: str | None = None


@dataclass(frozen=True)
class ComposeContext:
    """Every world fact the handoff states, read once by `gather()`.

    This type is what makes `compose()` pure and therefore replayable: the same
    context renders the same bytes, today and tomorrow. Each field defaults to
    a world-free value, so `compose()` stays callable with nothing but its four
    arguments -- a default is never a reading of the world, only the absence of
    one. `artifact_names` distinguishes "listed, and empty" (``()``) from
    "could not be listed" (``None``).
    """

    readiness_verdict: dict[str, Any] | None = None
    step_scope_rule: str = SCOPE_CURRENT_STEP
    dirty_step_paths: Sequence[str] = ()
    verdicts: Sequence[dict[str, Any]] = ()
    artifact_names: Sequence[str] | None = ()
    recent_log: tuple[str, int] | None = None
    branch: str = UNKNOWN
    base_sha: str = UNKNOWN
    worktree_path: str = UNKNOWN
    composed_at: str = UNKNOWN


# ---------------------------------------------------------------------------
# The composing entry point -- pure
# ---------------------------------------------------------------------------


def compose(
    slug: str,
    repo_root: Path | str,
    boundary: str,
    existing: str | None,
    *,
    context: ComposeContext | None = None,
    _changed_files_override: list[str] | None = None,
    _wal_rows_override: list[dict[str, Any]] | None = None,
    _test_status_override: str | None = None,
) -> dict[str, Any]:
    """Render the handoff for ``slug`` at ``boundary``.

    ``existing`` is the raw text of the prior ``HANDOFF.md`` or ``None``; the
    caller reads that file, so all four input states are derivable from
    ``(boundary, existing)`` alone.

    ``context`` carries every world fact the document states. Supplied, this
    function reaches for nothing else -- no file, no subprocess, no clock, no
    reconciler -- and is a function of its arguments alone. Omitted, it reads
    those same facts (and only those: never the readiness gate's inputs)
    through the one reader `gather()` also uses. The ``_*_override`` hooks pass
    through to ``reconcile()`` on that path, reusing its own hermetic-testing
    seam.

    Returns ``text``, ``byte_count`` (the judgement sections' combined size),
    ``over_8kib`` (advisory, never fatal), ``conflicts``, ``input_state`` and
    ``boundary``. Raises `HandoffError` for an unknown boundary or an existing
    handoff that cannot be parsed -- writing nothing is the refusal, since this
    function never writes at all.
    """
    _require_known_boundary(boundary)
    if context is None:
        context = _read_render_context(
            slug,
            Path(repo_root),
            _changed_files_override=_changed_files_override,
            _wal_rows_override=_wal_rows_override,
            _test_status_override=_test_status_override,
        )

    state, prior = _classify_input(existing, boundary)
    if state is InputState.PRESENT_UNPARSEABLE:
        raise HandoffError(
            f"the existing {os.path.join(str(repo_root), '.ai-work', slug, 'HANDOFF.md')} is "
            "missing one or more required sections or a recognized boundary header; "
            "refusing to overwrite it"
        )

    conflicts = _find_conflicts(context.verdicts)
    bodies = _section_bodies(slug, context, conflicts, state, prior)
    byte_count = sum(len(bodies[h].encode("utf-8")) for h in JUDGEMENT_HEADINGS)
    return {
        "text": _render(slug, boundary, prior, context, bodies),
        "byte_count": byte_count,
        "over_8kib": byte_count > BYTE_WARNING_THRESHOLD,
        "conflicts": conflicts,
        "input_state": state.value,
        "boundary": boundary,
        "continuation_prompt": continuation_prompt(slug, repo_root, session=False),
    }


# ---------------------------------------------------------------------------
# The boundary enum and the composer's input states
# ---------------------------------------------------------------------------


def _is_known_boundary(boundary: str) -> bool:
    if boundary in FIXED_BOUNDARIES:
        return True
    prefix = next((p for p in (MID_PHASE_PREFIX, SESSION_PREFIX) if boundary.startswith(p)), None)
    return prefix is not None and len(boundary) > len(prefix)


def _require_known_boundary(boundary: str) -> None:
    if not _is_known_boundary(boundary):
        raise HandoffError(
            f"unknown boundary {boundary!r}; expected one of "
            f"{', '.join(FIXED_BOUNDARIES)} or {MID_PHASE_PREFIX}<step-id>"
        )


def _classify_input(existing: str | None, boundary: str) -> tuple[InputState, PriorHandoff | None]:
    if not existing or not existing.strip():
        return InputState.ABSENT, None
    try:
        prior = _parse_prior(existing)
    except HandoffError:
        return InputState.PRESENT_UNPARSEABLE, None
    if prior.boundary == boundary:
        return InputState.PRESENT_SAME_BOUNDARY, prior
    return InputState.PRESENT_EARLIER_BOUNDARY, prior


def _parse_prior(text: str) -> PriorHandoff:
    """Parse a prior handoff, or raise. Every section must be present: a
    partial read would let a rewrite silently drop a carried instruction."""
    positions = []
    for heading in SECTION_HEADINGS:
        index = text.find(f"## {heading}")
        if index == -1:
            raise HandoffError(f"missing section heading: {heading}")
        positions.append((heading, index))
    positions.sort(key=lambda pair: pair[1])

    sections: dict[str, str] = {}
    for slot, (heading, index) in enumerate(positions):
        start = index + len(f"## {heading}")
        end = positions[slot + 1][1] if slot + 1 < len(positions) else len(text)
        sections[heading] = text[start:end].strip()

    boundary = _header_field(text, "boundary")
    if boundary is None or not _is_known_boundary(boundary):
        raise HandoffError("header carries no recognized boundary field")
    return PriorHandoff(
        boundary=boundary, sections=sections, history=_header_field(text, "boundary_history")
    )


def _header_field(text: str, name: str) -> str | None:
    """Read one `name: value` line from the header block above the first section."""
    prefix = f"{name}: "
    for line in text.splitlines():
        if line.startswith("## "):
            return None
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _judgement_bodies(state: InputState, prior: PriorHandoff | None) -> dict[str, str]:
    """Sections 3-6: placeholders when there is nothing to carry, else verbatim.

    Verbatim means verbatim -- the prior body is re-emitted unchanged, never
    reflowed, because a reflowed instruction is a changed instruction. Only the
    digest resets, and only when the boundary moved.
    """
    if prior is None:
        return dict.fromkeys(JUDGEMENT_HEADINGS, PLACEHOLDER)
    bodies = {heading: prior.sections[heading] for heading in CARRIED_HEADINGS}
    bodies[DIGEST_HEADING] = (
        prior.sections[DIGEST_HEADING] if state is InputState.PRESENT_SAME_BOUNDARY else PLACEHOLDER
    )
    return bodies


# ---------------------------------------------------------------------------
# Ground truth vs. the record
# ---------------------------------------------------------------------------


def _find_conflicts(verdicts: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Steps where the position of record disagrees with Tier-1 ground truth.

    The claim a handoff carries is the `WIP.md` checkbox -- which is also what
    any prior handoff was composed from. Two shapes contradict it: work ground
    truth proves done whose checkbox was never flipped, and a complete claim
    ground truth does not confirm. Ground truth wins in the rendered document;
    the disagreement is reported rather than silently resolved, because a
    convenience document that quietly outranks the reconciler is a correctness
    hazard.
    """
    contradicted = []
    for verdict in verdicts:
        if not (verdict.get("needs_mark") or verdict.get("verdict") == MISMATCH):
            continue
        contradicted.append(
            {
                "step": verdict.get("step", ""),
                "handoff_claim": verdict.get("wip_claim", ""),
                "reconciler_verdict": verdict.get("verdict", ""),
                "evidence": verdict.get("evidence", ""),
            }
        )
    return contradicted


# ---------------------------------------------------------------------------
# Rendering -- one function per section, then the assembler. All pure.
# ---------------------------------------------------------------------------


def _section_bodies(
    slug: str,
    context: ComposeContext,
    conflicts: Sequence[dict[str, Any]],
    state: InputState,
    prior: PriorHandoff | None,
) -> dict[str, str]:
    """The eight bodies: four computed from the world, four carried or blank."""
    bodies = {
        SECTION_HEADINGS[0]: _render_preflight(slug, context),
        SECTION_HEADINGS[1]: _render_state(context, conflicts),
        SECTION_HEADINGS[2]: _render_next_action(context.verdicts),
        SECTION_HEADINGS[7]: _render_start_here(slug),
    }
    bodies.update(_judgement_bodies(state, prior))
    return bodies


def _render_preflight(slug: str, context: ComposeContext) -> str:
    return "\n".join(
        [
            "Run these first. Each line is the command and the value to expect.",
            "",
            "- `git status --porcelain` — expect empty. A dirty tree is work no diff against "
            "the base will show you.",
            f"- `git rev-parse --abbrev-ref HEAD` — expect `{context.branch}`.",
            f"- `git merge-base HEAD <default-branch>` — expect `{context.base_sha}`. §1's "
            "position is diffed against that fork point, not against HEAD.",
            f"- `python3 scripts/reconcile_pipeline_state.py {slug} --json` — the authority on "
            "position. This document is not.",
            "- The project's own test command — expect the baseline recorded in "
            f"`.ai-work/{slug}/TEST_BASELINE.md`, when one exists.",
        ]
    )


def _render_state(context: ComposeContext, conflicts: Sequence[dict[str, Any]]) -> str:
    verdict = context.readiness_verdict or {"state": READY, "reasons": []}
    lines = [
        f"- Worktree `{context.worktree_path}`, branch `{context.branch}` at `{context.base_sha}`.",
        f"- Artifacts present: {_artifact_list(context.artifact_names)}.",
    ]
    if verdict.get("state") == OVERRIDDEN:
        lines.append(
            "- Composed with `--force` over a non-quiescent tree. Conditions still firing: "
            + ", ".join(verdict.get("reasons", []))
            + ". Re-derive this section from ground truth before trusting it."
        )
    lines.append("- Position, from the reconciler (Tier-1 ground truth, not the checkbox):")
    if context.verdicts:
        lines += [
            f"  - `{v.get('step', '?')}` — {v.get('verdict', '?')} — {v.get('evidence', '')}"
            for v in context.verdicts
        ]
    else:
        lines.append("  - no tracked steps in `WIP.md` yet.")
    if context.base_sha == UNKNOWN:
        lines.append(UNRESOLVED_BASE_ADVISORY)
    scope_advisory = WIDENED_SCOPE_ADVISORY.get(context.step_scope_rule)
    if scope_advisory:
        lines.append(scope_advisory)
    lines += [
        f"- Disagreement: `{c['step']}` is recorded as {c['handoff_claim']}, ground truth says "
        f"{c['reconciler_verdict']}. Ground truth wins; the record needs correcting."
        for c in conflicts
    ]
    advisory = _recent_log_note(context.recent_log)
    if advisory:
        lines.append(advisory)
    return "\n".join(lines)


def _render_step_action(verdict: dict[str, Any]) -> str:
    files = verdict.get("resume_scope") or verdict.get("tier1", {}).get("files_unchanged", [])
    scope = ", ".join(f"`{path}`" for path in files) or "see the plan's `Files:` field"
    return (
        f"`{verdict.get('step', '?')}` — {verdict.get('verdict', '?')}. File scope: {scope}.\n"
        f"Evidence: {verdict.get('evidence', '')}"
    )


def _render_next_action(verdicts: Sequence[dict[str, Any]]) -> str:
    if not verdicts:
        return "No tracked steps yet — read `WIP.md` § Next Action and start there."
    unknown = [v for v in verdicts if v.get("verdict") == VERDICT_UNKNOWN]
    nxt = pick_next_step(verdicts)
    if nxt is None:
        return (
            "Every tracked step is verified-complete against ground truth. The next action is "
            "the phase's own next move — see the plan's remaining steps."
        )
    if nxt.get("verdict") == VERDICT_UNKNOWN:
        return (
            f"No step is actionable beyond human verification. {render_owed_verification(unknown)}"
        )
    lines = [_render_step_action(nxt)]
    if unknown:
        lines.append(render_owed_verification(unknown))
    return "\n".join(lines)


def _render_start_here(slug: str) -> str:
    return "\n".join(
        [
            "1. Run §0 Preflight and reconcile what it reports against §1.",
            "2. Read §4–§6 before acting — the user's standing instructions, carried unchanged.",
            f"3. /resume-pipeline {slug}",
        ]
    )


def _render(
    slug: str,
    boundary: str,
    prior: PriorHandoff | None,
    context: ComposeContext,
    bodies: dict[str, str],
) -> str:
    verdict = context.readiness_verdict or {"state": READY, "reasons": []}
    header = [f"# HANDOFF: {slug}", "", f"slug: {slug}", f"boundary: {boundary}"]
    history = _boundary_history(prior, boundary)
    if history:
        header.append(f"boundary_history: {history}")
    header += [
        f"branch: {context.branch}",
        f"base_sha: {context.base_sha}",
        f"worktree_path: {context.worktree_path}",
        f"composed_at: {context.composed_at}",
        f"composer_version: {COMPOSER_VERSION}",
        f"readiness: {HEADER_READINESS.get(verdict.get('state', READY), READY)}",
        "",
    ]
    out = list(header)
    for heading in SECTION_HEADINGS:
        out += [f"## {heading}", "", bodies[heading], ""]
    return "\n".join(out) + "\n"


def _boundary_history(prior: PriorHandoff | None, boundary: str) -> str | None:
    """The chain of boundaries this artifact has passed through, oldest first."""
    if prior is None:
        return None
    if prior.boundary == boundary:
        return prior.history
    return f"{prior.history or prior.boundary} -> {boundary}"


def _artifact_list(names: Sequence[str] | None) -> str:
    if names is None:
        return "unreadable"
    return ", ".join(f"`{name}`" for name in names) or "none"


def _recent_log_note(recent_log: tuple[str, int] | None) -> str | None:
    """Advisory only -- a fresh raw-log mtime can never become a block reason."""
    if recent_log is None:
        return None
    name, age_seconds = recent_log
    return f"- Advisory: `{name}` changed {age_seconds}s ago — {RECENT_LOG_ADVISORY}."


# ---------------------------------------------------------------------------
# Reading the world -- every filesystem, subprocess and clock read lives here
# ---------------------------------------------------------------------------


def gather(
    slug: str,
    repo_root: Path,
    *,
    force: bool,
    _changed_files_override: list[str] | None = None,
    _wal_rows_override: list[dict[str, Any]] | None = None,
    _test_status_override: str | None = None,
) -> ComposeContext:
    """`main()`'s single read pass: the document's facts, plus the gate's verdict.

    The gate's own inputs -- the session WAL and the dirty paths -- are read
    only here, never on `compose()`'s path, because a rendering call has no
    business asking whether the tree is quiescent.
    """
    facts = _read_render_context(
        slug,
        repo_root,
        _changed_files_override=_changed_files_override,
        _wal_rows_override=_wal_rows_override,
        _test_status_override=_test_status_override,
    )
    dirty = dirty_paths(repo_root)
    step_files, scope_rule = step_file_scope(facts.verdicts, dirty)
    dirty_seen = set(dirty)
    return replace(
        facts,
        readiness_verdict=readiness(session_wal_rows(repo_root), dirty, step_files, force),
        step_scope_rule=scope_rule,
        # Scope order is step-owned-first, so naming the intersection in that
        # order puts the operator's own likely work at the head of the refusal.
        dirty_step_paths=tuple(path for path in step_files if path in dirty_seen),
    )


def _read_render_context(
    slug: str,
    repo_root: Path,
    *,
    _changed_files_override: list[str] | None = None,
    _wal_rows_override: list[dict[str, Any]] | None = None,
    _test_status_override: str | None = None,
) -> ComposeContext:
    """Read exactly the world facts the rendered handoff asserts, and no more.

    The base ref is resolved once and used twice -- as the reconciler's diff
    base and as the header's `base_sha` -- so the document names the very
    commit its position was computed against, rather than two different SHAs.
    """
    task_dir = repo_root / ".ai-work" / slug
    base_ref = resolve_base_ref(repo_root)
    return ComposeContext(
        verdicts=reconcile(
            slug,
            repo_root,
            base_ref,
            _changed_files_override=_changed_files_override,
            _wal_rows_override=_wal_rows_override,
            _test_status_override=_test_status_override,
        ),
        artifact_names=artifact_names(task_dir),
        recent_log=recent_log(task_dir, time.time()),
        branch=git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD") or UNKNOWN,
        base_sha=base_ref or UNKNOWN,
        worktree_path=str(repo_root),
        composed_at=datetime.now(timezone.utc).strftime(ISO_SECONDS),
    )


def _default_boundary(verdicts: Sequence[dict[str, Any]]) -> str | None:
    """A mid-phase boundary naming the current step, when none was given."""
    step = (pick_next_step(verdicts) or {}).get("step")
    return f"{MID_PHASE_PREFIX}{step}" if step else None


def _read_existing(path: Path) -> str | None:
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


# ---------------------------------------------------------------------------
# CLI -- the only writer
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR))
    if is_plugin_cache_path(repo_root):
        return _fail("refusing to run against a plugin-cache path; pass --repo-root")
    if args.session:  # deferred: the session module imports this one
        from _handoff_session import main_session

        return main_session(args, repo_root)

    task_dir = repo_root / ".ai-work" / args.slug
    if not (task_dir / "WIP.md").is_file():
        sys.stderr.write(f"compose_handoff: nothing to compose — no {task_dir / 'WIP.md'}\n")
        return 2

    context = gather(args.slug, repo_root, force=args.force)
    boundary = args.boundary or _default_boundary(context.verdicts)
    if boundary is None:
        return _fail("no tracked step to name a mid-phase boundary from; pass --boundary")

    verdict = context.readiness_verdict or {"state": READY, "reasons": []}
    if verdict["state"] == BLOCKED:
        _report_refusal(verdict, context.dirty_step_paths)
        return 1

    handoff_path = task_dir / "HANDOFF.md"
    try:
        result = compose(
            args.slug, repo_root, boundary, _read_existing(handoff_path), context=context
        )
    except Exception as exc:  # noqa: BLE001 — a composer refusal must not crash the seam
        return _fail(str(exc))

    if not args.dry_run:
        handoff_path.write_text(result["text"], encoding="utf-8")
    _report(args, handoff_path, result)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compose .ai-work/<slug>/HANDOFF.md, the cross-window pipeline handoff."
    )
    parser.add_argument("slug", help="task slug under .ai-work/<slug>/")
    parser.add_argument("--repo-root", default=None, help="git repo root (default: git rev-parse)")
    parser.add_argument(
        "--boundary",
        default=None,
        help=f"one of {', '.join(FIXED_BOUNDARIES)}, or {MID_PHASE_PREFIX}<step-id> "
        "(default: mid-phase at the current step)",
    )
    parser.add_argument("--dry-run", action="store_true", help="compose but write nothing")
    parser.add_argument(
        "--force", action="store_true", help="compose over a blocked readiness verdict"
    )
    parser.add_argument("--json", action="store_true", help="emit the composition report as JSON")
    parser.add_argument(
        "--session", action="store_true", help="hand off work that ran outside a pipeline"
    )
    return parser.parse_args(argv)


def _report_refusal(verdict: dict[str, Any], dirty_step_paths: Sequence[str]) -> None:
    for reason in verdict.get("reasons", []):
        remedy = REMEDIES.get(reason, "")
        if reason == DIRTY_STEP_FILES and dirty_step_paths:
            remedy = f"{remedy}: {', '.join(dirty_step_paths)}"
        sys.stderr.write(f"compose_handoff: refused — {reason}: {remedy}\n")
    sys.stderr.write(
        "compose_handoff: pass --force to compose anyway; the override is recorded in the "
        "artifact, not only in your memory\n"
    )


def _report(args: argparse.Namespace, handoff_path: Path, result: dict[str, Any]) -> None:
    if result["over_8kib"]:
        sys.stderr.write(
            f"compose_handoff: judgement sections are {result['byte_count']} bytes, above the "
            f"{BYTE_WARNING_THRESHOLD}-byte advisory threshold (not fatal)\n"
        )
    if args.json:
        print(
            json.dumps(
                {
                    "path": str(handoff_path),
                    "boundary": result["boundary"],
                    "input_state": result["input_state"],
                    "byte_count": result["byte_count"],
                    "over_8kib": result["over_8kib"],
                    "conflicts": result["conflicts"],
                    "dry_run": args.dry_run,
                    "continuation_prompt": result["continuation_prompt"],
                },
                indent=2,
            )
        )
        return
    verb = "would write" if args.dry_run else "wrote"
    print(
        f"compose_handoff: {verb} {handoff_path} — {result['byte_count']} judgement bytes, "
        f"{len(result['conflicts'])} disagreement(s) with ground truth"
    )
    print(f"\nContinue in the next window with:\n\n{result['continuation_prompt']}")


def _fail(message: str) -> int:
    sys.stderr.write(f"compose_handoff: {message}\n")
    return 3


if __name__ == "__main__":
    sys.exit(main())
