import "server-only";

// Normalizes the root <svg> open-tag of an already-sanitized SVG string to make
// it display responsively inside an aspect-ratio box.
//
// Root cause the normalization fixes: Mermaid and LikeC4 emit SVGs with a root
// `<svg width="100%" style="max-width: Npx; background-color: white;">`. The
// inline `style` specificity (1000) beats any stylesheet rule, so the SVG lays
// out at up to N px wide regardless of the container. Removing those declarations
// and stripping the `width`/`height` attributes lets CSS `aspect-ratio` + `width:
// 100%; height: 100%` do the right thing.
//
// Idempotent: a second call returns the same result as the first. Attributes
// already stripped are already absent; `preserveAspectRatio` and `data-*` are
// already present and will be overwritten with the same values.
//
// Scope guard: only the first `<svg` open-tag (the root element) is touched.
// Nested `<svg>` elements, `<style>` blocks, and all other inner content are
// passed through unchanged.
//
// Unmeasurable SVG: if neither `viewbox` nor parseable `width`/`height` attrs
// yield two positive numbers, the input is returned unchanged (no `data-aspect`
// added, no throw).

// Captures the entire root `<svg ...>` open-tag (from `<svg` to the first `>`
// that closes the open-tag). The `[\s\S]` in the attribute body handles
// multi-line open-tags.
const ROOT_SVG_OPEN_TAG = /^([\s\S]*?)(<svg\b([\s\S]*?)>)/i;

// Matches a viewbox attribute (case-insensitive; sanitize-html lowercases it to
// `viewbox`, but raw/test SVGs may retain the camelCase `viewBox`).
const VIEWBOX_ATTR = /\bviewbox\s*=\s*["']([^"']+)["']/i;

// Matches width or height attributes (the root element's intrinsic size attrs).
const WIDTH_ATTR = /\bwidth\s*=\s*["']([^"']+)["']/i;
const HEIGHT_ATTR = /\bheight\s*=\s*["']([^"']+)["']/i;

// Matches an inline style= attribute value.
const STYLE_ATTR = /\bstyle\s*=\s*("([^"]*)"|'([^']*)')/i;

// Style declarations to strip from the root element's inline style (case-insensitive).
const STYLE_DECLS_TO_STRIP =
  /\b(?:max-width|max-height|width|height|background-color)\s*:[^;]*(;|$)\s*/gi;

// Matches an existing preserveAspectRatio attribute.
const PRESERVE_ASPECT_ATTR = /\bpreserveAspectRatio\s*=/i;

// Matches data-aspect, data-vb-w, data-vb-h attributes (for idempotency check).
const DATA_ASPECT_ATTR = /\bdata-aspect\s*="[^"]*"/i;
const DATA_VB_W_ATTR = /\bdata-vb-w\s*="[^"]*"/i;
const DATA_VB_H_ATTR = /\bdata-vb-h\s*="[^"]*"/i;

/**
 * Parses a viewBox string ("minX minY vbW vbH" or "minX,minY,vbW,vbH") and
 * returns [vbW, vbH] if both are positive, or null if unparseable.
 */
function parseViewBox(viewBoxValue: string): [number, number] | null {
  const parts = viewBoxValue.trim().split(/[\s,]+/);
  if (parts.length < 4) return null;
  const vbW = parseFloat(parts[2] ?? "");
  const vbH = parseFloat(parts[3] ?? "");
  if (!isFinite(vbW) || !isFinite(vbH) || vbW <= 0 || vbH <= 0) return null;
  return [vbW, vbH];
}

/**
 * Strips display-blocking declarations from an inline `style` attribute value
 * and returns the cleaned value, or null if nothing remains.
 */
function stripStyleDecls(styleValue: string): string | null {
  const stripped = styleValue.replace(STYLE_DECLS_TO_STRIP, "").trim();
  // If only whitespace or lone semicolons remain, treat as empty.
  const cleaned = stripped.replace(/^[;\s]+|[;\s]+$/g, "").trim();
  return cleaned.length > 0 ? cleaned : null;
}

