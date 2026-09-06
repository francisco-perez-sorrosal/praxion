import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";

/**
 * The documentation route when no `doc_manifest.yaml` could be read — the
 * manifest is generated, so absence is normal sparse state, not an error.
 */
export function DocumentationEmpty() {
  return (
    <PageShell
      title="Documentation"
      sourcesContent={
        <p>
          Required artifact: <code>.ai-state/doc_manifest.yaml</code>
        </p>
      }
    >
      <p className="page-intro__lede muted">
        Generated documentation surfaces discovered from the project filesystem.
      </p>

      <EmptyState
        title="No doc manifest found"
        body="Run `python3 scripts/build_doc_manifest.py` in the target project to generate `.ai-state/doc_manifest.yaml`."
      />
    </PageShell>
  );
}
