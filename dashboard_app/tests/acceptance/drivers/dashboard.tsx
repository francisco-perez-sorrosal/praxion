/**
 * Acceptance driver for the dashboard: renders a route (or the root layout
 * with its sidebar) for a fixture project root, the way Next.js would serve
 * it, and reads the observable result back out of the DOM.
 *
 * The route modules are reached by their App Router locations
 * (`src/app/<route>/page.tsx`, `src/app/layout.tsx`) and the project root is
 * selected through `PRAXION_PROJECT_ROOT`, the dashboard's launch contract.
 * Async Server Components are resolved before rendering (a stand-in for the
 * RSC pass), then either serialized to static HTML (what the browser
 * receives) or mounted in jsdom (what runs after hydration).
 *
 * Every test file that uses this driver must register the navigation stub:
 *
 *   vi.mock("next/navigation", async (importOriginal) => ({
 *     ...(await importOriginal<object>()),
 *     ...(await import("./drivers/navigation-stub")).navigationOverrides
 *   }));
 */

process.env.TZ = "UTC";

import { act, cleanup, render } from "@testing-library/react";
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, vi } from "vitest";

import { FIXED_NOW, removeProjectRoots } from "./fixture-project";
import { navigation } from "./navigation-stub";

// ─── Routes ───────────────────────────────────────────────────────────────────

type PageModule = { default: (props: { searchParams: Promise<Record<string, string>> }) => unknown };

const ROUTES: Record<string, () => Promise<PageModule>> = {
  "/": () => import("@/app/page") as Promise<PageModule>,
  "/sentinel": () => import("@/app/sentinel/page") as Promise<PageModule>,
  "/metrics": () => import("@/app/metrics/page") as Promise<PageModule>,
  "/evals": () => import("@/app/evals/page") as Promise<PageModule>,
  "/workshops": () => import("@/app/workshops/page") as Promise<PageModule>,
  "/roadmap": () => import("@/app/roadmap/page") as Promise<PageModule>,
  "/architecture": () => import("@/app/architecture/page") as Promise<PageModule>,
  "/adrs": () => import("@/app/adrs/page") as Promise<PageModule>,
  "/documentation": () => import("@/app/documentation/page") as Promise<PageModule>
};

export type Route = keyof typeof ROUTES;

/** Every surface route, the Overview first. */
export const ALL_ROUTES = Object.keys(ROUTES) as Route[];

/** The surfaces reached from the sidebar, without the Overview. */
export const SURFACE_ROUTES = ALL_ROUTES.filter((route) => route !== "/");

// ─── Harness lifecycle ────────────────────────────────────────────────────────

const ENV_KEYS = ["PRAXION_PROJECT_ROOT", "PRAXION_DASHBOARD_POLL_SECONDS"] as const;

/**
 * Registers the per-test lifecycle: the clock frozen at FIXED_NOW (Date only),
 * an in-memory localStorage, and teardown of env, DOM and fixture roots.
 */
export function useDashboardHarness(): void {
  const saved: Partial<Record<(typeof ENV_KEYS)[number], string | undefined>> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS) saved[key] = process.env[key];
    vi.useFakeTimers({ toFake: ["Date"], now: FIXED_NOW });
    installBrowserStorage();
    navigation.reset();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("class");
    document.documentElement.removeAttribute("style");
  });

  afterEach(async () => {
    cleanup();
    vi.useRealTimers();
    for (const key of ENV_KEYS) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
    await removeProjectRoots();
  });
}

function selectProject(projectRoot: string, pollSeconds?: number): void {
  process.env.PRAXION_PROJECT_ROOT = projectRoot;
  if (pollSeconds === undefined) delete process.env.PRAXION_DASHBOARD_POLL_SECONDS;
  else process.env.PRAXION_DASHBOARD_POLL_SECONDS = String(pollSeconds);
}

/** jsdom under this Node lacks a working localStorage; give it a real Storage. */
function installBrowserStorage(): void {
  const data = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => (data.has(key) ? (data.get(key) as string) : null),
    key: (index) => Array.from(data.keys())[index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, String(value))
  };
  Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
}

// ─── Server-tree resolution ───────────────────────────────────────────────────

function isThenable(value: unknown): value is PromiseLike<unknown> {
  return typeof (value as { then?: unknown } | null)?.then === "function";
}

