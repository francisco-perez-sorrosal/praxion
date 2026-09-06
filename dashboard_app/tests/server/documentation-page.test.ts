/**
 * Characterization tests for the Documentation page (async Server Component),
 * written BEFORE td-164's extraction (Step 22: `<SurfaceBody>`,
 * `resolveRendererFor`, `<DocumentationEmpty />`, `selectSurface`). These must
 * pass GREEN against the current, unextracted `page.tsx` — they pin today's
 * observable output so Step 22 can prove the extraction is behavior-preserving.
 *
 * Strategy: mock the view-model (`@/server/view-models/documentation`) and the
 * config (`@/lib/config`) to return controlled fixtures, then render the page
 * with `renderToStaticMarkup(await DocumentationPage({ searchParams }))` and
 * assert on the resulting HTML string. Renderer components (`resolveRenderer`,
 * `RENDERER_REGISTRY`, the shells) are the page's real, unmocked collaborators
 * — only the server view-model boundary is mocked.
 *
 * Behaviors validated here:
 *   - `data === null` renders the doc-manifest empty state (no crash).
 *   - Surface selection from `searchParams.surface`: selected id present and
 *     matching -> that surface; absent -> first surface; present but unknown
 *     -> first surface (same fallback as absent); no surfaces -> null
 *     selection, "Select a surface..." placeholder, "Surface preview" heading,
 *     no artifact-meta chip row.
 *   - Every `renderMode` branch (markdown | api | code | unsupported | error)
 *     renders through the expected renderer/shell.
 *   - The duplicated null-body fallback (`errorMessage ?? "Unreadable file."`)
 *     in the markdown/api/code arms: default text when `errorMessage` is
 *     null, and the provided `errorMessage` when set.
 *
 * Environment: vitest node — renderToStaticMarkup from react-dom/server.
 * vi.mock hoisting: mocks must be at the top level (not in beforeEach/it) so
 * vitest's static analysis can hoist them before module imports.
 */

import { renderToStaticMarkup } from "react-dom/server";

import { beforeEach, describe, expect, it, vi } from "vitest";

// The page's module graph pulls in the full renderer registry (including
// @scalar/api-reference-react and recharts, via ApiReferenceShell / the chart
// renderers). Under full-suite concurrent worker load, the first cold import
// of that graph in this file can exceed vitest's 5s default test timeout even
// though the assertions themselves run in milliseconds — bump the budget for
// this file only.
vi.setConfig({ testTimeout: 45000 });

import type { DocumentationSurfaceData } from "@/server/view-models/documentation";
import type { ManifestSurface } from "@/server/types";

// ─── Module mocks (hoisted at top level) ─────────────────────────────────────

vi.mock("@/lib/config", () => ({
  getConfig: () => ({
    dashboardVersion: "0.0.0",
    pollIntervalSeconds: 15,
    projectName: "fake",
    projectRoot: "/fake-project"
  })
}));

vi.mock("@/server/view-models/documentation", () => ({
  getDocumentationData: vi.fn(),
  getDocumentationSurfaceData: vi.fn()
}));

// Call-history assertions ("never calls the per-surface fetcher") need each
// test to start from a clean slate — mocked modules are module-level
// singletons shared across every describe block in this file.
beforeEach(() => {
  vi.clearAllMocks();
});

// ─── Fixture helpers ─────────────────────────────────────────────────────────

function surface(overrides: Partial<ManifestSurface> & Pick<ManifestSurface, "id" | "title">): ManifestSurface {
  return {
    path: `docs/${overrides.id}.md`,
    type: "markdown",
    ...overrides
  };
}

const README_SURFACE = surface({ id: "readme", title: "Readme" });
const GUIDE_SURFACE = surface({ id: "guide", title: "Guide" });

function surfaceData(overrides: Partial<DocumentationSurfaceData> & { surface: ManifestSurface }): DocumentationSurfaceData {
  return {
    body: "fallback body",
    errorMessage: null,
    path: `/fake-project/${overrides.surface.path}`,
    renderMode: "markdown",
    ...overrides
  };
}

// ─── Render helper ────────────────────────────────────────────────────────────

