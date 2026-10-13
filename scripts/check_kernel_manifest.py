"""The kernel manifest checker: holds the always-loaded guidance, the manifest and the kernels together.

`python3 scripts/check_kernel_manifest.py [--json] [--repo-root DIR]` is the commit gate behind the
per-role kernels. It reads the repository once, then judges five invariants; a finding's kind
names the invariant it breaks. Exit 0 clean, 1 findings, 2 input error (no manifest, no plugin
checkout, PyYAML absent, an unreadable file) -- a gate that cannot read its input never passes.

| Kind                  | Holds when                                                                   |
| --------------------- | ---------------------------------------------------------------------------- |
| `I1-unclassified`     | every section and part of every always-loaded source has an audience entry   |
| `I1-orphan`           | every entry names a section or part that exists                              |
| `I1-duplicate-heading`| no source holds two sections of one heading (an entry could not tell apart)  |
| `I2-missing-core`     | every detected agent has a kernel core: the index lists it with strings      |
| `I3-contract-drift`   | the core carries the contract rule's own lines, and the preamble is current  |
| `I4-over-cap`         | no committed kernel file and no injected string exceeds the harness cap      |
| `I5-group-mismatch`   | the ADR-author and ledger-writer groups equal the agents that write those    |

The totality and group judgements are `kernel_model`'s; this module gathers the evidence, names
each finding and renders it. The index is read here as plain JSON, not through `kernel_model`,
because the model refuses an over-cap string at parse time and I4 must report one, not die on it.

Detected, never listed: the agents come from `agents/*.md`, the always-loaded sources from the
tree, so a new agent or rule is covered the day it exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

import generate_kernels as gk
import kernel_model as km
import kernel_sources as ks
from _repo_root import is_plugin_cache_path, resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

REPORT_SCHEMA = 1
KERNEL_FILE_GLOB = "*.md"
CORE_FILES = ("core.md", "core-1.md")  # a core above the cap is numbered parts; part one leads
PARAGRAPH_END = "\n\n"


# -- Pure: the five invariants ---------------------------------------------------------


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
    )


def check(root: Path) -> tuple[km.Finding, ...]:
    """Every finding for the checkout at `root`; raises on an input it cannot read."""
    evidence = gather(root)
    caps = {f"{gk.KERNELS_DIR}/{name}": text for name, text in evidence.kernel_files.items()}
    for role, strings in (evidence.index_strings or {}).items():
        caps.update({f"{km.INDEX_PATH} {role} string {n}": s for n, s in enumerate(strings, 1)})
    return (
        *totality_findings(evidence.manifest, evidence.sections, evidence.required),
        *core_findings(evidence.definitions, evidence.index_strings, evidence.kernel_files),
        *contract_findings(
            evidence.manifest, evidence.sections, evidence.kernel_files, evidence.preamble
        ),
        *cap_findings(caps),
        *group_findings(evidence.manifest, evidence.definitions),
    )


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


# -- Edge: the command line ---------------------------------------------------------------


def render_human(findings: Sequence[km.Finding]) -> str:
    if not findings:
        return "kernel manifest: clean"
    lines = [f"{f.kind}: {f.subject}" + (f" -- {f.detail}" if f.detail else "") for f in findings]
    return "\n".join([*lines, f"kernel manifest: {len(findings)} finding(s)"])


def render_json(findings: Sequence[km.Finding]) -> str:
    report = {
        "schema": REPORT_SCHEMA,
        "findings": [{"kind": f.kind, "subject": f.subject, "detail": f.detail} for f in findings],
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hold the kernels to the manifest and its sources."
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)
    try:
        root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
        if is_plugin_cache_path(root):
            raise ValueError(f"{root} is an installed-plugin cache: check the source checkout")
        findings = check(root)
    except (
        ValueError,
        km.MissingParserError,
        OSError,
    ) as exc:  # the model's errors are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(render_json(findings) if args.json else render_human(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
