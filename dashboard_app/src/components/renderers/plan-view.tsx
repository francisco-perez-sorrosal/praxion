import { MarkdownSurface } from "@/components/markdown-surface";
import { DefaultShell } from "@/components/shells";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

type PlanStep = {
  readonly checked: boolean;
  readonly key: string;
  readonly label: string;
};

const TASK_ITEM_RE = /^\s*-\s*\[([ xX])\]\s*(.+)$/;
const HEADING_RE = /^#{2,3}\s+(.+)$/;

function extractTaskSteps(body: string): PlanStep[] {
  const steps: PlanStep[] = [];
  body.split("\n").forEach((line, index) => {
    const match = TASK_ITEM_RE.exec(line);
    if (match === null) {
      return;
    }
    const [, marker, label] = match;
    steps.push({
      checked: marker?.toLowerCase() === "x",
      key: `task-${index}`,
      label: (label ?? "").trim()
    });
  });
  return steps;
}

function extractHeadingSteps(body: string): PlanStep[] {
  const steps: PlanStep[] = [];
  body.split("\n").forEach((line, index) => {
    const match = HEADING_RE.exec(line);
    if (match === null) {
      return;
    }
    steps.push({ checked: false, key: `heading-${index}`, label: (match[1] ?? "").trim() });
  });
  return steps;
}

/**
 * Derives a step-progress overview from GFM task-list items when present
 * (checkbox state reflects [x] / [ ]); falls back to H2/H3 headings — which
 * carry no completion state of their own — when the body has no task items.
 */
function derivePlanSteps(body: string): PlanStep[] {
  const taskSteps = extractTaskSteps(body);
  if (taskSteps.length > 0) {
    return taskSteps;
  }
  return extractHeadingSteps(body);
}

/** Thin Pathway-B preview of a plan/progress document's step-completion state. */
export function PlanViewRenderer({ body }: RendererProps) {
  const steps = derivePlanSteps(body);
  if (steps.length === 0) {
    return <DefaultShell body={body} />;
  }

  return (
    <div className="renderer-plan">
      <p className="renderer-plan-heading">Implementation plan</p>
      <ul className="renderer-plan-steps">
        {steps.map((step) => (
          <li key={step.key}>
            <input checked={step.checked} disabled type="checkbox" />
            <span>{step.label}</span>
          </li>
        ))}
      </ul>
      <div className="renderer-plan-body">
        <MarkdownSurface body={body} />
      </div>
    </div>
  );
}
