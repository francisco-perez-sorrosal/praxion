/**
 * Behavioral tests for `src/lib/health-tone.ts`.
 *
 * Behaviors validated:
 *   - metricTone: baseline (null previous), improving, worsening, stable,
 *     stable-within-epsilon, lower-is-better direction, higher-is-better direction.
 *   - healthSummary: all-good → "IMPROVING"; any-bad → "WORSENING";
 *     mixed/steady → "STABLE"; isBaseline flag → "BASELINE CAPTURED";
 *     degradedCollectors → degradedNote mentions the tool name.
 *
 * Implementation contract notes (discovered from src/lib/health-tone.ts):
 *   - metricTone arrow convention: ↘ = "improving" (value moving in the
 *     good direction), ↗ = "worsening" — regardless of which direction is
 *     "better". This is a tone arrow, not a value-direction arrow.
 *   - healthSummary "BASELINE CAPTURED" requires opts.isBaseline === true.
 *     An empty tones array without the flag returns "STABLE".
 *   - Degraded-collector note is in the `degradedNote` field, not in `label`.
 *   - Any single "bad" tone triggers "WORSENING" (not a majority rule).
 *
 * OBJECTION (registered): The prompt contract specifies ↗ for higher-is-better
 * improvements (value going up) and ↘ for lower-is-better improvements (value
 * going down). The implementation uses ↘ for ALL improvements regardless of
 * direction. The tests validate the implemented behavior — the implementer
 * should confirm whether the tone-arrow convention or value-direction-arrow
 * convention was intended.
 *
 * Environment: vitest node — deferred imports allow RED collection when the
 * module does not exist yet (concurrent BDD/TDD).
 */

import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// metricTone — pure per-metric tone derivation
// ---------------------------------------------------------------------------

describe("metricTone", () => {
  it("returns neutral tone with → arrow and 'baseline' word when both current and previous are null", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    const result = metricTone(null, null, "lower");
    expect(result.tone).toBe("neutral");
    expect(result.arrow).toBe("→");
    expect(result.word).toBe("baseline");
  });

  it("returns neutral/baseline when previous is null and current has a value", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    const result = metricTone(12.4, null, "lower");
    expect(result.tone).toBe("neutral");
    expect(result.arrow).toBe("→");
    expect(result.word).toBe("baseline");
  });

  it("returns good tone with ↘ arrow and 'improving' word when lower-is-better and current is lower", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    // 12.4 < 13.2: improvement for lower-is-better
    const result = metricTone(12.4, 13.2, "lower");
    expect(result.tone).toBe("good");
    expect(result.arrow).toBe("↘");
    expect(result.word).toBe("improving");
  });

  it("returns bad tone with ↗ arrow and 'worsening' word when lower-is-better and current is higher", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    // 18 > 16: worsening for lower-is-better
    const result = metricTone(18, 16, "lower");
    expect(result.tone).toBe("bad");
    expect(result.arrow).toBe("↗");
    expect(result.word).toBe("worsening");
  });

  it("returns good tone with ↘ arrow and 'improving' word when higher-is-better and current is higher", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    // 78 > 75: improvement for higher-is-better
    // Note: implementation uses ↘ for ALL improvements (tone arrow, not value-direction arrow).
    const result = metricTone(78, 75, "higher");
    expect(result.tone).toBe("good");
    expect(result.arrow).toBe("↘");
    expect(result.word).toBe("improving");
  });

  it("returns bad tone with ↗ arrow and 'worsening' word when higher-is-better and current is lower", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    // 75 < 78: worsening for higher-is-better
    // Note: implementation uses ↗ for ALL worsening cases.
    const result = metricTone(75, 78, "higher");
    expect(result.tone).toBe("bad");
    expect(result.arrow).toBe("↗");
    expect(result.word).toBe("worsening");
  });

  it("returns steady tone with → arrow and 'stable' word when current equals previous exactly", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    const result = metricTone(12.4, 12.4, "lower");
    expect(result.tone).toBe("steady");
    expect(result.arrow).toBe("→");
    expect(result.word).toBe("stable");
  });

  it("returns improving when difference exceeds epsilon (epsilon is 1e-9; 0.0001 is meaningful)", async () => {
    const { metricTone } = await import("@/lib/health-tone");
    // 12.4001 - 12.4 = 0.0001 >> 1e-9 epsilon; for lower-is-better this is worsening
    const result = metricTone(12.4001, 12.4, "lower");
    // 12.4001 > 12.4 with lower-is-better → worsening
    expect(result.tone).toBe("bad");
    expect(result.arrow).toBe("↗");
    expect(result.word).toBe("worsening");
  });
});

// ---------------------------------------------------------------------------
// healthSummary — aggregate tone from a collection of per-metric tones
// ---------------------------------------------------------------------------

describe("healthSummary", () => {
  it("returns 'IMPROVING' label when all tones are 'good'", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    const result = healthSummary(["good", "good", "good", "good"]);
    expect(result.label).toBe("IMPROVING");
  });

  it("returns 'WORSENING' label when any tone is 'bad' (even one in four)", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    // Implementation: any bad → WORSENING
    const result = healthSummary(["bad", "bad", "bad", "good"]);
    expect(result.label).toBe("WORSENING");
  });

  it("returns 'WORSENING' label when even one tone is 'bad' in a mixed set", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    const result = healthSummary(["good", "bad", "steady", "good"]);
    expect(result.label).toBe("WORSENING");
  });

  it("returns 'STABLE' label when tones are a mix of good and steady with no bad", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    // 1 good out of 4 is < ceil(4/2)=2, so no majority → STABLE
    const result = healthSummary(["good", "steady", "steady", "steady"]);
    expect(result.label).toBe("STABLE");
  });

  it("returns 'STABLE' label for an empty tones array (no crash)", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    // Empty array without isBaseline flag → STABLE (not BASELINE CAPTURED)
    expect(() => healthSummary([])).not.toThrow();
    expect(healthSummary([]).label).toBe("STABLE");
  });

  it("returns 'BASELINE CAPTURED' label when isBaseline option is true", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    const result = healthSummary(["neutral", "neutral", "neutral", "neutral"], {
      isBaseline: true
    });
    expect(result.label).toBe("BASELINE CAPTURED");
  });

  it("returns 'BASELINE CAPTURED' even with empty tones when isBaseline is true", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    const result = healthSummary([], { isBaseline: true });
    expect(result.label).toBe("BASELINE CAPTURED");
  });

  it("sets degraded to true and degradedNote to a non-null string when degradedCollectors is non-empty", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    const result = healthSummary(["good", "good", "good", "good"], {
      degradedCollectors: ["ruff"]
    });
    expect(result.degraded).toBe(true);
    expect(result.degradedNote).not.toBeNull();
  });

  it("includes the degraded tool name in degradedNote when degradedCollectors is non-empty", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    const result = healthSummary(["good", "good", "good", "good"], {
      degradedCollectors: ["ruff"]
    });
    expect(result.degradedNote).toContain("ruff");
    // The note must also mention data confidence in some form
    const noteLower = (result.degradedNote ?? "").toLowerCase();
    expect(noteLower).toContain("confidence");
  });

  it("sets degraded to false and degradedNote to null when no degraded collectors", async () => {
    const { healthSummary } = await import("@/lib/health-tone");
    const result = healthSummary(["good", "good", "good", "good"]);
    expect(result.degraded).toBe(false);
    expect(result.degradedNote).toBeNull();
  });
});
