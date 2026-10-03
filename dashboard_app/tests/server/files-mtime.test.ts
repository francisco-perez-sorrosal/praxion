import { mkdtemp, rm, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { fileMtime, newestMtime } from "@/server/artifacts/files";

const OLDER = new Date("2026-09-01T08:00:00.000Z");
const NEWER = new Date("2026-09-20T16:30:00.000Z");

let root: string;

beforeEach(async () => {
  root = await mkdtemp(path.join(os.tmpdir(), "dashboard-files-mtime-"));
});

afterEach(async () => {
  await rm(root, { force: true, recursive: true });
});

async function touch(name: string, at: Date): Promise<string> {
  const target = path.join(root, name);
  await writeFile(target, "x");
  await utimes(target, at, at);
  return target;
}

describe("fileMtime", () => {
  it("returns the modification time of a file as an ISO string", async () => {
    const target = await touch("a.md", OLDER);

    expect(await fileMtime(target)).toBe(OLDER.toISOString());
  });

  it("returns null for a path that does not exist", async () => {
    expect(await fileMtime(path.join(root, "missing.md"))).toBeNull();
  });
});

describe("newestMtime", () => {
  it("returns the newest modification time among the paths", async () => {
    const older = await touch("older.md", OLDER);
    const newer = await touch("newer.md", NEWER);

    expect(await newestMtime([older, newer])).toBe(NEWER.toISOString());
    expect(await newestMtime([newer, older])).toBe(NEWER.toISOString());
  });

  it("ignores paths that do not exist", async () => {
    const older = await touch("older.md", OLDER);

    expect(await newestMtime([path.join(root, "missing.md"), older])).toBe(OLDER.toISOString());
  });

  it("returns null when nothing was read", async () => {
    expect(await newestMtime([])).toBeNull();
    expect(await newestMtime([path.join(root, "missing.md")])).toBeNull();
  });
});
