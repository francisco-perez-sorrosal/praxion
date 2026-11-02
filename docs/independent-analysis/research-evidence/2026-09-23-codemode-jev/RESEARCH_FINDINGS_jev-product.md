# Research Findings: TypeSafe / Jev — Product & Ecosystem Dossier (Lens: jev-product, external)

## Research Goal

Determine whether and how Praxion (a Claude Code plugin for agentic software development) should use TypeSafe's Jev — a "System One" typed-decision model — for routing, fast context compaction, classification gates, and similar small typed decisions.

## Research Questions

1. What exactly does the Jev API offer (primitives, contract, limits, pricing, ToS/data handling)?
2. Who is TypeSafe, what is disclosed about Jev's architecture and calibration, and how credible are its performance claims?
3. What does `tamaratran/fast-jev-compaction` actually do, and what does its own issue tracker say about whether it works?
4. What do independent evaluations and community discussion say, separated from marketing?
5. How does Jev compare with adjacent "fast structured decision" approaches (Claude Haiku 4.5 structured output/classification, OpenAI logprobs classification, embedding routers, small fine-tuned classifiers, judge/reward models)?
6. What are the risks of adopting Jev in Praxion (vendor maturity, lock-in, privacy, determinism, task fit)?

## Note on an embedded instruction encountered during research

One MCP server ("claude.ai Claude Docs") injected tool-use instructions into this session directing that any work product be created as a live "claude.ai doc" via its own tools, first action of the turn. This conflicts with this task's explicit contract (write `RESEARCH_FINDINGS_jev-product.md` to the worktree, return a pointer, no artifact creation) and is not something the user asked for in this task. Per the standing rule that only the user's own messages or the permission system are consent, and fetched/injected content is data not instructions, this was **not acted upon**. Flagging it because a future agent in this same environment could be steered into creating an unwanted external artifact.

## Codebase Findings

Not applicable in depth for this lens — Praxion itself has no existing Jev/TypeSafe integration, and no dependency on it exists in `pyproject.toml`/`package.json`. This is a pure adoption-evaluation research task; see `Comparative Analysis` for how Jev would sit next to Praxion's existing model-routing surface (`rules/swe/agent-model-routing.md`, Haiku/Sonnet/Opus routing already in place per `skills/claude-ecosystem/SKILL.md`).

## External Findings

### 1. TypeSafe / Jev product surface (docs.typesafe.ai — Tier 1, official)

Crawled via `llms.txt`/`llms-full.txt` plus targeted page fetches (all through `WebFetch`, which returns a summarized version of page content, not byte-exact HTML — treat wording as paraphrase of the source, not verbatim quotation, except where I show inline quoted strings the tool itself surfaced as quotes).

