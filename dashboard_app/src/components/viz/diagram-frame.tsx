"use client";

import { useRef, useState } from "react";

import { DiagramModal } from "./diagram-modal";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const DATA_ASPECT_RE = /\bdata-aspect="([^"]*)"/i;

/**
 * Extract the aspect ratio from a normalized SVG string's `data-aspect` attr.
 * Returns `undefined` when the attribute is absent (unmeasurable SVG).
 */
function getAspectFromSvg(svg: string): number | undefined {
  const match = DATA_ASPECT_RE.exec(svg);
  if (!match || match[1] === undefined) return undefined;
  const value = parseFloat(match[1]);
  return isFinite(value) && value > 0 ? value : undefined;
}

// ─── Props ───────────────────────────────────────────────────────────────────

type DiagramFrameProps = {
  /** Pre-sanitized and pre-normalized SVG markup */
  readonly svg: string;
  readonly label: string;
};

// ─── Component ───────────────────────────────────────────────────────────────

/**
 * Responsive diagram card: an aspect-ratio CSS box containing the normalized
 * SVG (correct on server HTML before hydration), plus an Expand button that
 * opens a fullscreen pan/zoom modal.
 *
 * Client component so the Expand button can wire up modal state. The SVG
 * markup is present in server-rendered HTML via dangerouslySetInnerHTML on
 * the SSR pass.
 */
export function DiagramFrame({ svg, label }: DiagramFrameProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const expandButtonRef = useRef<HTMLButtonElement | null>(null);
  const aspect = getAspectFromSvg(svg);

  const boxStyle: React.CSSProperties =
    aspect !== undefined
      ? { aspectRatio: String(aspect) }
      : { minHeight: "16rem", maxHeight: "560px" };

  return (
    <>
      <figure className="diagram-frame">
        <div className="diagram-frame__box" style={boxStyle}>
          {/* eslint-disable-next-line react/no-danger */}
          <div dangerouslySetInnerHTML={{ __html: svg }} />
        </div>
        <figcaption className="diagram-frame__caption">
          <span className="diagram-frame__name">{label}</span>
          <button
            ref={expandButtonRef}
            type="button"
            className="diagram-frame__expand"
            aria-label={`Expand ${label} to full screen`}
            onClick={() => setModalOpen(true)}
          >
            ⤢ Expand
          </button>
        </figcaption>
      </figure>

      {modalOpen ? (
        <DiagramModal
          svg={svg}
          label={label}
          onClose={() => setModalOpen(false)}
          triggerRef={expandButtonRef}
        />
      ) : null}
    </>
  );
}
