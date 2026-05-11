import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  assertAllowedArtifactPath,
  validateProjectRoot
} from "@/server/artifacts/project-root";

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("project-root guards", () => {
  it("accepts Praxion project roots that expose canonical state directories", async () => {
    const root = await createTempProjectRoot("dashboard-root-valid-");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(root, ".ai-work"), { recursive: true });
    await mkdir(path.join(root, "docs"), { recursive: true });

    await expect(validateProjectRoot(root)).resolves.toBe(root);
  });

  it("rejects roots that are missing Praxion state directories", async () => {
    const root = await createTempProjectRoot("dashboard-root-invalid-");
    await mkdir(path.join(root, "docs"), { recursive: true });

    await expect(validateProjectRoot(root)).rejects.toThrow(/project root/i);
  });

  it("allows canonical dashboard artifact reads inside the selected root", async () => {
    const root = await createTempProjectRoot("dashboard-root-allowed-");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(root, ".ai-work", "demo-task"), { recursive: true });
    await mkdir(path.join(root, "docs"), { recursive: true });
    await writeFile(path.join(root, ".ai-state", "DESIGN.md"), "# Design\n");

    const allowedPath = await assertAllowedArtifactPath(
      root,
      path.join(root, ".ai-state", "DESIGN.md")
    );

    expect(allowedPath).toBe(path.join(root, ".ai-state", "DESIGN.md"));
  });

  it("blocks reads outside the dashboard artifact allowlist", async () => {
    const root = await createTempProjectRoot("dashboard-root-blocked-");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(path.join(root, ".ai-work"), { recursive: true });
    await writeFile(path.join(root, "package.json"), "{}\n");

    await expect(
      assertAllowedArtifactPath(root, path.join(root, "package.json"))
    ).rejects.toThrow(/allowed/i);
  });
});
