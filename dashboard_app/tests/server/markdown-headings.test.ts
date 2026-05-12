import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// Deferred imports — allow test collection to succeed before the module under
// test exists (concurrent BDD/TDD RED handshake). Each test that needs the
// module imports it lazily inside the test body.
// ---------------------------------------------------------------------------

async function importHeadings() {
  return import("@/lib/markdown-headings") as Promise<
    typeof import("@/lib/markdown-headings")
  >;
}

// ---------------------------------------------------------------------------
// MarkdownSurface render helper — returns static HTML string.
// renderToStaticMarkup works in a node environment without a DOM.
// ---------------------------------------------------------------------------

async function renderMarkdownSurface(body: string): Promise<string> {
  const { MarkdownSurface } = await import("@/components/markdown-surface");
  return renderToStaticMarkup(React.createElement(MarkdownSurface, { body }));
}

// ─── slugify ─────────────────────────────────────────────────────────────────
//
// All expected values are the known-correct outputs of github-slugger@2.0.0,
// confirmed by running `new GithubSlugger().slug(text)` against each fixture.
// slugify must match github-slugger exactly so a ToC href="#foo-bar" resolves
// the id="foo-bar" that rehype-slug emits for the same heading text.

describe("slugify", () => {
  it("lowercases words and replaces spaces with hyphens", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("Foo Bar")).toBe("foo-bar");
  });

  it("handles a multi-word phrase", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("System Overview")).toBe("system-overview");
  });

  it("strips trailing punctuation (question mark)", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("What is this?")).toBe("what-is-this");
  });

  it("strips special chars and preserves surrounding hyphens for spaces (ampersand and slash)", async () => {
    // github-slugger strips & and /, each surrounded-space becomes a hyphen
    // "A & B / C" → spaces become hyphens, & and / stripped → "a--b--c"
    const { slugify } = await importHeadings();
    expect(slugify("A & B / C")).toBe("a--b--c");
  });

  it("strips exclamation mark", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("Hello World!")).toBe("hello-world");
  });

  it("handles a hyphenated alphanumeric identifier", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("Phase-12 Heading")).toBe("phase-12-heading");
  });

  it("preserves accented characters and emits hyphens for non-word chars around emoji", async () => {
    // github-slugger preserves unicode letters (café) but strips ☕ and surrounding spaces
    // become hyphens: "Café ☕ Time" → "café--time"
    const { slugify } = await importHeadings();
    expect(slugify("Café ☕ Time")).toBe("café--time");
  });

  it("strips backticks from inline code spans and preserves the inner content", async () => {
    const { slugify } = await importHeadings();
    // `code` → code (backticks stripped as non-word, space-separated words join)
    expect(slugify("with `code` inline")).toBe("with-code-inline");
  });

  it("handles inline code in a function-name heading", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("The `foo` function")).toBe("the-foo-function");
  });

  it("component-map heading produces expected slug", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("Component Map")).toBe("component-map");
  });

  it("single word produces lower-cased slug with no hyphens", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("Setup")).toBe("setup");
  });

  // Note: github-slugger does NOT trim leading/trailing whitespace before
  // processing — spaces at the boundary become leading/trailing hyphens.
  // This is github-slugger@2 behavior and slugify must match it exactly.
  it("converts leading and trailing spaces to leading/trailing hyphens (github-slugger behavior)", async () => {
    const { slugify } = await importHeadings();
    expect(slugify("  Trim Me  ")).toBe("--trim-me--");
  });
});

// ─── extractToc ──────────────────────────────────────────────────────────────

