"""The adoption ledger's invariants (I9 and I10) of the kernel manifest checker, as pure judgements.

`check_kernel_manifest` gathers the evidence and renders the findings; this module names each
finding the ledger's rules can raise: the `omitClaudeMd` flag against a `switched` record, a
switched record's evidence, the run index against the results files it describes, every run a
switched record cites located by that index and judged from its results files, an eligible list
the ledger must not carry, the eligible roles held to the parent commit's list, the moves since
the parent commit, a deleted ledger, and the spawn hook reading every record as PyYAML does. No
command line; every function takes what it judges as an argument and reads nothing, except
`cited_run_findings`, which reads the results files of a cited run through `kernel_run_evidence`.
"""

from __future__ import annotations

import importlib
import re
import sys
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from types import ModuleType

import kernel_ledger as kl
import kernel_ledger_history as kh
import kernel_model as km
import kernel_run_evidence as kre
import kernel_run_index as kri

# hooks/ sits beside scripts/; the spawn hook's own ledger reader is what I10 holds to PyYAML's.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))


def _spawn_hook() -> ModuleType | None:
    """The spawn hook, or None in a copy of scripts/ apart from its checkout (the mutation sensor)."""
    try:
        return importlib.import_module("inject_kernel")
    except ModuleNotFoundError as exc:
        if exc.name != "inject_kernel":
            raise  # the hook is there and one of its own imports is not
        return None


inject_kernel = _spawn_hook()

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


def run_index_findings(adherence: kri.Adherence) -> tuple[km.Finding, ...]:
    """I9: the run index still describes every results file beside it: none gone, changed or new."""
    listed = {entry.file: entry.sha256 for entry in adherence.entries.values()}
    drifted = [
        (name, "is listed but gone" if name not in adherence.files else "changed since indexed")
        for name, digest in sorted(listed.items())
        if adherence.files.get(name) != digest
    ]
    unlisted = [
        (name, "is not in the index")
        for name in sorted(adherence.files)
        if name not in listed and name not in adherence.skipped
    ]
    return tuple(
        km.Finding(
            "I9-run-index-stale",
            f"{kri.RESULTS_DIR}/{name}",
            f"{what}: rebuild {kri.INDEX_NAME} with `{ADHERENCE_ENTRY} --reindex`",
        )
        for name, what in (*drifted, *unlisted)
    )


def cited_run_findings(
    ledger: kl.Ledger | km.KernelModelError | None, adherence: kri.Adherence
) -> tuple[km.Finding, ...]:
    """I9: every run a switched record cites is judged from its results files, never the index.

    New, changed or unchanged, a switched record is judged whole: each run it cites, the passing
    run included, is resolved through the index (a locator and a digest) and then derived from
    the results files beside it: its lineage, its complete pairs, its flip standing. The record
    and the index are held to those figures, and the passing run must stand clear on at least
    `kl.REQUIRED_PAIRS` pairs the gate counted itself and must have scored the role's convention
    check (the other cited runs need not). Two parts of one lineage derive the same
    values, so they are one run; a closed lineage stands "not clear", a draw that refuses nothing
    alone.
    """
    if not isinstance(ledger, kl.Ledger):
        return ()  # no ledger, or one the model refused: `record_findings` reports that
    files = kre.read_run_files(adherence.directory)
    return tuple(
        finding
        for role, record in sorted(ledger.records.items())
        if isinstance(record, kl.Switched)
        for run in record.runs
        for finding in _citation_findings(
            role, run, run.id == record.passing_run, adherence.lineage_of(run.id), files
        )
    )


