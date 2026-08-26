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
| statistician | A load-bearing decision rests on a quantitative claim: an asserted effect or regression, a chosen sample or run count, a comparison across benchmarks or runs, a derived threshold or tolerance band, or a stopping rule. The mere presence of a number does not fire this predicate; the claim must be one a decision turns on | applied-statistics | Is the sample or run count adequate to detect the effect being claimed, and was that asked before collection rather than after? Is multiple-comparisons exposure across the reported set accounted for? Is any trend claim exposed to confounding or Simpson's-paradox reversal? Is a tolerance band derived from an error model or merely asserted? Was the stopping rule fixed in advance of looking? | standard | researcher, systems-architect | none |
| evidence-appraiser | A load-bearing decision rests on an **imported** claim -- a cited study, a benchmark result, a vendor or model-provider doc, a blog-post finding -- whose strength has not been appraised against what we are asking of it. The mere presence of a citation does not fire this predicate; the claim must be one a decision turns on, and it must originate outside this project. Claims computed from our own data are the statistician's, not this discipline's | evidence-appraisal | Does the primary source say what the citing text says it says, or has the claim drifted across restatements and lost its hedge? Can the source's *design* license a claim this strong, independent of what it concluded? Does our setting satisfy the assumptions the source's setting did -- the transfer question, and the most common real failure? Is the evidentiary class named (peer-reviewed, preprint, vendor, self-run benchmark) and weighted accordingly, with marketing claims quarantined rather than averaged in? Do at least two independent traditions converge before this is treated as established? | standard | researcher, systems-architect | none |
| data-structure-specialist | A load-bearing decision rests on a chosen representation: a core domain type, state shape, or schema contract that two or more components (or agents) will couple to; an architecture whose complexity concentrates in data transformations; or a lifecycle modeled as correlated nullable fields. The mere presence of a new type does not fire this predicate; the representation must be one that downstream correctness or evolvability turns on | data-structure-design | Does the representable state space exceed the legal state space, and which illegal states can consumers construct? Does every stated invariant have a named enforcement point, and at which boundary does it bind? Is identity-vs-value assigned deliberately, with a named owner for every mutable structure? Does the shape follow the dominant access patterns and cardinality, or only the domain taxonomy? Is external input parsed once at the edge, or re-validated (or blindly trusted) downstream? What is the evolution contract when the shape must change while consumers are live? | standard | systems-architect, implementation-planner | none |

## Adding a Discipline

Adding a discipline is **one row here**, plus at most **one new skill file** when the knowledge does not yet exist in the repository. It must cost zero always-loaded bytes, zero new agent files, zero manifest entries, zero consultant `tools:` or `skills:` entries, and zero new pipeline stages. A committed fitness test asserts each of those, so a violation surfaces as a red test rather than as drift.

Before adding a row, read the disposition ledger. A roster that grows faster than it accumulates dispositions is an uncalibrated router — the point of the ledger is that the decision to add discipline N+1 is made against measured outcomes, not enthusiasm.
