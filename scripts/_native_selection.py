"""Native-ecosystem test-selection adapters.

Every non-Python pocket is handed to its own ecosystem's tool rather than
derived (Praxion derives only where no native tool exists). Two shapes of
adapter exist:

- **self-computing** -- the tool's own flag already walks its dependency
  graph (vitest `related`, jest `--findRelatedTests`, Maven `-pl … -amd`,
  Gradle `buildDependents`, nx `affected --files`, turbo `--affected`, Pants'
  own target resolution). The adapter here is just an argv builder; the
  closure is the tool's job at run time.
- **metadata-driven** -- no such flag exists (cargo, go), so the adapter
  reads the ecosystem's own metadata command (`cargo metadata`, `go list
  -json`) to build the dependency graph itself, then walks it in reverse.

Two known imprecisions, both inherent to the tool rather than this adapter,
and both named in `SYSTEMS_PLAN.md`'s Risk Assessment as accepted (native
adapters are not dogfoodable in Praxion; only vitest runs live): turbo has no
per-file "affected" flag, only a git-based one, so `paths` only confirms the
pocket was touched and turbo re-derives *which* packages itself; Pants
resolves each path to its owning target directly, which is precise but not
transitive-dependents-complete (that needs `--changed-since`'s git ref, not
a path list).

Bazel and any other unrecognized framework have no adapter at all and always
widen with `no-adapter`; the `rdeps` recipe is documented for a human to run
by hand. A recognized framework whose tool is missing from `PATH` widens with
`tool-unavailable` instead of raising -- exactly like an unmapped Python path,
a native pocket the resolver cannot account for runs in full, never in
silence.

Contract: `skills/testing-strategy/references/test-selection.md`.
Stdlib-only: it runs under a bare `python3` (gate-liveness GL05).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REASON_TOOL_UNAVAILABLE = "tool-unavailable"
REASON_NO_ADAPTER = "no-adapter"


@dataclass(frozen=True)
class Selected:
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Widen:
    reason: str
    detail: str


Native = Selected | Widen

# The tool each framework's adapter shells out to. A framework absent here
# (e.g. "unknown", "bazel") has no adapter at all -- `select()` widens with
# `no-adapter` before ever checking for a tool.
_TOOL_BY_FRAMEWORK: dict[str, str] = {
    "vitest": "vitest",
    "jest": "jest",
    "cargo": "cargo",
    "go": "go",
    "maven": "mvn",
    "gradle": "gradle",
    "nx": "nx",
    "turbo": "turbo",
    "pants": "pants",
}


def _top_segment(path: str) -> str:
    """The first path segment (a monorepo module/project directory), or `""` at the root."""
    return path.split("/", 1)[0] if "/" in path else ""


def _dirname(path: str) -> str:
    """The directory containing `path`, or `""` at the pocket root."""
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _under(path: str, directory: str) -> bool:
    return directory in ("", ".") or path == directory or path.startswith(directory + "/")


def _tool_available(tool: str, pocket_dir: Path) -> bool:
    """Is `tool` reachable -- globally on `PATH`, or as a local npm dev dependency?

    A project's own devDependency binaries (vitest, jest, nx, turbo) live at
    `<pocket>/node_modules/.bin/<tool>` and are run through a package-manager
    wrapper (`pnpm exec`, `npx`), never installed on the global `PATH` -- a
    `PATH`-only check reports every ordinary npm project as `tool-unavailable`
    and permanently widens it, which is precisely the pocket this adapter
    family exists to select narrowly.
    """
    return shutil.which(tool) is not None or (pocket_dir / "node_modules" / ".bin" / tool).is_file()


def _run_text(argv: Sequence[str], cwd: Path) -> str | None:
    """`argv`'s stdout, or None on any failure -- the caller turns that into a widen."""
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def _json_objects(text: str) -> list[dict]:
    """Concatenated JSON objects with no separator -- `go list -json`'s own shape."""
    decoder, items, index, text = json.JSONDecoder(), [], 0, text.strip()
    while index < len(text):
        obj, end = decoder.raw_decode(text, index)
        items.append(obj)
        index = end
        while index < len(text) and text[index].isspace():
            index += 1
    return items


def _reverse_closure(edges: dict[str, list[str]], seed: set[str]) -> set[str]:
    """Every node that transitively depends on a seed node, seeds included."""
    reverse: dict[str, list[str]] = {}
    for node, deps in edges.items():
        for dep in deps:
            reverse.setdefault(dep, []).append(node)
    closure, frontier = set(seed), list(seed)
    while frontier:
        for dependent in reverse.get(frontier.pop(), ()):
            if dependent not in closure:
                closure.add(dependent)
                frontier.append(dependent)
    return closure


