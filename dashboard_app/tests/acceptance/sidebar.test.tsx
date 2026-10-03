// @vitest-environment jsdom
/**
 * Acceptance: the sidebar groups the surfaces by intent, carries live
 * signals, marks the current page and offers a persisted theme choice that
 * applies before the page paints.
 */

import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  appliedTheme,
  hasToken,
  isKeyboardReachable,
  mountShell,
  navLink,
  renderShellDocument,
  sidebarOf,
  textOf,
  themeControls,
  useDashboardHarness
} from "./drivers/dashboard";
import { emptyProject, fullProject } from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

const ARROW = /[↑↓↗↘→←▲▼△▽⬆⬇]/;

function isBefore(a: Node, b: Node): boolean {
  return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

/** The innermost element of the sidebar whose whole text is the label. */
function groupLabel(sidebar: Element, label: string): Element {
  const candidates = Array.from(sidebar.querySelectorAll("*")).filter(
    (el) => textOf(el).toLowerCase() === label.toLowerCase()
  );
  const innermost = candidates.find((el) => !candidates.some((other) => other !== el && el.contains(other)));
  if (!innermost) throw new Error(`No sidebar group label "${label}" in: ${textOf(sidebar)}`);
  return innermost;
}

describe("the sidebar navigation", () => {
  it("lists the Overview first, then Health, Work and Knowledge groups holding their surfaces in order", async () => {
    const sidebar = sidebarOf(await renderShellDocument(await fullProject()));

    const hrefs = Array.from(sidebar.querySelectorAll("nav a[href^='/']")).map((a) => a.getAttribute("href"));
    const firstOccurrences = hrefs.filter((href, i) => hrefs.indexOf(href) === i);
    expect(firstOccurrences).toEqual([
      "/",
      "/sentinel",
      "/metrics",
      "/evals",
      "/workshops",
      "/roadmap",
      "/architecture",
      "/adrs",
      "/documentation"
    ]);

    const health = groupLabel(sidebar, "Health");
    const work = groupLabel(sidebar, "Work");
    const knowledge = groupLabel(sidebar, "Knowledge");
    expect(isBefore(navLink(sidebar, "/"), health)).toBe(true);
    expect(isBefore(health, navLink(sidebar, "/sentinel"))).toBe(true);
    expect(isBefore(navLink(sidebar, "/evals"), work)).toBe(true);
    expect(isBefore(work, navLink(sidebar, "/workshops"))).toBe(true);
    expect(isBefore(navLink(sidebar, "/roadmap"), knowledge)).toBe(true);
    expect(isBefore(knowledge, navLink(sidebar, "/architecture"))).toBe(true);
  });

  it("does not make the group labels links", async () => {
    const sidebar = sidebarOf(await renderShellDocument(await fullProject()));

    for (const label of ["Health", "Work", "Knowledge"]) {
      expect(groupLabel(sidebar, label).closest("a")).toBeNull();
    }
  });

  it("marks the current page and only the current page", async () => {
    const sidebar = sidebarOf(await renderShellDocument(await fullProject(), "/evals"));

    expect(navLink(sidebar, "/evals").getAttribute("aria-current")).toBe("page");
    expect(sidebar.querySelectorAll("[aria-current='page']")).toHaveLength(1);
  });
});

describe("the sidebar live signals", () => {
  it("shows the latest sentinel grade on the Sentinel entry", async () => {
    const sidebar = sidebarOf(await renderShellDocument(await fullProject()));

    expect(hasToken(textOf(navLink(sidebar, "/sentinel")), "C")).toBe(true);
  });

  it("shows the metrics health word with an arrow glyph on the Metrics entry", async () => {
    const entry = textOf(navLink(sidebarOf(await renderShellDocument(await fullProject())), "/metrics"));

    expect(entry).toMatch(/worsening/i);
    expect(entry).toMatch(ARROW);
  });

  it("shows the latest quality-eval run's failure count on the Evals entry", async () => {
    const entry = textOf(navLink(sidebarOf(await renderShellDocument(await fullProject())), "/evals"));

    expect(hasToken(entry, "3")).toBe(true);
  });

  it("counts only the workshops active in the last seven days on the Workshops entry", async () => {
    // FULL: alpha and beta are active; gamma is stale; delta and epsilon are finished
    const entry = textOf(navLink(sidebarOf(await renderShellDocument(await fullProject())), "/workshops"));

    expect(entry.match(/\d+/g)).toEqual(["2"]);
  });

  it("omits every signal whose artifact family is absent", async () => {
    const sidebar = sidebarOf(await renderShellDocument(await emptyProject()));

    expect(textOf(navLink(sidebar, "/sentinel"))).not.toMatch(/(^|[^A-Za-z])[A-F]([^A-Za-z]|$)/);
    expect(textOf(navLink(sidebar, "/metrics"))).not.toMatch(ARROW);
    expect(textOf(navLink(sidebar, "/metrics"))).not.toMatch(/improving|stable|worsening|baseline/i);
    expect(textOf(navLink(sidebar, "/evals"))).not.toMatch(/\d/);
    expect(textOf(navLink(sidebar, "/workshops"))).not.toMatch(/\d/);
  });
});

describe("the theme choice", () => {
  it("offers system, light and dark as keyboard-reachable controls in the sidebar", async () => {
    const sidebar = sidebarOf(await mountShell(await fullProject()));
    const controls = themeControls(sidebar);

    for (const choice of ["system", "light", "dark"] as const) {
      expect(controls[choice], `no ${choice} theme control`).toBeDefined();
      expect(isKeyboardReachable(controls[choice] as Element)).toBe(true);
    }
  });

  it("applies and remembers the chosen theme", async () => {
    const sidebar = sidebarOf(await mountShell(await fullProject()));
    const user = userEvent.setup();

    for (const choice of ["dark", "light"] as const) {
      const control = themeControls(sidebar)[choice];
      if (!control) throw new Error(`no ${choice} theme control`);
      await act(async () => {
        if (control.tagName === "SELECT") await user.selectOptions(control, choice);
        else await user.click(control);
      });

      expect(window.localStorage.getItem("praxion-theme")).toBe(choice);
      expect(appliedTheme()).toBe(choice);
    }
  });

  it.each(["dark", "light"] as const)(
    "applies a remembered %s theme from the document head, before the body paints",
    async (remembered) => {
      const shell = await renderShellDocument(await fullProject());
      const headScripts = Array.from(shell.head.querySelectorAll("script")).filter((script) =>
        (script.textContent ?? "").includes("praxion-theme")
      );
      expect(headScripts.length, "no inline head script reads the remembered theme").toBeGreaterThan(0);

      window.localStorage.setItem("praxion-theme", remembered);
      for (const script of headScripts) new Function(script.textContent ?? "")();

      expect(appliedTheme()).toBe(remembered);
    }
  );
});
