## v0.18.0 (2026-07-30)

### Feat

- record discipline-gap signals for human disposition
- prove discipline-consult loop live, first ledger rows

### Fix

- settle the always-loaded budget basis and correct T02
- close verification findings and archive the spec
- widen finalize rewrite scope to the consult ledger and specs
- revise the discipline-expansion criterion after its first consult

## v0.17.0 (2026-07-30)

### Feat

- **commands**: add /consult human entry point
- extend sentinel BC03 and P07 to the discipline consultant
- document Discipline directive and wire self-nomination
- document the discipline-consultant dialogue protocol
- bind statistician into the discipline registry
- **skills**: add applied-statistics skill
- add discipline-consultant agent, registry and live invariants
- add disposition ledger and extensibility fitness test
- **state**: add identity-consultant design, ADRs and spec
- **python-development**: add curated library catalog + version idioms

### Fix

- **skills**: correct CI-overlap inference in benchmarking guidance

## v0.16.0 (2026-07-29)

### Feat

- Add dashboard Copy-as-prompt handoff feature
- Add prompting-UX touchpoints from technique research
- Add HTML authorship boundary pre-commit guard
- Add project-owned label-taxonomy manifest + reconciler
- Add cross-model INTAKE gate + shared PROJECT-PRISM
- Add P6 self-healing metrics collector
- **upgrade**: /upgrade-project resolves + forwards hub SHA (P3b Scope C)
- **upgrade**: re-point ci-autofix caller hub SHA + add cross-model caller (P3b Scope B)
- **onboard**: install cross-model review caller in 8e.8 (P3b Scope A)
- **ci**: autofix PR-check + Dependabot + fork surfaces (P3a)
- **ci**: server-side finalize workflow for web-UI merges
- **issue-autofix**: add label-gated triage-first issue autofix workflow
- **issue-autofix**: add issue_triage template-validation module
- **sidecar**: wire healing sidecar into /onboard-project + sync docs
- **sidecar**: add SessionStart hook to surface pending feedback
- **sidecar**: add /report-praxion-issue HITL command
- **sidecar**: add reporter CLI + ecosystem-defect issue template
- **sidecar**: add praxion_feedback reporter package + gitleaks fixture allowlist
- **ci**: add cross-model-review caller template + Praxion caller #1
- **ci**: add reusable-cross-model-review hub
- **onboarding**: install ci-autofix caller + policy via /onboard-project
- **ci**: refactor Praxion autofixer into hub caller #1
- **ci**: P1 group A+B — hub reusable workflow + installable templates
- **ci**: cap CI autofixer at a daily run budget

### Fix

- Add agentic-transactions-architect to the architecture diagram
- Restore calibration_log.md append-only chronological order
- Make issue-autofix read fixer_model from policy
- Make autofix JS/TS install package-manager-aware + robust
- Harden autofix fixer against terminal-state stranding + polyglot thrash
- **ci**: allowlist dependabot[bot] for the autofix fixer (P3a follow-up)
- **ci**: add daily-budget gate to the autofix-fork job (V-01)
- **state**: rewrite dangling dec-draft ref to dec-284 in calibration log
- **issue-autofix**: gh --jq lacks --arg; interpolate ISSUE_NUMBER inline
- **sidecar**: make report_praxion_issue.py runnable as a plain file
- **ci**: cross-model gate — add --force to bypass Cursor workspace-trust prompt
- **ci**: cross-model gate — explicit --api-key, .result envelope unwrap, stderr
- **ci**: unflake dsl-validate — align architect-validator gate with its protocol

### Refactor

- **finalize**: share on-main entry + strict-mode gate

## v0.15.0 (2026-07-17)

### Feat

- canonical block refresh mechanism (manifest-only)

### Refactor

- trim agent-pipeline block to pointer form

## v0.14.0 (2026-07-16)

### Feat

- wire the eval-ledger producer (append_eval_log_row)
- emit first-class skill_activation events from the WAL emitter
- evidence-bundle artifacts for the readiness LLM judge
- add Railway agent-integration recipe to skills

### Fix

- two CI-surfaced portability defects from the report-only run
- backfill re_affirmed_by ADR reciprocity (sentinel I3/DL06)
- resolve td-038/td-039 ledger id collisions (sentinel I2)
- regenerate AGENTS.md.tmpl from CLAUDE.md

## v0.13.0 (2026-07-02)

### Feat

- **dashboard**: make manifest renderer field the highest-priority resolver key
- **dashboard**: add five per-artifact renderer components
- **dashboard**: add dedicated Tutorial/HowTo/Concepts Diátaxis shells
- add install.sh --dev-link mode for plugin-cache local testing
- add commit-time calibration reminder hook with canary tests
- add calibration-log Retrospective cells as skill-genesis harvest source
- widen calibration coverage detector to any-tier task commits

### Fix

- finalize_adrs frontmatter branch strip immune to hyphenated user slugs (td-052)
- resolve td-050 aria-hidden-on-ancestor a11y defect in DiagramModal
- deterministic worktree-path briefing for spawned subagents (td-034 residual)
- **dashboard**: add secondary allowlist for documentation surface paths (td-029)
- make subprocess coverage consistent with branch mode
- unwrap updatedInput envelope in subagent context hook

### Refactor

- **hooks**: consolidate subagent prompt injection into single emitter

## v0.12.0 (2026-06-29)

### Feat

- auto-regen committed doc_manifest in the finalize chain (R12b)
- exclude volatile .ai-work from committed doc_manifest (R12b)
- give P06 a mechanical CODE-kind gate-liveness checker (EA-06)
- separate done vs in-flight slugs in dashboard workshops view (R9-dash)
- add RD01 readiness-feedback gate + document eval human-gating (R8)

### Fix

