"use client";

import { useEffect, useRef, useState } from "react";

const CONFIRMATION_MS = 2000;

type CopyState = "idle" | "copied" | "failed";

const LABEL_BY_STATE: Record<CopyState, string> = {
  copied: "Copied",
  failed: "Copy failed",
  idle: "Copy as prompt"
};

/**
 * Copies a pre-composed handoff prompt to the clipboard and shows a brief
 * confirmation. Renders nothing when there is no prompt to copy (e.g. no
 * WIP.md for this workshop) — see `composeHandoffPrompt`'s null contract.
 */
export function CopyAsPromptButton({ prompt }: { readonly prompt: string | null }) {
  const [state, setState] = useState<CopyState>("idle");
  const resetTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    return () => {
      window.clearTimeout(resetTimer.current);
    };
  }, []);

  if (prompt === null) {
    return null;
  }

  async function handleClick() {
    try {
      await navigator.clipboard.writeText(prompt as string);
      setState("copied");
    } catch {
      setState("failed");
    }
    window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setState("idle"), CONFIRMATION_MS);
  }

  return (
    <button
      aria-live="polite"
      className={`copy-as-prompt-btn${state === "failed" ? " copy-as-prompt-btn--failed" : ""}`}
      onClick={handleClick}
      type="button"
    >
      {LABEL_BY_STATE[state]}
    </button>
  );
}
