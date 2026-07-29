import "server-only";

import type { WorkshopEvent, WorkshopProgressItem } from "@/server/types";

const CHECKLIST_LINE =
  /^\s*-\s+\[([xX ])\]\s+Step\s+(\S+?):\s+(.+?)(?:\s+\[[A-Z_]+\])?\s*$/;
const CHECKLIST_LINE_BARE = /^\s*-\s*\[([xX ])\]\s+(\d+)\.\s+(.+)$/i;
const EVENT_LINE =
  /^\[([^\]]+)\]\s+\[([^\]]+)\]\s+Phase\s+(\S+):\s+(?:\[[^\]]+\]\s+--\s+)?(.+)$/;

export function parseWipBody(body: string): {
  currentStep: string | null;
  nextAction: string | null;
  progress: WorkshopProgressItem[];
  status: string | null;
} {
  let currentStep: string | null = null;
  let status: string | null = null;
  let nextAction: string | null = null;
  const progress: WorkshopProgressItem[] = [];
  let section = "";

  for (const rawLine of body.split("\n")) {
    const line = rawLine.trim();
    if (line.startsWith("## ")) {
      const heading = line.slice(3).toLowerCase();
      if (heading.includes("current step") || heading.includes("current batch")) {
        section = "current";
      } else if (heading.includes("next action")) {
        section = "next-action";
      } else if (heading.includes("status")) {
        section = "status";
      } else if (heading.includes("progress")) {
        section = "progress";
      } else {
        section = "";
      }
      continue;
    }

    if (!line) {
      continue;
    }

    if (section === "current" && currentStep === null) {
      currentStep = line.replaceAll("*", "").trim();
      continue;
    }

    if (section === "status" && status === null) {
      status = line.replaceAll("*", "").trim();
      continue;
    }

    if (section === "next-action" && nextAction === null) {
      nextAction = line.replaceAll("*", "").trim();
      continue;
    }

    if (section !== "progress") {
      continue;
    }

    const match = CHECKLIST_LINE.exec(rawLine) ?? CHECKLIST_LINE_BARE.exec(rawLine);
    if (!match) {
      continue;
    }

    const checkMark = match[1] ?? " ";
    const stepId = match[2] ?? "";
    const label = match[3] ?? "";
    const checked = checkMark.toLowerCase() === "x";
    progress.push({
      checked,
      current: !checked && currentStep !== null && rawLine.includes(currentStep),
      label: label.trim(),
      stepId: stepId.trim()
    });
  }

  return { currentStep, nextAction, progress, status };
}

export function parseProgressBody(body: string): WorkshopEvent[] {
  return body
    .split("\n")
    .map((line) => EVENT_LINE.exec(line))
    .filter((match): match is RegExpExecArray => Boolean(match))
    .map((match) => ({
      agent: match[2] ?? "",
      phase: match[3] ?? "",
      summary: match[4] ?? "",
      timestamp: match[1] ?? ""
    }));
}
