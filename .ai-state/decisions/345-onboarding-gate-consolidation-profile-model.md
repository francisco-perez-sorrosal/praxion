---
id: dec-345
title: Onboarding gate consolidation via a single detection-defaulted Profile question
status: accepted
category: behavioral
date: 2026-08-30
summary: Collapse the 25 onboarding AskUserQuestion fires into 3 gate slots — one detection-defaulted capability Profile plus two conditional asks — so the happy path asks at most one question.
tags: [onboarding, interface-design, cli, ux, decision-fatigue, gates]
made_by: agent
agent_type: interface-designer
branch: worktree-onboarding-unification
pipeline_tier: full
affected_files:
  - skills/onboard-project/SKILL.md
  - scripts/onboard-project
dissent: "Pacing gates are cheap insurance against an agent misreading a project's state; removing sixteen of them removes sixteen chances for the user to halt a wrong run before it writes."
---

## Context

Praxion's two onboarding surfaces fire **25 `AskUserQuestion` gates** in total — 14 in `/onboard-project`, 11 in `/new-project`. Sixteen of those 25 are `Continue / Run all rest` pacing prompts that offer no alternative outcome: the only meaningful choice they present is "keep being asked" versus "stop being asked." Two more (Gate 7 in `/onboard-project`, gates 4a–4e in `/new-project`) gate phases that either write nothing at all or duplicate a Conversation Checkpoint the orchestrator already owns.

The user mandate for the unification is explicit: *"smooth, clear, letting the user make the best decisions or delegate in happy paths with the main default options."* Decision fatigue is the named enemy.

Two properties of the existing flow make consolidation safe rather than reckless: (a) every write is additive, idempotent, and `git add`-ed by explicit path but **never committed** — so the entire flow is reversible with `git restore --staged` plus a `git diff` review; (b) pre-flight detection already computes the correct default for every optional capability (stack, ML signals, plugin scope, Obsidian availability, prior onboarding state).

Applying the `goal-disambiguation` 2×2 (ask only when intent is ambiguous **AND** a wrong guess is hard to reverse): reversibility puts nearly the entire flow in the left column, where the rule is *proceed with stated assumptions*, not *ask*.

## Decision

Replace the 25 gate-fires with **three gate slots**, of which at most two fire in any single run:

- **G1 — Mode confirm.** Fires only when directory-state detection is ambiguous, or when hackathon state is detected without a mode flag. Default = the detected mode.
- **G2 — Build intent** (`new` mode only). The free-text "what would you like to build?" question. Suppressed by `--brief "<text>"` or `--yes`.
- **G3 — Profile.** A single `AskUserQuestion` multiSelect listing the seven optional capabilities (`arch`, `quality`, `ci`, `aac`, `ml`, `obsidian`, `observability`), each **pre-checked from detection** and each carrying its detection evidence inline. Suppressed by `--yes`, `--profile`, or any `--with`/`--without`.

Everything else becomes a default acted on without a prompt, or moves to a CLI flag:

- 16 pacing gates → **dropped**, replaced by a single up-front detection announcement (strictly more informative than any of them) and per-capability progress lines.
- Gate 0.5 (`CLAUDE.md` generate vs stub) → `--claude-md <generate|stub|skip>` flag, default `generate`.
- Gate 5b (hackathon) → mode, expressed by `--hackathon` / `--mode` / G1.
- Gate 8c.3 (free-text GPU-hours budget) → written as an editable default with a printed pointer; no prompt.
- Gates 5, 8, 8b, 8c, 8d, 8e → **batched** into G3 as checkboxes.

The `Run all rest` escape hatch is retired; `--yes` supersedes it.

Two capability defaults change as part of this decision: `obsidian` flips from default-on to detection-gated (today it asks, gets "yes," then silently skips its own sub-steps when the CLI or marketplace plugin is absent), and `ci` splits out of `quality` and defaults off (it is the only capability with out-of-band prerequisites — two `gh secret set` calls plus an org Actions-allowlist entry — and installing workflows that go red on the next PR is user-visible damage).

Four reversibility guarantees are surfaced in the CLI output (not only in docs), because they are what earns the right to drop the pacing gates: nothing is committed; nothing is overwritten; everything is idempotent; `--check` previews at zero risk.

