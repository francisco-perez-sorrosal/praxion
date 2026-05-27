"""Praxion evals — out-of-band quality measurement framework.

Single entrypoint: ``/eval-praxion`` (CLI: ``praxion-evals``). Runs two check
families against a resolved corpus and writes a Markdown report.

  - Family 1: Pipeline-outcome fidelity (ADR structure, supersession
    reciprocity, traceability, and — when ``--task-slug`` is supplied — the
    per-tier artifact-manifest scan over ``.ai-work/<slug>/``).
  - Family 2: Behavioral-contract adherence (VERIFICATION_REPORT.md BC tag
    scan and BC-rubric LLM checks).

``--mechanical-only`` skips every LLM-judged check across families and runs
without auth env vars. Two deferred-family sentinels live under ``stubs/``;
see ``eval/EVAL_PLAN.md`` for the deferred-family roadmap.

See dec-040 (and dec-204 narrowing clause 3) for the out-of-band invocation
contract — no hook integration, no pipeline integration.
"""

__version__ = "0.3.0"
