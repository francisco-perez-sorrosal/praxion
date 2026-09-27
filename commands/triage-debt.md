---
description: Judge tech-debt ledger candidates against the current project state and apply confirmed outcomes as dated stamps — repairs proposed per-row, discards judged against a confidence gate, unresolved rows escalated to the user rather than guessed.
argument-hint: "[--all] [--ids <td-NNN,...>] [--limit <n>]"
allowed-tools: [Read, Glob, Grep, Bash, Write, Edit, Task, AskUserQuestion]
disable-model-invocation: true
---

Triage the tech-debt ledger against the project's *current* state. `scripts/ledger_health.py`
reads the ledger, the ADR corpus and git history and computes, per active row, the delta
between the state the row was filed against and the state now — it never edits anything. This
command is the bridge: it judges each candidate, proposes an outcome, and applies only what the
user confirms. See `skills/software-planning/references/tech-debt-ledger.md § Triage` for the
outcome vocabulary and stamp grammar this command writes.

## Arguments

`$ARGUMENTS` carries optional flags. Empty means the default: every row the probe already flags
as a candidate.

| Flag | Description |
|------|-------------|
| `--all` | Judge every active row, not just candidates. Use for a first sweep — before anything is stamped, the mechanical recall is not 100%, so rows the probe misses still need a human pass. |
| `--ids <td-NNN,...>` | Judge only the named rows, ignoring candidacy. |
| `--limit <n>` | Judge at most `n` rows, in the probe's own rank order (strong tier first). Useful for a first pass over a large ledger; re-running picks up where the limit stopped. |

An unrecognised flag is an error to surface, not something to drop silently.

## Process

### 1. Gather

Run the probe from the project root:

```
ledger_health.py --digest [--all] [--ids <ids>]
```

The Praxion installer links it onto `PATH`; if it is not found, fall back to
`python3 scripts/ledger_health.py` from a Praxion checkout and mention that the installer has
not been run. `--limit` is not a probe flag — after the digest returns, keep only the first `n`
rows in `rows[]` (the probe already ranks strong tier before medium, and each tier by
evidence count).

Read the envelope before anything else:

- **`withheld`** — name every entry to the user up front. A withheld oracle means whole evidence
  classes were suppressed for some or all rows, not that those rows are clean.
- **`examined`** — report `active` / `candidates` / `unparseable` so the user knows the run's
  scope before seeing a single proposal.
- **`anchor`** — capture it; every stamp this run writes carries it.

If `rows` is empty, say so and stop. There is nothing to judge.

**Branch preflight.** The digest's `anchor` is `HEAD`, which only stands in for a proper
merge-base anchor while this command runs on the repository's default branch — the anchor-window
staleness detector (a later increment of this triage loop) resolves the anchor as
`git merge-base HEAD <default-branch>` instead. Determine the default branch
(`git remote show origin` if a remote exists, else assume the current branch is it) and compare
against `git branch --show-current`. If they differ, **refuse to apply** and say why: a stamp
written from a non-default branch would dangle the moment that branch is squashed or rebased.
Gathering and judging may still proceed — only the apply step (§4) is gated.

### 2. Judge — fan out to batches, never edit anything

Split `rows[]` into batches of about 10. Spawn one judge subagent per batch (`Task`, model
`sonnet`), passing that batch's row digests verbatim plus the instructions below. Each judge:

1. **Re-probes independently.** For every row, read the cited `file:line`s at `HEAD`, the
   named ADRs, and any cited commits. A judge proposes from what it verifies now, not from the
   digest's `evidence` array alone — the digest is a pointer to what to check, not a verdict.
2. **Proposes exactly one outcome per row**, from the bucket vocabulary in
   `tech-debt-ledger.md § Triage`:
   - **`discarded`** or **`merged`** (bucket 1) — only when the re-probe itself refutes the
     row's premise: a `file:line` at `HEAD` that contradicts it, a named decision, or a named
     state change. **This is the discard confidence gate.** Any judgment short of that —
     including any "this probably isn't worth doing" call — is `escalated`, never `discarded`.
     Value judgments belong to the user, never the judge.
   - **`realigned`** (bucket 2) — the row is still applicable and worth doing, but its location,
     notes citations, or severity drifted. Propose the new field values (`location` / `class` /
     `severity` / `goal-ref-value`) and the prior premise to keep in the stamp.
   - **`escalated`** (bucket 3) — the subject moved so far that a rewrite needs a judgment call,
     or the only open question is whether the row is still worth doing. No ledger write; this is
     a recommendation for the user, not a verdict.
   - **`kept`** (bucket 4, implicit) — the row's premise still holds. The evidence, if any, does
     not survive re-probing.
3. **Writes `.ai-work/triage-debt-<run-id>/TRIAGE_PROPOSALS_<batch>.md`** (never the ledger):
   one entry per row with `id`, `bucket`, `outcome`, the evidence (`file:line`, decision id, or
   state-change description) that justifies it, the proposed new cell values when `realigned`,
   and a one-sentence rationale.

