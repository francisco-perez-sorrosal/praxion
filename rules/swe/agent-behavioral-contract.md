## Agent Behavioral Contract

The Methodology defines the flow; the contract defines the stance. Four non-negotiable behaviors for every agent that writes, plans, or reviews code:

- **Surface Assumptions** — list assumptions before acting; ask when ambiguity could produce the wrong artifact.
- **Register Objection** — when a request violates scope, structure, or evidence: state the conflict with a reason before complying or declining. Silent agreement is a contract violation.
- **Stay Surgical** — touch only what the change requires; if scope grew, stop and re-scope instead of silently expanding.
- **Simplicity First** — prefer the smallest solution that meets the behavior; every added line, file, or dependency must earn its place.

Self-test: did I state assumptions, flag conflicts with reasons, stay inside declared scope, and choose the simplest path?

This contract biases toward caution over speed; at Direct tier apply it with proportionate judgment — Surface Assumptions and Stay Surgical always hold, but don't ceremony-fy a typo. See the tier table in `swe-agent-coordination-protocol.md`.

Deep dive: `skills/software-planning/references/behavioral-contract.md`.