def _citation_findings(
    role: str,
    run: kl.Run,
    passing: bool,
    indexed: kri.Lineage | None,
    files: Sequence[kre.RunFile],
) -> tuple[km.Finding, ...]:
    subject = f"role {role}"
    if indexed is None:
        detail = f"cites run {run.id!r}, which has no readable results file in {kri.RESULTS_DIR}"
        return (km.Finding("I9-run-missing", subject, detail),)
    try:
        derived = kre.derive(files, run.id, role)
    except kre.RunEvidenceError as exc:
        detail = f"cites run {run.id!r}, whose results files give no one lineage: {exc}"
        return (km.Finding("I9-run-missing", subject, detail),)
    measured = sorted(_measured_roles(files, derived.parts))
    if role not in measured:
        detail = f"cites run {run.id!r}, whose results measured {', '.join(measured) or 'no role'}"
        return (km.Finding("I9-run-wrong-role", subject, f"{detail}, not {role}"),)
    named = _named(derived.parts)
    reached = indexed.roles.get(role)
    broken = (
        *_lineage_claims(run, indexed, reached, derived, named),
        *_standing_claims(run, passing, reached, derived, named, files, role),
        *_convention_claims(run, passing, files, role),
    )
    return tuple(km.Finding(kind, subject, detail) for kind, detail in broken)


def _measured_roles(files: Sequence[kre.RunFile], parts: Collection[str]) -> set[str]:
    return {s.role for file in files if file.run_id in parts for s in file.sessions}


def _lineage_claims(
    run: kl.Run,
    indexed: kri.Lineage,
    reached: kri.Standing | None,
    derived: kre.Derived,
    named: str,
) -> list[tuple[str, str]]:
    """Where the index and the record disagree with the results files on lineage and pairs."""
    pairs = derived.complete_pairs
    listed = "no standing" if reached is None else f"{reached.complete_pairs} complete pairs"
    claims = [
        (
            "I9-run-lineage-differs",
            indexed.parts != derived.parts,
            f"the index lists the lineage of run {run.id!r} as {', '.join(indexed.parts)}, "
            f"the results files chain {', '.join(derived.parts)}",
        ),
        (
            "I9-run-index-pairs-differ",
            reached is None or reached.complete_pairs != pairs,
            f"the index lists run {run.id!r} with {listed}; {named} reached {pairs} complete pairs",
        ),
        (
            "I9-run-pairs-differ",
            run.complete_pairs != pairs,
            f"cites run {run.id!r} with {run.complete_pairs} complete pairs; "
            f"{named} reached {pairs} complete pairs",
        ),
    ]
    return [(kind, detail) for kind, broken, detail in claims if broken]


def _standing_claims(
    run: kl.Run,
    passing: bool,
    reached: kri.Standing | None,
    derived: kre.Derived,
    named: str,
    files: Sequence[kre.RunFile],
    role: str,
) -> list[tuple[str, str]]:
    """Where the index and the record disagree with the standing the results files give."""
    try:
        judged = kre.judged_standing(files, run.id, role)
    except kre.RunEvidenceError as exc:
        unrecorded = f"cites run {run.id!r}, whose lineage records no standing for {role}: {exc}"
        return [("I9-run-standing-unrecorded", unrecorded)]
    clear = judged == kri.CLEAR
    pairs = derived.complete_pairs
    recorded = _recorded_pairs(files, run.id, role)
    labelled = reached.flip if reached else None
    claims = [
        (
            "I9-run-index-flip-differs",
            reached is not None and reached.flip != judged,
            f"the index labels run {run.id!r} {labelled!r}; {named} stands {judged}",
        ),
        (
            "I9-run-flag-disagrees",
            run.passes_flip_rule != clear,
            f"cites run {run.id!r} with passes_flip_rule {str(run.passes_flip_rule).lower()}; "
            f"{named} stands {judged}",
        ),
        (
            "I9-run-passing-short",
            passing and not (clear and pairs >= kl.REQUIRED_PAIRS),
            f"rests on run {run.id!r}, which needs {kl.REQUIRED_PAIRS} complete pairs, clear; "
            f"{named} reached {pairs} complete pairs, {judged}",
        ),
        (
            "I9-run-recorded-pairs-differ",
            recorded not in (None, pairs),
            f"the results file records {recorded} complete pairs "
            f"for run {run.id!r}'s lineage; {named} reached {pairs} complete pairs",
        ),
    ]
    return [(kind, detail) for kind, broken, detail in claims if broken]


