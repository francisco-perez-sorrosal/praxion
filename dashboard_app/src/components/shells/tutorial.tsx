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
 * Ordered step-rail layout: a numbered rail of the body's level-2 headings
 * alongside the full body.
 * Suited for procedural documents that walk a reader through an ordered sequence.
 * The rail always renders (even empty) so its structure never varies with content.
 */
export function TutorialShell({ body }: RendererProps) {
  const steps = extractToc(body).filter(
    (entry: TocEntry) => entry.level === 2
  );

  return (
    <div className="shell-tutorial">
      <ol className="shell-tutorial-steps">
        {steps.map((step: TocEntry) => (
          <li key={step.slug} className="shell-tutorial-step">
            <a href={`#${step.slug}`}>{step.text}</a>
          </li>
        ))}
      </ol>
      <div className="shell-tutorial-body">
        <MarkdownSurface body={body} />
      </div>
    </div>
  );
}