Judges never touch `.ai-state/TECH_DEBT_LEDGER.md` or `TECH_DEBT_RESOLVED.md`. Only §4 does,
and only after the user confirms.

### 3. Merge and confirm

Read every `TRIAGE_PROPOSALS_<batch>.md` fragment and merge them into one pass over all rows.

Present **one confirmation table** covering bucket 1 (`discarded` / `merged`) and bucket 2
(`realigned`) proposals — one row per proposal, with the evidence visible next to the outcome so
a thin-evidence discard reads differently from a well-evidenced one. Wait for the user's
confirmation before applying anything from this table; an unconfirmed row is dropped, not
applied with a default.

Bucket 4 (`kept`) proposals are the mechanical, reversible half — a stamp records that the row
was checked and nothing moved, with no status or field change. Present them as **one bulk
summary** (count and row ids, not a full table) and ask for a single yes/no to apply all of
them, the same low-ceremony gate a wholly mechanical repair class gets elsewhere. Anything the
user does not want stamped stays unjudged and reappears on the next run.

Bucket 3 (`escalated`) proposals are never part of a confirmation table — see §5.

### 4. Apply

Apply only confirmed outcomes, one row at a time. For each:

1. **Build the stamp** per the grammar in `tech-debt-ledger.md § Triage`, using the anchor
   captured in §1:
   - `kept`: append `` // [triage <today> @<anchor>] kept: <file:line> <why>``.
   - `realigned`: rewrite `location` / `class` / `severity` / `goal-ref-value` to the proposed
     values, keep `id` and `first-seen` unchanged, append
     `` // [triage <today> @<anchor>] realigned from <old-base-key>: <prior premise>`` — the
     `from <old-base-key>` clause only when the base key actually changed.
   - `discarded`: set `status: wontfix`, append
     `` // [triage <today> @<anchor>] discarded: <the decision or state change>``.
   - `merged`: set `status: wontfix` on the absorbed row, append
     `` // [triage <today> @<anchor>] merged into <survivor-id>``; append
     `` // [triage <today> @<anchor>] kept: <evidence> absorbed <absorbed-id>`` to the survivor.
2. **Check the stamp before writing it** — grammar first, then every anchor it cites:

   ```
   ledger_health.py --row <td-NNN> --check-stamp '<stamp text>'
   ```

   Exit 0 prints `ok`. Exit 1 prints one `refused:` line per problem — a malformed stamp, a
   `dec-NNN` that is not a finalized decision, a `td-NNN` that is not a ledger row or is the row
   itself, a commit not reachable here, a cited path (or a `kept` stamp's evidence path) missing
   at `HEAD`, a merge that names no other active row as survivor, or a row that is not active.
   A refused stamp is never written: skip the row and report the reasons. This is the
   code-level backstop behind the discard confidence gate — the judge's confidence and the
   user's confirmation are necessary, but a stamp that merely *shapes* like it cites something
   checkable is refused regardless of either.
3. **Write the edit** to whichever file (`TECH_DEBT_LEDGER.md` or `TECH_DEBT_RESOLVED.md`)
   currently holds the row — `status` and `notes` only, plus `location` / `class` / `severity` /
   `goal-ref-value` for a `realigned` row. Never append a new row.

After every row that could be applied has been applied, run, in order, from the project root:

```
check_state_ledgers.py --backfill
check_state_ledgers.py --check
```

Both tools are on `PATH` after the Praxion installer; from a Praxion checkout without it, run
them as `python3 scripts/<tool>`.

`--backfill` re-keys any row whose `notes` edit changed a discriminated `dedup_key`; `--check`
then proves cross-file uniqueness. **If `--check` exits non-zero, stop and report** — the ledger
is left exactly as `--backfill` wrote it (never rolled back), and the failing rows are named for
the user.

### 5. Report

Write `.ai-work/triage-debt-<run-id>/TRIAGE_ESCALATIONS.md`: every bucket-3 (`escalated`) row,
with its evidence and the judge's recommendation, one entry per row — never a bulk list, since
each is a judgment call for the user, not a batch of identical repairs.

Report to the user:

- which rows were applied, by outcome;
- which rows were skipped at §4 (malformed stamp, unresolved anchor) and why;
- which rows were **re-keyed** by `--backfill` (their `dedup_key` changed because their `notes`
  changed);
- the escalation list's location and count.

**Propose, never run, a `chore(state)` commit** covering the ledger pair's edits. Do not commit
or push without explicit approval.

## Constraints

- **Judges never edit the ledger.** Only §4, and only after confirmation.
- **Never widen a confirmation** from one row to a class it was not shown for — the bucket-4
  bulk approval is the one deliberate exception, and it is deliberate because those writes are
  purely additive and carry no status or field change.
- **A `discarded` proposal with no re-probe evidence is `escalated`**, never nudged through on a
  vague rationale. This applies to the judge in §2 and is enforced again, mechanically, in §4.
- **Stop and report** rather than guessing when a row's own fields are malformed, or when
  `--check` fails after apply — a ledger with a structural problem needs a human, not a
  best-effort edit.
