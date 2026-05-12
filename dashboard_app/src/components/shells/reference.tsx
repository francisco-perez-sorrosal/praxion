"use client";

import { MarkdownSurface } from "@/components/markdown-surface";
import { extractToc } from "@/lib/markdown-headings";
import type { TocEntry } from "@/lib/markdown-headings";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

/**
 * Two-column layout: sticky ToC sidebar on the left, body on the right.
 * Suited for reference documents that readers scan by section.
 */
export function ReferenceShell({ body }: RendererProps) {
  const toc = extractToc(body);

  return (
    <div className="shell-reference">
      <nav className="shell-reference-toc" aria-label="Table of contents">
        <p className="shell-toc-heading">Contents</p>
        <ul className="shell-toc-list">
          {toc.map((entry: TocEntry) => (
            <li
              key={entry.slug}
              className="shell-toc-item"
              style={{ paddingLeft: `${(entry.level - 1) * 0.75}rem` }}
            >
              <a href={`#${entry.slug}`}>{entry.text}</a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="shell-reference-body">
        <MarkdownSurface body={body} />
      </div>
    </div>
  );
}
