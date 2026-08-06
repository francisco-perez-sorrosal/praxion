"""Shared CLI scaffolding for `scripts/` entry points.

Eight scripts had each grown a private `_configure_logging` -- semantically
identical, in two textual variants that differed only by hoisting `level` into
a local. That is the shape `coding-style.md` names: the same pattern appearing
three or more times is extracted, not copied again.

Sibling-imported the same way as `_repo_root`, so it resolves through the
`install_claude.sh` symlink without needing a link of its own. Not executable,
so the installer's `-f && -x` filter leaves it off `PATH` -- correct, since it
is a library and not a user-facing tool.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(levelname)s: %(message)s"


def configure_logging(verbose: bool) -> None:
    """Send `INFO` (or `DEBUG` when verbose) to stderr in the shared format.

    stderr, not stdout: every caller supports `--json`, and a log line on
    stdout would corrupt the machine-readable payload its consumers parse.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=_FORMAT,
        stream=sys.stderr,
    )
