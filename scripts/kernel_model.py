"""The kernel model: what the audience manifest, the adoption ledger and the index mean.

`rules/_audience.yaml` (who each always-loaded section serves), the per-role adoption
ledger `.ai-state/kernel_adoption.yaml` and the generated `claude/kernels/index.json` are
read here and nowhere else: each wire shape is parsed once, at the edge, into values whose
illegal states cannot be built, so no gate downstream re-validates or guesses.

Where each invariant is enforced:

| Invariant                                                              | Enforced by                           |
| ---------------------------------------------------------------------- | ------------------------------------- |
| scope is core / role / orchestrator-only / no-actor; core and role     | `Scope` sum, `_parse_scope`           |
|   carry a form; condensed carries authored text and a pin              | `Condensed`, `_parse_form`            |
| no empty audience, unknown agent or group, empty group                 | `Role`, `Group`, `_known_audience`    |
| orchestrator-only / no-actor give a reason and name no agent           | `_Reasoned`, `_parse_scope`           |
| one entry per section; parts of a section have distinct prefixes       | `_refuse_second_entry`                |
| an unknown `version` / `schema` is refused until taught                | `_check_version`                      |
| an injected string never exceeds the harness cap                       | `KernelString`, `RoleKernel`          |
| a switched record holds every piece of flip evidence                   | `Switched.__post_init__`              |
| ledger moves only absent -> trial -> switched                          | `ledger_transitions`                  |
| every section and part classified; no orphaned entry                   | `check_totality`                      |
| a condensed form's pin matches its source                              | `stale_pins`                          |
| the two writer groups equal what the definitions say                   | `group_coherence`                     |

The pure functions take plain values; the `load_*` functions are the edge. PyYAML is
imported lazily, so a bare `python3` without it fails naming the interpreter.

The ledger has two readers: `load_ledger` builds the evidence-checked record (the commit
gate); `load_statuses` reads only who is at trial or switched (the generator and the
liveness check, which must survive a record the gate is about to refuse).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import kernel_sources as ks

SUPPORTED_VERSION = 1
SUPPORTED_INDEX_SCHEMA = 1
MAX_STRING_CHARS = 10_000  # the harness replaces a longer injected string with a file path
REQUIRED_PAIRS = 20  # a flip rests on a run of at least this many complete pairs

CORE = "core"
ADR_AUTHOR = "adr-author"
LEDGER_WRITER = "ledger-writer"
STATUSES = ("trial", "switched")

MANIFEST_PATH = "rules/_audience.yaml"
LEDGER_PATH = ".ai-state/kernel_adoption.yaml"
INDEX_PATH = "claude/kernels/index.json"

_SWITCHED_FIELDS = tuple(
    "passing_run probe_before_tokens probe_after_tokens flip_rule_ratified flip_ratified".split()
)
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)
_APPENDS_ROWS = re.compile(r"append\b[^\n]*?\brows?\b", re.IGNORECASE)
_NAME_LINE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


class KernelModelError(ValueError):
    """A wire shape that is not a legal state; the message names the entry or role."""


class MissingParserError(RuntimeError):
    """PyYAML is absent from the running interpreter."""


@dataclass(frozen=True)
class Finding:
    """One thing a gate reports: a stable `kind`, where (`subject`) and why (`detail`)."""

    kind: str
    subject: str
    detail: str = ""


# -- Audience entries, groups, modules, authored text, the manifest ---------------


@dataclass(frozen=True)
class SectionTarget:
    source: str
    heading: str


@dataclass(frozen=True)
class PartTarget:
    """A part of a mixed-audience section: it starts at the one line beginning `prefix`."""

    source: str
    heading: str
    prefix: str

    def __post_init__(self) -> None:
        if not self.prefix.strip():
            raise KernelModelError("a part names no leading text")


Target = SectionTarget | PartTarget


@dataclass(frozen=True)
class Verbatim:
    """The source text, unchanged."""


@dataclass(frozen=True)
class Condensed:
    """Authored text standing for the source; `pinned_sha` is the source it was written from."""

    text_ref: str
    pinned_sha: str

    def __post_init__(self) -> None:
        if not self.pinned_sha:
            raise KernelModelError("a condensed form without a pin")
        if not self.text_ref:
            raise KernelModelError("a condensed form names no authored text")


Form = Verbatim | Condensed


@dataclass(frozen=True)
class Core:
    form: Form


@dataclass(frozen=True)
class Role:
    module: str
    form: Form

    def __post_init__(self) -> None:
        if not self.module or self.module == CORE:
            raise KernelModelError("a role entry names a module other than core")


@dataclass(frozen=True)
class _Reasoned:
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise KernelModelError(f"a {type(self).__name__} entry gives no reason")


class OrchestratorOnly(_Reasoned):
    """Text only the main session acts on; kept resident there, never in a kernel."""


class NoActor(_Reasoned):
    """Text no actor acts on; kept resident, never in a kernel."""


Scope = Core | Role | OrchestratorOnly | NoActor


@dataclass(frozen=True)
class AudienceEntry:
    target: Target
    scope: Scope

    @property
    def form(self) -> Form | None:
        return self.scope.form if isinstance(self.scope, Core | Role) else None


@dataclass(frozen=True)
class AuthoredText:
    id: str
    path: str
    module: str
    condenses: str | None  # "<source>#<heading>"; None for kernel-only text
    pinned_sha: str | None

    def __post_init__(self) -> None:
        if self.condenses is not None and not self.pinned_sha:
            raise KernelModelError(f"authored text {self.id!r} ({self.condenses}) carries no pin")


@dataclass(frozen=True)
class Manifest:
    groups: Mapping[str, tuple[str, ...]]  # group name -> member agents, never empty
    modules: Mapping[str, tuple[str, ...]]  # module name -> agents and/or groups served
    authored: tuple[AuthoredText, ...]
    entries: tuple[AudienceEntry, ...]


# -- Kernel strings, the index, the adoption record ---------------------------------


def _require_fits(text: str, where: str) -> None:
    if len(text) > MAX_STRING_CHARS:
        raise KernelModelError(f"{where}: {len(text)} characters exceed the {MAX_STRING_CHARS} cap")


@dataclass(frozen=True)
class KernelString:
    role: str
    ordinal: int  # 1-based position among the role's injected strings
    module: str
    part: int | None  # 1-based, for a module delivered as numbered parts
    text: str

    def __post_init__(self) -> None:
        _require_fits(self.text, f"kernel string {self.ordinal} of {self.role} ({self.module})")


@dataclass(frozen=True)
class RoleKernel:
    status: str | None  # "trial" | "switched" | None
    strings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status is not None and self.status not in STATUSES:
            raise KernelModelError(f"status {self.status!r} is neither trial nor switched")
        for number, text in enumerate(self.strings, start=1):
            _require_fits(text, f"injected string {number}")


@dataclass(frozen=True)
class KernelIndex:
    kernel_version: str
    slots: int
    roles: Mapping[str, RoleKernel]


@dataclass(frozen=True)
class Run:
    id: str
    complete_pairs: int
    passes_flip_rule: bool
    entry: str


@dataclass(frozen=True)
class Trial:
    role: str
    since: str
    runs: tuple[Run, ...]


@dataclass(frozen=True)
class Switched:
    role: str
    since: str
    runs: tuple[Run, ...]
    passing_run: str
    probe_before_tokens: int
    probe_after_tokens: int
    flip_rule_ratified: bool
    flip_ratified: bool

    def __post_init__(self) -> None:
        passing = next((run for run in self.runs if run.id == self.passing_run), None)
        gaps = (
            _run_gaps(passing) if passing else [f"cites {self.passing_run!r}, not among its runs"]
        )
        probes = ((n, getattr(self, n)) for n in _SWITCHED_FIELDS[1:3])
        gaps += [f"has no positive {n}" for n, v in probes if type(v) is not int or v <= 0]
        gaps += [
            f"lacks the user's {n}" for n in _SWITCHED_FIELDS[3:] if getattr(self, n) is not True
        ]
        if gaps:
            raise KernelModelError(f"role {self.role}: a switched record " + "; ".join(gaps))


def _run_gaps(run: Run) -> list[str]:
    gaps = []
    if run.complete_pairs < REQUIRED_PAIRS:
        gaps.append(
            f"rests on run {run.id!r} of {run.complete_pairs} pairs (needs {REQUIRED_PAIRS})"
        )
    if not run.passes_flip_rule:
        gaps.append(f"rests on run {run.id!r}, which does not pass the flip rule")
    return gaps


AdoptionRecord = Trial | Switched


@dataclass(frozen=True)
class Ledger:
    eligible: tuple[str, ...]
    records: Mapping[str, AdoptionRecord]


# -- Boundary: wire shapes to values ----------------------------------------------


def _check_version(raw: Mapping[str, Any], key: str, expected: int) -> None:
    value = raw.get(key)
    if type(value) is not int or value != expected:
        raise KernelModelError(
            f"{key} {value!r} is not supported: this reader knows {key} {expected} "
            "and refuses a newer shape until it is taught"
        )


def _mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KernelModelError(f"{what} must be a mapping, got {type(value).__name__}")
    return value


def _sequence(value: Any, what: str) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise KernelModelError(f"{what} must be a list, got {type(value).__name__}")
    return value


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KernelModelError(f"{what} must be non-empty text, got {value!r}")
    return value


@dataclass(frozen=True)
class _Declared:
    """What an entry may name: agents, groups, authored texts, and the modules in play."""

    agents: frozenset[str]
    groups: Mapping[str, tuple[str, ...]]
    modules: dict[str, tuple[str, ...]]  # grows as entries imply a module of their own
    authored: Mapping[str, AuthoredText]


def parse_manifest(raw: Mapping[str, Any], agents: Collection[str]) -> Manifest:
    """The manifest as values; every illegal entry shape is refused naming the entry."""
    raw = _mapping(raw, "the manifest")
    _check_version(raw, "version", SUPPORTED_VERSION)
    known = frozenset(agents)
    groups = _parse_groups(raw.get("groups"), known)
    declared = _Declared(
        known,
        groups,
        _parse_modules(raw.get("modules"), known, groups),
        {t.id: t for t in _parse_authored(raw.get("authored"))},
    )
    entries = _parse_entries(_sequence(raw.get("entries"), "entries"), declared)
    return Manifest(groups, declared.modules, tuple(declared.authored.values()), entries)


def _parse_groups(raw: Any, agents: frozenset[str]) -> dict[str, tuple[str, ...]]:
    groups = {}
    for name, members in _mapping(raw or {}, "groups").items():
        if name in agents:
            raise KernelModelError(f"group {name!r} shares its name with an agent")
        if not (listed := tuple(_sequence(members, f"group {name!r}"))):
            raise KernelModelError(f"group {name!r} has no members")
        unknown = [m for m in listed if m not in agents]
        if unknown:
            raise KernelModelError(f"group {name!r} names unknown agent {unknown[0]!r}")
        groups[name] = listed
    return groups


def _parse_modules(
    raw: Any, agents: frozenset[str], groups: Mapping[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    modules = {}
    for name, body in _mapping(raw or {}, "modules").items():
        audience = tuple(_sequence(_mapping(body, f"module {name!r}").get("audience"), name))
        if name == CORE or not audience:
            raise KernelModelError(f"module {name!r}: core is implicit and an audience is named")
        for member in audience:
            if member not in agents and member not in groups:
                raise KernelModelError(f"module {name!r} names unknown agent or group {member!r}")
        modules[name] = audience
    return modules


def _parse_authored(raw: Any) -> list[AuthoredText]:
    texts = []
    for row in _sequence(raw, "authored"):
        row = _mapping(row, "an authored text")
        for key in ("id", "path", "module"):
            _text(row.get(key), f"authored text {key}")
        texts.append(
            AuthoredText(
                row["id"], row["path"], row["module"], row.get("condenses"), row.get("pinned_sha")
            )
        )
    return texts


def _parse_entries(rows: Sequence[Any], declared: _Declared) -> tuple[AudienceEntry, ...]:
    entries: list[AudienceEntry] = []
    for position, row in enumerate(rows, start=1):
        row = _mapping(row, f"entry {position}")
        label = f"entry {position} ({row.get('source')} '{row.get('heading')}')"
        try:
            entry = AudienceEntry(_parse_target(row), _parse_scope(row, declared))
            _refuse_second_entry(entries, entry)
        except KernelModelError as exc:
            raise KernelModelError(f"{label}: {exc}") from exc
        entries.append(entry)
    return tuple(entries)


def _parse_target(row: Mapping[str, Any]) -> Target:
    source = _text(row.get("source"), "source")
    heading = _text(row.get("heading"), "heading")
    prefix = row.get("part")
    return SectionTarget(source, heading) if prefix is None else PartTarget(source, heading, prefix)


def _parse_scope(row: Mapping[str, Any], declared: _Declared) -> Scope:
    kind = row.get("scope")
    audience = _known_audience(row, declared)
    if kind in ("orchestrator-only", "no-actor"):
        if audience:
            raise KernelModelError(f"a {kind} entry names {audience[0]!r}: it has no actor to name")
        return (OrchestratorOnly if kind == "orchestrator-only" else NoActor)(
            row.get("reason") or ""
        )
    if kind == "core":
        return Core(_parse_form(row, declared.authored))
    if kind == "role":
        form = _parse_form(row, declared.authored)
        return Role(_module_serving(audience, declared.modules), form)
    if not kind:
        raise KernelModelError("an empty audience: the entry names no scope")
    raise KernelModelError(f"unknown scope {kind!r} (core, role, orchestrator-only, no-actor)")


def _known_audience(row: Mapping[str, Any], declared: _Declared) -> tuple[str, ...]:
    agents = tuple(_sequence(row.get("agents"), "agents"))
    groups = tuple(_sequence(row.get("groups"), "groups"))
    for agent in agents:
        if agent not in declared.agents:
            raise KernelModelError(f"unknown agent {agent!r}")
    for group in groups:
        if group not in declared.groups:
            raise KernelModelError(f"unknown group {group!r}")
    return (*agents, *groups)


def _module_serving(audience: tuple[str, ...], modules: dict[str, tuple[str, ...]]) -> str:
    """The declared module for exactly this audience, else the one a single name implies."""
    if not audience:
        raise KernelModelError("an empty audience: a role entry names no agent or group")
    for name, served in modules.items():
        if set(served) == set(audience):
            return name
    if len(audience) > 1:
        raise KernelModelError(f"no declared module serves {', '.join(audience)}")
    name = next(iter(audience))
    if name in modules:
        raise KernelModelError(f"module {name!r} is declared with another audience")
    modules[name] = audience
    return name


def _parse_form(row: Mapping[str, Any], authored: Mapping[str, AuthoredText]) -> Form:
    form = row.get("form")
    if form == "verbatim":
        return Verbatim()
    if form != "condensed":
        raise KernelModelError(f"form must be verbatim or condensed, got {form!r}")
    pin, ref = row.get("pin") or "", row.get("text") or ""
    condensed = Condensed(ref, pin)
    if ref not in authored:
        raise KernelModelError(f"names authored text {ref!r}, which is not registered")
    if authored[ref].pinned_sha != pin:
        raise KernelModelError(f"its pin differs from the pin of authored text {ref!r}")
    return condensed


def _refuse_second_entry(entries: Sequence[AudienceEntry], entry: AudienceEntry) -> None:
    target = entry.target
    for earlier in entries:
        other = earlier.target
        if (other.source, other.heading) != (target.source, target.heading):
            continue
        if not (isinstance(target, PartTarget) and isinstance(other, PartTarget)):
            raise KernelModelError("the section already has an entry: one audience per section")
        if target.prefix == other.prefix:
            raise KernelModelError("the section already has an entry: one audience per section")


def parse_index(raw: Mapping[str, Any]) -> KernelIndex:
    raw = _mapping(raw, "the index")
    _check_version(raw, "schema", SUPPORTED_INDEX_SCHEMA)
    slots = raw.get("slots")
    if type(slots) is not int or slots < 1:
        raise KernelModelError(f"slots must be a positive integer, got {slots!r}")
    roles = {}
    for name, body in _mapping(raw.get("roles"), "roles").items():
        body = _mapping(body, f"role {name!r}")
        strings = tuple(_sequence(body.get("strings"), f"role {name!r} strings"))
        try:
            roles[name] = RoleKernel(body.get("status"), strings)
        except KernelModelError as exc:
            raise KernelModelError(f"role {name!r}: {exc}") from exc
    version = _text(raw.get("kernel_version"), "kernel_version")
    return KernelIndex(version, slots, MappingProxyType(roles))


def parse_statuses(raw: Mapping[str, Any]) -> Mapping[str, str]:
    """Which roles are at trial or switched, trusting nothing else in the record."""
    raw = _mapping(raw, "the ledger")
    _check_version(raw, "version", SUPPORTED_VERSION)
    statuses = {}
    for role, row in _mapping(raw.get("roles") or {}, "roles").items():
        status = _mapping(row, f"role {role!r}").get("status")
        if status not in STATUSES:
            raise KernelModelError(f"role {role}: status {status!r} is neither trial nor switched")
        statuses[role] = status
    return MappingProxyType(statuses)


def parse_ledger(raw: Mapping[str, Any], agents: Collection[str]) -> Ledger:
    """The ledger with its evidence: a switched role missing any piece is refused by name."""
    statuses = parse_statuses(raw)
    eligible = tuple(_sequence(raw.get("eligible"), "eligible"))
    records = {}
    for role, status in statuses.items():
        if role not in agents:
            raise KernelModelError(f"role {role}: no such agent")
        records[role] = _parse_record(role, status, raw["roles"][role], role in eligible)
    return Ledger(eligible, MappingProxyType(records))


def _parse_record(role: str, status: str, row: Mapping[str, Any], eligible: bool) -> AdoptionRecord:
    since = _text(row.get("since"), f"role {role}: since")
    runs = tuple(_parse_run(role, run) for run in _sequence(row.get("runs"), "runs"))
    if status == "trial":
        return Trial(role, since, runs)
    if not eligible:
        raise KernelModelError(f"role {role}: is not eligible to be switched")
    missing = [key for key in _SWITCHED_FIELDS if row.get(key) is None]
    if missing:
        raise KernelModelError(f"role {role}: a switched record lacks {', '.join(missing)}")
    return Switched(role, since, runs, *(row[key] for key in _SWITCHED_FIELDS))


def _parse_run(role: str, row: Any) -> Run:
    row = _mapping(row, f"role {role}: a run")
    return Run(
        id=_text(row.get("id"), f"role {role}: run id"),
        complete_pairs=row.get("complete_pairs") or 0,
        passes_flip_rule=row.get("passes_flip_rule") is True,
        entry=row.get("entry") or "",
    )


# -- Pure: totality, pins, groups, transitions --------------------------------------


def _by_section(manifest: Manifest) -> dict[tuple[str, str], list[AudienceEntry]]:
    grouped: dict[tuple[str, str], list[AudienceEntry]] = {}
    for entry in manifest.entries:
        grouped.setdefault((entry.target.source, entry.target.heading), []).append(entry)
    return grouped


def _subject(source: str, heading: str) -> str:
    return f"{source} '{heading}'"


def check_totality(
    manifest: Manifest, sections: Mapping[str, Sequence[ks.Section]], required: Collection[str]
) -> tuple[Finding, ...]:
    """Unclassified sections and parts of `required` sources; entries naming nothing real.

    `sections` maps every required source and every other source the manifest cites to its
    sections (a cited source that is absent means its file is gone); a cited source outside
    `required` registers only what it contributes and is never required to be total.
    """
    by_section = _by_section(manifest)
    findings: list[Finding] = []
    for source in sorted(required):
        findings += _unclassified(source, sections[source], by_section)
    for (source, heading), entries in by_section.items():
        findings += _orphans(source, heading, entries, sections.get(source), source in required)
    return tuple(findings)


def _unclassified(
    source: str,
    sections: Sequence[ks.Section],
    by_section: Mapping[tuple[str, str], list[AudienceEntry]],
) -> list[Finding]:
    findings = []
    seen: set[str] = set()
    for section in sections:
        subject = _subject(source, section.heading)
        if section.heading in seen:
            findings.append(Finding("duplicate-heading", subject, "two sections share a heading"))
        elif (source, section.heading) not in by_section:
            findings.append(Finding("unclassified", subject))
        seen.add(section.heading)
    return findings


def _orphans(
    source: str,
    heading: str,
    entries: Sequence[AudienceEntry],
    sections: Sequence[ks.Section] | None,
    required: bool,
) -> list[Finding]:
    subject = _subject(source, heading)
    if sections is None:
        return [Finding("orphan", subject, "the source file does not exist")]
    section = next((s for s in sections if s.heading == heading), None)
    if section is None:
        return [Finding("orphan", subject, "no such heading in the source")]
    prefixes = [e.target.prefix for e in entries if isinstance(e.target, PartTarget)]
    if not prefixes:
        return []
    try:
        parts = ks.split_parts(section, prefixes)
    except ks.PartPrefixError as exc:
        return [Finding("orphan", subject, str(exc))]
    lead = next((p for p in parts if p.prefix is None), None)
    if lead is None or not required:
        return []
    first = next((line for line in lead.text.splitlines()[1:] if line.strip()), "").strip()
    return [Finding("unclassified", subject, f"leading text {first!r} has no entry")]


def entry_texts(
    manifest: Manifest, sections: Mapping[str, Sequence[ks.Section]]
) -> dict[AudienceEntry, str]:
    """The exact source bytes each entry covers; entries whose source cannot be cut are absent."""
    texts: dict[AudienceEntry, str] = {}
    for (source, heading), entries in _by_section(manifest).items():
        section = next((s for s in sections.get(source, ()) if s.heading == heading), None)
        prefixes = [e.target.prefix for e in entries if isinstance(e.target, PartTarget)]
        try:
            parts = ks.split_parts(section, prefixes) if section and prefixes else ()
        except ks.PartPrefixError:
            continue
        by_prefix = {part.prefix: part.text for part in parts}
        for entry in entries if section is not None else ():
            prefix = getattr(entry.target, "prefix", None)
            texts[entry] = by_prefix[prefix] if prefix else (section.text if section else "")
    return texts


def stale_pins(
    manifest: Manifest, sections: Mapping[str, Sequence[ks.Section]]
) -> tuple[Finding, ...]:
    return tuple(
        Finding(
            "stale-pin",
            _subject(entry.target.source, entry.target.heading),
            "the source changed since it was condensed",
        )
        for entry, text in entry_texts(manifest, sections).items()
        if isinstance(entry.form, Condensed) and ks.pin_sha(text) != entry.form.pinned_sha
    )


def writes_adr_drafts(definition: str) -> bool:
    """True when the definition tells its agent to create ADR draft fragments."""
    return any(
        "decisions/drafts/" in line and "create" in line.lower() for line in definition.splitlines()
    )


def appends_ledger_rows(definition: str) -> bool:
    """True when the definition tells its agent to append rows to the tech-debt ledger."""
    return any(
        "TECH_DEBT_LEDGER" in line and _APPENDS_ROWS.search(line)
        for line in definition.splitlines()
    )


_WRITER_GROUPS = {ADR_AUTHOR: writes_adr_drafts, LEDGER_WRITER: appends_ledger_rows}


def group_coherence(
    groups: Mapping[str, Sequence[str]], definitions: Mapping[str, str]
) -> tuple[Finding, ...]:
    """The adr-author and ledger-writer groups against what the definitions say, both ways."""
    findings = []
    for name, does in _WRITER_GROUPS.items():
        wanted = {agent for agent, text in definitions.items() if does(text)}
        have = set(groups.get(name, ()))
        findings += [
            Finding("group-missing", f"group {name}", f"{agent}'s definition does this, not listed")
            for agent in sorted(wanted - have)
        ]
        findings += [
            Finding("group-extra", f"group {name}", f"{agent}'s definition does not do this")
            for agent in sorted(have - wanted)
        ]
    return tuple(findings)


_LADDER = (None, "trial", "switched")  # a role stays or climbs one rung: no skipping, no descent


def ledger_transitions(before: Ledger | None, after: Ledger) -> tuple[Finding, ...]:
    """Moves from the parent commit's ledger that go anywhere but forward one status."""
    earlier = before.records if before is not None else {}
    findings = []
    for role in sorted(set(earlier) | set(after.records)):
        was, now = _status(earlier.get(role)), _status(after.records.get(role))
        if _LADDER.index(now) - _LADDER.index(was) not in (0, 1):
            move = f"{was or 'absent'} -> {now or 'absent'}"
            findings.append(Finding("ledger-transition", f"role {role}", move))
    return tuple(findings)


