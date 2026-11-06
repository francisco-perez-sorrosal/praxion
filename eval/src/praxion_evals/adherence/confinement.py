"""The shell confinement of a confined kit's session, as one value and its rendered settings.

The sessions of the confined roles (the implementer, the verifier, the test-engineer and the
systems-architect) run shell commands (the fixture's tests, the formatter, the linter, git
reads, Praxion's scripts). A command pattern cannot bound them, because pytest runs code the
role just wrote, so the harness's OS sandbox bounds them instead. ``confinement_for`` builds
the value from where the session runs and what the operator's machine holds; ``settings_of``
renders it as the ``sandbox`` block the session is started with (``--settings``). Every other
role gets ``None`` and keeps its grant.

Two facts shape the paths:

- The session's ``HOME`` is its sandbox home, so a ``~`` entry would protect the wrong
  directory. Every path here is absolute and rooted in the operator's real home.
- The harness matches a path as spelled, and a symlinked prefix reaches the same file under
  another spelling. Each path therefore appears in its given spelling and in its realpath.

Reads are denied across the real home and re-opened only where a session needs them (the
runner's environment, the plugin copy, the run root); the narrower path wins. A credential
entry that an ``allow_read`` entry covers would be re-opened, so such a pair is refused.

The one outside read is ``os.path.realpath``, which follows symlinks on disk; otherwise the
module is a function of its arguments.

The same module reads a broken confinement back from a session's record
(``confinement_breach``): a sandbox that never started, a sandbox refusal after startup, a
refused command the role's definition prescribes, or a prescribed command the sandbox blocked
(``Operation not permitted``). Each means the grant, not the role, failed. A refused command
that starts with a variable assignment is the exception: the harness sends it through the
regular permission flow by design, so its refusal says nothing of the grant (the shell allow
rule approves such a command, so one is no longer expected).

The settings keys were last checked against code.claude.com/docs/en/sandboxing.md and
code.claude.com/docs/en/settings-reference.md (2026-11-03).
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import dropwhile
from pathlib import Path
from typing import Any, NamedTuple

from praxion_evals.adherence.model import RefusedCommand, Role

CONFINED_ROLES: frozenset[Role] = frozenset(
    {"implementer", "verifier", "test-engineer", "systems-architect"}
)

# Names under the operator's real home. The first layer of protection is `deny_read` over the
# whole home; these also hold where the harness's filesystem isolation is off (macOS).
CREDENTIAL_LOCATIONS: tuple[str, ...] = (
    ".ssh",
    ".aws",
    ".config/gcloud",
    ".azure",
    ".kube",
    ".docker",
    ".npmrc",
    ".pypirc",
    ".cargo/credentials.toml",
    ".gem/credentials",
    ".config/gh",
    ".netrc",
    ".claude",
    ".claude.json",
)

# Dropped from a confined command's environment; the session process and its hooks keep them.
SESSION_CREDENTIAL_VARIABLES: tuple[str, ...] = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)

# Required, never unconfined (no fallback at startup, no retry), and commands inside run
# without a prompt. Fixed, so a "confined but optional" session cannot be built.
_FIXED_FLAGS: tuple[tuple[str, bool], ...] = (
    ("enabled", True),
    ("failIfUnavailable", True),
    ("allowUnsandboxedCommands", False),
    ("autoAllowBashIfSandboxed", True),
)
_DENY = "deny"
# sandboxing.md § Network isolation: set from `--settings`, a host outside the (empty)
# allowlist is denied instead of prompting, so the refusal never rests on the permission mode.
_NETWORK = {"strictAllowlist": True}
# sandboxing.md § Filesystem isolation (and settings-reference.md, Permission settings): the
# file tools refuse reads outside the working directories in every permission mode. The
# sandbox's `denyRead` does not reach the Read tool, so this is what keeps it off the token
# file. The working directories are the session's own (the run's scratch) and its `--add-dir`
# (the plugin copy).
_PERMISSIONS = {"blockReadsOutsideWorkingDirectories": True}
# sandboxing.md § Auto-allow mode: a sandboxed command is approved without a prompt, except the
# forms the harness sends through the regular permission flow (an env prefix, `eval`; probed on
# 2.1.317: a `( ... )` subshell and a `$?` expansion too), which `-p` then refuses. The sandbox,
# not a command pattern, bounds a confined session, so every shell command is approved and still
# runs inside it: with `allowUnsandboxedCommands` false and no `excludedCommands`, none can
# leave (probed: a subshell, a `$?` and an env-prefixed write outside the scratch each met
# `Operation not permitted`).
_SHELL_ALLOW = ("Bash",)


@dataclass(frozen=True)
class Places:
    """Where a confined session runs: the plugin copy it may read but never write, and the run
    root that holds its results."""

    run_root: Path
    plugin_copy: Path


@dataclass(frozen=True)
class Operator:
    """The operator's machine as the runner sees it.

    ``runner_prefix`` and ``runner_base_prefix`` are the runner interpreter's ``sys.prefix`` and
    ``sys.base_prefix``: the environment a session's tests run under. ``ambient_path`` is the
    directories of the PATH the runner was started with.
    """

    home: Path
    token_file: Path | None
    runner_prefix: Path
    runner_base_prefix: Path
    ambient_path: tuple[str, ...]


@dataclass(frozen=True)
class Confinement:
    """The paths, variables and program order of one confined session.

    Invariants, checked at construction: every path, ``program_order`` directories included, is
    absolute, and no ``allow_read`` entry covers a ``credential_files`` entry.
    """

    deny_write: tuple[str, ...]
    deny_read: tuple[str, ...]
    allow_read: tuple[str, ...]
    credential_files: tuple[str, ...]
    env_drops: tuple[str, ...]
    program_order: tuple[str, ...]

    def __post_init__(self) -> None:
        paths = (
            *self.deny_write,
            *self.deny_read,
            *self.allow_read,
            *self.credential_files,
            *self.program_order,
        )
        relative = [path for path in paths if not os.path.isabs(path)]
        if relative:
            raise ValueError(f"confinement paths must be absolute, got {relative}")
        swallowed = [
            (allowed, credential)
            for allowed in self.allow_read
            for credential in self.credential_files
            if _covers(allowed, credential)
        ]
        if swallowed:
            raise ValueError(f"an allow_read entry covers a credential entry: {swallowed}")


def confinement_for(role: Role, places: Places, operator: Operator) -> Confinement | None:
    """The confinement of `role`'s session; None for a role whose kit is not confined."""
    if role not in CONFINED_ROLES:
        return None
    credential_paths = [operator.home / name for name in CREDENTIAL_LOCATIONS]
    if operator.token_file is not None:
        credential_paths.append(operator.token_file)
    return Confinement(
        deny_write=_spellings([places.plugin_copy]),
        deny_read=_spellings([operator.home]),
        allow_read=_spellings(
            [
                operator.runner_prefix,
                operator.runner_base_prefix,
                places.plugin_copy,
                places.run_root,
            ]
        ),
        credential_files=_spellings(credential_paths),
        env_drops=SESSION_CREDENTIAL_VARIABLES,
        program_order=(
            str(places.plugin_copy / "scripts"),
            str(operator.runner_prefix / "bin"),
            *operator.ambient_path,
        ),
    )


