"""Generate the per-role kernels: the process each spawned agent needs, cut from the rules.

`python3 scripts/generate_kernels.py [--check] [--repo-root DIR]` reads the audience manifest
(`rules/_audience.yaml`), the always-loaded sources it classifies and the authored texts under
`claude/kernels/src/`, and writes under `claude/kernels/`:

- one file per module: `core.md` (the three universal blocks, then the rest of the core) and
  one for each declared module; a module above the 10,000-character cap arrives as
  `<module>-<n>.md` parts cut at paragraph ends, whose concatenation is the module (the first
  part of the core carries the contract, because the blocks come first);
- `core-blocks.md`: the three universal blocks, the part of the core every agent definition
  carries as its fallback (a hook-delivered kernel never repeats them);
- `index.json`: per role its status (projected from the adoption ledger), the modules in each
  of its injected strings, and the strings themselves, packed into the fewest strings under
  the cap with modules in order and none split; `slots` is the most strings any role has plus
  a reserve for the working project's own `CLAUDE.md`.

Text rendered is classified `core` or `role`; `orchestrator-only` and `no-actor` text never is.
Verbatim sections are the source bytes; a condensed entry is its authored text. Every run over
the same sources writes the same bytes. `--check` assembles in memory, writes nothing and exits
1 when anything on disk differs. Exit 0 written or fresh, 1 stale under `--check`, 2 input error.

Two wordings are role-specific rather than shared: a role whose own definition words the
partial-output stop line `Failed at` is told `Failed at`, not `Stopped at`, in its strings
(the module files keep the shared wording).

Stdlib plus PyYAML (read once, in `kernel_model`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import kernel_model as km
import kernel_sources as ks
from _markdown_tables import code_mask
from _repo_root import is_plugin_cache_path, resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

KERNELS_DIR = "claude/kernels"
BLOCKS_FILE = "core-blocks.md"
INDEX_SCHEMA = 1
PROJECT_FILE_RESERVE = 6  # slots kept for the working project's CLAUDE.md, ~10,000 characters each
PARAGRAPH_GAP = "\n\n"
MODULE_JOIN = "+"  # joins the module labels packed into one string

CONTRACT_SOURCE = "rules/swe/agent-behavioral-contract.md"
CONTRACT_HEADING = "Agent Behavioral Contract"
LINKS_TEXT = "praxion-links"
RETURN_TEXT = "return-contract"
BLOCK_TEXTS = frozenset({LINKS_TEXT, RETURN_TEXT})

SHARED_STOP_LABEL = "Stopped at"
OWN_STOP_LABEL = "Failed at"


class KernelPlanError(km.KernelModelError):
    """The sources cannot be assembled into kernels."""


@dataclass(frozen=True)
class Kernel:
    """The sources as text: the universal blocks and every module, before any splitting."""

    blocks: str  # contract block, links block, return-contract block; no trailing newline
    modules: Mapping[str, str]  # "core" (blocks first), then each declared module; newline-ended


@dataclass(frozen=True)
class RoleAssembly:
    role: str
    status: str | None
    modules: tuple[str, ...]  # the modules the role holds, core first
    strings: tuple[km.KernelString, ...]  # as injected, in order


@dataclass(frozen=True)
class KernelPlan:
    files: Mapping[str, bytes]  # repository-relative path -> bytes, everything generated
    roles: Mapping[str, RoleAssembly]

    def assembled_kernel(self, role: str) -> RoleAssembly:
        if role not in self.roles:
            raise KernelPlanError(f"no such role: {role!r}")
        return self.roles[role]


# -- Pure: assembling the text -------------------------------------------------------


def assemble(
    manifest: km.Manifest, sections: Mapping[str, Sequence[ks.Section]], authored: Mapping[str, str]
) -> Kernel:
    texts = km.entry_texts(manifest, sections)
    contract = _contract_entry(manifest)
    placed: dict[str, list[str]] = {name: [] for name in ("core", *manifest.modules)}
    for text in manifest.authored:
        if text.condenses is None and text.id not in BLOCK_TEXTS:
            _place(placed, text.module, authored[text.id], text.id)
    for entry in manifest.entries:
        module = _module_of(entry)
        if module is None or entry is contract or _block_text(entry):
            continue
        body = (
            authored[entry.form.text_ref] if isinstance(entry.form, km.Condensed) else texts[entry]
        )
        _place(placed, module, body, entry.target.heading)
    bare = next((name for name, pieces in placed.items() if name != "core" and not pieces), None)
    if bare:
        raise KernelPlanError(f"module {bare!r} has no text: no entry or authored text places any")
    blocks = PARAGRAPH_GAP.join(
        [
            _contiguous(texts[contract]),
            authored_block(authored, LINKS_TEXT),
            authored_block(authored, RETURN_TEXT),
        ]
    )
    modules = {
        name: PARAGRAPH_GAP.join(t.rstrip("\n") for t in pieces) for name, pieces in placed.items()
    }
    modules["core"] = blocks + PARAGRAPH_GAP + modules["core"]
    return Kernel(blocks, {name: text + "\n" for name, text in modules.items()})


def _contract_entry(manifest: km.Manifest) -> km.AudienceEntry:
    for entry in manifest.entries:
        target = entry.target
        if isinstance(entry.scope, km.Core) and (target.source, target.heading) == (
            CONTRACT_SOURCE,
            CONTRACT_HEADING,
        ):
            return entry
    raise KernelPlanError(f"the core carries no behavioral contract: {CONTRACT_SOURCE} gives none")


def _contiguous(text: str) -> str:
    """The contract's lines as the rule words them, minus the blank line before the self-test."""
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


