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
7. **Do not** manually invoke any index-regeneration script — `DECISIONS_INDEX.md` regenerates automatically at finalize.

## Identity Derivation and Filename Construction

Agents implement this pseudocode before creating a fragment ADR:

```
timestamp   = now_utc_formatted("YYYYMMDD-HHMM")   # filename-safe, no colons
user_raw    = git_config("user.email") or git_config("user.name") or "anon"
user_slug   = sanitize(user_raw.split("@")[0])     # username prefix from email, if email set
branch_raw  = git_rev_parse("--abbrev-ref", "HEAD") or "detached"
branch_slug = sanitize(branch_raw)
slug        = kebab_case(decision_title)
filename    = f"{timestamp}-{user_slug}-{branch_slug}-{slug}.md"
id          = f"dec-draft-{sha1(filename)[:8]}"
# Persist `branch_slug` into the fragment's frontmatter as `branch: <branch_slug>`
# so finalize can recover the authoring branch unambiguously, even after merge.
```

`sanitize(s)` lowercases and strips to `[a-z0-9-]` (replacing any run of other characters with a single `-`) and caps length at 40 characters. When both `user.email` and `user.name` are unset, use `anon` — never fabricate identity.

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
