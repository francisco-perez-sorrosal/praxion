/**
 * Sticky in-page table-of-contents rendered from raw Markdown body.
 *
 * Calls `extractToc(body)` from the single-sourced `@/lib/markdown-headings`
 * module — the same algorithm `rehype-slug` uses internally (both go through
 * github-slugger), so every `href="#<slug>"` here resolves the matching
 * `id="<slug>"` on the heading that `MarkdownSurface` emits.
 *
 * Returns null (renders nothing) when the body yields fewer than 3 headings —
 * a ToC with 1–2 entries adds more noise than value.
 *
 * No "use client" needed: the list is a static set of `<a href="#…">` anchors;
 * anchor-scroll is native browser behaviour and requires no JavaScript.
 */

import { extractToc } from "@/lib/markdown-headings";
import type { TocEntry } from "@/lib/markdown-headings";

const MIN_HEADINGS_TO_SHOW = 3;

type MarkdownTocProps = {
  readonly ariaLabel?: string;
  readonly body: string;
};

export function MarkdownToc({
  body,
  ariaLabel = "On this page"
}: MarkdownTocProps) {
  const entries = extractToc(body);

  if (entries.length < MIN_HEADINGS_TO_SHOW) {
    return null;
  }

  return (
    <nav className="markdown-toc" aria-label={ariaLabel}>
      <ul className="markdown-toc__list">
        {entries.map((entry: TocEntry) => (
          <li
            key={entry.slug}
            className={`markdown-toc__item markdown-toc__item--l${entry.level}`}
          >
            <a href={`#${entry.slug}`}>{entry.text}</a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
