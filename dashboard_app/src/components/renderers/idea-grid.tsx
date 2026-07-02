import { MarkdownSurface } from "@/components/markdown-surface";
import { DefaultShell } from "@/components/shells";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

const STATUS_SECTIONS = ["Implemented", "Pending", "Discarded"] as const;
const H2_HEADING_RE = /^##\s+(.+)$/;

function extractH2Sections(body: string): Map<string, string> {
  const sections = new Map<string, string>();
  let currentName: string | null = null;
  let currentLines: string[] = [];

  const flush = () => {
    if (currentName !== null) {
      sections.set(currentName, currentLines.join("\n").trim());
    }
  };

  for (const line of body.split("\n")) {
    const match = H2_HEADING_RE.exec(line);
    if (match !== null) {
      flush();
      currentName = (match[1] ?? "").trim();
      currentLines = [];
      continue;
    }
    if (currentName !== null) {
      currentLines.push(line);
    }
  }
  flush();

  return sections;
}

/**
 * Renders the ledger's Implemented/Pending/Discarded H2 sections as three
 * labelled status columns. A partial ledger (e.g. Pending only) still
 * renders the grid — the fallback only triggers when none of the three
 * recognized sections are present.
 */
export function IdeaGridRenderer({ body }: RendererProps) {
  const sections = extractH2Sections(body);
  const hasAnySection = STATUS_SECTIONS.some((name) => sections.has(name));
  if (!hasAnySection) {
    return <DefaultShell body={body} />;
  }

  return (
    <div className="renderer-idea-grid">
      {STATUS_SECTIONS.map((name) => (
        <div key={name} className="renderer-idea-grid-column">
          <h3>{name}</h3>
          {sections.has(name) ? (
            <MarkdownSurface body={sections.get(name) ?? ""} />
          ) : (
            <p className="renderer-idea-grid-empty">No items.</p>
          )}
        </div>
      ))}
    </div>
  );
}
