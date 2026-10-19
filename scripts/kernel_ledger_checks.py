"""The adoption ledger's invariants (I9 and I10) of the kernel manifest checker, as pure judgements.

`check_kernel_manifest` gathers the evidence and renders the findings; this module names each
finding the ledger's rules can raise: the `omitClaudeMd` flag against a `switched` record, a
switched record's evidence, an eligible list the ledger must not carry, the moves since the
parent commit, a deleted ledger, and the spawn hook reading every record as PyYAML does. No
command line; every function takes what it judges as an argument and reads nothing.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path

import kernel_ledger as kl
import kernel_model as km

# hooks/ sits beside scripts/; the spawn hook's own ledger reader is what I10 holds to PyYAML's.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import inject_kernel  # noqa: E402 (the spawn hook, after sys.path injection)

# The eval whose run a flip may rest on. The one line in `scripts/` that names it, as data: the
# paid-eval guard in the eval project's tests exempts exactly this line, so keep it alone.
ADHERENCE_ENTRY = "praxion-evals-adherence"
SWITCHED = "switched"

OMIT_KEY = "omitClaudeMd"
OMIT_SET = "true"  # the only text that sets the flag: YAML's other spellings are refused, not read

# The frontmatter block of a definition, as the model reads it.
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


def flip_findings(flags: Mapping[str, str], statuses: Mapping[str, str]) -> tuple[km.Finding, ...]:
    """I9: `omitClaudeMd` is a literal true, and it and a switched adoption record come together.

    `flags` maps each agent whose definition carries the key to the value as written.
    """
    omitting = {role for role, value in flags.items() if value == OMIT_SET}
    misspelled = tuple(
        km.Finding(
            "I9-flag-not-literal-true",
            f"role {role}",
            f"omitClaudeMd is {value!r}, not the literal {OMIT_SET}: no other spelling "
            "sets the flag, so the key is removed or written as the literal",
        )
        for role, value in sorted(flags.items())
        if value != OMIT_SET
    )
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
    return (*misspelled, *unrecorded, *unflagged)


def record_findings(ledger: kl.Ledger | km.KernelModelError | None) -> tuple[km.Finding, ...]:
    """I9: every switched record is eligible, holds all its evidence, rests on the adherence eval.

    The model refuses a record short of evidence (and says which role and piece), and a switched
    role the pin does not list; the eval a passing run came from is the commit gate's rule, not
    the model's. A ledger that lists eligible roles is refused outright: the list lives in
    `kernel_eligibility`, where a record cannot widen it.
    """
    if ledger is None:
        return ()
    if isinstance(ledger, kl.EligibleInLedger):
        return (km.Finding("I9-eligible-in-ledger", km.LEDGER_PATH, str(ledger)),)
    if isinstance(ledger, km.KernelModelError):
        return (km.Finding("I9-record-incomplete", km.LEDGER_PATH, str(ledger)),)
    return _foreign_eval_runs(ledger)


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


def omit_flags(definitions: Mapping[str, str]) -> Mapping[str, str]:
    """Each agent whose definition carries `omitClaudeMd`, to the value as written.

    As written, because YAML reads `yes`, `on` and a quoted `true` its own ways and the gate
    admits none of them: the value is the source text of the scalar, quotes included.
    """
    found = {}
    for name, text in definitions.items():
        # the model refuses frontmatter that is not YAML (and a missing PyYAML) before it is composed
        km.frontmatter(text, f"agents/{name}.md")
        if (block := _FRONTMATTER.match(text)) and (value := _written_flag(block.group(1))):
            found[name] = value[0]
    return found


def _written_flag(block: str) -> tuple[str] | None:
    """The key's value as written in the YAML `block`, in a tuple so an empty one is not absent."""
    import yaml  # present: km.frontmatter has just parsed this block with it

    root = yaml.compose(block)
    written = [
        block[value.start_mark.index : value.end_mark.index].strip()
        for key, value in getattr(root, "value", ())
        if isinstance(key, yaml.ScalarNode) and key.value == OMIT_KEY
    ]
    return (written[-1],) if written else None  # the last duplicate wins, as in YAML
