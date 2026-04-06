# Solid Foundation Improvements

**Date**: 2026-04-01
**Goal**: Make Praxion the definitive companion for the full Software Development Lifecycle through context engineering excellence
**Sources**: Researcher (external landscape + codebase analysis) + Context-Engineer (ecosystem audit)

---

## Executive Summary

Praxion is **well ahead of the community** in several areas: the 12-agent pipeline with document-based coordination, tier-based process calibration, spec-driven development with REQ traceability, and progressive disclosure are all aligned with or exceed what thought leaders describe as best practices. The ecosystem scores **Health B, Coherence A** (sentinel assessment).

However, four SDLC phases remain weak or absent (Security, Deployment, Monitoring, Versioning/Release), the always-loaded token budget overshoots by 8.6%, and language coverage is Python-only. This report maps out concrete improvements to solidify the foundation and fill the gaps.

**Key external validation**: The ACE-FCA framework's "Research -> Plan -> Implement" pattern maps directly to Praxion's researcher -> systems-architect -> implementation-planner pipeline. Addy Osmani's finding that "three focused agents consistently outperform one generalist working 3x as long" validates the multi-agent approach. Progressive disclosure achieves 60-85x token savings in benchmarks — Praxion already implements this well.

---

## 1. Current State Assessment

### 1.1 Ecosystem Inventory

| Component | Count | Health |
|-----------|-------|--------|
| Skills | 26 | 24 A-grade, 2 B-grade |
| Agents | 12 | 11 A-grade, 1 B-grade (sentinel approaching size ceiling) |
| Rules | 6 (5 always-loaded, 1 path-scoped) | All A-grade but total exceeds token budget |
| Commands | 12 | 9 A-grade, 3 B-grade |
| Hooks | 7 scripts | All A-grade |
| MCP Servers | 2 (memory, task-chronograph) | Both A-grade |
| CLAUDE.md files | 11 | All accurate and consistent |

### 1.2 SDLC Coverage Map

| Phase | Coverage | Key Artifacts | Gaps |
|-------|----------|---------------|------|
| Ideation | **Strong** | promethean agent, roadmap-planning skill | — |
| Requirements/Specs | **Strong** | spec-driven-development skill, sdd-coverage command | — |
| Research | **Strong** | researcher agent, external-api-docs skill | — |
| Architecture | **Strong** | systems-architect agent, api-design, data-modeling, performance-architecture skills | No ADR management |
| Planning | **Strong** | implementation-planner agent, software-planning skill | — |
| Implementation | **Strong** | implementer agent, python-development, refactoring skills | Python-only language coverage |
| Testing | **Strong** | test-engineer agent, agent-evals skill, testing-strategy skill, testing-conventions rule, /test command | — |
| Code Review | **Strong** | verifier agent, code-review skill, `/review-pr` command | — |
| CI/CD | **Strong** | cicd-engineer agent, cicd skill, security review workflow, release workflow | Issue triage and docs freshness workflows still open |
| Documentation | **Strong** | doc-engineer agent, doc-management skill | No changelog generation |
| Deployment | **Weak** | — | No deployment patterns, IaC, or container orchestration |
| Monitoring/Ops | **Weak** | task-chronograph (pipeline-only) | No app-level observability skill |
| Security | **Strong** | context-security-review skill, verifier Phase 4.5, GH Actions PR workflow, /full-security-scan command, secret redaction hooks | General code security (SAST/DAST) deferred |
| Versioning/Release | **Strong** | Commitizen config, versioning skill, /release command, GH Actions release workflow, CHANGELOG.md | — |
| Learning/Retrospective | **Strong** | skill-genesis agent, sentinel, memory MCP (v2.0), ADR files in `.ai-state/decisions/`, observation layer | Memory v2.0 phases 1-3 shipped; multi-project split pending |
| Cross-Session Continuity | **Strong** | memory MCP (v2.0), precompact hook, .ai-state/, observation layer | Memory v2.0 shipped with access tracking, importance tiers, cross-references, provenance. Multi-project split pending. |

**Score: 15/16 Strong, 1 Moderate, 1 Weak** — security, testing, versioning, CI/CD, and memory gaps filled. Remaining gaps: Deployment and Monitoring/Ops.

### 1.3 Token Budget Status

*Updated 2026-04-06*

| Source | Chars | Est. Tokens | % Budget |
|--------|-------|-------------|----------|
| `~/.claude/CLAUDE.md` (global) | 8,330 | 2,380 | 15.9% |
| Project `CLAUDE.md` | 2,845 | 813 | 5.4% |
| `swe-agent-coordination-protocol.md` | 11,653 | 3,329 | **22.2%** |
| `agent-intermediate-documents.md` | 7,842 | 2,241 | 14.9% |
| `coding-style.md` | 5,858 | 1,674 | 11.2% |
| `adr-conventions.md` | ~3,990 | ~1,140 | 7.6% |
| `git-conventions.md` | 2,191 | 626 | 4.2% |
| `memory-protocol.md` | 4,382 | 1,252 | 8.3% |
| **Total** | **47,091** | **13,455** | **89.7%** |
| **Budget** | **52,500** | **15,000** | **100%** |
| **Headroom** | **5,409** | **1,545** | **10.3%** |

Budget was raised to 15,000 tokens. No longer in overshoot, but headroom is tight (10.3%). The coordination protocol grew from 9,338 to 11,653 chars and `memory-protocol.md` (4,382 chars) was added. Compression remains desirable for growth margin.

---

## 2. External Landscape Insights

### 2.1 Context Engineering Paradigm (2025-2026)

The industry has converged on "context engineering" as the core discipline. Key frameworks:

**LangChain's Four Strategies**:

1. **Write** — persist information outside the context window (scratchpads, memory, state)
2. **Select** — pull relevant information in when needed (RAG, retrieval, progressive disclosure)
3. **Compress** — reduce token usage via summarization, trimming, hierarchical compaction
4. **Isolate** — split context across sub-agents with focused windows

**HumanLayer ACE-FCA** — the most concrete methodology for coding agents:

- Maintain context window utilization at 40-60% capacity
- Three-phase workflow: Research -> Plan -> Implement, each producing a compacted artifact
- Sub-agents for context isolation: parent never sees raw output, only structured summaries
- Demonstrated on 300k LOC Rust codebase: 3-5 senior engineer days compressed to 1-7 hours

**Context Quality Hierarchy** (most to least harmful failures):

1. Incorrect information in context (worst — actively misleads)
2. Missing information (bad — agent can't reason correctly)
3. Excessive noise (problematic — degrades performance)

**Critical thresholds**: At 70% context utilization, Claude starts losing precision; at 85%, hallucinations increase; at 90%+, responses become erratic.

### 2.2 Where Praxion Leads

- **Progressive disclosure**: Praxion's three-tier loading (frontmatter -> SKILL.md -> references/) matches industry best practice. Benchmarks show 60-85x token savings.
- **Multi-agent pipeline**: The 12-agent pipeline with document-based coordination is among the most sophisticated in the ecosystem. Most tools have 2-4 agents at best.
- **Spec-driven development**: The SDD skill with REQ IDs, traceability matrices, and coverage commands is well ahead of community standard. GitHub's spec-kit (72.7k stars) validates the approach but lacks Praxion's depth.
- **Tier-based calibration**: The Direct-through-Full calibration is unique — most tools apply the same process regardless of task complexity.
- **Decision tracking**: Structured ADR files in `.ai-state/decisions/` with YAML frontmatter and MADR body sections.

### 2.3 Where the Community Has More

- **Security**: Trail of Bits provides Claude Code security configs and skills. Snyk Agent Scan, Semgrep MCP exist for automated security.
- **MCP ecosystem**: Mature MCP servers exist for GitHub (PRs, issues), databases (schema-aware queries), search (Brave, Exa), cloud (AWS, Terraform), and project management (Linear, Jira).
- **CI/CD templates**: `claude-code-action` enables full Claude Code in GitHub Actions (PR review, documentation, issue triage) for ~$5/month per 50 PRs.
- **ADR management**: Architecture Decision Records are becoming standard with AI assistants. Multiple templates and agentic generation approaches exist.
- **Memory systems**: Mem0 (91% response time reduction), Amazon Bedrock AgentCore Memory, and MemRL (reinforcement learning for memory) represent the state of the art.

---

## 3. Improvement Roadmap

### Priority 1: Critical Path (blocks quality or efficiency)

#### P1.1 — Compress Always-Loaded Token Budget

**Problem**: ~~8.6% overshoot persists across multiple sentinel audits.~~ Budget was raised to 15,000 tokens, resolving the overshoot. However, the coordination protocol grew from 9,338 to 11,653 chars and `memory-protocol.md` (4,382 chars) was added. Headroom is only 10.3% (1,545 tokens) — tight for adding new always-loaded rules.

**Status**: Partially resolved. No overshoot, but compression remains valuable for growth margin.

**Original solution** (still applicable for reclaiming headroom):

- Compressing "Proactive Agent Usage" into a tighter list — ~800 chars
- Reducing "Delegation Depth", "Background Agents", "Multiplicity check" to one-liners with skill reference — ~600 chars
- Converting "Coordination Pipeline" prose to diagram + reference pointer — ~400 chars

**Impact**: Would reclaim ~1,800 chars (~514 tokens) of headroom for future rules.

#### P1.2 — Fix Dangling TypeScript Skill Reference

**Problem**: `implementer.md` and `test-engineer.md` agent prompts reference `skills/typescript-development/SKILL.md` which does not exist. Silent failure when agents try to load it.

**Solution**: Remove the TS reference from agent Language Context sections (pragmatic given Python-first workflow). Create the skill later when TS work begins.

**Impact**: Eliminates silent failure path in two core agents.

#### ~~P1.3 — Fix api-design Undiscoverable References~~ DONE

All 5 reference files (`openapi-patterns.md`, `graphql-patterns.md`, `api-versioning.md`, `data-contracts.md`, `interface-contracts.md`) are now listed in `api-design/SKILL.md` and exist on disk.

---

### Priority 2: SDLC Gap Filling (new capabilities)

#### ~~P2.1 — Create `security` Skill~~ DONE

Implemented as `context-security-review` skill — scoped to context artifact security (CLAUDE.md, agents, skills, rules, hooks, commands). Includes:
- SKILL.md with 6 vulnerability categories, security-critical paths checklist, diff/full-scan modes
- `references/permission-baseline.md`, `references/hook-safety-contract.md`, `references/secret-patterns.md`
- GitHub Actions PR workflow (`context-security-review.yml`) with `--plugin-dir .` and structured JSON output
- Verifier agent Phase 4.5 security review integration
- `/full-security-scan` command for project-wide audits
- Quick wins: `.env` gitignore, secret redaction in hooks, Bash scoping in commands

#### ~~P2.2 — Create `testing-strategy` Skill~~ DONE

Implemented as `testing-strategy` skill with language-agnostic core and progressive disclosure for language-specific content:
- SKILL.md: test pyramid, mocking philosophy, fixture patterns, property-based testing, coverage philosophy, naming conventions
- `references/python-testing.md`: advanced pytest patterns (conftest architecture, hypothesis, coverage strategy, plugin ecosystem)
- Path-scoped `swe/testing-conventions.md` rule with 13 declarative constraints (auto-loads on test files)
- `/test` command with auto-detect framework and project runner support
- Cross-reference from python-development skill
- Pattern 2b added to skill-crafting for language/context-specific progressive disclosure

#### P2.3 — Create `deployment` Skill

**Why**: CI/CD covers pipeline authoring but deployment strategies are absent. No guidance for blue-green, canary, rolling deployments, feature flags, or infrastructure-as-code.

**Scope**:

- SKILL.md: Deployment strategy selection, rollback planning, environment management
- `references/deployment-strategies.md`: Blue-green, canary, rolling, A/B patterns
- `references/container-patterns.md`: Dockerfile best practices, multi-stage builds, orchestration
- `references/iac-patterns.md`: Terraform, CloudFormation, Pulumi basics
- `references/feature-flags.md`: Feature flag patterns, gradual rollout

#### P2.4 — Create `observability` Skill

**Why**: The task-chronograph MCP covers pipeline observability but there is no guidance for application-level concerns. Structured logging, metrics, distributed tracing, and alerting are unaddressed.

**Scope**:

- SKILL.md: Observability strategy, three pillars (logs, metrics, traces), instrumentation
- `references/structured-logging.md`: Log levels, structured formats, correlation IDs
- `references/metrics-design.md`: RED/USE methods, counter vs gauge vs histogram
- `references/distributed-tracing.md`: OpenTelemetry patterns, span design, context propagation
- `references/alerting-patterns.md`: Alert design, runbooks, on-call patterns

#### ~~P2.5 — Create `/review-pr` Command~~ DONE

Implemented as `/review-pr` command (`commands/review-pr.md`). Accepts PR number, branch name, or no argument (current branch). Uses the `code-review` skill in standalone mode with the structured report template. Supports `gh` CLI for PR metadata and diff fetching. The security workflow (`context-security-review.yml`) covers security-specific PR review separately.

---

### Priority 3: Strengthening Existing Components

#### P3.1 — Create `typescript-development` Skill

**Why**: The Claude Code/MCP/plugin ecosystem is heavily TypeScript/JavaScript. Agent prompts already reference this skill. The Idea Ledger identifies it as a future path.

**Scope**:

- SKILL.md: TypeScript conventions, type patterns, project structure
- `references/typescript-patterns.md`: Advanced types, generics, discriminated unions
- `references/node-tooling.md`: ESLint, Prettier, Vitest/Jest, tsx configuration
- `references/react-patterns.md`: Component patterns, hooks, state management (if applicable)

**Priority**: Create when TS work begins or when cross-tool compatibility becomes a focus.

#### P3.2 — Memory v2.0

**Why**: Industry research shows 15-25% of interaction time is re-establishing context. The Idea Ledger's phased upgrade plan directly addresses this.

**Phases** (from Idea Ledger):

1. ~~Access tracking + importance scoring~~ DONE — `access_count`, `importance` (1-10), three injection tiers
2. ~~Source provenance + dedup-on-write~~ DONE — `source` object with type/agent_type/session_id
3. ~~Cross-references between memories~~ DONE — `links` array with target/relation pairs (54 links across 37 entries)
4. Multi-project memory split (global vs project-local) — **NOT DONE**

**Additional v2.0 features shipped**: type ontology (gotcha/pattern/decision/etc.), soft delete with `status` field, `valid_at`/`invalid_at` timestamps, `confidence` field, observation layer (`observations.jsonl` with 1,883 events), hook-injected context at session start, `memory-protocol.md` rule, memory gate enforcement, metrics MCP tool.

**Industry benchmark**: Mem0 reports 91% response time reduction with structured memory. Amazon Bedrock AgentCore Memory provides enterprise-grade persistence.

#### ~~P3.3 — Create `security-reviewer` Agent~~ SUPERSEDED

Decided against a dedicated agent. Instead, the verifier agent gained Phase 4.5 (security review) by loading the `context-security-review` skill. The GitHub Actions workflow provides CI-side review. This follows the "extend existing" principle — extract to a dedicated agent only if the verifier's security phase grows too heavy.

#### P3.4 — Sentinel Size Reduction

**Problem**: The sentinel agent is at 414 lines, approaching the 500-line ceiling. The embedded check catalog (~100 lines of tables) is the main contributor.

**Solution**: Extract the check catalog to a reference file or skill that the sentinel reads at runtime.

#### P3.5 — Consolidate `/co` and `/cop` Commands

**Problem**: 90% identical content. Maintenance drift risk.

**Solution**: Merge into one command with optional `--push` argument, or extract shared commit logic into a common section.

#### ~~P3.6 — Create `/test` Command~~ DONE

Implemented as `/test` command with two-phase detection: project runner (pixi > uv > python -m > pnpm > yarn > npx > cargo > go) then test framework. Supports scoping: no arg (changed files), path, or `all`.

---

### Priority 4: Ecosystem Expansion (new integrations)

#### P4.1 — GitHub Actions Workflow Templates

**Why**: `claude-code-action@v1` enables full Claude Code in GitHub Actions for ~$5/month per 50 PRs. No templates exist in the repo.

**Templates to create**:

- `.github/workflows/pr-review.yml` — Automated PR review with Claude Code
- `.github/workflows/issue-triage.yml` — Issue labeling and initial response
- `.github/workflows/docs-update.yml` — Documentation freshness checks

**Open question**: Bundle opinionated templates or teach `cicd-engineer` to generate from context? **Recommendation**: Both — templates as starting points, agent for customization.

#### ~~P4.2 — ADR Management~~ DONE

Implemented by replacing `decisions.jsonl` with structured ADR files in `.ai-state/decisions/`:
- MADR-format Markdown files with YAML frontmatter for agent queryability
- `adr-conventions.md` rule with format spec, supersession protocol, agent writing/discovery protocols
- `scripts/regenerate_adr_index.py` for auto-generating `DECISIONS_INDEX.md`
- Systems-architect and implementation-planner create ADR files directly via Write tool
- Lightweight `adr_reminder.py` hook replaces the broken LLM extraction hook
- `decision-tracker/` package removed (1,774 lines of code with anthropic+pydantic dependencies eliminated)

#### P4.3 — MCP Server Integration Documentation

**Why**: Only 2 MCP servers (memory, task-chronograph). The ecosystem has mature servers for GitHub, databases, search, security, and project management.

**Approach**: Document integration patterns via the `mcp-crafting` skill rather than bundling servers (keeps the repo lean, avoids version coupling).

**Priority integrations to document**:

- GitHub MCP — PR/issue management within the pipeline
- Database MCP — Schema-aware queries during implementation
- Snyk/Semgrep MCP — Security scanning integration
- Search MCP (Brave/Exa) — Enhanced research capability

#### ~~P4.4 — Versioning and Release Automation~~ DONE

Implemented with Commitizen:
- Root `pyproject.toml` with `[tool.commitizen]` config, unified versioning across plugin.json + 3 subproject pyproject.toml files
- `versioning` skill with tool detection and progressive disclosure (commitizen reference)
- `/release` command (tool-agnostic, dev/patch/minor/major)
- GitHub Actions release workflow with dev pre-release defaults
- CHANGELOG.md, README badges

---

## 4. Cross-Tool Compatibility Assessment

| Component | Claude Code | Cursor | Claude Desktop | Gemini/Codex/Roo |
|-----------|-------------|--------|----------------|-------------------|
| Skills | Full | Partial (Agent Skills standard) | None | Partial (SKILL.md readable) |
| Agents | Full | None (different format) | None | None |
| Rules | Full | Partial (export to .cursor/rules/) | None | None |
| Commands | Full | Partial (plain Markdown) | None | None |
| Hooks | Full | None | None | None |
| MCP Servers | Full | Partial (different config) | MCP only | None |
| CLAUDE.md | Full | None (uses .cursorrules) | None | None |

**Assessment**: Skills are the most portable component. To maximize cross-tool reach, prioritize skill creation over agent-specific features. The `install.sh cursor` script handles Cursor export but could be extended for other tools.

---

## 5. Open Architectural Questions

These require user decisions before implementation:

| # | Question | Options | Resolution |
|---|----------|---------|------------|
| ~~1~~ | ~~Security skill scope~~ | ~~Single broad vs. decomposed~~ | **Resolved**: Built `context-security-review` — scoped to context artifact security. General code security deferred to a future `code-security-review` skill. |
| ~~2~~ | ~~Testing skill vs. expanding existing~~ | ~~New skill vs. folding into agent-evals~~ | **Resolved**: New `testing-strategy` skill with language-agnostic core + progressive disclosure for language-specific references. |
| 3 | TypeScript priority | Create now vs. wait for TS work | Wait — create when needed |
| ~~4~~ | ~~ADR format~~ | ~~MADR vs. extended decisions.jsonl vs. agent output~~ | **Resolved**: MADR format with YAML frontmatter in `.ai-state/decisions/`. Replaced `decisions.jsonl` entirely. |
| 5 | GitHub Actions templates | Bundle vs. generate | Both — templates as starting points |
| ~~6~~ | ~~Token budget resolution~~ | ~~Increase budget vs. compress rule~~ | **Resolved**: Budget raised to 15,000 tokens; at 89.7% usage with 10.3% headroom. Compression still desirable for growth margin. |
| 7 | MCP server expansion | Bundle servers vs. document patterns | Document patterns via skills |

---

## 6. Implementation Sequencing

Recommended order based on impact, dependencies, and effort:

### Phase 1: Foundation Fixes (1-2 sessions)

1. P1.1 — ~~Compress coordination protocol rule~~ Partially resolved (budget raised, 10.3% headroom — compression still valuable)
2. P1.2 — Fix dangling TS skill reference (removes silent failure)
3. ~~P1.3 — Fix api-design undiscoverable references~~ DONE
4. P3.4 — Sentinel size reduction (459/500 lines — approaching ceiling)
5. P3.5 — Consolidate /co and /cop (reduces maintenance surface)

### ~~Phase 2: SDLC Gap Filling~~ DONE

1. ~~P2.1 — Security skill~~ DONE (`context-security-review` + GH Actions workflow + verifier Phase 4.5 + `/full-security-scan`)
2. ~~P2.2 — Testing-strategy skill + testing-conventions rule~~ DONE
3. ~~P2.5 — /review-pr command~~ DONE
4. ~~P3.6 — /test command~~ DONE
5. ~~P4.4 — Versioning and release automation~~ DONE (Commitizen + `/release` + `versioning` skill + GH Actions)

### Phase 3: Expansion (3-5 sessions)

1. P2.3 — Deployment skill
2. P2.4 — Observability skill
3. ~~P3.3 — Security-reviewer agent~~ SUPERSEDED (verifier Phase 4.5)
4. P4.1 — GitHub Actions workflow templates (PR review for general code, issue triage, docs freshness)

### Phase 4: Polish (ongoing)

1. P3.1 — TypeScript skill (when TS work begins)
2. P3.2 — ~~Memory v2.0 phases 1-3~~ DONE; Phase 4 (multi-project split) pending
3. ~~P4.2 — ADR management~~ DONE
4. P4.3 — MCP server integration docs

---

## 7. Key External Sources

### Context Engineering Methodology

- [HumanLayer ACE-FCA](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md) — Frequent Intentional Compaction, 40-60% utilization target
- [LangChain: Context Engineering for Agents](https://blog.langchain.com/context-engineering-for-agents/) — Write/Select/Compress/Isolate strategies
- [Builder.io: 50 Claude Code Tips](https://www.builder.io/blog/claude-code-tips-best-practices) — Context utilization thresholds (70%/85%/90%)

### Agent Orchestration

- [Addy Osmani: The Code Agent Orchestra](https://addyosmani.com/blog/code-agent-orchestra/) — Three focused agents > one generalist
- [Microsoft: AI Agent Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) — Enterprise orchestration

### Spec-Driven Development

- [GitHub Spec Kit](https://github.com/github/spec-kit) — Open-source SDD toolkit (72.7k stars)
- [Martin Fowler: SDD Tools](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) — Analysis of Kiro, spec-kit, Tessl

### Security

- [Trail of Bits: claude-code-config](https://github.com/trailofbits/claude-code-config) — Security-focused Claude Code configuration
- [Trail of Bits: Security Skills](https://github.com/trailofbits/skills) — Security research skills
- [Snyk: Agent Scan](https://github.com/snyk/agent-scan) — Security scanner for AI agents

### Memory and Learning

- [Mem0](https://github.com/mem0ai/mem0) — 91% response time reduction with structured memory
- [Amazon Bedrock AgentCore Memory](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-memory-building-context-aware-agents/) — Enterprise memory management

### Progressive Disclosure

- [Progressive Disclosure MCP Benchmark](https://matthewkruczek.ai/blog/progressive-disclosure-mcp-servers.html) — 85x token savings
- [Anthropic: Extend Claude with Skills](https://code.claude.com/docs/en/skills) — Official skills documentation

### CI/CD

- [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions) — Full Claude Code in GitHub Actions
- [Claude Code Review](https://code.claude.com/docs/en/code-review) — Built-in four-agent review

### Community

- [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code) — Curated skills, hooks, commands, plugins
- [coleam00/context-engineering-intro](https://github.com/coleam00/context-engineering-intro) — PRP templates, slash commands pattern
