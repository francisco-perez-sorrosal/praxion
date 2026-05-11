import "server-only";

import path from "node:path";

import {
  CANONICAL_WORKSHOP_ARTIFACTS,
  listDirectoryByMtimeDesc,
  pathExists
} from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";
import { parseProgressBody, parseWipBody } from "@/server/parsers/workshops";
import type { WorkshopState } from "@/server/types";

export async function getWorkshopsData(projectRoot: string): Promise<WorkshopState[]> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const workshopsRoot = path.join(validatedRoot, ".ai-work");
  const workshopDirs = await listDirectoryByMtimeDesc(workshopsRoot);

  return Promise.all(
    workshopDirs.map(async (dirName) => {
      const workshopRoot = path.join(workshopsRoot, dirName);
      const [wipPath, progressPath] = await Promise.all([
        assertAllowedArtifactPath(validatedRoot, path.join(workshopRoot, "WIP.md")),
        assertAllowedArtifactPath(validatedRoot, path.join(workshopRoot, "PROGRESS.md"))
      ]);
      const [wip, progress] = await Promise.all([
        readMarkdown(wipPath),
        readMarkdown(progressPath)
      ]);

      const wipState = wip
        ? parseWipBody(wip.body)
        : { currentStep: null, progress: [], status: null };
      const events = progress ? parseProgressBody(progress.body) : [];
      const artifacts = await Promise.all(
        CANONICAL_WORKSHOP_ARTIFACTS.map(async (artifact) => {
          const artifactPath = await assertAllowedArtifactPath(
            validatedRoot,
            path.join(workshopRoot, artifact)
          );
          return (await pathExists(artifactPath)) ? artifact : null;
        })
      );

      return {
        artifacts: artifacts.filter(
          (artifact): artifact is string => artifact !== null
        ),
        currentStep: wipState.currentStep,
        events,
        path: workshopRoot,
        progress: wipState.progress,
        status: wipState.status
      };
    })
  );
}