def _convention_claims(
    run: kl.Run, passing: bool, files: Sequence[kre.RunFile], role: str
) -> list[tuple[str, str]]:
    """Where the passing run's verdict did not score the role's convention check.

    Only the passing run is judged: the record's other cited runs need not have scored it. A run
    that records no standing is reported by `_standing_claims`, not here.
    """
    recorded = _recorded(files, run.id, role)
    check = kre.convention_check_name(role)
    if not passing or recorded is None or check in recorded.scored_checks:
        return []
    scored = ", ".join(recorded.scored_checks) or "no check"
    detail = f"rests on run {run.id!r}, whose verdict did not score {check!r}: it scored {scored}"
    return [("I9-run-convention-unscored", detail)]


def _recorded_pairs(files: Sequence[kre.RunFile], run_id: str, role: str) -> int | None:
    """The complete pairs the lineage's last results file records; None when it records none."""
    recorded = _recorded(files, run_id, role)
    return None if recorded is None else recorded.complete_pairs


def _recorded(files: Sequence[kre.RunFile], run_id: str, role: str) -> kre.Standing | None:
    """What the lineage's last results file records for the role; None when it records none."""
    try:
        return kre.recorded_standing(files, run_id, role)
    except kre.RunEvidenceError:
        return None


def _named(parts: Sequence[str]) -> str:
    """The run as one: its own id, or its lineage's root and every part when it was continued."""
    if len(parts) == 1:
        return f"run {parts[0]!r}"
    return f"the lineage of {parts[0]!r} (parts {', '.join(parts)})"


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


def eligibility_findings(
    pinned: Collection[str],
    parent: kh.ParentFlip | None,
    records: Mapping[str, object],
    flags: Mapping[str, str],
) -> tuple[km.Finding, ...]:
    """I9: the eligible roles are held to the parent commit's list, not to the one this commit sets.

    A role moves to switched only if the parent commit already listed it, and the commit that
    changes the list carries no adoption record and no `omitClaudeMd` flag. Nothing is judged
    without an earlier list to hold the commit to (no parent, or one that predates the pin).
    """
    if parent is None or isinstance(parent.eligible, kh.NotYetPinned):
        return ()
    then = parent.eligible
    return (
        *_eligible_only_from_here(pinned, then, parent.records, records),
        *_changed_beside_the_list(pinned, then, parent, records, flags),
    )


def _eligible_only_from_here(
    pinned: Collection[str],
    then: Collection[str],
    was: Mapping[str, object],
    records: Mapping[str, object],
) -> tuple[km.Finding, ...]:
    return tuple(
        km.Finding(
            "I9-eligible-not-yet",
            f"role {role}",
            f"moves to {SWITCHED} but is eligible only from this commit: the parent commit "
            f"lists {', '.join(then) or 'no roles'}",
        )
        for role in sorted(set(pinned) - set(then))
        if _status(records.get(role)) == SWITCHED and _status(was.get(role)) != SWITCHED
    )


def _changed_beside_the_list(
    pinned: Collection[str],
    then: Collection[str],
    parent: kh.ParentFlip,
    records: Mapping[str, object],
    flags: Mapping[str, str],
) -> tuple[km.Finding, ...]:
    added, dropped = sorted(set(pinned) - set(then)), sorted(set(then) - set(pinned))
    if not (added or dropped):
        return ()
    change = ", ".join([*(f"+{role}" for role in added), *(f"-{role}" for role in dropped)])
    recorded = _differing(records, parent.records)
    flagged = _differing(flags, omit_flags(parent.definitions))
    return tuple(
        km.Finding(
            "I9-eligible-with-move",
            f"role {role}",
            f"the eligible roles change in this commit ({change}) and so does its "
            + " and ".join(
                what
                for what, roles in (("adoption record", recorded), (f"{OMIT_KEY} flag", flagged))
                if role in roles
            ),
        )
        for role in sorted(recorded | flagged)
    )


def _differing(now: Mapping[str, object], was: Mapping[str, object]) -> set[str]:
    """The roles `now` and `was` do not hold alike, absence counting as a difference."""
    return {role for role in {*now, *was} if now.get(role) != was.get(role)}


def _status(record: object) -> object:
    return record.get("status") if isinstance(record, Mapping) else None


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
    if inject_kernel is None:
        raise km.KernelModelError(
            "hooks/inject_kernel.py is not beside scripts/: I10 cannot be judged"
        )
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
