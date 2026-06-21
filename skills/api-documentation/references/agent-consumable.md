# Agent-Consumable API Documentation

The differentiator: documenting your API surface for an LLM consumer — the spec *is* the agent doc, the human-vs-agent divergence, agent-metadata discipline, llms.txt (honestly framed), and emerging machine-readable conventions. Back to [SKILL.md](../SKILL.md).

This reference expands core item 3 of the [universal core](../SKILL.md#3-humans-and-agents-diverge--mind-the-metadata) for the agent consumer. Adoption maturity is tagged per item — fast-moving conventions carry their contested evidence so you don't over-invest.

## 1. The Spec IS the Agent Doc Surface

For an agent, the **OpenAPI / JSON-Schema spec itself is the primary documentation surface** — not the rendered HTML page. Human prose docs are derived and secondary for agents; the spec's `summary` / `description` / `examples` are load-bearing. An LLM consumes the spec directly: publish the **raw spec at a stable, versioned URL** and that single act delivers the agent surface (the rendered docs in [`rest-openapi.md`](rest-openapi.md) are for humans).

Confidence: **High** — consistent across academic and vendor sources. A machine-readable spec at a stable URL is the shared backbone both audiences depend on.

## 2. Human vs Agent — Converge, Then Diverge

**Converge on:** accuracy, stable canonical URLs, working examples, clear naming, a single source of truth. Good structure helps both audiences.

**Diverge on:**

| Axis | Human docs | Agent docs |
|------|-----------|-----------|
| Token economy | Prose, repetition, narrative onboarding fine | Every token costs context; terse, de-duplicated |
| Structure | Headings + prose | Structured/typed (JSON Schema, OpenAPI), deterministic |
| Retrieval | Browse / search / scan | Deterministic fetch of a known stable artifact |
| Redundancy | Repeating context aids reading | Repeated field context wastes the context window |
| Self-description | Spec is reference material | **The spec IS the agent-facing surface** — it must be self-sufficient |
| Output shape | Rich nested payloads tolerable | Prefer simplified, deterministic, essential-field outputs |

The key consequence: an agent has no human intuition to fill gaps. The spec is its **entire mental model**, every call, with no persistent learning between calls.

## 3. Agent-Metadata Discipline (the highest-value lever)

This is the most actionable, least-contested area — strong skill-core material. Rich spec metadata matters **more** for agents than humans because the spec is all the agent has.

| Field | Why it's load-bearing for agents |
|-------|----------------------------------|
| **`operationId`** | Tool names derive directly from it (→ snake_case, ~60-char cap). Missing/poor `operationId` → opaque auto-generated names from method+path. **Mandate clean, unique, verb-noun `operationId`s.** |
| **`summary`** | Becomes the short tool description the LLM selects on. Vague/duplicate summaries cause tool mis-selection. |
| **`description`** | State preconditions and what the return value means — write it as if onboarding a teammate who has never seen the system. |
| **`example` / `examples`** | Concrete example values dramatically improve agent call correctness. |

Automated *enrichment* of API specs measurably improves tool-invocation success (arXiv 2509.11626) — evidence that **metadata quality is the bottleneck, not the model**. Confidence: **High**.

## 4. llms.txt / llms-full.txt — Honest Framing

**What it is.** A proposed convention (a markdown file at site root `/llms.txt`) giving LLMs a curated, HTML-free map of a site's most useful content. Proposed by Jeremy Howard (Answer.AI / fast.ai), 2024-09-03.

**Format (from the primary spec):** H1 project name (required); optional blockquote summary; optional body markdown; optional H2 sections of curated link lists (`[name](url): notes`); a special **"Optional"** H2 whose links may be dropped for a shorter context (an explicit token-budget affordance); a companion pattern of serving a clean `.md` version of each HTML page. **`llms-full.txt`** inlines the *full* resolved documentation (resolved specs, SDK examples, markup-stripped page content) for agents that want everything in one fetch.

**How it differs:** `robots.txt` = crawler permissions; `sitemap.xml` = exhaustive URL index for search. `llms.txt` is **curated for direct LLM ingestion** — not exhaustive, not permission-oriented.

**Adoption — carry this contested evidence honestly:**

- Niche until **Mintlify** auto-generated it across hosted docs sites (Nov 2024). Named adopters include Anthropic, Stripe, Cursor, Cloudflare, Vercel, Supabase, LangGraph, Mintlify. Roughly ~10% of docs-heavy sites.
- **No major LLM provider consumes it at meaningful volume.** OpenAI, Google, and Anthropic crawlers do not fetch it measurably; **Google explicitly rejected it**, comparing it to the discredited keywords meta tag.
- A 300,000-domain SE Ranking study (Nov 2025) found **no measurable lift in AI citations**.
- Anti-patterns are already forming in audited files (stale links, dumping the full sitemap, duplicating content).

**Recommendation.** Treat `llms.txt` as a **low-cost, low-risk, opt-in deliverable**: it helps *agents the user points at the docs* (Cursor, Claude Code, Copilot loading a URL) far more than *provider crawlers* (which largely ignore it). Generate one **when docs are already markdown-navigable**. **Do NOT promise SEO or citation benefits** — the contested evidence above belongs in front of the user so they don't over-invest. Confidence: **Medium**.

## 5. MCP as a Consumption Surface

Treat a REST OpenAPI surface and an MCP wrapper as **two surfaces of one capability**. The agent surface needs deliberate curation, not a generator dump — naive 1:1 OpenAPI→MCP mapping is a starting point, not production (tool explosion, human-targeted descriptions, over-nested responses). Documenting an MCP server well = disciplined `name`, agent-targeted `description`, complete input + **structured output** schema, an explicit **error grammar**, and progressive disclosure of the tool catalog.

Full treatment — tool catalog from live `tools/list` introspection, the design-vs-document seam vs `agentic-interface-design`, OpenAPI↔MCP divergence — is in [`mcp-docs.md`](mcp-docs.md). Confidence: **High** (production + academic convergence).

## 6. Emerging Conventions — Confidence-Tagged

| Convention | What | Maturity / verdict |
|-----------|------|--------------------|
| **`/.well-known/api-catalog`** (RFC 9727) | GET returns `application/linkset+json` listing all of an org's OpenAPI/AsyncAPI specs — a machine entrypoint for API discovery | **Real RFC, near-zero adoption** (~4 providers publish one as of mid-2026). Substance, but premature. Confidence: **Medium-low**. |
| **Machine-readable changelogs** | Stable URL returning plain Markdown per release for AI assistants | Emerging, vendor-led; credible, low adoption. Confidence: **Low-medium**. |
| **`llms-full.txt`** | Full resolved docs in one file | Tied to llms.txt fate — useful for pointed agents, ignored by crawlers. |
| **"APIs as MCP servers"** | Expose an API as MCP so agents discover/invoke without scraping docs | **Highest-substance trend** — backed by production tooling and Anthropic's protocol. |
| **OpenAPI Overlays** | Non-invasive spec-enrichment layer | Stable OpenAPI Initiative spec; practical for agent-tuning specs without forking the source. |

**Verdict:** MCP-as-surface and OpenAPI metadata enrichment are *substance*; `.well-known/api-catalog` and machine-readable changelogs are *credible-but-early*; `llms.txt` SEO/citation claims are *largely hype*, though its pointed-agent utility is real.

## Sources

- [Answer.AI — /llms.txt proposal (Jeremy Howard)](https://www.answer.ai/posts/2024-09-03-llmstxt.html) — primary spec, format, intent
- [Mintlify — What is llms.txt](https://www.mintlify.com/blog/what-is-llms-txt) — adoption catalyst + skeptic breakdown
- [PPC Land — adoption stalls](https://ppc.land/llms-txt-adoption-stalls-as-major-ai-platforms-ignore-proposed-standard/) — provider non-consumption
- [Search Engine Land — proposed standard](https://searchengineland.com/llms-txt-proposed-standard-453676) — Google rejection
- [earezki — 30-file llms.txt audit, anti-patterns](https://earezki.com/ai-news/2026-05-20-i-audited-30-llmstxt-files-in-the-wild-5-anti-patterns-are-already-forming/)
- [Fern — prepare APIs for AI agent consumption](https://buildwithfern.com/post/prepare-apis-documentation-ai-agent-consumption) — human/agent divergence, llms-full.txt
- [Google ADK — OpenAPI tools](https://google.github.io/adk-docs/tools-custom/openapi-tools/) — operationId→tool-name mechanics
- [arXiv 2509.11626 — API enrichment for tool invocation](https://arxiv.org/pdf/2509.11626) — metadata-quality bottleneck evidence
- [arXiv 2507.16044 — From REST to MCP (empirical study)](https://arxiv.org/html/2507.16044) — wrapping/generation
- [Speakeasy — MCP from OpenAPI, 50+ production servers](https://www.speakeasy.com/blog/generating-mcp-from-openapi-lessons-from-50-production-servers) — OpenAPI↔MCP divergence
- [API Evangelist — .well-known/api-catalog adoption](https://apievangelist.com/blog/2026/05/22/four-providers-publishing-well-known-api-catalog/) — RFC 9727 reality check
