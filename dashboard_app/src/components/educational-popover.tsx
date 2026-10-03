"use client";

import { useId, useState } from "react";

const PANEL_SUFFIX = "-panel";

export function EducationalPopover({
  body,
  href,
  title
}: {
  body: string;
  href?: string;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const baseId = useId();
  const panelId = `${baseId}${PANEL_SUFFIX}`;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  }

  const ariaLabel = title ? `More information about ${title}` : "More information";

  // Phrasing content only: the trigger sits inside a <p> lede on most surfaces, so
  // a <div> or <p> here is invalid HTML and made React raise hydration error #418.
  return (
    <span
      className="educational-popover"
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        aria-describedby={panelId}
        aria-expanded={open}
        aria-label={ariaLabel}
        className="educational-popover__trigger"
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((prev) => !prev)}
        onFocus={() => setOpen(true)}
        type="button"
      >
        ?
      </button>
      <span
        className="educational-popover__panel"
        hidden={!open}
        id={panelId}
        role="tooltip"
      >
        {title ? (
          <span className="educational-popover__title">{title}</span>
        ) : null}
        <span className="educational-popover__body">{body}</span>
        {href ? (
          <a
            className="educational-popover__link"
            href={href}
            rel="noopener noreferrer"
            target="_blank"
          >
            Open ↗
          </a>
        ) : null}
      </span>
    </span>
  );
}
