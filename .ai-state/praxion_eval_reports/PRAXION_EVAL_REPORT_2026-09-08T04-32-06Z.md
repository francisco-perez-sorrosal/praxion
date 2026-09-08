# Praxion Eval Report — 2026-09-08T04-32-06Z

**Target**: `/Users/fperez/dev/praxion/.claude/worktrees/process-economy-phase1` (kind: path)
**Summary**: 1128 PASS / 39 WARN / 5 FAIL / 2 SKIP
**Judged**: 0 calls, 0 cache hits, 8 workers
**Tokens**: 0 in / 0 out / 0 cache-read / 0 cache-write
**Estimated cost**: $0.0000 USD

## Check Results

| Check | Kind | Verdict | Artifact | Score | Findings |
|-------|------|---------|----------|-------|----------|
| task_artifact_manifest | mechanical | FAIL | .ai-work/process-economy-phase1/SYSTEMS_PLAN.md | N/A | Expected required artifact missing: Architect's system plan with acceptance criteria. |
| task_artifact_manifest | mechanical | FAIL | .ai-work/process-economy-phase1/IMPLEMENTATION_PLAN.md | N/A | Expected required artifact missing: Planner's step decomposition. |
| task_artifact_manifest | mechanical | FAIL | .ai-work/process-economy-phase1/WIP.md | N/A | Expected required artifact missing: Live execution state. |
| task_artifact_manifest | mechanical | FAIL | .ai-work/process-economy-phase1/LEARNINGS.md | N/A | Expected required artifact missing: In-flight learning capture; produced by every pipeline agent. |
| task_artifact_manifest | mechanical | FAIL | .ai-work/process-economy-phase1/VERIFICATION_REPORT.md | N/A | Expected required artifact missing: Verifier's post-implementation review. |
| task_artifact_manifest | mechanical | WARN | .ai-work/process-economy-phase1/TEST_RESULTS.md | N/A | Expected optional artifact missing: Test-run evidence — required when a test step ran (TEST_BASELINE present). |
| task_artifact_manifest | mechanical | WARN | .ai-work/process-economy-phase1/traceability.yml | N/A | Expected optional artifact missing: REQ→test/impl mapping — required when the pipeline is SDD-tracked. |
| task_artifact_manifest | mechanical | PASS | .ai-state/DESIGN.md | N/A | Expected artifact present: Architect-facing design target; should be touched for structural changes. |
| task_artifact_manifest | mechanical | PASS | docs/architecture.md | N/A | Expected artifact present: Developer-facing navigation guide derived from DESIGN.md. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/001-skill-wrapper-over-mcp-server.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/002-otel-relay-architecture.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/003-phoenix-isolated-venv.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/004-openinference-span-kinds.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/005-dual-storage-eventstore-otel.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/006-commitizen-over-release-please.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/007-skill-centric-security-watchdog.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/008-diff-mode-default-security-review.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/009-dual-layer-memory-architecture.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/010-zero-llm-observation-capture.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/011-adr-injection-memory-first-budget.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/012-command-hook-over-prompt-hook.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/013-layered-duplication-prevention.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/014-upstream-stewardship-skill-command-composition.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/015-project-exploration-skill-command-composition.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/016-explore-project-naming.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/017-deployment-skill-local-first-compose-center.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/018-deployment-skill-opinionated-defaults.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/019-system-deployment-living-artifact.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/020-architecture-md-living-artifact.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/021-dual-audience-architecture-docs.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/022-coordination-detail-extraction.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/023-adr-first-hook-injection.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/024-ci-test-pipeline.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/025-memory-hygiene-rules.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/026-session-count-from-observations.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/027-principles-embedding-strategy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/028-diagram-conventions-path-scoping.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/029-roadmap-creation-shape-b-hybrid.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/030-roadmap-planning-skill-coexistence.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/031-roadmap-creation-pipeline-placement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/032-roadmap-md-location-and-lifecycle.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/033-six-dimension-lens-placement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/034-roadmap-budget-offset-via-prune.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/035-roadmap-parallel-audit-via-researchers.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/036-lens-framework-project-derived.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/037-opportunities-forward-lines.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/038-test-results-md-artifact.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/039-memory-gate-exemption-shared-constant.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/040-eval-framework-out-of-band.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/041-pyright-over-mypy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/042-scripts-filter-combined-predicate.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/044-coding-style-path-scoping.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/045-llm-prompt-engineering-skill.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/046-staleness-detection-system.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/047-cross-reference-validator.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/048-observation-span-correlation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/049-reaffirm-dec022-coord-cohort.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/050-always-loaded-budget-revision.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/052-telemetry-span-model-v2.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/054-separate-new-cc-project-from-install.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/056-concurrency-collab-research-fragment-adr-naming.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/057-concurrency-collab-research-unified-worktree-home.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/058-concurrency-collab-research-pr-conventions-rule.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/059-concurrency-collab-research-squash-merge-safety.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/060-concurrency-collab-research-auto-memory-orphan-cleanup.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/061-concurrency-collab-research-finalize-protocol.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/062-metrics-storage-schema.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/063-collector-protocol.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/064-graceful-degradation-policy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/065-hotspot-formula.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/066-project-metrics-planning-conventions.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/067-dispatcher-renderer-split.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/068-presentation-model.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/069-test-coverage-skill-verifier-discretion.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/070-consumer-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/071-ledger-living-artifact.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/072-tech-debt-integration-tech-debt-producer-integration.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/076-agent-model-routing-routing-dimensionality-1d-defer-2d.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/077-agent-model-routing-routing-frontmatter-floor-semantic.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/078-agent-model-routing-routing-mechanism-hybrid.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/079-agent-model-routing-routing-placement-always-loaded-rule.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/080-agent-model-routing-routing-telemetry-defer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/081-onboard-self-host-guard.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/082-extract-canonical-blocks-build-time-canonical-block-sync.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/083-separate-test-scopes-integration-vs-unit.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/084-integration-checkpoint-scope.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/085-lightweight-tier-activation-policy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/086-parallel-unsafe-and-marker-conflicts.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/087-pilot-strategy-trunk-only-then-defer-behavioral-pilot.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/088-runtime-envelope-opt-in-policy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/089-selector-manual-justification-format.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/090-topology-regeneration-cadence.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/091-test-partitioning-typed-pluggable-identifier-registry.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/092-retire-roadmap-living-document.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/093-diagram-coexistence-policy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/094-render-storage-commit-both.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/095-toolchain-likec4-d2.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/096-structurizr-d2-diagrams-step-ordering-constraint.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/097-aac-dac-cornerstone-framing.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/098-aac-fence-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/099-aac-idea8-directory-reconciliation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/100-architect-validator-charter.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/101-fitness-functions-infra.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/102-planner-decomposition-decisions.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/103-tech-debt-source-enum-widening.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/104-aac-dac-foundation-aac-dac-foundation-worktree1-decompositi.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/105-aac-dac-wireup-w2-agent-intermediate-docs-verify-only.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/106-aac-architecture-ci-pipeline.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/107-aac-diataxis-companion.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/108-aac-golden-rule-enforcement-hook.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/109-aac-likec4-querying-skill.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/110-aac-dac-v1-1-block-d-hook-slot-correction.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/111-req-arch-element-traceability.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/112-aac-dac-traceability-sentinel-ac-traceability-checks.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/113-aac-dac-onboarding-aac-onboarding-tier.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/114-tech-debt-ledger-resolved-split.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/115-ai-training-program-md-meta-prompt.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/116-ai-training-results-schema-owner.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/117-ai-training-skill-scope-decision.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/118-ai-training-tiered-backend-strategy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/119-ai-training-verifier-eval-mode.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/120-ai-training-onramp-step-ordering-for-ml-training-onramp.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/121-pipeline-dashboard-dashboard-claudemd-placement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/122-pipeline-dashboard-dashboard-cross-platform-scope.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/123-pipeline-dashboard-dashboard-dependency-isolation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/124-pipeline-dashboard-dashboard-frontmatter-parsing.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/125-pipeline-dashboard-dashboard-mermaid-strategy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/126-pipeline-dashboard-dashboard-poll-interval.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/127-pipeline-dashboard-dashboard-port-allocation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/128-pipeline-dashboard-dashboard-process-model.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/129-pipeline-dashboard-dashboard-supersede-metrics-viewer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/130-pipeline-dashboard-dashboard-visualization-stack.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/131-dashboard-sequential-data-then-parallel-pages.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/132-rename-architecture-to-design.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/133-drop-dev-prereleases.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/135-angular-exclusion-from-contexts.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/136-biome-eslint-coexistence.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/137-frontend-framework-nesting.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/138-mcp-sdk-v2-promotion-criteria.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/139-polyglot-skill-template.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/140-zod-version-split-housing.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/141-adr-graph-pure-svg.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/142-charting-recharts.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/143-design-token-layer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/144-diagram-serving-and-svg-sanitization.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/145-metrics-viewer-stub.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/146-renderer-registry-and-diataxis-shells.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/147-validate-project-root-relaxation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/148-step-decomposition-design.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/149-agent-shape-and-role-model.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/150-four-skill-decomposition.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/151-interface-designer-architect-boundary.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/152-interface-designer-opus-tier.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/153-review-interface-skill-command-pattern.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/154-specialist-sub-architects-active-advocates.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/155-context-engineer-executes-artifact-steps.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/156-architecture-page-composition.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/157-dashboard-visual-language-shift.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/158-markdown-heading-anchor-strategy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/159-metrics-page-information-architecture.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/160-overview-landing-surface.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/161-svg-server-side-normalization.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/162-token-palette-character-refinement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/163-worktree-orientation-banner.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/164-architecture-c4-dual-agent-representation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/165-praxion-dashboard-launcher-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/166-frontmatter-taxonomy-no-rename.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/167-hook-delivered-blacklist-mechanism.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/168-core-frontmatter-single-source-of-truth.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/169-git-conventions-blacklistable.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/170-auto-complete-install-per-file-refactor.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/171-no-ai-authorship-to-behavioral-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/172-schema-gt-1-fail-open.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/173-verifier-rework-loop-resume-rework-arg-shape.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/174-verifier-rework-loop-rework-manifest-format.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/175-verifier-rework-loop-verifier-findings-schema.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/176-verifier-rework-loop-cluster-rubric-smell-class-then-file.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/177-verifier-rework-loop-manifest-lifecycle-ephemeral.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/178-verifier-rework-loop-rework-routing-architect-first.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/179-verifier-rework-loop-shared-disposition-vocabulary.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/180-verifier-rework-loop-subagent-isolation-test-harness.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/181-verifier-rework-loop-td-linkage-notes-suffix.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/182-group-a-before-h-disposition-first.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/183-likec4-feedback-loop-modeling.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/184-hybrid-rework-dispatch.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/185-tests-after-shell-io-dispatch.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/186-skill-genesis-pull-driven-inversion.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/187-static-analysis-test-strategy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/188-verifier-baseline-disposition.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/189-hackathon-mode-activation-and-tier-integration.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/190-hackathon-mode-plan-decomposition.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/191-conversation-discipline.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/192-growth-trigger-thresholds.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/194-verifier-tier-appropriateness.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/195-sequential-group-ordering.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/196-cli-allowlist-policy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/197-kepano-shipping-mechanism.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/198-shape-b-default-on.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/199-obsidian-skills-marketplace-install.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/200-harden-obsidian-link-safety.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/201-gate-liveness-prove-enforcement-bites.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/202-register-python-topology-selectors.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/203-sentinel-t03-threshold-exception.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/204-praxion-self-eval-framework.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/205-harness-module-layout.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/206-praxion-hardening-nested-invocation-refusal.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/208-provider-contract-shape.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/209-robinhood-first-provider.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/210-trading-only-v1-scope.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/211-transactions-architect-role-placement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/212-sequential-markdown-build-execution.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/213-readiness-embed-vs-sibling.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/214-readiness-judge-transport.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/215-readiness-llm-contract-shift.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/216-agentic-eval-archetype-detection.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/217-eval-results-schema-verifier-reuse.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/218-ml-branch-storage-reconciliation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/219-project-profile-yaml-schema.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/220-run-store-backend-abstraction.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/221-unified-out-of-tree-storage-model.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/222-wave0-schema-first-step-ordering.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/223-wave1-dashboard-scope.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/224-nebius-neocloud-nebius-direct-adapter.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/225-remove-in-house-memory-subsystem.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/226-api-doc-reference-tiering.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/227-new-skill-api-documentation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/228-dashboard-api-spec-rendering.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/229-solid-ai-era-embedding-balanced-coupling-principle.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/230-calibrated-confidence-schema.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/231-defer-eval-lens-and-ach-matrix.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/232-di-disconfirmation-replaces-ach.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/233-extend-context-engineering-principle.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/234-multi-perspective-analysis-skill.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/235-intake-clarity-gate.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/236-decline-verified-merge-queue.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/237-sandbook-subsumes-beads-memory-direction.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/238-spec-drift-detect-not-regenerate.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/239-where-it-lives.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/240-reviewer-reuse-vs-new-agent.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/241-principles-artifact.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/242-principles-loader.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/243-reliability-skills-not-agent.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/244-dependency-scanning-scaffolding.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/245-structlog-pino-logging-default.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/246-unify-commit-gate-precommit.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/247-monorepo-healthcheck-detection.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/249-taskbrief-floor-standard-full.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/250-wal-bounding-rotation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/251-artifact-registry-declarative-spine.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/252-production-gate-cohort.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/253-retire-token-budgeting.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/254-report-retention.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/255-single-living-idea-ledger.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/256-registry-detection-gate.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/258-chain-eval-form.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/259-read-registry-cleanup-policy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/260-committed-vs-live-manifest.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/262-tier-vs-execution-mode-taxonomy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/263-retire-future-designed-producers.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/264-tier-threshold-drift-accepted.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/265-renderer-field-resolver-key.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/266-consolidate-subagent-prompt-injection.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/267-railway-deployment-lane-not-neo-cloud.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/268-eval-ledger-lazy-run-producer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/269-skill-activation-observations-event.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/270-agent-pipeline-block-pointer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/271-manifest-only-block-refresh.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/272-shipped-ci-autofix-design.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/274-new-project-mirror-scope.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/275-architect-validator-ci-budget.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/276-cross-model-gate-fails-open.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/278-defer-onboarding-install.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/280-praxion-feedback-module-split.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/281-label-application-arming-gate.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/282-praxion-only-issue-autofix-workflow.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/283-triage-first-safety-tier-classification.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/284-server-side-finalize-workflow.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/285-fork-pr-autofix-suggest-only.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/289-self-healing-metrics-baseline.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/290-decline-on-fixer-exit.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/291-jsts-runner-allowlist.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/294-label-taxonomy-manifest.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/295-label-taxonomy-manifest-html-authorship-ephemeral-exception.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/296-prompt-caching-canonical-home.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/297-python-library-catalog-placement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/298-consult-dialogue-protocol.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/299-consult-disposition-ledger.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/300-consult-selection-tiers-wave1-scope.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/301-consultant-model-effort-routing.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/302-parameterized-consultant-registry.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/303-peer-not-lens.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/304-consult-expansion-criterion-revision.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/306-lens-vs-consultant-criterion.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/307-strip-inert-plugin-agent-frontmatter.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/308-consult-cost-series.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/309-roster-ship-zero.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/310-sealed-consult-prior.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/311-defer-project-local-overlay-unit.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/312-draft-id-citation-detector.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/313-gate-placement-and-history-baseline.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/314-per-check-canary-coverage.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/315-release-staleness-named-consumer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/316-ruff-pin-coherence.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/317-retirement-is-a-status-carrying-a-remova.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/318-architectural-means-the-inventory-change.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/319-a-gate-that-exists-is-not-a-gate-that-ru.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/320-ambient-interpreter-gate-liveness.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/321-withheld-must-withhold-its-residual.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/322-metrics-freshness-in-commits.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/323-retire-sentinel-ac11-as-subsumed-by-ac13.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/324-p07-consult-clause-is-correct.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/325-architecture-validation-named-consumer.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/326-pre-merge-validator-verdict-gate.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/327-gate-identity-by-invocation-and-verdict-reach.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/328-derive-the-sentinel-t03-ceiling-from-its.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/329-specify-mcp-dependent-checks-against-bas.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/330-retire-p01-and-p02-rather-than-await-a-s.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/331-finalize-scope-idea-ledgers.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/332-task-brief-obligation-enforced-by-a-non.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/333-rename-plugin-identity-to-praxion.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/334-data-structure-pillar-shape.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/335-beauty-dimensions-shape.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/336-rust-development-skill-shape.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/337-language-dispatching-format-hook.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/338-rust-onboarding-integration.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/339-rust-contested-areas-adr-prompts.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/341-onboarding-hackathon-mode-signal-promotion.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/342-onboarding-phase-id-stability.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/343-onboarding-single-idempotency-mechanism.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/344-greenfield-permissions-baseline-seed.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/345-onboarding-gate-consolidation-profile-model.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/346-unified-onboard-cli-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/347-adr-retrieval-query-tool.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/348-reaffirm-context-hub-skill-wrapper.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/349-supersede-dashboard-claude-md-placement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/350-affected-files-creation-time-hygiene.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/351-design-checkpoint-living-view.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/352-discard-active-index.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/353-partial-supersession-edge.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/354-design-md-decomposition-scope.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/355-upgrade-path-consolidation.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/356-block-d-finalize-backstop.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/357-praxion-cli-exit-code-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/358-sidecar-reconciler-diagnostic-split.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/359-claude-md-block-target-placement.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/360-containment-guard-state-root.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/361-git-hook-chaining-model.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/362-hook-chain-session-start-heal.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/363-sidecar-autocommit-and-remote-policy.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/364-sidecar-placement-axis.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/365-state-repo-resolver-contract.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/366-sidecar-state-mount-worktree.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/367-ds1-gate-authority.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/369-finalize-citation-net.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/370-wal-lifecycle-suspension-stops-and-helper-verdict.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/371-ac12-bidirectional-traceability-unadopted.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/372-codex-model-routing-derives-from-tier.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/373-consult-cost-reconstructed-provenance.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/374-dashboard-overview-landing-unadopted.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/375-seal-witness-none-tombstone-exemption.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/376-calibration-verdict-owned-by-verifier.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/377-observations-wal-leaves-git.md | N/A | All required frontmatter fields present. |
| adr_frontmatter_completeness | mechanical | PASS | .ai-state/decisions/378-simplification-evidence-standard.md | N/A | All required frontmatter fields present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/001-skill-wrapper-over-mcp-server.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/002-otel-relay-architecture.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/003-phoenix-isolated-venv.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/004-openinference-span-kinds.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/005-dual-storage-eventstore-otel.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/006-commitizen-over-release-please.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/007-skill-centric-security-watchdog.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/008-diff-mode-default-security-review.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/009-dual-layer-memory-architecture.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/010-zero-llm-observation-capture.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/011-adr-injection-memory-first-budget.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/012-command-hook-over-prompt-hook.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/013-layered-duplication-prevention.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/014-upstream-stewardship-skill-command-composition.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/015-project-exploration-skill-command-composition.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/016-explore-project-naming.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/017-deployment-skill-local-first-compose-center.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/018-deployment-skill-opinionated-defaults.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/019-system-deployment-living-artifact.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/020-architecture-md-living-artifact.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/021-dual-audience-architecture-docs.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/022-coordination-detail-extraction.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/023-adr-first-hook-injection.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/024-ci-test-pipeline.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/025-memory-hygiene-rules.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/026-session-count-from-observations.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/027-principles-embedding-strategy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/028-diagram-conventions-path-scoping.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/029-roadmap-creation-shape-b-hybrid.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/030-roadmap-planning-skill-coexistence.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/031-roadmap-creation-pipeline-placement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/032-roadmap-md-location-and-lifecycle.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/033-six-dimension-lens-placement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/034-roadmap-budget-offset-via-prune.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/035-roadmap-parallel-audit-via-researchers.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/036-lens-framework-project-derived.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/037-opportunities-forward-lines.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/038-test-results-md-artifact.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/039-memory-gate-exemption-shared-constant.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/040-eval-framework-out-of-band.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/041-pyright-over-mypy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/042-scripts-filter-combined-predicate.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/044-coding-style-path-scoping.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/045-llm-prompt-engineering-skill.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/046-staleness-detection-system.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/047-cross-reference-validator.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/048-observation-span-correlation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/049-reaffirm-dec022-coord-cohort.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/050-always-loaded-budget-revision.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/052-telemetry-span-model-v2.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/054-separate-new-cc-project-from-install.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/056-concurrency-collab-research-fragment-adr-naming.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/057-concurrency-collab-research-unified-worktree-home.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/058-concurrency-collab-research-pr-conventions-rule.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/059-concurrency-collab-research-squash-merge-safety.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/060-concurrency-collab-research-auto-memory-orphan-cleanup.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/061-concurrency-collab-research-finalize-protocol.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/062-metrics-storage-schema.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/063-collector-protocol.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/064-graceful-degradation-policy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/065-hotspot-formula.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/066-project-metrics-planning-conventions.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/067-dispatcher-renderer-split.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/068-presentation-model.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/069-test-coverage-skill-verifier-discretion.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/070-consumer-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/071-ledger-living-artifact.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/072-tech-debt-integration-tech-debt-producer-integration.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/076-agent-model-routing-routing-dimensionality-1d-defer-2d.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/077-agent-model-routing-routing-frontmatter-floor-semantic.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/078-agent-model-routing-routing-mechanism-hybrid.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/079-agent-model-routing-routing-placement-always-loaded-rule.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/080-agent-model-routing-routing-telemetry-defer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/081-onboard-self-host-guard.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/082-extract-canonical-blocks-build-time-canonical-block-sync.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/083-separate-test-scopes-integration-vs-unit.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/084-integration-checkpoint-scope.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/085-lightweight-tier-activation-policy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/086-parallel-unsafe-and-marker-conflicts.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/087-pilot-strategy-trunk-only-then-defer-behavioral-pilot.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/088-runtime-envelope-opt-in-policy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/089-selector-manual-justification-format.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/090-topology-regeneration-cadence.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/091-test-partitioning-typed-pluggable-identifier-registry.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/092-retire-roadmap-living-document.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/093-diagram-coexistence-policy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/094-render-storage-commit-both.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/095-toolchain-likec4-d2.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/096-structurizr-d2-diagrams-step-ordering-constraint.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/097-aac-dac-cornerstone-framing.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/098-aac-fence-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/099-aac-idea8-directory-reconciliation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/100-architect-validator-charter.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/101-fitness-functions-infra.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/102-planner-decomposition-decisions.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/103-tech-debt-source-enum-widening.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/104-aac-dac-foundation-aac-dac-foundation-worktree1-decompositi.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/105-aac-dac-wireup-w2-agent-intermediate-docs-verify-only.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/106-aac-architecture-ci-pipeline.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/107-aac-diataxis-companion.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/108-aac-golden-rule-enforcement-hook.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/109-aac-likec4-querying-skill.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/110-aac-dac-v1-1-block-d-hook-slot-correction.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/111-req-arch-element-traceability.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/112-aac-dac-traceability-sentinel-ac-traceability-checks.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/113-aac-dac-onboarding-aac-onboarding-tier.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/114-tech-debt-ledger-resolved-split.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/115-ai-training-program-md-meta-prompt.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/116-ai-training-results-schema-owner.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/117-ai-training-skill-scope-decision.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/118-ai-training-tiered-backend-strategy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/119-ai-training-verifier-eval-mode.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/120-ai-training-onramp-step-ordering-for-ml-training-onramp.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/121-pipeline-dashboard-dashboard-claudemd-placement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/122-pipeline-dashboard-dashboard-cross-platform-scope.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/123-pipeline-dashboard-dashboard-dependency-isolation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/124-pipeline-dashboard-dashboard-frontmatter-parsing.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/125-pipeline-dashboard-dashboard-mermaid-strategy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/126-pipeline-dashboard-dashboard-poll-interval.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/127-pipeline-dashboard-dashboard-port-allocation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/128-pipeline-dashboard-dashboard-process-model.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/129-pipeline-dashboard-dashboard-supersede-metrics-viewer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/130-pipeline-dashboard-dashboard-visualization-stack.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/131-dashboard-sequential-data-then-parallel-pages.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/132-rename-architecture-to-design.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/133-drop-dev-prereleases.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/135-angular-exclusion-from-contexts.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/136-biome-eslint-coexistence.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/137-frontend-framework-nesting.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/138-mcp-sdk-v2-promotion-criteria.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/139-polyglot-skill-template.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/140-zod-version-split-housing.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/141-adr-graph-pure-svg.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/142-charting-recharts.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/143-design-token-layer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/144-diagram-serving-and-svg-sanitization.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/145-metrics-viewer-stub.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/146-renderer-registry-and-diataxis-shells.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/147-validate-project-root-relaxation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/148-step-decomposition-design.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/149-agent-shape-and-role-model.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/150-four-skill-decomposition.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/151-interface-designer-architect-boundary.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/152-interface-designer-opus-tier.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/153-review-interface-skill-command-pattern.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/154-specialist-sub-architects-active-advocates.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/155-context-engineer-executes-artifact-steps.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/156-architecture-page-composition.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/157-dashboard-visual-language-shift.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/158-markdown-heading-anchor-strategy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/159-metrics-page-information-architecture.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/160-overview-landing-surface.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/161-svg-server-side-normalization.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/162-token-palette-character-refinement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/163-worktree-orientation-banner.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/164-architecture-c4-dual-agent-representation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/165-praxion-dashboard-launcher-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/166-frontmatter-taxonomy-no-rename.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/167-hook-delivered-blacklist-mechanism.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/168-core-frontmatter-single-source-of-truth.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/169-git-conventions-blacklistable.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/170-auto-complete-install-per-file-refactor.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/171-no-ai-authorship-to-behavioral-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/172-schema-gt-1-fail-open.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/173-verifier-rework-loop-resume-rework-arg-shape.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/174-verifier-rework-loop-rework-manifest-format.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/175-verifier-rework-loop-verifier-findings-schema.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/176-verifier-rework-loop-cluster-rubric-smell-class-then-file.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/177-verifier-rework-loop-manifest-lifecycle-ephemeral.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/178-verifier-rework-loop-rework-routing-architect-first.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/179-verifier-rework-loop-shared-disposition-vocabulary.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/180-verifier-rework-loop-subagent-isolation-test-harness.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/181-verifier-rework-loop-td-linkage-notes-suffix.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/182-group-a-before-h-disposition-first.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/183-likec4-feedback-loop-modeling.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/184-hybrid-rework-dispatch.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/185-tests-after-shell-io-dispatch.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/186-skill-genesis-pull-driven-inversion.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/187-static-analysis-test-strategy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/188-verifier-baseline-disposition.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/189-hackathon-mode-activation-and-tier-integration.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/190-hackathon-mode-plan-decomposition.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/191-conversation-discipline.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/192-growth-trigger-thresholds.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/194-verifier-tier-appropriateness.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/195-sequential-group-ordering.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/196-cli-allowlist-policy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/197-kepano-shipping-mechanism.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/198-shape-b-default-on.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/199-obsidian-skills-marketplace-install.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/200-harden-obsidian-link-safety.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/201-gate-liveness-prove-enforcement-bites.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/202-register-python-topology-selectors.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/203-sentinel-t03-threshold-exception.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/204-praxion-self-eval-framework.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/205-harness-module-layout.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/206-praxion-hardening-nested-invocation-refusal.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/208-provider-contract-shape.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/209-robinhood-first-provider.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/210-trading-only-v1-scope.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/211-transactions-architect-role-placement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/212-sequential-markdown-build-execution.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/213-readiness-embed-vs-sibling.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/214-readiness-judge-transport.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/215-readiness-llm-contract-shift.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/216-agentic-eval-archetype-detection.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/217-eval-results-schema-verifier-reuse.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/218-ml-branch-storage-reconciliation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/219-project-profile-yaml-schema.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/220-run-store-backend-abstraction.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/221-unified-out-of-tree-storage-model.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/222-wave0-schema-first-step-ordering.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/223-wave1-dashboard-scope.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/224-nebius-neocloud-nebius-direct-adapter.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/225-remove-in-house-memory-subsystem.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/226-api-doc-reference-tiering.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/227-new-skill-api-documentation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/228-dashboard-api-spec-rendering.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/229-solid-ai-era-embedding-balanced-coupling-principle.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/230-calibrated-confidence-schema.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/231-defer-eval-lens-and-ach-matrix.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/232-di-disconfirmation-replaces-ach.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/233-extend-context-engineering-principle.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/234-multi-perspective-analysis-skill.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/235-intake-clarity-gate.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/236-decline-verified-merge-queue.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/237-sandbook-subsumes-beads-memory-direction.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/238-spec-drift-detect-not-regenerate.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/239-where-it-lives.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/240-reviewer-reuse-vs-new-agent.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/241-principles-artifact.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/242-principles-loader.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/243-reliability-skills-not-agent.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/244-dependency-scanning-scaffolding.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/245-structlog-pino-logging-default.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/246-unify-commit-gate-precommit.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/247-monorepo-healthcheck-detection.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/249-taskbrief-floor-standard-full.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/250-wal-bounding-rotation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/251-artifact-registry-declarative-spine.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/252-production-gate-cohort.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/253-retire-token-budgeting.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/254-report-retention.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/255-single-living-idea-ledger.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/256-registry-detection-gate.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/258-chain-eval-form.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/259-read-registry-cleanup-policy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/260-committed-vs-live-manifest.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/262-tier-vs-execution-mode-taxonomy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/263-retire-future-designed-producers.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/264-tier-threshold-drift-accepted.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/265-renderer-field-resolver-key.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/266-consolidate-subagent-prompt-injection.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/267-railway-deployment-lane-not-neo-cloud.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/268-eval-ledger-lazy-run-producer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/269-skill-activation-observations-event.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/270-agent-pipeline-block-pointer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/271-manifest-only-block-refresh.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/272-shipped-ci-autofix-design.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/274-new-project-mirror-scope.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/275-architect-validator-ci-budget.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/276-cross-model-gate-fails-open.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/278-defer-onboarding-install.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/280-praxion-feedback-module-split.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/281-label-application-arming-gate.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/282-praxion-only-issue-autofix-workflow.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/283-triage-first-safety-tier-classification.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/284-server-side-finalize-workflow.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/285-fork-pr-autofix-suggest-only.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/289-self-healing-metrics-baseline.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/290-decline-on-fixer-exit.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/291-jsts-runner-allowlist.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/294-label-taxonomy-manifest.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/295-label-taxonomy-manifest-html-authorship-ephemeral-exception.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/296-prompt-caching-canonical-home.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/297-python-library-catalog-placement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/298-consult-dialogue-protocol.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/299-consult-disposition-ledger.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/300-consult-selection-tiers-wave1-scope.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/301-consultant-model-effort-routing.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/302-parameterized-consultant-registry.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/303-peer-not-lens.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/304-consult-expansion-criterion-revision.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/306-lens-vs-consultant-criterion.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/307-strip-inert-plugin-agent-frontmatter.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/308-consult-cost-series.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/309-roster-ship-zero.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/310-sealed-consult-prior.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/311-defer-project-local-overlay-unit.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/312-draft-id-citation-detector.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/313-gate-placement-and-history-baseline.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/314-per-check-canary-coverage.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/315-release-staleness-named-consumer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/316-ruff-pin-coherence.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/317-retirement-is-a-status-carrying-a-remova.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/318-architectural-means-the-inventory-change.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/319-a-gate-that-exists-is-not-a-gate-that-ru.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/320-ambient-interpreter-gate-liveness.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/321-withheld-must-withhold-its-residual.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/322-metrics-freshness-in-commits.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/323-retire-sentinel-ac11-as-subsumed-by-ac13.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/324-p07-consult-clause-is-correct.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/325-architecture-validation-named-consumer.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/326-pre-merge-validator-verdict-gate.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/327-gate-identity-by-invocation-and-verdict-reach.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/328-derive-the-sentinel-t03-ceiling-from-its.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/329-specify-mcp-dependent-checks-against-bas.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/330-retire-p01-and-p02-rather-than-await-a-s.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/331-finalize-scope-idea-ledgers.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/332-task-brief-obligation-enforced-by-a-non.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/333-rename-plugin-identity-to-praxion.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/334-data-structure-pillar-shape.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/335-beauty-dimensions-shape.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/336-rust-development-skill-shape.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/337-language-dispatching-format-hook.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/338-rust-onboarding-integration.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/339-rust-contested-areas-adr-prompts.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/341-onboarding-hackathon-mode-signal-promotion.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/342-onboarding-phase-id-stability.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/343-onboarding-single-idempotency-mechanism.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/344-greenfield-permissions-baseline-seed.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/345-onboarding-gate-consolidation-profile-model.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/346-unified-onboard-cli-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/347-adr-retrieval-query-tool.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/348-reaffirm-context-hub-skill-wrapper.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/349-supersede-dashboard-claude-md-placement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/350-affected-files-creation-time-hygiene.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/351-design-checkpoint-living-view.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/352-discard-active-index.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/353-partial-supersession-edge.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/354-design-md-decomposition-scope.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/355-upgrade-path-consolidation.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/356-block-d-finalize-backstop.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/357-praxion-cli-exit-code-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/358-sidecar-reconciler-diagnostic-split.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/359-claude-md-block-target-placement.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/360-containment-guard-state-root.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/361-git-hook-chaining-model.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/362-hook-chain-session-start-heal.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/363-sidecar-autocommit-and-remote-policy.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/364-sidecar-placement-axis.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/365-state-repo-resolver-contract.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/366-sidecar-state-mount-worktree.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/367-ds1-gate-authority.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/369-finalize-citation-net.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/370-wal-lifecycle-suspension-stops-and-helper-verdict.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/371-ac12-bidirectional-traceability-unadopted.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/372-codex-model-routing-derives-from-tier.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/373-consult-cost-reconstructed-provenance.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/374-dashboard-overview-landing-unadopted.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/375-seal-witness-none-tombstone-exemption.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/376-calibration-verdict-owned-by-verifier.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/377-observations-wal-leaves-git.md | N/A | All required body sections present. |
| adr_body_sections | mechanical | PASS | .ai-state/decisions/378-simplification-evidence-standard.md | N/A | All required body sections present. |
| supersession_reciprocity | mechanical | PASS | (corpus-wide) | N/A | All supersedes/superseded_by links are symmetric. |
| re_affirmation_reciprocity | mechanical | PASS | (corpus-wide) | N/A | All re_affirms/re_affirmed_by links are symmetric. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_agent-model-routing_2026-04-25.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_design-dialectic_2026-04-17.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_diagrams_2026-04-30.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_multi-language-support_2026-05-11.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_multidisciplinary_identities_2026-07-30.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_p5-issue-autofix_2026-07-24.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_production-gate-cohort_2026-06-26.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_project-metrics_2026-04-23.md | N/A | Traceability Matrix section present. |
| spec_traceability_presence | mechanical | PASS | .ai-state/specs/SPEC_sidecar-placement_2026-09-03.md | N/A | Traceability Matrix section present. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/002-otel-relay-architecture.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/002-otel-relay-architecture.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/003-phoenix-isolated-venv.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/004-openinference-span-kinds.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/004-openinference-span-kinds.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/005-dual-storage-eventstore-otel.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/005-dual-storage-eventstore-otel.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/040-eval-framework-out-of-band.md | N/A | REQ ID 'REQ-EV-01' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/040-eval-framework-out-of-band.md | N/A | REQ ID 'REQ-EV-02' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/040-eval-framework-out-of-band.md | N/A | REQ ID 'REQ-EV-04' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/040-eval-framework-out-of-band.md | N/A | REQ ID 'REQ-EV-05' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/041-pyright-over-mypy.md | N/A | REQ ID 'REQ-TC-01' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/041-pyright-over-mypy.md | N/A | REQ ID 'REQ-TC-02' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/041-pyright-over-mypy.md | N/A | REQ ID 'REQ-TC-03' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/042-scripts-filter-combined-predicate.md | N/A | REQ ID 'REQ-SL-01' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/042-scripts-filter-combined-predicate.md | N/A | REQ ID 'REQ-SL-02' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/042-scripts-filter-combined-predicate.md | N/A | REQ ID 'REQ-SL-04' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/042-scripts-filter-combined-predicate.md | N/A | REQ ID 'REQ-SL-05' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | REQ ID 'REQ-BC-1' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | REQ ID 'REQ-BC-2' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | REQ ID 'REQ-BC-3' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | REQ ID 'REQ-BC-4' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | REQ ID 'REQ-BC-5' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | REQ ID 'REQ-BC-6' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/043-behavioral-contract-layer.md | N/A | REQ ID 'REQ-BC-7' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/044-coding-style-path-scoping.md | N/A | REQ ID 'REQ-BC-6' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/051-pre-impl-design-synthesis.md | N/A | REQ ID 'REQ-DDL-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | REQ ID 'REQ-ONBOARD-15' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | REQ ID 'REQ-ONBOARD-16' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | REQ ID 'REQ-ONBOARD-17' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | REQ ID 'REQ-ONBOARD-18' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | REQ ID 'REQ-ONBOARD-20' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/053-prompt-over-template-greenfield-scaffold.md | N/A | REQ ID 'REQ-ONBOARD-26' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-01' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-02' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-03' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-04' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-05' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-06' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-07' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-08' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-09' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-10' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | WARN | .ai-state/decisions/055-hybrid-bash-slash-command-orchestration.md | N/A | REQ ID 'REQ-ONBOARD-11' not found in any archived SPEC. This is expected for the ~80% of ADRs that predate the spec archival practice or belong to direct-tier work. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/073-unified-phase-plan.md | N/A | REQ ID 'REQ-16' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/074-praxion-first-class-install-completeness-auto-first-session.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/075-praxion-first-class-praxion-first-class-process.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/076-agent-model-routing-routing-dimensionality-1d-defer-2d.md | N/A | REQ ID 'AC2' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/076-agent-model-routing-routing-dimensionality-1d-defer-2d.md | N/A | REQ ID 'AC10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/077-agent-model-routing-routing-frontmatter-floor-semantic.md | N/A | REQ ID 'AC3' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/078-agent-model-routing-routing-mechanism-hybrid.md | N/A | REQ ID 'AC1' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/078-agent-model-routing-routing-mechanism-hybrid.md | N/A | REQ ID 'AC3' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/078-agent-model-routing-routing-mechanism-hybrid.md | N/A | REQ ID 'AC4' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/079-agent-model-routing-routing-placement-always-loaded-rule.md | N/A | REQ ID 'AC1' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/080-agent-model-routing-routing-telemetry-defer.md | N/A | REQ ID 'AC1' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/121-pipeline-dashboard-dashboard-claudemd-placement.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/122-pipeline-dashboard-dashboard-cross-platform-scope.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/122-pipeline-dashboard-dashboard-cross-platform-scope.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/123-pipeline-dashboard-dashboard-dependency-isolation.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/124-pipeline-dashboard-dashboard-frontmatter-parsing.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/124-pipeline-dashboard-dashboard-frontmatter-parsing.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/125-pipeline-dashboard-dashboard-mermaid-strategy.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/126-pipeline-dashboard-dashboard-poll-interval.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/127-pipeline-dashboard-dashboard-port-allocation.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/128-pipeline-dashboard-dashboard-process-model.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/128-pipeline-dashboard-dashboard-process-model.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/129-pipeline-dashboard-dashboard-supersede-metrics-viewer.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/130-pipeline-dashboard-dashboard-visualization-stack.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/130-pipeline-dashboard-dashboard-visualization-stack.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/130-pipeline-dashboard-dashboard-visualization-stack.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/134-dashboard-nextjs-runtime.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/166-frontmatter-taxonomy-no-rename.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/166-frontmatter-taxonomy-no-rename.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/166-frontmatter-taxonomy-no-rename.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/167-hook-delivered-blacklist-mechanism.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/167-hook-delivered-blacklist-mechanism.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/167-hook-delivered-blacklist-mechanism.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/167-hook-delivered-blacklist-mechanism.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/168-core-frontmatter-single-source-of-truth.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/168-core-frontmatter-single-source-of-truth.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/169-git-conventions-blacklistable.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/169-git-conventions-blacklistable.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/170-auto-complete-install-per-file-refactor.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/170-auto-complete-install-per-file-refactor.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/171-no-ai-authorship-to-behavioral-contract.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/171-no-ai-authorship-to-behavioral-contract.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/172-schema-gt-1-fail-open.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/172-schema-gt-1-fail-open.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/192-growth-trigger-thresholds.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/192-growth-trigger-thresholds.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/192-growth-trigger-thresholds.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/192-growth-trigger-thresholds.md | N/A | REQ ID 'REQ-18' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-16' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/193-test-topology-m2-activation.md | N/A | REQ ID 'REQ-17' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/194-verifier-tier-appropriateness.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/194-verifier-tier-appropriateness.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-16' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-17' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/207-pre-refactor-sub-pipeline.md | N/A | REQ ID 'REQ-18' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/208-provider-contract-shape.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/208-provider-contract-shape.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/208-provider-contract-shape.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/209-robinhood-first-provider.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/209-robinhood-first-provider.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/210-trading-only-v1-scope.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/210-trading-only-v1-scope.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/211-transactions-architect-role-placement.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/211-transactions-architect-role-placement.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/211-transactions-architect-role-placement.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/230-calibrated-confidence-schema.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/231-defer-eval-lens-and-ach-matrix.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/232-di-disconfirmation-replaces-ach.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/232-di-disconfirmation-replaces-ach.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/232-di-disconfirmation-replaces-ach.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/233-extend-context-engineering-principle.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/233-extend-context-engineering-principle.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/234-multi-perspective-analysis-skill.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/234-multi-perspective-analysis-skill.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/234-multi-perspective-analysis-skill.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/234-multi-perspective-analysis-skill.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/248-observations-wal-recovery-reconciliation.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/257-readiness-feedback-gate.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/261-direct-capture-contract.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/262-tier-vs-execution-mode-taxonomy.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/262-tier-vs-execution-mode-taxonomy.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/268-eval-ledger-lazy-run-producer.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/268-eval-ledger-lazy-run-producer.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/268-eval-ledger-lazy-run-producer.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/268-eval-ledger-lazy-run-producer.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/268-eval-ledger-lazy-run-producer.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/269-skill-activation-observations-event.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/269-skill-activation-observations-event.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/269-skill-activation-observations-event.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/269-skill-activation-observations-event.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/269-skill-activation-observations-event.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/273-hub-reusable-workflow-distribution.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/274-new-project-mirror-scope.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/274-new-project-mirror-scope.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/276-cross-model-gate-fails-open.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/276-cross-model-gate-fails-open.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/276-cross-model-gate-fails-open.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/277-cursor-reviews-claude-fixes.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/278-defer-onboarding-install.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/279-hitl-gated-healing-sidecar.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/280-praxion-feedback-module-split.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/280-praxion-feedback-module-split.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/280-praxion-feedback-module-split.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/280-praxion-feedback-module-split.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/280-praxion-feedback-module-split.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/281-label-application-arming-gate.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/281-label-application-arming-gate.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/281-label-application-arming-gate.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/282-praxion-only-issue-autofix-workflow.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/282-praxion-only-issue-autofix-workflow.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/282-praxion-only-issue-autofix-workflow.md | N/A | REQ ID 'REQ-16' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/283-triage-first-safety-tier-classification.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/283-triage-first-safety-tier-classification.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/283-triage-first-safety-tier-classification.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/283-triage-first-safety-tier-classification.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/285-fork-pr-autofix-suggest-only.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/285-fork-pr-autofix-suggest-only.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/285-fork-pr-autofix-suggest-only.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/286-pr-autofix-seam-and-privilege.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/287-cross-model-fleet-install.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/288-upgrade-caller-sha-rewrite.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/292-pm-aware-jsts-install.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/293-intake-gate-and-project-prism.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/298-consult-dialogue-protocol.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/298-consult-dialogue-protocol.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/298-consult-dialogue-protocol.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/298-consult-dialogue-protocol.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/298-consult-dialogue-protocol.md | N/A | REQ ID 'REQ-12' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/299-consult-disposition-ledger.md | N/A | REQ ID 'REQ-13' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/299-consult-disposition-ledger.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/299-consult-disposition-ledger.md | N/A | REQ ID 'REQ-17' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/300-consult-selection-tiers-wave1-scope.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/300-consult-selection-tiers-wave1-scope.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/300-consult-selection-tiers-wave1-scope.md | N/A | REQ ID 'REQ-18' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/301-consultant-model-effort-routing.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/301-consultant-model-effort-routing.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/302-parameterized-consultant-registry.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/302-parameterized-consultant-registry.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/302-parameterized-consultant-registry.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/302-parameterized-consultant-registry.md | N/A | REQ ID 'REQ-16' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/303-peer-not-lens.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/303-peer-not-lens.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/303-peer-not-lens.md | N/A | REQ ID 'REQ-18' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/305-project-local-discipline-registry-overlay.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/336-rust-development-skill-shape.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/336-rust-development-skill-shape.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/336-rust-development-skill-shape.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/337-language-dispatching-format-hook.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/337-language-dispatching-format-hook.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/338-rust-onboarding-integration.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/339-rust-contested-areas-adr-prompts.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/339-rust-contested-areas-adr-prompts.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/339-rust-contested-areas-adr-prompts.md | N/A | REQ ID 'REQ-11' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/340-onboarding-commands-to-skill.md | N/A | REQ ID 'REQ-10' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/341-onboarding-hackathon-mode-signal-promotion.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/341-onboarding-hackathon-mode-signal-promotion.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/342-onboarding-phase-id-stability.md | N/A | REQ ID 'REQ-09' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/343-onboarding-single-idempotency-mechanism.md | N/A | REQ ID 'REQ-07' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/343-onboarding-single-idempotency-mechanism.md | N/A | REQ ID 'REQ-08' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/367-ds1-gate-authority.md | N/A | REQ ID 'REQ-14' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-15' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-16' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-17' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-18' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-19' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-22' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-24' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-25' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-30' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-31' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-35' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-36' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/368-sidecar-module-split.md | N/A | REQ ID 'REQ-37' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/372-codex-model-routing-derives-from-tier.md | N/A | REQ ID 'REQ-01' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/372-codex-model-routing-derives-from-tier.md | N/A | REQ ID 'REQ-02' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/373-consult-cost-reconstructed-provenance.md | N/A | REQ ID 'REQ-06' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/375-seal-witness-none-tombstone-exemption.md | N/A | REQ ID 'REQ-03' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/375-seal-witness-none-tombstone-exemption.md | N/A | REQ ID 'REQ-04' found in at least one archived SPEC. |
| affected_reqs_resolvability | mechanical | PASS | .ai-state/decisions/375-seal-witness-none-tombstone-exemption.md | N/A | REQ ID 'REQ-05' found in at least one archived SPEC. |
| decisions_index_consistency | mechanical | PASS | .ai-state/decisions/DECISIONS_INDEX.md | N/A | DECISIONS_INDEX row count (378) matches ADR file count (378). |
| bc_corpus_presence | mechanical | SKIP | (no verification reports in corpus) | N/A | No VERIFICATION_REPORT.md files found in corpus. Family 2 requires at least one verification report. |
| scenario_spawn_selection_mechanical | mechanical | PASS | scenarios/spawn-selection.yaml | N/A | spawn-selection: recorded fixture conforms. |
| scenario_ui_step_conformance_mechanical | mechanical | PASS | scenarios/ui-step-conformance.yaml | N/A | ui-step-conformance: recorded fixture conforms. |
| scenario_adr_authoring_mechanical | mechanical | PASS | scenarios/adr-authoring.yaml | N/A | adr-authoring: recorded fixture conforms. |
| scenario_commit_staging_mechanical | mechanical | PASS | scenarios/commit-staging.yaml | N/A | commit-staging: recorded fixture conforms. |
| scenario_lightweight_fix_mechanical | mechanical | PASS | scenarios/lightweight-fix.yaml | N/A | lightweight-fix: recorded fixture conforms. |
| scenario_inheritance_probe_skip | skip | SKIP | scripts/inheritance_probe.py | N/A | judged-tier-only; not auto-run by the harness in either mode -- invoke `eval/scripts/inheritance_probe.py` directly (spawns a real `claude -p` session, once per M-confidence slice). |
| token_budget_stability | mechanical | WARN | .ai-state/token_budget_baseline.json | N/A | governed: 25,971/25,000 tokens (103.9%, basis=estimate (bytes / 3.6), 93,497 bytes over 9 files); listing: 13,664 tokens (basis=estimate (bytes / 3.6), ceiling=11336, 49,191 bytes over 126 files); no byte-tracked prior sample in the baseline — trailing-30-day delta unavailable; listing ceiling was frozen on basis 'tokenizer' but today's listing reading is basis 'estimate' — skipping the listing-ceiling check; governed tokens 25,971 exceed the 25,000 ceiling by 971 on the estimate basis — inconclusive until a tokenizer run (ANTHROPIC_API_KEY) measures it; utilisation 103.9% at or above the 90% warn threshold |

## Calibration Notes

**Family 1 — affected_reqs population gap (20%):** Many ADRs legitimately omit
`affected_reqs` (Praxion population rate ~20%). Unresolvable entries emit WARN,
not FAIL, to avoid drowning the signal in expected gaps. A high WARN count on
`affected_reqs_resolvability` is expected and should not be treated as breakage.

**Family 2 — PASS-only corpus (v1):** The behavioral-contract adherence family
is calibrated on VERIFICATION_REPORT.md files from a corpus where all known
reports show PASS findings. False-negative detection (cases where the LLM
judge misses a real violation) is not tested at v1. Interpret PASS verdicts
from Family 2 with appropriate caution; adversarial fixtures are deferred to v2.