- build_doc_manifest excludes dirs by path relative to root
- content-gate the program.md ML-detection signal (R19b)
- make datetime.UTC usage portable to Python 3.9 (EA-10)

### Refactor

- clean_work_safety reads registry cleanup_policy (EA-11)

## v0.11.3 (2026-06-27)

### Feat

- split detection from production in artifact registry
- add retain-last-N report pruning (prune_reports.py)
- add the production-gate cohort (spec-archival, calibration, challenge, stale-slug)
- grow the artifact registry into a declarative production-gate spine
- raise the TASK_BRIEF floor to mandatory at Standard/Full
- bound the recovery WAL with rotation + windowed read
- conditional eval specs via ArtifactSpec activation (closes F-10 follow-up)
- stale-slug advisory for .ai-work cleanup (F-21); resolve F-22
- sentinel CA03 detects calibration-log under-logging (F-11)
- add canonical artifact registry + drift gate (F-04)
- add state-aware /clean-work safety gate

### Fix

- remove dead PRAXION_DISABLE_MEMORY_* env-var family
- close F-16 disposition gap + reconcile audit verification pass
- root-align PreCompact PIPELINE_STATE path

### Refactor

- build_doc_manifest reads the registry (R18/EA-11)
- consolidate idea ledger into one living file
- strip on-demandable fields from doc_manifest
- split always-loaded artifact inventory to a reference (F-03)

## v0.11.2 (2026-06-25)

### Fix

- remove remember() obligation from PreCompact snapshot hook
- reconcile SYSTEM_DEPLOYMENT with dec-225 memory removal

### Refactor

- complete dec-132 DESIGN.md path migration in active guidance

## v0.11.1 (2026-06-23)

### Fix

- **ci**: graceful auth fallback for security review
- **ci**: disable empty uv cache in non-uv jobs
- **ci**: normalize d2 stamp to end diagram drift

## v0.11.0 (2026-06-23)

### Feat

- add pipeline truncation recovery

## v0.10.0 (2026-06-21)

### Feat

- **observability**: per-type healthcheck guidance + agent linkage
- **dashboard**: add readiness-lean /api/health route
- **metrics**: make healthcheck detection monorepo-aware
- sharpen Service Observability Baseline — structlog #1 Python, pino #1 Node
- add typecheck + logging baseline clauses to implementer and systems-architect
- add dependabot.yml.tmpl asset and onboard-project Phase 8e.7 sub-step
- add canonical structlog logging module
- **agent-evals**: add simulation-testing reference
- **agent-evals**: add online-evals + budget-gate reference
- **skills**: add agent-runtime-guardrails discipline skill
- **skills**: add agent-failure-taxonomy classification skill
- **agent-evals**: add eval-rigor reference — calibration + split gates
- add on-demand SPECS_INDEX generator
- add per-project principles artifact (advisory/blocking gates)
- add lightweight intra-step pair-review for risky steps
- add proactive spec-drift detection (detect-and-surface)

### Fix

- **dependabot**: group updates to stop per-dependency branch sprawl
- **pre-commit**: exclude generated .ai-state reports from large-file guard + record re-measures

### Refactor

- unify commit gate into the pre-commit framework

## v0.9.2 (2026-06-20)

### Fix

- sanitize ADR slug and warn on stranded drafts at finalize

## v0.9.1 (2026-06-20)

### Feat

- add /upgrade-project to re-point version-pinned project surfaces

## v0.9.0 (2026-06-19)

### Feat

- version-aware onboarding — drift detection, manifest, cleanup
- wire pipeline agents to consume TASK_BRIEF.md
- add goal-disambiguation intake mechanism

### Fix

- harden ADR draft-id authoring; reconcile Phase 8f producer claim
- guard finalize against plugin-cache writes; widen cross-ref scope
- resolve consumer repo root in finalize-chain scripts

### Refactor

- share repo-root resolver; drop scripts/ from cross-ref sweep

## v0.8.0 (2026-06-18)

### Feat

- engrave multi-perspective deliberation primitives into pipeline
- add multi-perspective-analysis skill (composition layer)

## v0.7.1 (2026-06-17)

### Fix

- migrate Claude workflows to CLAUDE_CODE_OAUTH_TOKEN auth

## v0.7.0 (2026-06-17)

### Feat

- embed SOLID for the AI era as the Balanced Coupling principle
- add api-documentation skill, /document-api command, dashboard API rendering
- delete the in-house curated-memory subsystem
- extract ADR injection into standalone inject_decisions hook

### Fix

- preserve full tool_input in inject_subagent_context hook (td-021)
- regenerate AGENTS.md.tmpl after CLAUDE.md memory removal

### Refactor

- stop shipping memory machinery in onboarding
- remove memory as a source and proposal type from skill-genesis
- drop memory.json from reconcile and inject_rules seams

## v0.6.0 (2026-06-06)

### Feat

- integrate Nebius as a managed neocloud provider

## v0.5.0 (2026-06-06)

### Feat

- bootstrap CLAUDE.md during onboarding instead of punting
- promote prompt versioning to managed convention
- add eval leaderboard dashboard panel
- add benchmark-leakage detection + eval CI smoke-test
- wire verifier tolerance bands to EVAL_RESULTS.md
- populate eval-data-governance rule + add data-governance skill ref
- add /scores eval leaderboard command
- scaffold rules/eval namespace + register eval-ledger inventory
- add run-store backend abstraction + convention tests
- add run-ledger schema for agentic-eval storage spine
- load .env in project-metrics CLI
- dual-axis metric trend charts in dashboard
- add code-quality baselines to Phase 8e
- code-quality baseline for managed projects
- recommendations + weighting for readiness

### Fix

- align data-governance dataset_sha mismatch severity to FAIL

