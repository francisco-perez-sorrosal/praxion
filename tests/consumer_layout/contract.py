"""Machine-derived model of the consumer layout `/onboard-project` installs.

Support module for `test_consumer_layout.py`. Nothing here asserts; it parses
`commands/onboard-project.md` into a typed contract and provides a runner that
executes the contract's own shell fragments against a scratch tree.

**Why a parser and not a hand-written list.** A hand-written expectation is an
answer key: it passes because someone transcribed the command correctly once,
and it drifts silently the moment a phase is added. Deriving the phase set, the
write payloads, and the idempotency predicates from the command's own text means
a new phase enters the harness the moment it enters the contract.

**Two extraction surfaces, deliberately kept apart.**

* *Payloads* -- the fenced literal blocks a phase writes into the consumer tree
  (`.gitignore` lines, the `.gitattributes` entry, the `jq` merge, the CLAUDE.md
  block bodies). These are what onboarding *does*.
* *Predicates* -- the shell fragments in the `§Idempotency Predicates` table and
  the phase bodies, which decide whether a phase has already run. These are what
  onboarding *checks*.

The two are written independently in the command and nothing today proves they
agree. Pairing them is the point of this harness.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
ONBOARD_FILE = REPO_ROOT / "commands" / "onboard-project.md"

HAVE_JQ = shutil.which("jq") is not None

# Phase ids as the command writes them: 1, 5b, 8c, 0.5.
_PHASE_ID = r"[0-9]+(?:\.5)?[a-z]?"

# A fragment is a candidate shell command only if it opens with one of these.
# Everything else inside backticks in a predicate cell is a path, a key name, or
# a heading -- not something to run.
_TREE_COMMANDS = ("grep ", "test ", "readlink ", "git config ", "jq ")
_HOST_COMMANDS = ("command -v", "claude plugin", "claude ")


@lru_cache(maxsize=1)
def onboard_text() -> str:
    """Return `commands/onboard-project.md` verbatim."""
    return ONBOARD_FILE.read_text(encoding="utf-8")


def section(heading_pattern: str, text: str | None = None) -> str:
    """Return one `## ` section body, from its heading to the next `## `.

    A fixed heading-to-heading window keeps every downstream match scoped to the
    phase that owns it, so no assertion can pass vacuously against a neighbour.
    """
    body = onboard_text() if text is None else text
    match = re.search(rf"^##\s+{heading_pattern}.*?(?=\n## |\Z)", body, re.DOTALL | re.MULTILINE)
    return match.group(0) if match else ""


def sub_step(heading_pattern: str) -> str:
    """Return one `### Sub-step ...` body, from its heading to the next `### ` or `## `."""
    match = re.search(
        rf"^###\s+{heading_pattern}.*?(?=\n### |\n## |\Z)", onboard_text(), re.DOTALL | re.MULTILINE
    )
    return match.group(0) if match else ""


def _fences(body: str, language: str) -> list[str]:
    return [m.group(1) for m in re.finditer(rf"```{language}\n(.*?)```", body, re.DOTALL)]


def _dedent(block: str) -> str:
    """Strip the uniform indent a fenced block carries when nested under a bullet."""
    lines = [line for line in block.splitlines() if line.strip()]
    if not lines:
        return block
    indent = min(len(line) - len(line.lstrip()) for line in lines)
    return "\n".join(line[indent:] for line in block.splitlines())


# -- Phase inventory ---------------------------------------------------------


def _table_phase_ids(body: str) -> tuple[str, ...]:
    return tuple(re.findall(rf"^\|\s*({_PHASE_ID})\s*\|", body, re.MULTILINE))


def flow_phases() -> tuple[str, ...]:
    """Phase ids declared by the `§Flow` table -- the command's own running order."""
    return _table_phase_ids(section("§Flow"))


def idempotency_phases() -> tuple[str, ...]:
    """Phase ids carrying a row in the `§Idempotency Predicates` table."""
    return _table_phase_ids(section("§Idempotency Predicates"))


def phase_headings() -> tuple[str, ...]:
    """Phase ids that have a `## §Phase N` section of their own."""
    return tuple(re.findall(rf"^## §Phase ({_PHASE_ID}) ", onboard_text(), re.MULTILINE))


# -- Payloads: what a phase writes -------------------------------------------


