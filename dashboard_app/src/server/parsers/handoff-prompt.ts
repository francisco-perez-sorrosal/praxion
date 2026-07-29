import "server-only";

const H1_TITLE = /^#\s+(.+)$/m;
const H1_KNOWN_PREFIX = /^(WIP|Task Brief):\s*/i;
const H2_HEADING = /^##\s+(.+)$/;
const CHECKLIST_ITEM = /^\s*-\s*\[[xX ]\]\s*(.+)$/;
const BULLET_ITEM = /^\s*-\s*(.+)$/;

/** Lines belonging to every `## <heading>` section matched by `isMatch` (concatenated, in document order). */
function extractSection(body: string, isMatch: (heading: string) => boolean): string[] {
  const lines: string[] = [];
  let inSection = false;

  for (const rawLine of body.split("\n")) {
    const heading = H2_HEADING.exec(rawLine.trim());
    if (heading?.[1]) {
      inSection = isMatch(heading[1].toLowerCase());
      continue;
    }
    if (inSection) {
      lines.push(rawLine);
    }
  }

  return lines;
}

/** First-level heading title, with the "WIP: " / "Task Brief: " prefix stripped. */
export function extractH1Title(body: string): string | null {
  const title = H1_TITLE.exec(body)?.[1];
  return title ? title.replace(H1_KNOWN_PREFIX, "").trim() : null;
}

/**
 * The intent prose from TASK_BRIEF.md, collapsed to one line. Matches both
 * the documented `## Task Intent` heading (goal-disambiguation's canonical
 * shape) and the shorter `## Intent` heading real TASK_BRIEF.md files use in
 * practice — confirmed by tracing this repo's own `.ai-work/` output.
 */
export function extractTaskIntent(body: string): string | null {
  const lines = extractSection(body, (heading) => heading.includes("intent"))
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  return lines.length > 0 ? lines.join(" ") : null;
}

/** Checklist item labels under `## Key Signals` in TASK_BRIEF.md. */
export function extractKeySignals(body: string): string[] {
  return extractSection(body, (heading) => heading.includes("key signals"))
    .map((line) => CHECKLIST_ITEM.exec(line)?.[1]?.trim())
    .filter((label): label is string => Boolean(label));
}

/** Bullet entries under `## Assumptions & Constraints Taken` in LEARNINGS.md. */
export function extractAssumptions(body: string): string[] {
  return extractSection(
    body,
    (heading) => heading.includes("assumptions") && heading.includes("constraints")
  )
    .map((line) => BULLET_ITEM.exec(line)?.[1]?.trim())
    .filter((label): label is string => Boolean(label));
}
