"""Driver for a plugin update: a scratch machine, its plugin cache, and a version's first session.

The system is reached only through its public entry points: the plugin's session-start completion
(`hooks/auto_complete_install.py`, run from a version's directory with `HOME` and
`CLAUDE_PLUGIN_ROOT` set, as Claude Code runs a plugin hook), the clone installer
(`bash install.sh --relink`), and the files a user sees: `~/.claude/CLAUDE.md`, `~/.local/bin`
and `~/.claude/rules`.

A version's directory holds real copies of this checkout's shipped tree (its tracked and
untracked files, less the trees a plugin run never reads), so nothing under the cache links out
of it. "A script V offers" and "a rule V links" are what a fresh install of V links: the same
completion, run in a HOME that holds nothing but a git identity. An update from N is modelled as
N's own first session, time passing, then N+1 arriving in the cache beside N and being registered.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE = Path(".claude/plugins/cache/bit-agora/praxion")
TEMPLATE = "claude/config/CLAUDE.md.tmpl"
RENDER = "claude/config/CLAUDE.md"
SAVED_VALUES = "claude/config/.personal_info.env"
HOOK = "hooks/auto_complete_install.py"
NOT_SHIPPED = (
    ".ai-state", ".ai-work", ".claude", ".github", ".obsidian", "codex", "cursor", "dashboard_app",
    "docs", "eval", "evals", "fitness", "task-chronograph-mcp", "tests",
)  # fmt: skip
OLDER, BEFORE, AFTER = "0.9.0", "1.0.0", "1.1.0"
DAY = 24 * 3600
SESSION_START_PAYLOAD = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})


@dataclass(frozen=True)
class Identity:
    name: str
    email: str


FIRST = Identity("Quentin Placeholder", "quentin.placeholder@example.invalid")
LATER = Identity("Rosalind Standin", "rosalind.standin@example.invalid")


# -- Trees ----------------------------------------------------------------------------------------


def checkout_files(root: Path = REPO_ROOT) -> list[str]:
    """This working tree's tracked and untracked (not ignored) files, read from its index."""
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    ).stdout  # fmt: skip
    return [p for p in out.decode().split("\0") if p]


def copy_files(files: list[str], src: Path, dest: Path) -> Path:
    for rel in files:
        source = src / rel
        if not source.exists():
            continue  # deleted in the working tree
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return dest


def shipped_tree(dest: Path) -> Path:
    """A copy of what a version of the plugin ships, from this working tree."""
    files = [f for f in checkout_files() if f.split("/", 1)[0] not in NOT_SHIPPED]
    return copy_files(files, REPO_ROOT, dest)


def as_git_repository(path: Path) -> Path:
    """Commit `path` as a repository of its own, as a clone checkout is."""
    git = ["git", "-c", "user.name=Stand In", "-c", "user.email=stand.in@example.invalid",
           "-c", "commit.gpgsign=false"]  # fmt: skip
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "--no-verify", "-m", "stand-in"]):
        subprocess.run([*git, *args], cwd=path, check=True, capture_output=True)
    return path


def edited_template(tree: Path, edit) -> Path:
    path = tree / TEMPLATE
    path.write_text(edit(path.read_text(encoding="utf-8")), encoding="utf-8")
    return tree


def with_release_notes(text: str) -> str:
    """A release's template change: a new section that also uses a placeholder."""
    return text + "\n## Release Notes\n\n- This release greets `{{USERNAME}}` by name.\n"


def without_github_line(text: str) -> str:
    """An earlier template that had no place for the GitHub URL."""
    return "".join(line for line in text.splitlines(keepends=True) if "{{GITHUB_URL}}" not in line)


# -- The instructions template --------------------------------------------------------------------


def render(template: str, values: dict[str, str]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)


def values_in(rendered: str, template: str) -> dict[str, str]:
    """The value a render carries for each placeholder, read by lining it up with its template."""
    values = {}
    for t_line, r_line in zip(template.splitlines(), rendered.splitlines(), strict=False):
        match = re.fullmatch(r"(.*?)\{\{(\w+)\}\}(.*)", t_line)
        if match and t_line.count("{{") == 1:
            pre, name, post = match.groups()
            if r_line.startswith(pre) and r_line.endswith(post) and len(r_line) >= len(pre + post):
                values[name] = r_line[len(pre) : len(r_line) - len(post)]
    return values


