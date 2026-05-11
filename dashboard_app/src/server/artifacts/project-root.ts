import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

const ALLOWED_ARTIFACT_ROOTS = [".ai-state", ".ai-work", "docs", "ROADMAP.md"] as const;
const REQUIRED_PROJECT_DIRECTORIES = [".ai-state", ".ai-work"] as const;

async function pathExists(target: string): Promise<boolean> {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function isDirectory(target: string): Promise<boolean> {
  try {
    return (await fs.stat(target)).isDirectory();
  } catch {
    return false;
  }
}

function normalizeProjectRoot(projectRoot: string): string {
  const trimmed = projectRoot.trim();
  if (!trimmed) {
    throw new Error("PRAXION project root is required.");
  }

  if (!path.isAbsolute(trimmed)) {
    throw new Error("PRAXION project root must be an absolute path.");
  }

  return path.resolve(trimmed);
}

function isContainedWithin(root: string, target: string): boolean {
  const relative = path.relative(root, target);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function isAllowedArtifactPath(relativePath: string): boolean {
  return ALLOWED_ARTIFACT_ROOTS.some(
    (allowedRoot) =>
      relativePath === allowedRoot || relativePath.startsWith(`${allowedRoot}${path.sep}`)
  );
}

export async function validateProjectRoot(projectRoot: string): Promise<string> {
  const normalizedRoot = normalizeProjectRoot(projectRoot);
  const missingDirectories: string[] = [];

  for (const directory of REQUIRED_PROJECT_DIRECTORIES) {
    if (!(await isDirectory(path.join(normalizedRoot, directory)))) {
      missingDirectories.push(directory);
    }
  }

  if (missingDirectories.length > 0) {
    throw new Error(
      `Invalid Praxion project root: missing required directories ${missingDirectories.join(", ")}.`
    );
  }

  return normalizedRoot;
}

async function assertProjectPath(
  projectRoot: string,
  target: string,
  requireAllowedRoots: boolean
): Promise<string> {
  const normalizedRoot = await validateProjectRoot(projectRoot);
  const absoluteTarget = path.resolve(target);

  if (!isContainedWithin(normalizedRoot, absoluteTarget)) {
    throw new Error("Artifact path must stay inside the configured project root.");
  }

  const lexicalRelativePath = path.relative(normalizedRoot, absoluteTarget);
  if (requireAllowedRoots && !isAllowedArtifactPath(lexicalRelativePath)) {
    throw new Error("Artifact path is outside the allowed dashboard roots.");
  }

  if (await pathExists(absoluteTarget)) {
    const [resolvedRoot, resolvedTarget] = await Promise.all([
      fs.realpath(normalizedRoot),
      fs.realpath(absoluteTarget)
    ]);

    if (!isContainedWithin(resolvedRoot, resolvedTarget)) {
      throw new Error("Artifact path resolves outside the configured project root.");
    }

    const resolvedRelativePath = path.relative(resolvedRoot, resolvedTarget);
    if (requireAllowedRoots && !isAllowedArtifactPath(resolvedRelativePath)) {
      throw new Error("Artifact path resolves outside the allowed dashboard roots.");
    }
  }

  return absoluteTarget;
}

export async function assertContainedProjectPath(
  projectRoot: string,
  target: string
): Promise<string> {
  return assertProjectPath(projectRoot, target, false);
}

export async function assertAllowedArtifactPath(
  projectRoot: string,
  target: string
): Promise<string> {
  return assertProjectPath(projectRoot, target, true);
}
