"""Target checkout → a read-only copy whose context layer the sessions load.

A materialization is a runner-owned copy of the target (a git ref's tree, or a
working tree's tracked and unignored files). Sessions receive it through
``--plugin-dir`` and a per-session sandbox populated by the copy's *own*
install primitives, so the measured layer is exactly the target's — never a
re-implementation of the installer, never the operator's ``~/.claude``.

The canary variant differs from HEAD by one pre-registered degradation, and a
missing section aborts the build rather than yielding an undegraded canary.
Nonce planting proves, before any scenario runs, that a session built this
way really loads the copy's global CLAUDE.md, rules, agents and hook-delivered
rules.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from praxion_evals.live.session import SandboxPaths

Variant = Literal["head", "canary"]

CANARY_FILE = "rules/swe/swe-agent-coordination-protocol.md"
CANARY_HEADING = "### Process Calibration"
SECTION_PREFIX = "### "

GLOBAL_TEMPLATE = "claude/config/CLAUDE.md.tmpl"
PLUGIN_AGENT = "agents/researcher.md"
HOOK_DELIVERED_RULE = "rules/swe/agent-model-routing.md"
MARKER_PREFIX = "PRXLIVE"
NONCE_BYTES = 4

_RENDER_SCRIPT = "scripts/render_claude_md.py"
_LINK_RULES = 'source "$1/lib/install_shared.sh" && link_rules "$1/rules" "$2"'
_FRONTMATTER_FENCE = "---"
_DESCRIPTION_KEY = "description:"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefTarget:
    ref: str
    sha: str


@dataclass(frozen=True)
class PathTarget:
    path: str
    head_sha: str
    dirty: bool


TargetIdentity = RefTarget | PathTarget


@dataclass(frozen=True)
class Degradation:
    file: str
    heading: str
    removed_bytes: int
    sha256_before: str
    sha256_after: str

    def __post_init__(self) -> None:
        if self.removed_bytes <= 0:
            raise ValueError(f"degradation of {self.file} removed nothing")


@dataclass(frozen=True)
class Materialization:
    variant: Variant
    root: Path
    target: TargetIdentity
    degradation: Degradation | None
    tree_digest: str

    def __post_init__(self) -> None:
        if (self.variant == "canary") != (self.degradation is not None):
            raise ValueError("a canary materialization, and only a canary, carries a degradation")


@dataclass(frozen=True)
class NoncePlant:
    """Fresh 32-bit nonces, one per context surface a preflight must prove loaded."""

    global_claude_md: str
    coordination_rule: str
    plugin_agent: str
    hook_delivered_rule: str

    def markers(self) -> dict[str, str]:
        return {
            "global_claude_md": _marker("GLOBAL", self.global_claude_md),
            "coordination_rule": _marker("RULE", self.coordination_rule),
            "plugin_agent": _marker("AGENT", self.plugin_agent),
            "hook_delivered_rule": _marker("HOOKRULE", self.hook_delivered_rule),
        }

    def missing_from(self, text: str) -> tuple[str, ...]:
        """Surfaces whose marker a preflight answer failed to echo."""
        return tuple(surface for surface, marker in self.markers().items() if marker not in text)


def _marker(surface: str, nonce: str) -> str:
    return f"{MARKER_PREFIX}-{surface}-{nonce}"


# ---------------------------------------------------------------------------
# Building a copy
# ---------------------------------------------------------------------------


def materialize_head(repo_root: Path, dest: Path, variant: Variant = "head") -> Materialization:
    return materialize_ref(repo_root, "HEAD", dest, variant)


def materialize_ref(
    repo_root: Path, ref: str, dest: Path, variant: Variant = "head"
) -> Materialization:
    """Extract ``ref``'s committed tree into ``dest`` (which must not exist yet)."""
    sha = _git(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    dest.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", sha],
        capture_output=True,
        check=True,
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return _finish(dest, variant, RefTarget(ref=ref, sha=sha))


def materialize_path(source: Path, dest: Path, variant: Variant = "head") -> Materialization:
    """Copy a working tree's tracked and unignored files into ``dest``."""
    listing = _git(source, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    dest.mkdir(parents=True)
    for relpath in sorted(set(filter(None, listing.split("\0")))):
        _copy_entry(source / relpath, dest / relpath)
    target = PathTarget(
        path=str(source.resolve()),
        head_sha=_git(source, "rev-parse", "HEAD").strip(),
        dirty=bool(_git(source, "status", "--porcelain").strip()),
    )
    return _finish(dest, variant, target)


def _finish(dest: Path, variant: Variant, target: TargetIdentity) -> Materialization:
    root = dest.resolve()  # sessions report real paths; isolation checks compare against this
    degradation = _degrade(root, CANARY_FILE, CANARY_HEADING) if variant == "canary" else None
    digest = tree_digest(root)
    # A `--add-dir` grant lets a session edit files under the copy; making
    # the copy read-only on disk is the actual enforcement point for "the
    # materialization is not mutated" — a permission grant cannot override a
    # filesystem permission. Callers that must write into a fresh copy
    # (nonce planting) restore write access first via `make_writable`.
    make_read_only(root)
    return Materialization(
        variant=variant, root=root, target=target, degradation=degradation, tree_digest=digest
    )


def make_read_only(root: Path) -> None:
    _set_tree_writable(root, writable=False)


def make_writable(root: Path) -> None:
    _set_tree_writable(root, writable=True)


def _set_tree_writable(root: Path, *, writable: bool) -> None:
    for path in (root, *root.rglob("*")):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode | 0o200 if writable else mode & ~0o222)


def _copy_entry(source: Path, dest: Path) -> None:
    if source.is_symlink():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(os.readlink(source))
    elif source.is_file():  # deleted-but-tracked files and submodule dirs are skipped
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


def _degrade(root: Path, relpath: str, heading: str) -> Degradation:
    path = root / relpath
    before = path.read_bytes()
    degraded, removed_bytes = remove_section(before.decode("utf-8"), heading)
    after = degraded.encode("utf-8")
    path.write_bytes(after)
    return Degradation(
        file=relpath,
        heading=heading,
        removed_bytes=removed_bytes,
        sha256_before=hashlib.sha256(before).hexdigest(),
        sha256_after=hashlib.sha256(after).hexdigest(),
    )


def remove_section(text: str, heading: str) -> tuple[str, int]:
    """Drop ``heading`` through the line before the next ``### `` heading (or EOF).

    Only same-level headings bound the section, so an intervening ``## `` goes
    with it. Raises ``ValueError`` when the heading is absent: a renamed section
    must abort the canary, never silently yield an undegraded copy.
    """
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.rstrip() == heading), None)
    if start is None:
        raise ValueError(f"section {heading!r} not found")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith(SECTION_PREFIX)),
        len(lines),
    )
    removed = "".join(lines[start:end])
    return "".join(lines[:start] + lines[end:]), len(removed.encode("utf-8"))