async function renderPage(
  params: Record<string, string | string[] | undefined> = {}
): Promise<string> {
  // Deferred import: the page may not be fully restructured when tests first
  // run (concurrent BDD/TDD). If the module is missing, the test fails with
  // ImportError — the expected RED state.
  const { default: DocumentationPage } = await import("@/app/documentation/page");
  const element = await DocumentationPage({ searchParams: Promise.resolve(params) });
  return renderToStaticMarkup(element);
}

async function getMockedGetDocumentationData() {
  const mod = await import("@/server/view-models/documentation");
  return mod.getDocumentationData as ReturnType<typeof vi.fn>;
}

async function getMockedGetDocumentationSurfaceData() {
  const mod = await import("@/server/view-models/documentation");
  return mod.getDocumentationSurfaceData as ReturnType<typeof vi.fn>;
}

// ─── DocumentationPage — no doc manifest (data === null) ───────────────────

describe("DocumentationPage — no doc manifest found", () => {
  beforeEach(async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue(null);
  });

  it("does not crash when the manifest is absent", async () => {
    await expect(renderPage()).resolves.not.toThrow();
  });

  it("renders the doc-manifest empty state with the producer command", async () => {
    const html = await renderPage();

    expect(html).toContain("No doc manifest found");
    expect(html).toContain("python3 scripts/build_doc_manifest.py");
    expect(html).toContain(".ai-state/doc_manifest.yaml");
  });

  it("never calls the per-surface data fetcher when the manifest is absent", async () => {
    await renderPage();

    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    expect(getDocumentationSurfaceData).not.toHaveBeenCalled();
  });
});

// ─── DocumentationPage — surface selection from searchParams ────────────────

describe("DocumentationPage — surface selection from searchParams.surface", () => {
  beforeEach(async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: [README_SURFACE, GUIDE_SURFACE]
    });

    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockImplementation(async (_root: string, sel: ManifestSurface) =>
      surfaceData({ body: `body for ${sel.id}`, surface: sel })
    );
  });

  it("selects the surface named by ?surface=<id> when it matches", async () => {
    const html = await renderPage({ surface: "guide" });

    expect(html).toContain("<h3>Guide</h3>");
  });

  it("falls back to the first surface when ?surface is absent", async () => {
    const html = await renderPage({});

    expect(html).toContain("<h3>Readme</h3>");
  });

  it("falls back to the first surface when ?surface names an unknown id", async () => {
    const html = await renderPage({ surface: "does-not-exist" });

    expect(html).toContain("<h3>Readme</h3>");
  });
});

describe("DocumentationPage — no surfaces in the manifest", () => {
  beforeEach(async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: []
    });
  });

  it("does not crash when there are no surfaces", async () => {
    await expect(renderPage()).resolves.not.toThrow();
  });

  it("shows the 'Surface preview' fallback heading, not a surface title", async () => {
    const html = await renderPage();

    expect(html).toContain("<h3>Surface preview</h3>");
  });

  it("shows the placeholder body text instead of rendered content", async () => {
    const html = await renderPage();

    expect(html).toContain("Select a surface from the manifest groups.");
  });

  it("omits the artifact-meta chip row when no surface is selected", async () => {
    const html = await renderPage();

    expect(html).not.toContain("artifact-meta");
  });

  it("never calls the per-surface data fetcher when there is no surface to select", async () => {
    await renderPage();

    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    expect(getDocumentationSurfaceData).not.toHaveBeenCalled();
  });
});

// ─── DocumentationPage — renderMode: markdown ────────────────────────────────

describe("DocumentationPage — renderMode 'markdown'", () => {
  beforeEach(async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: [README_SURFACE]
    });
  });

  it("renders the resolved renderer's output when the body is present", async () => {
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({ body: "# Hello Markdown", renderMode: "markdown", surface: README_SURFACE })
    );

    const html = await renderPage();

    expect(html).toContain("Hello Markdown");
  });

  it("falls back to 'Unreadable file.' when body is null and errorMessage is unset", async () => {
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({ body: null, errorMessage: null, renderMode: "markdown", surface: README_SURFACE })
    );

    const html = await renderPage();

    expect(html).toContain("Unreadable file.");
  });

  it("shows the provided errorMessage when body is null and errorMessage is set", async () => {
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({
        body: null,
        errorMessage: "Permission denied reading readme.md",
        renderMode: "markdown",
        surface: README_SURFACE
      })
    );

    const html = await renderPage();

    expect(html).toContain("Permission denied reading readme.md");
    expect(html).not.toContain("Unreadable file.");
  });
});

