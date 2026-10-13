"""The kernel manifest checker: holds the always-loaded guidance, the manifest and the kernels together.

`python3 scripts/check_kernel_manifest.py [--json] [--repo-root DIR]` is the commit gate behind the
per-role kernels. It reads the repository once, then judges nine invariants; a finding's kind
names the invariant it breaks. Exit 0 clean, 1 findings, 2 input error (no manifest, no plugin
checkout, PyYAML absent, an unreadable file) -- a gate that cannot read its input never passes.

| Kind                         | Holds when                                                              |
| ---------------------------- | ----------------------------------------------------------------------- |
| `I1-unclassified`            | every section and part of every always-loaded source has an audience entry |
| `I1-orphan`                  | every entry names a section or part that exists                         |
| `I1-duplicate-heading`       | no source holds two sections of one heading (an entry could not tell apart) |
| `I2-missing-core`            | every detected agent has a kernel core: the index lists it with strings |
| `I3-contract-drift`          | the core carries the contract rule's own lines, and the preamble is current |
| `I4-over-cap`                | no committed kernel file and no injected string exceeds the harness cap |
| `I5-group-mismatch`          | the ADR-author and ledger-writer groups equal the agents that write those |
| `I6-stale-pin`               | every condensed form's pin matches the source it condenses              |
| `I7-resident-text-in-kernel` | no orchestrator-only or no-actor paragraph is in any kernel or injected string |
| `I8-stale-kernel`            | the committed kernels, index, definitions' blocks and preamble equal what the generator writes now |
| `I9-flag-without-record`     | `omitClaudeMd` is set on an agent only while its adoption record is switched |
| `I9-switch-without-flag`     | an agent whose record is switched carries `omitClaudeMd`                |
| `I9-record-incomplete`       | a switched record is eligible and holds every piece of flip evidence, the passing run from the adherence eval |
| `I9-eligible-changed`        | the ledger's `eligible` list is the pilot's five roles, no more and no fewer |
| `I9-ledger-transition`       | a role moves only absent -> trial -> switched since the parent commit's ledger |
| `I9-ledger-deleted`          | a ledger present at the parent commit is still there                    |

`--liveness [--since REV] [--plugin-root DIR]` is a second mode, over an observation log instead
of the kernels: `liveness-missing-row` names each spawn of a role at trial or switched (by the
plugin's ledger) that left no `kernel_injected` row -- the only sign that the spawn hook did not
run for it. A role's spawns count from its record's `since`; `--since` keeps spawns at or after
that revision's commit time. The log is the one under `--repo-root`, read strictly: a log it
cannot find or read whole is an input error, and every report counts the spawns it judged, so a
clean one never means that nothing was judged.

The totality, pin, transition and group judgements are `kernel_model`'s; this module gathers the
evidence, names each finding and renders it. The index is read here as plain JSON, not through
`kernel_model`, because the model refuses an over-cap string at parse time and I4 must report one,
not die on it.

Detected, never listed: the agents come from `agents/*.md`, the always-loaded sources from the
tree, so a new agent or rule is covered the day it exists. No setting or variable turns any of
this off: the gate that cannot be disabled is the point.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import zip_longest
from pathlib import Path

import generate_kernels as gk
import kernel_ledger as kl
import kernel_model as km
import kernel_sources as ks
from _git_runner import run_git
from _repo_root import is_plugin_cache_path, resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

# hooks/_observation_log is the one reader of the observation log; it sits beside scripts/.
sys.path.insert(0, str(SCRIPT_DIR.parent / "hooks"))
from _observation_log import reader  # noqa: E402 (after sys.path injection)

REPORT_SCHEMA = 1
KERNEL_FILE_GLOB = "*.md"
CORE_FILES = ("core.md", "core-1.md")  # a core above the cap is numbered parts; part one leads
PARAGRAPH_END = "\n\n"
IDENTIFYING_CHARS = 24  # a paragraph shorter than this names no source
RESIDENT_SCOPES = (km.OrchestratorOnly, km.NoActor)
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
AGENT_PREFIX = "praxion:"  # the agent type of this plugin's agents, as the log records it
SPAWN_ROW = "agent_start"
KERNEL_ROW = "kernel_injected"
STATE_DIR = ".ai-state"

OMIT_KEY = (
    "omitClaudeMd"  # any value but false or null is read as the flag: a mistyped one still gates
)


# -- Pure: the nine invariants ---------------------------------------------------------


def totality_findings(
    manifest: km.Manifest, sections: Mapping[str, Sequence[ks.Section]], required: Collection[str]
) -> tuple[km.Finding, ...]:
    """I1: every section and part classified, no entry orphaned."""
    return tuple(
        km.Finding(f"I1-{found.kind}", found.subject, found.detail)
        for found in km.check_totality(manifest, sections, required)
    )


def core_findings(
    agents: Collection[str],
    index_strings: Mapping[str, Sequence[str]] | None,
    kernel_files: Mapping[str, str],
) -> tuple[km.Finding, ...]:
    """I2: a kernel core for every agent: a core file, and the index lists the agent with text."""
    if not any(name in kernel_files for name in CORE_FILES):
        return (km.Finding("I2-missing-core", gk.KERNELS_DIR, "there is no core kernel file"),)
    if index_strings is None:
        return (km.Finding("I2-missing-core", km.INDEX_PATH, "the index does not exist"),)
    return tuple(
        km.Finding("I2-missing-core", f"agent {agent}", "the index gives it no kernel strings")
        for agent in sorted(agents)
        if not index_strings.get(agent)
    )


def contract_findings(
    manifest: km.Manifest,
    sections: Mapping[str, Sequence[ks.Section]],
    kernel_files: Mapping[str, str],
    preamble: str | None,
) -> tuple[km.Finding, ...]:
    """I3: the core's contract block is the contract rule's own lines, the preamble derived."""
    lines = _contract_lines(manifest, sections)
    where = f"{gk.CONTRACT_SOURCE} '{gk.CONTRACT_HEADING}'"
    if lines is None:
        return (km.Finding("I3-contract-drift", where, "the core carries no behavioral contract"),)
    expected = [gk.CONTRACT_LEAD_IN, *lines]
    findings = [
        finding
        for name in (gk.BLOCKS_FILE, _core_file(kernel_files))
        if (finding := _block_drift(f"{gk.KERNELS_DIR}/{name}", kernel_files.get(name), expected))
    ]
    return (*findings, *_preamble_drift(expected, preamble))


def cap_findings(
    texts: Mapping[str, str], cap: int = km.MAX_STRING_CHARS
) -> tuple[km.Finding, ...]:
    """I4: no text above `cap` characters; `texts` maps where each came from to its text."""
    return tuple(
        km.Finding("I4-over-cap", where, f"{len(text)} characters exceed the {cap} cap")
        for where, text in texts.items()
        if len(text) > cap
    )


def group_findings(manifest: km.Manifest, definitions: Mapping[str, str]) -> tuple[km.Finding, ...]:
    """I5: the writer groups against what the definitions say, both ways."""
    return tuple(
        km.Finding("I5-group-mismatch", found.subject, found.detail)
        for found in km.group_coherence(manifest.groups, definitions)
    )


def pin_findings(
    manifest: km.Manifest, sections: Mapping[str, Sequence[ks.Section]]
) -> tuple[km.Finding, ...]:
    """I6: every condensed form's pin matches the source section it condenses."""
    return tuple(
        km.Finding(f"I6-{found.kind}", found.subject, found.detail)
        for found in km.stale_pins(manifest, sections)
    )


