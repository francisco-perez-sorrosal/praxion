"use client";

import { MarkdownSurface } from "@/components/markdown-surface";
import { DefaultShell } from "@/components/shells";
import { extractToc } from "@/lib/markdown-headings";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

/**
 * Thin Pathway-B preview of an architecture doc: a compact section-nav map
 * derived from the body's headings, plus a link to the full /architecture
 * explorer route. Not a reimplementation of that route.
 */
export function ArchitectureExplorerRenderer({ body }: RendererProps) {
  const toc = extractToc(body);
  if (toc.length === 0) {
    return <DefaultShell body={body} />;
  }

  return (
    <div className="renderer-architecture">
      <p className="renderer-architecture-heading">
        Architecture guide · {toc.length} sections
      </p>
      <nav className="renderer-architecture-nav" aria-label="Architecture sections">
        <ul>
          {toc.map((entry) => (
            <li key={entry.slug}>{entry.text}</li>
          ))}
        </ul>
      </nav>
      <a href="/architecture">Open the architecture explorer</a>
      <div className="renderer-architecture-body">
        <MarkdownSurface body={body} />
      </div>
    </div>
  );
}