## v0.4.1 (2026-06-04)

## v0.4.0 (2026-06-04)

### Feat

- add agent-readiness skill, docs, and ADRs
- render agent-readiness section on the metrics dashboard
- add agent-readiness scoring engine to project-metrics
- add release-staleness advisory check

### Fix

- **ci**: repair claude-review auth and context-security-review JSON parse

## v0.3.0 (2026-06-03)

### BREAKING CHANGE

- The `/eval` slash command and the `praxion-evals list` /
`praxion-evals behavioral` subcommands are removed with no shim. To reproduce
the old behavioral verdict, invoke:

### Feat

- **agents**: harden agentic-transactions capability
- **agents**: add agentic-transactions capability
- **parallel**: ui defaults panes+none, per-session yolo override
- **parallel**: add praxion-parallel + web launcher
- **systems-architect**: add Phase 2.5 pre-refactor assessment + mini-pipeline contract
- **eval-praxion**: harden v1 against nested-Claude-Code deadlock
- add /eval-praxion v1 (Praxion self-eval framework)
- **verifier**: de-dup Phase 3a + extend T03 exception to verifier
- **sentinel**: recalibrate T03 for the irreducible Check Catalog
- add gate-canary coverage meta-test + retrofit canaries (L2)
- add sentinel Gate Liveness family + GL02 detector (L3)
- add gate-liveness principle and canary recipe (L1)
- register Python topology selector identifiers
- capture load-bearing assumptions in LEARNINGS
- gate planner on architecture completeness
- auto-suppress memory-protocol when memory MCP is off
- add agent return contract to the pipeline
- add decisions.base ADR browser + usage docs
- harden Obsidian Shape B link safety
- switch obsidian-skills install to claude plugin marketplace
- add Obsidian integration onboarding
- activate test-topology protocol (M2)
- **dashboard**: improve four surface pages
- **ci**: add autofix workflow for CI failures
- thread Conversation into philosophy + blocks
- add Conversation Checkpoints to the pipeline
- sharpen Surface Assumptions discipline
- add --hackathon flag to new_project.sh
- **hackathon**: add opt-in hackathon mode
- add test-baseline disposition contract
- invert skill-genesis to pull-driven mode
- **rework**: hybrid rework dispatch script + osascript notification hook
- Add verifier rework loop (Phase 12.5 + /resume-rework)
- **rules**: warn on blacklist YAML misuse + ceiling docs
- **rules**: defense-in-depth against stale rule symlinks
- **rules**: extend YAML blacklist to symlinked rules
- **rules**: auto-place blacklist template in target projects via SessionStart hook
- **rules**: add per-project rules blacklist mechanism
- **researcher**: add continuous-improvement loop
- **hooks**: worktree-orientation SessionStart banner (roadmap P5)
- **onboarding**: project-essentials CLAUDE.md block + thin-tier template (roadmap P2)
- **dashboard**: professional console UI overhaul
- add interface-designer agent + 4 skills
- redesign dashboard with interactive visualizations
- add TypeScript/Node polyglot skill support
- **codex**: mirror Claude shared config surfaces
- update codex bridge
- translate agent routing
- **codex**: complete canonical hook bridge
- **codex**: bridge memory and observability hooks
- **codex**: register canonical MCP servers
- **codex**: Route via AGENTS.md
- Export Codex pipeline adapter
- **codex**: export Praxion slash commands as Codex skill wrappers
- add Codex rules bridge
- export codex skill wrappers
- add native Codex project onboarding
- Add Codex AGENTS adapter
- **versioning**: drop PEP 440 dev pre-releases for SemVer-only flow
- **streamlit**: metrics_view renderer — aggregate snapshot + redirect cue
- **streamlit**: architecture_explorer renderer — three-pane tabbed view
- **streamlit**: idea_grid renderer — proposal cards + ledger status tabs
- **streamlit**: verification_report renderer — color-coded findings
- **streamlit**: how_to_shell renderer — sections TOC + quick links
- **streamlit**: explanation_shell renderer — reading-mode wrapper
- **streamlit**: reference_shell renderer — anchored TOC + sortable large tables
- **streamlit**: adr_card renderer — frontmatter chips + supersede graph + body collapse
- **streamlit**: Documentation page — manifest-driven dispatch (HTML-D)
- **streamlit**: doc-surface component library + manifest generator (HTML-B + HTML-C generator)
- **dashboard**: rework Streamlit metrics page with semantic KPIs + dark theme
- **hooks**: add SessionStart context-surface measurement for data-driven audits
- add Praxion pipeline dashboard
- integrate sentrux into metrics viewer + ship to onboarded projects
- add opt-in sentrux structural quality sensor integration
- **agents**: add token-discipline guidance
- **hooks**: state-driven finalize chain via post-{merge,commit,checkout}
- add ML/AI training project archetype
- tech-debt ledger pair (active + resolved)
- **docs**: User-facing AaC+DaC explanation essay + README/concepts/CHANGELOG
- **aac-dac**: Idea 8 — onboarding-aware AaC tier (greenfield ON, existing OFF)
- **aac-dac**: Bundle X — bidirectional REQ↔arch traceability + sentinel AC extension
- **aac-dac**: Ship v1.1 — enforcement layer + likec4 skill + Diátaxis companion
- **aac-dac**: Wire architect-validator into agent ecosystem (Phase 4)
- **aac-dac**: implement v1 foundation (Phases 0-3)
- **aac-dac**: record v1 design as ADR drafts
- **rules**: allow orchestrator as ledger writer
- Add per-project landscape watchlist
- Encode dual-toolchain convention in skill + agent prompts
- Migrate .ai-state/ARCHITECTURE.md L0 and L1 diagrams
- Migrate live docs/architecture.md L1 to LikeC4 + D2
- Migrate architecture templates to LikeC4
- Wire LikeC4 MCP server and AI tooling references
- Add diagram regeneration hook and test harness
- Adopt dual-toolchain diagram conventions
- Default merge policy to fast-forward only
- Establish test-topology protocol (trunk-only)
- **commands**: Extract canonical CLAUDE.md blocks to single source of truth
- **onboarding**: Self-host guard for plugin source repos
- Praxion-first-class enforcement + install completeness
- **onboarding**: Rebuild commands, rename, self-awareness pass
- **model-routing**: Apply post-review cleanup pack (items 6-11)
- **model-routing**: Apply post-review fix-pack (items 1-5)
- **model-routing**: Add per-agent model routing policy
- **tech-debt**: Add ledger contract to doc-engineer
- **tech-debt**: Add ledger contract to implementer
- **tech-debt**: Add ledger contract to planner
- **tech-debt**: Add ledger contract to test-engineer
- **tech-debt**: Add ledger contract to architect
- **tech-debt**: Migrate verifier to ledger writes
- **tech-debt**: Add sentinel TD dimension
- **tech-debt**: Add ledger dedupe script (GREEN)
- **tech-debt**: Create ledger and mark Built
- **tech-debt**: Register ledger schema in rule
- **tech-debt**: Draft ledger and integration ADRs
- **project-metrics**: Surface Top-N languages by SLOC in scc subsection
- **project-metrics**: Document --refresh-coverage opt-in flag
- **project-metrics**: Slim MD to executive summary; filter ecosystem dirs
- **test-coverage**: Default pythonpath="." in skill's Python reference config
- **installer**: Offer optional Python tooling install (uv + dev group)
- **verifier**: Add test-coverage discretion guidance
- **pyproject**: Adopt test-coverage skill default config
- **project-metrics**: Add --refresh-coverage opt-in flag + tests
- **commands**: Add /project-coverage thin-wrapper command
- **test-coverage**: Add skill scaffold (dispatcher+renderer, Python v1)
- **installer**: Offer optional scc install for /project-metrics
- **project-metrics**: Add /project-metrics command with trend UI
- **dev**: Add claude-dev launcher for live-edit plugin development
- **installer**: Add /praxion-complete-install for marketplace-only users
- **installer**: Add --from-local flag for uniform dev-mode install

