"""Entry point for ``python -m scripts.project_metrics``.

Loads a ``.env`` file (cwd upward) so the operator's
``CLAUDE_CODE_OAUTH_TOKEN`` / ``ANTHROPIC_API_KEY`` need not be passed inline,
then dispatches ``sys.argv[1:]`` to :func:`scripts.project_metrics.cli.main` and
propagates its integer exit code to the operating system. ``.env`` loading lives
here (the process boundary), not in ``cli.main``, so unit tests that call
``cli.main`` directly stay isolated from any developer-local ``.env``.
"""

from __future__ import annotations

import sys

from scripts.project_metrics._dotenv import load_dotenv
from scripts.project_metrics.cli import main

__all__: list[str] = []


if __name__ == "__main__":
    # override=False — an explicit inline `export` still wins over the .env value.
    load_dotenv()
    sys.exit(main(sys.argv[1:]))
