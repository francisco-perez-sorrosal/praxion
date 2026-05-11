import path from "node:path";

export type DashboardConfig = {
  dashboardVersion: string;
  pollIntervalSeconds: number;
  projectName: string;
  projectRoot: string;
};

const DEFAULT_POLL_SECONDS = 15;
const MIN_POLL_SECONDS = 1;
const MAX_POLL_SECONDS = 300;
const FALLBACK_PROJECT_ROOT = "/praxion-project";

function clampPollSeconds(value: number): number {
  return Math.min(MAX_POLL_SECONDS, Math.max(MIN_POLL_SECONDS, value));
}

function readPollSeconds(): number {
  const raw = process.env.PRAXION_DASHBOARD_POLL_SECONDS?.trim();
  if (!raw) {
    return DEFAULT_POLL_SECONDS;
  }

  const parsed = Number.parseInt(raw, 10);
  if (Number.isNaN(parsed)) {
    return DEFAULT_POLL_SECONDS;
  }

  return clampPollSeconds(parsed);
}

function readProjectRoot(): string | null {
  const projectRoot = process.env.PRAXION_PROJECT_ROOT?.trim() ?? "";
  if (!projectRoot) {
    return null;
  }

  if (!path.isAbsolute(projectRoot)) {
    throw new Error("PRAXION_PROJECT_ROOT must be an absolute path.");
  }

  return path.resolve(projectRoot);
}

function buildConfig(projectRoot: string): DashboardConfig {
  return {
    dashboardVersion: "0.1.0",
    pollIntervalSeconds: readPollSeconds(),
    projectName: path.basename(projectRoot),
    projectRoot
  };
}

export function getConfig(): DashboardConfig {
  const projectRoot = readProjectRoot();
  if (projectRoot === null) {
    throw new Error("PRAXION_PROJECT_ROOT is required.");
  }

  return buildConfig(projectRoot);
}

export function getShellConfig(): DashboardConfig {
  return buildConfig(readProjectRoot() ?? FALLBACK_PROJECT_ROOT);
}