### Fix

- **parallel**: switch /color injection to safe-mode (task wins)
- **parallel**: swatch tracks /color dropdown + auto-inject /color + project picker
- **parallel**: pre-flight HEAD check + subshell stdout leak + bytes JSON
- **parallel**: warp diagnostics + panes layout + iterm2 splits
- **eval-praxion**: scan .ai-work in working tree, fail-soft judge loop
- **eval-praxion**: load .env, default to .ai-state
- **testing-strategy**: drop vaporware go-testing.md mention
- **skills**: defuse bang-injection in skill bodies
- decouple tech-debt ledger finalize from the ADR-draft gate
- **tech-debt**: resolve td-041 — reference-clock-aware git-log window
- **tech-debt**: resolve td-035 — subagent .ai-work/ Write verified
- allow subagent Write to .ai-work via settings
- symlink Praxion pre-commit hook in install_claude.sh
- clear sentinel doc/spec/ledger findings
- capture last affected_files entry in validate_adr_references
- gate paired test model to Standard/Full tier
- repair SDD traceability quality gates
- count hook-deliver rules in context-surface measurement
- trim behavioral-contract block under token budget
- repoint eval banner off retired roadmap
- repair cross-reference validation
- resolve praxion-dashboard symlink path
- **ci**: add log sanitization and path tripwire
- **ci**: harden ci-autofix per security review
- **ci**: pin d2 and realign committed renders
- **ci**: repair Architecture workflow failures
- resolve sentinel findings I2 and S1
- **staleness**: track sections in reference files
- **web-ui-design**: repair staleness frontmatter
- **sentinel**: scope SH01 to live references
- regenerate AGENTS.md.tmpl from CLAUDE.md
- **detector**: scan extensionless bash via shebang detection (td-038)
- **tests**: fixture target_agent should be systems-architect
- **codex**: regenerate AGENTS.md.tmpl from CLAUDE.md to clear test_claude_to_agents drift
- **dashboard**: SVG sanitizer was silently stripping viewBox
- dashboard diagram rendering — markdown raw-HTML/comments, foreignObject sanitization, DiagramViewer CSS + fit-to-viewport
- praxion-dashboard start — run next start from $APP_DIR
- dashboard /adrs and /sentinel 500s — resilient ADR frontmatter parsing + sparkline client boundary
- silence sanitize-html <style> warning in dashboard SVG sanitizer
- praxion-dashboard install — survive pnpm's sharp ignored-build error
- resolve dangling ADR refs in archived SPEC
- compile codex AGENTS from project template
- normalize Codex hook context output
- Reduce Codex rule hook noise
- harden Codex adapter exports
- **coverage**: include streamlit_app in pytest testpaths
- **scripts**: route IDEA_LEDGER_*.md to idea_grid + skip HTML-comment summaries
- **install**: sentinel-wrap pre-commit hook for idempotent re-install (td-020)
- **finalize_adrs**: record branch in fragment frontmatter for unambiguous parsing (td-017)
- **finalize_adrs**: use reflog HEAD@{1} for FF-merge draft detection (td-011)
- **dashboard**: drop python3 dep + propagate PYTHONPATH
- **aac-fence-validator**: Skip code-block contents and track nested fence depth
- **skill-crafting**: Accept path-scoped skill frontmatter
- **test**: Stub merge-state dependency in TestReconcileADRNumbers
- **spec**: Rewrite dec-draft references in SPEC_diagrams to dec-NNN
- Address verifier findings — T4 contract + ADR re_affirms cleanup
- Pass workspace dir to likec4 gen; adjust T4 for lenient parse
- **docs**: Correct LikeC4 npm package name
- **ci**: Resolve test, type-check, and link-validation failures
- **metrics-ui**: Point web app at the new metrics_reports/ subdir
- **plugin**: Stop marketplace shadow-load and dev-cycle leak
- **tech-debt**: Avoid pipe collision in notes-merge separator
- **project-metrics**: Repair complexipy/pydeps + hot-spots + trends columns
- **project-metrics**: Isolate complexipy cwd to prevent stray artifact
- **finalize_adrs**: Parse multi-hyphen branches via sibling prefix

