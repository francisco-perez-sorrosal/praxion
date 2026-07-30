# Fixture: consult_no_disposition

Golden bad-case fixture for sentinel gate **P07** (Undisposed Architecture Challenges),
extended to cover discipline-consultant artifacts.

## What P07 checks (consult extension)

For each `.ai-work/<slug>/CONSULT_<discipline>.md`, P07 greps for a non-empty
`## Challenges` section (the discipline-consultant's heading — deliberately distinct
from `## Architecture Challenges`). If a `### CH-NN` entry's `**Disposition:**` field is
empty or still the `<!-- convener, Round 2 -->` placeholder before the next `##`
heading, P07 flags **Important**.

## Files in this fixture

| File | Role | Expected P07 result |
|------|------|---------------------|
| `CONSULT_statistician.md` | **Golden bad-case** | P07 must WARN — non-empty `## Challenges` section with `### CH-01` left undispositioned |
| `CONSULT_statistician_no_challenge.md` | **No-false-positive control** | P07 must NOT warn — no `## Challenges` section present |

## Bad-case description

`CONSULT_statistician.md` models a `statistician` consult that raised one falsifiable
challenge (`CH-01`, questioning an unreplicated 12% metric-delta claim) against a
convened draft. The `## Challenges` section is non-empty and the challenge is
well-formed — claim, decision it would change, settling test, confidence — but the
`**Disposition:**` field is still the `<!-- convener, Round 2 -->` placeholder: no
`switch-now`/`defer-with-rationale`/`dismiss-with-rationale` was ever recorded. This is
the pattern P07 must catch — the consultant raised a load-bearing challenge and the
convener never adjudicated it.

## Control description

`CONSULT_statistician_no_challenge.md` models a `statistician` consult that read the
same sources, found the draft sound on every point in its checklist, and wrote only
`## Not Challenged`. It has no `## Challenges` section at all, so P07 must emit no
warning. A consult that raised nothing to challenge is healthy, not suspicious.

## Gate liveness

Per `rules/swe/gate-liveness.md` (PROMPT gates are proven by a documented golden
bad-case, not a pytest canary). This directory is that proof for P07's consult-artifact
extension. The no-false-positive control here satisfies AC3.
