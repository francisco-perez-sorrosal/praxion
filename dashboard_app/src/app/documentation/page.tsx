import path from "node:path";

import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";
import { resolveRenderer } from "@/components/registry";
import { getConfig } from "@/lib/config";
import {
  getDocumentationData,
  getDocumentationSurfaceData
} from "@/server/view-models/documentation";

import { DocGroupsNav } from "./doc-groups-nav";

type DocumentationPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function DocumentationPage({
  searchParams
}: DocumentationPageProps) {
  const cfg = getConfig();
  const data = await getDocumentationData(cfg.projectRoot);
  const params = await searchParams;
  const selectedSurfaceId = typeof params.surface === "string" ? params.surface : null;

  if (!data) {
    const emptySources = (
      <p>
        Required artifact: <code>.ai-state/doc_manifest.yaml</code>
      </p>
    );

    return (
      <PageShell title="Documentation" sourcesContent={emptySources}>
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

  const selectedSurface =
    data.surfaces.find((surface) => surface.id === selectedSurfaceId) ?? data.surfaces[0] ?? null;
  const selectedSurfaceData =
    selectedSurface === null
      ? null
      : await getDocumentationSurfaceData(cfg.projectRoot, selectedSurface);

  let renderedBody: React.ReactNode = (
    <p className="muted">Select a surface from the manifest groups.</p>
  );

  if (selectedSurfaceData?.renderMode === "markdown") {
    const Renderer = resolveRenderer(
      selectedSurface?.diataxis,
      selectedSurface?.type
    );
    renderedBody =
      selectedSurfaceData.body === null ? (
        <p className="muted">{selectedSurfaceData.errorMessage ?? "Unreadable file."}</p>
      ) : (
        <Renderer body={selectedSurfaceData.body} surface={selectedSurface ?? undefined} />
      );
  } else if (selectedSurfaceData?.renderMode === "api") {
    const Renderer = resolveRenderer(undefined, "api_reference");
    renderedBody =
      selectedSurfaceData.body === null ? (
        <p className="muted">{selectedSurfaceData.errorMessage ?? "Unreadable file."}</p>
      ) : (
        <Renderer body={selectedSurfaceData.body} surface={selectedSurface ?? undefined} />
      );
  } else if (selectedSurfaceData?.renderMode === "code") {
    renderedBody =
      selectedSurfaceData.body === null ? (
        <p className="muted">{selectedSurfaceData.errorMessage ?? "Unreadable file."}</p>
      ) : (
        <pre className="code-block">{selectedSurfaceData.body}</pre>
      );
  } else if (
    selectedSurfaceData?.renderMode === "unsupported" ||
    selectedSurfaceData?.renderMode === "error"
  ) {
    renderedBody = <p className="muted">{selectedSurfaceData.errorMessage}</p>;
  }

  const sources = (
    <p>
      Manifest: <code>{path.relative(cfg.projectRoot, data.manifestPath)}</code>
    </p>
  );

  return (
    <PageShell title="Documentation" sourcesContent={sources}>
      <p className="page-intro__lede muted">
        Live rendering of documentation surfaces discovered through the generated doc manifest.
      </p>

      <div className="grid-two">
        <section className="artifact-card">
          <h3>Groups</h3>
          <DocGroupsNav
            groups={data.groups}
            surfaces={data.surfaces}
            selectedSurfaceId={selectedSurface?.id ?? null}
          />
        </section>

        <section className="artifact-card">
          <h3>{selectedSurface?.title ?? "Surface preview"}</h3>
          {selectedSurface ? (
            <div className="artifact-meta">
              <span className="chip">
                {selectedSurfaceData && path.isAbsolute(selectedSurfaceData.path)
                  ? path.relative(cfg.projectRoot, selectedSurfaceData.path)
                  : selectedSurface.path}
              </span>
              {selectedSurface.diataxis ? <span className="chip">{selectedSurface.diataxis}</span> : null}
            </div>
          ) : null}
          {renderedBody}
        </section>
      </div>
    </PageShell>
  );
}
