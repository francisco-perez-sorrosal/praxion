"""The roles eligible to be switched to a lean spawn.

One literal, owned by the commit gate and held apart from everything a flip commit edits (the
adoption ledger, the agent definitions): a record that lists its own eligible roles could widen
the list in the commit that switches a role, and the list would be no rule at all. Changing the
tuple is a source change of its own; the gate refuses it beside an adoption record or a flag.

The tests' driver reads and rewrites the tuple by its syntax, so keep it a plain literal bound to
`ELIGIBLE_ROLES`.
"""

ELIGIBLE_ROLES = (
    "researcher",
    "verifier",
    "discipline-consultant",
    "skill-genesis",
    "context-engineer",
)
