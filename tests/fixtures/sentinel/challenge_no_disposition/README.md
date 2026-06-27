# Fixture: challenge_no_disposition

Golden bad-case fixture for sentinel gate **P07** (Undisposed Architecture Challenges).

## What P07 checks

For each `.ai-work/<slug>/INTERFACE_DESIGN.md` and `.ai-work/<slug>/TRANSACTIONS_DESIGN.md`,
P07 greps for a non-empty `## Architecture Challenges` section. If found and no disposition
paragraph follows (no "Status:", "Decision:", or "Resolved:"), P07 flags **Important**.

## Files in this fixture

| File | Role | Expected P07 result |
|------|------|---------------------|
| `INTERFACE_DESIGN.md` | **Golden bad-case** | P07 must WARN — non-empty `## Architecture Challenges` section with no recorded disposition |
| `INTERFACE_DESIGN_no_challenge.md` | **No-false-positive control** | P07 must NOT warn — no `## Architecture Challenges` section present |

## Bad-case description

`INTERFACE_DESIGN.md` models a token refresh API design with a genuine architecture
challenge (the OAuth 2.0 parallel refresh race condition). The `## Architecture Challenges`
section is non-empty and describes the options clearly, but there is **no disposition**:
no "Status:", no "Decision:", no "Resolved:" paragraph. This is the pattern P07 must catch —
the interface designer raised a load-bearing question and left the pipeline without a recorded
answer.

## Control description

`INTERFACE_DESIGN_no_challenge.md` models a trivial health check endpoint. It has no
`## Architecture Challenges` section at all, so P07 must emit no warning. A design that
never raised an architecture challenge is healthy, not suspicious.

## Gate liveness

Per `rules/swe/gate-liveness.md` (PROMPT gates are proven by a documented golden bad-case,
not a pytest canary). This directory is that proof for P07. The no-false-positive control
here satisfies AC3.
