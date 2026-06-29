---
id: dec-draft-1def3b96
title: clean_work_safety reads the registry's cleanup_policy as the file→severity-class source
status: re-affirmation
category: architectural
date: 2026-06-29
summary: Wire clean_work_safety to source each artifact's deletion-severity class from artifact_registry's cleanup_policy (Option a — registry supplies file→class, scanner keeps content-predicates + codes/remedies, per-dir aggregation unchanged), discharging dec-256's reversal-trigger and re-affirming the declarative-spine bet.
tags: [artifact-registry, cleanup-policy, clean-work, deletion-safety, declarative-spine, registry-consumer, ea-11, one-way-door]
made_by: agent
agent_type: systems-architect
branch: ea11-cleanup-policy-reader
pipeline_tier: standard
affected_files:
  - scripts/clean_work_safety.py
  - scripts/test_clean_work_safety.py
  - scripts/artifact_registry.py
re_affirms: dec-256
dissent: Option (a) leaves the per-file content-predicates and reason codes/remedies inside clean_work_safety, so the registry supplies only the severity *class*, not the full deletion contract — a future reader still consults two places to know exactly when a file triggers its class; the registry is read but not the sole source of truth.
---

## Context

`dec-251` grew `scripts/artifact_registry.py` into a declarative spine carrying `production_gate` +
`cleanup_policy`, recording the dissent that those fields were *populated but not read*. `dec-256` split
`detection_gate` from `production_gate`, wired `build_doc_manifest` as the spine's **first reader**, and
explicitly left `cleanup_policy` unread — closing EA-11 only *partially* and recording a **reversal-trigger**:
"if the per-artifact `cleanup_policy` reader never materialises (the granularity gap proves fundamental) …
collapse both back into documented `production_gate` semantics."

EA-11 is that reader. `scripts/clean_work_safety.py` — the classifier that drives what `/clean-work`
**DELETES** from gitignored `.ai-work/<slug>/` directories — currently hardcodes each artifact's deletion
severity inline (`"block"` / `"warn"` literals in `detect_reasons()`). The registry independently encodes the
*same* mapping in `cleanup_policy`: the 8 artifacts with `cleanup_policy != "delete"` are **exactly** the 8
files the classifier checks (`WIP.md`/`REWORK_MANIFEST.md` = `block-if-active` → BLOCK; `LEARNINGS.md`,
`VERIFICATION_REPORT.md`, `traceability.yml`, `SYSTEMS_PLAN.md`, `RECOVERY_LOG.md`, `PRE_REFACTOR_PLAN.md` =
`consume-marker` → WARN). The registry's own comment says `cleanup_policy` "mirror[s] clean_work_safety.py's
deletion classes" — so the duplication is acknowledged drift waiting to happen.

⚠ **This is a one-way-door change.** Deletion of a gitignored `.ai-work/` directory is irreversible; a wrong
classification deletes a file the user wanted to keep. The refactor must be **behavior-preserving and
deletion-monotonic** (delete LESS, never MORE).

The unavoidable design question: the registry encodes the per-file **class**, but `clean_work_safety`
produces a per-**directory** verdict by aggregating per-file `Reason`s, and the per-file **content
predicate** (WIP unchecked `- [ ]`; VERIFICATION only when LEARNINGS lacks the merge marker; PRE_REFACTOR
only when not `[CONSUMED]`; SYSTEMS_PLAN REQ-id AND no `traceability.yml` — the `elif`) plus the reason
`code`/`remedy` live ONLY in the scanner. How should per-file policy reconcile with the per-dir verdict?

## Decision

**Option (a): the registry supplies the file→severity-**class** mapping; `clean_work_safety` keeps the
per-file content-predicates and the reason `code`/`remedy` strings; the per-directory aggregation (BLOCK if
any block-severity reason, elif any → WARN, else SAFE) is unchanged.**

Concretely: a read-only projection helper `cleanup_policy_for(name)` is added to `artifact_registry.py`
(mirroring `dashboard_artifacts_ordered()`); `clean_work_safety` imports it (the same sibling-import
mechanism `from _repo_root import …` already uses), maps policy→severity via
`{block-if-active: block, consume-marker: warn, archive: warn, delete: safe}` with a conservative
WARN default for unknown/unregistered policies, and replaces each hardcoded `"block"`/`"warn"` literal in
`detect_reasons()` with that lookup. No artifact's `cleanup_policy` value or the policy vocabulary changes.

Because the map is 1:1 with today's literals, every verdict is preserved (empty `--json` dry-run diff over
the live `.ai-work/` dirs); because the default is WARN and `archive`→WARN, the gate can only ever become
MORE conservative, never less.

