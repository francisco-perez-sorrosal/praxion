# ADR Authoring Protocols

Procedural protocols for creating and maintaining Architecture Decision Records under `.ai-state/decisions/`. Reference material for the [Software Planning](../SKILL.md) skill. For the file format, frontmatter schema, naming conventions, and finalize protocol, see the [adr-conventions rule](../../../rules/swe/adr-conventions.md) — that is the canonical source of truth.

## ADR Creation Protocol (fragment-name-at-create)

Pipeline-authored ADRs land as **fragment files** under `.ai-state/decisions/drafts/` with a provisional `dec-draft-<8-char-hash>` id. Fragments are promoted to stable `<NNN>-<slug>.md` finalized records at merge-to-main by the post-merge finalize step. Agents do **not** assign `<NNN>` themselves.

When a decision-making agent (systems-architect, implementation-planner) records a decision in `LEARNINGS.md ### Decisions Made`:

1. **Derive author identity** from `git config` — see [Identity Derivation and Filename Construction](#identity-derivation-and-filename-construction) below for the pseudocode.
2. **Build the fragment filename** `<YYYYMMDD-HHMM>-<user>-<branch>-<slug>.md`, where `<slug>` is the kebab-case decision title and `<branch>` is the sanitized current branch (`git rev-parse --abbrev-ref HEAD`).
3. **Compute the provisional id** as `dec-draft-<sha1(filename)[:8]>`.
4. **Create the fragment** at `.ai-state/decisions/drafts/<fragment-filename>.md` using the Write tool, with frontmatter `id: dec-draft-<hash>`, `status: proposed`, and `branch: <branch_slug>` (the sanitized authoring branch from step 1) plus the full schema fields (see the [Frontmatter table](../../../rules/swe/adr-conventions.md#frontmatter) in the rule for the canonical schema). Recording `branch:` lets `finalize_adrs.py` parse hyphenated branches unambiguously even when only one fragment remains in `drafts/`.
5. **Cross-references between drafts** use `dec-draft-<hash>` values for `supersedes` / `superseded_by` / `re_affirms` / `re_affirmed_by`. Finalize rewrites these to `dec-NNN` at merge-to-main.
6. **Record the decision** in `LEARNINGS.md ### Decisions Made` citing `(dec-draft-<hash>)`. Finalize rewrites this reference too.
7. **Write the `## Disconfirmation` body block** when `category: architectural`. Three sub-items are required: (a) **Falsifier** — what evidence would make this decision wrong; (b) **Steelmanned runner-up** — the strongest case for the next-best option; (c) **Reversal trigger** — the future signal that should prompt revisiting. Set `dissent:` in frontmatter to a one-line summary of the strongest objection. This block attacks the chosen option and is always-on for architectural decisions; it is not optional.
8. **Do not** manually invoke any index-regeneration script — `DECISIONS_INDEX.md` regenerates automatically at finalize.

**`affected_files` names durable, committed paths only.** Never an `.ai-work/<task-slug>/` artifact (gitignored, deleted at pipeline cleanup) and never a path *shape* containing a placeholder such as `<slug>`. `.ai-state/` paths — archived specs, ledgers, sibling decisions — are durable and remain valid. If the decision's evidence lives only in a pipeline document, cite the decision's rationale in prose instead: an entry that cannot resolve is worse than no entry, because it reads as a reference while being invisible to every consumer that resolves the field. Verify each path exists before writing it; prefer omitting the field to padding it with plausible-looking paths.

## Identity Derivation and Filename Construction

Agents implement this pseudocode before creating a fragment ADR:

```
timestamp   = now_utc_formatted("YYYYMMDD-HHMM")   # filename-safe, no colons
user_raw    = git_config("user.email") or git_config("user.name") or "anon"
user_slug   = sanitize(user_raw.split("@")[0])     # username prefix from email, if email set
branch_raw  = git_rev_parse("--abbrev-ref", "HEAD") or "detached"
branch_slug = sanitize(branch_raw)
slug        = sanitize(decision_title)              # MUST match [a-z0-9-]+ (see note below)
filename    = f"{timestamp}-{user_slug}-{branch_slug}-{slug}.md"
id          = f"dec-draft-{sha1(filename)[:8]}"
# Persist `branch_slug` into the fragment's frontmatter as `branch: <branch_slug>`
# so finalize can recover the authoring branch unambiguously, even after merge.
```

`sanitize(s)` lowercases and strips to `[a-z0-9-]` (replacing any run of other characters with a single `-`, then trimming leading/trailing `-`) and caps length at 40 characters. When both `user.email` and `user.name` are unset, use `anon` — never fabricate identity.

**The slug runs through `sanitize`, not a bare kebab-case.** All three filename components — `user_slug`, `branch_slug`, *and* `slug` — must end up matching `[a-z0-9-]+`, because the finalize step (`finalize_adrs.py`, `FRAGMENT_ADR_PATTERN = ^\d{8}-\d{4}-[a-z0-9-]+\.md$`) only sees fragments whose **whole filename** matches that schema. A title with dots, colons, or version numbers — e.g. `"Phase 0 step ordering: 0.3 must land before 0.2 core-only CI leg"` — must sanitize to `phase-0-step-ordering-0-3-must-land-before-0-2` (a literal `0.3` would strand the draft: finalize silently skips any non-matching filename, so the decision never promotes and no error is raised). Verify the constructed `filename` matches `FRAGMENT_ADR_PATTERN` before writing the fragment.

**PII note**: the fragment filename contains a sanitized email-username prefix. This is acceptable for internal project state but is not a secret — treat fragment filenames the same way as commit-author metadata, not as redacted data. Teams with stricter privacy requirements can substitute a short hash of the email address for the username prefix.

**Collision avoidance**: minute-precision timestamp + user + branch makes collisions effectively impossible in normal use. If two drafts with the same minute, user, branch, and slug do land, append `-2`, `-3`, ... to the slug at write time.

## Who Creates ADRs

Not all agents create ADR fragments. The division follows decision-making authority:

| Agent | Creates ADR fragments | Records in LEARNINGS.md |
|-------|----------------------|-------------------------|
| systems-architect | Yes | Yes |
| implementation-planner | Yes | Yes |
| implementer | No | Yes |
| test-engineer | No | Yes |
| verifier | No | Yes |
| sentinel | No | N/A |

Implementers, test-engineers, and verifiers record decisions in `LEARNINGS.md` only — the planner or architect persists significant decisions as ADR fragments.

User-authored direct-tier ADRs (no pipeline involvement) MAY be created directly at `.ai-state/decisions/<NNN>-<slug>.md` with a manually-assigned `<NNN>`, but the fragment scheme is preferred even for direct-tier authoring because it avoids `<NNN>` collisions when work is in flight on multiple branches.

## Supersession Protocol

When a new decision replaces a prior one:

1. Set `supersedes: <target-id>` in the **new** ADR frontmatter — `dec-draft-<hash>` while both are drafts; `dec-NNN` when the target is finalized.
2. Set `superseded_by: <new-id>` in the **old** ADR frontmatter (same id-form rule).
3. Change the old ADR status to `superseded`.
4. Add a `## Prior Decision` section in the new ADR body explaining what changed and why.
5. `DECISIONS_INDEX.md` regenerates automatically at finalize — do not manually invoke.

## Re-affirmation Protocol

When a new ADR re-affirms a prior one without superseding it (a re-opening was considered and rejected for lack of new evidence):

1. Set `status: re-affirmation` on the new ADR — signals a meta-decision about another decision.
2. Set `re_affirms: <target-id>` in the new ADR frontmatter (same id-form rule as Supersession).
3. Append `<new-id>` to the old ADR's `re_affirmed_by` list (create the list if absent).
4. **Do not** change the old ADR's status — it stays `accepted`; no `superseded_by` is set.
5. Add a `## Prior Decision` section in the new ADR explaining what was considered and why the prior decision still holds; name the evidence that would justify a future supersession.

Re-affirmation is stronger than silent concurrence (it forces a public record of the re-opening) and gentler than supersession (the prior decision is untouched). Use it when a prior decision is challenged, re-examined, and found still correct — not as a routine acknowledgment.

## The `architectural` Test

The canonical statement lives in `rules/swe/adr-conventions.md`. This section carries the worked
examples, the evidence that produced the test, and the measurement that calibrates it.

### Why the obvious test does not work

The natural formulation — *architectural iff it constrains an element of the architecture model* —
was measured against the corpus and failed in both readings.

Read as **"touches a component"**, it bounds nothing: the structural components tile essentially
the whole repository, so every decision touches one. Read as **"edits the model"**, fewer than 1%
of decisions tagged architectural qualified — which would mean the project made two architectural
decisions in four months.

The cause is a **granularity mismatch**, not indiscipline. ADRs decide at the level of *capability
composition* — should this be a skill, an agent, a command, or a hook; where does one agent's remit
end; should this abstraction exist. The model describes *structural containment* — which boxes hold
which. Those are different layers, and binding one to the other assumes a correspondence that is
not there. A test built on it would demote an explicit agent-boundary decision while promoting
nothing of comparable weight.

### Worked examples

Architectural — each names a component that changed:

| Decision shape | What changed |
|---|---|
| "prevent duplication via existing agents, **not a new dedicated agent**" | inventory (a component deliberately not added) |
| "ship this capability as **agent + skill + command**" | inventory + composition across families |
| "the boundary between **these two agents**" | responsibility ownership |
| "introduce a **pluggable backend abstraction**" | a boundary added |
| "replace the bespoke gate with **the framework**" | a mechanism replaced wholesale |

Not architectural — consequential, but nothing in the inventory moved:

| Decision shape | True category |
|---|---|
| review cadence for a dependency upgrade | `behavioral` |
| the deliberation method used when writing ADRs | `behavioral` |
| which label arms a human-in-the-loop gate | `behavioral` |
| a new page inside an existing surface | `implementation` |

### Applying it

Ask the falsifier first: **name the component added, removed, or whose responsibility moved.** If
the answer is a sentence about why the choice was hard rather than a component name, the decision
is not architectural — record it at its true category, where it stays searchable and costs the
reader nothing.

The published half is exact and needs no judgment: `affected_files` touching a canonical block, a
shipped template, or an onboard-contract phase is architectural by definition, because the blast
radius is every managed project.

### What is and is not mechanised

The published half is checkable from `affected_files`. **The inventory half is not** — "did the
component inventory change" is not derivable from a path list, and a gate claiming to check it
would be blind to its own subject.

What ships instead is a **measurement**, not a gate: `adr_health.py` reports the category mix
across the corpus and across a recent window, and the sentinel surfaces the recent architectural
share. The signal is *movement* against the share recorded when the test was adopted, not an
absolute threshold — inventing a threshold would be a number with no evidence behind it.

**Adoption baseline, measured the day the test landed:** `architectural` held **72% of the corpus
(227/317)** and **84% of the most recent 50 decisions**. The recent window being *higher* than the
corpus is the finding that justifies the change — under the previous definition the category was
not merely broad, it was widening. Those two numbers are the reference points; a later run showing
the recent share below 84% is the test working, and a run at or above it is the test being ignored.

### No retroactive migration

The test binds new decisions only. Bulk-retagging the existing corpus would corrupt more than it
fixed, because most historical records need human judgment to categorise correctly. The corpus as
it stands is legible evidence of what the previous definition permitted, which is worth keeping.

## Retirement Protocol

When a later decision's action removed this decision's **subject**, rather than answering its question differently:

1. Set `status: retired` on the **old** ADR.
2. Set `retired_by: [<id>, ...]` on the old ADR — a **list**, because one removal routinely strands several decisions.
3. **Do not** modify the removing decisions. They answered a different question and made no claim about this one; nothing is written on their side.
4. Add a `## Prior Decision` section to the old ADR naming what was removed, by which decision, and what would have to return for the decision to matter again.
5. `DECISIONS_INDEX.md` regenerates automatically at finalize — do not manually invoke.

### The supersession-vs-retirement test

Ask what a reader could compare. **Supersession** answers the *same question differently*, so the two answers sit side by side and the reader sees a choice that changed. **Retirement** abolishes the question, so there is no second answer to compare against.

A commit-gate decision that placed a check in "Block D, not Block C" of a bespoke hook script is retired, not superseded, by the decision that replaced that script with a hook framework: the replacement does not choose a different block, it eliminates blocks. Recording that as supersession would assert a deliberation that never happened — the later decision never weighed the block placement at all.

Retirement also exists because supersession **cannot express** the common case. `supersedes` and `superseded_by` are single-valued, so a 1:1 relation. One removal typically strands several decisions at once — a subsystem deletion can orphan five — and the reciprocal `supersedes` half is then unwritable, since the remover would need to name all of them in a field that holds one id. `retired_by` is a list for exactly this reason.

### Re-open

A retired decision is preserved, never deleted. If its subject returns — a removed path reappears, a retired component is rebuilt — flip `status` back to `accepted` and clear `retired_by`, keeping the record's full history including its retirement. Architecture that comes back finds its prior reasoning waiting rather than being re-litigated from zero. (Precedent: the tech-debt reconciler already re-opens a terminal row whose `dedup_key` recurs.)

### Why retirement is a status, not a directory

Terminal records stay in `.ai-state/decisions/`. Moving them into a subdirectory would break the path-form links that persistent documents are required to use, and would silently narrow every consumer that globs the decisions directory flat — including the next-`NNN` scan in `finalize_adrs.py`, which iterates files and skips subdirectories, and would therefore reissue an archived record's id the first time a recent decision is retired. The lifecycle separation the archive was meant to provide is delivered by `status` plus index filtering, with no file movement and no dangling links.

## Finalize at Merge-to-Main

At merge-to-main, the post-merge finalize step promotes drafts in `.ai-state/decisions/drafts/` to finalized `<NNN>-<slug>.md` records. The protocol is **idempotent** (running twice on the same state is a no-op), so duplicated invocations from the post-merge hook + `/merge-worktree` command are safe. Agents do not run finalize manually.

The full step sequence:

1. **Draft detection.** Identify drafts added in the merged range (`<merge-base>..HEAD`) under `.ai-state/decisions/drafts/`. A manual-branch mode detects drafts added by a named branch. A dry-run mode prints the planned changes without writing.
2. **NNN assignment.** For each detected draft, assign the next sequential `<NNN>` by scanning `.ai-state/decisions/` for the highest existing `<NNN>-<slug>.md` value, ignoring the `drafts/` subdirectory entirely. Assignments follow filename-sort order across the batch so the sequence is deterministic.
3. **File rename and frontmatter rewrite.** Rename `.ai-state/decisions/drafts/<fragment>.md` to `.ai-state/decisions/<NNN>-<slug>.md` (slug extracted as the trailing `-<slug>.md` component of the fragment filename). Rewrite the frontmatter `id:` field from `dec-draft-<hash>` to `dec-NNN`, and rewrite `status: proposed` to `status: accepted` (the lifecycle transition that finalize represents).
4. **Cross-reference rewrite.** Rewrite every `dec-draft-<hash>` occurrence (for each promoted draft) to its newly assigned `dec-NNN` across a bounded set of locations (the walk is bounded by design — finalize does not sweep the full repo):

   | Location | Surface to rewrite |
   |----------|-------------------|
   | `.ai-state/decisions/**/*.md` | Frontmatter `supersedes` / `superseded_by` / `re_affirms` / `re_affirmed_by`; inline body references (`[dec-draft-<hash>]` or bare). Both drafts and finalized records. |
   | `.ai-state/DESIGN.md`, `.ai-state/TECH_DEBT_LEDGER.md`, `.ai-state/TECH_DEBT_RESOLVED.md`, `.ai-state/CONSULT_LEDGER.md`, project-root `ROADMAP.md` | All occurrences — persistent files that cite the ADR a decision, debt, or consult-disposition row resolved |
   | `docs/**/*.md` | All occurrences — design notes and integration docs cite ADR ids outside `.ai-state/` (subsumes `docs/architecture.md`) |
   | `.ai-work/*/LEARNINGS.md` | All occurrences |
   | `.ai-work/*/SYSTEMS_PLAN.md`, `.ai-work/*/IMPLEMENTATION_PLAN.md` | All occurrences |
   | `.ai-state/specs/SPEC_<name>_YYYY-MM-DD.md` | Files matching the current pipeline's task slug |
5. **Index regeneration.** After all drafts in the batch promote, `DECISIONS_INDEX.md` regenerates to reflect the new finalized records. Drafts are excluded from the index by construction; the index lists only finalized `<NNN>-<slug>.md` files.

**Concurrency safety.** Finalize acquires an advisory file lock before any writes so concurrent post-merge hook invocations serialize cleanly. Exit codes: `0` for success or no-op; non-zero only when manual intervention is needed (e.g., an unresolvable filename collision). The protocol deliberately avoids rewriting arbitrary repository text; the bounded walk scope is the contract.

## Spec Archival Cross-Reference

During end-of-feature spec archival, the implementation-planner cross-references decisions from `LEARNINGS.md ### Decisions Made` with ADR files in `.ai-state/decisions/`. The archived spec's `## Key Decisions` section should link to relevant ADR files for full context.

While a pipeline is in flight, both `LEARNINGS.md` and the archived spec carry `dec-draft-<hash>` references; these are rewritten to `dec-NNN` at merge-to-main alongside the ADR fragment promotions.

## End-of-Feature Decision Verification

During the end-of-feature workflow, verify consistency between:

- Decisions in `LEARNINGS.md ### Decisions Made`
- ADR fragments under `.ai-state/decisions/drafts/` (in flight) or finalized records under `.ai-state/decisions/` (post-merge)

Check for decisions recorded in `LEARNINGS.md` but missing as ADR fragments (creation protocol was not followed), and ADR fragments without corresponding `LEARNINGS.md` entries (unusual but not necessarily an error).
