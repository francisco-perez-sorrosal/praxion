# Fixture: consult_no_disposition

Golden bad-case fixture for sentinel gate **P07** (Undisposed Architecture Challenges),
extended to cover discipline-consultant artifacts.

## What P07 checks (consult extension)

For each `.ai-work/<slug>/CONSULT_<discipline>.md`, P07 greps for a non-empty
`## Challenges` section (the discipline-consultant's heading — deliberately distinct
from `## Architecture Challenges`). If a `### CH-NN` entry's `**Disposition:**` field is
**absent, empty, or still the `<!-- convener, Round 2 -->` placeholder** before the next
`##` heading, P07 flags **Important**.

The convener owes each adjudication to **two** surfaces — the fragment entry beside the
claim it answers, and one `.ai-state/CONSULT_LEDGER.md` row. A populated ledger does not
discharge the fragment obligation, so a ledger row is not a defence against this finding.

## Files in this fixture

| File | Role | Expected P07 result |
|------|------|---------------------|
| `CONSULT_statistician.md` | **Golden bad-case** (unfilled placeholder) | P07 must WARN — non-empty `## Challenges` section with `### CH-01` left undispositioned |
| `CONSULT_evidence-appraiser.md` | **Golden bad-case** (field omitted) | P07 must WARN — two well-formed challenges, neither carrying a `**Disposition:**` field at all; a trailing `## Disposition Summary` table of `<!-- convener -->` cells is substituted for the per-entry fields |
| `CONSULT_statistician_no_challenge.md` | **No-false-positive control** (nothing raised) | P07 must NOT warn — no `## Challenges` section present |
| `CONSULT_statistician_dispositioned.md` | **No-false-positive control** (raised and answered) | P07 must NOT warn — two challenges, each carrying a real `**Disposition:**` (`switch-now`, `defer-with-rationale`) and a rationale |

## Bad-case description

`CONSULT_statistician.md` models a `statistician` consult that raised one falsifiable
challenge (`CH-01`, questioning an unreplicated 12% metric-delta claim) against a
convened draft. The `## Challenges` section is non-empty and the challenge is
well-formed — claim, decision it would change, settling test, confidence — but the
`**Disposition:**` field is still the `<!-- convener, Round 2 -->` placeholder: no
`switch-now`/`defer-with-rationale`/`dismiss-with-rationale` was ever recorded. This is
the pattern P07 must catch — the consultant raised a load-bearing challenge and the
convener never adjudicated it.

## Second bad case — the omitted field

`CONSULT_evidence-appraiser.md` models the shape a live consult actually produced: the
consultant wrote two well-formed challenges but **omitted the per-entry `**Disposition:**`
and `**Rationale:**` fields entirely**, improvising a trailing `## Disposition Summary`
table of `<!-- convener -->` cells in their place. This is undocumented drift — the
template in `agents/discipline-consultant.md` defines only the inline per-entry form and
carries no summary table — and it is the more dangerous of the two bad cases, because a
check phrased as "the field is empty or still the placeholder" is *satisfied by the
omission*: there is no field to find empty. Absent must count as undispositioned, or a
fragment can evade P07 by declining to write the field the check inspects.

## Control descriptions

`CONSULT_statistician_no_challenge.md` models a `statistician` consult that read the
same sources, found the draft sound on every point in its checklist, and wrote only
`## Not Challenged`. It has no `## Challenges` section at all, so P07 must emit no
warning. A consult that raised nothing to challenge is healthy, not suspicious.

`CONSULT_statistician_dispositioned.md` is the control the other three cannot supply: a
consult that **did** raise challenges and whose convener **did** adjudicate them, one
`switch-now` and one `defer-with-rationale`, each with a rationale. Without it, a P07 that
flagged every fragment carrying a `## Challenges` section would satisfy every other file
here — the bad cases would all still fail correctly and no control would object. A gate
must be shown to pass for the right reason as well as to fail for the right one.

## Gate liveness

Per `rules/swe/gate-liveness.md` (PROMPT gates are proven by a documented golden
bad-case, not a pytest canary). This directory is that proof for P07's consult-artifact
extension: two bad cases covering the two ways a disposition can be missing (written but
unfilled; never written), and two controls covering the two ways a fragment can be
legitimately clean (nothing raised; everything answered).
