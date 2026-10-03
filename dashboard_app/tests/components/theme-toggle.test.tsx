// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  applyTheme,
  readStoredTheme,
  THEME_STORAGE_KEY,
  ThemeToggle
} from "@/components/theme-toggle";

const LAYOUT_SOURCE = readFileSync(path.join(process.cwd(), "src/app/layout.tsx"), "utf8");
const TOKENS_SOURCE = readFileSync(path.join(process.cwd(), "src/app/tokens.css"), "utf8");

/** jsdom under this Node lacks a working localStorage; give it a real Storage. */
function installStorage(): Storage {
  const data = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => Array.from(data.keys())[index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, String(value))
  };
  Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  return storage;
}

function pressed(): string[] {
  return screen
    .getAllByRole("button")
    .filter((button) => button.getAttribute("aria-pressed") === "true")
    .map((button) => button.getAttribute("aria-label") ?? "");
}

let storage: Storage;

beforeEach(() => {
  storage = installStorage();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
});

describe("ThemeToggle", () => {
  it("offers system, light and dark as buttons with exactly one pressed", () => {
    render(<ThemeToggle />);

    expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "System theme",
      "Light theme",
      "Dark theme"
    ]);
    expect(pressed()).toEqual(["System theme"]);
  });

  it("applies and remembers dark and light, one pressed at a time", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Dark theme" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(pressed()).toEqual(["Dark theme"]);

    fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(pressed()).toEqual(["Light theme"]);
  });

  it("clears the attribute and the stored key when system is chosen", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Dark theme" }));

    fireEvent.click(screen.getByRole("button", { name: "System theme" }));

    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(storage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(pressed()).toEqual(["System theme"]);
  });

  it("presses the remembered choice after mounting", () => {
    storage.setItem(THEME_STORAGE_KEY, "dark");

    render(<ThemeToggle />);

    expect(pressed()).toEqual(["Dark theme"]);
  });

  it("still applies the theme when the browser blocks storage", () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("blocked", "SecurityError");
      }
    });
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: "Light theme" }));

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(pressed()).toEqual(["Light theme"]);
  });
});

describe("readStoredTheme", () => {
  it.each([
    ["light", "light"],
    ["dark", "dark"],
    ["system", "system"],
    ["sepia", "system"],
    [null, "system"]
  ] as const)("reads %s as %s", (stored, expected) => {
    expect(readStoredTheme({ getItem: () => stored })).toBe(expected);
  });

  it("reads system when storage is unavailable", () => {
    expect(readStoredTheme(null)).toBe("system");
  });
});

describe("applyTheme", () => {
  it("pins light and dark on the root and stores them", () => {
    applyTheme("dark", document.documentElement, storage);

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(storage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("applies without storing when storage is unavailable", () => {
    applyTheme("light", document.documentElement, null);

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});

describe("theme delivery", () => {
  it("reads the same storage key in the layout's head script as the toggle writes", () => {
    expect(LAYOUT_SOURCE).toContain(`localStorage.getItem("${THEME_STORAGE_KEY}")`);
  });

  it("delivers every dual-valued colour through light-dark() with no media-query fork", () => {
    expect(TOKENS_SOURCE).not.toContain("prefers-color-scheme");
    expect(TOKENS_SOURCE).toMatch(/:root\s*{\s*color-scheme:\s*light dark;/);
    expect(TOKENS_SOURCE).toContain(':root[data-theme="light"] { color-scheme: light; }');
    expect(TOKENS_SOURCE).toContain(':root[data-theme="dark"]  { color-scheme: dark; }');
    expect(TOKENS_SOURCE).toMatch(/--color-text:\s+light-dark\(#0f172a, #f5f4f1\)/);
    expect(TOKENS_SOURCE).toMatch(/--color-bg:\s+light-dark\(#f8f7f5, #14130f\)/);
  });
});
