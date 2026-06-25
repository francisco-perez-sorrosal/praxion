import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

const FINALIZED_ADR = /^\d{3}-[a-z0-9-]+\.md$/;
const METRICS_REPORT_JSON = /^METRICS_REPORT_\d{4}-\d{2}-\d{2}(?:_\d{2}-\d{2}-\d{2})?\.json$/;
const SENTINEL_REPORT = /^SENTINEL_REPORT_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.md$/;

// Source of truth: the `dashboard` set in scripts/artifact_registry.py; drift
// from the registry (or from build_doc_manifest._AI_WORK_FILES) fails
// scripts/test_artifact_registry.py. Ordered by pipeline flow.
export const CANONICAL_WORKSHOP_ARTIFACTS: string[] = [
  "TASK_BRIEF.md",
  "IDEA_PROPOSAL.md",
  "RESEARCH_FINDINGS.md",
  "CONTEXT_REVIEW.md",
  "INTERFACE_DESIGN.md",
  "TRANSACTIONS_DESIGN.md",
  "SYSTEMS_PLAN.md",
  "PRE_REFACTOR_PLAN.md",
  "SPEC_DELTA.md",
  "IMPLEMENTATION_PLAN.md",
  "WIP.md",
  "LEARNINGS.md",
  "TEST_BASELINE.md",
  "TEST_RESULTS.md",
  "traceability.yml",
  "VERIFICATION_REPORT.md",
  "REWORK_MANIFEST.md",
  "PROGRESS.md",
  "RECOVERY_LOG.md"
] as const;

export async function pathExists(target: string): Promise<boolean> {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

export async function isDirectory(target: string): Promise<boolean> {
  try {
    return (await fs.stat(target)).isDirectory();
  } catch {
    return false;
  }
}

export async function listDirectory(target: string): Promise<string[]> {
  if (!(await isDirectory(target))) {
    return [];
  }

  const entries = await fs.readdir(target);
  return entries.sort((left, right) => left.localeCompare(right));
}

export async function listDirectoryByMtimeDesc(target: string): Promise<string[]> {
  if (!(await isDirectory(target))) {
    return [];
  }

  // Returns only subdirectories (not files) — by design for workshop discovery.
  const withStats = await Promise.all(
    (await fs.readdir(target)).map(async (entry) => {
      const entryPath = path.join(target, entry);
      return { entry, stat: await fs.stat(entryPath) };
    })
  );

  return withStats
    .filter((entry) => entry.stat.isDirectory())
    .sort((left, right) => right.stat.mtimeMs - left.stat.mtimeMs)
    .map((entry) => entry.entry);
}

export async function readText(target: string): Promise<string | null> {
  try {
    return await fs.readFile(target, "utf8");
  } catch {
    return null;
  }
}

// Diagram root directories to scan for rendered SVGs, relative to the project root.
// Scans both docs/diagrams/ (convention-docs diagrams) and .ai-state/diagrams/
// (architecture-as-code / DESIGN.md diagrams).
const DIAGRAM_ROOTS = ["docs/diagrams", ".ai-state/diagrams"] as const;

async function walkRenderedSvgsInRoot(diagramsRoot: string): Promise<string[]> {
  if (!(await isDirectory(diagramsRoot))) {
    return [];
  }

  const pending = [diagramsRoot];
  const results: string[] = [];

  while (pending.length > 0) {
    const current = pending.pop() as string;
    for (const entry of await fs.readdir(current, { withFileTypes: true })) {
      const entryPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(entryPath);
        continue;
      }

      if (
        entry.isFile() &&
        entry.name.endsWith(".svg") &&
        entryPath.includes(`${path.sep}rendered${path.sep}`)
      ) {
        results.push(entryPath);
      }
    }
  }

  return results;
}

export async function walkRenderedSvgs(projectRoot: string): Promise<string[]> {
  const allResults = await Promise.all(
    DIAGRAM_ROOTS.map((relRoot) => walkRenderedSvgsInRoot(path.join(projectRoot, relRoot)))
  );

  const combined = allResults.flat();
  return combined.sort((left, right) => left.localeCompare(right));
}

export function isFinalizedAdr(filename: string): boolean {
  return FINALIZED_ADR.test(filename);
}

export function isMetricsReportJson(filename: string): boolean {
  return METRICS_REPORT_JSON.test(filename);
}

export function isSentinelReport(filename: string): boolean {
  return SENTINEL_REPORT.test(filename);
}
