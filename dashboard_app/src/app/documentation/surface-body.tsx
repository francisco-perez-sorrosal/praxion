import { RENDERER_REGISTRY, resolveRenderer } from "@/components/registry";
import type { RendererComponent } from "@/components/registry";
import type { ManifestSurface } from "@/server/types";
import type { DocumentationSurfaceData } from "@/server/view-models/documentation";

const SELECT_SURFACE_MESSAGE = "Select a surface from the manifest groups.";
const UNREADABLE_FILE_MESSAGE = "Unreadable file.";

/** The render modes that carry a body and therefore need a renderer. */
type BodyRenderMode = "api" | "code" | "markdown";

/**
 * A resolved renderer, or the explicit absence of one. `raw-code` is a real
 * outcome — a `code` surface whose manifest `renderer:` key is missing or
 * unregistered — not a failure, so it is a variant rather than a null the
 * caller could forget to handle.
 */
export type SurfaceRenderer =
  | { readonly Renderer: RendererComponent; readonly kind: "component" }
  | { readonly kind: "raw-code" };

/**
 * Resolve the component that renders a body-bearing surface. Each mode keys
 * the registry differently: `markdown` through the manifest's own
 * renderer/diataxis/type chain, `api` always through the API-reference shell,
 * `code` only through an explicit `renderer:` key.
 */
export function resolveRendererFor(
  renderMode: BodyRenderMode,
  surface: ManifestSurface | null
): SurfaceRenderer {
  if (renderMode === "markdown") {
    return {
      Renderer: resolveRenderer(surface?.renderer, surface?.diataxis, surface?.type),
      kind: "component"
    };
  }

  if (renderMode === "api") {
    return { Renderer: resolveRenderer(undefined, undefined, "api_reference"), kind: "component" };
  }

  const rendererKey = surface?.renderer;
  const codeRenderer = rendererKey === undefined ? undefined : RENDERER_REGISTRY.get(rendererKey);
  return codeRenderer === undefined
    ? { kind: "raw-code" }
    : { Renderer: codeRenderer, kind: "component" };
}

type SurfaceBodyProps = {
  readonly surface: ManifestSurface | null;
  readonly surfaceData: DocumentationSurfaceData | null;
};

/**
 * The rendered body of the surface preview — the single owner of the
 * `renderMode` dispatch, so the page route itself stays branch-free.
 */
export function SurfaceBody({ surface, surfaceData }: SurfaceBodyProps) {
  if (surfaceData === null) {
    return <p className="muted">{SELECT_SURFACE_MESSAGE}</p>;
  }

  const { body, errorMessage, renderMode } = surfaceData;

  switch (renderMode) {
    case "unsupported":
    case "error":
      // These modes never carry a body; errorMessage is the whole payload.
      return <p className="muted">{errorMessage}</p>;

    case "api":
    case "code":
    case "markdown": {
      // One guard for all three body-bearing modes: an unreadable file has no
      // body to hand a renderer, whatever the mode would have selected.
      if (body === null) {
        return <p className="muted">{errorMessage ?? UNREADABLE_FILE_MESSAGE}</p>;
      }

      const resolved = resolveRendererFor(renderMode, surface);
      if (resolved.kind === "raw-code") {
        return <pre className="code-block">{body}</pre>;
      }

      const { Renderer } = resolved;
      return <Renderer body={body} surface={surface ?? undefined} />;
    }
  }

  // Compile-time exhaustiveness: `renderMode` only narrows to `never` here
  // while every variant is handled above — a new one breaks this line.
  renderMode satisfies never;
  return <p className="muted">{SELECT_SURFACE_MESSAGE}</p>;
}
