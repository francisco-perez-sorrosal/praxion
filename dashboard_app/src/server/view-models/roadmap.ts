import "server-only";

import path from "node:path";

import { fileMtime } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";

export async function getRoadmapData(projectRoot: string) {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const roadmapPath = await assertAllowedArtifactPath(
    validatedRoot,
    path.join(validatedRoot, "ROADMAP.md")
  );
  const roadmap = await readMarkdown(roadmapPath);
  return roadmap ? { ...roadmap, dataAsOf: await fileMtime(roadmapPath) } : null;
}
