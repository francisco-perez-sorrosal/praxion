import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { sanitizeSvg } from "@/server/diagrams/sanitize";
import { rewriteRelativeImageRefs } from "@/server/diagrams/rewrite-image-refs";
import { GET } from "@/app/api/diagram/route";

// ---------------------------------------------------------------------------
// sanitizeSvg
// ---------------------------------------------------------------------------

describe("sanitizeSvg — strips XSS vectors", () => {
  it("removes <script> elements from SVG input", () => {
    const input = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="40" fill="blue"/>
      <script>alert('xss')</script>
    </svg>`;

    const output = sanitizeSvg(input);

    expect(output).not.toContain("<script");
    expect(output).not.toContain("alert");
  });

  it("removes on* event handler attributes from SVG elements", () => {
    const input = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="40" fill="blue" onload="evil()"/>
      <rect x="0" y="0" width="50" height="50" onclick="steal()"/>
    </svg>`;

    const output = sanitizeSvg(input);

    expect(output).not.toContain("onload");
    expect(output).not.toContain("onclick");
    expect(output).not.toContain("evil()");
    expect(output).not.toContain("steal()");
  });

  it("preserves structural and visual SVG elements after sanitization", () => {
    // A representative slice of Mermaid/LikeC4 SVG output
    const input = `<svg id="diagram" width="100%" xmlns="http://www.w3.org/2000/svg"
        xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 400 200">
      <defs>
        <marker id="arrowEnd" viewBox="0 0 10 10" refX="5" refY="5"
            markerWidth="8" markerHeight="8" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#333"/>
        </marker>
        <filter id="drop-shadow">
          <feDropShadow dx="2" dy="2" stdDeviation="0" flood-opacity="0.06" flood-color="#000"/>
        </filter>
      </defs>
      <g class="nodes">
        <rect x="10" y="10" width="120" height="40" fill="#ECECFF" stroke="#9370DB"/>
        <text x="70" y="35" text-anchor="middle" font-family="sans-serif" font-size="14">
          Component A
        </text>
        <path d="M 130 30 L 200 30" stroke="#333" marker-end="url(#arrowEnd)"/>
      </g>
    </svg>`;

    const output = sanitizeSvg(input);

    expect(output).toContain("<g");
    expect(output).toContain("<path");
    expect(output).toContain("<rect");
    expect(output).toContain("<text");
    expect(output).toContain("<defs");
    expect(output).toContain("<marker");
    // htmlparser2 >= 12 restores the spec-correct camelCase tag name for known
    // SVG elements inside foreign content (feDropShadow, not fedropshadow) —
    // checked case-insensitively since the sanitizer's allowlist accepts both.
    expect(output.toLowerCase()).toContain("fedropshadow");
  });

  it("preserves the root viewBox and other camelCase SVG attributes (regression: htmlparser2 lowercases attribute names)", () => {
    // Mermaid emits <svg width="100%" viewBox="-50 -10 1645.5 597"> with no height.
    // Before the fix, "viewBox" (camelCase) in the allowlist matched nothing —
    // htmlparser2 lowercases attribute names — so viewBox was silently stripped and
    // the diagram rendered at intrinsic size with no fit-to-container (the original
    // "diagrams render badly" defect). The attribute survives as lowercase "viewbox";
    // the HTML5 parser restores the canonical casing when the markup is injected.
    const input = `<svg id="my-svg" width="100%" xmlns="http://www.w3.org/2000/svg"
        viewBox="-50 -10 1645.5 597" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="g" gradientTransform="rotate(20)" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stop-color="#fff"/>
        </linearGradient>
        <marker id="m" refX="5" refY="5" markerWidth="8" markerHeight="8"/>
      </defs>
      <rect x="0" y="0" width="100" height="50" fill="url(#g)"/>
    </svg>`;

    const output = sanitizeSvg(input);

    expect(output).toContain('viewbox="-50 -10 1645.5 597"');
    expect(output).toContain('preserveaspectratio="xMidYMid meet"');
    expect(output).toContain('gradienttransform="rotate(20)"');
    expect(output).toContain('gradientunits="userSpaceOnUse"');
    expect(output).toContain('refx="5"');
    expect(output).toContain('markerwidth="8"');
  });

  it("preserves <foreignObject> with safe HTML children (Mermaid node labels)", () => {
    // Mermaid renders every node label as HTML inside <foreignObject><div xmlns=...>.
    // Without foreignObject the label is invisible (empty yellow box).
    const input = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
      <g>
        <foreignObject width="120" height="40">
          <div xmlns="http://www.w3.org/1999/xhtml" class="nodeLabel">Some Label</div>
        </foreignObject>
      </g>
    </svg>`;

    const output = sanitizeSvg(input);

    // Checked case-insensitively: htmlparser2 >= 12 restores foreignObject's
    // spec-correct camelCase inside SVG foreign content (was foreignobject
    // pre-upgrade); the allowlist accepts both forms.
    expect(output.toLowerCase()).toContain("foreignobject");
    expect(output).toContain("nodeLabel");
    expect(output).toContain("Some Label");
    expect(output).toContain('xmlns="http://www.w3.org/1999/xhtml"');
  });

  it("strips <script> inside <foreignObject> while keeping safe content", () => {
    const input = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
      <foreignObject width="120" height="40">
        <div xmlns="http://www.w3.org/1999/xhtml" class="nodeLabel">
          Safe text
          <script>evil()</script>
        </div>
      </foreignObject>
    </svg>`;

    const output = sanitizeSvg(input);

    expect(output).toContain("Safe text");
    expect(output).not.toContain("<script");
    expect(output).not.toContain("evil()");
  });

  it("strips onload= handler inside <foreignObject> while keeping safe content", () => {
    const input = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
      <foreignObject width="120" height="40">
        <div xmlns="http://www.w3.org/1999/xhtml" onload="steal()">Safe</div>
      </foreignObject>
    </svg>`;

    const output = sanitizeSvg(input);

    expect(output).toContain("Safe");
    expect(output).not.toContain("onload");
    expect(output).not.toContain("steal()");
  });
});

// ---------------------------------------------------------------------------
// rewriteRelativeImageRefs
// ---------------------------------------------------------------------------

describe("rewriteRelativeImageRefs — path rewriting", () => {
  it("rewrites a relative <img> ref that resolves inside docs/ to /api/diagram", () => {
    const markdown =
      'See the diagram: <img src="../docs/diagrams/foo/rendered/foo.svg" alt="Foo">';
    const result = rewriteRelativeImageRefs(markdown, ".ai-state", "/project");

    expect(result).toContain("/api/diagram?path=");
    expect(result).toContain("docs%2Fdiagrams%2Ffoo%2Frendered%2Ffoo.svg");
    expect(result).not.toContain("../docs/diagrams");
  });

  it("rewrites a Markdown image ref that resolves inside docs/ to /api/diagram", () => {
    const markdown = "![Architecture](diagrams/architecture/rendered/components.svg)";
    const result = rewriteRelativeImageRefs(markdown, "docs", "/project");

    expect(result).toContain("/api/diagram?path=");
    expect(result).toContain(
      "docs%2Fdiagrams%2Farchitecture%2Frendered%2Fcomponents.svg"
    );
  });

  it("rewrites a .ai-state-relative <img> ref correctly", () => {
    const markdown = '<img src="diagrams/system/rendered/system.svg">';
    const result = rewriteRelativeImageRefs(markdown, ".ai-state", "/project");

    expect(result).toContain("/api/diagram?path=");
    expect(result).toContain(".ai-state%2Fdiagrams%2Fsystem%2Frendered%2Fsystem.svg");
  });

  it("leaves https:// image references untouched", () => {
    const markdown = '<img src="https://external.example.com/img.svg">';
    const result = rewriteRelativeImageRefs(markdown, ".ai-state", "/project");

    expect(result).toBe(markdown);
  });

  it("leaves data: image references untouched", () => {
    const markdown = '<img src="data:image/svg+xml;base64,PHN2Zy8+">';
    const result = rewriteRelativeImageRefs(markdown, ".ai-state", "/project");

    expect(result).toBe(markdown);
  });

  it("leaves absolute path references that are not in the allowlist untouched", () => {
    const markdown = '<img src="/absolute/path/outside/allowlist.svg">';
    const result = rewriteRelativeImageRefs(markdown, ".ai-state", "/project");

    // Absolute paths starting with / are treated as external and not rewritten
    expect(result).toBe(markdown);
  });

  it("leaves relative paths that resolve outside the allowlist untouched (broken image, not crash)", () => {
    const markdown = '<img src="../../etc/passwd">';
    const result = rewriteRelativeImageRefs(markdown, ".ai-state", "/project");

    // Out-of-root or out-of-allowlist refs are left as-is
    expect(result).toBe(markdown);
  });

  it("handles single-quoted <img src='...'> syntax", () => {
    const markdown = "<img src='../docs/diagrams/bar/rendered/bar.svg' alt='Bar'>";
    const result = rewriteRelativeImageRefs(markdown, ".ai-state", "/project");

    expect(result).toContain("/api/diagram?path=");
    expect(result).toContain("docs%2Fdiagrams%2Fbar%2Frendered%2Fbar.svg");
  });
});

// ---------------------------------------------------------------------------
// /api/diagram route handler
// ---------------------------------------------------------------------------

const tempRoots: string[] = [];

beforeEach(() => {
  // Reset between tests; root list cleared in afterEach
});

afterEach(async () => {
  const roots = tempRoots.splice(0);
  await Promise.all(roots.map((root) => rm(root, { force: true, recursive: true })));
  // Clean up the env var override
  delete process.env.PRAXION_PROJECT_ROOT;
});

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  await mkdir(path.join(root, ".ai-state"), { recursive: true });
  tempRoots.push(root);
  return root;
}

describe("/api/diagram GET handler", () => {
  it("returns 400 when the path query param is missing", async () => {
    const root = await createTempProjectRoot("diagram-route-test-");
    process.env.PRAXION_PROJECT_ROOT = root;

    const request = new Request("http://localhost/api/diagram") as Parameters<typeof GET>[0];
    const response = await GET(request);

    expect(response.status).toBe(400);
  });

  it("returns 403 when the path points outside the allowlist", async () => {
    const root = await createTempProjectRoot("diagram-route-test-");
    process.env.PRAXION_PROJECT_ROOT = root;

    const request = new Request(
      "http://localhost/api/diagram?path=package.json"
    ) as Parameters<typeof GET>[0];
    const response = await GET(request);

    // package.json is not in .ai-state/.ai-work/docs/ROADMAP.md allowlist
    expect(response.status).toBe(403);
  });

  it("returns 403 for path traversal attempts", async () => {
    const root = await createTempProjectRoot("diagram-route-test-");
    process.env.PRAXION_PROJECT_ROOT = root;

    const request = new Request(
      "http://localhost/api/diagram?path=../../../../etc/passwd.svg"
    ) as Parameters<typeof GET>[0];
    const response = await GET(request);

    expect(response.status).toBe(403);
  });

  it("returns 403 for a non-.svg extension", async () => {
    const root = await createTempProjectRoot("diagram-route-test-");
    process.env.PRAXION_PROJECT_ROOT = root;

    const request = new Request(
      "http://localhost/api/diagram?path=docs/diagrams/foo/rendered/foo.png"
    ) as Parameters<typeof GET>[0];
    const response = await GET(request);

    expect(response.status).toBe(403);
  });

  it("returns 404 for an allowlisted .svg path that does not exist on disk", async () => {
    const root = await createTempProjectRoot("diagram-route-test-");
    process.env.PRAXION_PROJECT_ROOT = root;
    // Create the docs directory but not the specific SVG file
    await mkdir(path.join(root, "docs", "diagrams", "arch", "rendered"), {
      recursive: true
    });

    const request = new Request(
      "http://localhost/api/diagram?path=docs%2Fdiagrams%2Farch%2Frendered%2Fmissing.svg"
    ) as Parameters<typeof GET>[0];
    const response = await GET(request);

    expect(response.status).toBe(404);
  });
});
