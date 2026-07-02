import { describe, expect, it } from "vitest";

import {
  ArchitectureExplorerRenderer,
  IdeaGridRenderer,
  MetricsViewRenderer,
  PlanViewRenderer,
  VerificationReportRenderer
} from "@/components/renderers";
import {
  RENDERER_REGISTRY,
  resolveRenderer
} from "@/components/registry";
import { ConceptsShell } from "@/components/shells/concepts";
import { DefaultShell } from "@/components/shells/default";
import { ExplanationShell } from "@/components/shells/explanation";
import { HowToShell } from "@/components/shells/how-to";
import { ReferenceShell } from "@/components/shells/reference";
import { TutorialShell } from "@/components/shells/tutorial";

// ─── RENDERER_REGISTRY size and coverage ────────────────────────────────────

describe("RENDERER_REGISTRY — twelve registered keys", () => {
  it("contains at least twelve keys (seven shells + five per-artifact renderers)", () => {
    expect(RENDERER_REGISTRY.size).toBeGreaterThanOrEqual(12);
  });

  it("registers the reference key", () => {
    expect(RENDERER_REGISTRY.has("reference")).toBe(true);
  });

  it("registers the explanation key", () => {
    expect(RENDERER_REGISTRY.has("explanation")).toBe(true);
  });

  it("registers the markdown key", () => {
    expect(RENDERER_REGISTRY.has("markdown")).toBe(true);
  });

  it("registers the tutorial key", () => {
    expect(RENDERER_REGISTRY.has("tutorial")).toBe(true);
  });

  it("registers the how-to key", () => {
    expect(RENDERER_REGISTRY.has("how-to")).toBe(true);
  });

  it("registers the concepts key", () => {
    expect(RENDERER_REGISTRY.has("concepts")).toBe(true);
  });

  it("registers the api_reference key", () => {
    expect(RENDERER_REGISTRY.has("api_reference")).toBe(true);
  });

  it("registers the metrics_view key", () => {
    expect(RENDERER_REGISTRY.has("metrics_view")).toBe(true);
  });

  it("registers the plan_view key", () => {
    expect(RENDERER_REGISTRY.has("plan_view")).toBe(true);
  });

  it("registers the verification_report key", () => {
    expect(RENDERER_REGISTRY.has("verification_report")).toBe(true);
  });

  it("registers the idea_grid key", () => {
    expect(RENDERER_REGISTRY.has("idea_grid")).toBe(true);
  });

  it("registers the architecture_explorer key", () => {
    expect(RENDERER_REGISTRY.has("architecture_explorer")).toBe(true);
  });
});

// ─── resolveRenderer — renderer field takes highest priority ─────────────────

describe("resolveRenderer — renderer field takes highest priority", () => {
  it("returns MetricsViewRenderer for renderer=metrics_view", () => {
    expect(resolveRenderer("metrics_view")).toBe(MetricsViewRenderer);
  });

  it("returns PlanViewRenderer for renderer=plan_view", () => {
    expect(resolveRenderer("plan_view")).toBe(PlanViewRenderer);
  });

  it("returns VerificationReportRenderer for renderer=verification_report", () => {
    expect(resolveRenderer("verification_report")).toBe(VerificationReportRenderer);
  });

  it("returns IdeaGridRenderer for renderer=idea_grid", () => {
    expect(resolveRenderer("idea_grid")).toBe(IdeaGridRenderer);
  });

  it("returns ArchitectureExplorerRenderer for renderer=architecture_explorer", () => {
    expect(resolveRenderer("architecture_explorer")).toBe(ArchitectureExplorerRenderer);
  });

  it("renderer match wins over a diataxis and contentType that would resolve elsewhere", () => {
    // metrics_view surfaces share diataxis=reference / type=markdown with plain
    // reference docs — the renderer field is the only key that selects them, so
    // it must beat the diataxis lookup that would otherwise return ReferenceShell.
    expect(resolveRenderer("metrics_view", "reference", "markdown")).toBe(MetricsViewRenderer);
  });
});

// ─── resolveRenderer — diataxis match when no renderer field ─────────────────

describe("resolveRenderer — diataxis match when the renderer field is absent", () => {
  it("returns ReferenceShell for diataxis=reference", () => {
    expect(resolveRenderer(undefined, "reference")).toBe(ReferenceShell);
  });

  it("returns ExplanationShell for diataxis=explanation", () => {
    expect(resolveRenderer(undefined, "explanation")).toBe(ExplanationShell);
  });

  it("diataxis match wins over contentType match", () => {
    // No renderer field: diataxis=reference wins over a contentType that would
    // otherwise resolve to markdown (DefaultShell). This is the pre-existing
    // resolution order, preserved unchanged for surfaces without a renderer field.
    expect(resolveRenderer(undefined, "reference", "markdown")).toBe(ReferenceShell);
  });
});

// ─── resolveRenderer — dedicated Diátaxis shells ─────────────────────────────

describe("resolveRenderer — tutorial/how-to/concepts resolve to dedicated shells", () => {
  it("returns TutorialShell for diataxis=tutorial", () => {
    expect(resolveRenderer(undefined, "tutorial")).toBe(TutorialShell);
  });

  it("returns HowToShell for diataxis=how-to", () => {
    expect(resolveRenderer(undefined, "how-to")).toBe(HowToShell);
  });

  it("returns ConceptsShell for diataxis=concepts", () => {
    expect(resolveRenderer(undefined, "concepts")).toBe(ConceptsShell);
  });
});

// ─── resolveRenderer — contentType fallback ──────────────────────────────────

describe("resolveRenderer — falls back to contentType when renderer and diataxis are absent", () => {
  it("returns DefaultShell for contentType=markdown with no renderer or diataxis", () => {
    expect(resolveRenderer(undefined, undefined, "markdown")).toBe(DefaultShell);
  });
});

// ─── resolveRenderer — unknown → DefaultShell ────────────────────────────────

describe("resolveRenderer — unknown values fall back to DefaultShell", () => {
  it("returns DefaultShell for an unrecognized renderer value", () => {
    expect(resolveRenderer("nonexistent-renderer")).toBe(DefaultShell);
  });

  it("returns DefaultShell for an unrecognized diataxis value", () => {
    expect(resolveRenderer(undefined, "unknown-type")).toBe(DefaultShell);
  });

  it("returns DefaultShell when renderer, diataxis and contentType are all undefined", () => {
    expect(resolveRenderer(undefined, undefined, undefined)).toBe(DefaultShell);
  });

  it("returns DefaultShell for an unrecognized contentType with no renderer or diataxis", () => {
    expect(resolveRenderer(undefined, undefined, "unknown-format")).toBe(DefaultShell);
  });
});
