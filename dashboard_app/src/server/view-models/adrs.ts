import "server-only";

import path from "node:path";

import { isFinalizedAdr, listDirectory } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";

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

  const records = await Promise.all([
    ...decisionEntries
      .filter((entry) => isFinalizedAdr(entry))
      .map((entry) => load(path.join(decisionsRoot, entry), false)),
    ...draftEntries
      .filter((entry) => entry.endsWith(".md"))
      .map((entry) => load(path.join(draftsRoot, entry), true))
  ]);

  return records.filter((record) => record !== null);
}