function isAsyncFunction(value: unknown): value is (props: unknown) => Promise<ReactNode> {
  return typeof value === "function" && value.constructor?.name === "AsyncFunction";
}

/** Awaits every async Server Component in the tree, leaving the rest intact. */
async function resolveServerTree(node: unknown): Promise<ReactNode> {
  if (isThenable(node)) return resolveServerTree(await node);
  if (Array.isArray(node)) return Promise.all(node.map(resolveServerTree));
  if (!isValidElement(node)) return node as ReactNode;
  const element = node as ReactElement<Record<string, unknown>>;
  if (isAsyncFunction(element.type)) {
    return resolveServerTree(await element.type(element.props));
  }
  const nextProps: Record<string, unknown> = {};
  let changed = false;
  for (const [key, value] of Object.entries(element.props ?? {})) {
    if (key === "children" || isValidElement(value)) {
      const resolved = await resolveServerTree(value);
      if (resolved !== value) {
        nextProps[key] = resolved;
        changed = true;
      }
    }
  }
  return changed ? cloneElement(element, nextProps) : element;
}

async function resolveRoute(route: Route, searchParams: Record<string, string>): Promise<ReactNode> {
  const load = ROUTES[route];
  if (!load) throw new Error(`Unknown route ${route}`);
  const { default: Page } = await load();
  return resolveServerTree(Page({ searchParams: Promise.resolve(searchParams) }));
}

// ─── Rendering ────────────────────────────────────────────────────────────────

export type RouteOptions = {
  pollSeconds?: number;
  searchParams?: Record<string, string>;
};

/**
 * The page as the browser first receives it: server-rendered HTML, parsed
 * into a detached container. Throws when the route cannot render (including
 * a redirect, which Next.js signals by throwing).
 */
export async function renderRoute(route: Route, projectRoot: string, options: RouteOptions = {}): Promise<HTMLElement> {
  selectProject(projectRoot, options.pollSeconds);
  navigation.pathname = route;
  const tree = await resolveRoute(route, options.searchParams ?? {});
  const container = document.createElement("div");
  container.innerHTML = renderToStaticMarkup(<>{tree}</>);
  return container;
}

export type MountedRoute = {
  container: HTMLElement;
  /** Advances the page's timers by the given seconds. */
  advanceSeconds: (seconds: number) => Promise<void>;
  /** How many times the page asked the router to re-render it. */
  refreshCount: () => number;
};

/** The page live in jsdom, with every timer under the test's control. */
export async function mountRoute(route: Route, projectRoot: string, options: RouteOptions = {}): Promise<MountedRoute> {
  selectProject(projectRoot, options.pollSeconds);
  navigation.pathname = route;
  const tree = await resolveRoute(route, options.searchParams ?? {});
  vi.useRealTimers();
  vi.useFakeTimers({ now: FIXED_NOW });
  const { container } = render(<>{tree}</>);
  return {
    container,
    advanceSeconds: async (seconds) => {
      await act(async () => {
        vi.advanceTimersByTime(seconds * 1000);
      });
    },
    refreshCount: () => navigation.refresh.mock.calls.length
  };
}

async function resolveShell(projectRoot: string, pathname: Route): Promise<ReactNode> {
  selectProject(projectRoot);
  navigation.pathname = pathname;
  const { default: RootLayout } = await import("@/app/layout");
  const layout = RootLayout as unknown as (props: { children: ReactNode }) => unknown;
  return resolveServerTree(layout({ children: <main data-testid="page-slot">page</main> }));
}

/** The root layout's server HTML as a parsed document (head included). */
export async function renderShellDocument(projectRoot: string, pathname: Route = "/"): Promise<Document> {
  const tree = await resolveShell(projectRoot, pathname);
  const html = `<!DOCTYPE html>${renderToStaticMarkup(<>{tree}</>)}`;
  return new DOMParser().parseFromString(html, "text/html");
}

/** The root layout live in jsdom, for interacting with the sidebar. */
export async function mountShell(projectRoot: string, pathname: Route = "/"): Promise<HTMLElement> {
  const tree = await resolveShell(projectRoot, pathname);
  const silenced = vi.spyOn(console, "error").mockImplementation(() => undefined);
  try {
    return render(<>{tree}</>).container;
  } finally {
    silenced.mockRestore();
  }
}