def settings_of(confinement: Confinement) -> dict[str, Any]:
    """The settings that put `confinement` into force: the `sandbox` block, the `permissions`
    key that holds the file tools to the working directories, and the rule that approves every
    shell command the sandbox confines.

    No `network.allowedDomains`: a confined command opens no connection.
    """
    return {
        "permissions": {**_PERMISSIONS, "allow": list(_SHELL_ALLOW)},
        "sandbox": {
            **dict(_FIXED_FLAGS),
            "network": dict(_NETWORK),
            "filesystem": {
                "denyWrite": list(confinement.deny_write),
                "denyRead": list(confinement.deny_read),
                "allowRead": list(confinement.allow_read),
            },
            "credentials": {
                "files": [{"path": path, "mode": _DENY} for path in confinement.credential_files],
                "envVars": [{"name": name, "mode": _DENY} for name in confinement.env_drops],
            },
        },
    }


def _spellings(paths: Iterable[Path]) -> tuple[str, ...]:
    """Each path as given, then as its realpath when that differs; first occurrence wins."""
    spelled = (spelling for path in paths for spelling in (str(path), os.path.realpath(path)))
    return tuple(dict.fromkeys(spelled))


def _covers(root: str, path: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


# ---------------------------------------------------------------------------
# A broken confinement, read from a session's record
# ---------------------------------------------------------------------------

_GIT_READS = frozenset({"git diff", "git log", "git show", "git status"})

# What each confined role's definition has it run, by program name, `python -m` module,
# script file name or `git <subcommand>`. The verifier and the systems-architect never run the
# test runner. The systems-architect's `git config` and `git rev-parse` reads name a decision
# fragment (its author and branch), so a refusal of them is the grant's, not the role's.
PRESCRIBED_COMMANDS: dict[Role, frozenset[str]] = {
    "implementer": frozenset(
        {
            "pytest",
            "py.test",
            "ruff",
            "resolve_test_scope.py",
            "check_id_citation_discipline.py",
            "mutation_sensor.py",
            "audit_tests.py",
        }
    )
    | _GIT_READS,
    "verifier": frozenset(
        {
            "ruff",
            "extract_spec.py",
            "check_test_results_shape.py",
            "check_state_ledgers.py",
            "rework_manifest.py",
            "check_footprint_criteria.py",
            "query_adrs.py",
            "reconcile_pipeline_state.py",
        }
    )
    | _GIT_READS,
    "test-engineer": frozenset({"pytest", "py.test", "ruff", "mutation_sensor.py"}) | _GIT_READS,
    "systems-architect": frozenset(
        {
            "extract_spec.py",
            "check_footprint_criteria.py",
            "check_design_checkpoint.py",
            "query_adrs.py",
            "git config",
            "git rev-parse",
        }
    )
    | _GIT_READS,
}

SANDBOX_REFUSAL = re.compile(r"Sandbox is required but failed to initialize[^\n]*")
BLOCKED_BY_SANDBOX = "Operation not permitted"
EVIDENCE_CHARS = 300
_CHAIN_OPERATORS = frozenset({"&&", "||", ";", ";;", "|", "&", "\n"})
_REDIRECT_START = ("<", ">")
_ENV_ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=")
_PYTHON_PROGRAM = re.compile(r"python[\d.]*")
_PACKAGE_RUNNERS = frozenset({"uv", "pixi", "poetry", "pipenv", "hatch"})
_SHELLS = frozenset({"bash", "sh"})
_DURATION = re.compile(r"\d+(\.\d+)?[smhd]?")
_TIMEOUT_OPTIONS_WITH_VALUE = frozenset({"-s", "-k", "--signal", "--kill-after"})
_ENV_OPTIONS_WITH_VALUE = frozenset({"-u", "-C", "-S", "--unset", "--chdir", "--split-string"})


class ShellRun(NamedTuple):
    """A shell command the role ran, and the output its tool result carried."""

    command: str
    output: str


def confinement_breach(
    role: Role,
    refused: Sequence[RefusedCommand],
    tool_result_texts: Iterable[str],
    stderr: str,
    started: bool,
    shell_runs: Iterable[ShellRun] = (),
) -> str | None:
    """The evidence that `role`'s session ran without its confinement, or None.

    `started` is whether the session produced its ``init`` event. The harness's startup text
    under ``failIfUnavailable`` is not documented, so a session that never started and whose
    stderr names the sandbox (any case) counts. `refused` and `shell_runs` carry the commands
    as the session ran them, unclipped, so the reading never parses half a command; the
    evidence clips what it names. The caller redacts everything it passes in.
    """
    if role not in CONFINED_ROLES:
        return None
    if not started and "sandbox" in stderr.lower():
        return f"the session exited at startup without its sandbox: {_clip(stderr.strip())}"
    for text in tool_result_texts:
        if match := SANDBOX_REFUSAL.search(text):
            return _clip(match.group())
    if (prescribed := refused_prescribed(role, refused)) is not None:
        return (
            f"a command the role's definition prescribes was refused: {_clip(prescribed.command)}"
        )
    if (blocked := blocked_prescribed(role, shell_runs)) is not None:
        return f"a command the role's definition prescribes met {BLOCKED_BY_SANDBOX!r}: " + _clip(
            blocked.command
        )
    return None


def refused_prescribed(role: Role, refused: Sequence[RefusedCommand]) -> RefusedCommand | None:
    """The first refused command that runs something `role`'s definition prescribes.

    A command that starts with a variable assignment goes through the regular permission flow
    by design (sandboxing.md § Auto-allow), so its refusal is not read: the fixtures declare
    ``pythonpath``, which leaves no prescribed form needing the prefix.
    """
    prescribed = PRESCRIBED_COMMANDS.get(role, frozenset())
    return next(
        (
            r
            for r in refused
            if any(not c.env_prefixed for c in _prescribed_commands(r.command, prescribed))
        ),
        None,
    )


def blocked_prescribed(role: Role, shell_runs: Iterable[ShellRun]) -> ShellRun | None:
    """The first prescribed command whose output says the sandbox blocked it: the grant is too
    narrow for work the role must do. The same output on any other command is the role's own."""
    prescribed = PRESCRIBED_COMMANDS.get(role, frozenset())
    return next(
        (
            run
            for run in shell_runs
            if BLOCKED_BY_SANDBOX in run.output
            and next(_prescribed_commands(run.command, prescribed), None) is not None
        ),
        None,
    )


def _clip(text: str) -> str:
    return text[:EVIDENCE_CHARS]


class _Command(NamedTuple):
    argv: list[str]
    env_prefixed: bool


def _prescribed_commands(line: str, prescribed: frozenset[str]) -> Iterator[_Command]:
    return (c for c in _commands(line) if _runs_one_of(c.argv, prescribed))


def _commands(line: str) -> Iterator[_Command]:
    """Every command a shell line runs: the chained ones, then what a wrapper runs in turn."""
    for words in _simple_commands(line):
        argv = list(dropwhile(_ENV_ASSIGNMENT.match, words))
        if argv:
            yield _Command(argv, len(argv) < len(words))
            yield from _wrapped_commands(argv)


def _simple_commands(command: str) -> Iterable[list[str]]:
    """The commands a shell line chains, each as words with redirects dropped."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()\n")
        lexer.whitespace, lexer.whitespace_split = " \t\r", True
        tokens = list(lexer)
    except ValueError:  # an unbalanced quote: the line never ran as written
        return
    words: list[str] = []
    skip_target = False
    for token in (*tokens, "\n"):
        if skip_target:
            skip_target = False
        elif token in _CHAIN_OPERATORS:
            if words:
                yield words
            words = []
        elif token.startswith(_REDIRECT_START):
            skip_target = True
        elif token not in ("(", ")"):
            words.append(token)


def _wrapped_commands(argv: list[str]) -> Iterator[_Command]:
    """What ``timeout N``, ``env`` and ``bash -c '...'`` run, however deeply they nest."""
    program, args = os.path.basename(argv[0]), argv[1:]
    if program in _SHELLS:
        yield from _commands(_shell_script(args))
        return
    if program == "timeout":
        inner = _past_options(args, _TIMEOUT_OPTIONS_WITH_VALUE)
        inner = inner[1:] if inner and _DURATION.fullmatch(inner[0]) else []
    elif program == "env":
        inner = list(dropwhile(_ENV_ASSIGNMENT.match, _past_options(args, _ENV_OPTIONS_WITH_VALUE)))
    else:
        return
    if inner:
        yield _Command(inner, False)
        yield from _wrapped_commands(inner)


def _shell_script(args: list[str]) -> str:
    """The text after a shell's ``-c`` (``-lc`` and the like included); empty with none."""
    for position, arg in enumerate(args[:-1]):
        if arg.startswith("-") and not arg.startswith("--") and "c" in arg:
            return args[position + 1]
    return ""


def _past_options(args: list[str], with_value: frozenset[str]) -> list[str]:
    position = 0
    while position < len(args) and args[position].startswith("-"):
        position += 2 if args[position] in with_value else 1
    return args[position:]


def _runs_one_of(argv: list[str], prescribed: frozenset[str]) -> bool:
    program = os.path.basename(argv[0])
    if program == "git":
        return _git_subcommand(argv[1:]) in prescribed
    if _PYTHON_PROGRAM.fullmatch(program):
        return _python_runs_one_of(argv[1:], prescribed)
    if program in _PACKAGE_RUNNERS and "run" in argv:
        start = argv.index("run") + 1
        return any(_runs_one_of(argv[i:], prescribed) for i in range(start, len(argv)))
    return program in prescribed


def _git_subcommand(args: list[str]) -> str:
    """``git -C <dir> -c <k=v> log`` is ``git log``."""
    rest = iter(args)
    for arg in rest:
        if arg in ("-C", "-c"):
            next(rest, None)
        elif not arg.startswith("-"):
            return f"git {arg}"
    return "git"


def _python_runs_one_of(args: list[str], prescribed: frozenset[str]) -> bool:
    for position, arg in enumerate(args):
        following = args[position + 1] if position + 1 < len(args) else ""
        if arg == "-m":
            return following in prescribed
        if arg == "-c":
            return any(
                name.removesuffix(".py") in following for name in prescribed if name.endswith(".py")
            )
        if not arg.startswith("-"):
            return os.path.basename(arg) in prescribed
    return False
