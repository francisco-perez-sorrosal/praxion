# Prompt Versioning

Git-first discipline; envelope-manifest shape (see `../assets/envelope-manifest.yaml`); rollout guards; rollback; A/B deployment patterns; DSPy/MIPROv2 as a compilation layer; platform specifics.

Back to: [../SKILL.md](../SKILL.md)

## When to Read This File

Load this deep dive when you are:

- Setting up prompt versioning on a new project for the first time.
- Evaluating prompt-management platforms (LangSmith, Langfuse, PromptLayer, Humanloop, Braintrust, Maxim AI, Mirascope).
- Designing rollout strategy — percentage splits, canary, rollback.
- Integrating DSPy/MIPROv2 into an existing prompt workflow.
- Structuring prompts for prompt-caching hit stability across versions.
- Migrating from "prompts live in the code" to a dual-track (git + platform) setup.

`SKILL.md` covers the consensus (pin the envelope, two-track practice, rollout discipline at summary level). This file gives the operational depth.

## Prompts Are Deployable Artifacts

A prompt is a configuration artifact with more failure modes than a typical config row:

- **Non-determinism**: the same prompt with `temperature > 0` produces different outputs.
- **Model dependency**: a prompt optimized for one model may underperform on another.
- **Subtle semantic drift**: a one-token change can shift accuracy on a long-tail class.
- **Envelope coupling**: the prompt is meaningful only with its `(model, temperature, max_tokens, tools, schema, effort, ...)` envelope.

Treat every prompt update with the same change-management discipline as a service deployment: reviewable diff, test suite, rollout plan, rollback plan, observability.

## Pin the Full Envelope

A "v3 prompt" without the envelope is not a deployable artifact — it is a fragment. The envelope manifest (`../assets/envelope-manifest.yaml`) pins:

- **`prompt_id`** — stable across versions (e.g., `issue-classifier`).
- **`version`** — monotone, human-readable (`v3`, not a git SHA, though a git SHA may be embedded for traceability).
- **`model`** — dated, exact model ID (e.g., `claude-sonnet-4-x` if the project has confirmed the ID via `external-api-docs`). Never ship a family-level name in production.
- **`created_at`** — ISO-8601 UTC.
- **`created_by`** — identity of author for audit.
- **`parent_version`** — the version this replaces or extends.
- **`rollout`** — `dev` / `canary` / `prod` / `percentage:N`. Traffic-label-driven, not replace-in-place.
- **`rollback_version`** — the target on failure.
- **`evaluation_id`** — the eval run that gated this release. Prompts should not be promoted to `prod` without an associated eval outcome.
- **`envelope`**: `temperature`, `top_p`, `max_tokens`, `stop`, `schema_hash` (content-addressed), `tools`, `reasoning_effort` (when applicable).

The manifest lives in git alongside the prompt body. When using a prompt-management platform, the platform becomes the canonical writer but the manifest is still committed for auditability.

### Schema hashing

When structured output is in play (`./structured-output.md`), the schema is part of the envelope. A hash of the schema content (e.g., `sha256` of the canonicalized JSON) gives you a content-addressed identifier. Two prompts with the same text and the same model but different schemas are different versions.

### Tools block

Tool registrations (names + schemas) are part of the envelope. Tool changes (new tool, renamed argument) trigger a new prompt version even if the prompt text is unchanged.

### Reasoning-effort parameter

When the target model has a reasoning knob (`reasoning_effort`, `thinking: adaptive`), the setting is part of the envelope. Moving from `medium` to `high` is a version change and should be re-evaluated.

## Two-Track Practice

Most production teams run both tracks and accept the dual source of truth.

### Track 1: Git-native

Prompt files in the repo, reviewed in PRs, deployed with the app.

Best for:

- Prompts that change with code (they call internal functions, reference internal schemas, or are invoked inside pipelines whose structure also evolves).
- High-stakes prompts where review discipline matters.
- Prompts that must deploy atomically with service changes.

File layout that scales:

```
prompts/
  issue-classifier/
    v1.md              # prompt body
    v2.md
    v3.md              # current
    manifest.yaml      # envelope manifest listing all versions
    CHANGELOG.md       # human-readable changelog
    evals/
      v3-fixtures.yaml # test inputs + expected outputs
```

Prompts referenced from code via a stable ID (`issue-classifier`) and version; the loader picks the active version from the manifest's `rollout` field.

### Track 2: Prompt-management platform

A CMS-style store with API/SDK pull, labels, A/B split.

Best for:

- Prompts iterated by non-engineering roles (product, prompt-ops).
- A/B experiments where traffic split must be adjustable without redeploy.
- Cross-repo reuse of the same prompt.

See **Platform Selection** below.

### When the two tracks disagree

Drift between git and the platform is inevitable without discipline. Mitigations:

- **Platform as source of truth, git as mirror**: a CI job syncs platform-approved versions into git on a schedule. Git diffs let code review notice semantic changes.
- **Git as source of truth, platform as cache**: the platform holds materialized copies of git-versioned prompts; the CI deploy pushes to the platform.
- **Read-only platform**: the platform is used only for analytics/observability, not for authoring.

Pick one; document it; enforce it in CI.

## Rollout Discipline

### Traffic labels over hard cutovers

Do not replace a prompt in place. Instead:

- Deploy the new version alongside the old (`v3` next to `v2`).
- Tag traffic by label (`prod`, `canary`) or percentage (`prod:90`, `canary:10`).
- Monitor metrics (error rate, output-quality score, p95 latency, cost per request) for the canary slice.
- Promote to full `prod` only when canary metrics meet the release gate.

### Release gate

At minimum:

1. **Eval suite passed** (`./prompt-testing.md`). The eval run's ID is pinned in the manifest's `evaluation_id`.
2. **No regression on the existing fixtures** — the v3 suite is a superset of v2's fixtures plus any new ones; v2 fixtures must still pass.
3. **Canary metrics within tolerance** for a defined window (e.g., 24h, 1M requests, whichever comes first).

### Changelog per version

A human-readable `CHANGELOG.md` or manifest field answering "why did this change?" Six months later, when a regression surfaces, the changelog is the first place you read. Bullet points at most; one sentence per change is ideal.

### Rollback

- Every version has a `rollback_version`. Rollback is re-labeling (swap `prod` to `v2`), not redeploy.
- Rollback triggers: accuracy regression, cost spike, unexpected refusal rate, safety incident.
- Log the rollback event with reason; feed the reason into the next iteration's changelog.

### Kill-switch

For safety-sensitive prompts (anything user-facing that can take an action), have a kill-switch that routes traffic to a known-safe fallback (prior version, or a non-LLM deterministic path). The kill-switch is part of the release checklist.

## A/B Testing and Experimentation

A/B testing is a superset of rollout: you route some percentage to `v3` and some to `v2`, measure a metric, and decide.

### What to measure

- **Output correctness** via an eval suite. Run the eval against both versions with the same test inputs.
- **User-observed quality** via production metrics (task completion, session length, explicit thumbs-up/down).
- **Cost per successful request** — total cost (prompt + completion + retries) divided by successful task count. A "better" prompt that doubles cost may not be net positive.

### Statistical rigor

- Run long enough to reach statistical significance for the primary metric. Underpowered experiments ship the wrong decision.
- Account for non-stationarity — traffic distribution drifts over weeks; a/b'ing across a month captures the drift.
- Pre-register the metric; do not go fishing for a metric that says your new version is better.

### Multi-armed bandit as an alternative

For prompts with many candidate versions, a multi-armed bandit allocates traffic dynamically toward better-performing versions. Most prompt-management platforms support this natively. The tradeoff vs. A/B: faster convergence but harder to reason about counterfactuals.

## Cache-Friendly Prompt Structure

Prompt caching (Anthropic, OpenAI, others) reduces cost and latency for stable prefixes. To preserve cache hits across prompt versions:

- Keep the **stable prefix** (system prompt, few-shot block, tool definitions) **first** and byte-identical across minor edits.
- Put volatile content (the user message, retrieval context) **last**.
- When you must edit the stable prefix, cut a new prompt version — the cache miss is expected.
- Cacheable block sizes vary by provider: Anthropic Opus/Sonnet require ≥ 1024 tokens per cached block; Haiku requires ≥ 2048. Blocks below the threshold silently do not cache. See `claude-ecosystem` for the current thresholds.

Cache-friendliness trades off against instruction-after-data positioning (`./prompt-injection-hardening.md`). Resolve by keeping the system/tool content stable at the head and placing the instruction shortly before the untrusted user input, not at the very end of a long prefix. The stable prefix can still end above the cache threshold even with the instruction closer to the end.

## DSPy / MIPROv2 as a Compilation Layer

DSPy (Stanford) reframes prompting as programming: you write a program that calls modules (Predict, ChainOfThought, etc.), specify a metric, and let an optimizer compile a better prompt + exemplar set. MIPROv2 is the current flagship optimizer in DSPy.

### When to use

- Pipelines with a **measurable metric** (accuracy on a labeled set, pass@k on generated tests, eval score).
- Prompts with a non-trivial exemplar block — the optimizer picks the exemplar set.
- Budget for optimization runs (MIPROv2 costs tokens proportional to program size × trials).

### When not to use

- Creative or open-ended tasks without a scalar metric.
- Prompts that change rarely and are already well-tuned — the optimization cost may exceed the gain.
- Early prototyping — hand-tune until the problem is clearly solvable, then optimize.