## Considered Options

### A. Keep the gates, add a `--yes` bypass (minimal change)

- **Pro**: smallest diff; no behavioural risk for existing users; the escape hatch already exists in the form of `Run all rest`.
- **Con**: does not address the mandate. The default experience — what a first-time user gets — remains 14 prompts. A bypass flag only helps users who already know the flow well enough not to need it. The `Run all rest` hatch already proves the gates are unwanted: the flow ships with a button whose purpose is to turn itself off.

### B. Three gate slots with a detection-defaulted Profile (chosen)

- **Pro**: the happy path asks once, with full information, after the detection announcement. Every question that survives is one the system genuinely cannot answer. One vocabulary (capability IDs) spans flags, checkboxes, progress lines, summary, and manifest. Hick's/Miller's limits respected (seven items, one screen).
- **Con**: fewer halt points. A user who wanted to stop mid-run must now `Ctrl-C` and `git restore --staged` rather than decline at the next gate. Mitigated by `--check`, by never committing, and by the fact that a mid-run halt already left a half-applied state under the old design too.

### C. Zero gates — pure detection, `--with`/`--without` only

- **Pro**: maximally decision-light; fully scriptable; the flow becomes a pure function of directory state and flags.
- **Con**: removes the user's only opinionated moment. `aac` and `ci` are genuinely taste-dependent and not derivable from detection; guessing them silently is the failure mode this design is trying to avoid in the other direction. Also removes the discoverability surface — a first-time user would never learn the capability tiers exist.

## Consequences

**Positive**

- 25 fires → at most 2 per run; typically 1 for an existing project, 2 for greenfield, 0 for hackathon or `--yes`.
- The one surviving free-text question (G2, build intent) is exactly the 2×2's bottom-right cell — ambiguous intent, hard-to-reverse outcome — which is the only cell that authorizes a blocking question.
- A re-run on a fully-onboarded project resolves "nothing to do" in the script and never launches a Claude session, eliminating a full 15-phase / 14-gate walk to reach the same conclusion.
- Capability IDs give the Profile, the flags, and the summary one shared vocabulary, so `--with aac` and the `[ ] aac` checkbox are the same concept spelled the same way.

**Negative**

- Sixteen fewer halt points (see `dissent`). A user who realises mid-run that the detection was wrong has `Ctrl-C` + `git restore --staged`, not a decline button.
- Two default changes (`obsidian`, `ci`) alter what a naive re-run installs relative to today. Both are documented in the summary output and in the unified doc; neither removes anything already installed.
- `--yes` cannot suppress the seed pipeline's own orchestrator Conversation Checkpoints in `new` mode. "Zero questions" is therefore true of this skill's gates only, and must be stated as such rather than implied.

**Neutral**

- The end-state artifact contract is unchanged. This decision governs how many questions precede the writes, never which files land.

## Disconfirmation

**Falsifier.** Evidence that would make this wrong: users reporting that an onboarding run installed something they did not want and would have declined at a pacing gate — specifically, a `git diff --staged` that a user rejects wholesale. A single such report against `arch` or `quality` (the two default-on capabilities with the largest footprint) would indicate the Profile's pre-checks are miscalibrated, or that the detection announcement is not being read before G3.

**Steelmanned runner-up.** Option A (keep gates, add `--yes`) is stronger than it first appears: the pacing gates cost the *expert* user almost nothing once they learn `Run all rest`, and they give the *novice* — precisely the user onboarding is for — repeated, cheap opportunities to notice that the agent has misread their project before it writes. The argument that a prompt offering only "continue" is not a real choice is weakened by the fact that the real choice it offers is `Ctrl-C`, and a prompt is a far more discoverable place to exercise it than a scrolling progress log. If detection quality turns out to be the weak link, A is the correct design.

**Reversal trigger.** Revisit if either holds: (a) two or more reports of an unwanted capability install traced to a wrong pre-check; or (b) detection accuracy for `ml` / `obsidian` / stack falls below reliable on real projects, at which point the Profile's pre-checks stop being informed defaults and become guesses — and guesses belong in questions.
