/**
 * Instrument-level educational copy for the Agent Readiness section.
 *
 * These describe the readiness *instrument* itself — what a level means, how the
 * 80%-per-level gate works, what the radar/heatmap show — as opposed to the
 * per-criterion and per-pillar copy, which travels inside each report (authored
 * in `scripts/project_metrics/collectors/readiness/criteria.py`). Instrument
 * concepts are universal and rarely change, so they live with the renderer and
 * are surfaced through the shared `EducationalPopover`.
 */

export type ReadinessDoc = {
  title: string;
  body: string;
};

/**
 * What each maturity level (1–5) means. Levels are additive: a project reaches
 * level N only after clearing 80% of every level 1..N. Not every pillar has a
 * criterion at every level — a level with no criteria in a pillar is shown as
 * "–" (not assessed), not a pass.
 */
export const LEVEL_MEANINGS: Record<number, ReadinessDoc> = {
  1: {
    title: "L1 — Foundational",
    body:
      "The essentials exist: a linter, a build manifest, tests on disk, a README, a .gitignore, a LICENSE, a CLAUDE.md. Without these an agent cannot operate safely at all."
  },
  2: {
    title: "L2 — Consistent",
    body:
      "Consistency and reproducibility: formatter + editorconfig, a dependency lockfile, an env-var example, a secrets policy, a README that actually explains the project."
  },
  3: {
    title: "L3 — Automated",
    body:
      "Automation and enforcement: pre-commit hooks, a CI pipeline that runs tests, a contributing guide, containerization, logging, dependency scanning, type-checking, and project git hooks."
  },
  4: {
    title: "L4 — Robust",
    body:
      "Depth and quality: behavior-focused test quality, agent-friendly documentation, health/monitoring surfaces, and a complexity or coverage gate."
  },
  5: {
    title: "L5 — Exemplary",
    body:
      "Best-in-class. No mechanical criteria gate L5 yet — it is reserved for future aspirational checks, so today it is effectively the ceiling once L4 is fully cleared."
  }
};

export const READINESS_DOCS = {
  level: {
    title: "Readiness level (1–5)",
    body:
      "The Factory-comparable maturity level over the 8 pillars: L1 Foundational, L2 Consistent, L3 Automated, L4 Robust, L5 Exemplary. A project reaches level N only when ≥80% of the applicable criteria at every level 1..N pass — levels are additive. Not every pillar has a criterion at every level; gaps are expected, and L5 currently has no criteria (it is the ceiling once L4 is cleared)."
  },
  weighting: {
    title: "Pillar weighting",
    body:
      "Not every pillar matters equally for every project — a research harness or docs repo may not need observability or containerization. A committed .ai-state/readiness_config.json sets per-pillar weights (≥0; 0 excludes a pillar). Weights tune the adjusted score; the canonical Factory score stays unweighted for cross-tool comparison."
  },
  adjustedScore: {
    title: "Adjusted vs canonical score",
    body:
      "Adjusted = the score under your pillar weights (the project headline). Canonical = the standard unweighted Factory score, kept for comparison across tools. When no weights are configured the two are identical and only the canonical score is shown."
  },
  passPct: {
    title: "Overall pass %",
    body:
      "Share of applicable, scored criteria across the 8 Factory pillars that pass. Non-applicable and LLM-pending criteria are excluded from the denominator, so a project is never penalized for a criterion that does not apply or could not be judged offline."
  },
  llmScoring: {
    title: "LLM vs mechanical scoring",
    body:
      "25 criteria are mechanical (deterministic filesystem/config checks); 4 are LLM-judged qualitative criteria (naming, test quality, README quality, agent-friendliness). The LLM tier runs only when an Anthropic credential is present — otherwise those 4 are skipped and excluded from the score (mechanical-only)."
  },
  pillarRadar: {
    title: "Pillar shape (radar)",
    body:
      "Each spoke is one of the 8 Factory pillars; the distance from center is that pillar's pass %. The radar gives an at-a-glance silhouette of where the project is strong and where it is thin."
  },
  pillarBars: {
    title: "Pillar scores (bars)",
    body:
      "Exact per-pillar pass ratios, sorted worst-first so the most actionable gaps rise to the top. The fraction is criteria-passed over criteria-counted for that pillar; non-applicable criteria are excluded."
  },
  heatmap: {
    title: "Pillar × level matrix",
    body:
      "For each pillar and each maturity level (1–5), whether that level's 80% gate is met within the pillar. ✓ clears, ✗ fails, – means no applicable criteria at that level. It shows exactly which level each pillar is held back at."
  },
  criteria: {
    title: "Criteria",
    body:
      "The individual pass/fail checks behind every pillar. Hover a pip for what it measures; failing criteria carry a recommendation on how to fix them. Mechanical criteria get deterministic guidance; the 4 LLM criteria get project-specific advice when scored with a credential."
  },
  manageability: {
    title: "Pillar 9 — Manageability",
    body:
      "A Praxion-native sub-score for agent-manageability surfaces (CLAUDE.md, AGENTS.md, git hooks, .ai-state/). It is reported separately and never folded into the 8-pillar Factory level, so the headline level stays comparable across tools."
  },
  recommendations: {
    title: "Recommendations",
    body:
      "Concrete how-to-fix guidance for each unmet criterion. Items tagged AI-tailored come from the LLM judge grounded in your actual project; the rest are deterministic, reproducible guidance authored in the rubric."
  }
} as const satisfies Record<string, ReadinessDoc>;

export type ReadinessDocKey = keyof typeof READINESS_DOCS;
