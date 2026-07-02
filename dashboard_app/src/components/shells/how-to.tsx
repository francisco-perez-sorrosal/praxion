import { MarkdownSurface } from "@/components/markdown-surface";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

/**
 * Goal-first layout: a labelled goal banner above the body.
 * Suited for procedural documents oriented around accomplishing a specific task.
 * The goal slot is empty in v1; future surfaces may populate it via surface metadata.
 */
export function HowToShell({ body }: RendererProps) {
  return (
    <div className="shell-howto">
      <section className="shell-howto-goal" aria-label="Goal">
        {/* Goal slot — populated by future surface metadata */}
      </section>
      <div className="shell-howto-body">
        <MarkdownSurface body={body} />
      </div>
    </div>
  );
}
