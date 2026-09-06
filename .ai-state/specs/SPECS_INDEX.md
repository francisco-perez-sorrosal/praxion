# Specs Index

Auto-generated from SPEC_*.md bold-key fields. Do not edit manually.
Regenerate: `python scripts/regenerate_specs_index.py`

| Spec | Slug | Archived | Status | Tier | ADRs | Summary |
|------|------|----------|--------|------|------|---------|
| [SPEC_sidecar-placement_2026-09-03.md](SPEC_sidecar-placement_2026-09-03.md) | sidecar-placement | 2026-09-03 | Integration pass Batch 21 executed 49 scenarios | Full | dec-364, dec-365, dec-361, dec-362, dec-359, dec-363, dec-357, dec-358, dec-368, dec-367, dec-366, dec-360, dec-366 | Praxion assumes it owns the git tree it manages. That assumption breaks for an operator running Praxion on someone else'... |
| [SPEC_multidisciplinary_identities_2026-07-30.md](SPEC_multidisciplinary_identities_2026-07-30.md) | multidisciplinary-identities | 2026-07-30 | Implemented and verified | Full | dec-303, dec-302, dec-243, dec-301, dec-076, dec-298, dec-154, dec-299, dec-300 | Praxion already owns most of the domain expertise a multidisciplinary reviewer would bring; what it lacks is a |
| [SPEC_p5-issue-autofix_2026-07-24.md](SPEC_p5-issue-autofix_2026-07-24.md) | p5-issue-autofix | 2026-07-29 (retroactively, per ground-truth reconciliation — see Note below) | Shipped | Standard | dec-281, dec-282, dec-283 | Ships `.github/workflows/issue-autofix.yml` (label-gated on `ecosystem-feedback`, non-Bot actor) and `scripts/praxion_fe... |
| [SPEC_production-gate-cohort_2026-06-26.md](SPEC_production-gate-cohort_2026-06-26.md) | production-gate-cohort | 2026-06-26 | Shipped | Full | dec-251, dec-252 | Turned the analysis's central theme — "designed obligation without a production mechanism" — into reality by adding five... |
| [SPEC_multi-language-support_2026-05-11.md](SPEC_multi-language-support_2026-05-11.md) | multi-language-support | 2026-05-11 | Shipped | Full | dec-135, dec-136, dec-137, dec-138, dec-139, dec-140 | Extended Praxion from Python-only to a polyglot ecosystem covering Node.js, TypeScript, React 19, and Vue 3 by formalizi... |
| [SPEC_diagrams_2026-04-30.md](SPEC_diagrams_2026-04-30.md) | structurizr-d2-diagrams | 2026-04-30 | Shipped | Standard | dec-093, dec-094, dec-095, dec-096 | Replaced the Mermaid-only diagram convention with a dual-toolchain policy: LikeC4 + D2 for C4-architectural diagrams (Sy... |
| [SPEC_agent-model-routing_2026-04-25.md](SPEC_agent-model-routing_2026-04-25.md) | agent-model-routing | 2026-04-25 | Shipped | Standard | dec-076, dec-077, dec-078, dec-079, dec-080 | Praxion's main orchestrator chooses the Claude model tier (`opus` / `sonnet` / `haiku`) per spawned subagent, governed b... |
| [SPEC_project-metrics_2026-04-23.md](SPEC_project-metrics_2026-04-23.md) | project-metrics | 2026-04-23 | Shipped | Full | dec-062, dec-063, dec-064, dec-065, dec-066 | Adds a user-invoked `/project-metrics` slash command that computes a curated set of project complexity / health metrics ... |
| [SPEC_design-dialectic_2026-04-17.md](SPEC_design-dialectic_2026-04-17.md) | design-dialectic | 2026-04-17 | Shipped | Full | dec-050, dec-051 | Adds an activation-gated pre-implementation design-synthesis capability across four pipeline stages — S1 (promethean ide... |
