"""Recording-mode resolution for the observation log.

``Mode`` is the closed set every writer in this package consults before
appending a row. ``resolve_mode`` is pure and parameterized -- the caller
hands it the environment mapping explicitly rather than this module reading
``os.environ`` itself -- so mode resolution is testable without monkeypatching
and stays a single, auditable precedence chain.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

# The setting this package owns.
SETTING = "PRAXION_OBSERVATION_LOG"

# The wider, pre-existing kill switch defined in ``hooks/_hook_utils.py`` as
# ``DISABLE_OBSERVABILITY``. Its name is duplicated here as a literal (not
# imported) so this package stays self-contained -- a plugin-installed copy
# of ``hooks/`` guarantees this directory's own internal imports resolve, but
# nothing about a sibling module living one level up in the same directory.
_LEGACY_DISABLE_SETTING = "PRAXION_DISABLE_OBSERVABILITY"
_TRUTHY = frozenset({"1", "true", "yes"})


class Mode(str, Enum):  # noqa: UP042 -- StrEnum needs 3.11; hooks/ targets 3.9+
    """The three recording modes a process can resolve to."""

    FULL = "full"
    STANDARD = "standard"
    OFF = "off"


class ModeSource(str, Enum):  # noqa: UP042 -- StrEnum needs 3.11; hooks/ targets 3.9+
    """Why ``resolve_mode`` returned the ``Mode`` it did.

    Stamped onto every ``session_start`` row as ``log_mode_source`` (a later
    step's job) so a reader can tell "the fleet default" apart from "this
    project opted in explicitly" apart from "a typo fell back to full".
    """

    DEFAULT = "default"
    SETTING = "setting"
    INVALID_SETTING = "invalid-setting"
    LEGACY_DISABLE = "legacy-disable"


def resolve_mode(env: Mapping[str, str]) -> tuple[Mode, ModeSource]:
    """Return the ``(Mode, ModeSource)`` in effect for ``env``.

    Precedence, highest first:

    1. The legacy switch (``PRAXION_DISABLE_OBSERVABILITY``) is truthy ->
       ``OFF`` / ``LEGACY_DISABLE``.
    2. ``PRAXION_OBSERVATION_LOG`` names a valid mode -> that mode, as given.
    3. ``PRAXION_OBSERVATION_LOG`` is set but names no valid mode -> ``FULL``
       / ``INVALID_SETTING`` (a typo fails open toward more data, not less).
    4. Otherwise -- including an explicitly falsy legacy switch, which is
       neutral and earns no rule of its own -- the default, ``STANDARD`` /
       ``DEFAULT``.
    """
    legacy = env.get(_LEGACY_DISABLE_SETTING, "").strip().lower()
    if legacy in _TRUTHY:
        return Mode.OFF, ModeSource.LEGACY_DISABLE

    raw = env.get(SETTING, "").strip()
    if not raw:
        return Mode.STANDARD, ModeSource.DEFAULT
    try:
        return Mode(raw), ModeSource.SETTING
    except ValueError:
        return Mode.FULL, ModeSource.INVALID_SETTING