// ─── Reading the page ─────────────────────────────────────────────────────────

/**
 * Visible text with whitespace collapsed. Text from different elements is
 * kept apart by a space ("Sentinel" + "C" reads "Sentinel C", not
 * "SentinelC"); text nodes of one element are joined as written.
 */
export function textOf(element: Element | null | undefined): string {
  if (!element) return "";
  const walker = element.ownerDocument.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let text = "";
  let previousParent: Node | null = null;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (previousParent !== null && node.parentNode !== previousParent) text += " ";
    text += node.nodeValue ?? "";
    previousParent = node.parentNode;
  }
  return text.replace(/\s+/g, " ").trim();
}

/** The sidebar of a rendered shell. */
export function sidebarOf(scope: ParentNode): HTMLElement {
  const aside = scope.querySelector("aside");
  if (!aside) throw new Error("No sidebar (<aside>) in the rendered shell");
  return aside as HTMLElement;
}

/** The navigation link to a surface. */
export function navLink(scope: ParentNode, href: string): HTMLAnchorElement {
  const link = scope.querySelector(`nav a[href="${href}"]`);
  if (!link) throw new Error(`No navigation link to ${href}`);
  return link as HTMLAnchorElement;
}

/** The "data as of" stamp in the page header, or null when absent. */
export function dataAsOf(scope: ParentNode): { at: Date; text: string } | null {
  const time = scope.querySelector("header time[datetime]");
  if (!time) return null;
  return { at: new Date(time.getAttribute("datetime") as string), text: textOf(time) };
}

/**
 * A card or tile: the nearest article, section or link around the first
 * heading whose text matches.
 */
export function cardTitled(scope: ParentNode, title: RegExp): HTMLElement | null {
  const heading = Array.from(scope.querySelectorAll("h1, h2, h3, h4, h5, h6")).find((h) => title.test(textOf(h)));
  return (heading?.closest("article, section, a[href]") as HTMLElement | null) ?? null;
}

/** The headings, in document order, that match any of the given titles. */
export function headingOrder(scope: ParentNode, titles: RegExp[]): number[] {
  const headings = Array.from(scope.querySelectorAll("h2, h3, h4")).map(textOf);
  return titles.map((title) => headings.findIndex((text) => title.test(text)));
}

/** A card's text without its heading. */
export function bodyTextOf(card: Element): string {
  const clone = card.cloneNode(true) as Element;
  clone.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((h) => h.remove());
  return textOf(clone);
}

/** Whether the element, a descendant, or its enclosing link points at href. */
export function linksTo(element: Element, href: string): boolean {
  const own = element.closest("a[href]");
  if (own?.getAttribute("href") === href) return true;
  return element.querySelector(`a[href="${href}"]`) !== null;
}

export type Disclosure = { element: Element; open: boolean; content: Element | null };

/**
 * A disclosure labelled by the given text: a `<details>` whose `<summary>`
 * matches, or a button with `aria-expanded` whose text matches.
 */
export function disclosureLabelled(scope: ParentNode, label: RegExp): Disclosure | null {
  for (const details of Array.from(scope.querySelectorAll("details"))) {
    const summary = details.querySelector(":scope > summary");
    if (summary && label.test(textOf(summary))) {
      return { element: details, open: details.hasAttribute("open"), content: details };
    }
  }
  for (const button of Array.from(scope.querySelectorAll("button[aria-expanded], [role='button'][aria-expanded]"))) {
    if (label.test(textOf(button))) {
      const controlled = button.getAttribute("aria-controls");
      const content = controlled ? (button.ownerDocument.getElementById(controlled) ?? null) : null;
      return { element: button, open: button.getAttribute("aria-expanded") === "true", content };
    }
  }
  return null;
}

/** A copy of the scope with every disclosure's hidden body removed. */
export function withoutDisclosureBodies(scope: Element): Element {
  const clone = scope.cloneNode(true) as Element;
  clone.querySelectorAll("details").forEach((details) => {
    Array.from(details.children).forEach((child) => {
      if (child.tagName !== "SUMMARY") child.remove();
    });
  });
  clone.querySelectorAll("[aria-expanded][aria-controls]").forEach((button) => {
    const id = button.getAttribute("aria-controls");
    if (id) clone.querySelector(`[id="${id}"]`)?.remove();
  });
  return clone;
}

