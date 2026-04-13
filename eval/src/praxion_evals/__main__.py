"""Module entrypoint — enables `python -m praxion_evals`."""

from __future__ import annotations

import sys

from praxion_evals.cli import main

if __name__ == "__main__":
    sys.exit(main())
