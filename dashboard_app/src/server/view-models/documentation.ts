import "server-only";

import path from "node:path";

import {
  assertAllowedArtifactPath,
  assertContainedProjectPath,
  validateProjectRoot
} from "@/server/artifacts/project-root";
import { readJson, readMarkdown, readYaml } from "@/server/parsers/content";
import type { ManifestGroup, ManifestSurface } from "@/server/types";

export type DocumentationSurfaceData = {
  body: string | null;
  errorMessage: string | null;
  path: string;
  renderMode: "code" | "error" | "markdown" | "unsupported";
  surface: ManifestSurface;
};

export async function getDocumentationData(projectRoot: string) {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const manifestPath = await assertAllowedArtifactPath(
    validatedRoot,
    path.join(validatedRoot, ".ai-state", "doc_manifest.yaml")
  );
  const manifest = await readYaml<{
    groups?: ManifestGroup[];
    surfaces?: ManifestSurface[];
  }>(manifestPath);

  if (!manifest) {
    return null;
  }

  return {
    groups: manifest.groups ?? [],
    manifestPath,
    surfaces: manifest.surfaces ?? []
  };
}

export async function getDocumentationSurfaceData(
  projectRoot: string,
  surface: ManifestSurface
): Promise<DocumentationSurfaceData> {
  const validatedRoot = await validateProjectRoot(projectRoot);

  try {
    const absolutePath = await assertContainedProjectPath(
      validatedRoot,
      path.join(validatedRoot, surface.path)
    );

    if (surface.type === "markdown") {
      const file = await readMarkdown(absolutePath);
      return {
        body: file?.body ?? null,
        errorMessage: file ? null : "Unreadable file.",
        path: absolutePath,
        renderMode: "markdown",
        surface
      };
    }

    if (surface.type === "json") {
      const value = await readJson<Record<string, unknown>>(absolutePath);
      return {
        body: value === null ? null : JSON.stringify(value, null, 2),
        errorMessage: value === null ? "Unreadable file." : null,
        path: absolutePath,
        renderMode: "code",
        surface
      };
    }

    if (surface.type === "yaml") {
      const value = await readYaml<Record<string, unknown>>(absolutePath);
      return {
        body: value === null ? null : JSON.stringify(value, null, 2),
        errorMessage: value === null ? "Unreadable file." : null,
        path: absolutePath,
        renderMode: "code",
        surface
      };
    }

    return {
      body: null,
      errorMessage: `Unsupported surface type for this slice: ${surface.type}`,
      path: absolutePath,
      renderMode: "unsupported",
      surface
    };
  } catch (error) {
    return {
      body: null,
      errorMessage:
        error instanceof Error ? error.message : "Surface path could not be resolved.",
      path: surface.path,
      renderMode: "error",
      surface
    };
  }
}
