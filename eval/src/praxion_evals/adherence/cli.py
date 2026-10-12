"""``praxion-evals-adherence``: the adherence eval's opt-in console entry.

Every session costs money, so this entry is the only way to reach the eval and
no other module imports it. It is a stub until the session loop is wired.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

NOT_WIRED_EXIT = 2
NOT_WIRED_MESSAGE = "praxion-evals-adherence: not wired yet; no session was launched"


def main(argv: Sequence[str] | None = None) -> int:
    print(NOT_WIRED_MESSAGE, file=sys.stderr)
    return NOT_WIRED_EXIT


if __name__ == "__main__":
    sys.exit(main())
