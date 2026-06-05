---
paths:
- evaluate.py
- data/private/**
- tasks/**
- "**/MANIFEST.json"
core: false
---

## Eval Data Governance

Path-scoped conventions for benchmark/eval-driven projects. Loaded when eval scoring
code (`evaluate.py`), held-out ground truth (`data/private/`), task definitions
(`tasks/`), or a dataset provenance manifest (`**/MANIFEST.json`) is touched.

Zero always-loaded cost — these conventions apply only inside eval/benchmark projects,
not every session.

### Rules

<!-- TODO: P3 wave — populate with governance content: held-out-vs-public split discipline,
     "no ground-truth in a shipped/committed artifact" guard, dataset provenance MANIFEST
     (sha256 + version) verified before scoring, eval determinism + CI smoke-test. -->

### Sentinel Checks

<!-- TODO: P3 wave — populate with the substrate-triggered sentinel check (answer-key-in-package
     / missing-provenance detection) following the AC-dimension conditional-activation idiom. -->