// ─── DocumentationPage — renderMode: api ─────────────────────────────────────

describe("DocumentationPage — renderMode 'api'", () => {
  const OPENAPI_SURFACE = surface({
    id: "openapi",
    path: "docs/openapi.yaml",
    renderer: "api_reference",
    title: "OpenAPI",
    type: "yaml"
  });

  beforeEach(async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: [OPENAPI_SURFACE]
    });
  });

  it("renders through the ApiReferenceShell when body is present", async () => {
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({ body: "openapi: 3.1.0\ninfo:\n  title: Sample\n", renderMode: "api", surface: OPENAPI_SURFACE })
    );

    const html = await renderPage();

    expect(html).toContain("shell-api-reference");
  });

  it("falls back to 'Unreadable file.' when body is null and errorMessage is unset", async () => {
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({ body: null, errorMessage: null, renderMode: "api", surface: OPENAPI_SURFACE })
    );

    const html = await renderPage();

    expect(html).toContain("Unreadable file.");
  });
});

// ─── DocumentationPage — renderMode: code ────────────────────────────────────

describe("DocumentationPage — renderMode 'code'", () => {
  const RAW_JSON_SURFACE = surface({
    id: "raw-json",
    path: ".ai-work/raw.json",
    title: "Raw JSON",
    type: "json"
  });
  const VERIFICATION_SURFACE = surface({
    id: "verification",
    path: ".ai-work/VERIFICATION_REPORT.md",
    renderer: "verification_report",
    title: "Verification Report",
    type: "json"
  });

  it("renders through the registry-matched CodeRenderer when the renderer key resolves", async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: [VERIFICATION_SURFACE]
    });
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({ body: "Overall verdict: PASS", renderMode: "code", surface: VERIFICATION_SURFACE })
    );

    const html = await renderPage();

    // renderer-verification is a marker unique to VerificationReportRenderer's
    // wrapper (proves RENDERER_REGISTRY.get("verification_report") was used,
    // not the raw <pre> fallback).
    expect(html).toContain("renderer-verification");
  });

  it("falls back to a raw <pre> code block when no renderer key resolves in the registry", async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: [RAW_JSON_SURFACE]
    });
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({ body: '{"key":"value"}', renderMode: "code", surface: RAW_JSON_SURFACE })
    );

    const html = await renderPage();

    expect(html).toContain('class="code-block"');
    expect(html).toContain("{&quot;key&quot;:&quot;value&quot;}");
    expect(html).not.toContain("renderer-verification");
  });

  it("falls back to 'Unreadable file.' when body is null and errorMessage is unset", async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: [RAW_JSON_SURFACE]
    });
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({ body: null, errorMessage: null, renderMode: "code", surface: RAW_JSON_SURFACE })
    );

    const html = await renderPage();

    expect(html).toContain("Unreadable file.");
  });
});

// ─── DocumentationPage — renderMode: unsupported / error ────────────────────

describe("DocumentationPage — renderMode 'unsupported' and 'error'", () => {
  const WEIRD_SURFACE = surface({ id: "weird", path: "docs/weird.xyz", title: "Weird", type: "xyz" });

  beforeEach(async () => {
    const getDocumentationData = await getMockedGetDocumentationData();
    getDocumentationData.mockResolvedValue({
      groups: [],
      manifestPath: "/fake-project/.ai-state/doc_manifest.yaml",
      surfaces: [WEIRD_SURFACE]
    });
  });

  it("renders the errorMessage directly for renderMode 'unsupported'", async () => {
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({
        body: null,
        errorMessage: "Unsupported surface type for this slice: xyz",
        renderMode: "unsupported",
        surface: WEIRD_SURFACE
      })
    );

    const html = await renderPage();

    expect(html).toContain("Unsupported surface type for this slice: xyz");
  });

  it("renders the errorMessage directly for renderMode 'error'", async () => {
    const getDocumentationSurfaceData = await getMockedGetDocumentationSurfaceData();
    getDocumentationSurfaceData.mockResolvedValue(
      surfaceData({
        body: null,
        errorMessage: "Surface path could not be resolved.",
        renderMode: "error",
        surface: WEIRD_SURFACE
      })
    );

    const html = await renderPage();

    expect(html).toContain("Surface path could not be resolved.");
  });
});