/**
 * Rewrites the root `<svg>` open-tag to enable responsive layout:
 * - Removes `width` and `height` attributes.
 * - Strips `max-width`, `max-height`, `width`, `height`, and `background-color`
 *   from the inline `style=` value; drops the attribute if nothing remains.
 * - Adds `preserveAspectRatio="xMidYMid meet"` if absent.
 * - Adds `data-aspect`, `data-vb-w`, `data-vb-h` derived from `viewBox` (or
 *   `width`/`height` attrs as fallback).
 *
 * Returns the input unchanged if the SVG is unmeasurable (no parseable viewBox
 * and no parseable width/height attrs that yield positive numbers).
 */
export function normalizeSvg(svg: string): string {
  const tagMatch = ROOT_SVG_OPEN_TAG.exec(svg);
  if (tagMatch === null) return svg;

  const prefix = tagMatch[1] ?? "";
  const fullOpenTag = tagMatch[2] ?? "";
  const attrBlock = tagMatch[3] ?? "";
  const afterTag = svg.slice(prefix.length + fullOpenTag.length);

  // --- Measure the viewbox (dimension source) ---
  let dimensions: [number, number] | null = null;

  const viewBoxMatch = VIEWBOX_ATTR.exec(attrBlock);
  if (viewBoxMatch !== null) {
    dimensions = parseViewBox(viewBoxMatch[1] ?? "");
  }

  if (dimensions === null) {
    // Fallback: try width and height attributes (strip px/% suffixes).
    const wMatch = WIDTH_ATTR.exec(attrBlock);
    const hMatch = HEIGHT_ATTR.exec(attrBlock);
    if (wMatch !== null && hMatch !== null) {
      const w = parseFloat(wMatch[1] ?? "");
      const h = parseFloat(hMatch[1] ?? "");
      if (isFinite(w) && isFinite(h) && w > 0 && h > 0) {
        dimensions = [w, h];
      }
    }
  }

  // Unmeasurable: return unchanged.
  if (dimensions === null) return svg;

  const [vbW, vbH] = dimensions;
  const aspect = Math.round((vbW / vbH) * 10000) / 10000;

  // --- Rewrite the attribute block ---
  let attrs = attrBlock;

  // Strip width and height attributes.
  attrs = attrs.replace(/\s*\bwidth\s*=\s*(?:"[^"]*"|'[^']*')/gi, "");
  attrs = attrs.replace(/\s*\bheight\s*=\s*(?:"[^"]*"|'[^']*')/gi, "");

  // Rewrite or drop the style attribute.
  const styleMatch = STYLE_ATTR.exec(attrs);
  if (styleMatch !== null) {
    const rawValue = styleMatch[2] ?? styleMatch[3] ?? "";
    const cleaned = stripStyleDecls(rawValue);
    if (cleaned !== null) {
      attrs = attrs.replace(styleMatch[0], `style="${cleaned}"`);
    } else {
      attrs = attrs.replace(/\s*\bstyle\s*=\s*(?:"[^"]*"|'[^']*')/i, "");
    }
  }

  // Add preserveAspectRatio if absent.
  if (!PRESERVE_ASPECT_ATTR.test(attrs)) {
    attrs = attrs + ` preserveAspectRatio="xMidYMid meet"`;
  }

  // Add or replace data-aspect, data-vb-w, data-vb-h.
  attrs = attrs.replace(DATA_ASPECT_ATTR, "");
  attrs = attrs.replace(DATA_VB_W_ATTR, "");
  attrs = attrs.replace(DATA_VB_H_ATTR, "");
  attrs = attrs + ` data-aspect="${aspect}" data-vb-w="${vbW}" data-vb-h="${vbH}"`;

  // Normalise interior whitespace (collapse multiple spaces, trim edges).
  attrs = attrs.replace(/\s+/g, " ").trim();

  return `${prefix}<svg ${attrs}>${afterTag}`;
}