### Refactor

- **eval-praxion**: collapse /eval surface into single /eval-praxion entrypoint
- **skills**: G10 meta/individuals conformance pass
- **skills**: G9 comms/docs/security conformance pass
- **skills**: G8 ops/infra conformance pass
- **skills**: G7 language/prj-mgmt conformance pass
- **skills**: G6 quality conformance pass
- **skills**: G5 planning conformance pass
- **skills**: G4 ML/AI-training conformance pass
- **skills**: G3 AI/agent-building conformance pass
- **skills**: G2 interface/API/data conformance pass
- **skills**: G1 crafting-family conformance pass
- **skills**: dedup artifact-naming reference
- split otel_relay into layered modules
- compact skill description frontmatter
- compact agent frontmatter descriptions
- path-scope experiment-commit rule
- condense SDD format-rationale to essence
- trim always-on surface via progressive disclosure
- trim Praxion's always-on Obsidian block to a pointer
- **plugin**: consolidate likec4 MCP into plugin.json
- **skills**: trim observability description to fit listing budget
- **skills**: trim llm-training-eval description to fit listing budget
- **skills**: trim ml-training description to fit listing budget
- **skills**: trim neo-cloud-abstraction description to fit listing budget
- **skills**: trim tui-design description to fit listing budget
- **skills**: trim web-ui-design description to fit listing budget
- **skills**: trim roadmap-synthesis description to fit listing budget
- **skills**: trim api-design-craft description to fit listing budget
- **skills**: trim agentic-interface-design description to fit listing budget
- **skills**: trim experiment-tracking description to fit listing budget
- **rules**: relocate blacklist template to claude/config/
- **rules**: consolidate ts and dashboard rules
- **dashboard**: split globals.css into 6 cascade layers (td-030)
- **dashboard**: drop dead metricTone/ToneResult and activeWorkshopCount alias (td-031, td-032)
- remove legacy streamlit_app dashboard
- **rules**: P6 relocate-don't-delete pass — trim always-loaded surface
- **streamlit**: extract _render_helpers — single source for anchored body + H2 sidebar TOC
- extract send_event hook handlers (td-014)
- extract /co + /cop shared workflow to canonical block (td-006)
- token-budget pass on always-loaded rules (td-007..td-010)
- Retire ROADMAP.md; route content to TECH_DEBT_LEDGER and idea_ledgers
- **.ai-state**: Group timestamped reports into subdirs
- **tech-debt**: Drop Tech Debt section from LEARNINGS
- **dev**: Rename claude-dev → praxion-claude-dev, default to --dangerously-skip-permissions

### Perf

- bound ADR index reads (recency + grep scope)
- make verifier test-coverage load conditional
- bound implementer and planner agent returns

## v0.2.0 (2026-04-22)

### Feat

- **skills**: Add id-decontamination skill + /decontaminate-ids command
- **hooks**: Add id-citation-discipline detector + commit gate
- **sdd**: Externalize REQ/AC traceability, abolish in-code ID citations
- **onboarding**: Produce full architect+planner artifacts in seed
- **onboarding**: Add Claude.app as opt-in editor surface
- **onboarding**: Pre-launch editor + per-subagent gates + tool allowlist
- **onboarding**: Add phase gates to new-cc-project for pedagogical pacing
- **agents**: Spawn test-engineer before implementer in paired BDD/TDD
- **sentinel**: Add F10 check for git hook source-vs-installed drift
- **hooks**: Add worktree cross-boundary write guard
- **finalize**: Expand bounded walk to architecture docs and scripts/
- **concurrency**: Unified concurrency & collaboration model
- **pipeline**: Require library freshness checks across agents
- **installer**: Template global CLAUDE.md for per-user personal identifiers
- **onboarding**: Greenfield project scaffolding flow
- **chronograph**: Resolve spawn parent via PreToolUse FIFO
- **chronograph**: Fork-group clustering, agent rollups, and Phase 4 context attrs
- **chronograph**: Openinference-standard attributes (tool.id, user.id, llm.*)
- **chronograph**: Duration-correlated tool spans via PreToolUse pairing
- **eval**: Port trajectory_eval to arize-phoenix-evals 3.x API
- Add pre-impl design-synthesis capability
- **skills**: Tier-template scaffolds (FW-4)
- **rules**: Re-affirmation ADR status (FW-3)
- **rules**: Lightweight tier clauses (FW-2)
- **sentinel**: EC06 condensed-block drift (FW-1)
- **hooks**: Memory MCP unified kill switch
- **rules**: Lightweight gap closure + tier selector tree (D3+D4)
- **skills**: Add tier-templates.md parametric scaffolds (D2)
- **ecosystem**: LLM prompt engineering skill + staleness system + skill compression
- **validation**: Cross-reference validator + CI soft-launch
- **observability**: Correlate memory-MCP observations with OTel traces
- **context**: Add compaction guidance and pipeline checkpoint strategy
- **behavioral-contract**: Integrate four-behavior contract across ecosystem
- **hooks**: Per-project opt-out for memory and observability
- **agents**: Inject external-api-docs across pipeline
- **eval**: emit TODO banner on regression and capture-baseline
- **eval**: make regression diffs actually catch drift
- Phase 3 quality & automation (ROADMAP 3.1, 3.2, 3.4, 3.5, 3.6)
- Harden agent pipeline (ROADMAP Phase 2.1, 2.2, 2.4)
- Add roadmap-cartographer + lens framework
- Add SHA-pinned CI test workflow with MCP matrix
- Extract coordination procedural content to on-demand skill reference
- Add comprehensive spring cleaning ROADMAP.md
- Add path-prefix lifecycle convention to document references
- Add delegation checklists and deliverable awareness for agents
- Split architecture docs into dual-audience model (dec-021)
- Bootstrap ARCHITECTURE.md, remediate sentinel audit findings
- Add living ARCHITECTURE.md capability to agent pipeline (dec-020)
- Add batched improvement parallelism and ordered operations rules
- Auto-migrate memory.json from v1.x to v2.0 schema
- Add SYSTEM_DEPLOYMENT.md living artifact to agent pipeline
- Add Mermaid diagram conventions as rule + skill reference
- Add deployment skill with local-first Docker Compose core
- Add project-exploration skill and /explore-project command
- Add /save-changes command for persisting WIP to memory
- Add upstream stewardship skill, /report-upstream command, and issue tracker
- Add observability skill with structured logging, metrics, tracing, and alerting
- Add /review-pr command and update improvements roadmap
- Add memory metrics MCP tool
- Add lazy agent span creation for background agents
- Add hierarchical observability with git context and artifact tracking
- Add commit-time memory reminder hook
- Add memory enforcement gates to prevent empty memory.json
- Add layered duplication prevention system
- Automated .ai-state/ reconciliation for worktree merges
- Inject ADR decision context into every subagent
- Evolve memory system to v2.0 dual-layer architecture
- Implement memory system v1.3 with progressive disclosure, consolidation, and enforcement

