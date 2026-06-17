import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { ApiReferenceShell } from "@/components/shells/api-reference";
import { resolveRenderer } from "@/components/registry";
import { getDocumentationSurfaceData } from "@/server/view-models/documentation";
import type { ManifestSurface } from "@/server/types";

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  // Minimal Praxion-project shape so validateProjectRoot accepts the root.
  await mkdir(path.join(root, ".ai-state"), { recursive: true });
  await mkdir(path.join(root, ".ai-work"), { recursive: true });
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

const OPENAPI_SPEC = [
  "openapi: 3.1.0",
  "info:",
  "  title: Sample API",
  "  version: 1.2.3",
  "paths: {}"
].join("\n");

function apiSurface(overrides: Partial<ManifestSurface>): ManifestSurface {
  return {
    diataxis: "reference",
    id: "openapi",
    path: "openapi.yaml",
    renderer: "api_reference",
    title: "Sample API",
    type: "yaml",
    ...overrides
  };
}

describe("resolveRenderer — api_reference key", () => {
  it("resolves to ApiReferenceShell regardless of diataxis", () => {
    expect(resolveRenderer(undefined, "api_reference")).toBe(ApiReferenceShell);
  });
});

describe("getDocumentationSurfaceData — api_reference surfaces", () => {
  it("returns renderMode 'api' with the raw spec body for a yaml spec", async () => {
    const root = await createTempProjectRoot("dashboard-docapi-yaml-");
    await writeFile(path.join(root, "openapi.yaml"), OPENAPI_SPEC);

    const result = await getDocumentationSurfaceData(root, apiSurface({}));

    expect(result.renderMode).toBe("api");
    expect(result.body).toBe(OPENAPI_SPEC);
    expect(result.errorMessage).toBeNull();
  });

  it("routes a json spec through the api branch (not the code dump)", async () => {
    const root = await createTempProjectRoot("dashboard-docapi-json-");
    const jsonSpec = '{"openapi":"3.1.0","info":{"title":"J","version":"1"},"paths":{}}';
    await writeFile(path.join(root, "openapi.json"), jsonSpec);

    const result = await getDocumentationSurfaceData(
      root,
      apiSurface({ id: "openapi-json", path: "openapi.json", type: "json" })
    );

    expect(result.renderMode).toBe("api");
    expect(result.body).toBe(jsonSpec);
  });

  it("degrades to an empty/error body when the spec is unreadable", async () => {
    const root = await createTempProjectRoot("dashboard-docapi-missing-");

    const result = await getDocumentationSurfaceData(
      root,
      apiSurface({ path: "does-not-exist.yaml" })
    );

    expect(result.body).toBeNull();
    expect(result.errorMessage).toBe("Unreadable file.");
  });
});
