---
description: Disposition decision-health findings in batch — repairs first as grouped approvals, retirement candidates one at a time, never in bulk.
argument-hint: "[--class <decay-class>] [--limit <n>]"
allowed-tools: [Read, Glob, Grep, Bash, Edit, AskUserQuestion]
disable-model-invocation: true
---

Work through the decision-health findings for this project and apply the dispositions the
user approves. The detector emits candidates and never edits a decision record; this command
is the bridge that turns a candidate into a change, and every change needs an explicit
approval.

## Arguments

`$ARGUMENTS` carries optional flags. When it is empty, work every finding the detector reports,
in the order below. When it is non-empty, parse the two flags below and **honour both** —
an unrecognised flag is an error to surface, not something to drop silently, because a dropped
`--limit` turns a deliberately narrow first pass into a full sweep the user never asked for.

| Flag | Description |
|------|-------------|
| `--class <decay-class>` | Work only one decay class (e.g. the rename class). Forward it verbatim to the detector, which takes the same flag. |
| `--limit <n>` | Stop after `n` records are dispositioned. **This command enforces it — the detector has no such flag.** Useful for a first pass over a large corpus. |

`--limit` counts records across the whole pass, not per class, and the count runs in the working
order below — so a limit reached during the repair classes means retirement candidates are never
raised at all. That is the safe direction and is intended: the classes whose disposition is
mechanical get exhausted before the class whose disposition is a judgment is ever opened.

## Process

### 1. Gather

Run `adr_health.py --json` from the project root, appending `--class <decay-class>` when the
arguments supplied one. The Praxion installer links it onto `PATH`, which is what lets this
command work in a managed project; if it is not found, fall back to
`python3 scripts/adr_health.py --json` from a Praxion checkout and mention that the installer
has not been run.

Under `--class`, say which class was scoped to when reporting. A single-class run is not a
picture of the corpus, and a count from it must never be presented as one.

**Read `withheld` before reading anything else.** A non-empty `withheld` means an oracle was
unavailable and whole decay classes were suppressed rather than guessed. Say so up front, and
do not present a class-count summary as if it were complete — a suppressed class reads as
"nothing to do here", which is the one wrong conclusion.

Findings in the `unclassified` class are the suppressed members: the detector could not
determine their cause, so it proposes nothing for them. Report them with the withheld note and
**never** work them as candidates. Their presence also means the retirement list is shorter than
it would otherwise be — a shorter list here is missing evidence, not a healthier corpus.

If there are no findings, say so and stop. Re-running after a clean pass is a no-op.

### 2. Order the work — repairs first, retirement last

**This ordering is the point of the command, not a presentation preference.**

Findings are not homogeneous. Most classes describe a *stale reference* and their repair is
mechanical, high-confidence, and reversible. One class describes a *decision that may no
longer belong*, and its disposition is a judgment that deletes standing from the record.
Presenting them together invites a bulk sweep of the second while the reader is in the rhythm
of approving the first.

So: work every repair class to completion first. Only then raise retirement candidates.

### 3. Repairs — grouped approval

For the classes whose disposition is a path fix (renames, path shapes, out-of-repo paths):
group by class and present **one approval per class**, with the full list of records visible.
The detector already names the replacement for a rename, so the change is determinate and the
approval is genuinely a single decision.

Two things to check before proposing a repair, because both silently produce a wrong edit:

- **Is the replacement already present** in that record's affected-files list? Then the
  disposition is to *drop* the stale entry, not to repoint it — repointing writes a duplicate.
- **Does the decision still stand?** Verify against the current tree, not the record's prose.
  A file can move to a differently-named, differently-shaped, sometimes differently-languaged
  successor that no rename detector will ever see.

Repair the *index* only. The body prose of a decision is a record of what was decided and
stays untouched, even where it names the path being repaired.

### 4. Retirement candidates — one at a time, and never a backlog

**Do not offer a bulk action here. Do not summarize this class as a count to clear.** A
decision can be correct and silent forever; its example files vanishing says nothing about
whether it still constrains work. The count is a residual left after every repair class is
exhausted, not a queue.

For each candidate, establish the one distinction that decides it:

| Situation | Disposition |
|---|---|
| The decision still constrains work; only its reference went stale | **Prune the stale entry.** The decision keeps its standing; the finding disappears because the defect was the entry |
| The decision's *subject* is gone — the thing it decided about no longer exists | **Retire it**, per the retirement protocol in the ADR conventions |

Ask which it is. If the user cannot tell without reading the record, read the record — that is
cheaper than a wrong retirement.

When retiring, name the removing decision in the retirement pointer *if one can be identified*.
Leave it empty rather than guessing; a wrong attribution is worse than an absent one, and the
field is a list precisely because one removal often strands several decisions.

**Retirement is not supersession.** Supersession means a later decision answered the same
question differently, so a reader can compare two answers. A removal abolishes the question.
Do not write supersession cross-references here — the conventions rule owns that distinction
and the protocols differ.

### 5. Re-open candidates

If the detector reports re-open candidates, present them separately: these are retired
decisions whose subject has come back. Confirm the returning thing is the *same* subject
before restoring the record — a path can reappear for unrelated reasons.

### 6. Apply and report

Apply only what was approved, one record at a time. After each batch, state what changed and
what remains. Close by re-running the detector so the user sees the new counts — the finding
count going down is the only evidence the dispositions actually landed.

When `--limit` was given, stop as soon as that many records are dispositioned and say plainly
that the pass stopped at the limit rather than at the end of the work — otherwise the remaining
findings read as a clean corpus. Re-running picks up where this pass stopped.

Do not commit. Leave the working tree for the user to review.

## Constraints

- **Never edit a record the user did not approve**, and never widen an approval from one
  record to its class.
- **Never change a status as a side effect of a path repair.** They are different dispositions
  with different evidence.
- **Stop and report** rather than guessing when a record's own frontmatter is malformed —
  a decision corpus with a parse error needs a human, not a best-effort edit.
