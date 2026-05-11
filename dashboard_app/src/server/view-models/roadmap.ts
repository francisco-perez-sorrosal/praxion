import "server-only";

import path from "node:path";

import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";

export async function getRoadmapData(projectRoot: string) {
  const validatedRoot = await validateProjectRoot(projectRoot);
  return readMarkdown(
    await assertAllowedArtifactPath(validatedRoot, path.join(validatedRoot, "ROADMAP.md"))
  );
}