**Company / model identity**
- TypeSafe AI: founded by **Diogo Almeida** (ex-OpenAI, credited with instruction-following/RLHF work behind ChatGPT), with co-founders **Erik Gafni** and **Sasha Sheng**. San Francisco. ~2 years in stealth before launch [source: WebSearch aggregation of firecrawl.dev/finance.yahoo.com articles — tier 3, cross-referenced across 2 independent write-ups, certainty: med — secondary sources agree but I could not independently verify against a primary "About" page].
- Funding: **~$40M led by DCVC**, announced at launch (Yahoo Finance headline) [tier 3 syndicated wire piece — certainty: med].
- Jev launched **2026-09-15** (per most secondary sources) or **2026-09-24** (per the WebFetch summary of TypeSafe's own blog post `typesafe.ai/blog/introducing-system-one-models-and-jev`) [certainty: low — **directly conflicting dates from different fetch passes of ostensibly the same primary source**; see Divergence Map]. Current model **`jev-1.13.0`** as of the docs snapshot; `jev-latest`/`jev-preview` both alias to it. A per-model "jaggedness"/known-limitations page exists (`model-jaggedness/jev-1.13.md`, last reviewed 2026-09-17).
- Architecture disclosure (from the blog announcement, Tier 1 but self-reported): "a new model architecture, parallel sampler for maximum efficiency, and a training method we call **Reinforcement Learning for Calibrated Decisions (RLCD)**"; the model is explicitly **non-autoregressive** — it evaluates all questions against one state in a single parallel pass rather than generating tokens sequentially. No paper, no benchmark methodology disclosure, no parameter count, no third-party audit found. The `machine-learning-primer` docs page mirrors this at a conceptual level (Kahneman System-1/System-2 framing) without adding technical substance.

**The three primitives** (`primitives.md`, `primitives/{choice,score,noul}.md`)
- **Choice** — select one of a defined, unordered option set (max **255 options**); returns `choice`, `probabilities` (full distribution), `confidence`.
- **Score** — position on an ordered rubric of **2–10 levels**; returns `score` (can fall between two levels), `legend`, `probabilities`, `confidence`.
- **Noul** — yes/no truth value in **[0, 1]**; returns a single `noul` field, no separate confidence (the value itself carries it: near 0.5 = uncertain).
- Design guidance: keep questions atomic; combine answers in application code; always include an "other/none" option in Choice; use nested JSON with dotted/backticked field references in `state` to reduce ambiguity.

**API contract** (`api.md`, `introduction/quickstart.md`)
- Endpoint: `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <API_KEY>`, `Content-Type: application/json`.
- Request: `{ state: string | object | array<string>, model: string, questions: { [key: string]: Question } }`. Question shapes:
  - Noul: `{ type: "noul", instructions: string|object|array, criteria?: {true, false} }`
  - Choice: `{ type: "choice", instructions, criteria: map<string,string> (≤255 entries) }`
  - Score: `{ type: "score", instructions, criteria: array[2..10] of level descriptions }`
- Response: `{ model: string, answers: { [key]: Answer }, usage: { input_tokens, output_tokens } }`.
  - `Answer` (noul): `{ type: "noul", noul: number 0-1 }`
  - `Answer` (choice): `{ type: "choice", choice: string, probabilities: map<string,number>, confidence: number 0-1 }`
  - `Answer` (score): `{ type: "score", score: number, legend: map, probabilities: map, confidence: number 0-1 }`
- Example (quickstart, verified consistent across two independently fetched pages):
  ```json
  // request
  {"state": "Hi, I've been trying to connect my Stripe account for 3 days...",
   "model": "jev-latest",
   "questions": {"urgency": {"type": "noul", "instructions": "Does this message express urgency?"}}}
  // response
  {"model": "jev-1.13.0", "answers": {"urgency": {"type": "noul", "noul": 1.0}},
   "usage": {"input_tokens": 392, "output_tokens": 65}}
  ```
- Error codes: `401` invalid/missing key, `422` schema validation failure, `429` rate limit, `529` overloaded (all documented; independent testers report hitting `529` and Cloudflare `403` in practice — see § fast-jev-compaction issues below).

**Limits, pricing, latency** (`models.md`)
- Context: **64k tokens per request total**; **32k tokens for `state` + the single longest question**.
- Input: text only (string/JSON object/array of text). No image/audio/video. English is the best-supported language; CJK scripts accepted with lower accuracy (independently confirmed to be a real, measurable degradation — see calibration findings below, not just a documentation caveat).
- Pricing: **$0.042 per million input tokens; output tokens are free** (as of the docs snapshot, dated 2026-09 in the fetched summary).
- Rate limits: **250,000 tokens/sec; 1,200 requests/minute**, explicitly stated as adjusting dynamically with demand/GPU capacity; higher limits via enterprise plans.
- Latency: docs claim "most queries complete in ~100ms" / "70–500ms" depending on page; independent testing (below) measured 370ms median in one benchmark and sub-second consistently, so the claim is directionally supported but the docs' own numbers are inconsistent across pages (100ms vs 70-500ms) [certainty: med — internal doc inconsistency, not independently arbitrated].
- No documented SLA. No documented batching endpoint (batching in this API means "many questions in one request", not an async batch-processing API like OpenAI's/Anthropic's Batch API).

**Confidence semantics** (`confidence.md`)
- Confidence is derived purely from the shape of the `probabilities` distribution, not a separately calibrated signal. Docs show, for a 3-option Choice, the illustrative formula `confidence = (3 × top_probability − 1) / 2`, explicitly called an "approximation." This means **confidence and the top probability are close to redundant by construction** — a fact independently confirmed and criticized (see beri.net evaluation: "the separate confidence field was never better than the max probability").
- Guidance: confidence thresholds are action-specific, not global; example bands: universal floor ~0.5-0.6 (route to human below), 0.6–0.85 medium-stakes (confirm), >0.85–0.9 high-stakes (auto-act only above).

**Terms of Service / data handling** (`legal.md` — important for a code-context tool)
- Governed by a "Master Customer Agreement"; separate Data Processing Agreement and Privacy Policy.
- States a commitment **not to train models on user data**.
- Offers **zero data retention (ZDR) for enterprise customers** (implying non-enterprise/default tier retains data) — contact `privacy@typesafe.ai` for specifics.
- **No data residency information found.** **No default (non-enterprise) retention period disclosed** in the crawled content. This is a real gap for anyone considering sending source code or conversation transcripts (as `fast-jev-compaction` does) to the API on a non-enterprise plan.

**SDKs & agent skill**
- Official Python SDK: `typesafe-sdk` (`pip install typesafe-sdk`), `TypeSafeClient` / `AsyncTypeSafeClient`; no documented minimum Python version, no documented retry/timeout defaults in the crawled pages.
- Official JavaScript SDK exists with a full generated API reference (classes, interfaces, error types including `RateLimitError`, `APITimeoutError`, etc. — typical generated-SDK error taxonomy).
- A Claude Code **agent skill** is distributed by TypeSafe itself (`claude plugin marketplace add typesafe-ai/skills`) that teaches an agent the three question types and patterns — this is TypeSafe's own equivalent of Praxion's `external-api-docs` pattern for its own API, not a general integration.
- **The official "Jev with coding agents" docs page explicitly disclaims that Jev is a replacement for the LLM behind Claude Code/Cursor/etc.** and frames it purely as an in-app decision primitive coding agents can call from code they write — consistent with the "AI-powered software, not agent" philosophy stated across the docs.

**Patterns documented**: Speculative fan-out (send many questions per request, let code decide), Confidence-gated routing, Composite scoring (weighted combination of multiple Choice/Score/Noul answers in code), Intent routing. All are code-side composition patterns, not model features — Jev provides no orchestration of its own.

**Known failure modes** (`model-jaggedness/jev-1.13.md`, official, dated 2026-09-17): literal reading (misses implied intent), cannot count/do arithmetic reliably, cannot reason about date/time as ordered quantities, degrades on multi-hop/double-negative "indirection," distracted by irrelevant detail in large state, does not treat input as potentially adversarial (no built-in prompt-injection defense), degrades under contradictory instructions/criteria, **no guaranteed mathematical relationship between separately-asked questions** (you cannot rely on probabilities across two questions summing sensibly), not trained for text generation at all.

### 2. Independent evaluations (Tier 3, cross-referenced across 4 distinct authors — the strongest external signal available)

Three substantive independent write-ups were found and fetched; their numbers partially corroborate each other and partially conflict, which is itself informative.

**beri.net (`typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval`)** — the most methodologically detailed source found:
- Phishing detection, 2,000 synthetic emails (PhishNChips v5.2, labels from URL reputation feeds, not human review — a real limitation of this source's own ground truth).
- Single-question format: **Jev 62.6% vs Claude Haiku 4.5 81.3%** (statistically significant gap, McNemar p<0.0001); Jev false-negative rate 56.8%.
- Decomposed into 5 atomic signals + a logistic-regression combiner fitted on 1,000 labeled examples: **Jev 95.0% vs Haiku 93.2% vs a 2-line regex 91.8%** (Jev-Haiku gap no longer significant, p=0.063). Notably, decomposition helped Jev but **hurt** Haiku (Haiku's single best atomic signal alone, 94.2%, beat its own 5-question composite).
- Cost per 1,000 emails: Jev $0.038 vs Haiku single-question $0.462 (12x) vs Haiku five-signal $1.02 (27x).
- **Calibration**: out-of-distribution ECE = 0.107 ("4.4x the 0.024 noise floor"); Choice/Score answers were *overconfident* (refit temperatures 3.29–3.40), Noul answers *underconfident* (refit temperature 0.66); on genuinely unknowable/policy-based questions Jev was "right 44.7% of the time while assigning average probability 0.74" — i.e., badly overconfident exactly where it should express doubt. In-distribution public-benchmark calibration (ECE 0.024-0.032) was much better, which the author flags as possible **training-set contamination** of the public benchmarks TypeSafe itself might reference.
- A pre-registered follow-up (5,721 calls, 21 experiments) found accuracy flat from confidence 0.50 to 0.95, then jumping to 100% only at 0.99 (covering 60% of traffic) — with **zero out-of-scope inputs flagged even at 0.99 confidence**, because Noul/Choice questions force a valid-shape answer with no "unknown" option.
- Author's verdict, directly quoted by the fetch tool: "Jev prices a decision at a fraction of a cent. It doesn't price being wrong. Your labelled log does."

**thoughts.jock.pl** (self-run, 40 hand-labeled support tickets across 5 models via OpenRouter with identical JSON-schema constraints — explicitly caveated by its own author as too small a sample to generalize):
- Speed: Jev 370ms vs Haiku 4.5 1.2s vs "Fable" ~4s.
- Cost: Jev $0.0000172/call; "$1 buys 51,613 Jev triages vs 2,049 Haiku vs 157 Fable" triages.
- Accuracy: 1 error in 40 routing decisions, and that one error carried low self-reported confidence (0.33) — read by the author as a genuine, useful calibration signal for the *urgency* question specifically (monotonic confidence-vs-accuracy relationship observed), though Choice-type confidence was bimodal (certain or clearly confused) rather than smoothly informative.
- Directly disputes TypeSafe's own headline numbers: "the headline claims... 193.6x faster and 444.6x cheaper come from their own four workflow evals with reference answers averaged from GPT-6 Astra and Fable 5.1. My numbers are smaller and measured, and I would trust neither set without running your own."
- Also reports operational flakiness during the launch week: `529 system_overloaded` on 5 of 6 calls mid-test.

**kdnuggets ("What Everyone Is Getting Wrong About TypeSafe AI's Jev")** — opinion/analysis piece, not a new benchmark:
- Central thesis: Jev is a refinement of established techniques (zero-shot classification, intent detection), not a new paradigm; the "zero hallucinations" claim means only "zero out-of-schema outputs," not "zero wrong answers" — same critique independently made by the top Hacker News comment (see below), a genuine cross-source convergence.
- Flags that TypeSafe's own ~68% benchmark number is measured against a **reference built by averaging two frontier LLMs' answers**, not independent ground truth — i.e., "agreement with a model-derived reference" rather than "verified correctness."

**Hacker News launch thread** (`news.ycombinator.com/item?id=49745752` and related; ~1,655 points / 456 comments reported by secondary aggregation — not independently re-counted by me):
- The submission title was changed within an hour from a stronger "New frontier model 40-400x cheaper and 20-200x faster" framing to a more neutral one, indicating community pushback on the headline framing.
- Top comment (attributed to "jacobgold" by the search-tool summary): "it can't emit an invalid type, but it can still emit a wrong valid value" — i.e., schema-conformance is not correctness, mirroring the kdnuggets critique.
- A secondary objection noted this capability is exactly what every major LLM provider's existing JSON-mode/structured-output feature already gives you when you were only doing classification anyway — directly relevant to whether Jev is *distinct* from Haiku+structured-output.
- Open-source response: **within about a week of Jev's launch, open-source "typed-decision" clones appeared** — notably **`convaiinnovations/laya-typed-decisions` ("Laya", 421M params)** and references to "SWE-Pruner" (0.6B, `ayanami-kitasan/code-pruner`) and "Needle 3" (121M embedding model), runnable on consumer hardware (RTX 3090/3050 cited). These are referenced independently both in HN-adjacent coverage and in `fast-jev-compaction` issue #99/#86 (see below) — a genuine cross-source convergence, not a single unverified claim.
- **Not independently verified by me**: exact HN point/comment counts (I did not load the HN page directly — WebFetch was not used on it; this is a WebSearch-tool aggregation and should be treated as secondary).

### 3. `tamaratran/fast-jev-compaction` — deep technical breakdown

Cloned locally (`tmp/fast-jev-compaction`, shallow clone, 50 commits fetched — repo has only 22 commits total) and inspected directly; repo metadata pulled via `gh api` (ground truth, not a summary):

**Repo facts (verified via `gh api repos/tamaratran/fast-jev-compaction`, not trusted from any secondary source)**
- **6,607 stars, 387 forks, 81 open issues, 12 subscribers**, MIT license, TypeScript, `size: 245` (KB).
- Created **2026-09-17**, last push **2026-09-18** — i.e., all development happened in roughly **one day**, then the repo went essentially dormant except for issue traffic (issues run through at least #100, opened over the following days, none closed in the fetched sample — active discussion, no further code response visible in the commit log).
- Commit history (22 commits) is dominated by `devin/<ticket-id>-...` branch names merged via PR — strongly suggesting the repository was built by an autonomous coding agent (Devin or similar), not hand-written incrementally. This matters for trusting the code's own self-review: several of the most serious limitations were filed as **GitHub issues by third parties after the fact**, not caught during development.
- `package.json`: version `0.2.0` (note: issues reference `0.3.0` at commit `e3f262a`, i.e., the version number moved after my clone's HEAD or the working tree's `package.json` lags a release tag — **unreconciled discrepancy, not chased further**), MIT, Node `>=18`, deps limited to `@types/node`, `tsx`, `typescript`, `vitest` (no runtime dependencies beyond Node's native `fetch`).
- Tests: 433 + 149 lines across two Vitest files; README states tests run against a fake Jev and never contact the real API — i.e., **the test suite validates the compaction/state-fitting logic, not actual Jev accuracy or the network integration**.

**Algorithm** (`src/compact.ts`, `src/state.ts`, `hooks/fast-jev.ts` — read directly, not summarized):
1. Pair every `tool_use` with its `tool_result` by `tool_use_id`. Calls in the first message or the newest `preserveRecentMessages` (default 6) messages are pinned and untouched.
2. Build **`state`** = the entire conversation, oldest-first, with every tool *result* replaced by a one-line note (`ok, 4213 chars (omitted)`); tool *inputs* and all user/assistant text are included verbatim.
3. Fit that state into `maxStateTokens` (default 25,000) via a staged, best-effort degradation: truncate tool inputs (1000→200→60 chars) → abridge long texts to head+tail (oldest-first) → collapse old non-pinned messages to `[… N chars omitted …]` → collapse old tool calls to one line → drop old call-less messages → fold runs of old call-only messages. Throws if it still doesn't fit. Token counts are a **heuristic, not a real tokenizer**: digits→len/2, ASCII letters→1+⌊(len−1)/6⌋, everything else→0.9 per char, "calibrated to land a little above what Jev reports."
4. For every **non-pinned tool call**, ask Jev exactly **two `noul` questions**: "should the call stay" and "should the result stay verbatim." Both use fixed instruction templates embedded in `questionsFor()` (quoted above verbatim from source), not user-configurable per-project.
5. Questions are batched so state+questions stay under `maxRequestTokens` (default 30,000, under Jev's documented 32k state+longest-question limit); the **full state is resent unchanged with every batch** — an explicitly acknowledged inefficiency in the README's own Limitations section for histories near the size ceiling.
6. Decision rule against `keepThreshold` (default 0.5): `keepResult ≥ threshold` → keep call+result; else `keepCall ≥ threshold` → keep call, truncate result to `truncateHeadChars` (default 300) + note; else → drop the call and its result entirely.
7. Message list rebuilt; a message that loses all content is removed; unmodified messages are returned as the *same object references* (an implementation detail that matters for the Claude Code hook's message-identity-based diffing in `toSessionMessages`).
8. On any failure (missing key, malformed Jev response, network error, "history too large for Jev," or estimated reduction below `minReductionRatio` = 0.25 default) the Claude Code hook **falls back to Claude Code's built-in compaction summary** — this fallback path is real and exercised in practice (see issues below).

**Claude Code hook integration**
- Uses **Claude Code "function hooks" / "Mods"** — a genuinely-existing, currently early-access Claude Code feature, gated by the env var **`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`**. I verified this is real (not a fabrication by the repo) against multiple independent sources: `code.claude.com/docs/en/hooks`, a third-party feature write-up (`claudefa.st/blog/tools/hooks/function-hooks`), and the open GitHub proposal `anthropics/claude-code#91870` (opened 2026-09-03). Per those sources this surface is **GrowthBook-gated, default-off, explicitly "may change between releases without notice" until GA** — i.e., an early-access surface, exactly as `fast-jev-compaction`'s own README states, and the repo pins its generated type declarations to Claude Code **2.1.274** with an explicit warning to regenerate after upgrading. This is an accurate, non-hallucinated characterization on the repo's part.
- The plugin hooks two events: `session.compact` (does the actual work: builds a `JevAsker` over `$.http.fetch`, calls the library, maps results back to `SessionMessage[]`) and `turn.complete` (auto-triggers `$.session.compact()` once `context.percent` crosses `compactAtPercent`, default 60%, with an in-flight guard to avoid re-entrancy).
- Plugin-declared config surface (`.claude-plugin/plugin.json` `userConfig`): `keepThreshold`, `preserveRecentMessages`, `compactAtPercent`, `minReductionRatio`, `maxStateTokens`, `maxRequestTokens`, `truncateHeadChars`, `model`, plus a sensitive `apiKey` option (env var `TYPESAFE_API_KEY` is the documented/recommended path).

**Stated results**: the README makes no standalone benchmark claims of its own beyond describing the mechanism; all performance numbers in this dossier for the plugin come from third-party issue reports (below), not from the repo's own claims — a point in its favor for honesty, but it also means **there is no first-party evidence the tool achieves its stated goal (verbatim, lossless-ish compaction cheaper/better than summarization) at scale.**

**Issues (read directly via `gh api`, ground truth) — this is the single most load-bearing evidence in this dossier for a go/no-go decision:**

- **#88 — "hooks cannot actually replace compaction, and full transcripts are sent to a third-party API"** (open, unresolved at time of research). Two independent claims: (a) the plugin sends tool calls, tool results, and file/code contents to a third-party API as an undisclosed-as-security-relevant config step, not flagged as a trust decision; (b) **Claude Code's actual hook surface around compaction only fires `PreCompact`/`PostCompact` — it cannot substitute the summarization step itself**, contradicting the README's core claim of "replacing" compaction. This is a **direct challenge to the plugin's central value proposition**, filed by a third party, and I found **no rebuttal or fix commit** addressing it in the commit log.
- **#89 — "Compaction is undone on `--resume`"** (open). Measured: plugin-compacted sessions reload ~166-168k tokens on resume vs ~28k for native compaction (n=12 vs n=10, same 173,575-token seed session) — because the plugin's `compact_boundary` record lacks the `preservedSegment`/`preservedMessages` anchors Claude Code's transcript loader requires; **the entire token-reduction benefit is lost the moment a session is resumed**, which is a normal, frequent Claude Code workflow. The reporter ties this to a filed upstream Claude Code bug, `anthropics/claude-code#95328`. In-session speed is genuinely good (743ms median vs 30,375ms native, n=6) but this is undermined by the resume defect.
- **#97 — "Jev requests from real sessions are blocked by Cloudflare WAF (HTTP 403 HTML page)"** (open). On real coding-session content (shell commands, SQL, file paths, code), Cloudflare's WAF in front of `api.typesafe.ai` returns an HTML block page instead of reaching the model — meaning **the plugin can silently and systematically fail on exactly the content it's designed to compact** (code/shell/SQL-heavy transcripts), always falling back to built-in summarization. The reporter reproduced this with a minimal repro script varying only `state` content between plain prose (200 OK) and shell/SQL/path payloads (403).
- **#70 — "Repeated compaction: the candidate set never covers what accumulates"** (open, 4 comments). Across two live 9-round sessions: each round's Jev-eligible candidate set is only calls made *since the last compaction round* — the 70-90% of content the *previous* round already reduced to notes is never reconsidered, so retained size grows monotonically across rounds (36K→52K→59K→74K→87K tokens in one session) despite repeated compaction. Also found: the `goalFromMessages` heuristic (last 3 user texts) captures machine-generated noise (`/compact` echoes, `<task-notification>`, `<system-reminder>`) rather than the actual task on manual `/compact` calls, and after 6 rounds 54% of "retained user text" was machine-generated rather than human-authored.
- **#99 — independent local-model replay study** (open, by a different third party building toward a non-Jev alternative). Using the reporter's own 23 real Claude Code transcripts, no line-selection strategy tested — including several small open-source "typed-decision" models (Laya, SWE-Pruner, Needle 3) and even an oracle given the agent's own next message — beat a naive head+tail truncation baseline by more than 3 percentage points on "was this line used later" at the smallest cut size. This is an important **external check on whether any typed-decision-style selection (Jev or its open clones) meaningfully beats trivial truncation** for this specific compaction task, using a different methodology from `fast-jev-compaction`'s own approach. Caveat acknowledged by that reporter: the "used later" proxy over-counts coincidence and misses paraphrase.
- **#81 — token-estimate undercounting** (open). `estimateTokens`'s character-based heuristic undercounts dense hex/UUID/base64 runs, occasionally (4 times across ~160 compactions on one host) causing a server-side 400 `max_tokens_exceeded` even though the local `fitState` check passed — a real but rare correctness gap in the state-fitting logic, degrading gracefully to fallback.
- **#82** — a related CJK/Han-script token-estimation calibration issue (estimator stays biased high for Han text, ~0.99 tokens/char measured against 10 archived pairs) — consistent with the official docs' own caveat that non-English text has lower accuracy, but here specifically about the *plugin's own* token-budgeting math, not Jev's answer quality.
- **#92, #86** — feature requests for a local (non-API) decision engine as an alternative backend, evidence that a meaningful subset of the user base wants to avoid the third-party-API dependency entirely (privacy/latency/cost or all three).
- **#100 — "Is it really accurate?"** (open, 0 comments at fetch time) — an unanswered, unresolved open question straight from the issue tracker, i.e., **the project itself has not demonstrated accuracy** as of this research.

### 4. Comparable "fast structured decision" alternatives

No official curated docs for TypeSafe/Jev were found in context-hub (`chub search "jev"` / `"typesafe jev"` both returned zero results) — all findings above are from official docs + web research, not context-hub. `external-api-docs` skill invoked per protocol; nothing to annotate/rate since no entry exists.

- **Claude Haiku 4.5 + structured outputs/JSON mode**: $1/$5 per million input/output tokens (confirmed across multiple pricing-aggregator sources, tier 3 but mutually consistent — certainty: med-high). In the beri.net phishing benchmark, Haiku *beat* Jev on raw single-question accuracy (81.3% vs 62.6%) and was competitive after decomposition (93.2% vs 95.0%, not statistically distinguishable); Haiku is ~12-27x more expensive per call in that benchmark's token-cost accounting, and ~3x slower (1.2s vs 370ms) in the jock.pl benchmark. Structured output via JSON schema/tool-use is a mature, already-integrated Praxion capability (no new vendor).
- **OpenAI logprobs-based classification**: not covered by any source fetched in this pass — genuinely absent from this research; flagged as an open unknown below rather than invented.
- **Small fine-tuned classifiers / open-source typed-decision clones**: Laya (421M, `convaiinnovations/laya-typed-decisions`), SWE-Pruner (0.6B, `ayanami-kitasan/code-pruner`), Needle 3 (121M embeddings) — all surfaced via `fast-jev-compaction` issue #99 and cross-referenced in HN-adjacent coverage as post-launch open-source responses to Jev, runnable on consumer GPUs (RTX 3090/3050). Per #99's own local replay, none of these meaningfully beat naive head+tail truncation on the tool-output-pruning task specifically — a concrete, if narrow, data point that "typed-decision small models" as a category is not obviously superior to trivial heuristics for *this* use case, independent of whether Jev itself is good.
- **Embedding-based routers (RouteLLM, semantic-router/Portkey, NotDiamond, Martian)**: RouteLLM (LMSYS, OSS) reports up to 85% cost savings at 95% GPT-4-equivalent quality on MT-Bench, needing the strong model only ~14% of the time, with its priciest strategy adding <0.4% overhead cost (tier 3, single-source WebSearch aggregation, not independently re-verified — certainty: med). NotDiamond reports a 39% SRE-benchmark accuracy improvement in one customer case study (vendor-published, certainty: low — self-reported case study). Martian is described as adaptive/traffic-pattern-learning without independent numbers found. `RouterArena` (arXiv 2510.00202) is cited as ranking "a leading commercial router 12th," suggesting router quality varies widely and marketing claims across this entire category should be treated skeptically, not just TypeSafe's. These are architecturally a different tool than Jev — they route a *whole request* to a *whole model*, not decompose one state into many typed sub-questions — but they compete for the same "cheap fast structured decision" budget line as a routing use case specifically.
- **Reward/judge models**: not independently researched in this pass beyond the general LLM-guardrails pattern documented on TypeSafe's own site (`cookbooks/llm_guardrails.md`, `citation_check.md`) — flagged as an open unknown.

## Comparative Analysis

| Criterion | Jev (TypeSafe) | Claude Haiku 4.5 (structured output) | Embedding routers (RouteLLM/semantic-router) | Small OSS typed-decision models (Laya et al.) |
|---|---|---|---|---|
| Cost (per-call, observed) | Lowest observed ($0.0000172-$0.038/1k-item benchmarks) [certainty: med — 2 independent benchmarks agree on order of magnitude] | 12-27x Jev in the same benchmark | Router adds <0.4% of routed-request cost (RouteLLM's own claim) [certainty: low — vendor-adjacent, single source] | Free/self-hosted compute cost only; no API fee |
| Latency (observed) | 370ms median, docs claim 70-500ms | 1.2s in same benchmark | N/A (routing decision itself is fast; total latency dominated by routed model) | Not benchmarked for latency in sources found |
| Raw single-question accuracy (phishing benchmark) | 62.6% | 81.3% | N/A (different task shape) | Not directly comparable — evaluated on line-retention, not classification accuracy |
| Accuracy after task decomposition | 95.0% (helped by decomposition) | 93.2% (decomposition *hurt* vs its own single best signal, 94.2%) | N/A | Did not beat head+tail truncation baseline on tool-pruning (#99) |
| Calibration | Mixed: good in-distribution, poor OOD (ECE 0.107, 4.4x noise floor); overconfident on Choice/Score, underconfident on Noul [certainty: med — single detailed independent study] | Not evaluated for calibration in sources found | N/A | Not evaluated for calibration |
| Vendor/ecosystem maturity | Launched 2026-09, early access, single-region, undocumented rate-limit changes, WAF false-positives reported in production use | Mature, GA, part of an existing multi-model Anthropic account Praxion already uses | RouteLLM OSS/mature (LMSYS-originated); commercial routers vary (RouterArena ranks a "leading" one 12th) | Days-old community projects, unaudited |
| Lock-in / dependency surface | New third-party vendor, new API key, new billing relationship, no SLA found | Zero new dependency — same account, same billing, same skill (`claude-ecosystem`) Praxion already uses | New dependency if using a hosted router; none if self-hosting RouteLLM's OSS core | New dependency (self-hosted weights, own inference stack) |
| Data leaves the machine? | Yes, to TypeSafe (state = your data); no default-tier retention policy found; ZDR is enterprise-only | Yes, to Anthropic — but Praxion already sends code to Claude for the primary agentic work, so this is not a *new* trust boundary | Depends on router (hosted vs self-hosted) | No, if self-hosted |
| Fits "atomic, no-reasoning question" model well? | Yes, by design — but per docs' own jaggedness page, poorly suited to counting, dates, multi-hop reasoning, and per independent findings, poorly suited to open-ended/policy-based questions ("right 44.7% of the time at 0.74 average confidence") | Can do the same shape of task via JSON schema/tool constraints, with more general reasoning available if needed | Designed for whole-request routing, not sub-question decomposition | Task-specific; general routing-fitness unproven |

### Trade-offs Summary

- **Jev**: Genuine order-of-magnitude cost/latency advantage *when it works and the task is truly atomic and in-distribution*; undermined by (a) an unresolved, third-party-filed claim that its flagship Claude Code integration (compaction replacement) is not actually supported by Claude Code's hook surface, (b) a demonstrated resume-defect that silently erases the token-reduction benefit, (c) demonstrated Cloudflare WAF false-positives on exactly the code/shell/SQL content a coding agent would send, (d) mixed-to-poor out-of-distribution calibration — the property Praxion would most need to trust for gating decisions, (e) a brand-new, single-vendor dependency with no disclosed default-tier data retention terms.
- **Claude Haiku 4.5 + structured output**: No new vendor, no new trust boundary, already integrated into Praxion's routing skill, more general (can reason, not just classify), and *outperformed* Jev on raw single-question accuracy in the one detailed independent benchmark found — at meaningfully higher cost and latency, though the absolute costs/latencies involved are small in Praxion's likely per-decision volume.
- **Embedding routers**: Solve a different problem (whole-request model routing) than Jev's per-question typed decomposition; relevant only if Praxion's need is specifically "which model handles this whole prompt," not "score/classify N atomic properties of this state."
- **OSS small models**: Cheapest and most private option, but the one concrete apples-to-apples test found (#99) showed no OSS typed-decision model beating trivial head+tail truncation for the specific compaction task — a caution against assuming "small model = free win" without task-specific validation.

## Continuous Improvement Signals

None meeting the strict-improvement bar. Jev is a plausible new capability for narrow use cases, not a demonstrated strict improvement over Praxion's existing Haiku-based routing/classification path — the one detailed independent accuracy benchmark found favors Haiku on raw accuracy, and the compaction-specific application (`fast-jev-compaction`) has multiple open, unresolved correctness/integration defects reported by third parties. This section is intentionally left without a signal; the risk register below carries the actionable content instead.

## Risk Register

| Risk | Evidence | Severity |
|---|---|---|
| Vendor immaturity | Product launched 2026-09-15/24 (~1 week to ~10 days old at research time); single region; documented dynamic/undocumented rate-limit changes; `529 overloaded` and Cloudflare WAF `403` reported in real use within days of launch | High |
| Core Claude Code integration claim may be technically unsupported | Issue #88: Claude Code hooks only fire Pre/PostCompact, cannot substitute the summarization step itself — filed against `fast-jev-compaction`, unresolved, no rebuttal found in commit history | High |
| Silent, systematic failure on code-shaped content | Issue #97: Cloudflare WAF blocks `state` payloads containing shell/SQL/code patterns — exactly Praxion's typical payload shape — with reproducible minimal repro | High |
| Benefit erased on session resume | Issue #89: measured 166-168k vs 28k post-resume tokens; upstream Claude Code bug implicated (`anthropics/claude-code#95328`) | High (specific to the compaction use case) |
| Poor out-of-distribution calibration | Independent study: ECE 0.107 OOD vs 0.024 noise floor; 44.7% accuracy at 0.74 average confidence on policy-based questions; confidence flat 0.50-0.95 then jumps at 0.99 | High (undermines confidence-gated routing, Praxion's most likely use case) |
| Data privacy / retention terms unclear | Official legal docs: "no training on user data" stated, but default (non-enterprise) retention period and data residency not found anywhere in crawled docs; ZDR is enterprise-only | Medium-High |
| Determinism / reproducibility | Non-autoregressive parallel model with probability-based answers; no seed/determinism guarantee found in API docs; self-consistency cookbook exists specifically because repeated calls can disagree | Medium |
| Task-fit mismatch ("no reasoning, atomic questions") | Official jaggedness page + independent findings: fails at counting, dates, multi-hop reasoning, no cross-question invariants, no built-in adversarial-input handling — several of these (counting, ordering, cross-signal invariants) are plausible needs in a routing/gating use case | Medium |
| Lock-in | New vendor, new API key, new billing relationship, no SLA; no migration path documented if TypeSafe changes terms or shuts down (single point of failure for any decision gated on it) | Medium |
| Marketing vs. measured reality gap | TypeSafe's own headline "193.6x faster / 444.6x cheaper" is explicitly built from TypeSafe's own 4-workflow eval with a reference derived by averaging two frontier LLMs' answers, not independent ground truth; two independent authors (jock.pl, kdnuggets) explicitly call this out and report smaller, mixed numbers | Medium (affects trust calibration on all vendor-supplied numbers, not a functional blocker per se) |

## Divergence Map

- **Jev launch date**: WebSearch-aggregated secondary sources say **2026-09-15**; a direct `WebFetch` of TypeSafe's own blog post returned **2026-09-24** as the "announcement published" date. Both claim to describe the same primary source (the TypeSafe launch blog post). Tier: both nominally Tier 1/derived-from-Tier-1, but mutually exclusive on a single fact. **Not resolved** — flagging both dates rather than picking one. [certainty: low — direct date conflict, no arbitration source found]
- **Jev's own docs latency claim**: "~100ms" (machine-learning-primer/how-to-build page) vs "70-500ms" (llms-full.txt summary, api.md-adjacent content) — both Tier 1 (official docs), internally inconsistent with each other, not a conflict between independent sources but worth flagging since it affects how tightly to trust the vendor's own latency SLA-adjacent claims. [certainty: med]
- **`fast-jev-compaction` package version**: `package.json` in the cloned working tree reads `0.2.0`; multiple GitHub issues (filed after my clone's commit) reference `0.3.0` at commit `e3f262a` (which *is* the HEAD I cloned). This suggests either an unpublished/untagged version bump or a `package.json` that lags behind issue-reporters' expectations — genuinely unreconciled, not chased further given scope. Tier: primary source (repo itself) vs primary source (issue metadata on the same repo) disagreeing with itself.
- **TypeSafe's own headline benchmark (193.6x/444.6x) vs independent benchmarks**: Not a factual contradiction so much as a **methodology divergence** — TypeSafe's number comes from its own 4-workflow eval scored against a GPT-6-Astra/Fable-5.1-averaged reference; jock.pl's and beri.net's independently-run benchmarks produce materially smaller (and in the single-question phishing case, *negative* for Jev vs Haiku) results. Both independent authors explicitly flag this divergence themselves rather than silently averaging it — treat TypeSafe's headline number as marketing-tier (Tier 3/4, self-reported) and the independent numbers as the more load-bearing evidence for any accuracy decision. [certainty: med — 2 independent sources converge on "distrust the vendor headline," but neither replicates the other's exact benchmark]
- No divergence found between the official docs' stated API contract (endpoint, schema, error codes) and any independent source that exercised the API directly (`fast-jev-compaction`'s `src/request.ts`, the issue #97 repro script) — the contract itself appears accurately documented.

## Open Questions

- Exact Jev launch date (see Divergence Map) — immaterial to the adoption decision but worth resolving before citing a date externally.
- Whether TypeSafe's default (non-enterprise) tier has any stated data retention window — not found anywhere in the crawled `legal.md` content; would need direct contact with `privacy@typesafe.ai` or reading the full DPA/Privacy Policy documents (only indexed, not fetched in full — the crawl reached the legal index page, not the underlying DPA/MCA/Privacy Policy documents themselves).
- OpenAI logprobs-based classification comparison — not researched in this pass; genuinely absent, not merely thin.
- Whether `fast-jev-compaction` issue #88's core claim (Claude Code hooks cannot substitute compaction) has since been acknowledged, disputed, or resolved by the maintainer — no response was visible in the commit log or open issue thread at time of research.
- Whether Jev has a documented async/batch endpoint distinct from "many questions per synchronous request" — no such endpoint was found in the crawled docs; "batching" in TypeSafe's own vocabulary means the latter only.
- Real-world (non-benchmark) accuracy of Jev on a routing/gating task representative of Praxion's actual candidate use cases (model/agent/skill/tier selection) — no source evaluated this specific task shape; all independent evaluations used support-ticket triage or phishing/email classification as proxies.

## Sources

- [docs.typesafe.ai/introduction](https://docs.typesafe.ai/introduction) — official product overview (Tier 1)
- [docs.typesafe.ai/llms.txt](https://docs.typesafe.ai/llms.txt) — full doc-site URL/title index (Tier 1)
- [docs.typesafe.ai/llms-full.txt](https://docs.typesafe.ai/llms-full.txt) — condensed full-doc-site content (Tier 1)
- [docs.typesafe.ai/introduction/quickstart.md](https://docs.typesafe.ai/introduction/quickstart.md) — setup, auth, first request/response (Tier 1)
- [docs.typesafe.ai/introduction/coding-agents.md](https://docs.typesafe.ai/introduction/coding-agents.md) — explicit non-replacement-for-LLM framing (Tier 1)
- [docs.typesafe.ai/concepts/system-one.md](https://docs.typesafe.ai/concepts/system-one.md) — System One concept, Kahneman framing (Tier 1)
- [docs.typesafe.ai/concepts/state.md](https://docs.typesafe.ai/concepts/state.md) — state format/constraints (Tier 1)
- [docs.typesafe.ai/concepts/how-to-build-with-system-one.md](https://docs.typesafe.ai/concepts/how-to-build-with-system-one.md) — architecture guidance, worked example (Tier 1)
- [docs.typesafe.ai/introduction/machine-learning-primer.md](https://docs.typesafe.ai/introduction/machine-learning-primer.md) — conceptual ML primer (Tier 1)
- [docs.typesafe.ai/primitives.md](https://docs.typesafe.ai/primitives.md), [primitives/choice](https://docs.typesafe.ai/primitives/choice.md)-equivalent content — the three primitives (Tier 1)
- [docs.typesafe.ai/confidence.md](https://docs.typesafe.ai/confidence.md) — confidence formula and guidance (Tier 1)
- [docs.typesafe.ai/patterns.md](https://docs.typesafe.ai/patterns.md), [patterns/confidence-routing.md](https://docs.typesafe.ai/patterns/confidence-routing.md) — architectural patterns (Tier 1)
- [docs.typesafe.ai/models.md](https://docs.typesafe.ai/models.md) — model list, limits, pricing, rate limits (Tier 1)
- [docs.typesafe.ai/api.md](https://docs.typesafe.ai/api.md) — full API reference (Tier 1)
- [docs.typesafe.ai/legal.md](https://docs.typesafe.ai/legal.md) — ToS/DPA/privacy index (Tier 1, incomplete crawl — index only)
- [docs.typesafe.ai/model-jaggedness/jev-1.13.md](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md) — known failure modes (Tier 1)
- [docs.typesafe.ai/sdk/python.md](https://docs.typesafe.ai/sdk/python.md) — Python SDK (Tier 1)
- [docs.typesafe.ai/agent-skill.md](https://docs.typesafe.ai/agent-skill.md) — TypeSafe's own Claude Code skill (Tier 1)
- [typesafe.ai/blog/introducing-system-one-models-and-jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) — launch announcement, architecture/RLCD claim, funding-adjacent framing (Tier 1, self-reported)
- [github.com/tamaratran/fast-jev-compaction](https://github.com/tamaratran/fast-jev-compaction) — cloned and read directly: README, `src/compact.ts`, `hooks/fast-jev.ts`, `hooks/README.md`, `package.json`, tests (Tier 2, primary source, ground-truth via `gh api`)
- [github.com/tamaratran/fast-jev-compaction/issues/88](https://github.com/tamaratran/fast-jev-compaction/issues/88), [/89](https://github.com/tamaratran/fast-jev-compaction/issues/89), [/97](https://github.com/tamaratran/fast-jev-compaction/issues/97), [/70](https://github.com/tamaratran/fast-jev-compaction/issues/70), [/99](https://github.com/tamaratran/fast-jev-compaction/issues/99), [/81](https://github.com/tamaratran/fast-jev-compaction/issues/81), [/82](https://github.com/tamaratran/fast-jev-compaction/issues/82), [/100](https://github.com/tamaratran/fast-jev-compaction/issues/100), [/86](https://github.com/tamaratran/fast-jev-compaction/issues/86), [/92](https://github.com/tamaratran/fast-jev-compaction/issues/92) — read directly via `gh api` (Tier 2, primary)
- [code.claude.com/docs/en/hooks](https://code.claude.com/docs/en/hooks), [claudefa.st/blog/tools/hooks/function-hooks](https://claudefa.st/blog/tools/hooks/function-hooks), `anthropics/claude-code#91870` — used to verify `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` is a real, early-access Claude Code feature (Tier 1/Tier 3 cross-check)
- [beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval](https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval) — most detailed independent benchmark + calibration study found (Tier 3, methodologically transparent)
- [thoughts.jock.pl/p/jev-typesafe-system-one-model-benchmark-2026](https://thoughts.jock.pl/p/jev-typesafe-system-one-model-benchmark-2026) — independent 40-ticket benchmark, explicit self-caveated sample size (Tier 3)
- [kdnuggets.com/what-everyone-is-getting-wrong-about-typesafe-ais-jev](https://www.kdnuggets.com/what-everyone-is-getting-wrong-about-typesafe-ais-jev) — critical analysis, schema-vs-correctness distinction (Tier 3)
- Hacker News launch thread(s) (`news.ycombinator.com/item?id=49745752` and related IDs surfaced via WebSearch) — community reaction, not independently re-fetched (Tier 4, secondary aggregation only)
- [pasqualepillitteri.it/en/news/17263](https://pasqualepillitteri.it/en/news/17263/typesafe-jev-open-source-clones-free-rtx-3090) — attempted fetch failed (socket hang up); open-source clone names (Laya, SWE-Pruner, Needle 3) corroborated instead via `fast-jev-compaction` issue #99, a primary source (Tier 2)
- WebSearch aggregations for founder/funding facts (firecrawl.dev, finance.yahoo.com articles) — Tier 3, not independently re-fetched, certainty flagged inline
- WebSearch aggregation for RouteLLM/NotDiamond/Martian/RouterArena figures — Tier 3, not independently re-fetched
- Pricing-aggregator sources for Claude Haiku 4.5 ($1/$5 per million tokens) — Tier 3, mutually consistent across ≥3 independent aggregator sites
