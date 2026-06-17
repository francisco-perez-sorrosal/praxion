"use client";

import { ApiReferenceReact } from "@scalar/api-reference-react";
import "@scalar/api-reference-react/style.css";

import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

/**
 * Renders an API spec as live API-reference documentation.
 *
 * OpenAPI / AsyncAPI specs (type yaml|json) are handed to the vendored Scalar
 * standalone bundle as a raw spec string — no view-time CDN fetch, offline-first.
 * GraphQL SDL has no Scalar try-it equivalent, so it falls back to a
 * read-only source view inside the same shell.
 */
export function ApiReferenceShell({ body, surface }: RendererProps) {
  if (surface?.type === "graphql") {
    return (
      <div className="shell-api-reference shell-api-reference--sdl">
        <pre className="code-block">{body}</pre>
      </div>
    );
  }

  return (
    <div className="shell-api-reference">
      <ApiReferenceReact configuration={{ content: body }} />
    </div>
  );
}
