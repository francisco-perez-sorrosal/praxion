import "server-only";

import sanitizeHtml from "sanitize-html";

// Only inline-injected SVGs need sanitization (dangerouslySetInnerHTML / interactive viewer).
// SVGs served via <img src="/api/diagram?path=..."> are opaque to the page —
// an <img>-sourced SVG cannot execute script even when it contains <script> elements,
// so those bytes are served as-is without sanitization.

// sanitize-html / htmlparser2 lowercases all tag names before matching.
// SVG camelCase element names (clipPath, linearGradient, feDropShadow, etc.)
// must be registered in their lowercase form to survive the allowlist check.
// The sanitized output will carry lowercase tag names — functionally equivalent
// for rendering purposes (browsers resolve SVG elements case-insensitively).
const SVG_ALLOWED_TAGS = [
  "svg",
  "g",
  "path",
  "rect",
  "circle",
  "ellipse",
  "line",
  "polyline",
  "polygon",
  "text",
  "tspan",
  "defs",
  "marker",
  "use",
  "symbol",
  "title",
  "desc",
  "style",
  "clippath",          // SVG: clipPath
  "mask",
  "pattern",
  "lineargradient",    // SVG: linearGradient
  "radialgradient",    // SVG: radialGradient
  "stop",
  "a",
  "image",
  "filter",
  "feblend",           // SVG: feBlend
  "fecolormatrix",     // SVG: feColorMatrix
  "fecomponenttransfer", // SVG: feComponentTransfer
  "fecomposite",       // SVG: feComposite
  "feconvolvematrix",  // SVG: feConvolveMatrix
  "fediffuselighting", // SVG: feDiffuseLighting
  "fedisplacementmap", // SVG: feDisplacementMap
  "fedropshadow",      // SVG: feDropShadow
  "feflood",           // SVG: feFlood
  "fefunca",           // SVG: feFuncA
  "fefuncb",           // SVG: feFuncB
  "fefuncg",           // SVG: feFuncG
  "fefuncr",           // SVG: feFuncR
  "fegaussianblur",    // SVG: feGaussianBlur
  "feimage",           // SVG: feImage
  "femerge",           // SVG: feMerge
  "femergenode",       // SVG: feMergeNode
  "femorphology",      // SVG: feMorphology
  "feoffset",          // SVG: feOffset
  "fespecularlighting", // SVG: feSpecularLighting
  "fetile",            // SVG: feTile
  "feturbulence",      // SVG: feTurbulence
  // Intentionally excluded: <script>, <foreignObject>, <iframe>
  // foreignObject allows arbitrary HTML injection including script execution.
  "animate",
  "animatetransform",  // SVG: animateTransform
  "mpath",
  "set"
];

const SVG_ALLOWED_ATTRIBUTES: sanitizeHtml.IOptions["allowedAttributes"] = {
  "*": [
    // Identity and presentation
    "id",
    "class",
    "style",
    // Geometry
    "d",
    "points",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "width",
    "height",
    "viewBox",
    "preserveAspectRatio",
    "transform",
    // Fill and stroke
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-opacity",
    "opacity",
    "visibility",
    "display",
    "clip-path",
    "clip-rule",
    "color",
    "color-interpolation",
    "color-interpolation-filters",
    // Text
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "font-variant",
    "text-anchor",
    "dominant-baseline",
    "dx",
    "dy",
    "rotate",
    "letter-spacing",
    "word-spacing",
    "text-decoration",
    // Markers
    "marker-start",
    "marker-mid",
    "marker-end",
    "markerWidth",
    "markerHeight",
    "markerUnits",
    "orient",
    "refX",
    "refY",
    // Gradients and stops
    "offset",
    "stop-color",
    "stop-opacity",
    "gradientUnits",
    "gradientTransform",
    "patternUnits",
    "patternTransform",
    "patternContentUnits",
    "spreadMethod",
    "fx",
    "fy",
    // Filters
    "filter",
    "filterUnits",
    "primitiveUnits",
    "result",
    "in",
    "in2",
    "stdDeviation",
    "flood-color",
    "flood-opacity",
    "mode",
    "type",
    "values",
    "k1",
    "k2",
    "k3",
    "k4",
    "operator",
    "order",
    "divisor",
    "bias",
    "kernelMatrix",
    "baseFrequency",
    "numOctaves",
    "seed",
    "stitchTiles",
    "fractalNoise",
    // Masks and clips
    "maskUnits",
    "maskContentUnits",
    // Definitions and linking
    "href",
    "xlink:href",
    "xmlns",
    "xmlns:xlink",
    "version",
    // Use element
    "xlink:type",
    // Accessibility
    "role",
    "aria-label",
    "aria-labelledby",
    "aria-roledescription",
    // Data attributes used by Mermaid for edge metadata
    "data-edge",
    "data-et",
    "data-id",
    "data-look",
    "data-points",
    // Animation (SMIL — non-scriptable)
    "attributeName",
    "attributeType",
    "begin",
    "dur",
    "end",
    "from",
    "to",
    "by",
    "repeatCount",
    "repeatDur",
    "calcMode",
    "keyTimes",
    "keySplines",
    "additive",
    "accumulate"
  ]
};

export function sanitizeSvg(raw: string): string {
  return sanitizeHtml(raw, {
    allowedTags: SVG_ALLOWED_TAGS,
    allowedAttributes: SVG_ALLOWED_ATTRIBUTES,
    // Restrict href/xlink:href to safe schemes only — block javascript: URIs
    allowedSchemesByTag: {
      a: ["http", "https"],
      image: ["http", "https", "data"]
    },
    disallowedTagsMode: "discard",
    // <style> is in the allowlist because LikeC4 / D2 / Mermaid embed their styling
    // there. sanitize-html warns on every call that <style> is "vulnerable", flooding
    // the dashboard server log. The real XSS vectors (<script>, on* handlers, javascript:
    // URIs) are already stripped above, and the SVGs come from the project's own
    // diagrams/ (trusted generators), so the CSS-injection risk a bare <style> carries
    // is acceptable here. Acknowledge it explicitly to silence the warning rather than
    // dropping <style> (which would break diagram styling).
    allowVulnerableTags: true,
    // Do not strip style= attribute values — they are in the allowlist above and
    // carry visual-only CSS; parsing them as security surface is unnecessary overhead.
    parseStyleAttributes: false
  });
}
