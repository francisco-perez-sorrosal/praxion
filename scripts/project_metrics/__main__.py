"""Entry point for ``python -m scripts.project_metrics``.

Dispatches ``sys.argv[1:]`` to :func:`scripts.project_metrics.cli.main`
and propagates its integer exit code to the operating system.
"""

from __future__ import annotations

import sys

from scripts.project_metrics.cli import main

__all__: list[str] = []


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