### Fix

- **hooks**: Broaden id-citation detector; fix user-project invocation
- **onboarding**: Allow chub CLI in new-cc-project seed
- **hooks**: Honor PRAXION_DISABLE_MEMORY_MCP in commit gate
- **onboarding**: Strip frontmatter before passing command body to claude
- **reconcile**: Tighten drafts-present guard to *.md files
- **gitignore**: Recursive match for .ai-state/ lock files
- **onboarding**: Deterministic seed, pipeline-driven app, orchestrator-first mushi doc
- **tests**: sys.path prep for hook modules
- **behavioral-contract**: Deliver verifier Phase 5.5 + sentinel BC01-BC04
- Restore claude/config/CLAUDE.md (intentional user-CLAUDE mirror)
- Skip memory gate when memory system is not active
- Resolve memory metrics instrumentation gap and missing metrics tool
- Increase verifier maxTurns and add budget awareness
- Guard against string source field in memory metrics
- Resolve worktree path to main repo root for chronograph port derivation
- Increase maxTurns and add turn-budget awareness for 3 agents
- Reduce sentinel maxTurns from 150 to 100
- Prevent sentinel agent turn-budget exhaustion
- Add key-naming convention to memory protocol
- Make memory gate phase-aware and auto-write on ADD
- Add background flag to all Bg Safe agents
- Update hook-crafting docs for auto-discovery model
- Move hooks to plugin root for auto-discovery
- Quote argument-hint values in command frontmatter
- Consolidate hooks to plugin authority, make commit gate blocking
- Budget overflow in inject_memory.py obligation footer
- Inject memory context at SessionStart for main agent
- Strengthen memory gate hooks to verify remember() was called
- Remove isolation: "worktree" from agent spawning to prevent worktree proliferation
- Track observations.jsonl as persistent project intelligence
- Add hookEventName to all hook outputs for proper context injection
- Fill agent_id on all observations using session_id as fallback for main agent
- Enrich observation capture with semantic summaries and better classification
- Rename /memory command to /cajalogic and install memory hooks

### Refactor

- **tests**: Remove AC/step citations from scripts/test_*.py
- **tests**: Remove REQ/EC citations from test_cleanup_gate.py
- **tests**: Remove REQ/step citations from test_send_event.py
- **skills**: Retire github-star; inline into /star-repo
- Rename to Claude Ecosystem Learning Resources for broader scope
- Path-scope coding-style.md to code-file globs
- Derive session_count from observations; fix migration docs
- Slim coordination rules with summary-plus-pointer stubs
- Extract shared hook utils and broaden memory gate criteria
- Consolidate symlink logic and add --relink subcommand

## v0.1.0 (2026-04-03)

### Feat

