"""The adoption ledger's invariants (I9 and I10) of the kernel manifest checker, as pure judgements.

`check_kernel_manifest` gathers the evidence and renders the findings; this module names each
finding the ledger's rules can raise: the `omitClaudeMd` flag against a `switched` record, a
switched record's evidence, the eligible list, the moves since the parent commit, a deleted
ledger, and the spawn hook reading every record as PyYAML does. No command line; every
function takes what it judges as an argument and reads nothing.
"""

from __future__ import annotations

import sys
from collections.abc import Collection, Mapping
from pathlib import Path

import kernel_ledger as kl
import kernel_model as km

# hooks/ sits beside scripts/; the spawn hook's own ledger reader is what I10 holds to PyYAML's.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import inject_kernel  # noqa: E402 (the spawn hook, after sys.path injection)

# The eval whose run a flip may rest on. The one line in `scripts/` that names it, as data: the
# paid-eval guard in the eval project's tests exempts exactly this line, so keep it alone.
ADHERENCE_ENTRY = "praxion-evals-adherence"
PILOT_ROLES = (
    "researcher",
    "verifier",
    "discipline-consultant",
    "skill-genesis",
    "context-engineer",
)
SWITCHED = "switched"

OMIT_KEY = (
    "omitClaudeMd"  # any value but false or null is read as the flag: a mistyped one still gates
)


def flip_findings(omitting: Collection[str], statuses: Mapping[str, str]) -> tuple[km.Finding, ...]:
    """I9: `omitClaudeMd` and a switched adoption record come together, both ways."""
    unrecorded = tuple(
        km.Finding(
            "I9-flag-without-record",
            f"role {role}",
            f"omitClaudeMd is set but its adoption record is {statuses.get(role, 'absent')}, "
            f"not {SWITCHED}",
        )
        for role in sorted(omitting)
        if statuses.get(role) != SWITCHED
    )
    unflagged = tuple(
        km.Finding(
            "I9-switch-without-flag",
            f"role {role}",
            f"its adoption record is {SWITCHED} but the definition does not set omitClaudeMd",
        )
        for role, status in sorted(statuses.items())
        if status == SWITCHED and role not in omitting
    )
    return (*unrecorded, *unflagged)


def record_findings(ledger: kl.Ledger | km.KernelModelError | None) -> tuple[km.Finding, ...]:
    """I9: every switched record is eligible, holds all its evidence, rests on the adherence eval.

    The model refuses a record short of evidence (and says which role and piece); the eval a
    passing run came from, and the eligible roles themselves, are the commit gate's rule, not
    the model's: a ledger that could widen its own list would make the list no rule at all.
    """
    if ledger is None:
        return ()
    if isinstance(ledger, km.KernelModelError):
        return (km.Finding("I9-record-incomplete", km.LEDGER_PATH, str(ledger)),)
    return (*_eligible_changed(ledger), *_foreign_eval_runs(ledger))


def _eligible_changed(ledger: kl.Ledger) -> tuple[km.Finding, ...]:
    if sorted(ledger.eligible) == sorted(PILOT_ROLES):
        return ()
    detail = f"eligible lists {sorted(ledger.eligible)}, not the pilot's {sorted(PILOT_ROLES)}"
    return (km.Finding("I9-eligible-changed", km.LEDGER_PATH, detail),)


def _foreign_eval_runs(ledger: kl.Ledger) -> tuple[km.Finding, ...]:
    return tuple(
        km.Finding(
            "I9-record-incomplete",
            f"role {role}",
            f"rests on run {run.id!r} of eval {run.entry!r}, not {ADHERENCE_ENTRY!r}",
        )
        for role, record in sorted(ledger.records.items())
        if isinstance(record, kl.Switched)
        for run in [_passing_run(record)]
        if run.entry != ADHERENCE_ENTRY
    )


def _passing_run(record: kl.Switched) -> kl.Run:
    return next(run for run in record.runs if run.id == record.passing_run)  # the model holds it


def transition_findings(
    parent: kl.ParentLedger | None, entries: Mapping[str, kl.Entry]
) -> tuple[km.Finding, ...]:
    """I9: moves since the parent commit's ledger; none when the parent held no (readable) ledger."""
    if parent is None:
        return ()
    return tuple(
        km.Finding(f"I9-{found.kind}", found.subject, found.detail)
        for found in kl.ledger_transitions(parent, entries)
    )


def deletion_findings(
    parent: kl.ParentLedger | None, ledger: kl.Ledger | km.KernelModelError | None
) -> tuple[km.Finding, ...]:
    """I9: a ledger the parent commit holds is still there, or its first appearance could repeat."""
    if parent is None or ledger is not None:
        return ()
    detail = "the parent commit holds this ledger and this tree does not: restore it"
    return (km.Finding("I9-ledger-deleted", km.LEDGER_PATH, detail),)


def misreading_findings(
    statuses: Mapping[str, str], ledger_text: str | None
) -> tuple[km.Finding, ...]:
    """I10: the spawn hook reads each role's status from the ledger's text as PyYAML does."""
    misread = kl.hook_misreadings(statuses, ledger_text or "", inject_kernel.adoption_status)
    return tuple(km.Finding(f"I10-{found.kind}", found.subject, found.detail) for found in misread)


def omitting_roles(definitions: Mapping[str, str]) -> frozenset[str]:
    """The agents whose definition sets `omitClaudeMd` to anything but false."""
    return frozenset(name for name, text in definitions.items() if _omits_claude_md(name, text))


def _omits_claude_md(name: str, definition: str) -> bool:
    flag = km.frontmatter(definition, f"agents/{name}.md").get(OMIT_KEY)
    return flag is not None and flag is not False
