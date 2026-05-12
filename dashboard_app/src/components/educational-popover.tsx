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
      <div
        className="educational-popover__panel"
        hidden={!open}
        id={panelId}
        role="tooltip"
      >
        {title ? (
          <p className="educational-popover__title">{title}</p>
        ) : null}
        <p className="educational-popover__body">{body}</p>
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
      </div>
    </span>
  );
}
