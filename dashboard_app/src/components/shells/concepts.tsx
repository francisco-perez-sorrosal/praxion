import { MarkdownSurface } from "@/components/markdown-surface";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

/**
 * Narrative layout with a key-takeaway callout aside.
 * Suited for conceptual documents that build understanding over reference lookup.
 * The takeaway slot is empty in v1; future surfaces may populate it via surface metadata.
 */
export function ConceptsShell({ body }: RendererProps) {
  return (
    <div className="shell-concepts">
      <div className="shell-concepts-body">
        <MarkdownSurface body={body} />
      </div>
      <aside className="shell-concepts-takeaway" role="note">
        {/* Key-takeaway slot — populated by future surface metadata */}
      </aside>
    </div>
  );
}