def _status(record: AdoptionRecord | None) -> str | None:
    return None if record is None else type(record).__name__.lower()


# -- Edge: files ------------------------------------------------------------------


def _require_yaml() -> Any:
    """Import PyYAML, or raise naming the interpreter that lacks it."""
    try:
        import yaml
    except ImportError as exc:
        raise MissingParserError(
            f"PyYAML is required to read the kernel manifest and ledger, and {sys.executable} "
            "does not have it. Run under the project environment (for example "
            "`uv run --with pyyaml python <script>`) or install pyyaml into that interpreter."
        ) from exc
    return yaml


def _read_yaml(path: Path) -> Mapping[str, Any]:
    yaml = _require_yaml()
    try:
        loaded = yaml.safe_load(path.read_bytes().decode("utf-8"))
    except yaml.YAMLError as exc:
        raise KernelModelError(f"{path}: not valid YAML: {exc}") from exc
    return _mapping(loaded, str(path))


def agent_definitions(root: Path) -> dict[str, str]:
    """Agent name to definition text, for each `agents/*.md` whose frontmatter declares a name."""
    found = {}
    for path in sorted((root / "agents").glob("*.md")):
        text = path.read_bytes().decode("utf-8")
        frontmatter = _FRONTMATTER.match(text)
        if frontmatter and (name := _NAME_LINE.search(frontmatter.group(1))):
            found[name.group(1)] = text
    return found


def load_manifest(root: Path, agents: Collection[str]) -> Manifest:
    path = root / MANIFEST_PATH
    if not path.is_file():
        raise KernelModelError(
            f"{path} does not exist: a gate over no manifest passes over nothing"
        )
    return parse_manifest(_read_yaml(path), agents)


def load_ledger(root: Path, agents: Collection[str]) -> Ledger:
    """The evidence-checked ledger; no ledger file is an empty ledger."""
    path = root / LEDGER_PATH
    if not path.is_file():
        return Ledger((), MappingProxyType({}))
    return parse_ledger(_read_yaml(path), agents)


def load_statuses(root: Path) -> Mapping[str, str]:
    path = root / LEDGER_PATH
    return parse_statuses(_read_yaml(path)) if path.is_file() else MappingProxyType({})


def load_index(root: Path) -> KernelIndex | None:
    """The committed index; none means no kernel is injected anywhere."""
    path = root / INDEX_PATH
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_bytes().decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise KernelModelError(f"{path}: not valid JSON: {exc}") from exc
    return parse_index(raw)
