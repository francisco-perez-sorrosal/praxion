"""Driver for the hand-path journey: a refresh that stopped, the skill, the command, the answers.

N is installed and used, then N+1 lands in the cache and is registered. N+1's first session runs
the plugin's first-session hook, whose refresh stops short in one of two ways: N's render no
longer reads back (the person edited it by hand), or N+1's template could not be read for that
session. The person then invokes `/praxion-complete-install` (its bash blocks, run as Claude Code
runs them, with the installed version substituted for `${CLAUDE_PLUGIN_ROOT}`), takes the root
whose check the skill ran as the command it hands over, and runs that command in their own
terminal, answering its questions.

Built from the acceptance drivers `plugin_update`, `hook_reports`, `hand_path_skill` and
`hand_path_command`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import hand_path_command as hc
from tests.acceptance.drivers import hand_path_skill as hp
from tests.acceptance.drivers import plugin_update as pu


@dataclass(frozen=True)
class Journey:
    update: pu.Update
    hook: pu.Session  # N+1's first session
    handed_over: Path | None  # the root of the command the skill handed over
    finished: hc.CommandRun | None  # the command, run by the person; None when none was handed


def stopped_refresh(scratch: Path, sources, how: str) -> tuple[pu.Update, pu.Session]:
    """N+1's first session over a refresh that stops: "unreadable-render" or
    "template-unreadable" (a fault that clears once the session is over)."""
    n, n1, fresh = sources
    update = pu.prepare_update(scratch, n, n1, fresh)
    restore = []
    if how == "unreadable-render":
        (update.n / pu.RENDER).write_text(hc.unreadable(update, "hand-edited"), encoding="utf-8")
    else:
        restore = hc.blocked([(update.n1 / pu.TEMPLATE, 0o000)])
    try:
        session = update.run()
    finally:
        hc.restored(restore)
    return update, session


def journey(scratch: Path, sources, how: str, person: hc.Person) -> Journey:
    update, session = stopped_refresh(scratch, sources, how)
    skill = hp.run_skill("install", update.machine, substituted=update.n1)
    checks = skill.checks()
    handed = Path(checks[0]) if len(checks) == 1 else None
    if handed is None or not (handed / "install.sh").is_file():
        return Journey(update, session, handed, None)
    return Journey(update, session, handed, hc.run_command(handed, update.machine, person))
