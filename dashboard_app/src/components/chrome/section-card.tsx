import type { ReactNode } from "react";

import type { Tone } from "@/lib/tone";

export type SectionCardProps = {
  /** Right-aligned slot in the header: a selector, a link, a count pill. */
  actions?: ReactNode;
  children: ReactNode;
  /** Render as a `<details>` disclosure; `defaultOpen` then applies. */
  collapsible?: boolean;
  defaultOpen?: boolean;
  /** Heading level of the title (the page title is the h1); default 2. */
  headingLevel?: 2 | 3 | 4;
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
 * disclosure of heavy content (full reports, long tables). The title is a real
 * heading so every card names itself in the document outline; inside a
 * `<summary>` it sits directly beside the chevron, as the content model requires
 * (heading content may be mixed with phrasing there, a wrapper `span` may not).
 */
export function SectionCard({
  actions,
  children,
  collapsible = false,
  defaultOpen = true,
  headingLevel = 2,
  id,
  subtitle,
  title,
  tone
}: SectionCardProps) {
  const className = `section-card${tone ? ` section-card--${tone}` : ""}`;
  const Title = `h${headingLevel}` as const;
  const heading = <Title className="section-card__title">{title}</Title>;
  const subtitleSlot = subtitle != null ? <span className="section-card__subtitle">{subtitle}</span> : null;
  const actionsSlot = actions != null ? <span className="section-card__actions">{actions}</span> : null;

  if (collapsible) {
    return (
      <section className={`${className} section-card--collapsible`} id={id}>
        <details open={defaultOpen}>
          <summary className="section-card__header section-card__summary">
            <span className="section-card__chevron" aria-hidden="true" />
            {heading}
            {subtitleSlot}
            {actionsSlot}
          </summary>
          <div className="section-card__body">{children}</div>
        </details>
      </section>
    );
  }

  return (
    <section className={className} id={id}>
      <header className="section-card__header">
        <div className="section-card__heading">
          {heading}
          {subtitleSlot}
        </div>
        {actionsSlot}
      </header>
      <div className="section-card__body">{children}</div>
    </section>
  );
}
