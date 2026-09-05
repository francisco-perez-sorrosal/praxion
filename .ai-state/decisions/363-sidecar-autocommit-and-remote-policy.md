---
id: dec-363
title: The sidecar autocommits on finalize and on session stop; the project never does; and the sidecar has no remote by default
status: accepted
category: behavioral
date: 2026-09-02
summary: Praxion has never auto-committed anything, deliberately. The sidecar is personal, unreviewed and linear, so the discipline differs there and only there - the finalize chain and a Stop hook commit it, while project commits stay human-owned. The sidecar gets no git remote by default, and adding one is refused when the host differs from the project origin's host unless the operator acknowledges it explicitly.
tags: [autocommit, commit-policy, data-boundary, sidecar, remote, trust-boundary, hitl]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - hooks/sidecar_autocommit.py
  - scripts/praxion-sidecar
  - scripts/finalize_chain.sh
  - docs/onboarding.md
---

## Context

Praxion auto-commits nothing today. Verified: every one of the four scripts that
touch `.ai-state/` calls `git add` and never `git commit`, and the onboarding
skill's own claim — "safe to re-run; nothing is committed" — is code-true. The
human owns every commit decision. That is a deliberate and load-bearing property
of a tool that operates inside repositories it does not own.

Sidecar placement changes the object being committed, not the principle. The
sidecar is a **personal, unreviewed, linear** repository holding one operator's
project intelligence. Nobody reviews its commits; there are no pull requests, no
branches, no history that anyone reads as a narrative. Meanwhile the tree
changes constantly and asynchronously — an ADR promotion here, a ledger
migration there, an observations append on every tool call — with no natural
moment for a human to say "yes, commit that". Applying the project's commit
discipline to it would mean either an operator running `git -C <sidecar> commit`
several times a session, or a state store whose history is a single enormous
uncommitted diff.

The second half is a data-boundary question. On a work machine, project
intelligence — ADRs, design notes, ledger rows quoting code — must stay inside
the company boundary. A sidecar with a remote is a channel out of that boundary,
and a channel created by a single convenient command.

## Decision

1. **The sidecar autocommits; the project never does.** The finalize chain
   commits the sidecar after it finishes rewriting state, and a `Stop` hook
   commits any residue at session end. The project repository receives no
   automatic commit under any placement — the existing `git add`-never-`git
   commit` contract is untouched.

