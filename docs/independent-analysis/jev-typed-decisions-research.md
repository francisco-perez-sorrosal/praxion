---
title: Jev and Typed Decisions in Praxion — Routing, Gates and Compaction with a System-One Model
type: independent-analysis
diataxis: explanation
audience: architect / maintainer
status: spike (research + ranked integration list; no implementation)
date: 2026-09-23
updated: 2026-11-01 (§10, Haiku 5.5 addendum)
head_sha_analyzed: 29f9c7f1
author: Francisco Perez-Sorrosal (analysis run as a two-lens Spike with Claude Code — one external product lens, one internal decision-site lens, collected independently and reconciled here)
companion: skill-selection-code-mode-research.md
evidence: research-evidence/2026-09-23-codemode-jev/
verification_legend:
  VERIFIED: primary source fetched, file:line read, or number produced by a stated command
  SINGLE-SOURCE: one source, not independently confirmed
  ASSUMPTION: stated belief that shapes a recommendation; falsifier named where possible
---

# Jev and Typed Decisions in Praxion

> **Scope.** A Spike, not an implementation. The questions were:
>
> - What is Jev ([TypeSafe](https://docs.typesafe.ai/introduction))?
> - How good is the evidence behind it?
> - Where in Praxion's process and artifacts could it simplify work, above all routing, but also gates, triage and compaction?
> - Should Praxion adopt [`fast-jev-compaction`](https://github.com/tamaratran/fast-jev-compaction) or build its own?
>
> The output is a ranked integration list, from easy proofs of integration to elaborate builds. Jev launched on **2026-09-15**, eight days before this analysis, so every finding is early and should be re-checked before any build. (One fetch pass returned 2026-09-24, which is later than today's date; the 09-15 date is consistent with the independent evaluations published on 09-20.)

## 0. TL;DR

> **Addendum, 2026-11-01:** Haiku 5.5 now lists at a tenth of the Haiku 4.5 prices this report used, and one independent re-run puts it level with Jev on two of three tasks. The recommendation stands; see §10.

- **What Jev is.** A non-autoregressive "System One" model. You send a `state` and a set of typed questions, and it answers all of them in parallel in one pass. The question types are:
  - **Choice**: pick from ≤255 options, returning a probability distribution and a confidence.
  - **Score**: a rubric of 2–10 levels.
  - **Noul**: a truth value in [0, 1].

  It does no text generation and no reasoning. Pricing is **$0.042 per million input tokens, and output is free**. Limits are 64k tokens per request and 32k for state plus the longest question, with 1,200 req/min. Observed latency is ~370 ms. VERIFIED (official docs, fetched today).
- **Independent evidence cuts both ways:**
  - **Asked as one question**, Jev lost clearly to Claude Haiku 4.5: **62.6% vs 81.3%** on a 2,000-email phishing benchmark.
  - **Decomposed** into five atomic questions and combined with a logistic regression fitted on labels, it matched Haiku (**95.0% vs 93.2%**, not significant) at **12–27× lower cost**.
  - **Calibration outside its training distribution is poor:** ECE 0.107, 4.4× the noise floor. On questions whose answer isn't in the state it was right **44.7%** of the time at an average stated probability of **0.74**.

  VERIFIED ([beri.net, 2026-09-20](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval)). A second independent test agrees on speed and cost, and disputes TypeSafe's headline "193.6× faster / 444.6× cheaper" as self-benchmarked ([jock.pl](https://thoughts.jock.pl/p/jev-typesafe-system-one-model-benchmark-2026)).
- **The lesson for Praxion.** The evaluation author put it this way: *"accuracy and the calibration aren't in the box. They come from how you break the decision down, the labels you check it against, and the per-question fit you maintain."* **The durable value for Praxion is the *typed-decision discipline*, not the vendor.** Praxion already holds the labels this needs:
  - the calibration log (tier chosen, plus a retrospective verdict);
  - ~390 ADRs, each with a category;
  - consult-ledger dispositions;
  - autofix outcomes.
- **Don't adopt `fast-jev-compaction`.** Its central claim, replacing Claude Code's compaction, rests on an early-access, default-off "function hooks" surface. That surface is absent from the [official hooks reference](https://code.claude.com/docs/en/hooks), which today lists five hook types and gives `PreCompact`/`PostCompact` no way to supply the summary. Beyond that, its own open issues report:
  - compaction undone on `--resume` (166–168k tokens reloaded vs 28k native, #89);
  - Cloudflare's WAF blocking exactly the shell/SQL/code payloads a coding session contains (#97);
  - repeated compaction never re-considering earlier content (#70);
  - an independent replay in which no typed-decision selector beat a naive **head+tail truncation** baseline by more than 3 points (#99).

  The repo was built in about a day by an autonomous coding agent and has been dormant since. VERIFIED (repository read directly; `gh api`).
- **Recommendation.** Build a small, **backend-neutral typed-decision seam** plus an **offline replay harness** over Praxion's labelled corpora. Evaluate three backends on the same decisions: heuristics, Claude Haiku 4.5 or Claude Code's native `prompt` hooks (no new vendor), and Jev. Promote a backend to *advisory, confidence-gated* use only where it wins on Praxion's own labels with per-question calibration. Never make Jev the sole decider of a gate. The rankings in §6 start with offline replays that carry zero runtime risk and produce useful findings even if Jev loses.

## 1. What Jev is (VERIFIED, official docs)

| Property | Value |
|---|---|
| Model | `jev-1.13.0` (the `jev-latest` and `jev-preview` aliases point to it); a published "jaggedness" page lists known failure modes |
| Endpoint | `POST https://api.typesafe.ai/v1/systemone`, Bearer auth |
| Request | `{state: string|object|array, model, questions: {key: {type: noul|choice|score, instructions, criteria}}}` |
| Response | `answers.{key}`: Noul returns `noul` ∈ [0, 1]. Choice returns `choice`, `probabilities` and `confidence`. Score returns `score` (can fall between levels), `legend`, `probabilities` and `confidence` |
| Limits | 64k tokens per request, 32k for state plus the longest question. Choice ≤255 options; Score 2–10 levels. Text only; English best |
| Price, rate | $0.042 per million input tokens, output free. 250k tok/s, 1,200 req/min; limits adjust dynamically; no SLA found |
| Confidence | Derived from the *shape* of the distribution (for 3 options roughly `(3·p_max − 1)/2`), so it is nearly redundant with the top probability. There is no separately calibrated signal |
| SDKs | `typesafe-sdk` (Python), a JS SDK, and a Claude Code skill (`typesafe-ai/skills`) |
| Data | "Not trained on customer requests." **Zero data retention is enterprise-only.** The default-tier retention period and data residency are **not disclosed** |
| Known failure modes (vendor) | Reads literally; can't count or do arithmetic; can't order dates; weak at multi-hop reasoning and double negatives; distracted by irrelevant state; **no prompt-injection defence**; no consistency guaranteed *across* separately asked questions |
| Vendor's own positioning | The "Jev with coding agents" page says it is **not** a replacement for the LLM behind a coding agent. It is a decision primitive that code calls |

The company is TypeSafe AI (founder ex-OpenAI; ~$40M led by DCVC). That comes from secondary press, SINGLE-SOURCE-level.

## 2. The evidence, sorted by independence

| Source | Independence | What it shows |
|---|---|---|
| TypeSafe launch blog / docs | Vendor | "193.6× faster / 444.6× cheaper" and ~68% agreement, scored against a reference **averaged from two frontier LLMs' answers**, not ground truth. Quarantine as marketing |
| [beri.net](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval) (2026-09-20) | Independent, methodology disclosed | Single question: 62.6% vs Haiku 81.3%. Decomposed with fitted weights: 95.0% vs 93.2%. ECE 0.107 out of distribution. Choice/Score **overconfident** (refit temperature ≈3.3), Noul **underconfident** (≈0.66). A pre-registered follow-up found accuracy **flat from confidence 0.50 to 0.95**, reaching 100% only at ≥0.99 (about 60% of traffic), and zero out-of-scope inputs flagged, because the question types force a valid answer |
| [jock.pl](https://thoughts.jock.pl/p/jev-typesafe-system-one-model-benchmark-2026) | Independent, self-caveated n=40 | 370 ms vs Haiku 1.2 s. $1 buys ~51.6k Jev triages vs ~2k Haiku. 1 error in 40, and it carried low confidence. Hit `529 overloaded` on 5 of 6 calls during launch week |
| [KDnuggets](https://www.kdnuggets.com/what-everyone-is-getting-wrong-about-typesafe-ais-jev) and the HN launch thread | Independent opinion | "Zero hallucinations" means *no out-of-schema outputs*, not *no wrong answers*. Existing structured outputs already provide schema conformance. Two unrelated authors converge on this |
| Open-source clones (Laya 421M, SWE-Pruner 0.6B, Needle 3) | Community, days old | Typed decisions on local hardware. Relevant as a **future private backend** |

**Convergence** across two or more independent sources:
- Jev is cheap and fast, genuinely.
- Its accuracy depends on decomposing the decision and on labels.
- The vendor's headline numbers are not load-bearing.
- Confidence is informative only at the extremes, and only after a per-question fit.

## 3. `fast-jev-compaction`: teardown and verdict

**Algorithm**, read from `src/compact.ts` and `hooks/fast-jev.ts`:

1. Pair each tool call with its result. Pin the first message and the last 6 messages.
2. Build the state from the full conversation, with every tool *result* replaced by a one-line placeholder such as `ok, 4213 chars (omitted)`.
3. Fit the state into 25k tokens through staged degradation (truncate inputs, abridge text, collapse old messages). Token counts use a character heuristic, not a real tokenizer.
4. For each unpinned call, ask two **Noul** questions: should the call stay, and should the result stay verbatim.
5. Apply the rule at the 0.5 threshold: keep both, keep the call with its result truncated to 300 chars, or drop both.
6. Rebuild the conversation. Kept content is never rewritten, and the hook falls back to native compaction on any failure or when the reduction is under 25%.

The approach is good: **verbatim pruning keeps kept content at full fidelity instead of summarising it**.

**Why not to adopt it:**

| Problem | Evidence |
|---|---|
| The integration surface is not a supported one | It uses "function hooks" (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`, early-access, gated, "may change without notice", pinned to v2.1.274). The official hooks reference lists five types (`command`, `http`, `mcp_tool`, `prompt`, `agent`) and documents no output that lets `PreCompact`/`PostCompact` supply a summary. Issue #88 ("hooks cannot actually replace compaction") has no answer. VERIFIED |
| The benefit disappears on resume | #89: 166–168k tokens reloaded vs 28k for native compaction (n=12 vs n=10), because a transcript anchor is missing. Linked upstream as claude-code#95328 |
| Fails on code-shaped content | #97: Cloudflare's WAF returns a 403 HTML page for state containing shell, SQL or paths, which is most of a coding transcript. Reproduced with a minimal script |
| Earlier content never gets reconsidered | #70: across rounds, retained size grows monotonically (36K → 87K). The task-goal heuristic picks up `<system-reminder>`/`/compact` noise |
| The core idea is not shown to beat a trivial baseline | #99: on 23 real transcripts, no selector (typed-decision models, or even an oracle given the agent's next message) beat head+tail truncation by >3 points |
| Provenance | 22 commits over ~1 day on `devin/*` branches, dormant since. 6.6k stars. Tests use a fake Jev, so the code has never been measured for accuracy |
| Privacy | Whole transcripts, including code and file contents, go to a third party whose default-tier retention is undisclosed |

**Build our own instead?** Not as a compaction replacement. Praxion's documented position (`docs/context-economy.md`) is that forcing compaction at a threshold doesn't preserve the orchestrator's judgement state, and that the phase-boundary **`/handoff`** does. The Praxion-shaped version of this idea is **ranking what to carry forward into a handoff**, and even that should first pass an offline replay against the head+tail baseline (§6 J10).

## 4. Where Praxion makes small typed decisions (internal inventory)

The decision-site lens searched hooks, scripts, rules, agents, workflows and eval code. The candidates:

| Site | Today's mechanism | Shape | Labels already on disk? | Jev fit | If wrong |
|---|---|---|---|---|---|
| ADR `category` (the "architectural" falsifier test) | Author LLM, unaudited | Choice ×4 over the ADR's own text | **Yes: ~390 finalised ADRs** | Medium–strong. The text contains the answer; no lookup needed | Advisory; ledger quality |
| Tier selection (Direct → Full, Spike) | Orchestrator applies a 6-signal rubric by hand | Choice ×5, plus Score for the two soft signals | **Yes: calibration-log rows** with retrospectives (weak labels, see §5) | Strong for "is this architectural?" and "complexity". The countable signals stay mechanical | Advisory; the user always confirms |
| Skill/agent shortlist | Native listing only | Choice among ≤255 ids | Not yet. The M1 golden eval in the companion report creates them | Medium; a candidate ranker arm | Advisory hint |
| Eval tool-selection judge (`eval/trajectory_eval.py`) | GPT-4o judge per span | Choice (correct/incorrect) | Judge outputs can serve as silver labels | Strong shape match | A metric, not a gate |
| CI-autofix flake vs real defect (`reusable-ci-autofix.yml`) | A full agent run with a 60-turn budget; ~70% of attempts end without a fix | Choice/Score over the failure log | **Yes: `self_healing_metrics.py` outcomes** | Medium, as a *pre-filter* that skips obvious flakes. WAF risk on log content | Asymmetric: skipping a real fix costs more than an extra run |
| Sentinel Pass-2 semantic checks (GL01/GL03/DH03/AC*) | Batched LLM | Noul per artifact ("hollow container?") | Past sentinel reports | Medium: semantic but shallow, the niche Jev targets | A report finding |
| Discipline-consultant trigger predicates; RISKY-step review trigger; researcher mode | Orchestrator reading its own prompt | Noul / Choice ×3 | Consult ledger (dispositions) | Medium | Cost vs quality, reversible |
| `detect_duplication.py` semantic confirmation | AST/text heuristic | Noul on a candidate pair | No | Medium, but a synchronous hook on code content (timeout, WAF, privacy) | WARN only |
| Verifier PASS/FAIL/WARN sub-checks | Opus agent | Choice, many per run | Past verification reports | Weak overall. A few sub-checks become mechanical once the evidence is assembled | **Pre-merge gate. Second opinion only** |
| `capture_observations.py` event labels | Regex, <1 ms, async | Choice ×~11 | — | Excellent shape, but an API call per tool event loses to free regex. Only a **local** backend changes that | A cosmetic label |

**Excluded on purpose:**
- **CODE-kind gates** (id-citation, token ratchet, shipped-artifact isolation) must stay deterministic and canary-provable under `gate-liveness.md`. A probabilistic call would be a regression.
- **Ledger dedup keys** and **test-scope radius** are deterministic by design.

## 5. Reconciliation: what the two lenses imply together

1. **Labels are Praxion's scarce asset, and it already has several labelled corpora.** The independent evidence says Jev is useful *only* with decomposition, labels and a per-question fit. That turns Praxion's `.ai-state/` corpora into evaluation sets. **Caveat:** the process-economy roadmap found that 0 of 85 calibration rows ever recorded an over-heavy tier, so tier-retrospective labels have near-zero variance and are self-graded. Recent rows do show `under-calibrated`, but tier labels are *weak* and need a human-relabelled slice. ADR categories are stronger labels, because the falsifier test is written down.
2. **Confidence-gated escalation is the new capability, but not with vendor-default thresholds.** Accuracy was flat between confidence 0.50 and 0.95 and jumped only at ≥0.99. A usable pattern is therefore: *Jev decides at ≥0.99 after a per-question temperature refit; everything else escalates to the current LLM or human path*. Coverage, meaning the share of decisions Jev can take, is then what saves money, and it has to be measured per question on Praxion's data.
3. **Hooks constrain it.** Hooks are stdlib-only `python3` with tight timeouts and fail open. A Jev call from a hook has to use `urllib`, skip when `TYPESAFE_API_KEY` is absent (the sentinel "TT idiom" / `CHUB_TELEMETRY` precedent), and time out fast. A synchronous hook on the commit path is the wrong first place.
4. **The native competitors are strong and add no vendor.** Claude Code's **`prompt` hook type** sends a single-turn evaluation to a fast Claude model and gets a JSON decision back, inside the harness, with no new trust boundary. **Haiku 4.5 with structured outputs** beat Jev on single-question accuracy. Adopting Jev needs a measured win on *Praxion's* decisions: cost at equal accuracy, or coverage at equal error.
5. **Privacy decides where Jev can go.** State leaves the machine, default-tier retention is undisclosed, zero retention is enterprise-only, and the WAF rejects code. Jev fits best on **prose-shaped state** (ADR text, request text, plan prose, artifact descriptions), not diffs, logs or transcripts. For managed projects it must be **opt-in only**, and never on by default in a shipped hook.
6. **Typed decisions are good data design whatever backend answers them.** Writing Praxion's small decisions as *versioned typed questions*, with explicit options, criteria and "none/other", is *Data Structures First* applied to routing. It makes the tier rubric, discipline predicates and ADR falsifier inspectable, testable and swappable. Heuristics, Haiku, prompt hooks, Jev or a local model can then answer the same question under one schema, and every answer logs into one decision log for calibration. **This part is worth building even if Jev never ships in Praxion.**

## 6. Ranked integrations (easy proofs → elaborate)

### Tier 0: foundations (Lightweight; prerequisites for everything below)

| # | Item | Deliverable | Why first |
|---|---|---|---|
| **J0.1** | **Typed-decision schema and seam** | A small data format for questions (`id`, `type`, `instructions`, `criteria`, `version`) and a stdlib `decide(state, questions, backend)` with backends `heuristic`, `claude` (Haiku structured output) and `jev` (urllib). Every answer logs to a local JSONL decision log | Swapping backends, shadow runs and calibration all rest on this. No vendor lock-in |
| **J0.2** | **Offline replay harness** | Replays a labelled corpus through each backend and reports accuracy, ECE (before and after a per-question temperature refit), coverage at confidence τ, cost and latency. Built on `eval/` conventions | Turns "is Jev good for us?" into a number, with zero runtime risk |
| **J0.3** | **Third-party inference policy** (ADR) | Opt-in env var, skip-with-INFO when absent, prose-only state, never sole gate decider, never default-on in shipped hooks, per-backend data-handling note | No prior ADR governs this. dec-225's clean-seam stance is the nearest precedent |

### Tier 1: easy proofs of integration (offline, advisory, days)

| # | Item | State that leaves the machine | Useful output even if Jev loses |
|---|---|---|---|
| **J1** | **ADR category replay.** Choice over {architectural, behavioral, implementation, configuration} on each ADR's Context and Decision text, for ~390 ADRs, compared against the recorded category | ADR prose (already public in the repo) | **A list of probably miscategorised ADRs** for the ledger, plus a candidate advisory self-check for ADR authors |
| **J2** | **Tier-selection replay.** Score "does this request describe an architectural decision?" and "request complexity", then Choice over tiers, on calibration-log task text, compared against the recorded tier and retrospective | Short task summaries | A second, independent reading of the calibration log's under- and over-calibration pattern. **Relabel a slice by hand first**, because the labels are weak |
| **J3** | **Skill-selection arm** in the companion report's M1 golden eval: Choice over ≤255 skill ids given the task text, against BM25, Haiku and the native listing | Task text | Tells the S4 shortlist hook which ranker to use |
| **J4** | **Eval-judge arm.** A Jev Choice judge beside the existing GPT-4o tool-selection judge in `eval/trajectory_eval.py`; measure agreement | Tool-call spans (may contain code, so check WAF behaviour) | A cheaper high-volume judge for eval runs, if agreement is high |

### Tier 2: live, shadow-first, confidence-gated (Lightweight → Standard)

| # | Item | Pattern | Guard |
|---|---|---|---|
| **J5** | **Shortlist-hint ranker** for the companion report's S4 `UserPromptSubmit` hook | Jev or Haiku ranks the top-k skills from prompt text; only the hint is injected | Shadow first. Promote only on a win on M1 |
| **J6** | **CI-autofix flake pre-filter.** A Score over known-flake signatures (timeout, network, runner OOM) vs assertion/stack shape, run *before* the 60-turn agent | Skip the agent only at calibrated ≥0.99 "flake"; otherwise the flow is unchanged | Shadow against `self_healing_metrics` outcomes first. The error costs are asymmetric. Test WAF behaviour on real logs, and fall back to Haiku if blocked |
| **J7** | **Sentinel Pass-2 per-artifact Noul** ("does this section substantively cover its claimed scope?") with LLM escalation below τ | Cheap wide first pass; the LLM spends its budget on ambiguous cases | Sentinel findings are advisory. Track any drift in the findings rate |
| **J8** | **Orchestrator decision assists:** discipline-consultant trigger predicates, RISKY-step flags, researcher-mode routing, model-tier suggestion | One schema, answers surfaced to the orchestrator with probabilities | Advisory. The consult ledger supplies labels over time |

### Tier 3: elaborate (Standard/Full; only after Tier 1 and 2 evidence)

| # | Item | Why it's elaborate |
|---|---|---|
| **J9** | **Verifier second opinion** on the sub-checks that become mechanical once evidence is assembled (for example, "deployment files changed but deployment doc untouched → WARN") | Needs the verifier's ~20 classifications split into *evidence-gathered-then-bounded* and *needs reasoning*. Pre-merge gate: second opinion only, never an override |
| **J10** | **Handoff carry-forward ranking.** At a `/handoff` or `PreCompact` boundary, score WAL items and tool results for "needed in the next phase?" and carry the kept items *verbatim* into the handoff document | Must first pass an offline replay on Praxion's own transcripts against **head+tail truncation** and a Haiku selector, using #99's "used later" metric with its paraphrase caveat. Transcripts are code-heavy (WAF, privacy). Justified only by a clear margin |
| **J11** | **Local typed-decision backend** (open clones or a small fine-tuned classifier) behind the J0.1 seam | Removes the privacy, WAF and latency objections, and would make per-tool-call uses (`capture_observations`, duplicate confirmation) viable. Needs its own serving story. Watch the clones mature |

### Not recommended

- **Adopting `fast-jev-compaction`** (§3).
- **Replacing any CODE-kind deterministic gate** with a probabilistic call.
- **Any gate where Jev is the sole decider**, or any **default-on** Jev call in hooks shipped to managed projects.
- **Using TypeSafe's vendor confidence bands** (0.6 / 0.85 / 0.9) instead of per-question fitted thresholds.

## 7. Risk register

| Risk | Evidence | Severity | Mitigation built into the ranking |
|---|---|---|---|
| Vendor immaturity | 8 days old; `529 overloaded` and WAF 403s in launch week; limits adjust dynamically; no SLA | High | Seam plus fallback. Offline first |
| Poor OOD calibration | ECE 0.107; 44.7% right at 0.74 stated probability | High | Per-question refit. τ ≥ 0.99. Escalate everything else |
| Code content blocked | fast-jev-compaction #97 | High for code state | Prose-only state policy (J0.3) |
| Privacy / retention | ZDR enterprise-only; default retention undisclosed | Medium–High | Opt-in; never default in managed projects |
| No cross-question consistency; no "unknown" | Vendor jaggedness page; beri.net found 0 out-of-scope inputs flagged | Medium | Always include a "none/other" option. Combine answers in code, never trust them jointly |
| Lock-in | New key, billing and terms | Medium | Backend-neutral seam; local backend (J11) |
| Weak Praxion labels | 0 of 85 calibration rows ever recorded over-heavy (process-economy §4) | Medium | Relabel by hand before J2; prefer ADR labels (J1) |

## 8. Open questions

1. Has fast-jev-compaction #88 been answered, and will "function hooks" reach GA with a compaction-replacement contract?
2. What is TypeSafe's default-tier retention window? The DPA was indexed but not read in full.
3. How does Jev compare with **OpenAI logprobs classification** and with Claude Code's native **`prompt` hooks** on the same questions? Neither was covered by any source; J0.2 can measure the prompt-hook arm directly.
4. Is a **coverage** (share of decisions at τ ≥ 0.99) high enough on Praxion's decisions to save meaningful spend at the J6/J7 sites?
5. Do the open-source typed-decision models reach Haiku-level accuracy on *decomposed* Praxion questions? That decides whether J11 is viable.

## 9. Sources

Primary (vendor): [docs.typesafe.ai introduction](https://docs.typesafe.ai/introduction) · [models (pricing, limits)](https://docs.typesafe.ai/models.md) · [API](https://docs.typesafe.ai/api.md) · [primitives](https://docs.typesafe.ai/primitives.md) · [confidence](https://docs.typesafe.ai/confidence.md) · [patterns](https://docs.typesafe.ai/patterns.md) · [jaggedness jev-1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md) · [coding agents](https://docs.typesafe.ai/introduction/coding-agents.md) · [legal](https://docs.typesafe.ai/legal.md) · [launch blog](https://typesafe.ai/blog/introducing-system-one-models-and-jev) · [llms-full.txt](https://docs.typesafe.ai/llms-full.txt)

Independent: [beri.net calibration and decomposition study (2026-09-20)](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval) · [jock.pl benchmark](https://thoughts.jock.pl/p/jev-typesafe-system-one-model-benchmark-2026) · [KDnuggets analysis](https://www.kdnuggets.com/what-everyone-is-getting-wrong-about-typesafe-ais-jev) · HN launch thread (secondary aggregation only)

Repository: [tamaratran/fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction) and issues [#70](https://github.com/tamaratran/fast-jev-compaction/issues/70), [#81](https://github.com/tamaratran/fast-jev-compaction/issues/81), [#88](https://github.com/tamaratran/fast-jev-compaction/issues/88), [#89](https://github.com/tamaratran/fast-jev-compaction/issues/89), [#97](https://github.com/tamaratran/fast-jev-compaction/issues/97), [#99](https://github.com/tamaratran/fast-jev-compaction/issues/99), [#100](https://github.com/tamaratran/fast-jev-compaction/issues/100)

Claude Code: [hooks reference](https://code.claude.com/docs/en/hooks) (five hook types; Pre/PostCompact semantics) · anthropics/claude-code#91870 (function hooks proposal) · #95328 (resume anchor)

Comparators: RouteLLM (LMSYS) · [RouterArena (arXiv:2510.00202)](https://arxiv.org/abs/2510.00202) · Claude Haiku 4.5 pricing ($1/$5 per million tokens)

Internal: `hooks/hooks.json` · `hooks/capture_observations.py` · `hooks/detect_duplication.py` · `eval/trajectory_eval.py` · `.github/workflows/reusable-ci-autofix.yml` · `scripts/self_healing_metrics.py` · `agents/verifier.md` · `agents/sentinel.md` · `rules/swe/gate-liveness.md` · `rules/swe/adr-conventions.md` · `skills/spec-driven-development/references/calibration-procedure.md` · `docs/context-economy.md` · `.ai-state/decisions/225-remove-in-house-memory-subsystem.md`

## 10. Addendum, 2026-11-01: Haiku 5.5 changes the incumbent

This report compared Jev against Claude Haiku 4.5. Since then, Haiku 5.5 has become what the `haiku` alias resolves to on the Anthropic API, and its price changes the arithmetic in §0 and §6.

- **Price.** Haiku 5.5 lists at **$0.10 per million input tokens and $0.50 per million output** for prompts up to 100,000 tokens. That is a tenth of Haiku 4.5's $1 and $5, the prices behind the 12–27× ratio quoted above. Jev's list price is unchanged: $0.042 per million input tokens, with free output. VERIFIED ([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), fetched 2026-11-01).
- **One independent re-run.** AY Automate re-ran its 791-decision benchmark on 24 October 2026: 8-way and 77-way Banking77 routing, and prompt-injection detection. Accuracy for Jev vs Haiku 5.5:
  - 8-way: 84.4% vs 83.8% (exact McNemar p = 1.0);
  - 77-way: 80.5% vs 75.3% (p = 0.036);
  - injection: 87.0% vs 84.8% (p = 0.175).

  Cost per 1,000 decisions on the 8-way task, at list prices with no caching: Jev $0.015, Haiku 5.5 $0.050, Haiku 4.5 $0.360. Median latency: 0.36 s vs 1.36 s. SINGLE-SOURCE ([AY Automate, 2026-10-24](https://www.ayautomate.com/blog/jev-vs-claude-haiku-5-5-benchmark)). Weigh it accordingly:
  - each system ran once, through OpenRouter;
  - Haiku 5.5 ran at default sampling, because the route accepts no temperature;
  - the article does not say whether Jev's questions were decomposed;
  - the author's firm sells agent-development services, and it discloses no tie to TypeSafe.
- **What it changes for Praxion.** The recommendation stands, and the bar for adding Jev rises:
  - On this evidence the cost gap narrows from an order of magnitude to about 3× at list price. Accuracy ties on two of the three tasks, with Jev ahead only on the 77-way routing.
  - The no-new-vendor backend in Tier 1 and Tier 2, Haiku through the `haiku` alias (Haiku 5.5 on the API), now costs roughly a tenth of what §6 assumed. That makes it the baseline arm of the offline replay.
  - Jev now has to beat that arm on Praxion's own labels by enough to justify a second vendor, another credential and an alpha endpoint.
  - The backend-neutral seam, the replay harness over Praxion's labelled records, and the verdict on `fast-jev-compaction` are unchanged.
