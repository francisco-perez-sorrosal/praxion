import "server-only";

import {
  extractAssumptions,
  extractH1Title,
  extractKeySignals,
  extractTaskIntent
} from "@/server/parsers/handoff-prompt";
import { parseWipBody } from "@/server/parsers/workshops";

export type HandoffPromptSources = {
  learningsBody: string | null;
  taskBriefBody: string | null;
  taskSlug: string;
  wipBody: string | null;
};

function formatWhereItStands(wip: ReturnType<typeof parseWipBody>): string {
  const parts: string[] = [];

  if (wip.progress.length > 0) {
    const completed = wip.progress.filter((item) => item.checked).length;
    parts.push(`Step ${completed} of ${wip.progress.length} complete.`);
  }

  const statusSuffix = wip.status ? ` (${wip.status})` : "";
  parts.push(`Current step: ${wip.currentStep ?? "unspecified"}${statusSuffix}.`);

  return parts.join(" ");
}

function resolveFeatureName(sources: HandoffPromptSources, wipBody: string): string {
  return (
    extractH1Title(wipBody) ??
    (sources.taskBriefBody ? extractH1Title(sources.taskBriefBody) : null) ??
    sources.taskSlug
  );
}

/**
 * Composes the "Resume work" handoff prompt (see
 * `skills/software-planning/references/document-templates.md` § Handoff
 * Prompt Structure) from a workshop's already-fetched artifact bodies —
 * no additional filesystem reads. Fields whose source artifact is absent
 * are omitted rather than fabricated. Returns `null` only when there is no
 * WIP.md to resume from.
 */
export function composeHandoffPrompt(sources: HandoffPromptSources): string | null {
  if (sources.wipBody === null) {
    return null;
  }

  const wip = parseWipBody(sources.wipBody);
  const featureName = resolveFeatureName(sources, sources.wipBody);

  const lines: string[] = [
    `Resume ${featureName} (task slug: ${sources.taskSlug}) — read ` +
      `\`.ai-work/${sources.taskSlug}/WIP.md\` and \`.ai-work/${sources.taskSlug}/LEARNINGS.md\` first.`,
    ""
  ];

  const intent = sources.taskBriefBody ? extractTaskIntent(sources.taskBriefBody) : null;
  if (intent) {
    lines.push(`**Goal**: ${intent}`, "");
  }

  lines.push(`**Where it stands**: ${formatWhereItStands(wip)}`, "");

  const assumptions = sources.learningsBody ? extractAssumptions(sources.learningsBody) : [];
  if (assumptions.length > 0) {
    lines.push(`**Constraints already decided** (don't re-litigate): ${assumptions.join("; ")}`, "");
  }

  if (wip.nextAction) {
    lines.push(`**Next action**: ${wip.nextAction}`, "");
  }

  const keySignals = sources.taskBriefBody ? extractKeySignals(sources.taskBriefBody) : [];
  if (keySignals.length > 0) {
    lines.push(`**Verify it worked by**: ${keySignals.join("; ")}`);
  }

  return lines.join("\n").trim();
}
