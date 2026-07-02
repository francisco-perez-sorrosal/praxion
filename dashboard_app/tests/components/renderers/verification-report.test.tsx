// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { VerificationReportRenderer } from "@/components/renderers/verification-report";

afterEach(() => {
  cleanup();
});

// VERIFICATION_REPORT.md-shaped markdown carrying the report's own verdict
// vocabulary (PASS / FAIL / WARN).
const PASS_BODY = `# Verification Report

## Verdict

PASS

## Findings

- No blocking findings.
`;

const FAIL_BODY = `# Verification Report

## Verdict

FAIL

## Findings

- Acceptance criterion not met.
`;

const WARN_BODY = `# Verification Report

## Verdict

WARN

## Findings

- Minor documentation gap.
`;

const NO_VERDICT_BODY = "A report body with no recognizable verdict token.";

describe("VerificationReportRenderer — verdict badge", () => {
  it("surfaces a PASS verdict as visible badge text", () => {
    const { container } = render(<VerificationReportRenderer body={PASS_BODY} />);

    expect(container.querySelector(".renderer-verification")).toBeTruthy();
    const badge = container.querySelector(".renderer-verification-verdict");
    expect(badge).toBeTruthy();
    expect(badge?.textContent).toMatch(/PASS/);
  });

  it("surfaces a FAIL verdict as visible badge text", () => {
    const { container } = render(<VerificationReportRenderer body={FAIL_BODY} />);

    const badge = container.querySelector(".renderer-verification-verdict");
    expect(badge).toBeTruthy();
    expect(badge?.textContent).toMatch(/FAIL/);
  });

  it("surfaces a WARN verdict as visible badge text", () => {
    const { container } = render(<VerificationReportRenderer body={WARN_BODY} />);

    const badge = container.querySelector(".renderer-verification-verdict");
    expect(badge).toBeTruthy();
    expect(badge?.textContent).toMatch(/WARN/);
  });

  it("falls back to the default shell when no PASS/FAIL/WARN verdict is recognizable", () => {
    const { container } = render(
      <VerificationReportRenderer body={NO_VERDICT_BODY} />
    );

    expect(container.querySelector(".shell-default")).toBeTruthy();
    expect(container.querySelector(".renderer-verification")).toBeFalsy();
  });
});