- Add mandatory worktree isolation for Standard/Full pipeline tiers
- Add ADR index as discovery source for researcher, architect, and promethean
- Replace decision extraction hook with ADR reminder hook
- Add ADR index regeneration script
- Add ADR conventions rule and 8 seed decision records
- Add /test command with auto-detect framework support
- Add Python testing reference with advanced pytest patterns
- Add path-scoped testing-conventions rule for test files
- Add testing-strategy skill with language-agnostic test methodology
- Add /full-security-scan command for project-wide security audit
- Add security review Phase 4.5 to verifier agent
- Add GitHub Actions PR security review workflow
- Add context-security-review skill with diff/full-scan modes
- Add secret pattern redaction to hook event logging
- Add tool-agnostic /release command for version bumping
- Add versioning skill with tool detection and Commitizen reference
- Add GitHub Actions release workflow with Commitizen
- Add Commitizen config and align all versions to 0.0.1
- Add feedback step and align external-api-docs with upstream chub skill
- Add nested CLAUDE.md files for progressive disclosure
- Per-project chronograph ports for multi-project parallelism
- Add chronograph-ctl for dev-cycle restarts
- Add trajectory evaluation script for Phoenix traces
- Add phoenix-ctl, expand hook registration, update installer
- Expand send_event.py for all Tier 1 hook events
- Wire OTelRelay into server event handler
- Add OTel relay module for Phoenix trace export
- Add external-api-docs skill with context-hub integration
- Add hook-crafting skill for hook creation and registration
- Add code quality hooks for Python formatting and commit gating
- Add spec auto-update on decision approval
- Add /sdd-coverage command for mid-flight spec coverage checks
- Add decision tracking system with dual-path capture
- Add agent-evals skill for AI agent evaluation
- Upgrade skill-crafting with Anthropic's internal skill practices
- Add stakeholder-communications skill
- Add roadmap-planning skill
- Add performance-architecture skill
- Add api-design skill with cross-references
- Add data-modeling skill
- Add scale-adaptive process calibration with signal scoring
- Add spec delta workflow for brownfield SDD pipeline
- Add unified process calibration and cross-reference SWE artifacts
- Update pipeline agents and reference for new coordination patterns
- Add context-engineer shadowing and doc-engineer parallel execution
- Add spec-driven development skill with pipeline integration
- Add ccwt script for multi-worktree Claude sessions
- Embed BDD/TDD into the agent coordination pipeline
- Add test-engineer agent to the development crew
- Add package/module structure discipline to planner
- Add post-refactoring re-wiring verification
- Elevate doc-engineer to proactive pipeline participant
- Add native subagent features to all agents
- Generalize intra-stage parallelism for all Bg Safe agents
- Add mandatory format-and-lint step to implementer
- Add communicating-agents skill for A2A protocol
- Add agentic-sdks skill for OpenAI Agents and Claude Agent SDKs
- Add CI/CD skill and cicd-engineer agent
- Add skill-genesis agent for post-pipeline learning harvest
- Wire claude-ecosystem skill to relevant agents
- Add claude-ecosystem skill
- Add /onboard-project command
- Add /clean-work command for .ai-work/ cleanup
- Reengineer skill-crafting using official skill-creator as guide
- Migrate memory system to MCP-backed storage
- Add memory MCP server
- Add candidate selection step to promethean agent
- Update session memory with assistant identity and learnings
- Add persistent memory skill with JSON storage
- Add github-star skill and /star-repo command
- Add .ai-work/ cleanup prompt to co and cop commands
- Add artifact naming rule and rename documentation skill
- Add hybrid stdio+HTTP transport and plugin MCP registration
- Add documentation management system (skill, agent, rule update)
- Add sentinel agent with ecosystem coherence and promethean integration
- Add CLAUDE.md Structure sync to promethean agent
- Add agent observability, pipeline governance, and Task Chronograph MCP
- Add implementer agent, rename python skill, add parallel execution
- Add verifier agent and code-review skill
- Add persistent project index for efficient ideation
- Add prompt sizing, memory, and permissionMode guidance
- Register commands directory in plugin manifest
- Add naming convention guidance to command-crafting spec
- Add README section ordering guidance to skill-crafting spec
- Add promethean ideation agent
- Add .ai-work/ placement rule for agent documents
- Add /add-rules command for per-project rule distribution
- Add [CUSTOMIZE] sections to all rules
- Add [CUSTOMIZE] sections to rule-crafting
- Integrate context-engineer as full crew member
- Add software-agents-usage rule
- Split software-architect into researcher, systems-architect, and implementation-planner
- Add context-engineer agent
- Add software-architect agent with stakeholder review and execution supervision
- Add coding-style rule and slim down CLAUDE.md
- Add readme-style writing rule and /readme command
- Add rule-crafting skill for creating and managing rules
- Add mcp-server skill for MCP server development in Python
- Add cross-agent portability, content type framework, and resources to agent-skills
- Rename planning to software-planning, add contexts and phases
- Add commit commands, Desktop config, and restructure skills

### Fix