def tree_digest(root: Path) -> str:
    """Content hash of the tree — paths, entry kinds and bytes; never mtimes."""
    digest = hashlib.sha256()
    entries = (p for p in root.rglob("*") if p.is_symlink() or p.is_file())
    for relpath, path in sorted((p.relative_to(root).as_posix(), p) for p in entries):
        kind, payload = (
            ("link", os.readlink(path).encode())
            if path.is_symlink()
            else ("file", path.read_bytes())
        )
        digest.update(f"{relpath}\0{kind}\0{hashlib.sha256(payload).hexdigest()}\n".encode())
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Nonce planting (preflight copies only)
# ---------------------------------------------------------------------------


def plant_nonces(copy_root: Path, rule_relpath: str) -> NoncePlant:
    """Plant one fresh marker in each surface; ``rule_relpath`` is the rule under test."""
    plant = NoncePlant(*(secrets.token_hex(NONCE_BYTES) for _ in range(4)))
    markers = plant.markers()
    _append_marker(copy_root / GLOBAL_TEMPLATE, markers["global_claude_md"])
    _append_marker(copy_root / rule_relpath, markers["coordination_rule"])
    _plant_in_description(copy_root / PLUGIN_AGENT, markers["plugin_agent"])
    _append_marker(copy_root / HOOK_DELIVERED_RULE, markers["hook_delivered_rule"])
    return plant


def _append_marker(path: Path, marker: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + f"\n\n{marker}\n", encoding="utf-8")


def _plant_in_description(path: Path, marker: str) -> None:
    """Agent bodies never reach the top-level session; only the description does."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].rstrip() != _FRONTMATTER_FENCE:
        raise ValueError(f"{path} has no frontmatter to carry a description marker")
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].rstrip() == _FRONTMATTER_FENCE), None
    )
    if closing is None:
        raise ValueError(f"{path} has an unterminated frontmatter block")
    description = next(
        (i for i in range(1, closing) if lines[i].startswith(_DESCRIPTION_KEY)), None
    )
    if description is None:
        lines.insert(1, f"{_DESCRIPTION_KEY} {marker}\n")
    else:
        lines.insert(description + 1, f"  {marker}\n")  # continuation line of the scalar
    path.write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# User-scope install into a session sandbox
# ---------------------------------------------------------------------------


def install_user_scope(materialization_root: Path, sandbox_root: Path) -> None:
    """Populate a sandbox HOME the way the copy's own installer populates ``~/.claude``.

    The global CLAUDE.md is rendered by the copy's renderer and rules are linked
    by the copy's manifest-driven ``link_rules`` (hook-delivered rules are left
    for the copy's hook). Every write lands under ``sandbox_root``.
    """
    paths = SandboxPaths(sandbox_root)
    paths.config_dir.mkdir(parents=True)
    paths.tmp.mkdir(parents=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run(
        [
            sys.executable,
            str(materialization_root / _RENDER_SCRIPT),
            str(materialization_root / GLOBAL_TEMPLATE),
            str(paths.config_dir / "CLAUDE.md"),
        ],
        cwd=sandbox_root,  # outside any repo: the renderer reads only global git identity
        env=env,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            "bash",
            "-c",
            _LINK_RULES,
            "_",
            str(materialization_root),
            str(paths.config_dir / "rules"),
        ],
        cwd=sandbox_root,
        env=env,
        capture_output=True,
        check=True,
    )
    (paths.config_dir / "settings.json").write_text("{}\n", encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout
