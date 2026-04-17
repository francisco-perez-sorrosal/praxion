# Evaluation Lens Framework

Methodology for deriving a **project-specific lens set** — the 4-8 evaluation lenses the `roadmap-cartographer` applies to a target project. Lens derivation replaces hardcoded universal lenses with a project-aware composition.

> Back to the skill: [../SKILL.md](../SKILL.md).

## Concepts

- A **lens** is an evaluation dimension: a named question-set applied to a project's state, with explicit evidence types and failure signals.
- A **lens set** is the 4-8 lenses chosen for a specific project at a specific audit time. The set is **derived**, not inherited.
- An **exemplar lens set** is a named, reusable composition (SPIRIT, DORA, SPACE, FAIR, CNCF Platform Maturity) that fits a recognizable project class. Exemplars are starting points, not defaults.

The SPIRIT six-dimension set (Automation · Coordinator Awareness · Quality · Evolution · Pragmatism · Curiosity & Imagination) is the exemplar Praxion uses for its own audits. It is not the canonical default for arbitrary projects — applying it to a project that doesn't match its shape is a cargo-cult anti-pattern (R4). Full SPIRIT detail is preserved in the [SPIRIT Appendix](#spirit-appendix-six-dimensions-in-detail) below.

---

## Why project-derived lens sets

Different project classes have different organizing concerns:

| Project class | What the audit must surface |
|---|---|
| Python library / CLI | API stability, type safety, docs, test coverage, release hygiene |
| Agentic eval framework | Hallucination rate, ground-truth quality, reproducibility, grader reliability |
| Data pipeline | Schema evolution, latency budgets, backfill safety, observability |
| Research code / notebooks | FAIR-ness, data provenance, citation integrity, reproducibility |
| Multi-agent dev tool (Praxion) | Automation, coordinator awareness, evolution, pragmatism, curiosity |
| Infrastructure platform | Investment, adoption, interfaces, operations, measurement |

Forcing any of these through SPIRIT produces a roadmap that under-emphasizes the actual decision drivers. SPIRIT's own Pragmatism dimension is the reason: use the right tool for the decision at hand.

---

## Four-step derivation methodology

### Step 1 — Inventory the project's own values

Read what the project says about itself. Sources, in priority order:

1. `README.md` — look for sections titled "Goals", "Non-goals", "Principles", "Why this exists", "What You Get"
2. `CLAUDE.md` / `AGENTS.md` — coordinator-facing intent, if the project is agentic
3. `CONTRIBUTING.md` — quality expectations, review standards
4. `docs/architecture.md` or equivalent — design intent
5. `CHANGELOG.md` — what the project prioritizes shipping vs. deferring
6. `.ai-state/decisions/` ADRs — recurring themes across architectural choices
7. Issues labeled `good-first-issue`, `help-wanted`, pinned — community-visible pain

Grep for phrases: `we value`, `our principles`, `principles`, `goals`, `non-goals`, `what we care about`, `design tenets`, `core beliefs`, `mission`.

**Extract**: 3-6 recurring themes the project's own docs emphasize. If a principles list exists (often bullets in README), quote it verbatim — these are candidate lens names.

### Step 2 — Inventory domain constraints

Read the project's paradigm, deployment shape, and stakeholders:

- **Paradigm** (deterministic / agentic / hybrid) — see [paradigm-detection.md](paradigm-detection.md). Detection feeds lens selection: agentic projects care about coordinator awareness; deterministic ones care about API stability.
- **Deployment model** — library / CLI / web service / embedded / research code / developer tool / internal platform
- **Team shape** — single maintainer, small OSS, large OSS, internal enterprise. Single-maintainer projects over-index on bus-factor and docs; large OSS over-indexes on contributor experience.
- **Stakeholders** — public users, internal teams, peer researchers, mixed
- **Constraints** — regulatory (HIPAA, GDPR, SOC2), latency/cost budgets, backwards-compatibility pledges, accessibility commitments

These shape which lenses deserve emphasis. A research repo emphasizes reproducibility and FAIR-ness; an internal enterprise tool emphasizes operations and observability.

### Step 3 — Compose the lens set

4-8 lenses drawn from three sources:

