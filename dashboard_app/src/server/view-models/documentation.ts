import "server-only";

import path from "node:path";

import {
  assertAllowedArtifactPath,
  assertContainedProjectPath,
  validateProjectRoot
} from "@/server/artifacts/project-root";
import { readText } from "@/server/artifacts/files";
import { readJson, readMarkdown, readYaml } from "@/server/parsers/content";
import type { ManifestGroup, ManifestSurface } from "@/server/types";

export type DocumentationSurfaceData = {
  body: string | null;
  errorMessage: string | null;
  path: string;
  renderMode: "api" | "code" | "error" | "markdown" | "unsupported";
  surface: ManifestSurface;
};

// Secondary allowlist for individual documentation surfaces (td-029):
// `assertContainedProjectPath` alone only guarantees containment inside the
// project root -- any file under the root passes it, so a compromised
// doc_manifest.yaml could expose `src/` or `.env`. This mirrors the bounded
// set of locations `scripts/build_doc_manifest.py` can actually emit: prose
// docs under docs/.ai-state/.ai-work, root-level markdown, and the shallow
// API-spec locations in its `_API_SPEC_DIRS` / `_API_SPEC_FILENAMES` /
// `_API_SPEC_SUFFIXES`. Keep both lists in sync when the generator's bounded
// set changes.
const ALLOWED_DOC_SURFACE_PREFIX_ROOTS = ["docs", ".ai-state", ".ai-work"] as const;
const ROOT_MARKDOWN_FILENAME_PATTERN = /^[A-Za-z0-9][\w.-]*\.md$/;
const API_SPEC_SHALLOW_DIRS = new Set(["", "docs", "openapi", "api", "spec", "specs"]);
const API_SPEC_FILENAMES = new Set([
  "openapi.yaml",
  "openapi.yml",
  "openapi.json",
  "asyncapi.yaml",
  "asyncapi.yml",
  "asyncapi.json"
]);
const API_SPEC_SUFFIXES = new Set([".graphql", ".graphqls"]);

function isApiSpecSurfacePath(relativePath: string): boolean {
  const dirname = path.dirname(relativePath);
  const shallowDir = dirname === "." ? "" : dirname;
  if (!API_SPEC_SHALLOW_DIRS.has(shallowDir)) {
    return false;
  }

  const filename = path.basename(relativePath).toLowerCase();
  return API_SPEC_FILENAMES.has(filename) || API_SPEC_SUFFIXES.has(path.extname(filename));
}

function isAllowedDocSurfacePath(relativePath: string): boolean {
  const isUnderPrefixRoot = ALLOWED_DOC_SURFACE_PREFIX_ROOTS.some(
    (root) => relativePath === root || relativePath.startsWith(`${root}${path.sep}`)
  );
  if (isUnderPrefixRoot) {
    return true;
  }

  const isRootLevelMarkdown =
    path.dirname(relativePath) === "." &&
    ROOT_MARKDOWN_FILENAME_PATTERN.test(path.basename(relativePath));

  return isRootLevelMarkdown || isApiSpecSurfacePath(relativePath);
}

function assertAllowedDocSurface(root: string, absolutePath: string): string {
  const relativePath = path.relative(root, absolutePath);
  if (!isAllowedDocSurfacePath(relativePath)) {
    throw new Error(
      "Documentation surface path is outside the allowed doc surfaces " +
        "(docs/, .ai-state/, .ai-work/, a root-level markdown file, or a recognized API spec location)."
    );
  }
  return absolutePath;
}

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
    assertAllowedDocSurface(validatedRoot, absolutePath);

    // API-reference surfaces route through the registry regardless of `type`
    // (yaml/json/graphql): the raw spec text is read server-side and handed to
    // the Scalar-backed shell. This is the one renderer reached on a
    // non-markdown surface.
    if (surface.renderer === "api_reference") {
      const text = await readText(absolutePath);
      return {
        body: text,
        errorMessage: text === null ? "Unreadable file." : null,
        path: absolutePath,
        renderMode: "api",
        surface
      };
    }

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