def authored_block(authored: Mapping[str, str], text_id: str) -> str:
    if text_id not in authored:
        raise KernelPlanError(f"universal block {text_id!r} is not an authored text")
    return authored[text_id].rstrip()


def _module_of(entry: km.AudienceEntry) -> str | None:
    match entry.scope:
        case km.Core():
            return "core"
        case km.Role(module=module):
            return module
        case _:
            return None


def _block_text(entry: km.AudienceEntry) -> bool:
    return isinstance(entry.form, km.Condensed) and entry.form.text_ref in BLOCK_TEXTS


def _place(placed: dict[str, list[str]], module: str, text: str, where: str) -> None:
    if module not in placed:
        raise KernelPlanError(f"{where}: module {module!r} is not declared")
    placed[module].append(text)


def paragraph_atoms(text: str) -> list[str]:
    """`text` cut where a blank-line run (outside code) ends a paragraph; atoms concatenate to it.

    Each cut falls right after the paragraph's own newline, so the blank line that separates
    two paragraphs opens the next atom: a part never ends in a blank line (the end-of-file
    fixer would eat it) and joined parts keep their separators.
    """
    lines = text.splitlines(keepends=True)
    in_code = code_mask([line.rstrip("\r\n") for line in lines])
    line_offsets = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line))
    cuts = [
        text.index("\n", len(text[: line_offsets[i]].rstrip())) + 1
        for i in range(1, len(lines))
        if lines[i].strip() and not lines[i - 1].strip() and not in_code[i - 1]
    ]
    return [text[a:b] for a, b in zip([0, *cuts], [*cuts, len(text)], strict=True)]


def split_parts(text: str, cap: int = km.MAX_STRING_CHARS) -> tuple[str, ...]:
    """`text` as the fewest parts of at most `cap` characters, cut at paragraph ends."""
    if len(text) <= cap:
        return (text,)
    parts: list[str] = []
    current = ""
    for atom in paragraph_atoms(text):
        if len(atom) > cap:
            raise KernelPlanError(f"a paragraph of {len(atom)} characters exceeds the {cap} cap")
        if current and len(current) + len(atom) > cap:
            parts.append(current)
            current = ""
        current += atom
    return (*parts, current)


