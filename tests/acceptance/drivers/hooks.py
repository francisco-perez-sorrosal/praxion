"""Driver for git operations in a main checkout whose finalize hooks are installed.

A managed project has every finalize hook slot (`post-merge`, `post-commit`,
`post-checkout` and `post-rewrite`) in `.git/hooks/` as a symlink to the plugin's
`scripts/git-finalize-hook.sh`; this driver installs exactly that, pointing at this
repository's own `scripts/`, so the hooks run the code under test. Linked
worktrees share the common `.git/hooks/`, so the same hooks run there.

What a scenario can observe, all from outside the hooks:

* the logs (through `log_segments`), and everything git and the hooks printed;
* whether merge-in was started: `python3` on the hooks' PATH is a recording shim
  that appends its command line to a file and then runs the suite's interpreter,
  so a start of the merge-in command (`scripts/merge_worktree_log.py`) shows up
  as a recorded command line naming it;
* how many git processes the hooks ran: git's own trace (`GIT_TRACE2_EVENT`)
  marks every git process a hook starts as a child of the operation's process.

Isolation: git runs with its own HOME and an empty global configuration, no system
configuration, no inherited `GIT_*`, `CLAUDE*` or `PRAXION_*` variables, a fixed
identity, no signing and editors that accept the default message.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DISPATCHER_NAME = "git-finalize-hook.sh"
FINALIZE_HOOKS = ("post-merge", "post-commit", "post-checkout", "post-rewrite")
MERGE_IN_COMMAND = "merge_worktree_log.py"
NON_BLOCKING_WARNING = "warned (non-blocking)"
# The commit this change starts from: the hook cost "before this change" is measured
# with the scripts as they were there.
BASE_COMMIT = "4c44dea5bdc56798f16dbc6dd6147123c4059770"

_IDENTITY = (
    "-c",
    "user.name=Merge Triggers Acceptance",
    "-c",
    "user.email=merge-triggers-acceptance@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


@dataclass(frozen=True)
class Hooked:
    """A main checkout with the finalize hooks installed, and the sandbox they run in."""

    main: Path
    sandbox: Path

    @property
    def starts_file(self) -> Path:
        return self.sandbox / "python3-command-lines.txt"

    def env(self, **extra: str) -> dict[str, str]:
        env = {
            k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "PRAXION_"))
        }
        env.update(
            HOME=str(self.sandbox / "home"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=str(self.sandbox / "home" / ".gitconfig"),
            GIT_EDITOR="true",
            GIT_SEQUENCE_EDITOR="true",
            GIT_TERMINAL_PROMPT="0",
            PATH=f"{self.sandbox / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
        )
        env.update(extra)
        return env

    def git(
        self, *args: str, cwd: Path | None = None, check: bool = True, **extra_env: str
    ) -> subprocess.CompletedProcess[str]:
        """Run git with hooks enabled; `output` of the result is stdout plus stderr."""
        result = subprocess.run(
            ["git", *_IDENTITY, *args],
            cwd=cwd or self.main,
            env=self.env(**extra_env),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed in {cwd or self.main}: {result.stdout}{result.stderr}"
            )
        return result

    def run_hook(
        self, name: str, *args: str, stdin: str = "", cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run an installed hook again by hand, the way git runs it."""
        hooks_dir = Path(self.git("rev-parse", "--git-common-dir").stdout.strip())
        if not hooks_dir.is_absolute():
            hooks_dir = self.main / hooks_dir
        return subprocess.run(
            [str(hooks_dir / "hooks" / name), *args],
            cwd=cwd or self.main,
            env=self.env(),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def merge_in_starts(self) -> list[str]:
        """Every recorded `python3` command line that started the merge-in command."""
        if not self.starts_file.exists():
            return []
        lines = self.starts_file.read_text(encoding="utf-8").splitlines()
        return [line for line in lines if MERGE_IN_COMMAND in line]

    def forget_starts(self) -> None:
        self.starts_file.unlink(missing_ok=True)

    def head_parents(self, cwd: Path | None = None) -> list[str]:
        line = self.git("rev-list", "--parents", "-n", "1", "HEAD", cwd=cwd).stdout.split()
        return line[1:]

    def head(self, cwd: Path | None = None) -> str:
        return self.git("rev-parse", "HEAD", cwd=cwd).stdout.strip()

    def contains(self, sha: str, cwd: Path | None = None) -> bool:
        result = self.git("merge-base", "--is-ancestor", sha, "HEAD", cwd=cwd, check=False)
        return result.returncode == 0


def output_of(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "") + (result.stderr or "")


def install_finalize_hooks(main: Path, sandbox: Path, *, scripts_dir: Path = SCRIPTS_DIR) -> Hooked:
    """Install the four finalize hook slots in `main` as symlinks to `scripts_dir`'s dispatcher."""
    (sandbox / "home").mkdir(parents=True, exist_ok=True)
    (sandbox / "home" / ".gitconfig").write_text("", encoding="utf-8")
    bin_dir = sandbox / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    hooked = Hooked(main, sandbox)
    shim = bin_dir / "python3"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{hooked.starts_file}'\n"
        f"exec '{sys.executable}' \"$@\"\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    hooks_dir = main / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for name in FINALIZE_HOOKS:
        slot = hooks_dir / name
        slot.unlink(missing_ok=True)
        slot.symlink_to(scripts_dir / DISPATCHER_NAME)
    return hooked


def base_scripts(destination: Path) -> Path | None:
    """The `scripts/` (and `hooks/`) of the base commit, unpacked; None when the commit is absent."""
    archive = subprocess.run(
        ["git", "archive", "--format=tar", BASE_COMMIT, "scripts", "hooks"],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=120,
    )
    if archive.returncode != 0:
        return None
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(destination, filter="tar")
    return destination / "scripts"


def git_processes_started_by_hooks(trace_file: Path) -> int:
    """How many git processes the hooks of one traced operation started."""
    count = 0
    for line in trace_file.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") != "start":
            continue
        if "/" in event.get("sid", ""):  # a child of the operation's own git process
            count += 1
    return count


def lines_naming(output: str, *names: str) -> list[str]:
    """The lines of `output` that name any of `names` (a worktree's directory name, say)."""
    return [line for line in output.splitlines() if any(name in line for name in names)]


def normalized(lines: list[str], *, checkout: Path, sandbox: Path) -> list[str]:
    """Lines with the scratch locations and the reporting hook's name made comparable."""
    out = []
    for line in lines:
        for location, token in (
            (str(checkout.resolve()), "<main>"),
            (str(checkout), "<main>"),
            (str(sandbox.resolve()), "<sandbox>"),
            (str(sandbox), "<sandbox>"),
        ):
            line = line.replace(location, token)
        out.append(re.sub(r"post-(merge|commit|rewrite)", "post-<hook>", line))
    return out
