"""Whether the harness takes a confined kit's sandbox settings as written, checked at no cost.

A confined kit's session starts with its sandbox block as ``--settings`` JSON, and ``claude -p``
drops an entry it does not take without a word. A run whose block lost a key measures sessions
that ran under other settings than the run declares, and nothing in its records says so.

``claude doctor`` starts no session and calls no model. It reads the ``settings.json`` of its
configuration directory (user scope, which takes the sandbox and credential keys as
``--settings`` does) and reports a wrong type, a value outside its choices and malformed JSON,
each under the setting's dotted path. It says nothing of a key it does not know. Two readings
close that gap:

1. the settings as written: doctor reports nothing for the file;
2. the same settings with every value given a wrong type: doctor reports each one by its path.
   A value it passes over sits under a key the harness does not know, which it would drop.

The second reading is what lets the check fail. A report doctor no longer prints in the shape
read here leaves every value unrecognized, so it refuses, never accepts. Doctor runs in a scratch
configuration directory, a scratch home and an empty working directory, with ``PATH`` the only
variable taken from the operator: no token, no key, no real home. This proves the keys are
taken, not that the sandbox enforces them; the first session that shows a broken confinement
still stops the run (``confinement.confinement_breach``). Doctor's report was last read on
Claude Code 2.1.316.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple, cast

from praxion_evals.adherence.confinement import CONFINED_ROLES, settings_of
from praxion_evals.adherence.model import Role
from praxion_evals.adherence.session_launch import REAL_HOME, session_confinement
from praxion_evals.live.session import CLAUDE_BINARY

DOCTOR_TIMEOUT_S = 120
_PATH_MARK = " › "  # doctor's separator between a file and the setting it reports


class Reported(NamedTuple):
    """One line of doctor's report about a settings file: the setting's dotted path (empty for
    the file as a whole) and doctor's message."""

    path: str
    message: str


class _NoReadingError(Exception):
    """Doctor could not be run or ended in error, so the settings were not read."""


def refuse_unaccepted_settings(roles: Iterable[str], token_file: Path | None) -> None:
    """Raise naming every way the harness would not take a confined kit's settings as written.

    Returns when it takes all of them, or when no named role is confined. Each confined role's
    settings are built as its sessions' are on this machine, with the run's paths named, not made.
    """
    confined = sorted(set(roles) & CONFINED_ROLES)
    with tempfile.TemporaryDirectory(prefix="praxion-evals-settings-") as scratch:
        problems = [
            f"{role}: {problem}"
            for role in confined
            for problem in unaccepted(
                kit_settings(cast(Role, role), token_file), Path(scratch) / role
            )
        ]
    if problems:
        raise ValueError(
            "the harness would not take the confined kits' sandbox settings as written, so their"
            " sessions would run under other settings than the run declares:"
            + "".join(f"\n  {problem}" for problem in problems)
        )


def kit_settings(role: Role, token_file: Path | None) -> dict[str, Any]:
    """The settings a confined `role` session of a run on this machine starts with."""
    run_root = Path(tempfile.gettempdir()) / "praxion-evals-adherence-settings-check"
    confinement = session_confinement(
        role, run_root / role / "full", run_root, home=REAL_HOME, token_file=token_file,
        ambient=os.environ,
    )  # fmt: skip
    if confinement is None:
        raise ValueError(f"{role} is not a confined kit")
    return settings_of(confinement)


def unaccepted(
    settings: Mapping[str, Any], scratch: Path, binary: str = CLAUDE_BINARY
) -> tuple[str, ...]:
    """Every way the harness would not take `settings` as written; empty when it takes them."""
    try:
        as_written = _doctor(settings, scratch / "as-written", binary)
        mistyped = _doctor(_mistyped(settings), scratch / "mistyped", binary)
    except _NoReadingError as error:
        return (str(error),)
    rejected = tuple(f"the harness rejects {_named(line)}: {line.message}" for line in as_written)
    recognized = {line.path for line in mistyped}
    unknown = tuple(
        f"the harness does not know `{path}` and would drop it"
        for path in leaf_paths(settings)
        if path not in recognized
    )
    return (*rejected, *unknown)


def leaf_paths(settings: Mapping[str, Any]) -> tuple[str, ...]:
    """The dotted path of every value in `settings`, as doctor names it (a list index is a part)."""
    return tuple(path for path, _ in _leaves(settings, ""))


def reported_for(file: Path, output: str) -> tuple[Reported, ...]:
    """The lines of doctor's `output` about `file`, under either spelling of its path."""
    heads = tuple(
        f"- {spelling}" for spelling in dict.fromkeys((str(file), os.path.realpath(file)))
    )
    found: list[Reported] = []
    for line in output.splitlines():
        rest = next((line[len(head) :] for head in heads if line.startswith(head)), None)
        if rest is None:
            continue
        if rest.startswith(_PATH_MARK):
            path, _, message = rest[len(_PATH_MARK) :].partition(": ")
            found.append(Reported(path, message))
        elif rest.startswith(": "):
            found.append(Reported("", rest[2:]))
    return tuple(found)


def _doctor(settings: Mapping[str, Any], place: Path, binary: str) -> tuple[Reported, ...]:
    config, home, cwd = (place / name for name in ("config", "home", "cwd"))
    for directory in (config, home, cwd):
        directory.mkdir(parents=True, exist_ok=True)
    file = config / "settings.json"
    file.write_text(json.dumps(settings), encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(config),
        "TERM": "dumb",
    }
    try:
        done = subprocess.run(
            [binary, "doctor"],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=DOCTOR_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise _NoReadingError(f"`{binary} doctor` did not run: {error}") from error
    if done.returncode != 0:
        raise _NoReadingError(
            f"`{binary} doctor` exited {done.returncode}: {done.stderr.strip()[-300:]}"
        )
    return reported_for(file, done.stdout + done.stderr)


def _leaves(value: Any, path: str) -> Iterator[tuple[str, Any]]:
    if isinstance(value, Mapping) and value:
        for key, child in value.items():
            yield from _leaves(child, f"{path}.{key}" if path else str(key))
    elif _is_record_list(value):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}.{index}")
    else:
        yield path, value


def _mistyped(value: Any) -> Any:
    """`value` with every leaf replaced by one of another JSON type."""
    if isinstance(value, Mapping) and value:
        return {key: _mistyped(child) for key, child in value.items()}
    if _is_record_list(value):
        return [_mistyped(item) for item in value]
    return 7 if isinstance(value, str | list | Mapping) else "x"


def _is_record_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, Mapping) for v in value)


def _named(line: Reported) -> str:
    return f"`{line.path}`" if line.path else "the settings file"


def main(argv: Sequence[str] | None = None) -> int:
    """The check alone, at no cost: ``python -m praxion_evals.adherence.settings_acceptance``."""
    parser = argparse.ArgumentParser(prog="python -m praxion_evals.adherence.settings_acceptance")
    parser.add_argument("roles", nargs="*", choices=sorted(CONFINED_ROLES), metavar="ROLE")
    parser.add_argument("--session-oauth-token-file", type=Path, default=None)
    args = parser.parse_args(argv)
    roles = args.roles or sorted(CONFINED_ROLES)
    try:
        refuse_unaccepted_settings(roles, args.session_oauth_token_file)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"accepted as written: {', '.join(roles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
