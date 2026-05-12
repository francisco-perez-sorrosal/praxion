import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

const REPO_ROOT = path.resolve(__dirname, "../../..");

function readFixture(relPath: string): string {
  return readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

// Real fixture files (committed to .ai-state)
const MERMAID_SVG = readFixture(
  ".ai-state/diagrams/adr-finalize-flow/rendered/adr-finalize-flow.svg"
);
const LIKEC4_SVG = readFixture(
  ".ai-state/diagrams/deployment-system-context/rendered/deployment-system-context.svg"
);

// ---------------------------------------------------------------------------
// normalizeSvg — deferred import so this file collects cleanly before the
// module under test exists (concurrent BDD/TDD RED handshake).
// ---------------------------------------------------------------------------

async function normalize(svg: string): Promise<string> {
  const mod = await import("@/server/diagrams/normalize-svg");
  return mod.normalizeSvg(svg);
}

// ---------------------------------------------------------------------------
// Measurable inputs
// ---------------------------------------------------------------------------

describe("normalizeSvg", () => {
  describe("measurable inputs", () => {
    it("strips root width and height attributes from a Mermaid SVG", async () => {
      const result = await normalize(MERMAID_SVG);

      // The root <svg> open-tag must not carry width= or height= as attrs
      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      expect(rootOpenTag).not.toMatch(/\bwidth=/);
      expect(rootOpenTag).not.toMatch(/\bheight=/);
    });

    it("strips max-width and background-color from the Mermaid SVG root style and drops the style attribute", async () => {
      const result = await normalize(MERMAID_SVG);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      // max-width and background-color were the only declarations — style attr should be gone
      expect(rootOpenTag).not.toMatch(/max-width/i);
      expect(rootOpenTag).not.toMatch(/background-color/i);
      expect(rootOpenTag).not.toMatch(/\bstyle=/);
    });

    it("adds preserveAspectRatio to a Mermaid SVG that lacked it", async () => {
      const result = await normalize(MERMAID_SVG);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      expect(rootOpenTag).toContain('preserveAspectRatio="xMidYMid meet"');
    });

    it("adds data-vb-w, data-vb-h, and data-aspect derived from the Mermaid SVG viewBox", async () => {
      // viewBox="-50 -10 1645.5 597" => vbW=1645.5, vbH=597
      const result = await normalize(MERMAID_SVG);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      expect(rootOpenTag).toContain('data-vb-w="1645.5"');
      expect(rootOpenTag).toContain('data-vb-h="597"');

      const aspectRaw = rootOpenTag.match(/data-aspect="([^"]+)"/)?.[1];
      expect(aspectRaw).toBeDefined();
      const aspect = parseFloat(aspectRaw ?? "0");
      // 1645.5 / 597 ≈ 2.7563
      expect(aspect).toBeCloseTo(1645.5 / 597, 3);
    });

    it("preserves the id attribute and viewBox on the root svg element", async () => {
      const result = await normalize(MERMAID_SVG);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      expect(rootOpenTag).toContain('id="my-svg"');
      expect(rootOpenTag).toContain('viewBox="-50 -10 1645.5 597"');
    });

    it("handles a style attribute that has other declarations besides targeted ones — preserves them and keeps the style attr", async () => {
      // Synthetic LikeC4-style SVG: style has max-width, background-color, AND display:block
      const svg = `<svg id="test" viewBox="0 0 800 400" style="max-width:800px; background-color: white; display: block;">
  <rect width="100" height="50"/>
</svg>`;
      const result = await normalize(svg);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      expect(rootOpenTag).not.toMatch(/max-width/i);
      expect(rootOpenTag).not.toMatch(/background-color/i);
      // display:block survives
      expect(rootOpenTag).toMatch(/display\s*:\s*block/);
      // style attr is kept (not dropped) because it still has content
      expect(rootOpenTag).toMatch(/\bstyle=/);
    });

    it("parses a comma-separated viewBox correctly", async () => {
      const svg = `<svg viewBox="0,0,800,400" xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="50"/>
</svg>`;
      const result = await normalize(svg);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      expect(rootOpenTag).toContain('data-vb-w="800"');
      expect(rootOpenTag).toContain('data-vb-h="400"');

      const aspectRaw = rootOpenTag.match(/data-aspect="([^"]+)"/)?.[1];
      expect(aspectRaw).toBeDefined();
      expect(parseFloat(aspectRaw ?? "0")).toBeCloseTo(2, 3);
    });

    it("falls back to width/height attrs when viewBox is absent", async () => {
      const svg = `<svg width="800" height="400" xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="50"/>
</svg>`;
      const result = await normalize(svg);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      // width/height attrs stripped
      expect(rootOpenTag).not.toMatch(/\bwidth=/);
      expect(rootOpenTag).not.toMatch(/\bheight=/);
      // derived from the removed attrs
      expect(rootOpenTag).toContain('data-vb-w="800"');
      expect(rootOpenTag).toContain('data-vb-h="400"');
      expect(parseFloat(rootOpenTag.match(/data-aspect="([^"]+)"/)?.[1] ?? "0")).toBeCloseTo(
        2,
        3
      );
    });

    it("handles an SVG with no style attribute — does not introduce a style attr", async () => {
      const svg = `<svg width="600" height="300" viewBox="0 0 600 300" xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="40"/>
</svg>`;
      const result = await normalize(svg);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      // No style attr should be added
      expect(rootOpenTag).not.toMatch(/\bstyle=/);
      expect(rootOpenTag).not.toMatch(/\bwidth=/);
      expect(rootOpenTag).not.toMatch(/\bheight=/);
      expect(rootOpenTag).toContain('data-aspect="2"');
    });

    it("handles a multi-line root svg open-tag (attrs spread across lines)", async () => {
      const svg =
        '<svg\n  id="multiline"\n  viewBox="0 0 400 200"\n  width="100%"\n  xmlns="http://www.w3.org/2000/svg"\n>\n  <rect width="50" height="25"/>\n</svg>';
      const result = await normalize(svg);

      const rootOpenTag = result.match(/<svg[\s\S]*?>/)?.[0] ?? "";
      expect(rootOpenTag).not.toMatch(/\bwidth=/);
      expect(rootOpenTag).toContain('data-vb-w="400"');
      expect(rootOpenTag).toContain('data-vb-h="200"');
      expect(parseFloat(rootOpenTag.match(/data-aspect="([^"]+)"/)?.[1] ?? "0")).toBeCloseTo(
        2,
        3
      );
    });

    it("does not overwrite preserveAspectRatio when already present", async () => {
      const svg = `<svg viewBox="0 0 100 50" preserveAspectRatio="xMinYMin slice" xmlns="http://www.w3.org/2000/svg">
  <rect width="50" height="25"/>
</svg>`;
      const result = await normalize(svg);

      const rootOpenTag = result.match(/<svg[^>]*>/)?.[0] ?? "";
      // The existing value must be preserved, not overwritten
      expect(rootOpenTag).toContain('preserveAspectRatio="xMinYMin slice"');
      expect(rootOpenTag).not.toContain("xMidYMid meet");
    });
  });

  // ---------------------------------------------------------------------------
  // Unmeasurable inputs
  // ---------------------------------------------------------------------------

  describe("unmeasurable inputs", () => {
    it("returns the input unchanged when there is no viewBox and no parseable width/height attrs", async () => {
      const svg = `<svg xmlns="http://www.w3.org/2000/svg">
  <rect width="100" height="50"/>
</svg>`;
      const result = await normalize(svg);

      expect(result).toBe(svg);
    });

    it("does not throw on an unmeasurable SVG", async () => {
      const svg = `<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>`;
      await expect(normalize(svg)).resolves.toBe(svg);
    });

    it("returns the input unchanged when viewBox has zero dimensions", async () => {
      const svg = `<svg viewBox="0 0 0 0" xmlns="http://www.w3.org/2000/svg">
  <rect width="10" height="10"/>
</svg>`;
      const result = await normalize(svg);

      expect(result).toBe(svg);
    });
  });

  // ---------------------------------------------------------------------------
  // Idempotency
  // ---------------------------------------------------------------------------

  describe("idempotency", () => {
    it("is idempotent on the real Mermaid SVG fixture", async () => {
      const once = await normalize(MERMAID_SVG);
      const twice = await normalize(once);

      expect(twice).toBe(once);
    });

    it("is idempotent on the LikeC4 SVG fixture", async () => {
      const once = await normalize(LIKEC4_SVG);
      const twice = await normalize(once);

      expect(twice).toBe(once);
    });

    it("is idempotent on a comma-separated viewBox SVG", async () => {
      const svg = `<svg viewBox="0,0,800,400" xmlns="http://www.w3.org/2000/svg"><rect/></svg>`;
      const once = await normalize(svg);
      const twice = await normalize(once);

      expect(twice).toBe(once);
    });

    it("is idempotent on a fallback width/height SVG", async () => {
      const svg = `<svg width="800" height="400" xmlns="http://www.w3.org/2000/svg"><rect/></svg>`;
      const once = await normalize(svg);
      const twice = await normalize(once);

      expect(twice).toBe(once);
    });

    it("reaches a fixed point on an already-normalized SVG (f(f(x)) === f(x))", async () => {
      // Functional idempotency: running normalize on output of normalize changes nothing further.
      // This is the f(f(x))===f(x) property — not necessarily f(x)===x for a hand-authored string.
      const svg = `<svg viewBox="0 0 400 200" xmlns="http://www.w3.org/2000/svg">
  <rect width="50" height="25"/>
</svg>`;
      const once = await normalize(svg);
      const twice = await normalize(once);

      expect(twice).toBe(once);
    });
  });

  // ---------------------------------------------------------------------------
  // Scope: root element only
  // ---------------------------------------------------------------------------

  describe("scope (root element only)", () => {
    it("does not touch width attr on a nested svg element", async () => {
      const svg = `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <svg viewBox="0 0 10 10" width="10" height="10"/>
</svg>`;
      const result = await normalize(svg);

      // Outer svg: width/height stripped (it had none, so no change here)
      // Inner svg: width="10" and height="10" must be preserved byte-for-byte
      expect(result).toContain('<svg viewBox="0 0 10 10" width="10" height="10"/>');
    });

    it("does not touch max-width inside an inner style block", async () => {
      const svg = `<svg viewBox="0 0 400 200" xmlns="http://www.w3.org/2000/svg">
  <style>#my-svg{max-width:100px;background-color:red;}</style>
  <rect width="50" height="25"/>
</svg>`;
      const result = await normalize(svg);

      // The inner <style> block must be byte-identical to what was in the input
      expect(result).toContain("<style>#my-svg{max-width:100px;background-color:red;}</style>");
    });
  });
});
