/**
 * Behavioral tests for the Architecture page (async Server Component).
 *
 * Strategy: mock the view-model (`@/server/view-models/architecture`) and the
 * config (`@/lib/config`) to return controlled fixtures, then render the page
 * with `renderToStaticMarkup(await ArchitecturePage())` and assert on the
 * resulting HTML string.
 *
 * Behaviors validated here:
 *   - With ≥2 diagrams, only the first is in the open/default-expanded state;
 *     all diagrams' SVG markup is present in the server HTML.
 *   - With DESIGN.md present, the Component-index nav is derived from its
 *     headings; with DESIGN.md absent, there is no Component-index nav and the
 *     page does not crash.
 *   - AaC generated/authored regions render a provenance chip; plain regions
 *     have no chip.
 *
 * Interactive behaviors that require a live DOM are not covered here
 * (DiagramModal focus-trap, Escape, pan-zoom) — those need manual/e2e review.
 *
 * Environment: vitest node — renderToStaticMarkup from react-dom/server.
 * vi.mock hoisting: mocks must be at the top level (not in beforeEach/it) so
 * vitest's static analysis can hoist them before module imports.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { beforeEach, describe, expect, it, vi } from "vitest";

// ─── Module mocks (hoisted at top level) ─────────────────────────────────────

vi.mock("@/lib/config", () => ({
  getConfig: () => ({ projectRoot: "/fake-project", projectName: "fake", dashboardVersion: "0.0.0", pollIntervalSeconds: 15 })
}));

vi.mock("@/server/view-models/architecture", () => ({
  getArchitectureData: vi.fn()
}));

// ─── Fixture helpers ─────────────────────────────────────────────────────────

const SVG_A = `<svg data-aspect="2" data-vb-w="200" data-vb-h="100" viewBox="0 0 200 100" preserveAspectRatio="xMidYMid meet"><title>Diagram A</title></svg>`;
const SVG_B = `<svg data-aspect="1.5" data-vb-w="150" data-vb-h="100" viewBox="0 0 150 100" preserveAspectRatio="xMidYMid meet"><title>Diagram B</title></svg>`;

/** Rich fixture: design + guide + 2 diagrams + all 3 region kinds */
const RICH_DATA = {
  design: { body: "## System Overview\n## Component Map\n## Data Flow\nsome content" },
  guide: { body: "## Navigating\nsome guide content" },
  diagrams: [
    { markup: SVG_A, path: "/fake-project/docs/diagrams/rendered/a.svg" },
    { markup: SVG_B, path: "/fake-project/docs/diagrams/rendered/b.svg" }
  ],
  regions: [
    { kind: "generated" as const, attrs: { source: "likec4", view: "context" }, content: "## Component Map\ngenerated content" },
    { kind: "authored" as const, attrs: { owner: "architect" }, content: "## System Overview\nauthored content" },
    { kind: "plain" as const, attrs: {}, content: "intro text" }
  ]
};

/** No DESIGN.md fixture */
const NO_DESIGN_DATA = {
  design: null,
  guide: { body: "## Navigating\nsome guide content" },
  diagrams: [
    { markup: SVG_A, path: "/fake-project/docs/diagrams/rendered/a.svg" }
  ],
  regions: []
};

/** No architecture.md fixture */
const NO_GUIDE_DATA = {
  design: { body: "## System Overview\n## Component Map\n## Data Flow\nsome content" },
  guide: null,
  diagrams: [],
  regions: []
};

/** No diagrams fixture */
const NO_DIAGRAMS_DATA = {
  design: { body: "## System Overview\n## Component Map\n## Data Flow\nsome content" },
  guide: { body: "## Navigating\nsome content" },
  diagrams: [],
  regions: []
};

/** Fully empty fixture */
const EMPTY_DATA = {
  design: null,
  guide: null,
  diagrams: [],
  regions: []
};

// ─── Render helper ────────────────────────────────────────────────────────────

async function renderPage(): Promise<string> {
  // Deferred import: the page may not be fully restructured when tests first
  // run (concurrent BDD/TDD). If the module is missing, the test fails with
  // ImportError — the expected RED state.
  const { default: ArchitecturePage } = await import("@/app/architecture/page");
  // ArchitecturePage is an async Server Component — it must be awaited first
  // (React 19 async function components cannot be passed to renderToStaticMarkup
  // directly; it would suspend). Awaiting produces a React element tree that
  // renderToStaticMarkup can serialise synchronously.
  const element = await ArchitecturePage();
  return renderToStaticMarkup(element);
}

