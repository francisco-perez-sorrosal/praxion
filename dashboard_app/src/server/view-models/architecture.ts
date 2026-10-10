import "server-only";

import path from "node:path";

import { modelSourcesBeside, newestMtime, readText, walkRenderedSvgs } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { sanitizeSvg } from "@/server/diagrams/sanitize";
import { normalizeSvg } from "@/server/diagrams/normalize-svg";
import { rewriteRelativeImageRefs } from "@/server/diagrams/rewrite-image-refs";
import { declaredViewIds, orderRenders } from "@/server/diagrams/view-order";
import { readMarkdown } from "@/server/parsers/content";
import { splitAacRegions } from "@/server/aac/parse-fences";

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

  const rewrittenDesign = design
    ? { ...design, body: rewriteRelativeImageRefs(design.body, ".ai-state", validatedRoot) }
    : null;

  const rewrittenGuide = guide
    ? { ...guide, body: rewriteRelativeImageRefs(guide.body, "docs", validatedRoot) }
    : null;

  // Narrative order: the view declarations of each rendered/ directory's sibling src/ models.
  const declared = new Map<string, string[]>();
  for (const renderedDir of new Set(diagramPaths.map((diagramPath) => path.dirname(diagramPath)))) {
    const sources = await Promise.all(
      (await modelSourcesBeside(renderedDir)).map(async (source) =>
        readText(await assertAllowedArtifactPath(validatedRoot, source))
      )
    );
    const text = sources.filter((source): source is string => source !== null).join("\n");
    declared.set(renderedDir, declaredViewIds(text));
  }

  const diagrams = (
    await Promise.all(
      orderRenders(diagramPaths, declared).map(async (diagramPath) => {
        const safePath = await assertAllowedArtifactPath(validatedRoot, diagramPath);
        const raw = await readText(safePath);
        const sanitized = raw !== null ? sanitizeSvg(raw) : null;
        const markup = sanitized !== null ? normalizeSvg(sanitized) : null;
        return {
          markup,
          path: safePath
        };
      })
    )
  ).filter((diagram) => diagram.markup);

  const regions = rewrittenDesign ? splitAacRegions(rewrittenDesign.body) : [];
  const dataAsOf = await newestMtime([designPath, guidePath, ...diagramPaths]);

  return { dataAsOf, design: rewrittenDesign, diagrams, guide: rewrittenGuide, regions };
}
