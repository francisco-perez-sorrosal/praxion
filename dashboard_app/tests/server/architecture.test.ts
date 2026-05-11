import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { getArchitectureData } from "@/server/view-models/architecture";

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("getArchitectureData", () => {
  it("rejects roots that do not look like Praxion projects", async () => {
    const root = await createTempProjectRoot("dashboard-architecture-invalid-");

    await expect(getArchitectureData(root)).rejects.toThrow(/project root/i);
  });

  it("reads design, guide, and rendered diagrams from canonical paths", async () => {
    const root = await createTempProjectRoot("dashboard-architecture-valid-");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(root, ".ai-work"), { recursive: true });
    await mkdir(path.join(root, "docs", "diagrams", "rendered"), { recursive: true });
    await mkdir(path.join(root, "docs", "diagrams", "drafts"), { recursive: true });

    await writeFile(path.join(root, ".ai-state", "DESIGN.md"), "# Design\n");
    await writeFile(path.join(root, "docs", "architecture.md"), "# Guide\n");
    await writeFile(
      path.join(root, "docs", "diagrams", "rendered", "system.svg"),
      "<svg><title>System</title></svg>"
    );
    await writeFile(
      path.join(root, "docs", "diagrams", "drafts", "system.svg"),
      "<svg><title>Draft</title></svg>"
    );

    const data = await getArchitectureData(root);

    expect(data.design?.body).toContain("Design");
    expect(data.guide?.body).toContain("Guide");
    expect(data.diagrams).toHaveLength(1);
    expect(data.diagrams[0]?.path).toBe(
      path.join(root, "docs", "diagrams", "rendered", "system.svg")
    );
    expect(data.diagrams[0]?.markup).toContain("System");
  });
});