describe("extractToc", () => {
  it("returns an empty array for an empty body", async () => {
    const { extractToc } = await importHeadings();
    expect(extractToc("")).toEqual([]);
  });

  it("returns an empty array when body has only paragraphs", async () => {
    const { extractToc } = await importHeadings();
    const body = "This is a paragraph.\n\nAnother paragraph here.";
    expect(extractToc(body)).toEqual([]);
  });

  it("extracts h1, h2, and h3 with correct level, text, and slug", async () => {
    const { extractToc } = await importHeadings();
    const body = "# A\n## B\n### C";
    expect(extractToc(body)).toEqual([
      { level: 1, text: "A", slug: "a" },
      { level: 2, text: "B", slug: "b" },
      { level: 3, text: "C", slug: "c" },
    ]);
  });

  it("extracts headings h1 through h6", async () => {
    const { extractToc } = await importHeadings();
    const body = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6";
    const toc = extractToc(body);
    expect(toc).toHaveLength(6);
    expect(toc[0]).toEqual({ level: 1, text: "H1", slug: "h1" });
    expect(toc[5]).toEqual({ level: 6, text: "H6", slug: "h6" });
  });

  it("skips non-heading lines (paragraphs, horizontal rules, list items)", async () => {
    const { extractToc } = await importHeadings();
    const body = "## Real Heading\n\nSome paragraph text.\n\n- list item\n\n## Second Heading";
    const toc = extractToc(body);
    expect(toc).toHaveLength(2);
    expect(toc[0]?.slug).toBe("real-heading");
    expect(toc[1]?.slug).toBe("second-heading");
  });

  it("de-duplicates repeated heading text with -1, -2, ... suffixes", async () => {
    // This is the key cross-consistency test: slugs must match what rehype-slug emits
    const { extractToc } = await importHeadings();
    const body = "## Setup\n## Setup\n## Setup";
    const toc = extractToc(body);
    expect(toc).toHaveLength(3);
    expect(toc[0]?.slug).toBe("setup");
    expect(toc[1]?.slug).toBe("setup-1");
    expect(toc[2]?.slug).toBe("setup-2");
  });

  it("skips headings inside a fenced code block", async () => {
    const { extractToc } = await importHeadings();
    const body =
      "## Real\n\n```\n## Fake\n```\n\n## Also Real";
    const toc = extractToc(body);
    expect(toc).toHaveLength(2);
    expect(toc[0]?.text).toBe("Real");
    expect(toc[1]?.text).toBe("Also Real");
  });

  it("skips headings inside a tilde-fenced code block", async () => {
    const { extractToc } = await importHeadings();
    const body = "## Real\n\n~~~\n## Hidden\n~~~\n\n## Visible";
    const toc = extractToc(body);
    expect(toc).toHaveLength(2);
    expect(toc[0]?.text).toBe("Real");
    expect(toc[1]?.text).toBe("Visible");
  });

  it("strips backticks from inline code in heading text and preserves the inner word", async () => {
    // Implementation strips backticks and trims; the displayText is "The foo function"
    const { extractToc } = await importHeadings();
    const body = "## The `foo` function";
    const toc = extractToc(body);
    expect(toc).toHaveLength(1);
    // text has backticks stripped
    expect(toc[0]?.text).toBe("The foo function");
    // slug is a valid github-slug
    expect(toc[0]?.slug).toBe("the-foo-function");
  });

  it("produces a non-empty slug for a heading with inline code", async () => {
    const { extractToc } = await importHeadings();
    const body = "## The `foo` API";
    const toc = extractToc(body);
    expect(toc).toHaveLength(1);
    const slug = toc[0]?.slug ?? "";
    expect(slug.length).toBeGreaterThan(0);
    expect(slug).toBe("the-foo-api");
  });

  it("round-trip invariant: slugify(entry.text) equals entry.slug for non-duplicated headings", async () => {
    // Guards the single-source invariant: the slug computed during extractToc
    // for a unique heading must equal what a fresh slugify call returns for the
    // same (backtick-stripped, trimmed) displayText.
    const { extractToc, slugify } = await importHeadings();
    const body =
      "# Introduction\n## Installation\n### Quick Start\n## Architecture Overview";
    const toc = extractToc(body);
    // All headings are unique in this body — no de-dup suffix involved
    for (const entry of toc) {
      expect(slugify(entry.text)).toBe(entry.slug);
    }
  });

  it("handles blank lines between headings gracefully", async () => {
    const { extractToc } = await importHeadings();
    const body = "## First\n\n\n## Second\n\n\n\n## Third";
    const toc = extractToc(body);
    expect(toc).toHaveLength(3);
    expect(toc.map((e) => e.slug)).toEqual(["first", "second", "third"]);
  });
});