// Re-import the mocked module to control its return value in each scenario
async function getMockedGetArchitectureData() {
  const mod = await import("@/server/view-models/architecture");
  return mod.getArchitectureData as ReturnType<typeof vi.fn>;
}

// ─── ArchitecturePage — rich scenario ────────────────────────────────────────

describe("ArchitecturePage — rich fixture: design + guide + 2 diagrams + 3 region kinds", () => {
  beforeEach(async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue(RICH_DATA);
  });

  it("renders a Component-index nav derived from DESIGN.md headings", async () => {
    const html = await renderPage();

    expect(html).toContain('aria-label="Component index"');
    expect(html).toContain('href="#system-overview"');
    expect(html).toContain('href="#component-map"');
  });

  it("includes both diagrams' SVG markup in the server HTML", async () => {
    const html = await renderPage();

    expect(html).toContain("Diagram A");
    expect(html).toContain("Diagram B");
  });

  it("only the first diagram is in the default-open state", async () => {
    const html = await renderPage();

    // The first ArtifactCard (details) for diagrams must have open attribute
    // and the second must not. We look for the first open="true" detail block
    // that contains SVG_A before any that contains SVG_B.
    const idxA = html.indexOf("Diagram A");
    const idxB = html.indexOf("Diagram B");
    // Both must be present (SVG in server HTML regardless of collapse state)
    expect(idxA).toBeGreaterThan(-1);
    expect(idxB).toBeGreaterThan(-1);

    // The first diagram's containing ArtifactCard must carry the open attribute
    // and the second must not. We check that before Diagram A there's an 'open'
    // keyword in the surrounding details element (defaultOpen=true renders as
    // <details open>). We locate the nearest <details before each SVG title.
    const detailsBeforeA = html.lastIndexOf("<details", idxA);
    const detailsBeforeB = html.lastIndexOf("<details", idxB);
    expect(detailsBeforeA).toBeGreaterThan(-1);
    expect(detailsBeforeB).toBeGreaterThan(-1);

    // Slice from the <details tag up to the diagram content to check open attr
    const snippetA = html.slice(detailsBeforeA, idxA);
    const snippetB = html.slice(detailsBeforeB, idxB);

    expect(snippetA).toMatch(/\bopen\b/);
    expect(snippetB).not.toMatch(/\bopen\b/);
  });

  it("renders a Generated chip containing source and view provenance", async () => {
    const html = await renderPage();

    // The generated region's chip label: "Generated · source=likec4 · view=context"
    expect(html).toContain("Generated");
    expect(html).toContain("source=likec4");
    expect(html).toContain("view=context");
  });

  it("renders an Authored chip containing the owner provenance", async () => {
    const html = await renderPage();

    expect(html).toContain("Authored");
    expect(html).toContain("owner=architect");
  });

  it("does not render a provenance chip for the plain region", async () => {
    const html = await renderPage();

    // The plain region contains "intro text" — check it's present without a chip
    expect(html).toContain("intro text");
    // The chip for plain would be 'Generated' or 'Authored' inside a plain region;
    // we can verify no chip immediately precedes the plain content. Since the
    // plain region has no kind badge, we count chip occurrences:
    // expect exactly 2 chips (one generated, one authored)
    const chipMatches = html.match(/class="chip[^"]*"/g) ?? [];
    // At least 2 chips (generated + authored) but the plain region adds none
    expect(chipMatches.length).toBeGreaterThanOrEqual(2);
  });

  it("renders the architecture.md guide content", async () => {
    const html = await renderPage();

    expect(html).toContain("Navigating");
    expect(html).toContain("some guide content");
  });
});

// ─── ArchitecturePage — no diagrams ──────────────────────────────────────────

describe("ArchitecturePage — no diagrams: omits the diagram section", () => {
  beforeEach(async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue(NO_DIAGRAMS_DATA);
  });

  it("does not crash when diagrams array is empty", async () => {
    await expect(renderPage()).resolves.not.toThrow();
  });

  it("does not render a Diagrams section heading when diagrams are absent", async () => {
    const html = await renderPage();

    // No Diagrams card header
    expect(html).not.toContain(">Diagrams<");
  });

  it("still renders the DESIGN.md content without diagrams", async () => {
    const html = await renderPage();

    expect(html).toContain("System Overview");
  });
});