def ai_state_skeleton() -> tuple[str, ...]:
    """Consumer-relative `.ai-state/` paths the skeleton phase creates.

    Derived from every backticked `.ai-state/...` path in the phase body, minus
    the bare parent directories (implied by their children) and minus the one
    path the phase explicitly forbids creating: the observability WAL, which the
    semantic merge driver expects to be absent until first use.
    """
    body = section(r"§Phase 2 — `\.ai-state/` skeleton")
    found = set(re.findall(r"`(\.ai-state/[A-Za-z0-9_./-]+)`", body))
    forbidden = set(re.findall(r"Do NOT create `(\.ai-state/[A-Za-z0-9_./-]+)`", body))
    parents = {p for p in found if any(o != p and o.startswith(p) for o in found)}
    return tuple(sorted(found - forbidden - parents))


def gitignore_payloads() -> dict[str, str]:
    """Every literal `.gitignore` block onboarding appends, keyed by owning phase.

    Keyed by the *top-level* phase id because that is the grain of the predicate
    table, so a payload joins to its own check without a second mapping.
    """
    return {
        "1": _dedent(_fences(section(r"§Phase 1 "), "gitignore")[0]),
        "8c": _dedent(_fences(sub_step(r"Sub-step 8c\.2"), "gitignore")[0]),
        "8d": _dedent(_fences(sub_step(r"Sub-step 8d\.1"), "gitignore")[0]),
    }


def gitattributes_payload() -> str:
    """The literal `.gitattributes` block the merge-driver phase appends."""
    return _dedent(_fences(section(r"§Phase 3 "), "gitattributes")[0])


def claude_md_blocks() -> dict[str, str]:
    """Each `## §<Name> Block` section's fenced payload, keyed by its own heading.

    The command installs these bodies into the consumer's `CLAUDE.md`; the
    idempotency table then greps for a heading inside them. Key by the heading
    the payload actually carries, so the pairing test compares two independently
    authored texts rather than one text with itself.
    """
    blocks: dict[str, str] = {}
    for match in re.finditer(r"^## §(.+?) Block\b.*?(?=\n## §|\Z)", onboard_text(), re.S | re.M):
        fences = _fences(match.group(0), "markdown")
        if not fences:
            continue
        body = _dedent(fences[0])
        heading = re.search(r"^## .+$", body, re.MULTILINE)
        if heading:
            blocks[heading.group(0)] = body
    return blocks


@dataclass(frozen=True)
class JqPair:
    """A sub-step's idempotency check paired with the merge that satisfies it."""

    name: str
    target: str
    predicate: str
    action: str


def jq_pairs() -> tuple[JqPair, ...]:
    """Sub-steps that document both a `jq` predicate and the `jq` merge behind it."""
    pairs = []
    for name, heading, target in (
        ("permissions.allow baseline", r"Sub-step 5b", ".claude/settings.json"),
        ("permissions.deny baseline", r"Sub-step 8d\.5b", ".claude/settings.json"),
    ):
        body = sub_step(heading)
        blocks = [b.strip() for b in _fences(body, "bash")]
        predicate = next((b for b in blocks if b.startswith("jq -e")), "")
        action = next((b for b in blocks if b.startswith("jq '") or b.startswith('jq "')), "")
        pairs.append(JqPair(name=name, target=target, predicate=predicate, action=action))
    return tuple(pairs)


def plugin_asset_paths() -> tuple[str, ...]:
    """Plugin-side source paths the command reads or copies into a consumer.

    Two unambiguous sources: any path prefixed with a plugin-root shell variable,
    and the brace-expanded list in the code-quality phase's *Asset resolution*
    paragraph, which states outright that those files live in the plugin install.
    Ambiguous bare paths are deliberately excluded -- several name consumer-side
    files with the same shape.
    """
    text = onboard_text()
    found: set[str] = set()

    var = r"(?:\$\{PLUGIN_INSTALL_PATH\}|\$\{PLUGIN_ROOT\}|\$CLAUDE_PLUGIN_ROOT)"
    found.update(re.findall(rf"{var}/([A-Za-z0-9_./-]+)", text))

    resolution = re.search(r"\*\*Asset resolution\.\*\*(.*)", text)
    if resolution:
        for base, names in re.findall(r"`([A-Za-z0-9_./-]+)/\{([^}]+)\}`", resolution.group(1)):
            found.update(f"{base}/{name.strip()}" for name in names.split(","))
    return tuple(sorted(found))


# -- Predicates: what a phase checks -----------------------------------------


