"""Driver for the routing move's install journey: install, open a session, touch a definition.

The journey reaches the system through the installer (`install.sh`), the user rules directory it
links and the session-start rule injection, over a scratch HOME, as a user would; the frozen base
link set (`tests/acceptance/fixtures/model_routing_move/base_links.json`) stands in for an install
made before the move. The marketplace first-session completion is reached through
`model_routing_move.marketplace_complete`, unbound until its binding step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import model_routing_move as move


@dataclass(frozen=True)
class Installed:
    """A finished install: its user rules directory, its links and the session-start text."""

    rules: Path
    links: dict[str, Path]
    session_start_text: str
    check_output: str
    checkout: Path  # the stand-in checkout the install ran from


def installed(scratch: Path, *, over_an_old_install: bool = False) -> Installed:
    """Install this checkout into `scratch`'s HOME (over the base's links when asked), check it,
    and open a session: the linked rules with no path scope plus the injection's text."""
    if over_an_old_install:
        move.plant_old_install(scratch)
    result = move.install(scratch)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    rules = move.rules_dir(scratch)
    resident = [
        p.read_text(encoding="utf-8")
        for p in sorted(rules.rglob("*.md"))
        if "paths" not in move.frontmatter(p.read_text(encoding="utf-8"))
    ]
    injection = move.session_start(scratch / "session")
    checked = move.install_check(scratch)
    return Installed(
        rules=rules,
        links=move.linked_rules(rules),
        session_start_text="\n".join([*resident, injection.context]),
        check_output=checked.stdout + checked.stderr,
        checkout=move.stand_in_root(scratch).resolve(),
    )


def marketplace_installed(scratch: Path) -> dict[str, Path]:
    """The links the marketplace first-session completion leaves in the user rules directory."""
    return move.linked_rules(move.marketplace_complete(scratch))
