import "server-only";

import path from "node:path";

import { readText, walkRenderedSvgs } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";

export async function getArchitectureData(projectRoot: string) {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const [designPath, guidePath] = await Promise.all([
    assertAllowedArtifactPath(validatedRoot, path.join(validatedRoot, ".ai-state", "DESIGN.md")),
    assertAllowedArtifactPath(validatedRoot, path.join(validatedRoot, "docs", "architecture.md"))
  ]);
  const [design, guide, diagramPaths] = await Promise.all([
    readMarkdown(designPath),
    readMarkdown(guidePath),
    walkRenderedSvgs(validatedRoot)
  ]);

  const diagrams = (
    await Promise.all(
      diagramPaths.map(async (diagramPath) => {
        const safePath = await assertAllowedArtifactPath(validatedRoot, diagramPath);
        return {
          markup: await readText(safePath),
          path: safePath
        };
      })
    )
  ).filter((diagram) => diagram.markup);

  return { design, diagrams, guide };
}
