/**
 * Behavioral tests for MarkdownToc — the sticky in-page table-of-contents
 * component rendered from raw Markdown body.
 *
 * Contract:
 *   - MarkdownToc({ body, ariaLabel? }) → <nav aria-label="..."> with a <ul>
 *     of <li><a href="#slug">text</a></li> for each heading, one per TocEntry
 *     from extractToc(body).
 *   - Returns null (renders nothing) when body yields fewer than 3 headings.
 *   - ariaLabel defaults to "On this page".
 *   - <li> elements carry a per-level class (markdown-toc__item--l1, --l2, --l3
 *     etc.) that distinguishes heading depth in the ToC.
 *   - ToC href="#<slug>" values are byte-identical to the id="" attributes that
 *     MarkdownSurface/rehype-slug emit for the same body (cross-consistency proof).
 *
 * Environment: vitest node — renderToStaticMarkup from react-dom/server.
 * Imports are deferred into each test body for the concurrent BDD/TDD RED handshake.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { describe, expect, it } from "vitest";

// ─── Deferred import helpers ─────────────────────────────────────────────────

async function importMarkdownToc() {
  return import("@/components/markdown-toc") as Promise<
    typeof import("@/components/markdown-toc")
  >;
}

async function importMarkdownSurface() {
  return import("@/components/markdown-surface") as Promise<
    typeof import("@/components/markdown-surface")
  >;
}

async function importHeadings() {
  return import("@/lib/markdown-headings") as Promise<
    typeof import("@/lib/markdown-headings")
  >;
}

// ─── MarkdownToc — nav structure and <a href> entries ────────────────────────

describe("MarkdownToc — renders a nav with one entry per heading", () => {
  it("renders a <nav> element with the default aria-label", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# A\n## B\n### C\n## D";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    expect(html).toContain("<nav");
    expect(html).toContain('aria-label="On this page"');
  });

  it("renders a <ul> with one <li> per heading (4 headings → 4 items)", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# A\n## B\n### C\n## D";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    // Four headings → four list items
    const liMatches = html.match(/<li\b/g) ?? [];
    expect(liMatches).toHaveLength(4);
  });

  it("renders <a href='#slug'> entries matching extractToc slugs", async () => {
    const { MarkdownToc } = await importMarkdownToc();
    const { extractToc } = await importHeadings();

    const body = "# A\n## B\n### C\n## D";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));
    const toc = extractToc(body);

    for (const entry of toc) {
      expect(html).toContain(`href="#${entry.slug}"`);
    }
  });

  it("each anchor text matches the heading display text", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# Introduction\n## Getting Started\n### Installation";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    expect(html).toContain("Introduction");
    expect(html).toContain("Getting Started");
    expect(html).toContain("Installation");
  });
});

// ─── MarkdownToc — suppression when < 3 headings ─────────────────────────────

describe("MarkdownToc — renders nothing when body has fewer than 3 headings", () => {
  it("renders null for a body with only 1 heading", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# Only one";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    // null renders as empty string via renderToStaticMarkup
    expect(html).toBe("");
  });

  it("renders null for a body with exactly 2 headings", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# Only one\n## Two";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    expect(html).toBe("");
  });

  it("renders the nav when body has exactly 3 headings", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# One\n## Two\n### Three";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    expect(html).toContain("<nav");
    const liMatches = html.match(/<li\b/g) ?? [];
    expect(liMatches).toHaveLength(3);
  });

  it("renders null when body has no headings at all", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "no headings here, just prose text";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    expect(html).toBe("");
  });
});

// ─── MarkdownToc — level markers ─────────────────────────────────────────────

describe("MarkdownToc — <li> elements carry per-level class markers", () => {
  it("assigns distinct class names for h1, h2, and h3 items", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# H1 Section\n## H2 Section\n### H3 Section";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    // The implementer uses markdown-toc__item--l1/l2/l3 classes
    expect(html).toContain("--l1");
    expect(html).toContain("--l2");
    expect(html).toContain("--l3");
  });

  it("uses three distinct level markers for mixed h1/h2/h3 body", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# Top Level\n## Mid Level\n### Deep Level\n## Another Mid";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    // Collect all level class values present
    const levelMatches = html.match(/--l(\d+)/g) ?? [];
    const uniqueLevels = new Set(levelMatches);
    // At least 3 distinct level markers (l1, l2, l3)
    expect(uniqueLevels.size).toBeGreaterThanOrEqual(3);
  });
});

// ─── MarkdownToc — ariaLabel prop ────────────────────────────────────────────

describe("MarkdownToc — ariaLabel prop controls the nav accessible name", () => {
  it("uses the supplied ariaLabel on the nav element", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# One\n## Two\n### Three";
    const html = renderToStaticMarkup(
      createElement(MarkdownToc, { body, ariaLabel: "Component index" })
    );

    expect(html).toContain('aria-label="Component index"');
  });

  it("defaults aria-label to 'On this page' when ariaLabel is not supplied", async () => {
    const { MarkdownToc } = await importMarkdownToc();

    const body = "# One\n## Two\n### Three";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));

    expect(html).toContain('aria-label="On this page"');
  });
});

// ─── MarkdownToc — ToC↔heading-id cross-consistency ─────────────────────────
//
// Cross-consistency invariant: MarkdownToc href="#<slug>" values must match
// both the slugs extractToc returns AND the id="" attributes MarkdownSurface
// (via rehype-slug) emits for the same body.

describe("MarkdownToc — ToC hrefs agree with MarkdownSurface heading ids", () => {
  it("hrefs match extractToc slugs for a body with duplicate headings", async () => {
    const { MarkdownToc } = await importMarkdownToc();
    const { extractToc } = await importHeadings();

    // Duplicate heading → de-dup slugs from github-slugger
    const body = "## System Overview\n## Component Map\nbody text\n## Component Map";
    const html = renderToStaticMarkup(createElement(MarkdownToc, { body }));
    const toc = extractToc(body);

    // extractToc must produce 3 entries with de-dup suffixes
    expect(toc).toHaveLength(3);
    expect(toc[0]?.slug).toBe("system-overview");
    expect(toc[1]?.slug).toBe("component-map");
    expect(toc[2]?.slug).toBe("component-map-1");

    // MarkdownToc must contain all three hrefs
    expect(html).toContain('href="#system-overview"');
    expect(html).toContain('href="#component-map"');
    expect(html).toContain('href="#component-map-1"');
  });

  it("hrefs byte-match the id attributes MarkdownSurface emits for the same body", async () => {
    const { MarkdownToc } = await importMarkdownToc();
    const { MarkdownSurface } = await importMarkdownSurface();
    const { extractToc } = await importHeadings();

    // Use a body with duplicate heading to exercise de-dup path
    const body = "## System Overview\n## Component Map\nbody text\n## Component Map";

    const tocHtml = renderToStaticMarkup(createElement(MarkdownToc, { body }));
    const surfaceHtml = renderToStaticMarkup(createElement(MarkdownSurface, { body }));

    const toc = extractToc(body);

    for (const entry of toc) {
      // Each ToC href must be findable in the surface's id attributes
      expect(tocHtml).toContain(`href="#${entry.slug}"`);
      expect(surfaceHtml).toContain(`id="${entry.slug}"`);
    }
  });
});
