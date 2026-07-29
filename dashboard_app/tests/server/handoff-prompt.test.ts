import { describe, expect, it } from "vitest";

import {
  extractAssumptions,
  extractH1Title,
  extractKeySignals,
  extractTaskIntent
} from "@/server/parsers/handoff-prompt";
import { composeHandoffPrompt } from "@/server/view-models/handoff-prompt";

const WIP_BODY = `
# WIP: Label taxonomy manifest

## Current Step

Step 3 of 5: Wire the reconciler into CI

## Status

[IN-PROGRESS] - writing the reconciler tests

## Progress

- [x] Step 1: Scaffold the manifest schema
- [x] Step 2: Write the reconciler
- [ ] Step 3: Wire the reconciler into CI
- [ ] Step 4: Document the manifest
- [ ] Step 5: Ship

## Next Action

Run the reconciler against the fixture repo and confirm no drift.
`;

const TASK_BRIEF_BODY = `
# Task Brief: Label taxonomy manifest

## Task Intent

Give each project an owned label taxonomy manifest so labels stop drifting
between repos.

## Key Signals

- [ ] The reconciler reports zero drift on a freshly onboarded project
- [ ] Existing labels are preserved when the manifest is applied
`;

const LEARNINGS_BODY = `
# Learnings: Label taxonomy manifest

## Assumptions & Constraints Taken
- **[implementer] Manifest format**: Using YAML to match the rest of \`.ai-state/\`.
- **[implementer] No renames**: Never renaming a label that already has open issues attached.
`;

describe("handoff-prompt parsers", () => {
  it("extracts the H1 title with a known WIP/Task Brief prefix stripped", () => {
    expect(extractH1Title(WIP_BODY)).toBe("Label taxonomy manifest");
    expect(extractH1Title(TASK_BRIEF_BODY)).toBe("Label taxonomy manifest");
  });

  it("returns null when no H1 heading is present", () => {
    expect(extractH1Title("## Current Step\n\nSomething")).toBeNull();
  });

  it("extracts the Task Intent prose collapsed to one line", () => {
    expect(extractTaskIntent(TASK_BRIEF_BODY)).toBe(
      "Give each project an owned label taxonomy manifest so labels stop drifting between repos."
    );
  });

  it("extracts intent from the shorter '## Intent' heading real TASK_BRIEF.md files use", () => {
    const shortHeadingBody = `
# Task Brief: Example

## Intent

Fix the thing properly.

## Key Signals

- [ ] It stays fixed
`;
    expect(extractTaskIntent(shortHeadingBody)).toBe("Fix the thing properly.");
  });

  it("extracts Key Signals checklist labels", () => {
    expect(extractKeySignals(TASK_BRIEF_BODY)).toEqual([
      "The reconciler reports zero drift on a freshly onboarded project",
      "Existing labels are preserved when the manifest is applied"
    ]);
  });

  it("extracts Assumptions & Constraints Taken bullets", () => {
    expect(extractAssumptions(LEARNINGS_BODY)).toEqual([
      "**[implementer] Manifest format**: Using YAML to match the rest of `.ai-state/`.",
      "**[implementer] No renames**: Never renaming a label that already has open issues attached."
    ]);
  });
});

describe("composeHandoffPrompt", () => {
  it("returns null when there is no WIP.md to resume from", () => {
    const prompt = composeHandoffPrompt({
      learningsBody: LEARNINGS_BODY,
      taskBriefBody: TASK_BRIEF_BODY,
      taskSlug: "label-taxonomy-manifest",
      wipBody: null
    });

    expect(prompt).toBeNull();
  });

  it("composes every field when all three sources are present", () => {
    const prompt = composeHandoffPrompt({
      learningsBody: LEARNINGS_BODY,
      taskBriefBody: TASK_BRIEF_BODY,
      taskSlug: "label-taxonomy-manifest",
      wipBody: WIP_BODY
    });

    expect(prompt).toContain(
      "Resume Label taxonomy manifest (task slug: label-taxonomy-manifest)"
    );
    expect(prompt).toContain("read `.ai-work/label-taxonomy-manifest/WIP.md`");
    expect(prompt).toContain(
      "**Goal**: Give each project an owned label taxonomy manifest so labels stop drifting between repos."
    );
    expect(prompt).toContain(
      "**Where it stands**: Step 2 of 5 complete. Current step: Step 3 of 5: Wire the reconciler into CI ([IN-PROGRESS] - writing the reconciler tests)."
    );
    expect(prompt).toContain("**Constraints already decided**");
    expect(prompt).toContain("Manifest format");
    expect(prompt).toContain(
      "**Next action**: Run the reconciler against the fixture repo and confirm no drift."
    );
    expect(prompt).toContain("**Verify it worked by**");
    expect(prompt).toContain("The reconciler reports zero drift on a freshly onboarded project");
  });

  it("omits Goal and Verify-it-worked-by when TASK_BRIEF.md is absent, without fabricating content", () => {
    const prompt = composeHandoffPrompt({
      learningsBody: LEARNINGS_BODY,
      taskBriefBody: null,
      taskSlug: "label-taxonomy-manifest",
      wipBody: WIP_BODY
    });

    expect(prompt).not.toBeNull();
    expect(prompt).not.toContain("**Goal**");
    expect(prompt).not.toContain("**Verify it worked by**");
    expect(prompt).toContain("**Where it stands**");
    expect(prompt).toContain("**Next action**");
  });

  it("omits Constraints when LEARNINGS.md is absent", () => {
    const prompt = composeHandoffPrompt({
      learningsBody: null,
      taskBriefBody: TASK_BRIEF_BODY,
      taskSlug: "label-taxonomy-manifest",
      wipBody: WIP_BODY
    });

    expect(prompt).not.toBeNull();
    expect(prompt).not.toContain("**Constraints already decided**");
  });
});
