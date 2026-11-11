"""What Praxion's hooks need from the `python3` they run under, and the line naming a shortfall.

Every hook is registered as `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/<hook>.py`, so
it runs under whichever `python3` comes first on the user's PATH; stock macOS
puts 3.9 without PyYAML there. Below the floor each hook degrades on its own:
rule injection skips without PyYAML, and other hooks stop on a 3.10 or 3.11
construct. The floor is declared once, here, and the shortfall is named where a
person looks: `install.sh --check` (this file as a script: exit 1 and the line,
or exit 0 and nothing) and the first session after an install or update (the
`auto_complete_install` hook, through `notice`).

The interpreter being judged parses this file first, so it keeps to syntax
Python 3.7 reads (a test holds it there).
"""

from __future__ import annotations

import importlib.util
import sys

FLOOR = (3, 11)
_FLOOR_TEXT = ".".join(str(part) for part in FLOOR)
# The module a hook imports, and the distribution a person installs to get it.
REQUIRED_MODULES = (("yaml", "PyYAML"),)


def shortfalls(version, importable) -> tuple[str, ...]:
    """Each way `version` and the modules `importable` finds fall short, in a fixed order."""
    found = []
    if tuple(version[:2]) < FLOOR:
        major, minor, micro = version[:3]
        found.append(f"Python {major}.{minor}.{micro}, needs {_FLOOR_TEXT} or newer")
    for module, distribution in REQUIRED_MODULES:
        if not importable(module):
            found.append(f"{distribution} is not importable")
    return tuple(found)


def describe(executable: str, found: tuple[str, ...]) -> str:
    return (
        f"python3 at {executable} falls short of what Praxion's hooks need: "
        f"{'; '.join(found)}. Put a Python {_FLOOR_TEXT} or newer with PyYAML first on PATH."
    )


def notice(version=None, importable=None, executable=None) -> str | None:
    """The line naming this interpreter's shortfall, or None when it meets the floor."""
    found = shortfalls(version or sys.version_info, importable or _is_importable)
    if not found:
        return None
    return describe(executable or sys.executable, found)


def _is_importable(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def main(version=None, importable=None, executable=None) -> int:
    line = notice(version, importable, executable)
    if line is None:
        return 0
    print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
