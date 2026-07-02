import type { ComponentType } from "react";

import type { ManifestSurface } from "@/server/types";

import {
  ArchitectureExplorerRenderer,
  IdeaGridRenderer,
  MetricsViewRenderer,
  PlanViewRenderer,
  VerificationReportRenderer
} from "./renderers";
import {
  ApiReferenceShell,
  ConceptsShell,
  DefaultShell,
  ExplanationShell,
  HowToShell,
  ReferenceShell,
  TutorialShell
} from "./shells";

// ─── Types ───────────────────────────────────────────────────────────────────

export type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

export type RendererComponent = ComponentType<RendererProps>;

// ─── Registry ────────────────────────────────────────────────────────────────

/**
 * Maps manifest renderer names, Diátaxis values, and content-type strings to
 * their components. Lookup order in resolveRenderer:
 * renderer → diataxis → contentType → DefaultShell.
 */
export const RENDERER_REGISTRY: Map<string, RendererComponent> = new Map([
  ["tutorial", TutorialShell],
  ["how-to", HowToShell],
  ["reference", ReferenceShell],
  ["explanation", ExplanationShell],
  ["concepts", ConceptsShell],
  ["markdown", DefaultShell],
  ["api_reference", ApiReferenceShell],
  ["metrics_view", MetricsViewRenderer],
  ["plan_view", PlanViewRenderer],
  ["verification_report", VerificationReportRenderer],
  ["idea_grid", IdeaGridRenderer],
  ["architecture_explorer", ArchitectureExplorerRenderer]
]);

// ─── Resolver ────────────────────────────────────────────────────────────────

/**
 * Resolve the appropriate component for a given surface.
 * Priority: renderer match → diataxis match → contentType match → DefaultShell.
 *
 * The leading `renderer` argument is the manifest `renderer:` field — the only
 * key that uniquely selects the per-artifact renderers whose diataxis/type they
 * share with generic docs. It is optional and leading, so callers that only key
 * on diataxis/contentType keep their prior behavior once they pass it through.
 */
export function resolveRenderer(
  renderer?: string,
  diataxis?: string,
  contentType?: string
): RendererComponent {
  if (renderer !== undefined) {
    const byRenderer = RENDERER_REGISTRY.get(renderer);
    if (byRenderer !== undefined) {
      return byRenderer;
    }
  }
  if (diataxis !== undefined) {
    const byDiataxis = RENDERER_REGISTRY.get(diataxis);
    if (byDiataxis !== undefined) {
      return byDiataxis;
    }
  }
  if (contentType !== undefined) {
    const byType = RENDERER_REGISTRY.get(contentType);
    if (byType !== undefined) {
      return byType;
    }
  }
  return DefaultShell;
}
