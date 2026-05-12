import ReactMarkdown from "react-markdown";
import rehypeAutolinkHeadings from "rehype-autolink-headings";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";

// react-markdown escapes raw HTML by default (security posture: no rehype-raw).
// Project markdown bodies (.ai-state/DESIGN.md, docs/architecture.md, etc.) embed
// diagrams as raw <img> tags and surround sections with <!-- OWNER: ... --> comments.
// Both show as literal escaped text unless preprocessed. This helper normalises them
// before react-markdown sees the content, without relaxing the no-raw-HTML posture:
//   1. Strip HTML comments (<!-- ... -->) — purely cosmetic; agents read the source.
//   2. Convert standalone <img src="..." alt="..."> to markdown image syntax ![alt](src)
//      so react-markdown renders them as real <img> elements.
// Markdown image syntax (![alt](url)) is untouched — it already renders correctly.
export function prepareMarkdownBody(raw: string): string {
  // 1) strip HTML comments
  const noComments = raw.replace(/<!--[\s\S]*?-->/g, "");

  // 2) convert raw <img ...> tags to markdown image syntax.
  // Handles both double- and single-quoted attribute values, optional whitespace,
  // self-closing slash, and any attribute order.
  const noRawImg = noComments.replace(
    /<img\s([^>]*?)>/gi,
    (_match: string, attrs: string) => {
      const srcMatch = attrs.match(/src=["']([^"']*)["']/i);
      const altMatch = attrs.match(/alt=["']([^"']*)["']/i);
      const src = srcMatch ? srcMatch[1] : "";
      const alt = altMatch ? altMatch[1] : "";
      if (!src) return "";
      return `![${alt}](${src})`;
    }
  );

  return noRawImg;
}

// rehype-slug adds id="kebab-slug" to every h1–h6 element by operating on the
// HAST (HTML Abstract Syntax Tree) that react-markdown has already parsed from
// Markdown. rehype-autolink-headings then appends a focusable anchor element.
//
// These are pure HAST AST transforms — they do NOT re-introduce a raw-HTML parse
// step (that would be rehype-raw, which is deliberately omitted). The no-raw-HTML
// security posture is fully preserved.
//
// Plugin order matters: rehype-slug must run before rehype-autolink-headings
// because autolink reads the id that slug just added.
const REHYPE_AUTOLINK_OPTIONS = {
  behavior: "append" as const,
  properties: {
    className: ["heading-anchor"],
    "aria-label": "Link to this section",
  },
  content: {
    type: "element" as const,
    tagName: "span",
    properties: { "aria-hidden": "true" },
    children: [{ type: "text" as const, value: "§" }],
  },
};

export function MarkdownSurface({ body }: { body: string }) {
  return (
    <div className="markdown-surface">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSlug, [rehypeAutolinkHeadings, REHYPE_AUTOLINK_OPTIONS]]}
      >
        {prepareMarkdownBody(body)}
      </ReactMarkdown>
    </div>
  );
}
