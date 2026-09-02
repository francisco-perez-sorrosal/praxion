# Praxion Landscape Watchlist

> Praxion is the operational infrastructure for a development philosophy centered on context engineering, behavior-driven development, and incremental evolution — codifying that philosophy as the skills, agents, rules, and commands that downstream projects auto-discover and dogfood. This watchlist tracks the agentic-software-factory landscape Praxion exists in dialogue with: peer agentic-dev tools and orchestrators (so adjacent-project traction grounds promethean's idea generation and roadmap-cartographer's Opportunities lens), practitioner blogs that surface emergent context-engineering and agent patterns, and the governance bodies whose protocol decisions (MCP, A2A, AGENTS.md, llms.txt) propagate into Praxion's own design space. This file follows the llms.txt structural convention (consumed inbound, not exposed).

## Peer projects

Active agentic software factories, coding agents, and agent orchestrators. Watch for design patterns, context-engineering choices, and ecosystem-shaping decisions.

- [Superpowers (obra)](https://github.com/obra/superpowers): Claude Code skills plugin, 280k stars (2026-09-02), 14 harnesses; Praxion's nearest structural competitor — same shape, far more distribution, far less governance · last-checked 2026-09-02
- [GitHub Spec Kit](https://github.com/github/spec-kit): constitution → specify → plan → tasks; 133k stars; one workflow for all task sizes (the over-ceremony critique in Thoughtworks Radar v34 lands here) · last-checked 2026-09-02
- [OpenSpec (Fission-AI)](https://github.com/Fission-AI/OpenSpec): delta-specs against existing code, brownfield-first; 67k stars; closest peer to Praxion's SPEC_DELTA · last-checked 2026-09-02
- [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD): PM/architect/dev/QA personas, right-sized planning paths ("start anywhere"); 53k stars · last-checked 2026-09-02
- [Agent OS (Builder Methods)](https://buildermethods.com/agent-os): standards dir + "discover standards" from an existing codebase — a cheap primitive Praxion lacks · last-checked 2026-09-02
- [Conductor (Google Labs)](https://github.com/gemini-cli-extensions/conductor): Gemini CLI extension; context dirs in git shared across a team; tracks spec→plan→impl · last-checked 2026-09-02
- [Kiro (AWS)](https://kiro.dev): spec-driven IDE (EARS requirements → design → tasks), steering files, file-event hooks; known over-ceremony on small tasks · last-checked 2026-09-02
- [Factory.ai](https://factory.ai): "software factory" in the 2026 org-fleet sense; Agent Readiness (8 pillars × 5 levels) is the model `/project-metrics` adopts · last-checked 2026-09-02
- [Tessl](https://tessl.io): spec-as-source vision; engine not GA after ~9 months beta, repositioned to a spec registry — the cautionary case for climbing past spec-anchored · last-checked 2026-09-02
- [Beads](https://github.com/steveyegge/beads) / [Backlog.md](https://github.com/MrLesk/Backlog.md): git-native, agent-queryable task state; emerging convergence, nearest primitive to a "zero-repo-footprint" state namespace · last-checked 2026-09-02
- [Antigravity / Jules (Google)](https://antigravity.google): async agents with scheduled tasks and manager view; one of seven independent continuous-AI implementations · last-checked 2026-09-02
- [Aider](https://github.com/Aider-AI/aider): CLI-native pair programmer; SWE-bench bellwether; no push since 2026-05-22 (staleness flag) · last-checked 2026-09-02
- [Cline](https://github.com/cline/cline): IDE-embedded Plan/Act + MCP integration; watch fork churn (Roo archived, Kilocode) · last-checked 2026-04-30
- [OpenHands](https://github.com/OpenHands/OpenHands): Full agent platform (SDK + GUI + hosted); 86k stars; org moved from All-Hands-AI · last-checked 2026-09-02
- [SWE-agent](https://github.com/SWE-agent/SWE-agent): Princeton/Stanford academic origin; SOTA on SWE-bench Feb 2026 · last-checked 2026-04-30
- [Goose](https://github.com/aaif-goose/goose): AAIF governance realized — repo moved from block/goose; CLI + desktop · last-checked 2026-09-02
- [OpenCode](https://github.com/anomalyco/opencode): 203k stars; moved from sst/opencode; AGENTS.md-native, `.opencode/agent/*.md` subagents · last-checked 2026-09-02
- [ruflo (ex claude-flow)](https://github.com/ruvnet/ruflo): swarm orchestrator, 70k stars; renamed from claude-flow · last-checked 2026-09-02
- [Gas Town](https://github.com/gastownhall/gastown): Steve Yegge "Normsky" multi-agent orchestrator (tmux/beads) · last-checked 2026-04-30
- [Kilocode](https://github.com/kilo-org/kilocode): Roo + Cline superset; 500+ model support · last-checked 2026-04-30
- [Sweep](https://github.com/sweepai/sweep): Pivoted to JetBrains 2025; watch if GitHub-native flow revives · last-checked 2026-04-30
- [Cosine (Genie)](https://cosine.sh): SWE-Lancer 72%; closed-source but signal via benchmarks · last-checked 2026-04-30
- [Devin (Cognition)](https://devin.ai): Enterprise commercial agent; 67% PR merge rate; adoption signal · last-checked 2026-04-30
- [v0 (Vercel)](https://v0.dev): Frontend-only codegen; UX conventions for code-gen UI · last-checked 2026-04-30
- [Bolt.new](https://bolt.new): WebContainer-native full-stack agent; browser-native patterns · last-checked 2026-04-30
- [Lovable](https://lovable.dev): Full-stack MVP agent with deployment; non-technical-user adoption · last-checked 2026-04-30
- [LangGraph](https://github.com/langchain-ai/langgraph): v1.0 GA Oct 2025; durable-state agent orchestration · last-checked 2026-04-30
- [GitHub Agentic Workflows](https://github.com/github/gh-aw): Markdown-authored workflows in GitHub Actions, 5 engines, sandboxed jobs with validated safe-outputs; converges with Praxion's hub reusable-workflow pattern · last-checked 2026-09-02
- [agent-orchestrator (Untrivial-ai)](https://github.com/Untrivial-ai/agent-orchestrator): Per-agent git worktrees; structural overlap with Praxion; moved from ComposioHQ · last-checked 2026-09-02
- [prp (Wirasm)](https://github.com/Wirasm/prp): Product Requirement Prompts; renamed from PRPs-agentic-eng · last-checked 2026-09-02
- [AgentHub (k0msenapati)](https://github.com/k0msenapati/agent-hub): Agent platform; verify scope and activity on first /landscape-refresh · last-checked 2026-04-30

## Blogs / writers / feeds

Practitioner writing with original signal on agentic dev, context engineering, and agent architecture. Reputable individuals and engineering teams whose original ideas shape the field.

- [Simon Willison's Weblog](https://simonwillison.net): Tier-1 synthesizer of practitioner patterns · RSS: https://simonwillison.net/atom/everything/ · weekly+ · last-checked 2026-04-30
- [Latent Space](https://www.latent.space): swyx + Alessio; agent-labs interviews · RSS: https://www.latent.space/feed · weekly · last-checked 2026-04-30
- [Andrej Karpathy](https://karpathy.ai): Long-form essays on agentic engineering; sporadic but high-impact · last-checked 2026-04-30
- [Anthropic Engineering Blog](https://www.anthropic.com/engineering): Context-engineering and agent patterns from the source · irregular cadence · last-checked 2026-04-30
- [Steve Yegge](https://steve-yegge.medium.com): Normsky architecture and Gas Town essays · RSS: https://steve-yegge.medium.com/feed · last-checked 2026-04-30
- [Chip Huyen](https://huyenchip.com): AI Engineering book; ML-to-production patterns · RSS: https://huyenchip.com/feed · last-checked 2026-04-30
- [Hamel Husain](https://hamel.dev): Evals and agent-debugging methodology · last-checked 2026-04-30
- [Eugene Yan](https://eugeneyan.com): Production AI systems; agents-with-MCP · RSS: https://eugeneyan.com/atom.xml · last-checked 2026-04-30
- [Addy Osmani](https://addyosmani.com/blog): Browser/Web platform × agent patterns · last-checked 2026-04-30
- [Pragmatic Engineer](https://newsletter.pragmaticengineer.com): Enterprise-adoption signal from engineering-management view · paid · last-checked 2026-04-30

## Standards & convening bodies

Protocol working groups and foundations whose decisions propagate into Praxion's design space.

- [AAIF — Agentic AI Foundation](https://aaif.io): Linux Foundation; governs MCP, Goose, AGENTS.md; meta-watch (when AAIF moves, several entries shift together) · last-checked 2026-04-30
- [MCP — Model Context Protocol](https://modelcontextprotocol.io/specification/2025-11-25): Tool connectivity standard; v2.0 Streamable HTTP + OAuth 2.1 roadmap · last-checked 2026-04-30
- [A2A Protocol](https://a2a-protocol.org/latest/): Agent interoperability; v1.0 stable Q1 2026; Interop WG with MCP · last-checked 2026-04-30
- [AGENTS.md spec](https://agents.md): Open standard for agent instruction files in repos; adoption figures range 60K–600K projects across sources (methodology unresolved — quote neither) · last-checked 2026-09-02
- [Agent Skills open standard](https://agentskills.io): Anthropic-published SKILL.md standard, 47 client implementations (Codex, Cursor, Gemini CLI, Copilot, Kiro, OpenCode, Amp, VS Code); Praxion's `skills/*/SKILL.md` layout is conformant unchanged · last-checked 2026-09-02
- [llms.txt convention](https://llmstxt.org): Structural convention this watchlist itself follows · last-checked 2026-04-30
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python): Multi-agent SDK with handoffs, guardrails, tracing · last-checked 2026-04-30
- [LangGraph spec / LCEL](https://github.com/langchain-ai/langgraph): Stable-API commitment Oct 2025; orchestration substrate · last-checked 2026-04-30

## Reference repos

Canonical implementations and pattern-defining artifacts.

- [Anthropic platform.claude.com/docs/llms.txt](https://platform.claude.com/docs/llms.txt): Mintlify-generated faithful llms.txt example · last-checked 2026-04-30
- [Stripe llms.txt](https://stripe.com/llms.txt): Largest section count among adopters; uses `## Optional` · last-checked 2026-04-30
- [Vercel llms.txt](https://vercel.com/llms.txt): Fern-generated; pairs with `llms-full.txt` cache · last-checked 2026-04-30
- [Goose AGENTS.md](https://github.com/block/goose/blob/main/AGENTS.md): Major OSS reference for AGENTS.md authoring · last-checked 2026-04-30
- [OpenAI Codex AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md): Authoritative AGENTS.md authoring guide · last-checked 2026-04-30
- [Aider llms.txt (verify)](https://aider.chat/llms.txt): Existence unverified — confirm on first /landscape-refresh · last-checked 2026-04-30
- [disler/claude-code-hooks-multi-agent-observability](https://github.com/disler/claude-code-hooks-multi-agent-observability): Exemplary CLAUDE.md + hooks pattern · last-checked 2026-04-30

## Industry evidence

Measured or expert-assessed claims about whether agentic scaffolding helps. Weight these over vendor benchmarks; the divergences are documented in `docs/independent-analysis/personal-software-factory-analysis.md` § 2.6.

- [DORA 2025 — State of AI-assisted Software Development](https://dora.dev/dora-report-2025/): AI amplifies the existing system; seven-capability AI model (the 7th, quality internal platforms, is where individual gains become organizational) · verify the capability list against the PDF before quoting · last-checked 2026-09-02
- [METR — Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/): RCT, experts on mature repos 19% slower with 43-point self-assessment error; the falsifier any heavyweight process must answer · last-checked 2026-09-02
- [Thoughtworks Technology Radar vol. 34 — spec-driven development](https://www.thoughtworks.com/radar/techniques/spec-driven-development): SDD at Assess; bitter-lesson caution against handcrafted rule sets; "cognitive debt" and "progressive context disclosure" as named entries · last-checked 2026-09-02
- [Birgitta Böckeler — Understanding spec-driven development (martinfowler.com)](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html): spec-first / spec-anchored / spec-as-source ladder; MDD parallel; "false sense of control" finding · last-checked 2026-09-02
- [Harness engineering — martinfowler.com](https://martinfowler.com/articles/harness-engineering.html) and [OpenAI](https://openai.com/index/harness-engineering/): environment-as-artifact thesis; 1M-LoC zero-human-lines claim (vendor claim, greenfield; openai.com blocks non-browser fetches) · last-checked 2026-09-02
- Greenfield & Short, *Software Factories* (Wiley, 2004): the definition Praxion actually matches — schema + DSLs + patterns + tooling producing a family of similar applications

## Optional

Lower-priority entries — agents may skip these under tight context-window budgets. Demoted for low original-idea signal, not deactivated; cherry-pick when relevant.

- [Every / Dan Shipper](https://every.to): Productivity-leaning; lower signal for agentic dev specifically · last-checked 2026-04-30
- [Sourcegraph blog](https://sourcegraph.com/blog): Yegge + Liu essays appear here, but tone is self-promotional; cherry-pick · last-checked 2026-04-30

## Inactive / archived

Known-but-stale projects. Kept so future refreshes don't re-add them.

- Roo Code: `RooCodeInc/Roo-Code` archived 2026-05-15; no successor repo found (still listed on the agentskills.io client showcase — showcase is stale)
- Plandex: no push since 2025-10-03; keep off the active list until it moves
- AutoCode Labs: unresolvable phantom name in 2026-04-30 research
- LCEL standalone: absorbed into LangGraph 1.0 (Oct 2025)
- OpenDevin: renamed to OpenHands
- Klotho / Wing: both shut down 2024–2025