**Relationship to dec-256 — RE-AFFIRM, not supersede.** Building this reader is the precise event dec-256's
reversal-trigger watched for. The reader *materialising* (and doing so behavior-preservingly) confirms the
declarative-spine bet rather than collapsing it; dec-256's `detection_gate` split and three reclassifications
are untouched and remain correct. Per the Re-affirmation Protocol this ADR is `status: re-affirmation`,
`re_affirms: dec-256`, and dec-256 gains a `re_affirmed_by` entry while staying `accepted`.

## Considered Options

### Option (a) — registry supplies file→class; scanner keeps predicates + codes/remedies (CHOSEN)

- **Pros:** the only behavior-preserving option (empty dry-run diff) — mandatory for a one-way-door deletion
  change; smallest honest read (one projection helper + one map + eight literal→lookup substitutions); the
  registry becomes the genuine source of the file→class mapping (closes EA-11) with no signature or JSON
  contract change; a set-equality drift test makes the new coupling self-guarding.
- **Cons:** the registry supplies only the *class*, not the content-predicate or codes/remedies, so the full
  deletion contract still lives in two files (the recorded `dissent:`).

### Option (b) — per-file granularity (report/delete individual files within a directory)

- **Pros:** would let `/clean-work` delete safe files inside an otherwise-WARN/BLOCK directory; arguably the
  "fullest" use of a per-file policy field.
- **Cons:** introduces a **new deletion semantic** — partial-directory deletion — where today the task
  directory is the atomic unit. That is a deliberate *behavioral delta*, not a behavior-preserving read; it
  fails KS2/KS3, demands explicit sign-off and individual tests, and is exactly the wrong shape for closing
  EA-11's narrow "make it read" gap on a one-way-door surface. Rejected (may return as its own scoped task).

### Option (c) — hybrid (read the class now, scaffold per-file granularity behind a flag)

- **Pros:** keeps a door open to (b) without committing to it.
- **Cons:** adds machinery (a flag, a per-file code path, more tests) for a future need we do not have —
  violates Simplicity First / Incremental Evolution, and grows the very surface a one-way-door change should
  keep minimal. Rejected.

## Consequences

**Positive:**
- `cleanup_policy` gains its reader; EA-11 is fully closed and dec-251's original "populated, not read"
  dissent is discharged for the second (and last core) field.
- The file→class mapping has a single source of truth; the registry comment "mirrors clean_work_safety's
  deletion classes" becomes literally true instead of an honor-system duplicate.
- The new read is load-bearing and self-guarding (the set-equality drift test bites on divergence).

**Negative / costs:**
- The deletion contract is split across two files (class in the registry, predicate + codes/remedies in the
  scanner) — the accepted `dissent:`.
- A new coupling: the scanner's predicate set must track the registry's non-`delete` set (guarded by the
  drift test, but a maintenance fact).

## Disconfirmation

- **Falsifier:** the old-vs-new `--json` dry-run diff over the live `.ai-work/` dirs is **non-empty**, or any
  characterization pin that was green on the unchanged code fails after the refactor — either proves the read
  silently changed a deletion verdict and (a) was mis-executed (or is wrong).
- **Steelmanned runner-up (Option b):** a `cleanup_policy` attached *per artifact* most naturally expresses a
  *per-file* deletion decision; aggregating it back up to a whole-directory verdict arguably wastes the
  field's granularity, and a user with one stale BLOCK file in an otherwise-cleanable directory is forced to
  keep the whole directory. If partial-directory cleanup becomes a real, repeated need, (b) is the design the
  field was *shaped* for, and (a) will look like it under-used the data.
- **Reversal trigger:** if partial-directory deletion becomes a recurring, signed-off requirement, revisit
  (a) and promote to (b) as its own behavioral-delta task — at which point the flat per-artifact
  `cleanup_policy` may need to grow a per-file predicate encoding, which is the evidence that would supersede
  *this* decision (not dec-256).

## Prior Decision (re-affirmation of dec-256)

dec-256 left `cleanup_policy` unread and recorded a reversal-trigger naming "the per-artifact `cleanup_policy`
reader never materialis[ing]" as the signal to collapse the spine back. This ADR **materialises that reader
behavior-preservingly**, so dec-256's bet is confirmed, not overturned: its `detection_gate` split, the
three production/detection reclassifications, and the `build_doc_manifest` reader all stand. dec-256 remains
`accepted`.

What a *future supersession* of dec-256 would require (the evidence bar this re-affirmation sets): a
demonstrated need that the spine's one-policy-class-per-artifact model **cannot** express — e.g. partial-
directory deletion (Option b) forcing a per-file predicate field, or `detection_gate` proving to add no
breadth a year on (dec-256's own falsifier). Absent such evidence, the spine — now with both `production_gate`
(read by `build_doc_manifest`) and `cleanup_policy` (read by `clean_work_safety`) wired to consumers — is
the standing design.
