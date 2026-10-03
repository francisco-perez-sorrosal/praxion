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

import { afterEach, describe, expect, it, vi } from "vitest";

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

describe("AppHeader — the data-as-of label names the local calendar day", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("runs in a zone that is not UTC, or the pins below could not fail", () => {
    // vitest.config.ts pins TZ; in UTC the local day and the UTC day coincide at noon only.
    expect(new Date(2026, 9, 1, 23, 30).getTimezoneOffset()).not.toBe(0);
  });

  it("labels an earlier day with its local date, not the UTC date", async () => {
    const { AppHeader } = await import("@/components/app-header");
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 2, 12, 0, 0));

    // 23:30 local on 1 Oct: the UTC date is 2 Oct in every zone west of Greenwich.
    const html = renderToStaticMarkup(
      createElement(AppHeader, { title: "Sentinel", dataAsOf: new Date(2026, 9, 1, 23, 30, 0) })
    );

    expect(html).toContain(">2026-10-01</time>");
  });

  it("labels today with the local clock time", async () => {
    const { AppHeader } = await import("@/components/app-header");
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 2, 12, 0, 0));

    const html = renderToStaticMarkup(
      createElement(AppHeader, { title: "Sentinel", dataAsOf: new Date(2026, 9, 2, 9, 5, 0) })
    );

    expect(html).toContain(">09:05</time>");
  });
});

describe("AppHeader — the live cue appears only on pages that refresh", () => {
  it("omits the live cue by default", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(
      createElement(AppHeader, { title: "Metrics", dataAsOf: new Date("2026-05-10T14:32:00Z") })
    );

    expect(html).not.toContain("live");
  });

  it("renders the live cue when the page refreshes", async () => {
    const { AppHeader } = await import("@/components/app-header");

    const html = renderToStaticMarkup(
      createElement(AppHeader, { title: "Workshops", dataAsOf: new Date("2026-05-10T14:32:00Z"), live: true })
    );

    expect(html).toContain("live ⟳");
  });

  it("PageShell passes the cue through to its header", async () => {
    const { PageShell } = await import("@/components/page-shell");
    const dataAsOf = new Date("2026-05-10T14:32:00Z");

    const still = renderToStaticMarkup(createElement(PageShell, { children: "body", dataAsOf, title: "ADRs" }));
    const refreshing = renderToStaticMarkup(createElement(PageShell, { children: "body", dataAsOf, live: true, title: "Overview" }));

    expect(still).not.toContain("live");
    expect(refreshing).toContain("live ⟳");
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
