import "server-only";

import path from "node:path";

import { isSentinelReport, listDirectory } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";

export async function getSentinelData(projectRoot: string) {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const reportsRoot = path.join(validatedRoot, ".ai-state", "sentinel_reports");
  const reportPaths = (await listDirectory(reportsRoot))
    .filter((entry) => isSentinelReport(entry))
    .sort((left, right) => right.localeCompare(left))
    .map((entry) => path.join(reportsRoot, entry));

  const latest =
    reportPaths.length > 0
      ? await readMarkdown(await assertAllowedArtifactPath(validatedRoot, reportPaths[0]))
      : null;
  const log = await readMarkdown(
    await assertAllowedArtifactPath(validatedRoot, path.join(reportsRoot, "SENTINEL_LOG.md"))
  );

  return {
    latest,
    log,
    reports: await Promise.all(
      reportPaths.map((reportPath) => assertAllowedArtifactPath(validatedRoot, reportPath))
    )
  };
}