### Workflow

1. Define the DSPy program (modules, signatures).
2. Collect a labeled dataset (small is fine — MIPROv2 works with O(100) examples).
3. Define a metric that maps `(input, predicted, expected) → bool` or `→ float`.
4. Run MIPROv2 with a budget; the output is a compiled prompt variant + exemplar set.
5. **Commit the compiled prompt to git** with a new version number. The optimizer output is code, not runtime configuration.
6. Gate deployment via the same eval + rollout flow as a hand-written prompt.

### Relationship to hand-tuning

DSPy is not a replacement for hand-tuning — it is a mechanical co-pilot. Hand-tune for comprehensibility and edge cases; run MIPROv2 to sweep exemplar sets and instruction phrasings that humans miss. Combine.

## Platform Selection (Practitioner Notes)

### LangSmith

LangChain-native, trace-linked debugging, eval and prompt-registry features. Best when the application already runs on LangChain or LangGraph. Outside that ecosystem, the integration tax is meaningful.

### Langfuse

OSS (self-hostable) + cloud. OpenTelemetry-native, multi-provider, prompt CMS + evals + tracing in one package. Strong choice for teams with data-residency needs or multi-provider stacks. The self-host path takes real ops work; factor it in.

### PromptLayer

SaaS, git-like registry + visual diff. Simplest mental model for small teams. Less strong on eval integration.

### Humanloop

Strong non-technical authoring UX; eval coupled to authoring. Best when product or prompt-ops people iterate.

### Braintrust

Eval-first; prompt versioning secondary. Best when eval is the primary motion (a lot of A/B experimentation, a lot of golden-dataset curation).

### Maxim AI

End-to-end (prompt + eval + observability). Enterprise one-vendor preference. Evaluate lock-in seriously.

### Mirascope

Code-first library with content-addressable versioning. Richer than raw git; lighter than a platform. Good middle ground when a full platform is overkill but a manifest alone is underkill.

### DSPy

Not a platform — an optimizer library. Combine with git-native or platform-based versioning for the authoring and deploy surfaces.

### What drifts between platforms

Cost, latency, feature surface (new tracing views, new eval types, policy controls) drift quarterly. The table in `SKILL.md` is a starting set, not a scorecard. Verify specifics via the vendor's docs or `external-api-docs` before committing.

### Evaluation checklist for platforms

- Prompt versioning model (immutable vs. mutable; label-based vs. branch-based).
- Rollout primitives (labels, percentage, A/B, bandit).
- Eval integration (built-in vs. bring-your-own).
- SDK coverage in your project's language(s).
- Data residency (self-host available? region constraints?).
- Observability integration (OpenTelemetry? vendor-specific tracing?).
- Export path (if the vendor goes away, can you export the prompts and metadata?).
- Cost model (per-prompt-call? per-seat? per-eval?).

## Migration Between Versions

Common migration shapes:

- **Text edit, same model**: minor version bump, re-run eval suite, canary → prod.
- **Model upgrade, same text**: treat as an independent experiment; re-tune prompt elements (few-shot ordering, reasoning effort) because behavior shifts. See `./prompt-testing.md` for the independent-experiment rule.
- **Text + model together**: bad practice. Split into two version bumps so you can attribute regressions.
- **Schema change**: `schema_hash` changes → new version. If the schema change is additive (new optional fields), old clients still work; if breaking, coordinate with consumers.
- **Few-shot set change**: new version. Exemplar set is part of the envelope for reproducibility.

## Cross-References

- `../SKILL.md` — overview of envelope pinning and platform matrix.
- `./prompt-testing.md` — eval suite that gates promotion; non-determinism discipline.
- `./few-shot-patterns.md` — exemplar set as part of the envelope.
- `./structured-output.md` — schema hashing in the envelope.
- `./reasoning-and-cot.md` — reasoning-effort as a pinnable envelope field.
- `../assets/envelope-manifest.yaml` — canonical starter manifest.
- Sibling skill: `claude-ecosystem` — prompt-caching thresholds (Opus/Sonnet 1024, Haiku 2048) that constrain cache-friendly layout.
- Sibling skill: `external-api-docs` — verify current SDK parameter shapes before pinning envelope fields.
- Sibling skill: `agent-evals` — eval CI architecture beyond single-prompt testing.

## External Sources

- DSPy docs — https://dspy.ai/ — MIPROv2 optimizer.
- *Optimizing Instructions and Demonstrations* (arxiv 2406.11695).
- LangSmith, Langfuse, PromptLayer, Humanloop, Braintrust, Maxim AI, Mirascope — vendor docs (verify current).
- Anthropic, *Prompt caching* — block-size thresholds and 5m/1h tiers.
- OpenAI, *Prompt caching* — provider-specific semantics.
