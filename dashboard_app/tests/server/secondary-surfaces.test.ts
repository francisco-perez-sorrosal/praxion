import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { getAdrData } from "@/server/view-models/adrs";
import {
  getDocumentationData,
  getDocumentationSurfaceData
} from "@/server/view-models/documentation";
import { getMetricsData } from "@/server/view-models/metrics";
import { getRoadmapData } from "@/server/view-models/roadmap";
import { getSentinelData } from "@/server/view-models/sentinel";
import type { ManifestSurface } from "@/server/types";

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

async function seedProjectRoot(root: string): Promise<void> {
  await mkdir(path.join(root, ".ai-state"), { recursive: true });
  await mkdir(path.join(root, ".ai-work"), { recursive: true });
  await mkdir(path.join(root, "docs"), { recursive: true });
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("secondary dashboard surfaces", () => {
  it("loads finalized and draft ADRs from canonical decisions paths", async () => {
    const root = await createTempProjectRoot("dashboard-adrs-valid-");
    await seedProjectRoot(root);
    await mkdir(path.join(root, ".ai-state", "decisions", "drafts"), { recursive: true });

    await writeFile(
      path.join(root, ".ai-state", "decisions", "001-dashboard-runtime.md"),
      "---\ntitle: Runtime decision\nstatus: accepted\n---\n# Runtime\n"
    );
    await writeFile(
      path.join(root, ".ai-state", "decisions", "drafts", "2026-05-11-dashboard.md"),
      "---\ntitle: Draft decision\nstatus: proposed\n---\n# Draft\n"
    );

    const adrs = await getAdrData(root);

    expect(adrs).toHaveLength(2);
    expect(adrs.some((adr) => adr.isDraft)).toBe(true);
    expect(adrs.some((adr) => adr.body.includes("Runtime"))).toBe(true);
  });

  it("loads the latest sentinel report and the history log", async () => {
    const root = await createTempProjectRoot("dashboard-sentinel-valid-");
    await seedProjectRoot(root);
    await mkdir(path.join(root, ".ai-state", "sentinel_reports"), { recursive: true });

    await writeFile(
      path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_REPORT_2026-05-10_09-00-00.md"),
      "# Earlier report\n"
    );
    await writeFile(
      path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_REPORT_2026-05-11_09-00-00.md"),
      "# Latest report\n"
    );
    await writeFile(
      path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_LOG.md"),
      "# History\n"
    );

    const sentinel = await getSentinelData(root);

    expect(path.basename(sentinel.reports[0] ?? "")).toBe(
      "SENTINEL_REPORT_2026-05-11_09-00-00.md"
    );
    expect(sentinel.latest?.body).toContain("Latest report");
    expect(sentinel.log?.body).toContain("History");
  });

  it("loads roadmap and the latest metrics report from canonical locations", async () => {
    const root = await createTempProjectRoot("dashboard-metrics-valid-");
    await seedProjectRoot(root);
    await mkdir(path.join(root, ".ai-state", "metrics_reports"), { recursive: true });

    await writeFile(path.join(root, "ROADMAP.md"), "# Roadmap\n");
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_REPORT_2026-05-10_09-00-00.json"),
      JSON.stringify({ aggregate: { sloc_total: 100 } })
    );
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_REPORT_2026-05-11_09-00-00.json"),
      JSON.stringify({ aggregate: { sloc_total: 200 } })
    );
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_LOG.md"),
      "# Metrics history\n"
    );

    const [roadmap, metrics] = await Promise.all([getRoadmapData(root), getMetricsData(root)]);

    expect(roadmap?.body).toContain("Roadmap");
    expect(path.basename(metrics.latestPath ?? "")).toBe(
      "METRICS_REPORT_2026-05-11_09-00-00.json"
    );
    expect((metrics.latest?.aggregate as { sloc_total?: number })?.sloc_total).toBe(200);
    expect(metrics.log?.body).toContain("Metrics history");
  });

  it("renders manifest-driven documentation surfaces through the server layer", async () => {
    const root = await createTempProjectRoot("dashboard-docs-valid-");
    await seedProjectRoot(root);

    await writeFile(path.join(root, "docs", "guide.md"), "# Guide\n");
    await writeFile(
      path.join(root, ".ai-state", "stats.json"),
      JSON.stringify({ total: 3 }, null, 2)
    );
    await writeFile(
      path.join(root, ".ai-state", "doc_manifest.yaml"),
      [
        "groups:",
        "  - id: docs",
        "    label: Docs",
        "    surface_ids: [guide, stats]",
        "surfaces:",
        "  - id: guide",
        "    title: Guide",
        "    path: docs/guide.md",
        "    type: markdown",
        "  - id: stats",
        "    title: Stats",
        "    path: .ai-state/stats.json",
        "    type: json"
      ].join("\n")
    );

    const manifest = await getDocumentationData(root);
    expect(manifest).not.toBeNull();

    const surfaces = manifest?.surfaces ?? [];
    const markdownSurface = await getDocumentationSurfaceData(
      root,
      surfaces[0] as ManifestSurface
    );
    const jsonSurface = await getDocumentationSurfaceData(root, surfaces[1] as ManifestSurface);

    expect(markdownSurface.renderMode).toBe("markdown");
    expect(markdownSurface.body).toContain("Guide");
    expect(jsonSurface.renderMode).toBe("code");
    expect(jsonSurface.body).toContain("\"total\": 3");
  });

  it("blocks documentation surfaces that escape the selected project root", async () => {
    const root = await createTempProjectRoot("dashboard-docs-invalid-surface-");
    await seedProjectRoot(root);

    const surface: ManifestSurface = {
      id: "escape",
      path: "../outside.md",
      title: "Escape",
      type: "markdown"
    };

    const data = await getDocumentationSurfaceData(root, surface);

    expect(data.renderMode).toBe("error");
    expect(data.errorMessage).toMatch(/project root/i);
  });
});
