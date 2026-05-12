/**
 * Single-sourced heading utilities for the dashboard.
 *
 * Both the `MarkdownSurface` rendering path (via rehype-slug) and the in-page
 * table-of-contents rendering path (via `extractToc`) must agree on heading IDs.
 * rehype-slug uses github-slugger internally. This module uses github-slugger
 * directly so `extractToc` produces the same slugs — and the same de-duplication
 * counter — that rehype-slug will emit for the same document.
 *
 * Consequence: callers must use one shared `GithubSlugger` instance per document
 * (not per call) so repeated headings get the expected -1, -2, ... suffixes.
 */
import GithubSlugger, { slug as slugSingle } from "github-slugger";

/**
 * Produce a GitHub-flavored heading slug for a single heading text.
 *
 * Does NOT track de-duplication (no counter state). Use this when you need
 * a one-off slug for a heading that you know is unique in the document.
 * For ToC extraction over a full document, use `extractToc` which instantiates
 * a fresh `GithubSlugger` per call and handles de-duplication automatically.
 */
export function slugify(text: string): string {
  return slugSingle(text);
}

export type TocEntry = {
  readonly level: number;
  readonly text: string;
  readonly slug: string;
};

// ATX heading pattern: one to six # chars followed by at least one space and text.
const ATX_HEADING_RE = /^(#{1,6})\s+(.+)$/;

// Fenced code block open/close: three or more backticks or tildes at line start.
const FENCE_OPEN_RE = /^(`{3,}|~{3,})/;

/**
 * Extract the table-of-contents entries from a raw Markdown body.
 *
 * Headings inside fenced code blocks are skipped. The slug for each entry is
 * computed via a single `GithubSlugger` instance (reset per `extractToc` call)
 * so repeated headings get -1, -2, ... suffixes that exactly match what
 * rehype-slug emits for the same document.
 *
 * Inline backtick code in heading text is stripped before display (backticks
 * removed, content preserved — e.g. `foo` → foo). Other inline markdown
 * markers (bold **, italic *, links) are not stripped because they are uncommon
 * in headings and stripping them would require a full inline parser.
 */
export function extractToc(body: string): TocEntry[] {
  const slugger = new GithubSlugger();
  const entries: TocEntry[] = [];
  let inFence = false;
  let fenceMarker = "";

  for (const line of body.split("\n")) {
    // Track fenced code block boundaries.
    const fenceMatch = FENCE_OPEN_RE.exec(line);
    if (fenceMatch) {
      if (!inFence) {
        inFence = true;
        fenceMarker = fenceMatch[1]?.[0] ?? "`";
      } else if (line.startsWith(fenceMarker)) {
        inFence = false;
        fenceMarker = "";
      }
      continue;
    }

    if (inFence) continue;

    const headingMatch = ATX_HEADING_RE.exec(line);
    if (!headingMatch) continue;

    const hashes = headingMatch[1];
    const rawText = headingMatch[2];
    if (!hashes || !rawText) continue;

    // Strip inline backtick code spans (preserve the content, drop the backticks).
    const displayText = rawText.replace(/`([^`]*)`/g, "$1").trim();

    entries.push({
      level: hashes.length,
      text: displayText,
      // Slug the raw text (without stripped backticks) to match what rehype-slug
      // sees — rehype-slug slugs the rendered text content of the heading node,
      // which for `foo` inline code is "foo" (just the text). Using displayText
      // keeps both paths aligned.
      slug: slugger.slug(displayText),
    });
  }

  return entries;
}
