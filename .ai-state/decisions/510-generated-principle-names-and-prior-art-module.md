---
id: dec-510
draft_id: dec-draft-d170480e
title: "Kernel principle names come from the template; a prior-art module delivers the new principle"
status: accepted
category: architectural
date: 2026-11-12
summary: "The kernels' principles pointer takes its count and names from the philosophy template's headings through the generator, and a new principles-prior-art kernel module delivers the principle Standing on the Shoulders of Giants to the promethean, the systems architect and the researcher."
tags: [kernels, principles, audience, generator, drift]
made_by: agent
agent_type: systems-architect
branch: feat/process-principles
pipeline_tier: standard
affected_files:
  - claude/config/CLAUDE.md.tmpl
  - rules/_audience.yaml
  - claude/kernels/src/principles-pointer.md
  - scripts/generate_kernels.py
  - scripts/test_kernel_authored_texts.py
  - codex/config/AGENTS.md.tmpl
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04]
---

## Context

A ninth principle joins the philosophy template. Two roles never load the user file because they are switched to their kernels: the systems architect and the researcher. They reach the principle only through their kernels, and the promethean joins them once adopted. The kernels' principles pointer names the principles by hand ("The eight principles are ..."), and nothing compares that list with the template. A ninth principle would drift there silently. The manifest joins a role entry to the declared module whose audience equals its own, so no existing module serves exactly these three roles.

## Decision

1. **New module.** Declare `principles-prior-art: {audience: [promethean, systems-architect, researcher]}` and classify the new heading `scope: role`, `form: verbatim` for those three roles.
2. **Generated pointer.** The authored pointer text keeps two markers, `@@PRINCIPLE_COUNT@@` and `@@PRINCIPLE_NAMES@@`. `generate_kernels.py` fills them from the template's `### ` principle headings, through the same single heading reader that already derives `principles.md`. The count is a number word up to twenty and digits beyond; the names are joined "A, B and C". A missing, repeated or unfilled marker raises. The existing `--check` and manifest I8 then fail while committed kernels lag the template.
3. **Codex mirror.** The Codex baseline mirror gains the principle.

## Considered Options

- **New module (chosen).** Measured on scratch copies, the researcher's string goes 7,906 to 8,972 characters, about 9,010 with the pointer change, and slots stay at 9. This follows the `adr-reader` precedent.
- **Widen `principles-digest`.** All six sibling entries must name the researcher, and the researcher would receive five unrequested principles (about 1,300 tokens per spawn).
- **Put the principle in `core`.** Every role would get it, and the cartographer's string reaches about 10,200 characters, past the cap.
- **Pointer as a fully derived file.** This changes the authored-versus-generated shape (I6) for one sentence.
- **Keep the hand list and add a comparison test.** Every principle change would still need a hand edit.

## Consequences

- **Positive.** Exactly the decided audience receives the principle. Adding, removing or renaming a principle needs no hand edit. No new manifest invariant is needed, because I8 and `--check` guard it.
- **Negative.** Every kernel changes (the pointer is in `core`), so every Codex wrapper digest moves and frozen guards need re-pinning. The pointer source no longer reads as the delivered text. The researcher is about 990 characters under the cap.

## Disconfirmation

- **Falsifier.** A regenerated kernel whose pointer differs from the template's headings passes `generate_kernels.py --check`. Or a role outside the three receives the principle's text.
- **Steelmanned runner-up.** Widening `principles-digest` keeps the module count flat, and gives the researcher the same principles the architect reasons with. It loses on cost: about 1,300 extra tokens per researcher spawn for principles the user did not ask to deliver there.
- **Reversal trigger.** The researcher's string nears the cap, or the user decides the researcher should carry the full digest. Then merge the module into a widened `principles-digest`.

**Activation:** no. The trade-off is measured, with one clearly dominated runner-up.