# -- A machine ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    exit_code: int | None
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool

    @property
    def lines(self) -> list[str]:
        return [line for line in (self.stdout + "\n" + self.stderr).splitlines() if line.strip()]


@dataclass
class Machine:
    root: Path

    def __post_init__(self) -> None:
        for path in (self.home, self.root / "work", self.root / "shims"):
            path.mkdir(parents=True, exist_ok=True)
        python = self.root / "shims" / "python3"
        python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        python.chmod(0o755)
        claude = self.root / "shims" / "claude"
        claude.write_text(f'#!/bin/sh\necho "$@" >> "{self.root}/claude-calls.log"\nexit 1\n')
        claude.chmod(0o755)

    home = property(lambda self: self.root / "home")
    cache = property(lambda self: self.home / CACHE)
    bin = property(lambda self: self.home / ".local" / "bin")
    rules = property(lambda self: self.home / ".claude" / "rules")
    instructions = property(lambda self: self.home / ".claude" / "CLAUDE.md")

    def version(self, name: str) -> Path:
        return self.cache / name

    def set_identity(self, who: Identity) -> None:
        (self.home / ".gitconfig").write_text(
            f"[user]\n\tname = {who.name}\n\temail = {who.email}\n", encoding="utf-8"
        )

    def env(self, plugin: Path | None = None) -> dict[str, str]:
        drop = ("CLAUDE", "PRAXION_", "GIT_", "PYTEST_", "ANTHROPIC_")
        env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
        env.update(
            HOME=str(self.home),
            PATH=f"{self.root / 'shims'}{os.pathsep}{env.get('PATH', '')}",
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"),
            GIT_TERMINAL_PROMPT="0",
            PRAXION_DISABLE_EVENT_POSTING="1",
            PRAXION_DISABLE_SIDECAR_AUTOCOMMIT="1",
        )
        if plugin is not None:
            env["CLAUDE_PLUGIN_ROOT"] = str(plugin)
        return env

    def install_version(self, name: str, source: Path) -> Path:
        """Claude Code installing a version into its own directory of the cache and registering it."""
        dest = self.version(name)
        shutil.copytree(source, dest, symlinks=True)
        registry = self.home / ".claude" / "plugins" / "installed_plugins.json"
        registry.write_text(
            json.dumps({"plugins": {"praxion@bit-agora": [
                {"scope": "user", "installPath": str(dest), "version": name}]}}),
            encoding="utf-8",
        )  # fmt: skip
        return dest

    def session(self, name: str, *, terminal: bool = False, timeout: float = 180) -> Session:
        """A session start: the version's completion hook, run as Claude Code runs it, its
        payload on stdin and stdin then closed. With `terminal`, the hook's process also has a
        controlling terminal that never sends anything, as an interactive session has."""
        plugin = self.version(name)
        tty = os.openpty() if terminal else None

        def attach_terminal() -> None:
            os.setsid()
            fcntl.ioctl(tty[1], termios.TIOCSCTTY, 0)

        start = time.monotonic()
        proc = subprocess.Popen(
            [sys.executable, str(plugin / HOOK)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=self.root / "work", env=self.env(plugin), text=True,
            start_new_session=not terminal, preexec_fn=attach_terminal if terminal else None,
        )  # fmt: skip
        try:
            out, err = proc.communicate(SESSION_START_PAYLOAD, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            timed_out = True
        finally:
            for fd in tty or ():
                os.close(fd)
        return Session(proc.returncode, out, err, time.monotonic() - start, timed_out)

    def first_install(self, name: str, source: Path) -> Path:
        plugin = self.install_version(name, source)
        result = self.session(name)
        if not self.instructions.is_symlink():
            raise AssertionError(
                f"the first install of {name} left no global instructions link: "
                f"{result.stdout[-800:]}{result.stderr[-800:]}"
            )
        return plugin

    def let_time_pass(self) -> None:
        """Everything on the machine dates from a day ago, as after weeks of use."""
        then = time.time() - DAY
        for path in [self.root, *self.root.rglob("*")]:
            os.utime(path, (then, then), follow_symlinks=False)


def links(directory: Path) -> dict[str, str]:
    """Every link under `directory`: its place relative to the directory -> its link text."""
    if not directory.exists():
        return {}
    return {
        str(p.relative_to(directory)): os.readlink(p)
        for p in sorted(directory.rglob("*"))
        if p.is_symlink()
    }


def inside(path: str | Path, directory: Path) -> str | None:
    """`path`'s place relative to `directory` once both are resolved, or None outside it."""
    real, base = os.path.realpath(path), os.path.realpath(directory)
    return os.path.relpath(real, base) if real.startswith(base + os.sep) else None


# -- A fresh install ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fresh:
    """What a fresh install of a version leaves: offered scripts, linked rules, its instructions."""

    scripts: dict[str, str]  # name in ~/.local/bin -> path in the version's directory
    rules: dict[str, str]  # place in ~/.claude/rules -> path in the version's directory
    instructions: str


def fresh_install(scratch: Path, source: Path, version: str, who: Identity) -> Fresh:
    machine = Machine(scratch)
    machine.set_identity(who)
    plugin = machine.first_install(version, source)
    scripts = {
        name: rel
        for name in links(machine.bin)
        if (rel := inside(machine.bin / name, plugin)) is not None
    }
    rules = {
        place: rel
        for place in links(machine.rules)
        if (rel := inside(machine.rules / place, plugin)) is not None
    }
    if not scripts or not rules:
        raise AssertionError(f"a fresh install of {version} linked no script or no rule")
    return Fresh(scripts, rules, machine.instructions.read_text(encoding="utf-8"))


# -- An update from N to N+1 ----------------------------------------------------------------------


@dataclass
class Update:
    """A marketplace install of N, aged, then N+1 in the cache; `session` is N+1's first one."""

    machine: Machine
    fresh: Fresh  # a fresh install of N+1, the oracle for what N+1 offers and links
    n_template: str
    n_render: str
    roles: dict[str, str] = field(default_factory=dict)
    before: dict[str, tuple] = field(default_factory=dict)  # HOME, as N+1 lands
    clone_before: dict[str, tuple] = field(default_factory=dict)  # the clone checkout, likewise
    session: Session | None = None

    @property
    def n(self) -> Path:
        return self.machine.version(BEFORE)

    @property
    def n1(self) -> Path:
        return self.machine.version(AFTER)

    @property
    def n_values(self) -> dict[str, str]:
        return values_in(self.n_render, self.n_template)

    def run(self, **kwargs) -> Session:
        self.session = self.machine.session(AFTER, **kwargs)
        return self.session


SCRIPT_ROLES = ("free", "skipped", "current", "clone", "gone_outside", "regular")
RULE_ROLES = ("missing", "skipped", "current", "gone_outside", "clone", "regular")
USER_PROGRAM = b"#!/bin/sh\necho 'a program the user put here'\n"
USER_RULE = b"# A rule the user wrote\n\nKeep it.\n"


def _replace(path: Path, *, link_to: Path | str | None = None, data: bytes | None = None) -> None:
    if path.is_symlink() or path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if link_to is not None:
        path.symlink_to(link_to)
    else:
        path.write_bytes(data or b"")


def prepare_update(
    scratch: Path, n_source: Path, n1_source: Path, fresh: Fresh, *, instructions: str = "render"
) -> Update:
    """N installed fresh under FIRST's identity, then every kind of link a user's machine can hold,
    then a day passes, the identity changes to LATER, and N+1 lands in the cache.

    `instructions` is what `~/.claude/CLAUDE.md` is when N+1 arrives: `render` (N's render, as N
    left it), `clone` (a link into a clone checkout), `regular` (a file the user owns) or
    `dangling` (N's render already gone)."""
    m = Machine(scratch)
    m.set_identity(FIRST)
    n = m.first_install(BEFORE, n_source)
    n_render = m.instructions.read_text(encoding="utf-8")
    update = Update(m, fresh, (n_source / TEMPLATE).read_text(encoding="utf-8"), n_render)
    older = m.version(OLDER)
    n1 = m.version(AFTER)  # where N+1 will be; links into it are planted before it lands
    clone = m.root / "clone"
    gone = m.root / "gone"
    elsewhere = m.root / "elsewhere"

    names = sorted(fresh.scripts)
    script = dict(zip(SCRIPT_ROLES, names, strict=False))
    for name in names[len(SCRIPT_ROLES) :]:
        _replace(m.bin / name, link_to=n / fresh.scripts[name])  # as N linked it
    if m.bin.joinpath(script["free"]).is_symlink() or m.bin.joinpath(script["free"]).exists():
        m.bin.joinpath(script["free"]).unlink()
    (older / fresh.scripts[script["skipped"]]).parent.mkdir(parents=True, exist_ok=True)
    (older / fresh.scripts[script["skipped"]]).write_text("#!/bin/sh\necho older\n")
    _replace(m.bin / script["skipped"], link_to=older / fresh.scripts[script["skipped"]])
    _replace(m.bin / script["current"], link_to=n1 / fresh.scripts[script["current"]])
    (clone / "scripts").mkdir(parents=True, exist_ok=True)
    (clone / "scripts" / script["clone"]).write_text("#!/bin/sh\necho clone\n")
    _replace(m.bin / script["clone"], link_to=clone / "scripts" / script["clone"])
    _replace(m.bin / script["gone_outside"], link_to=gone / "scripts" / script["gone_outside"])
    _replace(m.bin / script["regular"], data=USER_PROGRAM)
    (n / "scripts" / "retired-tool").write_text("#!/bin/sh\necho retired\n")
    _replace(m.bin / "retired-tool", link_to=n / "scripts" / "retired-tool")
    _replace(m.bin / "praxion-readme", link_to=n1 / "README.md")
    elsewhere.mkdir(parents=True, exist_ok=True)
    (elsewhere / "my-own-tool").write_text("#!/bin/sh\necho mine\n")
    _replace(m.bin / "my-own-tool", link_to=elsewhere / "my-own-tool")
    script.update(retired="retired-tool", stray="praxion-readme", own="my-own-tool")

    places = sorted(fresh.rules)
    rule = dict(zip(RULE_ROLES, places, strict=False))
    for place in places[len(RULE_ROLES) :]:
        _replace(m.rules / place, link_to=n / fresh.rules[place])
    if m.rules.joinpath(rule["missing"]).is_symlink():
        m.rules.joinpath(rule["missing"]).unlink()
    _replace(m.rules / rule["skipped"], link_to=older / fresh.rules[rule["skipped"]])
    _replace(m.rules / rule["current"], link_to=n1 / fresh.rules[rule["current"]])
    _replace(m.rules / rule["gone_outside"], link_to=gone / "rules" / rule["gone_outside"])
    (clone / "rules" / rule["clone"]).parent.mkdir(parents=True, exist_ok=True)
    (clone / "rules" / rule["clone"]).write_text("# the clone's own rule\n")
    _replace(m.rules / rule["clone"], link_to=clone / "rules" / rule["clone"])
    _replace(m.rules / rule["regular"], data=USER_RULE)
    retired_rule = Path("rules/swe/retired-rule.md")
    (n / retired_rule).parent.mkdir(parents=True, exist_ok=True)
    (n / retired_rule).write_text("# a rule N linked and N+1 no longer does\n")
    _replace(m.rules / "swe" / "retired-rule.md", link_to=n / retired_rule)
    unlinked = sorted(
        str(p.relative_to(n1_source / "rules"))
        for p in (n1_source / "rules").rglob("*")
        if p.is_file() and f"rules/{p.relative_to(n1_source / 'rules')}" not in fresh.rules.values()
    )[0]
    _replace(m.rules / unlinked, link_to=n1 / "rules" / unlinked)
    (elsewhere / "mine.md").write_text("# my personal rule\n")
    _replace(m.rules / "personal" / "mine.md", link_to=elsewhere / "mine.md")
    rule.update(retired="swe/retired-rule.md", stray=unlinked, own="personal/mine.md")

    if instructions == "clone":
        (clone / RENDER).parent.mkdir(parents=True, exist_ok=True)
        (clone / RENDER).write_text("# A developer's own rendered instructions\n")
        _replace(m.instructions, link_to=clone / RENDER)
    elif instructions == "regular":
        _replace(m.instructions, data=b"# Instructions the user wrote and owns\n")
    elif instructions == "dangling":
        (n / RENDER).unlink()

    m.let_time_pass()
    m.set_identity(LATER)
    m.install_version(AFTER, n1_source)
    update.roles = {**{f"script:{k}": v for k, v in script.items()},
                    **{f"rule:{k}": v for k, v in rule.items()}}  # fmt: skip
    update.before = snapshot(m.home, hash_files=False)
    update.clone_before = snapshot(clone)
    return update


# -- Observation ----------------------------------------------------------------------------------


def snapshot(root: Path, *, hash_files: bool = True) -> dict[str, tuple]:
    """Every path under `root`: kind, link text or content digest, inode and modification time."""
    state = {}
    for path in [root, *sorted(root.rglob("*"))]:
        st = path.lstat()
        if path.is_symlink():
            what = ("link", os.readlink(path))
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if hash_files else ""
            what = ("file", digest)
        else:
            what = ("dir", "")
        state[str(path.relative_to(root))] = (*what, st.st_ino, st.st_mtime_ns)
    return state


def logs_written(root: Path, since: float) -> list[Path]:
    """Log-like files under `root` written at or after `since`."""
    return [
        p
        for p in root.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and p.stat().st_mtime >= since
        and (p.suffix in (".log", ".jsonl") or any("log" in part for part in p.parts[-3:-1]))
    ]


# -- The clone installer --------------------------------------------------------------------------


def relink(clone: Path, machine: Machine, answers: str = "") -> subprocess.CompletedProcess[str]:
    """`bash install.sh --relink` from `clone` into the machine's HOME, as its operator runs it,
    typing `answers` at its prompts (none, by default: stdin is at its end)."""
    return subprocess.run(
        ["bash", str(clone / "install.sh"), "--relink"],
        cwd=clone, env=machine.env(), input=answers, capture_output=True, text=True, timeout=600,
    )  # fmt: skip


def saved_values_file(values: dict[str, str]) -> str:
    return "".join(f"PRAXION_{key}={value}\n" for key, value in values.items())


# -- Test runs over a stand-in checkout -----------------------------------------------------------

INSTALLER_NAMES = re.compile(
    r"install\.sh|install_claude\.sh|render_claude_md|auto_complete_install"
)
INSTALLER_CALLS = re.compile(
    r"\.(?:install|installed_home|installed|marketplace_complete|marketplace_installed)\("
    r"|\b(?:installed|installed_home|run_\w*install\w*|run_dev_link)\("
)


def installer_tests(root: Path) -> list[str]:
    """The test files that run an installer or the completion: by name, or through a driver call.

    The scenarios of this update are left out, so a run never nests itself."""
    found = []
    for top in ("tests", "scripts", "hooks", "skills"):
        for path in sorted((root / top).rglob("test_*.py")):
            if "drivers" in path.parts or path.name.startswith("test_plugin_update"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if INSTALLER_NAMES.search(text) or INSTALLER_CALLS.search(text):
                found.append(str(path.relative_to(root)))
    return found


def stand_in_checkout(dest: Path) -> Path:
    """A whole copy of this working tree, committed as a repository of its own."""
    return as_git_repository(copy_files(checkout_files(), REPO_ROOT, dest))


def run_tests(checkout: Path, home: Path, paths: list[str]) -> subprocess.CompletedProcess[str]:
    """The checkout's own test runner over `paths`, as an operator runs it from that checkout."""
    home.mkdir(parents=True, exist_ok=True)
    drop = ("PYTEST_", "PRAXION_", "CLAUDE", "GIT_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider", *paths],
        cwd=checkout, env=env, capture_output=True, text=True, timeout=1800,
    )  # fmt: skip
