import type { ReactNode } from "react";

import type { Tone } from "@/lib/tone";

export type SectionCardProps = {
  /** Right-aligned slot in the header: a selector, a link, a count pill. */
  actions?: ReactNode;
  children: ReactNode;
  /** Render as a `<details>` disclosure; `defaultOpen` then applies. */
  collapsible?: boolean;
  defaultOpen?: boolean;
  id?: string;
  subtitle?: ReactNode;
  title: ReactNode;
  /** Optional accent on the header (attention cards, failing sections). */
  tone?: Tone;
};

/**
 * Titled card for a digest section. The non-collapsible sibling of
 * `ArtifactCard`: the header is always visible, the body is always rendered,
 * and `collapsible` turns the header into a `<summary>` for progressive
 * disclosure of heavy content (full reports, long tables).
 */
export function SectionCard({
  actions,
  children,
  collapsible = false,
  defaultOpen = true,
  id,
  subtitle,
  title,
  tone
}: SectionCardProps) {
  const className = `section-card${tone ? ` section-card--${tone}` : ""}`;
  const heading = (
    <>
      <span className="section-card__heading">
        <span className="section-card__title">{title}</span>
        {subtitle != null ? <span className="section-card__subtitle">{subtitle}</span> : null}
      </span>
      {actions != null ? <span className="section-card__actions">{actions}</span> : null}
    </>
  );

  if (collapsible) {
    return (
      <section className={`${className} section-card--collapsible`} id={id}>
        <details open={defaultOpen}>
          <summary className="section-card__header section-card__summary">
            <span className="section-card__chevron" aria-hidden="true" />
            {heading}
          </summary>
          <div className="section-card__body">{children}</div>
        </details>
      </section>
    );
  }

  return (
    <section className={className} id={id}>
      <header className="section-card__header">{heading}</header>
      <div className="section-card__body">{children}</div>
    </section>
  );
}
