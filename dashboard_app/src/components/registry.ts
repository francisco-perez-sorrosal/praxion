import type { ComponentType } from "react";

import type { ManifestSurface } from "@/server/types";

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
 * Maps Diátaxis values and content-type strings to shell components.
 * Lookup order in resolveRenderer: diataxis → contentType → DefaultShell.
 */
export const RENDERER_REGISTRY: Map<string, RendererComponent> = new Map([
  ["tutorial", TutorialShell],
  ["how-to", HowToShell],
  ["reference", ReferenceShell],
  ["explanation", ExplanationShell],
  ["concepts", ConceptsShell],
  ["markdown", DefaultShell],
  ["api_reference", ApiReferenceShell]
]);

// ─── Resolver ────────────────────────────────────────────────────────────────

/**
 * Resolve the appropriate shell component for a given surface.
 * Priority: diataxis match → contentType match → DefaultShell.
 */
export function resolveRenderer(
  diataxis?: string,
  contentType?: string
): RendererComponent {
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