# -- Pure: files, role strings, index --------------------------------------------------


def plan_files(kernel: Kernel) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """The kernel files by name, and each module's parts."""
    files = {BLOCKS_FILE: kernel.blocks + "\n"}
    parts = {name: split_parts(text) for name, text in kernel.modules.items()}
    for name, pieces in parts.items():
        numbered = len(pieces) > 1
        for number, piece in enumerate(pieces, start=1):
            files[f"{name}-{number}.md" if numbered else f"{name}.md"] = piece
    return files, parts


def compose(
    kernel: Kernel,
    manifest: km.Manifest,
    definitions: Mapping[str, str],
    statuses: Mapping[str, str],
) -> KernelPlan:
    files, parts = plan_files(kernel)
    roles = {
        role: _assemble_role(role, kernel, manifest, parts, definitions[role], statuses.get(role))
        for role in sorted(definitions)
    }
    slots = max(len(r.strings) for r in roles.values()) + PROJECT_FILE_RESERVE if roles else 0
    index = _render_index(files, roles, slots)
    encoded = {f"{KERNELS_DIR}/{name}": text.encode("utf-8") for name, text in files.items()}
    encoded[km.INDEX_PATH] = index.encode("utf-8")
    return KernelPlan(encoded, roles)


def _assemble_role(
    role: str,
    kernel: Kernel,
    manifest: km.Manifest,
    parts: Mapping[str, tuple[str, ...]],
    definition: str,
    status: str | None,
) -> RoleAssembly:
    names = ("core", *(m for m in manifest.modules if role in _members(manifest, m)))
    label = OWN_STOP_LABEL if _words_stop_line_as_failed(definition) else SHARED_STOP_LABEL
    units = [
        (module_label, text.replace(f"**{SHARED_STOP_LABEL}**", f"**{label}**").strip())
        for module_label, text in _units(names, parts, kernel.blocks)
    ]
    return RoleAssembly(role, status, names, _pack(role, units))


def _members(manifest: km.Manifest, module: str) -> frozenset[str]:
    return frozenset(
        agent for name in manifest.modules[module] for agent in manifest.groups.get(name, (name,))
    )


def _words_stop_line_as_failed(definition: str) -> bool:
    return OWN_STOP_LABEL in definition and SHARED_STOP_LABEL not in definition


def _units(
    names: Sequence[str], parts: Mapping[str, tuple[str, ...]], blocks: str
) -> Iterator[tuple[str, str]]:
    """(label, text) per module part a role holds; the blocks stay in the definition."""
    for name in names:
        for number, part in enumerate(parts[name], start=1):
            text = part.removeprefix(blocks) if name == "core" and number == 1 else part
            if text.strip():
                yield (name if len(parts[name]) == 1 else f"{name}-{number}"), text


def _pack(role: str, units: Sequence[tuple[str, str]]) -> tuple[km.KernelString, ...]:
    """Units in order into the fewest strings under the cap; a unit is never split."""
    groups: list[tuple[list[str], str]] = []
    for label, text in units:
        if groups and len(groups[-1][1]) + len(PARAGRAPH_GAP) + len(text) <= km.MAX_STRING_CHARS:
            labels, held = groups[-1]
            groups[-1] = ([*labels, label], held + PARAGRAPH_GAP + text)
        else:
            groups.append(([label], text))
    return tuple(
        km.KernelString(role, ordinal, MODULE_JOIN.join(labels), None, text)
        for ordinal, (labels, text) in enumerate(groups, start=1)
    )


def _render_index(files: Mapping[str, str], roles: Mapping[str, RoleAssembly], slots: int) -> str:
    body = {
        "schema": INDEX_SCHEMA,
        "kernel_version": _kernel_version(files, roles),
        "slots": slots,
        "roles": {
            name: {
                "status": role.status,
                "modules": [s.module for s in role.strings],
                "strings": [s.text for s in role.strings],
            }
            for name, role in roles.items()
        },
    }
    return json.dumps(body, indent=2, ensure_ascii=False) + "\n"


