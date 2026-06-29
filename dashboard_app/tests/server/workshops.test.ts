import { mkdtemp, mkdir, rm, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { parseProgressBody, parseWipBody } from "@/server/parsers/workshops";
import { getWorkshopsData } from "@/server/view-models/workshops";

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("workshop parsing", () => {
  it("extracts current step, checklist state, and status from WIP markdown", () => {
    const parsed = parseWipBody(`
# WIP

## Current Step

Draft failing tests

## Status

[IN-PROGRESS] - RED test skeletons are being written

## Progress

- [x] Step alpha: Reshape the scaffold into the ratified package layout
- [ ] Step beta: Draft failing tests
`);

    expect(parsed.currentStep).toBe("Draft failing tests");
    expect(parsed.status).toContain("[IN-PROGRESS]");
    expect(parsed.progress).toEqual([
      {
        checked: true,
        current: false,
        label: "Reshape the scaffold into the ratified package layout",
        stepId: "alpha"
      },
      {
        checked: false,
        current: true,
        label: "Draft failing tests",
        stepId: "beta"
      }
    ]);
  });

  it("extracts workshop events from PROGRESS entries", () => {
    const events = parseProgressBody(`
[2026-05-11T09:00:00Z] [test-engineer] Phase 1/6: [understand-scope] -- Read the first-slice spec
[2026-05-11T09:10:00Z] [test-engineer] Phase 3/6: [red-tests] -- Wrote failing contract tests
`);

    expect(events).toEqual([
      {
        agent: "test-engineer",
        phase: "1/6",
        summary: "Read the first-slice spec",
        timestamp: "2026-05-11T09:00:00Z"
      },
      {
        agent: "test-engineer",
        phase: "3/6",
        summary: "Wrote failing contract tests",
        timestamp: "2026-05-11T09:10:00Z"
      }
    ]);
  });
});

describe("parseWipBody — bare checklist format", () => {
  it("parses bare numeric checklist items like '- [ ] 1. description'", () => {
    const parsed = parseWipBody(`
## Current Step

Ship the reader

## Status

[IN-PROGRESS]

## Progress

- [x] 1. scaffold the package layout
- [ ] 2. Ship the reader
`);

    expect(parsed.progress).toEqual([
      { checked: true, current: false, label: "scaffold the package layout", stepId: "1" },
      { checked: false, current: true, label: "Ship the reader", stepId: "2" }
    ]);
  });

  it("parses a body that mixes Step X.Y: format and bare numeric format", () => {
    const parsed = parseWipBody(`
## Current Step

Beta task

## Status

[IN-PROGRESS]

## Progress

- [x] Step alpha: Earlier checkpoint
- [ ] 2. Beta task
`);

    expect(parsed.progress).toHaveLength(2);
    expect(parsed.progress[0]).toMatchObject({ checked: true, stepId: "alpha" });
    expect(parsed.progress[1]).toMatchObject({ checked: false, stepId: "2" });
  });

  it("still parses the original Step X.Y: format unchanged", () => {
    const parsed = parseWipBody(`
## Current Step

Draft failing tests

## Status

[IN-PROGRESS]

## Progress

- [x] Step 1.1: Scaffold
- [ ] Step 1.2: Draft failing tests
`);

    expect(parsed.progress).toEqual([
      { checked: true, current: false, label: "Scaffold", stepId: "1.1" },
      { checked: false, current: true, label: "Draft failing tests", stepId: "1.2" }
    ]);
  });
});

describe("getWorkshopsData", () => {
  it("rejects roots that do not look like Praxion projects", async () => {
    const root = await createTempProjectRoot("dashboard-workshops-invalid-");

    await expect(getWorkshopsData(root)).rejects.toThrow(/project root/i);
  });

  it("returns workshop cards in descending recency with canonical artifacts only", async () => {
    const root = await createTempProjectRoot("dashboard-workshops-valid-");
    const olderWorkshop = path.join(root, ".ai-work", "older-task");
    const newerWorkshop = path.join(root, ".ai-work", "newer-task");

    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(olderWorkshop, { recursive: true });
    await mkdir(newerWorkshop, { recursive: true });

    await writeFile(
      path.join(olderWorkshop, "WIP.md"),
      `
## Current Step

Review backlog

## Status

[WAITING]

## Progress

- [ ] Step alpha: Review backlog
`
    );
    await writeFile(
      path.join(newerWorkshop, "WIP.md"),
      `
## Current Step

Ship the server reader

## Status

[IN-PROGRESS]

## Progress

- [x] Step alpha: Earlier checkpoint
- [ ] Step beta: Ship the server reader
`
    );
    await writeFile(
      path.join(newerWorkshop, "PROGRESS.md"),
      "[2026-05-11T09:10:00Z] [implementer] Phase 2/6: [server-layer] -- Implemented workshop reader\n"
    );
    await writeFile(path.join(newerWorkshop, "IMPLEMENTATION_PLAN.md"), "# plan\n");
    await writeFile(path.join(newerWorkshop, "notes.txt"), "ignore me\n");
    await utimes(olderWorkshop, new Date("2026-05-10T09:00:00Z"), new Date("2026-05-10T09:00:00Z"));
    await utimes(newerWorkshop, new Date("2026-05-11T09:00:00Z"), new Date("2026-05-11T09:00:00Z"));

    const workshops = await getWorkshopsData(root);

    expect(workshops.map((workshop) => path.basename(workshop.path))).toEqual([
      "newer-task",
      "older-task"
    ]);
    expect(workshops[0]?.artifacts.map((artifact) => artifact.name)).toEqual([
      "IMPLEMENTATION_PLAN.md",
      "WIP.md",
      "PROGRESS.md"
    ]);
    expect(workshops[0]?.status).toContain("[IN-PROGRESS]");
    expect(workshops[0]?.events).toHaveLength(1);
  });

  it("reads canonical artifact contents with an extension-derived render mode", async () => {
    const root = await createTempProjectRoot("dashboard-workshops-artifacts-");
    const workshop = path.join(root, ".ai-work", "content-task");

    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(workshop, { recursive: true });
    await writeFile(path.join(workshop, "IMPLEMENTATION_PLAN.md"), "# plan\n\nDetails.\n");
    await writeFile(path.join(workshop, "traceability.yml"), "req-01: covered\n");

    const workshops = await getWorkshopsData(root);
    const artifacts = workshops[0]?.artifacts ?? [];

    const plan = artifacts.find((artifact) => artifact.name === "IMPLEMENTATION_PLAN.md");
    expect(plan?.body).toBe("# plan\n\nDetails.\n");
    expect(plan?.renderMode).toBe("markdown");

    const trace = artifacts.find((artifact) => artifact.name === "traceability.yml");
    expect(trace?.body).toBe("req-01: covered\n");
    expect(trace?.renderMode).toBe("code");
  });

  it("marks a workshop done when VERIFICATION_REPORT.md is present", async () => {
    const root = await createTempProjectRoot("dashboard-workshops-done-report-");
    const workshop = path.join(root, ".ai-work", "finished-task");

    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(workshop, { recursive: true });
    await writeFile(path.join(workshop, "VERIFICATION_REPORT.md"), "# Verification\n\nAll green.\n");

    const workshops = await getWorkshopsData(root);

    expect(workshops[0]?.isDone).toBe(true);
  });

  it("marks a workshop done when PROGRESS.md ends with a terminal phase", async () => {
    const root = await createTempProjectRoot("dashboard-workshops-done-progress-");
    const workshop = path.join(root, ".ai-work", "completed-task");

    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(workshop, { recursive: true });
    await writeFile(
      path.join(workshop, "PROGRESS.md"),
      [
        "[2026-05-11T09:00:00Z] [implementer] Phase 1/6: [understand-scope] -- Read the files",
        "[2026-05-11T10:00:00Z] [implementer] Phase 6/6: [report] -- Step complete",
        ""
      ].join("\n")
    );

    const workshops = await getWorkshopsData(root);

    expect(workshops[0]?.isDone).toBe(true);
  });

  it("does not mark a workshop done when neither VERIFICATION_REPORT nor terminal phase exists", async () => {
    const root = await createTempProjectRoot("dashboard-workshops-active-");
    const workshop = path.join(root, ".ai-work", "active-task");

    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    await mkdir(workshop, { recursive: true });
    await writeFile(
      path.join(workshop, "PROGRESS.md"),
      "[2026-05-11T09:00:00Z] [implementer] Phase 2/6: [implement] -- Writing code\n"
    );

    const workshops = await getWorkshopsData(root);

    expect(workshops[0]?.isDone).toBe(false);
  });
});
