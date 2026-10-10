import { mkdtemp, mkdir, rm, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { getArchitectureData } from "@/server/view-models/architecture";

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("getArchitectureData", () => {
  it("rejects roots that do not look like Praxion projects", async () => {
    const root = await createTempProjectRoot("dashboard-architecture-invalid-");

    await expect(getArchitectureData(root)).rejects.toThrow(/project root/i);
  });

  it("reads design, guide, and rendered diagrams from canonical paths", async () => {
    const root = await createTempProjectRoot("dashboard-architecture-valid-");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(root, ".ai-work"), { recursive: true });
    await mkdir(path.join(root, "docs", "diagrams", "rendered"), { recursive: true });
    await mkdir(path.join(root, "docs", "diagrams", "drafts"), { recursive: true });

    await writeFile(path.join(root, ".ai-state", "DESIGN.md"), "# Design\n");
    await writeFile(path.join(root, "docs", "architecture.md"), "# Guide\n");
    await writeFile(
      path.join(root, "docs", "diagrams", "rendered", "system.svg"),
      "<svg><title>System</title></svg>"
    );
    await writeFile(
      path.join(root, "docs", "diagrams", "drafts", "system.svg"),
      "<svg><title>Draft</title></svg>"
    );

    const data = await getArchitectureData(root);

    expect(data.design?.body).toContain("Design");
    expect(data.guide?.body).toContain("Guide");
    expect(data.diagrams).toHaveLength(1);
    expect(data.diagrams[0]?.path).toBe(
      path.join(root, "docs", "diagrams", "rendered", "system.svg")
    );
    expect(data.diagrams[0]?.markup).toContain("System");
  });

  it("applies normalization after sanitization: markup has data-aspect and no width attr", async () => {
    const root = await createTempProjectRoot("dashboard-architecture-normalize-");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(root, ".ai-work"), { recursive: true });
    await mkdir(path.join(root, "docs", "diagrams", "rendered"), { recursive: true });

    // SVG with explicit width/height numeric attributes so normalizeSvg can
    // compute the aspect ratio via the width/height fallback path (sanitize-html
    // lowercases attribute names, which means `viewBox` is not currently
    // preserved through sanitizeSvg — tracked as a dependency; this test uses
    // the numeric width/height path that does survive sanitization).
    // The style="max-width:..." should be stripped by normalizeSvg.
    const svgWithNumericSize =
      '<svg id="my-svg" width="1645" height="597" style="max-width: 1645px; background-color: white;"><title>Diagram</title></svg>';

    await writeFile(path.join(root, ".ai-state", "DESIGN.md"), "# Design\n");
    await writeFile(path.join(root, "docs", "architecture.md"), "# Guide\n");
    await writeFile(
      path.join(root, "docs", "diagrams", "rendered", "flow.svg"),
      svgWithNumericSize
    );

    const data = await getArchitectureData(root);

    const diagram = data.diagrams[0];
    expect(diagram).toBeDefined();
    // normalizeSvg must have run: data-aspect is present (computed from w/h).
    expect(diagram?.markup).toContain("data-aspect=");
    // The width and height attributes must be gone.
    expect(diagram?.markup).not.toMatch(/\bwidth="\d+"/);
    expect(diagram?.markup).not.toMatch(/\bheight="\d+"/);
    // The inline max-width declaration must be gone.
    expect(diagram?.markup).not.toMatch(/max-width/i);
  });
});

describe("getArchitectureData diagram order", () => {
  it("lists renders in the order their views are declared, undeclared renders last", async () => {
    const root = await createTempProjectRoot("dashboard-architecture-order-");
    const diagrams = path.join(root, "docs", "diagrams", "architecture");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(diagrams, "rendered"), { recursive: true });
    await mkdir(path.join(diagrams, "src"), { recursive: true });
    await writeFile(
      path.join(diagrams, "src", "architecture.c4"),
      "views {\n  view index {\n  }\n  dynamic view flow {\n  }\n  view components {\n  }\n}\n"
    );
    for (const stem of ["components", "extra", "flow", "index"]) {
      await writeFile(
        path.join(diagrams, "rendered", `${stem}.svg`),
        `<svg><title>${stem}</title></svg>`
      );
    }

    const data = await getArchitectureData(root);

    expect(data.diagrams.map((diagram) => path.basename(diagram.path))).toEqual([
      "index.svg",
      "flow.svg",
      "components.svg",
      "extra.svg"
    ]);
  });

  it("keeps the alphabetical order when no model source declares the views", async () => {
    const root = await createTempProjectRoot("dashboard-architecture-undeclared-");
    const rendered = path.join(root, "docs", "diagrams", "rendered");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(rendered, { recursive: true });
    for (const stem of ["b", "a"]) {
      await writeFile(path.join(rendered, `${stem}.svg`), `<svg><title>${stem}</title></svg>`);
    }

    const data = await getArchitectureData(root);

    expect(data.diagrams.map((diagram) => path.basename(diagram.path))).toEqual(["a.svg", "b.svg"]);
  });
});

describe("getArchitectureData dataAsOf", () => {
  const stamp = (iso: string) => new Date(iso);

  async function seed(prefix: string) {
    const root = await createTempProjectRoot(prefix);
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(root, ".ai-work"), { recursive: true });
    await mkdir(path.join(root, "docs", "diagrams", "rendered"), { recursive: true });
    return root;
  }

  async function writeAt(target: string, body: string, at: Date) {
    await writeFile(target, body);
    await utimes(target, at, at);
  }

  it("is the newest of the design, the guide and the rendered diagrams", async () => {
    const root = await seed("dashboard-architecture-asof-");
    await writeAt(path.join(root, ".ai-state", "DESIGN.md"), "# Design\n", stamp("2026-09-01T00:00:00Z"));
    await writeAt(path.join(root, "docs", "architecture.md"), "# Guide\n", stamp("2026-09-02T00:00:00Z"));
    await writeAt(
      path.join(root, "docs", "diagrams", "rendered", "system.svg"),
      "<svg><title>System</title></svg>",
      stamp("2026-09-03T00:00:00Z")
    );

    expect((await getArchitectureData(root)).dataAsOf).toBe("2026-09-03T00:00:00.000Z");
  });

  it("is null when no architecture artifact exists", async () => {
    const root = await seed("dashboard-architecture-asof-empty-");

    expect((await getArchitectureData(root)).dataAsOf).toBeNull();
  });
});