- Reset version to 0.0.1.dev0 for clean first release
- Use commitizen changelog as GitHub release body
- Reset version to 0.0.1.dev0 for first release
- Add post-release dev bump to release workflow
- Separate changelog commit to preserve version tag
- Simplify release to manual-only stable releases
- No-tag dev bumps, changelog on stable only
- Drop changelog generation from release workflow
- Use annotated tags for version releases
- Set initial dev version and fix release workflow
- Reduce terminal noise from hooks and VS Code markdownlint
- Ensure all agents discover ADRs through index, then read full files
- Make runner detection conditional — direct invocation is fine without a runner
- Enforce project runner detection in testing skill and Python reference
- Detect project runner (pixi/uv/pnpm/yarn) before invoking test framework
- Add missing testing constraints (commented-out tests, assertions, file org)
- Use OAuth token instead of API key for claude-code-action auth
- Add id-token permission for claude-code-action OIDC auth
- Add .env gitignore patterns and scope Bash in commands
- Default to dev pre-release tags in release workflow
- End agent spans immediately for real-time Phoenix visibility
- Resolve trace completeness and reliability issues
- Allow OTelRelay to create new root spans across sessions
- Use random trace IDs, deduplicate session root spans
- Default OTEL_ENABLED to false, opt-in via chronograph-ctl
- Pass session_id and project_dir to record_tool for auto-init
- Pass project_dir through to relay for subagent initialization
- End session root span immediately for Phoenix Traces visibility
- Add logging to _relay_event for observability of relay failures
- Make session span a true root for Phoenix Traces view
- Use cwd from hook payload for project directory detection
- Use openinference.project.name for Phoenix project routing, add lazy init
- Fix PID parsing in phoenix-ctl, register all Tier 1 hooks
- Change format_python hook from async to sync for feedback delivery
- Register code quality hooks in installer, remove test file
- Add quality gate to commit commands, align code quality artifacts
- Make commit-time decision review gate functional
- Align sdd-coverage command with command-crafting conventions
- Address remaining sentinel suggested findings
- Address sentinel audit findings (1 critical, 3 important)
- Correct functional bugs in researcher, plugin manifest, hooks, and verifier
- Ecosystem audit fixes and philosophy alignment
- Audit fixes for cursor-compat branch
- Remove redundant name fields from skill frontmatter
- Use installed_plugins.json for plugin detection
- Close missing quote in onboard-project plugin check
- Use correct GitHub repo name in star skill and command
- Correct repo name and add emojis in github-star skill
- Inline check code prefixes in sentinel scorecard headers
- Require root-relative paths for README.md in sentinel reports
- Resolve MCP endpoint routing and enrich hook events
- Add missing argument-hint to commit commands
- Mark name field as optional in skill-crafting spec
- Update stale agent count in software-agents-usage rule
- Update stale agent catalog in agent-crafting README
- Update stale rule catalog in rule-crafting README
- Remove stale ticker and stock-clusters entries from skills catalog
- Repair broken YAML frontmatter in readme command
- Repair broken YAML frontmatter in context-engineer agent
- Add anti-pattern for slash command refs in skills
- Modernize agent-creator skill per agent-skills spec
- Modernize slash-cmd skill per agent-skills spec
- Modernize python-prj-mgmt skill per agent-skills spec
- Modernize software-planning skill per agent-skills spec
- Modernize python skill per agent-skills spec
- Use backtick skill names in refactoring Related Skills
- Modernize refactoring skill per agent-skills spec
- Address remaining low-priority skill review items
- Modernize software-planning skill per spec and current tooling
- Add cross-references and Related Skills to refactoring skill
- Update CI action versions and clarify uv config in python-prj-mgmt
- Update python skill with fresh versions, async patterns, match/case
- Repair broken link and update model naming in slash-cmd
- Add Related Skills and expand integration example in agent-creator
- Correct skills/README.md field references and add cross-links
- Add frontmatter to slash commands and fix typos

### Refactor

- Remove old decision tracking infrastructure
- Update docs, READMEs, and project files for ADR migration
- Update skills to reference ADR files and adr-conventions rule
- Update rules to reference ADR files instead of decisions.jsonl
- Update sentinel, verifier, and skill-genesis to consume ADR files
- Update agent prompts to write ADR files instead of decisions.jsonl
- Fix language agnosticism and add context-specific progressive disclosure
- Scope .ai-work/ documents to task-slug subdirectories
- Gate PreToolUse hooks behind shell commit check
- Split decision-tracking rule to resolve token budget overshoot
- Retire custom dashboard, delegate UI to Phoenix
- Move chub CLI install to shared layer, chub MCP to ~/.claude.json
- Pass 2 voice normalization across 6 skills
- Pass 1 additive upgrade for stakeholder-communications skill
- Pass 1 additive upgrade for spec-driven-development skill
- Pass 1 additive upgrade for software-planning skill
- Pass 1 additive upgrade for roadmap-planning skill
- Pass 1 additive upgrade for refactoring skill
- Pass 1 additive upgrade for python-prj-mgmt skill
- Pass 1 additive upgrade for performance-architecture skill
- Pass 1 additive upgrade for claude-ecosystem skill
- Pass 1 additive upgrade for communicating-agents skill
- Pass 1 additive upgrade for code-review skill
- Pass 1 additive upgrade for agentic-sdks skill
- Pass 1 additive upgrade for memory skill
- Pass 1 additive upgrade for doc-management skill
- Pass 1 additive upgrade for python-development skill
- Pass 1 additive upgrade for data-modeling skill
- Pass 1 additive upgrade for mcp-crafting skill
- Pass 1 additive upgrade for agent-crafting skill
- Pass 1 additive upgrade for command-crafting skill
- Pass 1 additive upgrade for cicd skill
- Pass 1 additive upgrade for rule-crafting skill
- Extend pipeline contract for context shadowing and doc parallelism
- Optimize token budget and unify naming across ecosystem
- Unify formatting and linting across the pipeline
- Align CLAUDE.md files with development philosophy
- Rewrite CLAUDE.md philosophy and add LEARNINGS.md attribution
- split installer into router + claude/cursor config dirs
- Fix rules loading docs and restructure READMEs
- Enforce self-containment for rules and agents
- Restructure docs and add hook auto-installation
- Extract reference files for progressive disclosure in 3 skills
- Compress 3 always-loaded rules to meet token budget
- Reduce always-loaded token budget from ~14k to ~8.5k tokens
- Generalize mcp-crafting skill into language-generic core with Python context
- Make sentinel independent and timestamp report filenames
- Rename readme command and add commands README
- Rename worktree commands to kebab-case
- Standardize satellite file terminology in agent-crafting
- Standardize cross-reference format in skill READMEs
- Remove Related Skills sections from SKILL.md files
- Standardize README heading to "When to Use" across all skills
- Standardize compatibility field to "Claude Code"
- Reframe /add-rules as customization tool
- Remove auto-discovered content from CLAUDE.md
- Reorganize rules into swe/vcs subdirectory
- Move commit conventions to rules/ dir
- Rename skills to *-crafting convention
- Move shared assets to repo root for plugin distribution
- Modernize refactoring skill per agent-skills spec
- Modernize python-prj-mgmt skill per agent-skills spec
- Modernize python skill per agent-skills spec
- Rename claude-agents to agent-creator, trim per agent-skills spec
- Restructure slash-cmd skill with progressive disclosure
- Remove plan-executor agent, consolidate planning in skill
- Restructure claude-agents skill with progressive disclosure
