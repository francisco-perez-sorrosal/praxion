import { describe, expect, it } from "vitest";

import {
  gradeChipVariant,
  gradeTone,
  healthLabelTone,
  newestOf,
  normalizeGrade,
  relativeAge,
  verdictTone
} from "@/lib/tone";

const NOW = new Date("2026-10-03T12:00:00Z");

describe("grade mapping", () => {
  it.each([
    ["A", "good"],
    ["b", "info"],
    ["C", "warn"],
    ["D", "bad"],
    ["f", "bad"]
  ])("maps grade %s to the %s tone regardless of case", (grade, tone) => {
    expect(gradeTone(grade)).toBe(tone);
  });

  it("treats an unknown or missing grade as neutral", () => {
    expect(gradeTone("Z")).toBe("neutral");
    expect(gradeTone(null)).toBe("neutral");
    expect(gradeTone(undefined)).toBe("neutral");
  });

  it("gives F its own chip variant instead of folding it into D", () => {
    expect(gradeChipVariant("F")).toBe("grade-f");
    expect(gradeChipVariant("D")).toBe("grade-d");
    expect(gradeChipVariant("?")).toBe("neutral");
  });

  it("normalizes whitespace and case to a letter", () => {
    expect(normalizeGrade(" c ")).toBe("C");
    expect(normalizeGrade("")).toBeNull();
  });
});

describe("health and verdict mapping", () => {
  it("maps each health word to a tone", () => {
    expect(healthLabelTone("IMPROVING")).toBe("good");
    expect(healthLabelTone("STABLE")).toBe("neutral");
    expect(healthLabelTone("WORSENING")).toBe("bad");
    expect(healthLabelTone("BASELINE CAPTURED")).toBe("info");
    expect(healthLabelTone(null)).toBe("neutral");
  });

  it("maps verdict words to tones case-insensitively", () => {
    expect(verdictTone("PASS")).toBe("good");
    expect(verdictTone("warn")).toBe("warn");
    expect(verdictTone("Fail")).toBe("bad");
    expect(verdictTone("SKIP")).toBe("neutral");
    expect(verdictTone("other")).toBe("neutral");
  });
});

describe("relative age", () => {
  it.each([
    ["2026-10-03T11:59:40Z", "just now"],
    ["2026-10-03T11:55:00Z", "5 min ago"],
    ["2026-10-03T09:00:00Z", "3 h ago"],
    ["2026-09-21T12:00:00Z", "12 d ago"],
    ["2026-06-01T12:00:00Z", "4 mo ago"]
  ])("renders %s as %s", (stamp, expected) => {
    expect(relativeAge(stamp, NOW)).toBe(expected);
  });

  it("reads a future stamp as just now rather than a negative age", () => {
    expect(relativeAge("2026-10-04T12:00:00Z", NOW)).toBe("just now");
  });

  it("returns null for an unparseable or missing stamp", () => {
    expect(relativeAge("not a date", NOW)).toBeNull();
    expect(relativeAge(null, NOW)).toBeNull();
  });
});

describe("date helpers", () => {
  it("picks the newest parseable stamp and ignores the rest", () => {
    expect(newestOf(["2026-01-01T00:00:00Z", null, "bad", "2026-10-01T00:00:00Z"])).toBe(
      "2026-10-01T00:00:00.000Z"
    );
    expect(newestOf([null, undefined, "bad"])).toBeNull();
  });
});
