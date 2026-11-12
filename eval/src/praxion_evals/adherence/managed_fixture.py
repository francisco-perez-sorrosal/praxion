"""A task fixture the sandbox marks as a managed project, without changing what its session receives.

A session launched in a directory with no ``.ai-state/`` was never served the behaviours that are
delivered to managed projects only. The eval's fixtures stay in that position: the marker is an
empty ``.ai-state/``, which git does not see, so what the graded git checks read is what they read,
and the existing disable switches keep the managed-only behaviours that would write into the
fixture or add to the task prompt off. A fixture whose overlay already carries state was already
managed, so it is left exactly as it was.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

STATE_DIRNAME = ".ai-state"

# The managed-only behaviours that reach a launched session: the reminder added to its task prompt,
# and the observation capture that would write into the fixture. The decision context, the rule
# template and the host-native preamble add nothing there (no decisions, a template an unmanaged
# launch already wrote, and a preamble that skips the roles under test).
UNMANAGED_BEHAVIOUR_SWITCHES: Mapping[str, str] = MappingProxyType(
    {
        "PRAXION_DISABLE_PROCESS_INJECT": "1",
        "PRAXION_DISABLE_OBSERVABILITY": "1",
    }
)

NO_SWITCHES: Mapping[str, str] = MappingProxyType({})


def mark_managed(project: Path) -> None:
    """Give the fixture copy at ``project`` an empty ``.ai-state/`` unless it carries one."""
    (project / STATE_DIRNAME).mkdir(exist_ok=True)


def switches_for(project: Path) -> Mapping[str, str]:
    """The environment a launch in ``project`` adds: the switches when the marker is the empty
    directory `mark_managed` made, none when the fixture's overlay carried state of its own.

    The empty directory is the tell: git tracks no empty directory, so a fixture copied from
    tracked files never arrives with one.
    """
    state = project / STATE_DIRNAME
    if state.is_dir() and not any(state.iterdir()):
        return UNMANAGED_BEHAVIOUR_SWITCHES
    return NO_SWITCHES


def switches_planned(sources: Iterable[Path]) -> Mapping[str, str]:
    """What `switches_for` will say for a fixture copied from the ``sources`` directories, before
    it is built: none when a source already carries state, the switches otherwise."""
    carries_state = any(
        (state := source / STATE_DIRNAME).is_dir() and any(state.iterdir()) for source in sources
    )
    return NO_SWITCHES if carries_state else UNMANAGED_BEHAVIOUR_SWITCHES
