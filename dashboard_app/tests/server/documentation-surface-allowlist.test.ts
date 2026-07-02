import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { getDocumentationSurfaceData } from "@/server/view-models/documentation";
import type { ManifestSurface } from "@/server/types";

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  await mkdir(path.join(root, ".ai-state"), { recursive: true });
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

function markdownSurface(overrides: Partial<ManifestSurface>): ManifestSurface {
  return {
    id: "surface",
    path: "docs/guide.md",
    title: "Surface",
    type: "markdown",
    ...overrides
  };
}

describe("getDocumentationSurfaceData — secondary doc-surface allowlist (td-029)", () => {
  it.each([
    ["docs/guide.md", "docs", "guide.md"],
    [".ai-state/DESIGN.md", ".ai-state", "DESIGN.md"],
    [".ai-work/some-task/WIP.md", ".ai-work/some-task", "WIP.md"],
    ["README.md", "", "README.md"],
    ["CLAUDE.md", "", "CLAUDE.md"]
  ])("allows the known-safe surface %s", async (surfacePath, dir, fileName) => {
    const root = await createTempProjectRoot("dashboard-doc-allow-");
    if (dir) {
      await mkdir(path.join(root, dir), { recursive: true });
    }
    await writeFile(path.join(root, dir, fileName), "# Allowed\n");

    const result = await getDocumentationSurfaceData(root, markdownSurface({ path: surfacePath }));

    expect(result.renderMode).toBe("markdown");
    expect(result.errorMessage).toBeNull();
  });

  it("allows a root-level openapi.yaml spec surface", async () => {
    const root = await createTempProjectRoot("dashboard-doc-allow-apispec-");
    await writeFile(path.join(root, "openapi.yaml"), "openapi: 3.1.0\n");

    const result = await getDocumentationSurfaceData(
      root,
      markdownSurface({
        path: "openapi.yaml",
        renderer: "api_reference",
        type: "yaml"
      })
    );

    expect(result.renderMode).toBe("api");
    expect(result.errorMessage).toBeNull();
  });

  it("rejects a surface path pointing into the source tree", async () => {
    const root = await createTempProjectRoot("dashboard-doc-reject-src-");
    await mkdir(path.join(root, "src"), { recursive: true });
    await writeFile(path.join(root, "src", "example.ts"), "export const x = 1;\n");

    const result = await getDocumentationSurfaceData(
      root,
      markdownSurface({ path: "src/example.ts" })
    );

    expect(result.renderMode).toBe("error");
    expect(result.errorMessage).toMatch(/allowed doc surfaces/i);
  });

  it("rejects a dotfile surface path (blocks .env)", async () => {
    const root = await createTempProjectRoot("dashboard-doc-reject-dotfile-");
    await writeFile(path.join(root, ".env"), "SECRET=leak\n");

    const result = await getDocumentationSurfaceData(root, markdownSurface({ path: ".env" }));

    expect(result.renderMode).toBe("error");
    expect(result.errorMessage).toMatch(/allowed doc surfaces/i);
  });

  it("rejects a surface path that escapes the project root", async () => {
    const root = await createTempProjectRoot("dashboard-doc-reject-escape-");

    const result = await getDocumentationSurfaceData(
      root,
      markdownSurface({ path: "../escape.md" })
    );

    expect(result.renderMode).toBe("error");
    expect(result.errorMessage).toMatch(/project root/i);
  });
});