1. **Project values** (Step 1) — each recurring theme becomes a lens or folds into an existing one.
2. **Exemplar lens sets** ([catalog below](#exemplar-lens-sets)) — adopt whole, borrow individual lenses, or use for inspiration.
3. **Universal lenses** — almost every project benefits from a Quality lens (correctness, tests, CI) and a Docs lens (discoverability, onboarding).

**Rules of composition**:

- **Cap at 8** — more lenses produce thin per-lens findings; researchers can't go deep.
- **Floor at 4** — fewer loses multi-angle framing; findings skew to whatever the first lens sees first.
- **Each lens must be project-actionable** — "Quality" alone is too broad; "Test coverage on the critical-path modules" is actionable.
- **Prefer project vocabulary** — if the project's README calls it "robustness", use "Robustness" not "Quality".
- **Always include a Curiosity lens (or equivalent)** — the multi-angle reframe procedure (SKILL.md §"Multi-angle reframing") is universal regardless of the rest of the lens set.

### Step 4 — User confirmation (Gate 1)

The cartographer proposes the derived lens set via `AskUserQuestion`. Proposal format:

```text
Detected paradigm: [deterministic | agentic | hybrid]
Proposed lens set for this project: [L1, L2, ..., Ln]
Derived from:
  - Project values: [quoted principle or theme]
  - Domain constraints: [paradigm, deployment, stakeholders]
  - Exemplar reference: [SPIRIT | DORA | SPACE | FAIR | CNCF | Custom]
Accept, modify, or override with a named exemplar?
```

The user can:

- **Accept** — proceed with the proposed set
- **Modify** — add, remove, or rename individual lenses
- **Override with named exemplar** — "use SPIRIT", "use DORA"
- **Override with custom** — provide their own lens list

Whatever lands, the user's decision is recorded in the ROADMAP's Methodology Footer so the audit is auditable and reproducible. This is the SPIRIT Automation dimension in practice — automate the derivation, user-gate the outcome.

---

## Exemplar lens sets

### SPIRIT (Praxion's own; multi-agent tooling projects)

Praxion's six-dimension set. Applies when the project is a multi-agent coordination tool, an agent-oriented platform, or any project where the main product IS an AI-assisted workflow. Full worked detail in the [SPIRIT Appendix](#spirit-appendix-six-dimensions-in-detail) below.

1. **Automation** — SDLC scripted end-to-end with user gates only where judgment is required
2. **Coordinator Awareness** — main agent knows and wields the project's capabilities
3. **Quality** — non-negotiable; no workarounds, no silent failures
4. **Evolution** — keeping current with 2026 agentic-era practice without abandoning SWE rigor
5. **Pragmatism** — decisions grounded in measured internal + external evidence
6. **Curiosity & Imagination** — multi-angle framings, rejected options recorded

**When to use**: multi-agent coordination projects, LLM-application frameworks, AI-dev-tool projects, or Praxion itself.

### DORA (continuous-delivery products)

From the State of DevOps reports. Four metric-driven lenses good for web services, SaaS products, anything on a continuous-delivery track.

1. **Deployment Frequency** — how often does code reach production?
2. **Lead Time for Changes** — how long from commit to prod?
3. **Change Fail Rate** — what % of changes require rollback?
4. **Mean Time to Recovery** — how fast do incidents resolve?

**When to use**: web services, SaaS products, internal platforms with real deploy cycles.

### SPACE (developer productivity)

From the 2021 GitHub/ACM paper. Pick at least 3 of 5. Good for internal developer platforms and engineering productivity teams.

1. **Satisfaction and well-being**
2. **Performance** (code quality, review cycles)
3. **Activity** (commits, PRs, reviews)
4. **Communication and collaboration**
5. **Efficiency and flow** (interruptions, context switches)

**When to use**: internal dev-experience teams, DX platforms, productivity instrumentation projects.

### FAIR (research / data projects)

The data stewardship principles. Good for research codebases, scientific data repositories, reproducibility-oriented projects.

1. **Findable** — metadata + persistent identifiers
2. **Accessible** — retrievable with open protocols
3. **Interoperable** — standard schemas, vocabularies
4. **Reusable** — licensing + provenance + documentation

**When to use**: research code, data repositories, scientific pipelines, open-science platforms.

### CNCF Platform Maturity (infra platforms)

Five-dimension model from CNCF's platform-engineering guidance. Good for internal developer platforms, Kubernetes operators, infrastructure tooling.

1. **Investment** — resourcing adequate to mission
2. **Adoption** — teams actually using it
3. **Interfaces** — API / CLI / UX quality
4. **Operations** — observability, reliability, incident response
5. **Measurement** — outcome tracking (often the bottleneck)

**When to use**: IDPs, K8s platforms, cloud-infra tooling.

### Custom / Derived

When no exemplar fits, compose from scratch. Examples observed in practice:

- Data pipeline: `Schema Safety + Backfill + Latency + Observability + Compliance`
- Eval framework: `Hallucination Rate + Eval Integrity + Benchmark Coverage + Harness Robustness + Reproducibility`
- Python library: `API Stability + Type Safety + Docs + Coverage + Performance`
- Embedded firmware: `Determinism + Memory Safety + Power + Boot Reliability`

Custom lens sets require the [lens schema](#lens-schema) for each lens.

---

## Lens schema

Every lens — whether drawn from an exemplar or composed ad-hoc — must declare:

- **Name** — Title Case; use the project's own vocabulary where available
- **Definition** — 1-2 sentences: what does this lens care about?
- **Sub-questions** — 5-7 applied to the project's state; vary by paradigm where relevant
- **Evidence types accepted** — what counts as grounding a finding on this lens
- **Failure signals** — what to flag as a weakness under this lens
- **Example findings** — 1-2 concrete examples (optional but useful)

Paradigm-aware sub-questions: when the project is `agentic` or `hybrid`, include agentic-flavored sub-questions (e.g., for a Quality lens: "Are hallucination rates tracked?"). When `deterministic`, stay deterministic-flavored (e.g., "Is p99 latency budgeted?"). See the [SPIRIT Appendix](#spirit-appendix-six-dimensions-in-detail) for a worked example of paradigm-split sub-questions.

---

## Using the derived lens set in the audit

1. **Fan-out**: cartographer spawns N researchers where N = min(6, lens_count) per [audit-methodology.md](audit-methodology.md) parallel-invocation rules.
2. **One researcher per lens**: spawn with the lens name + sub-questions + evidence-type rubric.
3. **Fragments**: each researcher writes `.ai-work/<slug>/AUDIT_<lens-slug>.md`.
4. **Synthesis**: cartographer merges fragments into **four buckets** — strengths, weaknesses, **opportunities**, improvements — then composes deprecations from the merged picture. Weaknesses are deficit-framed; opportunities are forward-framed (new capabilities, strategic bets, evolution trends).
5. **Multi-angle reframe**: for the top 3 weaknesses, the cartographer articulates ≥2 framings (universal procedure regardless of lens set).

### Weaknesses vs Opportunities — which lenses feed which

- **Lenses that naturally surface weaknesses**: any lens with "Quality", "Reliability", "Operations", or similar deficit-oriented framing. Sub-questions often begin "Is X covered?", "Are errors handled?", "Does the CI gate Y?".
- **Lenses that naturally surface opportunities**: Evolution-class lenses (SPIRIT Evolution, CNCF Platform Maturity Adoption, DORA trending-improvement sub-questions) and Curiosity-class lenses (SPIRIT Curiosity & Imagination, FAIR reuse-extension). Sub-questions often begin "What external trend could the project ride?", "Which adjacent-project pattern applies here?", "What could X unlock if added?".
- A project that produces only Weaknesses and no Opportunities is structurally incomplete — the cartographer must seek out forward-looking material during synthesis, and if fragments don't surface it, explicitly query the Evolution/Curiosity lenses' "what's shifting" and "what's adjacent" sub-questions before finalizing.

The Methodology Footer of the emitted `ROADMAP.md` records which lens set was used, how it was derived (values + constraints + exemplar), and which researcher handled each lens — making every roadmap auditable and reproducible.

---

## Anti-patterns

- **Cargo-cult SPIRIT** — applying Praxion's six dimensions to a project that isn't a multi-agent tool. Adapt or replace.
- **Silent project-vocabulary mismatch** — using "Automation" when the project's README uses "Shipping Speed". Always prefer project vocabulary.
- **Floor violation (< 4 lenses)** — under 4 lenses fails multi-angle framing; findings skew to first-lens perspective.
- **Ceiling violation (> 8 lenses)** — over 8 produces thin per-lens findings; researchers can't go deep.
- **No user gate** — derivation without user confirmation strips SPIRIT-Automation (human-in-the-loop for architecture/design decisions).
- **Paradigm-blind sub-questions** — applying deterministic sub-questions to an agentic project misfires the audit (anti-pattern R15).
- **Exemplar-only thinking** — treating exemplars as the complete catalog. The `Custom / Derived` branch is first-class; novel projects get novel lens sets.

---

## SPIRIT Appendix: six dimensions in detail

The worked example of a full exemplar lens set. This is the content originally in `six-dimension-lens.md`, preserved verbatim because it is the reference Praxion uses for its own audits and because it illustrates every element of the lens schema above.

### Automation

**Definition**: Maximize automation across the SDLC while preserving user involvement at architecture, design, and deployment decision points. Automation that removes user judgment from high-stakes decisions is a regression.

**Sub-questions — deterministic projects**:
- Are build, test, lint, and release steps scripted end-to-end (no manual glue)?
- Does CI run the full quality gate (format, lint, type check, test) on every change?
- Are deployments automated behind a user-gated promotion step?
- Are repetitive developer tasks (scaffolding, migrations) codified as commands/scripts rather than tribal knowledge?
- Where is the user required in the loop, and is that gate intentional or an automation gap?

**Sub-questions — agentic projects**:
- Are hooks used for deterministic enforcement (pre-commit, post-tool, session-start) rather than agent self-policing?
- Do agent-to-agent handoffs avoid human bottlenecks for low-stakes steps, while surfacing high-stakes steps for user approval?
- Are pipeline artifacts written to disk automatically, or does the user shepherd them manually?
- Is memory persistence (`remember`/`recall`) automated at session boundaries, or dependent on agent vigilance?
- Where does the pipeline require user judgment, and is that a principled gate or an automation gap?

**Evidence types**: CI workflow files and step coverage; hook registrations; pipeline agent handoff declarations; manual-step counts from recent transcripts.

**Failure signals**: procedural runbooks ("run `make deploy` and watch"); quality checks that exist locally but not in CI; user-gate points with no declared rationale.

**Example findings**:
- *Deterministic*: "CI runs `pytest` but skips `ruff`; regressions ship. Evidence: `.github/workflows/test.yml` has no `ruff check` step."
- *Agentic*: "Memory `remember()` required by hook but subagents lack the tool injection, so gate blocks silently. Evidence: `agents/sentinel.md` + hook config."

### Coordinator Awareness

**Definition**: The main coordinator agent (Claude Code, Cursor, or equivalent) must surface and wield the project's capabilities — skills, agents, commands, rules, MCP servers — without the user re-teaching them each session.

**Sub-questions — deterministic projects**:
- Does `README.md` map capabilities to tasks (decision tree or index)?
- Is onboarding documentation current, or does it describe a prior architecture?
- Do tooling discoverability aids exist (`make help`, `scripts/README.md`, command catalogs)?
- Are conventions captured as enforceable rules (linter configs, pre-commit hooks) rather than prose?
- Can a new contributor ship a change without reading every file?

**Sub-questions — agentic projects**:
- Is there an `AGENTS.md`, `CLAUDE.md`, or equivalent loaded automatically that covers available capabilities?
- Does the coordinator proactively recommend the right agent/skill/command, or wait to be told?
- Is pipeline topology documented and discoverable (coordination-protocol rule, pipeline diagram)?
- Are delegation deliverables documented where the coordinator sees them (always-loaded config, not deep references)?
- Does the coordinator have a way to verify subagent deliverables landed on disk?

**Evidence types**: presence/recency of `AGENTS.md` or `CLAUDE.md`; always-loaded token budget; recent session transcripts; delegation-checklist placement.

**Failure signals**: capability exists but coordinator never invokes it (write-only artifact); docs describe an architecture the code no longer reflects; subagent reports "complete" while deliverable missing.

**Example findings**:
- *Deterministic*: "`README.md` documents a 2023 CLI layout; four commands renamed since. New contributors waste ~1h before finding current syntax."
- *Agentic*: "`memory-mcp` exposes a `metrics()` tool the coordinator never calls; tool is absent from coordinator's `allowed-tools`. Evidence: `claude/config/CLAUDE.md`, `memory-mcp/src/memory_mcp/server.py`."

### Quality

**Definition**: Non-negotiable. Quality takes precedence over expediency — no workarounds, no sloppy shortcuts, no silent failures. When trade-offs surface between shipping fast and shipping right, this dimension selects "right" and demands explicit rationale for deviation.

**Sub-questions — deterministic projects**:
- Does the test suite cover behavioral criteria, not just happy paths?
- Are lint/type/format checks required before merge, or only advisory?
- Are errors handled explicitly at boundaries, or silently swallowed?
- Is technical debt tracked (issues, ADRs, roadmap entries) or accumulating silently?
- Do release artifacts get verified before distribution?

**Sub-questions — agentic projects**:
- Are agent behaviors under evaluation (eval framework, regression tests), or only tested ad hoc?
- Do prompts include turn-budget awareness, error handling, and partial-output contracts?
- Are LLM outputs grounded in verifiable sources (citations, file refs, tool results)?
- Is memory curation enforced (deduplication, archival, importance hygiene)?
- Do pipeline artifacts pass structural validation before downstream consumption?

**Evidence types**: test counts + coverage reports (with methodology); CI gate configuration and pass/fail history; error-handling patterns in critical paths; eval framework breadth; memory write:read ratio.

**Failure signals**: tests run locally but not in CI; error handlers catch and discard without logging; "TODO: handle this" comments older than 90 days in production paths; agent prompts without turn-budget guidance; memory write-only skew.

**Example findings**:
- *Deterministic*: "631 tests pass locally; CI runs zero. Regressions ship undetected. Evidence: `.github/workflows/` has no `test.yml`."
- *Agentic*: "Eval framework is a stub (1 evaluation type). Skill changes cannot be validated for quality impact. Evidence: `evals/` listing."

### Evolution

**Definition**: Traditional software engineering rules hold, but the agentic-era landscape shifts quickly. Stay current with standards, tooling, and practice — without chasing fads. Evolution is selective adoption grounded in evidence, not novelty-seeking.

**Sub-questions — deterministic projects**:
- Are dependency versions current, or lagging significantly behind upstream?
- Is the architecture compatible with current best practices (containerization, observability, CI/CD patterns)?
- Are deprecated APIs or language features still in use where modern alternatives exist?
- Has the project adopted standards convergence (OpenAPI, OpenTelemetry, SBOM formats) where applicable?
- Does the project track upstream releases relevant to its dependencies?

**Sub-questions — agentic projects**:
- Does the project align with 2026 agentic-coding conventions (MCP, AGENTS.md, A2A, AAIF)?
- Are skills/agents/rules versioned or marked with staleness indicators?
- Has the project adopted evaluation frameworks aligned with industry practice (Promptfoo, DeepEval, SWE-bench, LLM-as-judge)?
- Is observability (tracing, span hierarchies) aligned with OpenInference or equivalent conventions?
- Does the project publish patterns in a form portable across coordinators (not Claude-Code-specific)?

**Evidence types**: dependency manifests vs upstream latest (with fetch date); external research sources with publication dates; ADRs documenting evolution decisions; cross-tool compatibility claims.

**Failure signals**: dependencies >1 major version behind with no tracked upgrade plan; architecture pattern documented as "our way" with no acknowledgment of industry convergence; no external-research citations in recent planning artifacts; standards adoption claimed but not implemented.

**Example findings**:
- *Deterministic*: "`httpx` pinned to 0.24 (released 2023-10); integration uses old `client.events()` shape. Evidence: `pyproject.toml`, `external-api-docs` skill drift check."
- *Agentic*: "MCP + AGENTS.md + A2A converging under AAIF (2026); project exposes MCP but not AGENTS.md — cross-tool portability gap. Evidence: `.claude-plugin/plugin.json`, repo root listing."

### Pragmatism

**Definition**: Results through decisions grounded in external research and internal codebase evaluation. Pragmatism favors the concrete over the abstract, the measured over the imagined, and the sufficient over the perfect. It is the force that stops gold-plating and starts shipping.

**Sub-questions — deterministic projects**:
- Are architectural decisions backed by evidence (benchmarks, profiles, prior-art comparisons)?
- Is scope disciplined (MVP shipped before nice-to-haves pile up)?
- Are trade-offs documented (ADRs, LEARNINGS) with rejected alternatives explained?
- Is optimization driven by profiling, or by intuition?
- Are rewrites justified by measured pain, or by aesthetic preference?

**Sub-questions — agentic projects**:
- Are roadmap items backed by audit evidence (`file:line` citations, metrics), not speculation?
- Is pipeline tier selection driven by measurable signals (file count, complexity), or by habit?
- Are "we should probably..." suggestions grounded in an observed weakness, or imported from external trends?
- Is agent prompt length justified by capability, or inflated by defensive instructions?
- Do memory entries carry importance calibrated to actual reuse, or inflated by authoring bias?

**Evidence types**: ADR bodies with Considered Options and explicit cons for rejected options; benchmarks/profiles/user-feedback cited in prioritization; `file:line` references in weaknesses; external research citations (URL + fetch date) paired with internal anchors.

**Failure signals**: "industry best practice" claimed without citation; metrics stated as round numbers without source; architectural debates resolved by seniority rather than evidence; roadmap items with no Evidence line.

**Example findings**:
- *Deterministic*: "Proposed rewrite of module X cites 'maintainability concerns' but has no bug/change-frequency data. Evidence: `git log` on the module shows 2 changes in 18 months."
- *Agentic*: "Roadmap W3 claims 'coordinator burden unsustainable' — quantified at 30+ decisions per pipeline with citation. Evidence: `rules/swe/swe-agent-coordination-protocol.md` line count."

### Curiosity & Imagination

**Definition**: Multi-angle framing and creative recombination prevent single-point-of-view traps. When stuck, change the angle: approach the problem from a different stakeholder, a different layer, a different timescale, or a different paradigm. Sometimes the answer is a twist on the current view; sometimes it is a fusion of angles.

**Sub-questions — deterministic projects**:
- For significant decisions, are multiple options considered explicitly, or is the first-viable-option default silently accepted?
- Are alternative framings documented (ADR "Considered Options") rather than rationalized post hoc?
- Does the team borrow patterns from adjacent domains (FP, game engines, embedded systems) when relevant?
- Are rejected approaches kept accessible (ADRs, LEARNINGS) for future reconsideration?
- Do retrospectives challenge prior assumptions?

**Sub-questions — agentic projects**:
- Does the cartographer spawn multiple researchers with distinct lenses (not one generic sweep)?
- Are rejected agent-pipeline shapes documented alongside the chosen shape?
- Does the project combine patterns from multiple frameworks (LangChain, Goose, crew-based, protocol-based) rather than committing to one orthodoxy?
- Do skills encourage reframing (alternative angles, competing hypotheses) or converge on single answers?
- When a plan fails, does the team explore rejected options, or repeat the failing approach?

**Evidence types**: ADRs with 3+ Considered Options (not chosen + strawman); LEARNINGS entries recording rejected approaches with rationale; research-phase fragments citing multiple paradigm sources; skill content encouraging multi-angle analysis.

**Failure signals**: ADRs where only the chosen option is meaningfully described; roadmaps picking a direction without naming rejected options; planning sessions converging on first suggestion; architectural monocultures.

**Example findings**:
- *Deterministic*: "Last three ADRs describe chosen option in depth; rejected options each get one sentence. Imagination signal low — may indicate foregone conclusions. Evidence: `.ai-state/decisions/NNN-*.md` body lengths."
- *Agentic*: "Cartographer fans out to 6 researchers with distinct lenses; synthesis surfaces cross-lens tensions as 'Considered Angles'. Evidence: `audit-methodology.md`."
