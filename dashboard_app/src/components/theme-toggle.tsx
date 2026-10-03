"use client";

import { useEffect, useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";

/**
 * The browser storage key. The root layout's inline head script reads the same
 * literal before first paint; that file cannot import it (a server module
 * importing a value from a "use client" module receives a reference, not the
 * string), so the pair is pinned by a test.
 */
export const THEME_STORAGE_KEY = "praxion-theme";

const THEME_ATTRIBUTE = "data-theme";

const OPTIONS: ReadonlyArray<{ choice: ThemeChoice; glyph: string; label: string }> = [
  { choice: "system", glyph: "◐", label: "System theme" },
  { choice: "light", glyph: "☼", label: "Light theme" },
  { choice: "dark", glyph: "☾", label: "Dark theme" }
];

/** The remembered choice; `system` when nothing (or something unknown) is stored. */
export function readStoredTheme(storage: Pick<Storage, "getItem"> | null): ThemeChoice {
  const stored = storage?.getItem(THEME_STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

/**
 * Pins the document to a theme and remembers the choice. `system` removes both
 * the attribute and the stored key, so the operating system decides again.
 */
export function applyTheme(
  choice: ThemeChoice,
  root: Pick<HTMLElement, "setAttribute" | "removeAttribute">,
  storage: Pick<Storage, "setItem" | "removeItem"> | null
): void {
  if (choice === "system") {
    root.removeAttribute(THEME_ATTRIBUTE);
    storage?.removeItem(THEME_STORAGE_KEY);
    return;
  }
  root.setAttribute(THEME_ATTRIBUTE, choice);
  storage?.setItem(THEME_STORAGE_KEY, choice);
}

/** `null` when the browser blocks storage; the theme then lasts for the page view only. */
function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>("system");

  // The server cannot know the stored choice, so the first render says
  // "system"; the head script has already applied the real theme to <html>,
  // and this effect catches the buttons up. It also re-applies the theme: when
  // React recovers from a hydration mismatch it client-renders the document
  // and strips <html>'s attributes, which would silently drop the head
  // script's data-theme.
  useEffect(() => {
    const storage = browserStorage();
    const stored = readStoredTheme(storage);
    setChoice(stored);
    applyTheme(stored, document.documentElement, storage);
  }, []);

  function choose(next: ThemeChoice) {
    setChoice(next);
    applyTheme(next, document.documentElement, browserStorage());
  }

  return (
    <div className="theme-toggle" role="group" aria-label="Theme">
      {OPTIONS.map((option) => (
        <button
          key={option.choice}
          type="button"
          className="theme-toggle__option"
          aria-pressed={choice === option.choice}
          aria-label={option.label}
          title={option.label}
          onClick={() => choose(option.choice)}
        >
          <span aria-hidden="true">{option.glyph}</span>
        </button>
      ))}
    </div>
  );
}
