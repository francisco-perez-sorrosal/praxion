/**
 * Behavioral tests for AppHeader — the global page header component.
 *
 * AppHeader renders:
 *   - an <h1> with the surface title
 *   - a <time dateTime={...}> "data as of" stamp when dataAsOf is provided
 *   - a breadcrumb <nav aria-label="Breadcrumb"> only when breadcrumb.length > 1
 *
 * Uses renderToStaticMarkup (react-dom/server) in the vitest node environment,
 * matching the pattern established in diagram-frame.test.ts.
 *
 * Imports are deferred into each test body for the concurrent BDD/TDD RED handshake.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { describe, expect, it } from "vitest";

// ─── AppHeader ────────────────────────────────────────────────────────────────

describe("AppHeader — renders title as the page-level heading", () => {
  it("renders an h1 containing the supplied title", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(createElement(AppHeader, { title: "Architecture" }));

    expect(html).toContain("<h1");
    expect(html).toContain("Architecture");
  });

  it("renders a time element with a dateTime attribute when dataAsOf is provided", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const mtime = new Date("2026-05-10T14:32:00Z");
    const html = renderToStaticMarkup(
      createElement(AppHeader, { title: "Sentinel", dataAsOf: mtime })
    );

    expect(html).toContain("<time");
    // The ISO string must appear somewhere as the dateTime attribute value
    expect(html.toLowerCase()).toMatch(/datetime=/);
  });

  it("omits the time element when dataAsOf is not provided", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(createElement(AppHeader, { title: "Workshops" }));

    expect(html).not.toContain("<time");
  });

  it("omits the time element when dataAsOf is null", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(
      createElement(AppHeader, { title: "ADRs", dataAsOf: null })
    );

    expect(html).not.toContain("<time");
  });
});

describe("AppHeader — breadcrumb nav is rendered only for multi-segment paths", () => {
  it("renders a breadcrumb nav when breadcrumb has more than one entry", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(
      createElement(AppHeader, {
        title: "Documentation",
        breadcrumb: [
          { label: "Overview", href: "/overview" },
          { label: "Documentation", href: "/documentation" }
        ]
      })
    );

    expect(html).toContain('aria-label');
    expect(html).toContain("breadcrumb");
    expect(html).toContain("<nav");
  });

  it("omits the breadcrumb nav when breadcrumb has exactly one entry", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(
      createElement(AppHeader, {
        title: "Architecture",
        breadcrumb: [{ label: "Architecture", href: "/architecture" }]
      })
    );

    // Single-item breadcrumb is not navigational context — no nav needed
    expect(html).not.toContain("<nav");
  });

  it("omits the breadcrumb nav when breadcrumb is empty", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(
      createElement(AppHeader, { title: "Metrics", breadcrumb: [] })
    );

    expect(html).not.toContain("<nav");
  });

  it("omits the breadcrumb nav when breadcrumb prop is absent", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(createElement(AppHeader, { title: "Roadmap" }));

    expect(html).not.toContain("<nav");
  });
});

describe("AppHeader — does not crash on edge-case props", () => {
  it("renders without error when only a title is supplied", async () => {
    const { AppHeader } = await import("@/components/app-header");

    expect(() =>
      renderToStaticMarkup(createElement(AppHeader, { title: "Minimal" }))
    ).not.toThrow();
  });

  it("renders without error with all optional props provided", async () => {
    const { AppHeader } = await import("@/components/app-header");

    expect(() =>
      renderToStaticMarkup(
        createElement(AppHeader, {
          title: "Full props",
          dataAsOf: new Date("2026-05-12T00:00:00Z"),
          breadcrumb: [
            { label: "Home", href: "/" },
            { label: "Full props", href: "/full" }
          ]
        })
      )
    ).not.toThrow();
  });
});
