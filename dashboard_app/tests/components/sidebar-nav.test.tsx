// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SidebarNav } from "@/components/sidebar-nav";
import type { SidebarSignals } from "@/server/view-models/sidebar-signals";

const navigation = vi.hoisted(() => ({ pathname: "/" }));

vi.mock("next/navigation", () => ({ usePathname: () => navigation.pathname }));

const LAYOUT_SOURCE = readFileSync(path.join(process.cwd(), "src/app/layout.tsx"), "utf8");

const NO_SIGNALS: SidebarSignals = { activeWorkshops: 0, sentinelGrade: null };

function renderNav(signals: SidebarSignals = NO_SIGNALS, pathname = "/") {
  navigation.pathname = pathname;
  return render(<SidebarNav signals={signals} />);
}

function linkHrefs(): Array<string | null> {
  return screen.getAllByRole("link").map((link) => link.getAttribute("href"));
}

afterEach(cleanup);

describe("SidebarNav structure", () => {
  it("lists the Overview first, then the Health, Work and Knowledge groups in order", () => {
    renderNav();

    expect(linkHrefs()).toEqual([
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
    for (const [label, hrefs] of [
      ["Health", ["/sentinel", "/metrics", "/evals"]],
      ["Work", ["/workshops", "/roadmap"]],
      ["Knowledge", ["/architecture", "/adrs", "/documentation"]]
    ] as const) {
      const group = screen.getByRole("group", { name: label });
      const inGroup = within(group).getAllByRole("link").map((link) => link.getAttribute("href"));
      expect(inGroup).toEqual(hrefs);
    }
  });

  it("gives the Overview no group label and makes no label a link", () => {
    renderNav();

    expect(screen.getAllByRole("group")).toHaveLength(3);
    for (const label of ["Health", "Work", "Knowledge"]) {
      expect(screen.getByText(label).closest("a")).toBeNull();
    }
  });

  it.each([
    ["/", "Overview"],
    ["/evals", "Evals"],
    ["/documentation", "Documentation"]
  ])("marks only the current page (%s)", (pathname, label) => {
    renderNav(NO_SIGNALS, pathname);

    const current = screen.getAllByRole("link").filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual([label]);
  });
});

describe("SidebarNav signals", () => {
  it("renders the sentinel grade as a toned chip for its grade variant", () => {
    renderNav({ activeWorkshops: 0, sentinelGrade: "C" });

    const chip = within(screen.getByRole("link", { name: /sentinel/i })).getByText("C");
    expect(chip.className).toContain("chip--grade-c");
    expect(chip.closest("[data-tone]")?.getAttribute("data-tone")).toBe("warn");
  });

  it.each([
    ["A", "chip--grade-a", "good"],
    ["D", "chip--grade-d", "bad"],
    ["F", "chip--grade-f", "bad"]
  ])("maps grade %s to %s with tone %s", (grade, chipClass, tone) => {
    renderNav({ activeWorkshops: 0, sentinelGrade: grade });

    const chip = within(screen.getByRole("link", { name: /sentinel/i })).getByText(grade);
    expect(chip.className).toContain(chipClass);
    expect(chip.closest("[data-tone]")?.getAttribute("data-tone")).toBe(tone);
  });

  it("shows the active workshop count on the Workshops row", () => {
    renderNav({ activeWorkshops: 2, sentinelGrade: null });

    expect(within(screen.getByRole("link", { name: /workshops/i })).getByText("2")).toBeDefined();
  });

  it("omits a signal whose family is absent", () => {
    renderNav(NO_SIGNALS);

    expect(document.querySelectorAll(".nav-card__signal")).toHaveLength(0);
    expect(document.querySelector("[data-tone]")).toBeNull();
  });
});

describe("root layout", () => {
  it("does not mount the global live refresh", () => {
    expect(LAYOUT_SOURCE).not.toContain("LiveRefresh");
    expect(LAYOUT_SOURCE).not.toContain("live-refresh");
  });

  it("tolerates the head script's pre-hydration data-theme attribute", () => {
    expect(LAYOUT_SOURCE).toContain("suppressHydrationWarning");
  });
});