/**
 * The number shown with a label (a tile such as "Critical 1" or
 * "3 FAIL"): inside the innermost element holding both, the number closest
 * to the label. Tables and selectors are skipped (history, not tiles). Null when
 * no element holds both.
 */
export function labelledNumber(scope: Element, label: RegExp): number | null {
  const holders = Array.from(scope.querySelectorAll("*")).filter(
    (el) => !el.closest("table, select") && label.test(textOf(el)) && /\d/.test(textOf(el))
  );
  const innermost = holders.filter((el) => !holders.some((other) => other !== el && el.contains(other)));
  for (const el of innermost) {
    const text = textOf(el);
    const labelMatch = new RegExp(label.source, label.flags.replace("g", "")).exec(text);
    if (!labelMatch) continue;
    const labelStart = labelMatch.index;
    const labelEnd = labelStart + labelMatch[0].length;
    let best: { value: number; distance: number } | null = null;
    for (const m of text.matchAll(/\d[\d,]*(?:\.\d+)?/g)) {
      const start = m.index ?? 0;
      const end = start + m[0].length;
      const distance = end <= labelStart ? labelStart - end : start >= labelEnd ? start - labelEnd : 0;
      if (!best || distance < best.distance) best = { value: Number(m[0].replace(/,/g, "")), distance };
    }
    if (best) return best.value;
  }
  return null;
}

/** Whether the text holds the token as a standalone word (e.g. a grade). */
export function hasToken(text: string, token: string): boolean {
  return new RegExp(`(^|[^A-Za-z0-9])${token}([^A-Za-z0-9]|$)`).test(text);
}

/**
 * The tones carried by the innermost `[data-tone]` elements whose text holds
 * the token (a grade letter or a word).
 */
export function tonesShowing(scope: ParentNode, token: string | RegExp): string[] {
  const matches = (el: Element) =>
    typeof token === "string" ? hasToken(textOf(el), token) : token.test(textOf(el));
  const toned = Array.from(scope.querySelectorAll("[data-tone]")).filter(matches);
  return toned
    .filter((el) => !toned.some((other) => other !== el && el.contains(other)))
    .map((el) => el.getAttribute("data-tone") as string);
}

/**
 * Table rows of placeholder dashes: every data cell empty or a dash, a
 * leading rank number aside.
 */
export function dashOnlyRows(scope: ParentNode): Element[] {
  return Array.from(scope.querySelectorAll("tr")).filter((row) => {
    const cells = Array.from(row.querySelectorAll("td"));
    const data = cells.length > 1 && /^\s*#?\d+\s*$/.test(cells[0]?.textContent ?? "") ? cells.slice(1) : cells;
    return data.length > 0 && data.every((cell) => /^[\s—–-]*$/.test(cell.textContent ?? ""));
  });
}

/** The theme the document is set to, read from `<html>`. */
export function appliedTheme(doc: Document = document): "light" | "dark" | null {
  const root = doc.documentElement;
  const attribute = root.getAttribute("data-theme");
  if (attribute === "light" || attribute === "dark") return attribute;
  if (root.classList.contains("dark")) return "dark";
  if (root.classList.contains("light")) return "light";
  const scheme = root.style.colorScheme;
  if (scheme === "light" || scheme === "dark") return scheme;
  return null;
}

/** Matches a calendar date in any common rendering (ISO, "Sep 5", "5 Sep"). */
export function mentionsDate(text: string, isoDay: string): boolean {
  const [year, month, day] = isoDay.split("-").map(Number) as [number, number, number];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const name = months[month - 1] as string;
  const patterns = [
    isoDay,
    `${name}[a-z]*\\.? ${day}\\b`,
    `\\b${day} ${name}`,
    `\\b${month}/${day}/${year}`,
    `\\b${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`
  ];
  return patterns.some((pattern) => new RegExp(pattern, "i").test(text));
}

/** A copy of the scope without the body of the disclosure with that label. */
export function withoutDisclosure(scope: Element, label: RegExp): Element {
  const clone = scope.cloneNode(true) as Element;
  const found = disclosureLabelled(clone, label);
  if (found?.element.tagName === "DETAILS") {
    Array.from(found.element.children).forEach((child) => {
      if (child.tagName !== "SUMMARY") child.remove();
    });
  } else {
    found?.content?.remove();
  }
  return clone;
}