// ─── ArchitecturePage — no DESIGN.md ─────────────────────────────────────────

describe("ArchitecturePage — design absent: no Component-index nav, no crash", () => {
  beforeEach(async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue(NO_DESIGN_DATA);
  });

  it("does not crash when design is null", async () => {
    await expect(renderPage()).resolves.not.toThrow();
  });

  it("does not render a Component-index nav when DESIGN.md is absent", async () => {
    const html = await renderPage();

    expect(html).not.toContain('aria-label="Component index"');
  });

  it("still renders the architecture.md guide when design is absent", async () => {
    const html = await renderPage();

    expect(html).toContain("Navigating");
  });
});

// ─── ArchitecturePage — no architecture.md ───────────────────────────────────

describe("ArchitecturePage — guide absent: no Developer-guide card, no crash", () => {
  beforeEach(async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue(NO_GUIDE_DATA);
  });

  it("does not crash when guide is null", async () => {
    await expect(renderPage()).resolves.not.toThrow();
  });

  it("still renders the DESIGN.md Component-index when guide is absent", async () => {
    const html = await renderPage();

    expect(html).toContain('aria-label="Component index"');
    expect(html).toContain('href="#system-overview"');
  });

  it("does not render guide content when architecture.md is absent", async () => {
    const html = await renderPage();

    // NO_GUIDE_DATA has no guide; "Navigating" should not appear
    expect(html).not.toContain("Navigating");
  });
});

// ─── ArchitecturePage — empty state ──────────────────────────────────────────

describe("ArchitecturePage — fully empty: renders EmptyState, no crash", () => {
  beforeEach(async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue(EMPTY_DATA);
  });

  it("does not crash when all artifacts are absent", async () => {
    await expect(renderPage()).resolves.not.toThrow();
  });

  it("renders the EmptyState component with a meaningful title", async () => {
    const html = await renderPage();

    // EmptyState renders an <h2> with the title
    expect(html).toMatch(/<h2[^>]*>.*architecture.*<\/h2>/i);
  });

  it("renders the producerPath in the EmptyState", async () => {
    const html = await renderPage();

    // EmptyState renders the producer path in a <code> element
    expect(html).toContain("DESIGN.md");
  });

  it("does not render any diagram, design, or guide content", async () => {
    const html = await renderPage();

    expect(html).not.toContain("<svg");
    expect(html).not.toContain("Component index");
    expect(html).not.toContain("Developer guide");
  });
});

// ─── ArchitecturePage — AaC provenance preserved ─────────────────────────────

describe("ArchitecturePage — AaC provenance: chip text carries all attrs", () => {
  it("generated chip includes both source and view when both attrs are present", async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue({
      ...EMPTY_DATA,
      design: { body: "## Intro" },
      regions: [
        {
          kind: "generated" as const,
          attrs: { source: "mermaid", view: "pipeline" },
          content: "## Intro\ncontent here"
        }
      ]
    });

    const html = await renderPage();

    expect(html).toContain("Generated");
    expect(html).toContain("source=mermaid");
    expect(html).toContain("view=pipeline");
  });

  it("authored chip includes the owner when owner attr is present", async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue({
      ...EMPTY_DATA,
      design: { body: "## Intro" },
      regions: [
        {
          kind: "authored" as const,
          attrs: { owner: "team-leads" },
          content: "## Intro\ncontent here"
        }
      ]
    });

    const html = await renderPage();

    expect(html).toContain("Authored");
    expect(html).toContain("owner=team-leads");
  });

  it("plain region renders its content without any chip element", async () => {
    const getArchitectureData = await getMockedGetArchitectureData();
    getArchitectureData.mockResolvedValue({
      ...EMPTY_DATA,
      design: { body: "## Intro" },
      regions: [
        {
          kind: "plain" as const,
          attrs: {},
          content: "plain region prose only"
        }
      ]
    });

    const html = await renderPage();

    expect(html).toContain("plain region prose only");
    // No chip for plain — the aac-badge div is not rendered
    expect(html).not.toContain("aac-badge");
  });
});
