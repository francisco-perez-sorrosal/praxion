"""Per-project readiness configuration — pillar weighting.

Some projects are not typical software products (a research harness, a
philosophy-as-infrastructure repo, a docs site) where certain Factory pillars
are simply less relevant. Equal-weighting every pillar then drags the headline
score down unfairly. This module loads an optional, committed, language-agnostic
config that lets a project re-weight (or exclude) pillars.

Config file: ``.ai-state/readiness_config.json`` at the repo root. Stdlib
``json`` only — no third-party YAML/TOML dependency, consistent with the metrics
package's zero-dependency contract and usable by non-Python projects.

Schema::

    {
      "pillar_weights": {
        "observability": 0,        # 0 = exclude the pillar from the score
        "dev_environment": 0.5,    # < 1 = count it less
        "security": 0.5
      }
    }

Weights are floats ``>= 0``; unlisted pillars default to ``1.0``. Only the eight
Factory pillars may be weighted — the Pillar-9 manageability sub-score is always
reported separately and is never folded into the level. Any malformed config
(bad JSON, non-numeric or negative weight, unknown pillar key) degrades to a
stderr warning and is ignored value-by-value; the run still succeeds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.project_metrics.collectors.readiness.criteria import FACTORY_PILLARS

__all__ = ["CONFIG_BASENAME", "load_pillar_weights"]

CONFIG_BASENAME: str = "readiness_config.json"
_AI_STATE_DIRNAME: str = ".ai-state"


def load_pillar_weights(repo_root: Path) -> dict[str, float]:
    """Return validated per-pillar weights for the eight Factory pillars.

    Reads ``<repo_root>/.ai-state/readiness_config.json`` when present. Every
    Factory pillar is represented in the returned dict; unlisted pillars and any
    invalid entries fall back to ``1.0``. A missing file returns all-``1.0``
    (the no-config, unweighted default). Never raises — malformed input degrades
    to a warning so the metrics run is not blocked.
    """

    weights: dict[str, float] = dict.fromkeys(FACTORY_PILLARS, 1.0)
    config_path = repo_root / _AI_STATE_DIRNAME / CONFIG_BASENAME
    if not config_path.is_file():
        return weights

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        print(
            f"warning: could not read {config_path} ({exc}); ignoring readiness weights",
            file=sys.stderr,
        )
        return weights

    pillar_weights = raw.get("pillar_weights") if isinstance(raw, dict) else None
    if not isinstance(pillar_weights, dict):
        return weights

    for pillar, value in pillar_weights.items():
        if pillar not in FACTORY_PILLARS:
            print(
                f"warning: readiness_config.json names unknown pillar "
                f"{pillar!r}; ignoring (known: {', '.join(FACTORY_PILLARS)})",
                file=sys.stderr,
            )
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            print(
                f"warning: readiness weight for {pillar!r} is not a number ({value!r}); using 1.0",
                file=sys.stderr,
            )
            continue
        if value < 0:
            print(
                f"warning: readiness weight for {pillar!r} is negative ({value}); using 1.0",
                file=sys.stderr,
            )
            continue
        weights[pillar] = float(value)

    return weights
