import type { ReactNode } from "react";

export function ArtifactCard({
  children,
  defaultOpen = false,
  footer,
  meta,
  title
}: {
  children: ReactNode;
  defaultOpen?: boolean;
  footer?: ReactNode;
  meta?: ReactNode;
  title: string;
}) {
  return (
    <article className="artifact-card artifact-card--collapsible">
      <details open={defaultOpen}>
        <summary className="artifact-card__summary">
          <span className="artifact-card__chevron" aria-hidden="true" />
          <span className="artifact-card__title">{title}</span>
          {meta ? <div className="artifact-card__meta">{meta}</div> : null}
        </summary>
        <div className="artifact-card__body">{children}</div>
        {footer ? <footer className="artifact-card__footer">{footer}</footer> : null}
      </details>
    </article>
  );
}
