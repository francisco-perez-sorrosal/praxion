import "server-only";

import path from "node:path";

import { isFinalizedAdr, listDirectory, newestMtime } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";
import { buildAdrGraph } from "@/server/view-models/adr-graph";

export async function getAdrData(projectRoot: string) {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const decisionsRoot = path.join(validatedRoot, ".ai-state", "decisions");
  const draftsRoot = path.join(decisionsRoot, "drafts");
  const [decisionEntries, draftEntries] = await Promise.all([
    listDirectory(decisionsRoot),
    listDirectory(draftsRoot)
  ]);

  const load = async (target: string, isDraft: boolean) => {
    const file = await readMarkdown(await assertAllowedArtifactPath(validatedRoot, target));
    return file ? { ...file, isDraft } : null;
  };

  const records = (
    await Promise.all([
      ...decisionEntries
        .filter((entry) => isFinalizedAdr(entry))
        .map((entry) => load(path.join(decisionsRoot, entry), false)),
      ...draftEntries
        .filter((entry) => entry.endsWith(".md"))
        .map((entry) => load(path.join(draftsRoot, entry), true))
    ])
  ).filter((record) => record !== null);

  const graph = buildAdrGraph(records);
  const dataAsOf = await newestMtime(records.map((record) => record.path));

  return { dataAsOf, graph, records };
}
