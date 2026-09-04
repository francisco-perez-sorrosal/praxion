import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  ALLOWED_ARTIFACT_ROOTS,
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

  it("accepts a freshly-onboarded project that has only .ai-state and no .ai-work", async () => {
    const root = await createTempProjectRoot("dashboard-root-fresh-");
    await mkdir(path.join(root, ".ai-state"), { recursive: true });

    await expect(validateProjectRoot(root)).resolves.toBe(root);
  });

  it("rejects a project that has .ai-work but no .ai-state", async () => {
    const root = await createTempProjectRoot("dashboard-root-no-state-");
    await mkdir(path.join(root, ".ai-work"), { recursive: true });

    await expect(validateProjectRoot(root)).rejects.toThrow(/project root/i);
  });

  it("rejects a directory that has neither .ai-state nor .ai-work", async () => {
    const root = await createTempProjectRoot("dashboard-root-empty-");

    await expect(validateProjectRoot(root)).rejects.toThrow(/project root/i);
  });
});

describe("project-root guards — sidecar state mount", () => {
  // Sidecar placement (ARCH_WT_RULING.md § 9): every checkout that opts into
  // sidecar placement mounts Praxion state as a real git worktree at
  // `<checkout>/.praxion-state/`, and `.ai-state` in the checkout becomes a
  // *relative* symlink pointing inward at `.praxion-state/.ai-state`. Both existing
  // containment checks (lexical + post-existence realpath) stay unchanged;
  // the only change under test is the allowlist gaining a `.praxion-state/.ai-state`
  // entry so the resolved path clears `isAllowedArtifactPath` too.
  async function createSidecarMountFixture(prefix: string): Promise<string> {
    const root = await createTempProjectRoot(prefix);
    await mkdir(path.join(root, ".praxion-state", ".ai-state", "decisions", "drafts"), {
      recursive: true
    });
    await writeFile(path.join(root, ".praxion-state", ".ai-state", "DESIGN.md"), "# Design\n");
    await writeFile(
      path.join(root, ".praxion-state", ".ai-state", "decisions", "drafts", "x.md"),
      "# Draft\n"
    );
    // Relative symlink, matching the ruling's contract exactly — an absolute
    // symlink would still resolve correctly here but wouldn't pin the
    // relative-ness the ruling requires for a portable checkout.
    await symlink(path.join(".praxion-state", ".ai-state"), path.join(root, ".ai-state"), "dir");
    return root;
  }

  it("serves an artifact reached through the state mount", async () => {
    const root = await createSidecarMountFixture("dashboard-sidecar-mount-");

    const allowedPath = await assertAllowedArtifactPath(
      root,
      path.join(root, ".ai-state", "DESIGN.md")
    );

    expect(allowedPath).toBe(path.join(root, ".ai-state", "DESIGN.md"));
  });

  it("serves a nested artifact reached through the state mount", async () => {
    const root = await createSidecarMountFixture("dashboard-sidecar-nested-");

    const allowedPath = await assertAllowedArtifactPath(
      root,
      path.join(root, ".ai-state", "decisions", "drafts", "x.md")
    );

    expect(allowedPath).toBe(path.join(root, ".ai-state", "decisions", "drafts", "x.md"));
  });

  it("serves the same artifact when requested by its lexical mount path", async () => {
    // Assumption: the allowlist gate applies identically whether the caller
    // reaches the artifact through the `.ai-state` shadow or through the
    // mount's own `.praxion-state/.ai-state` path — both are legitimate on-disk
    // locations for the same data, so both must resolve.
    const root = await createSidecarMountFixture("dashboard-sidecar-lexical-");

    const allowedPath = await assertAllowedArtifactPath(
      root,
      path.join(root, ".praxion-state", ".ai-state", "DESIGN.md")
    );

    expect(allowedPath).toBe(path.join(root, ".praxion-state", ".ai-state", "DESIGN.md"));
  });

  it("still rejects a symlink that escapes the project root under an allowed name", async () => {
    const outsideRoot = await createTempProjectRoot("dashboard-sidecar-outside-");
    await writeFile(path.join(outsideRoot, "secret.md"), "# Secret\n");

    const escapeRoot = await createTempProjectRoot("dashboard-sidecar-escape-");
    await symlink(outsideRoot, path.join(escapeRoot, ".ai-state"), "dir");

    await expect(
      assertAllowedArtifactPath(escapeRoot, path.join(escapeRoot, ".ai-state", "secret.md"))
    ).rejects.toThrow(/resolves outside the configured project root/i);
  });

  it("still rejects a lexically escaping relative path", async () => {
    const root = await createSidecarMountFixture("dashboard-sidecar-traversal-");

    await expect(
      assertAllowedArtifactPath(root, path.join(root, "..", "..", "etc", "passwd"))
    ).rejects.toThrow(/stay inside the configured project root/i);
  });

  it("rejects a path under the mount that falls outside the state allowlist", async () => {
    const root = await createSidecarMountFixture("dashboard-sidecar-narrow-");
    await writeFile(path.join(root, ".praxion-state", "CLAUDE.local.md"), "# Local\n");

    await expect(
      assertAllowedArtifactPath(root, path.join(root, ".praxion-state", "CLAUDE.local.md"))
    ).rejects.toThrow(/allowed/i);
  });

  it("accepts a project root whose .ai-state is a symlink into the mount", async () => {
    const root = await createSidecarMountFixture("dashboard-sidecar-validate-");

    await expect(validateProjectRoot(root)).resolves.toBe(root);
  });

  it("ignores a PRAXION_STATE_ROOT environment override when rejecting an escape", async () => {
    // Pins the retired containment-guard-state-root ADR's re-open condition:
    // no second root is ever admitted through an environment channel. The
    // module reads no env var today, so this guards against that changing
    // silently — the escape is rejected identically whether or not the
    // variable is set.
    const outsideRoot = await createTempProjectRoot("dashboard-sidecar-env-outside-");
    await writeFile(path.join(outsideRoot, "secret.md"), "# Secret\n");

    const escapeRoot = await createTempProjectRoot("dashboard-sidecar-env-escape-");
    await symlink(outsideRoot, path.join(escapeRoot, ".ai-state"), "dir");

    const previousEnv = process.env.PRAXION_STATE_ROOT;
    process.env.PRAXION_STATE_ROOT = outsideRoot;
    try {
      await expect(
        assertAllowedArtifactPath(escapeRoot, path.join(escapeRoot, ".ai-state", "secret.md"))
      ).rejects.toThrow(/resolves outside the configured project root/i);
    } finally {
      if (previousEnv === undefined) {
        delete process.env.PRAXION_STATE_ROOT;
      } else {
        process.env.PRAXION_STATE_ROOT = previousEnv;
      }
    }
  });

  it("exposes exactly the expected allowed artifact roots, including the state mount", () => {
    expect(new Set(ALLOWED_ARTIFACT_ROOTS)).toEqual(
      new Set([".ai-state", ".ai-work", "docs", "ROADMAP.md", ".praxion-state/.ai-state"])
    );
  });
});
