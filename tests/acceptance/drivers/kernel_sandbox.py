"""Driver for the kernel surfaces of a plugin checkout, reached from outside.

A scenario works on a sandbox: a copy of this checkout's files (tracked, plus
untracked files git does not ignore, minus the trees no kernel surface reads) in a
git repository of its own, so a scenario may edit rules, agent definitions or the
audience manifest without touching this checkout. A module builds one template per
worker and every scenario copies it.

Bound here, because the specification or the base commit fixes them:

- the kernel generator is run as `python3 scripts/generate_kernels.py` from the
  checkout root with no arguments ("a maintainer runs `scripts/generate_kernels.py`");
- the commit gate is what `.pre-commit-config.yaml` registers. A gate run executes
  every local hook whose entry names one of the gate scripts, the way
  `pre-commit run --all-files` would (the entry and its args, plus the matching
  files unless `pass_filenames` is false), after staging every change. A commit
  is refused when any of them exits non-zero. The kernel gates are the hooks naming
  `check_kernel_manifest.py` or `generate_kernels.py`, and at least one must name
  the manifest checker;
- the committed kernels are `claude/kernels/*.md`. A module's text is its file
  `<module>.md` or, above the size cap, its numbered parts concatenated in number
  order. Module names are the specification's names in kebab case (provisional:
  the specification names the modules but not their files);
- the shared-block gate's existing `--json` report and `--print-canonical SLUG`;
- the Codex exporter's `--repo-root/--out-dir` and the Cursor exporter's two
  positional arguments (repository root, output directory).

Isolation: every process runs with its own HOME, a `python3`/`python` on PATH that
is this suite's interpreter, and no inherited `CLAUDE*`, `PRAXION_*`, `GIT_*` or
`ANTHROPIC_*` variables, so no gate can reach a tokenizer API or the user's files.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

GENERATOR = "scripts/generate_kernels.py"
MANIFEST_CHECKER = "check_kernel_manifest.py"
KERNEL_GATE_SCRIPTS = (MANIFEST_CHECKER, "generate_kernels.py")
SHARED_BLOCKS_GATE = "check_agent_shared_blocks.py"
KERNELS_DIR = "claude/kernels"
AUDIENCE_MANIFEST = "rules/_audience.yaml"
ADOPTION_LEDGER = ".ai-state/kernel_adoption.yaml"
CONTRACT_RULE = "rules/swe/agent-behavioral-contract.md"
USER_TEMPLATE = "claude/config/CLAUDE.md.tmpl"
PROJECT_INSTRUCTIONS = "CLAUDE.md"

INJECTION_CAP = 10_000
PLUGIN_TOKEN = "<plugin-root>"
PLUGIN_ROOT_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"

UNIVERSAL_BLOCKS = ("behavioral-contract", "praxion-links", "return-contract")
PILOT_ROLES = (
    "researcher",
    "verifier",
    "discipline-consultant",
    "skill-genesis",
    "context-engineer",
)

# Trees no kernel surface reads; leaving them out keeps a sandbox copy fast.
_SKIPPED_TREES = (
    "tests",
    "dashboard_app",
    "eval",
    "evals",
    "task-chronograph-mcp",
    "fitness",
    ".obsidian",
    ".github",
)
_IDENTITY = (
    "-c",
    "user.name=Kernel Acceptance",
    "-c",
    "user.email=kernel-acceptance@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


class UnboundDriverError(NotImplementedError):
    """Raised by a driver hook not yet bound to the designed surface."""


# -- Processes -----------------------------------------------------------------


def isolated_env(scratch: Path, **extra: str) -> dict[str, str]:
    """An environment that reaches nothing outside `scratch` and this interpreter."""
    home = scratch / "home"
    shims = scratch / "bin"
    home.mkdir(parents=True, exist_ok=True)
    shims.mkdir(parents=True, exist_ok=True)
    for name in ("python3", "python"):
        shim = shims / name
        if not shim.exists():
            shim.symlink_to(sys.executable)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_"))
    }
    env.update(
        HOME=str(home),
        PATH=f"{shims}{os.pathsep}{env.get('PATH', '')}",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=str(home / ".gitconfig"),
        GIT_TERMINAL_PROMPT="0",
        PRAXION_DISABLE_EVENT_POSTING="1",
        PRAXION_DISABLE_AUTO_COMPLETE="1",
        PRAXION_DISABLE_SIDECAR_AUTOCOMMIT="1",
    )
    env.update(extra)
    return env


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    output: str


def _run(argv: list[str], cwd: Path, env: dict[str, str], timeout: int = 300) -> RunResult:
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    return RunResult(proc.returncode, proc.stdout + proc.stderr)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *_IDENTITY, *args],
        cwd=root,
        env=isolated_env(root.parent / f".{root.name}-git"),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return proc.stdout


# -- Sandboxes -----------------------------------------------------------------


def _in_sandbox(rel: str) -> bool:
    path = REPO_ROOT / rel
    return (
        bool(rel)
        and rel.split("/", 1)[0] not in _SKIPPED_TREES
        and (path.is_file() or path.is_symlink())
    )


def _checkout_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split("\0")
    return sorted(rel for rel in set(listed) if _in_sandbox(rel))


def build_template(dest: Path) -> Path:
    """A copy of this checkout's files in a fresh git repository with one commit."""
    dest.mkdir(parents=True, exist_ok=True)
    for rel in _checkout_files():
        source = REPO_ROOT / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, target)
    _git(dest, "init", "-q")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "--no-verify", "-m", "plugin checkout under test")
    return dest


