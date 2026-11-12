"""Which log, and which ``project``, a working directory belongs to.

The package's one answer to that question, now owned by ``hooks/_project_scope.py``
(the single predicate for "is this directory served by a ``.ai-state/``?"); this
module re-exports it so the log's importers keep one stable path. Behaviour is
unchanged: ``locate`` walks up from the working directory to the nearest
``.ai-state/`` and stops at the first ``.git`` entry.
"""

from __future__ import annotations

try:  # imported as ``hooks._observation_log`` (repo root on the path)
    from .._project_scope import (
        CHECKOUT_MARKER,
        STATE_DIRNAME,
        SUMMARY_FILENAME,
        Location,
        locate,
    )
except ImportError:  # imported bare, with ``hooks/`` on the path (every hook script)
    from _project_scope import CHECKOUT_MARKER, STATE_DIRNAME, SUMMARY_FILENAME, Location, locate

__all__ = ("CHECKOUT_MARKER", "STATE_DIRNAME", "SUMMARY_FILENAME", "Location", "locate")