def _kernel_version(files: Mapping[str, str], roles: Mapping[str, RoleAssembly]) -> str:
    """sha1 over every generated kernel byte: the files and each role's strings, in name order."""
    digest = hashlib.sha1(usedforsecurity=False)
    for name in sorted(files):
        digest.update(f"{name}\0{files[name]}\0".encode())
    for name in sorted(roles):
        for string in roles[name].strings:
            digest.update(f"{name}\0{string.module}\0{string.text}\0".encode())
    return digest.hexdigest()


# -- Edge: reading the repository, writing the kernels -----------------------------------


def plan_kernels(root: Path) -> KernelPlan:
    """Everything the generator would write for `root`; refuses sources it cannot trust."""
    definitions = km.agent_definitions(root)
    manifest = km.load_manifest(root, definitions)
    sections = _load_sections(root, manifest)
    _refuse(km.check_totality(manifest, sections, ks.always_loaded_sources(root)))
    kernel = assemble(manifest, sections, _read_authored(root, manifest))
    return compose(kernel, manifest, definitions, _statuses(root, definitions))


def _load_sections(root: Path, manifest: km.Manifest) -> dict[str, tuple[ks.Section, ...]]:
    sources = {*ks.always_loaded_sources(root), *(e.target.source for e in manifest.entries)}
    return {s: ks.load_sections(root, s) for s in sorted(sources) if (root / s).is_file()}


def _refuse(findings: Sequence[km.Finding]) -> None:
    if findings:
        shown = "; ".join(f"{f.kind}: {f.subject} {f.detail}".strip() for f in findings[:5])
        raise KernelPlanError(f"{len(findings)} problem(s) in the sources: {shown}")


def _read_authored(root: Path, manifest: km.Manifest) -> dict[str, str]:
    """Each authored text without its one closing newline."""
    texts = {}
    for text in manifest.authored:
        path = root / text.path
        if not path.is_file():
            raise KernelPlanError(f"authored text {text.id!r}: {text.path} does not exist")
        texts[text.id] = path.read_bytes().decode("utf-8").removesuffix("\n")
    return texts


def _statuses(root: Path, definitions: Mapping[str, str]) -> Mapping[str, str]:
    statuses = km.load_statuses(root)
    unknown = sorted(set(statuses) - set(definitions))
    if unknown:
        raise KernelPlanError(f"the adoption ledger names {unknown[0]!r}, which is no agent")
    return statuses


def stale_files(root: Path, files: Mapping[str, bytes]) -> list[str]:
    """Generated paths whose bytes differ on disk, are missing, or are kernel files nobody makes."""
    stale = [rel for rel, data in files.items() if _on_disk(root / rel) != data]
    return sorted({*stale, *_leftovers(root, files)})


def _on_disk(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _leftovers(root: Path, files: Mapping[str, bytes]) -> list[str]:
    directory = root / KERNELS_DIR
    found = (
        [p.relative_to(root).as_posix() for p in directory.glob("*.md")]
        if directory.is_dir()
        else []
    )
    return [rel for rel in found if rel not in files]


def write_files(root: Path, files: Mapping[str, bytes]) -> list[str]:
    """Write what differs and delete leftover kernel files; the paths touched."""
    touched = stale_files(root, files)
    for rel in touched:
        path = root / rel
        if rel in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(files[rel])
        else:
            path.unlink()
    return touched


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the per-role kernels.")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 when stale")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)
    try:
        root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
        if is_plugin_cache_path(root):
            raise KernelPlanError(f"{root} is an installed-plugin cache: edit the source checkout")
        plan = plan_kernels(root)
        stale = stale_files(root, plan.files) if args.check else write_files(root, plan.files)
    except (
        ValueError,
        km.MissingParserError,
        OSError,
    ) as exc:  # the model's errors are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for rel in stale:
        print(f"{'stale' if args.check else 'wrote'}: {rel}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