def resident_findings(
    manifest: km.Manifest, sections: Mapping[str, Sequence[ks.Section]], injected: Mapping[str, str]
) -> tuple[km.Finding, ...]:
    """I7: no paragraph of an orchestrator-only or no-actor section in any text a spawn receives.

    `injected` maps where each text came from to the text. A paragraph counts when it is long
    enough to identify its source and is not a bare heading (two rules may share a heading); so
    does each such line of a list or table, which a kernel may carry without its neighbours.
    """
    resident = {
        entry: _identifying_texts(text)
        for entry, text in km.entry_texts(manifest, sections).items()
        if isinstance(entry.scope, RESIDENT_SCOPES)
    }
    return tuple(
        km.Finding(
            "I7-resident-text-in-kernel",
            where,
            f"holds text of the {_audience(entry)} section {_section_label(entry)}",
        )
        for where, text in injected.items()
        for entry, paragraphs in resident.items()
        if any(identifying in text for identifying in paragraphs)
    )


def stale_findings(regeneration: tuple[str, ...] | km.KernelModelError) -> tuple[km.Finding, ...]:
    """I8: the paths the generator would change now, or why it cannot say."""
    if isinstance(regeneration, km.KernelModelError):
        detail = f"the generator cannot assemble the kernels: {regeneration}"
        return (km.Finding("I8-stale-kernel", gk.KERNELS_DIR, detail),)
    return tuple(
        km.Finding("I8-stale-kernel", path, "differs from what the generator writes: regenerate")
        for path in regeneration
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


def transition_findings(
    parent: Mapping[str, str] | None, statuses: Mapping[str, str]
) -> tuple[km.Finding, ...]:
    """I9: moves since the parent commit's ledger; none when the parent held no (readable) ledger."""
    if parent is None:
        return ()
    return tuple(
        km.Finding(f"I9-{found.kind}", found.subject, found.detail)
        for found in kl.ledger_transitions(parent, statuses)
    )


def deletion_findings(
    parent: Mapping[str, str] | None, ledger: kl.Ledger | km.KernelModelError | None
) -> tuple[km.Finding, ...]:
    """I9: a ledger the parent commit holds is still there, or its first appearance could repeat."""
    if parent is None or ledger is not None:
        return ()
    detail = "the parent commit holds this ledger and this tree does not: restore it"
    return (km.Finding("I9-ledger-deleted", km.LEDGER_PATH, detail),)


def omitting_roles(definitions: Mapping[str, str]) -> frozenset[str]:
    """The agents whose definition sets `omitClaudeMd` to anything but false."""
    return frozenset(name for name, text in definitions.items() if _omits_claude_md(name, text))


@dataclass(frozen=True)
class LivenessReport:
    """What the liveness check judged and found: a clean report states how much it judged."""

    judged: int  # spawns of adopted roles at or after their record's start
    adopted: int  # roles at trial or switched in the ledger read
    findings: tuple[km.Finding, ...]


def liveness_report(
    adoptions: Mapping[str, kl.Adoption],
    rows: Sequence[Mapping[str, object]],
    since: datetime | None = None,
) -> LivenessReport:
    """Each spawn of an adopted role, from its record's start and from `since`, judged for its row.

    A spawn is an agent's first `agent_start`; a later one is a resume and is never judged. Only
    this plugin's agents (`praxion:<role>`) count; the role is what follows the prefix. Rows are
    matched by agent id, so one row serves exactly the spawn that wrote it.
    """
    delivered = {row.get("agent_id") for row in rows if row.get("event_type") == KERNEL_ROW}
    judged = _judged_spawns(adoptions, rows, since)
    findings = tuple(
        km.Finding(
            "liveness-missing-row",
            f"role {role}",
            f"agent {agent_id} started at {row.get('timestamp')} and left no {KERNEL_ROW} row",
        )
        for agent_id, role, row in judged
        if agent_id not in delivered
    )
    return LivenessReport(len(judged), len(adoptions), findings)


def _judged_spawns(
    adoptions: Mapping[str, kl.Adoption],
    rows: Sequence[Mapping[str, object]],
    since: datetime | None,
) -> list[tuple[object, str, Mapping[str, object]]]:
    spawns: dict[object, Mapping[str, object]] = {}
    for row in rows:
        if row.get("event_type") == SPAWN_ROW:
            spawns.setdefault(row.get("agent_id"), row)
    judged = []
    for agent_id, row in spawns.items():
        role = _adopted_role(row, adoptions)
        if role is not None and reader.row_time(dict(row)) >= _judged_from(adoptions[role], since):
            judged.append((agent_id, role, row))
    return judged


def _judged_from(adoption: kl.Adoption, since: datetime | None) -> datetime:
    return adoption.since if since is None else max(adoption.since, since)


def _identifying_texts(text: str) -> tuple[str, ...]:
    texts: list[str] = []
    for block in (b.strip() for b in re.split(r"\n\s*\n", text)):
        if len(block) >= IDENTIFYING_CHARS and not block.startswith("#"):
            texts.append(block)
        lines = [line.strip() for line in block.splitlines()]
        if len(lines) > 1:
            texts += [line for line in lines if _names_its_source(line)]
    return tuple(texts)


def _names_its_source(line: str) -> bool:
    """A line long enough in letters and digits to be this source's: rules of dashes name none."""
    return not line.startswith("#") and sum(c.isalnum() for c in line) >= IDENTIFYING_CHARS


def _audience(entry: km.AudienceEntry) -> str:
    return "orchestrator-only" if isinstance(entry.scope, km.OrchestratorOnly) else "no-actor"


def _section_label(entry: km.AudienceEntry) -> str:
    target = entry.target
    label = f"{target.source} '{target.heading}'"
    return f"{label} (part {target.prefix!r})" if isinstance(target, km.PartTarget) else label


def _passing_run(record: kl.Switched) -> kl.Run:
    return next(run for run in record.runs if run.id == record.passing_run)  # the model holds it


def _omits_claude_md(name: str, definition: str) -> bool:
    flag = km.frontmatter(definition, f"agents/{name}.md").get(OMIT_KEY)
    return flag is not None and flag is not False


def _adopted_role(row: Mapping[str, object], adoptions: Collection[str]) -> str | None:
    agent_type = row.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type.startswith(AGENT_PREFIX):
        return None
    role = agent_type.removeprefix(AGENT_PREFIX)
    return role if role in adoptions else None


def _contract_lines(
    manifest: km.Manifest, sections: Mapping[str, Sequence[ks.Section]]
) -> list[str] | None:
    """The rule's contract lines the core carries, as the manifest classifies them; None for none."""
    target = (gk.CONTRACT_SOURCE, gk.CONTRACT_HEADING)
    entry = next(
        (
            e
            for e in manifest.entries
            if isinstance(e.scope, km.Core) and (e.target.source, e.target.heading) == target
        ),
        None,
    )
    text = km.entry_texts(manifest, sections).get(entry) if entry else None
    return None if text is None else [line.rstrip() for line in text.splitlines() if line.strip()]


def _core_file(kernel_files: Mapping[str, str]) -> str:
    return next((name for name in CORE_FILES if name in kernel_files), CORE_FILES[0])


def _block_drift(where: str, text: str | None, expected: Sequence[str]) -> km.Finding | None:
    """A finding when `text` does not open with the contract block `expected`, line for line."""
    if text is None:
        return km.Finding("I3-contract-drift", where, "the file does not exist")
    actual = text.split(PARAGRAPH_END, 1)[0].splitlines()
    for want, got in zip_longest(expected, actual):
        if want != got:
            return km.Finding(
                "I3-contract-drift",
                where,
                f"the contract block differs: wanted {want!r}, has {got!r}",
            )
    return None


def _preamble_drift(expected: Sequence[str], preamble: str | None) -> tuple[km.Finding, ...]:
    where = gk.PREAMBLE_PATH
    try:
        derived = gk.render_preamble("\n".join(expected))
    except gk.KernelPlanError as exc:
        return (km.Finding("I3-contract-drift", where, f"no preamble can be derived: {exc}"),)
    if preamble is None:
        return (km.Finding("I3-contract-drift", where, "the file does not exist"),)
    if preamble != derived:
        detail = "the preamble's wording is not derived from the contract: regenerate the kernels"
        return (km.Finding("I3-contract-drift", where, detail),)
    return ()


# -- Edge: reading the repository ---------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """Everything the invariants judge, read once from one checkout."""

    definitions: Mapping[str, str]
    manifest: km.Manifest
    sections: Mapping[str, Sequence[ks.Section]]
    required: tuple[str, ...]
    kernel_files: Mapping[str, str]  # name -> text, for each `claude/kernels/*.md`
    index_strings: Mapping[str, tuple[str, ...]] | None  # role -> injected strings; None: no index
    preamble: str | None
    regeneration: (
        tuple[str, ...] | km.KernelModelError
    )  # paths the generator would change, or why not
    statuses: Mapping[str, str]  # role -> trial or switched, whatever else the ledger holds
    ledger: kl.Ledger | km.KernelModelError | None  # evidence-checked, the refusal, or no file
    parent_statuses: Mapping[str, str] | None  # the ledger's statuses at HEAD; None: no ledger


def gather(root: Path) -> Evidence:
    definitions = km.agent_definitions(root)
    manifest = km.load_manifest(root, definitions)
    required = ks.always_loaded_sources(root)
    sources = {*required, *(entry.target.source for entry in manifest.entries)}
    return Evidence(
        definitions,
        manifest,
        {s: ks.load_sections(root, s) for s in sorted(sources) if (root / s).is_file()},
        required,
        _kernel_files(root),
        _index_strings(root),
        _read_text(root / gk.PREAMBLE_PATH),
        _regeneration(root),
        km.load_statuses(root),  # first: a ledger it cannot read is an input error, not a finding
        _evidence_checked_ledger(root, definitions),
        _parent_statuses(root),
    )


def check(root: Path) -> tuple[km.Finding, ...]:
    """Every finding for the checkout at `root`; raises on an input it cannot read."""
    evidence = gather(root)
    injected = injected_texts(evidence)
    totality = totality_findings(evidence.manifest, evidence.sections, evidence.required)
    return (
        *totality,
        *core_findings(evidence.definitions, evidence.index_strings, evidence.kernel_files),
        *contract_findings(
            evidence.manifest, evidence.sections, evidence.kernel_files, evidence.preamble
        ),
        *cap_findings(injected),
        *group_findings(evidence.manifest, evidence.definitions),
        *pin_findings(evidence.manifest, evidence.sections),
        *resident_findings(evidence.manifest, evidence.sections, injected),
        # the generator refuses sources that fail I1: that refusal is I1's finding, not a second
        *(() if totality else stale_findings(evidence.regeneration)),
        *flip_findings(omitting_roles(evidence.definitions), evidence.statuses),
        *record_findings(evidence.ledger),
        *transition_findings(evidence.parent_statuses, evidence.statuses),
        *deletion_findings(evidence.parent_statuses, evidence.ledger),
    )


def injected_texts(evidence: Evidence) -> dict[str, str]:
    """Where each text a spawn can receive came from, to the text: kernel files, then strings."""
    texts = {f"{gk.KERNELS_DIR}/{name}": text for name, text in evidence.kernel_files.items()}
    for role, strings in (evidence.index_strings or {}).items():
        texts.update({f"{km.INDEX_PATH} {role} string {n}": s for n, s in enumerate(strings, 1)})
    return texts


def check_liveness(root: Path, plugin_root: Path, since: str | None) -> LivenessReport:
    """Spawns in the observation log under `root` that left no kernel row, by the plugin's ledger."""
    adoptions = kl.load_adoptions(plugin_root)
    return liveness_report(adoptions, _observation_rows(root), _commit_time(root, since))


def _read_text(path: Path) -> str | None:
    return path.read_bytes().decode("utf-8") if path.is_file() else None


def _kernel_files(root: Path) -> dict[str, str]:
    directory = root / gk.KERNELS_DIR
    paths = sorted(directory.glob(KERNEL_FILE_GLOB)) if directory.is_dir() else []
    return {path.name: path.read_bytes().decode("utf-8") for path in paths}


def _index_strings(root: Path) -> dict[str, tuple[str, ...]] | None:
    path = root / km.INDEX_PATH
    if not path.is_file():
        return None
    try:
        roles = json.loads(path.read_bytes().decode("utf-8"))["roles"]
        return {role: tuple(body["strings"]) for role, body in roles.items()}
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise km.KernelModelError(f"{path}: not an index this checker can read: {exc!r}") from exc


def _regeneration(root: Path) -> tuple[str, ...] | km.KernelModelError:
    try:
        return tuple(gk.stale_files(root, gk.plan_kernels(root).files))
    except km.KernelModelError as refusal:
        return refusal


def _evidence_checked_ledger(
    root: Path, definitions: Collection[str]
) -> kl.Ledger | km.KernelModelError | None:
    if not (root / km.LEDGER_PATH).is_file():
        return None
    try:
        return kl.load_ledger(root, definitions)
    except km.KernelModelError as refusal:
        return refusal


def _parent_statuses(root: Path) -> Mapping[str, str] | None:
    """The ledger's statuses as of HEAD, the commit this one builds on; None when HEAD has none.

    Only statuses matter to the ladder, so the parent is read as leniently as the generator
    reads the working copy: a commit that repairs a ledger the model now refuses must not be
    blocked by the old one. A parent too broken even for that is told, then judged as none.
    """
    shown = run_git(root, "show", f"HEAD:{km.LEDGER_PATH}")
    if shown.returncode != 0:  # no repository, no commit yet, or no ledger in it
        return None
    try:
        return km.parse_statuses(km.parse_yaml(shown.stdout, f"{km.LEDGER_PATH} at HEAD"))
    except km.KernelModelError as unreadable:
        print(f"note: {unreadable}: its moves are not judged", file=sys.stderr)
        return None


def _observation_rows(root: Path) -> list[dict]:
    """Every row of the log under `root`, read strictly: a lost row could hide a violation."""
    state_dir = root / STATE_DIR
    listing = reader.segment_listing(state_dir, archives=True)
    if listing.error:
        raise km.KernelModelError(
            f"{state_dir}: the observation log cannot be listed: {listing.error}"
        )
    if not listing.segments:
        raise km.KernelModelError(f"no observation log under {state_dir}: nothing to judge")
    rows: list[dict] = []
    for path in listing.segments:
        segment = reader.read_segment(path)
        if segment.error or segment.malformed_lines:
            problem = segment.error or f"unparseable lines {list(segment.malformed_lines)}"
            raise km.KernelModelError(
                f"{path}: the observation log is not readable whole: {problem}"
            )
        rows.extend(segment.rows)
    return rows


def _commit_time(root: Path, revision: str | None) -> datetime | None:
    if revision is None:
        return None
    shown = run_git(root, "log", "-1", "--format=%cI", revision, "--")
    if shown.returncode != 0 or not shown.stdout.strip():
        raise km.KernelModelError(f"--since {revision!r} is not a revision of {root}")
    return datetime.fromisoformat(shown.stdout.strip())


# -- Edge: the command line ---------------------------------------------------------------


def render_human(
    findings: Sequence[km.Finding], label: str = "kernel manifest", scope: str = ""
) -> str:
    """The report as text; `scope` says how much was judged, shown after the verdict."""
    tail = f" ({scope})" if scope else ""
    if not findings:
        return f"{label}: clean{tail}"
    lines = [f"{f.kind}: {f.subject}" + (f" -- {f.detail}" if f.detail else "") for f in findings]
    return "\n".join([*lines, f"{label}: {len(findings)} finding(s){tail}"])


def render_json(findings: Sequence[km.Finding], **extra: object) -> str:
    report = {
        "schema": REPORT_SCHEMA,
        "findings": [{"kind": f.kind, "subject": f.subject, "detail": f.detail} for f in findings],
        **extra,
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


def render_liveness(report: LivenessReport, as_json: bool) -> str:
    if as_json:
        return render_json(report.findings, judged=report.judged, adopted=report.adopted)
    scope = f"{report.judged} spawn(s) of {report.adopted} adopted role(s) judged"
    return render_human(report.findings, "kernel liveness", scope)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hold the kernels to the manifest and its sources."
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    parser.add_argument(
        "--liveness",
        action="store_true",
        help="judge the observation log under --repo-root instead of the kernels: each spawn of "
        "a role at trial or switched that left no kernel_injected row",
    )
    parser.add_argument(
        "--since", metavar="REV", help="with --liveness: only spawns at or after REV's commit time"
    )
    parser.add_argument(
        "--plugin-root",
        help="with --liveness: the plugin checkout whose ledger names the adopted roles "
        "(defaults to the checkout this script is in)",
    )
    args = parser.parse_args(argv)
    if (args.since or args.plugin_root) and not args.liveness:
        parser.error("--since and --plugin-root apply only with --liveness")
    try:
        root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
        if is_plugin_cache_path(root):
            raise ValueError(f"{root} is an installed-plugin cache: check the source checkout")
        if args.liveness:
            plugin_root = Path(args.plugin_root) if args.plugin_root else SCRIPT_DIR.parent
            report = check_liveness(root, plugin_root, args.since)
            output, findings = render_liveness(report, args.json), report.findings
        else:
            findings = check(root)
            output = render_json(findings) if args.json else render_human(findings)
    except (
        ValueError,
        km.MissingParserError,
        OSError,
    ) as exc:  # the model's errors are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