1a. **The commit is serialized by an advisory lock; staging is
   pathspec-scoped.** Under the shared-live-tree model
   (`dec-364`), two concurrent pipelines produce up to four
   committers — two finalize, two `Stop` — racing on the sidecar's single
   `.git/index` and `index.lock`. The sidecar index is shared mutable state and
   is given a named owner: `praxion-sidecar commit` acquires an advisory
   `fcntl` lock scoped to the sidecar repo (`<sidecar>/.git/praxion-sidecar-commit.lock`,
   mirroring `finalize_adrs.py`'s `.finalize.lock`) before staging and releases
   it after committing; a committer that cannot acquire it waits (bounded) and,
   on timeout, defers to the next trigger rather than racing — safe because the
   discipline is idempotent. Staging is **pathspec-scoped**
   (`git add -- <written paths>`), never `git add -A`, so two committers that
   acquire the lock in sequence never stage each other's partial work. The
   held-lock ("commit-in-progress") state is modeled and reported by `doctor`,
   so a stale lock from a crashed process is diagnosable rather than surfacing
   as an opaque `fatal: Unable to create '.../index.lock'`. This closes the
   index-corruption failure mode inside the accepted shared-live-tree trade-off;
   it does not remove that trade-off (the higher-level "two pipelines see each
   other's drafts" property keeps its own reversal trigger in
   `dec-364`).

2. **The policy is a manifest field with a closed enum**, not a hardcoded
   behaviour: `on-finalize-and-stop` (default), `on-finalize`, `manual`. An
   operator who wants full control sets `manual` and the automatic paths become
   no-ops. There is deliberately **no `on-stop` value**: committing at session
   boundaries while skipping finalize-triggered commits would leave the sidecar
   inconsistent with the state finalize just rewrote, which is a state nobody
   should be able to ask for.

3. **The sidecar has no git remote by default.** A fresh sidecar is
   `git init` with no `origin`. Its history exists for recovery and for
   inspection, not for distribution.

4. **Adding a remote is trust-boundary gated.** `praxion-sidecar remote add`
   compares the proposed URL's host against the project origin's host and
   refuses a mismatch unless `--allow-foreign-host` is passed. The
   acknowledgement is **recorded in the manifest** (`foreign_host_ack`), so a
   deliberate cross-host remote reports as a pass in `doctor` while an
   unrecorded one reports as a failure — the check informs once rather than
   nagging forever.

5. **The sidecar location is announced at session start**, so an operator on a
   work machine always knows where project intelligence is accumulating without
   having to go looking.

6. Every automatic path fails open and carries a `PRAXION_DISABLE_*` opt-out,
   matching the existing hook conventions.

## Considered Options

### A — No autocommit; the operator commits the sidecar manually

Pros: perfectly consistent with Praxion's existing discipline; no new
commit-producing code anywhere; nothing surprising in `git log`.

Cons: the sidecar's value is its history, and a history that depends on an
operator remembering to commit a repository they rarely visit is a history that
will not exist. The realistic outcome is a permanently dirty sidecar, which
means recovery from it is not actually available — the main justification for a
repository rather than a plain directory disappears.

### B — Autocommit the sidecar, keep the project human-owned (chosen)

Pros: the history exists without ceremony; the property that actually matters —
Praxion never commits to a repository someone else reviews — is preserved
exactly; the policy is a manifest field, so an operator who disagrees can set
`manual`.

Cons: Praxion now produces commits, which it never has; a reader of the sidecar's
`git log` sees machine-generated messages rather than human intent; the commit
granularity is dictated by hook timing rather than by logical change.

### C — Autocommit and push

Pros: the state is backed up off-machine, which is the one thing option B does
not give; a lost laptop loses nothing.

Cons: it turns every session into an outbound data flow from a work machine, by
default, for content that quotes the employer's code. That is the wrong default
regardless of how convenient the backup is. Available as an opt-in
(`push: on-autocommit`) once a remote has been consciously added.

### D — Remote allowed freely; warn on host mismatch

Pros: less friction; the operator is an adult.

Cons: a warning at the moment of configuration is seen once and then never
again, while the data flow continues indefinitely. Refusal-plus-recorded-
acknowledgement makes the decision explicit exactly once and then stops asking,
which is strictly better on both axes.

## Consequences

**Positive.** The sidecar accumulates a real, usable history with no operator
effort, so recovery and cross-machine sync are genuinely available rather than
theoretically available. The property Praxion actually needs to protect —
never committing to a repository under someone else's review — is stated as an
invariant rather than inherited by accident from "we never commit anything". The
default is safe for the work-machine case without forbidding the personal one.

**Negative.** Praxion writes commits, which is a new capability and a new class
of thing that can go wrong; a bug in the autocommit path corrupts the store it
was meant to protect. Commit granularity is mechanical, so the sidecar's history
is a log rather than a narrative. With no remote by default, a lost machine
still loses everything — the design chooses the data boundary over the backup
and documents that as an operator responsibility rather than solving it. The
host comparison is a heuristic: a company using an external managed host for
some repositories will see false refusals until the acknowledgement is recorded.

## Disconfirmation

**Falsifier.** If operators routinely set `autocommit: manual` and then commit
the sidecar by hand, the automatic path was solving a problem they did not have
and option A was correct. Conversely, if the no-remote default is routinely
overridden within the first session — every operator immediately adding a
remote — then backup is the dominant need and the default is miscalibrated
against real use.

**Steelmanned runner-up.** Option A deserves more weight than its rejection
gives it. Praxion's blanket no-autocommit rule is not merely a habit; it is the
reason the tool is safe to point at an unfamiliar repository, and every
exception to a safety rule erodes the rule's clarity — a future contributor
reading "the sidecar autocommits" has to hold a caveat that the previous rule
did not require. Option A also has a cheap mitigation this decision does not
credit: the session-start banner could report "sidecar has N uncommitted
changes", turning the forgotten-commit failure into a visible one for a fraction
of the machinery. If a bug in the autocommit path ever corrupts a sidecar, that
mitigation plus option A becomes the right design, and the exception should be
withdrawn rather than repaired.

**Reversal trigger.** Any observed sidecar corruption attributable to the
autocommit path; or a second place in Praxion wanting to auto-commit something,
which would mean the exception has become a policy and deserves to be argued as
one rather than inherited from here.
