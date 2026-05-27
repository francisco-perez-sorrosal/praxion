"""Praxion evals — out-of-band quality measurement framework.

Tier 1: behavioral (artifact manifest check via /eval).
Tier 2: LLM-as-judge over completed artifacts via /eval-praxion (harness/).
  - Family 1: Pipeline-outcome fidelity (ADR structure, supersession reciprocity, traceability).
  - Family 2: Behavioral-contract adherence (VERIFICATION_REPORT.md BC-rubric).
Tier 2 stubs (cost, decision quality): raise NotImplementedError pending design.

See dec-040 (and dec-draft-e1f01781 narrowing clause 3) for the out-of-band invocation
contract — no hook integration.
"""

__version__ = "0.1.0"