# --- Self-computing adapters: the tool's own flag walks its dependency graph ---


def _vitest(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    return Selected((*prefix, "vitest", "related", *paths, "--run"))


def _jest(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    return Selected((*prefix, "jest", "--findRelatedTests", *paths))


def _maven(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    modules = sorted({_top_segment(path) or "." for path in paths})
    return Selected((*prefix, "mvn", "test", "-pl", ",".join(modules), "-amd"))


def _gradle(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    projects = sorted({f":{segment}" if (segment := _top_segment(path)) else "" for path in paths})
    tasks = tuple(
        f"{project}:buildDependents" if project else "buildDependents" for project in projects
    )
    return Selected((*prefix, "gradle", *tasks))


def _nx(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    return Selected((*prefix, "nx", "affected", "--target=test", f"--files={','.join(paths)}"))


def _turbo(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    return Selected((*prefix, "turbo", "run", "test", "--affected"))


def _pants(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    return Selected((*prefix, "pants", "test", *paths))


# --- Metadata-driven adapters: no such flag exists, so read the graph ourselves ---


def _cargo(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    metadata_text = _run_text((*prefix, "cargo", "metadata", "--format-version", "1"), pocket_dir)
    if metadata_text is None:
        return Widen(REASON_TOOL_UNAVAILABLE, "`cargo metadata` failed")
    metadata = json.loads(metadata_text)
    workspace = set(metadata.get("workspace_members", []))
    crate_dir = {
        pkg["id"]: Path(pkg["manifest_path"]).parent.resolve().relative_to(pocket_dir).as_posix()
        for pkg in metadata.get("packages", [])
        if pkg["id"] in workspace
    }
    seed = {
        crate for crate, directory in crate_dir.items() if any(_under(p, directory) for p in paths)
    }
    edges = {
        node["id"]: node.get("dependencies", [])
        for node in metadata.get("resolve", {}).get("nodes", [])
    }
    affected = _reverse_closure(edges, seed)
    names = sorted(pkg["name"] for pkg in metadata["packages"] if pkg["id"] in affected)
    return Selected((*prefix, "cargo", "test", *(flag for name in names for flag in ("-p", name))))


def _go(pocket_dir: Path, prefix: tuple[str, ...], paths: tuple[str, ...]) -> Native:
    listing = _run_text((*prefix, "go", "list", "-json", "./..."), pocket_dir)
    if listing is None:
        return Widen(REASON_TOOL_UNAVAILABLE, "`go list` failed")
    packages = {
        pkg["ImportPath"]: {
            "dir": Path(pkg["Dir"]).resolve().relative_to(pocket_dir).as_posix(),
            "deps": set(pkg.get("Deps", ())),
        }
        for pkg in _json_objects(listing)
        if "ImportPath" in pkg and "Dir" in pkg
    }
    seed = {path for path, pkg in packages.items() if any(_dirname(p) == pkg["dir"] for p in paths)}
    # `Deps` is already the full transitive closure, so one pass finds every dependent.
    affected = seed | {path for path, pkg in packages.items() if pkg["deps"] & seed}
    return Selected((*prefix, "go", "test", *sorted(affected)))


_BUILDERS: dict[str, Callable[[Path, tuple[str, ...], tuple[str, ...]], Native]] = {
    "vitest": _vitest,
    "jest": _jest,
    "cargo": _cargo,
    "go": _go,
    "maven": _maven,
    "gradle": _gradle,
    "nx": _nx,
    "turbo": _turbo,
    "pants": _pants,
}

# The `adapter` values the schema-2 payload names for a native pocket -- exposed so the
# resolver can report which framework actually served a selection, not just
# "none" for every non-Python pocket.
ADAPTERS = frozenset(_BUILDERS)


def select(
    framework: str, pocket_dir: Path, runner_prefix: Sequence[str], paths: Sequence[str]
) -> Native:
    """`framework`'s own tool over `paths` (pocket-relative), run from `pocket_dir`."""
    builder = _BUILDERS.get(framework)
    if builder is None:
        return Widen(REASON_NO_ADAPTER, f"no selection adapter for the {framework} framework")
    tool = _TOOL_BY_FRAMEWORK[framework]
    if not _tool_available(tool, pocket_dir):
        return Widen(REASON_TOOL_UNAVAILABLE, f"{tool!r} is not on PATH")
    return builder(pocket_dir, tuple(runner_prefix), tuple(paths))
