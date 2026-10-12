"""Process-adherence eval: does a spawned Praxion role follow its own process?

Each task runs one role as a spawned subagent of a fresh headless
``claude -p`` session, in two paired arms (``full``: today's inherited
context; ``lean``: the role with ``omitClaudeMd``), and each session is graded
into exactly one outcome per check. A pure verdict core then compares the
arms pair by pair on the declared flip rule: no regression on any mechanical
check, non-inferiority within a declared margin on every judged check.

The data model (:mod:`.model`) is closed sums with their invariants enforced
at construction; the verdict (:mod:`.verdict`) is pure arithmetic over it.

Out-of-band rule: every session costs money, so this package is reachable
only through its own opt-in console entry, ``praxion-evals-adherence``
(:mod:`.cli`). No hook, workflow, pre-commit configuration, agent prompt or
``harness/`` module names or imports it, and no module but the console entry
imports the console entry.
"""
