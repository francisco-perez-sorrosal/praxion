# Discipline Registry

The complete roster of consulting disciplines, as data. One row per discipline; adding a discipline is adding a row. Back to [SKILL.md](../SKILL.md).

This file is read at two moments: by a **convener** *before* spawning a consultant (to pick which discipline the signal calls for, and how hard to route it), and by the **consultant** *after* spawn (to resolve its `Discipline:` directive into obligations and a runtime skill binding). Both readers need the same table, which is why the roster lives here as a reference file rather than inside an agent body — an agent body is unreadable before its own spawn.

**A discipline absent from this table does not exist.** A consultant handed an unmatched `Discipline:` value returns `[BLOCKED]`; it never improvises a substitute.

## Row Schema

| Field | Purpose |
|---|---|
| `discipline` | Registry key; the value carried by the `Discipline:` spawn directive. Methodological, never sociodemographic |
| `fires-when` | Authored trigger predicate — the signal class that convenes this discipline. Restrictive by construction; "any numeric claim" is not a predicate |
| `binds-to` | Skill name(s) loaded at runtime through the `Skill` tool. **Never** added to the consultant's `skills:` frontmatter |
| `challenge-obligations` | What this discipline *must* interrogate when convened — its non-negotiable checklist |
| `difficulty-hint` | `routine` / `standard` / `high-stakes`. Input to the consultant's single generic routing policy; carries no model alias of its own |
| `attaches-to` | Which pipeline stage(s) may convene it |
| `lens-collision` | `none`, or the named evaluation lens whose owning artifact this discipline shares. A non-`none` value obliges the author to document an escalation relationship between the two mechanisms, or to supersede the lens catalog |

Every field is required on every row. A field left blank is a populated-looking absence, and the committed fitness test treats it as a failure.

## Registry

| discipline | fires-when | binds-to | challenge-obligations | difficulty-hint | attaches-to | lens-collision |
|---|---|---|---|---|---|---|

## Adding a Discipline

Adding a discipline is **one row here**, plus at most **one new skill file** when the knowledge does not yet exist in the repository. It must cost zero always-loaded bytes, zero new agent files, zero manifest entries, zero consultant `tools:` or `skills:` entries, and zero new pipeline stages. A committed fitness test asserts each of those, so a violation surfaces as a red test rather than as drift.

Before adding a row, read the disposition ledger. A roster that grows faster than it accumulates dispositions is an uncalibrated router — the point of the ledger is that the decision to add discipline N+1 is made against measured outcomes, not enthusiasm.