@dataclass(frozen=True)
class Predicate:
    """One shell fragment lifted verbatim from the command's predicate prose."""

    phase: str
    snippet: str
    kind: str  # tree | host | elided | templated

    @property
    def label(self) -> str:
        return f"phase {self.phase}: {self.snippet}"


def _classify(snippet: str) -> str | None:
    if snippet.startswith(_HOST_COMMANDS):
        return "host"
    if not snippet.startswith(_TREE_COMMANDS):
        return None
    if re.search(r"<[a-z][a-z-]*>", snippet):
        return "templated"
    if "[...]" in snippet:
        return "elided"
    return "tree"


def predicates() -> tuple[Predicate, ...]:
    """Every shell fragment the `§Idempotency Predicates` table cites, classified.

    Fragments are lifted **verbatim**, backslashes included. A cell's `\\|` is
    ambiguous by construction -- it is both the Markdown escape for a literal
    pipe and a BRE alternation -- and normalising it either way would silently
    rewrite one of the two readings into a fragment the command never wrote.
    """
    out: list[Predicate] = []
    for phase, cell in re.findall(
        rf"^\|\s*({_PHASE_ID})\s*\|(.*)$", section("§Idempotency Predicates"), re.MULTILINE
    ):
        for raw in re.findall(r"`([^`]+)`", cell):
            snippet = raw.strip()
            kind = _classify(snippet)
            if kind:
                out.append(Predicate(phase=phase, snippet=snippet, kind=kind))
    return tuple(out)


def predicate_row(phase: str) -> str:
    """The raw `§Idempotency Predicates` cell for one phase."""
    match = re.search(
        rf"^\|\s*{re.escape(phase)}\s*\|(.*)$", section("§Idempotency Predicates"), re.MULTILINE
    )
    return match.group(1) if match else ""


# -- The runner --------------------------------------------------------------


# The scratch tree must answer for itself, not for the machine running the
# suite. A developer with the merge driver registered at global scope would
# otherwise see the `git config --get` predicate report "already done" on a repo
# that was never onboarded -- a machine-dependent result from a test whose whole
# subject is a tree.
_ISOLATED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _env() -> dict[str, str]:
    return {**os.environ, **_ISOLATED_GIT_ENV}


def bare_repo(root: Path) -> Path:
    """An empty git repo -- a project the instant before onboarding first runs."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=_env(),
    )
    return root


def run_shell(snippet: str, tree: Path) -> subprocess.CompletedProcess[str]:
    """Execute a contract fragment for real, inside a scratch tree.

    Running the literal text is the whole point: a structural test proves the
    command *says* the right thing, and this proves the thing it says *works*.
    """
    return subprocess.run(
        ["bash", "-c", snippet],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=30,
        env=_env(),
    )


def holds(snippet: str, tree: Path) -> bool:
    """True when the fragment reports "already done" for this tree."""
    return run_shell(snippet, tree).returncode == 0


# -- The checks themselves, as plain functions -------------------------------
#
# Each returns its findings rather than asserting, so a canary can drive the
# same function with a known-bad input and prove the check bites.


def table_parity_gaps(declared: tuple[str, ...], predicated: tuple[str, ...]) -> tuple[str, ...]:
    """Phases that run without a row in the per-phase predicate table.

    A phase missing from that table has no stated contract for re-runs -- it
    either rewrites on every invocation or skips one it never performed, and
    which of the two is undiscoverable from the table that claims to say.
    """
    return tuple(sorted(set(declared) - set(predicated)))


def missing_assets(paths: tuple[str, ...], plugin_root: Path) -> tuple[str, ...]:
    """Plugin-side sources the contract reads that are absent from the plugin tree.

    Self-hosting hides this: a path resolves here because this repo *is* the
    plugin, so a source removed or renamed still reads fine from a session
    running inside it, and fails only in a consumer that has no such file.
    """
    return tuple(sorted(p for p in paths if not (plugin_root / p).exists()))


def missing_skeleton_files(paths: tuple[str, ...], tree: Path) -> tuple[str, ...]:
    """Declared skeleton entries the tree does not carry."""
    return tuple(sorted(p for p in paths if not holds(f"test -e {p}", tree)))


def settings_of(tree: Path) -> dict:
    """Parse the consumer's Claude settings file."""
    return json.loads((tree / ".claude" / "settings.json").read_text(encoding="utf-8"))


def seed_settings(tree: Path, content: dict) -> Path:
    """Write a starting `.claude/settings.json` for a merge round trip."""
    path = tree / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")
    return path