@dataclass(frozen=True)
class Sandbox:
    """A plugin checkout a scenario may change freely."""

    root: Path

    @property
    def scratch(self) -> Path:
        path = self.root.parent / f".{self.root.name}-scratch"
        path.mkdir(exist_ok=True)
        return path

    def path(self, rel: str) -> Path:
        return self.root / rel

    def read(self, rel: str) -> str:
        return self.path(rel).read_text(encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        target = self.path(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def replace(self, rel: str, old: str, new: str) -> None:
        text = self.read(rel)
        assert old in text, f"{rel} no longer contains {old!r}; the scenario's edit has no target"
        self.write(rel, text.replace(old, new, 1))

    def append(self, rel: str, text: str) -> None:
        current = self.read(rel)
        self.write(rel, current.rstrip("\n") + "\n\n" + text.strip("\n") + "\n")

    def delete(self, rel: str) -> None:
        self.path(rel).unlink()


def new_sandbox(template: Path, dest: Path) -> Sandbox:
    shutil.copytree(template, dest, symlinks=True)
    return Sandbox(dest)


# -- The kernel generator and the commit gate ------------------------------------


def generate_kernels(root: Path) -> RunResult:
    """Run the kernel generator the way a maintainer does."""
    assert (root / GENERATOR).is_file(), f"there is no kernel generator at {GENERATOR}"
    scratch = root.parent / f".{root.name}-generator"
    return _run([sys.executable, GENERATOR], root, isolated_env(scratch))


def regenerate(root: Path) -> None:
    result = generate_kernels(root)
    assert result.exit_code == 0, f"the kernel generator failed:\n{result.output}"


@dataclass(frozen=True)
class GateVerdict:
    refused: bool
    output: str
    hooks_run: tuple[str, ...]


def _local_hooks(root: Path) -> list[dict]:
    config = yaml.safe_load((root / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    return [hook for repo in config.get("repos", []) for hook in repo.get("hooks", [])]


def _tracked(root: Path) -> list[str]:
    return [p for p in _git(root, "ls-files", "-z").split("\0") if p]


def _hook_files(hook: dict, tracked: list[str]) -> list[str]:
    files = re.compile(hook.get("files", ""))
    exclude = re.compile(hook["exclude"]) if hook.get("exclude") else None
    return [f for f in tracked if files.search(f) and not (exclude and exclude.search(f))]


def commit_gate(root: Path, scripts: tuple[str, ...] = KERNEL_GATE_SCRIPTS) -> GateVerdict:
    """Stage every change and run the registered commit-gate hooks naming `scripts`."""
    _git(root, "add", "-A")
    hooks = [h for h in _local_hooks(root) if any(s in h.get("entry", "") for s in scripts)]
    assert any(scripts[0] in h.get("entry", "") for h in hooks), (
        f"no commit gate in .pre-commit-config.yaml runs {scripts[0]}"
    )
    tracked = _tracked(root)
    env = isolated_env(root.parent / f".{root.name}-gate")
    refused = False
    output = []
    ran = []
    for hook in hooks:
        matched = _hook_files(hook, tracked)
        if not matched and not hook.get("always_run", False):
            continue
        argv = shlex.split(hook["entry"]) + list(hook.get("args", []))
        if hook.get("pass_filenames", True):
            argv += matched
        result = _run(argv, root, env)
        ran.append(hook["entry"])
        refused = refused or result.exit_code != 0
        output.append(f"$ {hook['entry']} -> exit {result.exit_code}\n{result.output}")
    return GateVerdict(refused, "\n".join(output), tuple(ran))


def shared_blocks_gate(root: Path) -> GateVerdict:
    return commit_gate(root, (SHARED_BLOCKS_GATE,))


def universal_block_carriers(root: Path) -> tuple[int, dict[str, int]]:
    """(agent definitions, carriers per universal block) from the shared-block report."""
    result = _run(
        [sys.executable, f"scripts/{SHARED_BLOCKS_GATE}", "--json", "--repo-root", "."],
        root,
        isolated_env(root.parent / f".{root.name}-blocks"),
    )
    report = json.loads(result.output[result.output.index("{") :])
    carriers = {slug: b["carriers"] for slug, b in report["blocks"].items() if b["universal"]}
    return report["definitions"], carriers


def canonical_block(root: Path, slug: str) -> str:
    result = _run(
        [sys.executable, f"scripts/{SHARED_BLOCKS_GATE}", "--print-canonical", slug],
        root,
        isolated_env(root.parent / f".{root.name}-blocks"),
    )
    assert result.exit_code == 0, f"no canonical text for the {slug} block:\n{result.output}"
    return result.output.strip("\n")


# -- Committed kernels -----------------------------------------------------------


def kernel_files(root: Path) -> dict[str, str]:
    """Every committed kernel file, by name; at least one must exist."""
    directory = root / KERNELS_DIR
    files = sorted(directory.glob("*.md")) if directory.is_dir() else []
    assert files, f"no committed kernel files under {KERNELS_DIR}/"
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def _part_number(stem: str, module: str) -> int | None:
    if stem == module:
        return 0
    match = re.fullmatch(rf"{re.escape(module)}[-_.](?:part[-_]?)?(\d+)", stem)
    return int(match.group(1)) if match else None


def module_parts(root: Path, module: str) -> list[str]:
    """A module's committed text, one entry per file, in part order."""
    numbered = []
    for name, text in kernel_files(root).items():
        number = _part_number(name.removesuffix(".md"), module)
        if number is not None:
            numbered.append((number, text))
    assert numbered, f"no committed kernel file for the {module} module under {KERNELS_DIR}/"
    return [text for _, text in sorted(numbered)]


def module_text(root: Path, module: str) -> str:
    return "".join(module_parts(root, module))


def all_kernel_text(root: Path) -> str:
    return "\n\n".join(kernel_files(root).values())


# -- Text --------------------------------------------------------------------------


def normalize_plugin_location(text: str, plugin_root: Path) -> str:
    """The text with the plugin location, written out or as the variable, made one token."""
    for written in sorted({str(plugin_root), str(plugin_root.resolve())}, key=len, reverse=True):
        text = text.replace(written, PLUGIN_TOKEN)
    return text.replace(PLUGIN_ROOT_VARIABLE, PLUGIN_TOKEN)


def paragraphs(text: str, *, shortest: int = 24) -> list[str]:
    """The blank-line-separated blocks of `text` long enough to identify their source."""
    blocks = (b.strip() for b in re.split(r"\n\s*\n", text))
    return [b for b in blocks if len(b) >= shortest]


def missing_paragraphs(expected_from: str, within: str) -> list[str]:
    return [p for p in paragraphs(expected_from) if p not in within]


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    body: str


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def markdown_sections(text: str) -> list[Section]:
    """Every heading's own text (up to the next heading of any level), outside fences."""
    sections: list[Section] = []
    heading, level, body, fenced = None, 0, [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        match = None if fenced else _HEADING.match(line)
        if match:
            if heading is not None:
                sections.append(Section(heading, level, "\n".join(body)))
            heading, level, body = match.group(2), len(match.group(1)), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append(Section(heading, level, "\n".join(body)))
    return sections


def section_body(text: str, heading: str) -> str:
    found = [s.body for s in markdown_sections(text) if s.heading == heading]
    assert found, f"no section headed {heading!r}"
    return found[0]


def frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.index("\n---", 4)
    return yaml.safe_load(text[4:end]) or {}


# -- Agent definitions ---------------------------------------------------------------


def agent_path(name: str) -> str:
    return f"agents/{name}.md"


def agent_names(root: Path) -> list[str]:
    return sorted(
        p.stem for p in (root / "agents").glob("*.md") if frontmatter(p.read_text()).get("name")
    )


def set_frontmatter_key(sandbox: Sandbox, agent: str, line: str) -> None:
    """Add `line` to an agent definition's frontmatter, right after its `name:` line."""
    rel = agent_path(agent)
    text = sandbox.read(rel)
    name_line = next(ln for ln in text.splitlines() if ln.startswith("name:"))
    sandbox.replace(rel, name_line + "\n", f"{name_line}\n{line}\n")


def copy_agent(sandbox: Sandbox, source: str, new_name: str) -> None:
    """A new agent definition: `source`'s text under a new name."""
    text = sandbox.read(agent_path(source)).replace(f"name: {source}\n", f"name: {new_name}\n", 1)
    sandbox.write(agent_path(new_name), text)


# -- Exporters -------------------------------------------------------------------------


def export_codex(root: Path, out_dir: Path) -> dict[str, str]:
    result = _run(
        [
            sys.executable,
            "codex/config/export-codex-agents.py",
            "--repo-root",
            str(root),
            "--out-dir",
            str(out_dir),
        ],
        root,
        isolated_env(out_dir.parent / f".{out_dir.name}-env"),
    )
    assert result.exit_code == 0, f"the Codex export failed:\n{result.output}"
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(out_dir.glob("*.toml"))}


def codex_instructions(wrapper: str) -> str:
    return tomllib.loads(wrapper)["developer_instructions"]


def export_cursor(root: Path, out_dir: Path) -> dict[str, bytes]:
    result = _run(
        [sys.executable, "cursor/config/export-cursor-rules.py", str(root), str(out_dir)],
        root,
        isolated_env(out_dir.parent / f".{out_dir.name}-env"),
    )
    assert result.exit_code == 0, f"the Cursor export failed:\n{result.output}"
    return {
        str(p.relative_to(out_dir)): p.read_bytes()
        for p in sorted(out_dir.rglob("*"))
        if p.is_file()
    }