// ─── MarkdownSurface heading anchors ─────────────────────────────────────────
//
// These tests verify that the rehype-slug + rehype-autolink-headings pipeline
// wired into MarkdownSurface emits stable id= attributes on headings and the
// § link affordance. They also cross-check that extractToc slugs match the
// id= values for the same body (the ToC↔heading-id agreement proof).

describe("MarkdownSurface heading anchors", () => {
  it("emits an id attribute on an h2 matching the github-slugger slug", async () => {
    const html = await renderMarkdownSurface("## Component Map\n\nsome text");
    expect(html).toContain('id="component-map"');
  });

  it("emits the heading-anchor link with aria-label on an h2", async () => {
    const html = await renderMarkdownSurface("## Component Map\n\nsome text");
    expect(html).toContain('class="heading-anchor"');
    expect(html).toContain('aria-label="Link to this section"');
  });

  it("includes the § glyph inside the heading anchor", async () => {
    const html = await renderMarkdownSurface("## Component Map\n\nsome text");
    // The § is rendered inside a span[aria-hidden="true"] wrapped in the anchor
    expect(html).toContain("§");
  });

  it("de-duplicates heading ids for repeated heading text matching extractToc", async () => {
    // Cross-consistency proof (ToC↔heading-id agreement):
    // The ids emitted by rehype-slug must match the slugs extractToc returns.
    const body = "## Setup\n## Setup";
    const html = await renderMarkdownSurface(body);

    // Assert both ids are present in the rendered HTML
    expect(html).toContain('id="setup"');
    expect(html).toContain('id="setup-1"');

    // Cross-check against extractToc
    const { extractToc } = await importHeadings();
    const toc = extractToc(body);
    expect(toc[0]?.slug).toBe("setup");
    expect(toc[1]?.slug).toBe("setup-1");

    // The toc slugs and the html ids must agree
    const idMatches = [...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]);
    expect(idMatches).toContain(toc[0]?.slug);
    expect(idMatches).toContain(toc[1]?.slug);
  });

  it("emits a non-empty id on an h2 whose text contains inline code", async () => {
    // rehype-slug operates on the HAST text nodes (backtick-stripped),
    // so "The `foo` API" produces id="the-foo-api" (not empty or mangled).
    const html = await renderMarkdownSurface("## The `foo` API\n\ntext");
    // Any non-empty id on an h2
    const h2IdMatch = html.match(/<h2[^>]*\bid="([^"]+)"/);
    expect(h2IdMatch).not.toBeNull();
    const id = h2IdMatch?.[1] ?? "";
    expect(id.length).toBeGreaterThan(0);
    expect(id).toBe("the-foo-api");
  });

  it("still strips HTML comments from the body (prepareMarkdownBody regression guard)", async () => {
    const body = "<!-- x -->\n\n## Heading\n\nSome prose.";
    const html = await renderMarkdownSurface(body);
    expect(html).not.toContain("<!--");
    expect(html).toContain("Some prose.");
  });

  it("converts raw img tags to real img elements (prepareMarkdownBody regression guard)", async () => {
    const body = '<img src="diagrams/a.svg" alt="a">\n\n## A Heading';
    const html = await renderMarkdownSurface(body);
    // The raw <img> was converted to ![a](diagrams/a.svg) by prepareMarkdownBody,
    // which react-markdown then renders as a real <img> element.
    expect(html).toContain('<img');
    expect(html).toContain('src="diagrams/a.svg"');
    expect(html).toContain('alt="a"');
    // The comment is gone and the heading is still rendered
    expect(html).toContain('id="a-heading"');
  });
});
