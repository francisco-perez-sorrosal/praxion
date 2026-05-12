"use client";

import { useEffect, useId, useRef } from "react";

import { usePanZoom } from "./use-pan-zoom";

// ─── Focus trap ───────────────────────────────────────────────────────────────

const FOCUSABLE_SELECTORS = [
  "a[href]",
  "button:not([disabled])",
  "textarea",
  "input",
  "select",
  '[tabindex]:not([tabindex="-1"])'
].join(", ");

function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS));
}

// ─── Props ────────────────────────────────────────────────────────────────────

type DiagramModalProps = {
  /** Pre-sanitized and pre-normalized SVG markup */
  readonly svg: string;
  readonly label: string;
  readonly onClose: () => void;
  readonly triggerRef: React.RefObject<HTMLElement | null>;
};

// ─── Component ───────────────────────────────────────────────────────────────

/**
 * Fullscreen pan/zoom modal for diagram inspection.
 *
 * Accessibility: role="dialog", aria-modal="true", focus-trapped within,
 * Tab/Shift+Tab cycle within, Escape closes, focus returns to trigger on close.
 * Body scroll is locked while open (SSR-safe guard).
 */
export function DiagramModal({ svg, label, onClose, triggerRef }: DiagramModalProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const labelId = useId();

  const {
    containerRef,
    transform,
    onWheel,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onKeyDown,
    reset,
    zoomIn,
    zoomOut
  } = usePanZoom();

  const transformStyle = `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`;

  // ── Focus management + body-scroll lock ──────────────────────────────────
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    // Lock body scroll (SSR-safe)
    if (typeof document !== "undefined") {
      document.body.style.overflow = "hidden";
    }

    // Move focus into the dialog
    const focusable = getFocusableElements(dialog);
    focusable[0]?.focus();

    return () => {
      // Restore body scroll
      if (typeof document !== "undefined") {
        document.body.style.overflow = "";
      }
      // Return focus to the trigger that opened this modal
      triggerRef.current?.focus();
    };
  }, [triggerRef]);

  // ── Focus trap (Tab / Shift+Tab) ─────────────────────────────────────────
  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>): void {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }

    if (e.key !== "Tab") return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusable = getFocusableElements(dialog);
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement as HTMLElement | null;

    if (e.shiftKey) {
      if (active === first) {
        e.preventDefault();
        last?.focus();
      }
    } else {
      if (active === last) {
        e.preventDefault();
        first?.focus();
      }
    }
  }

  // ── Backdrop click (close) ────────────────────────────────────────────────
  function handleBackdropClick(e: React.MouseEvent<HTMLDivElement>): void {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }

  return (
    /* Backdrop */
    <div
      className="diagram-modal__backdrop"
      onClick={handleBackdropClick}
      aria-hidden="true"
    >
      {/* Dialog surface */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        className="diagram-modal"
        onKeyDown={handleKeyDown}
      >
        {/* Header row */}
        <div className="diagram-modal__header">
          <span id={labelId} className="diagram-modal__title">
            {label}
          </span>
          <div className="diagram-modal__controls">
            <button
              type="button"
              className="diagram-modal__btn"
              aria-label="Zoom in"
              onClick={zoomIn}
            >
              +
            </button>
            <button
              type="button"
              className="diagram-modal__btn"
              aria-label="Zoom out"
              onClick={zoomOut}
            >
              −
            </button>
            <button
              type="button"
              className="diagram-modal__btn"
              aria-label="Reset zoom to fit"
              onClick={reset}
            >
              Fit
            </button>
            <button
              type="button"
              className="diagram-modal__btn diagram-modal__btn--close"
              aria-label="Close diagram"
              onClick={onClose}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Pan/zoom surface */}
        <div
          ref={containerRef}
          className="diagram-modal__pan-zoom"
          role="region"
          aria-label={`Pan and zoom view of ${label}`}
          tabIndex={0}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onKeyDown={onKeyDown}
        >
          <div
            data-pan-zoom-content
            className="diagram-modal__transform"
            style={{ transform: transformStyle, transformOrigin: "0 0" }}
            // eslint-disable-next-line react/no-danger
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>

        <p className="diagram-modal__hint">
          Scroll to zoom · drag to pan · keyboard +/−/0/arrows · Esc to close
        </p>
      </div>
    </div>
  );
}