/** The innermost element holding every one of the given texts. */
export function innermostHolding(scope: ParentNode, texts: string[]): Element | null {
  const holders = Array.from(scope.querySelectorAll("*")).filter((el) =>
    texts.every((text) => (el.textContent ?? "").includes(text))
  );
  return holders.find((el) => !holders.some((other) => other !== el && el.contains(other))) ?? null;
}

/** The list entry (item, row, link, card or option) that names the given text. */
export function entryFor(scope: ParentNode, name: string): Element | null {
  const entries = Array.from(
    scope.querySelectorAll("li, tr, a, button, article, [role='option'], [role='listitem']")
  ).filter((el) => (el.textContent ?? "").includes(name));
  return entries.find((el) => !entries.some((other) => other !== el && el.contains(other))) ?? null;
}

/** A group of entries: a disclosure, or a card, labelled by the given text. */
export function groupLabelled(scope: ParentNode, label: RegExp): Element | null {
  return disclosureLabelled(scope, label)?.element ?? cardTitled(scope, label);
}

/** Text plus every accessible label and tooltip inside the element. */
export function accessibleTextOf(element: Element): string {
  const labels = Array.from(element.querySelectorAll("[aria-label], [title], title"))
    .map((el) => el.getAttribute("aria-label") ?? el.getAttribute("title") ?? el.textContent ?? "")
    .join(" ");
  return `${textOf(element)} ${element.getAttribute("aria-label") ?? ""} ${labels}`;
}

export type ThemeChoice = "system" | "light" | "dark";

/**
 * The theme options offered in the scope: a native select with the three
 * options, or one control per option (button, radio) named by its text,
 * aria-label or label.
 */
export function themeControls(scope: ParentNode): Partial<Record<ThemeChoice, HTMLElement>> {
  const names: ThemeChoice[] = ["system", "light", "dark"];
  for (const select of Array.from(scope.querySelectorAll("select"))) {
    const options = Array.from(select.options).map((o) => `${o.value} ${o.text}`.toLowerCase());
    if (names.every((name) => options.some((o) => o.includes(name)))) {
      return Object.fromEntries(names.map((name) => [name, select as HTMLElement]));
    }
  }
  const controls = Array.from(scope.querySelectorAll("button, input[type='radio'], [role='radio']"));
  const nameOf = (el: Element): string => {
    const label = el.id ? el.ownerDocument.querySelector(`label[for="${el.id}"]`) : null;
    return `${textOf(el)} ${el.getAttribute("aria-label") ?? ""} ${textOf(el.closest("label"))} ${textOf(label)} ${el.getAttribute("value") ?? ""}`.toLowerCase();
  };
  const found: Partial<Record<ThemeChoice, HTMLElement>> = {};
  for (const name of names) {
    const control = controls.find((el) => new RegExp(`\\b${name}\\b`).test(nameOf(el)));
    if (control) found[name] = control as HTMLElement;
  }
  return found;
}

/** Whether keyboard focus can reach the element without custom scripting. */
export function isKeyboardReachable(element: Element): boolean {
  if (element.getAttribute("tabindex") === "-1" || element.hasAttribute("disabled")) return false;
  if (["BUTTON", "SELECT", "INPUT", "TEXTAREA", "SUMMARY"].includes(element.tagName)) return true;
  if (element.tagName === "A" && element.hasAttribute("href")) return true;
  return element.hasAttribute("tabindex");
}

/**
 * A region labelled by the given text: an element whose aria-label matches,
 * the section around a matching heading, caption or summary, or the parent
 * of any other element whose own text matches.
 */
export function regionLabelled(scope: ParentNode, label: RegExp): Element | null {
  const byAria = Array.from(scope.querySelectorAll("[aria-label]")).find((el) =>
    label.test(el.getAttribute("aria-label") ?? "")
  );
  if (byAria) return byAria;
  const titled = cardTitled(scope, label);
  if (titled) return titled;
  for (const el of Array.from(scope.querySelectorAll("figcaption, caption, legend, summary, span, p, div"))) {
    const ownText = Array.from(el.childNodes)
      .filter((child) => child.nodeType === Node.TEXT_NODE)
      .map((child) => child.nodeValue ?? "")
      .join("");
    if (label.test(ownText)) return el.closest("figure, table, fieldset, details") ?? el.parentElement;
  }
  return null;
}
