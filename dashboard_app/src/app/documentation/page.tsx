import path from "node:path";

import { Chip } from "@/components/chrome/chip";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { newestOf } from "@/lib/tone";
import {
  getDocumentationData,
  getDocumentationSurfaceData
} from "@/server/view-models/documentation";

import { DocGroupsNav } from "./doc-groups-nav";
import { DocumentationEmpty } from "./documentation-empty";
import { selectSurface } from "./select-surface";
import { SurfaceBody } from "./surface-body";

type DocumentationPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function DocumentationPage({
  searchParams
}: DocumentationPageProps) {
  const cfg = getConfig();
  const data = await getDocumentationData(cfg.projectRoot);
  const params = await searchParams;

  if (!data) {
    return <DocumentationEmpty />;
  }

  const selectedSurface = selectSurface(data.surfaces, params);
  const selectedSurfaceData =
    selectedSurface === null
      ? null
      : await getDocumentationSurfaceData(cfg.projectRoot, selectedSurface);

  const sources = (
    <p>
      Manifest: <code>{path.relative(cfg.projectRoot, data.manifestPath)}</code>
    </p>
  );

  return (
    <PageShell
      title="Documentation"
      dataAsOf={newestOf([data.dataAsOf, selectedSurfaceData?.dataAsOf])}
      sourcesContent={sources}
    >
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
              <Chip>
                {selectedSurfaceData && path.isAbsolute(selectedSurfaceData.path)
                  ? path.relative(cfg.projectRoot, selectedSurfaceData.path)
                  : selectedSurface.path}
              </Chip>
              {selectedSurface.diataxis ? <Chip>{selectedSurface.diataxis}</Chip> : null}
            </div>
          ) : null}
          <SurfaceBody surface={selectedSurface} surfaceData={selectedSurfaceData} />
        </section>
      </div>
    </PageShell>
  );
}
