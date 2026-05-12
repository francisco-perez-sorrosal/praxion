/**
 * Thin per-page wrapper combining AppHeader with a content section and an
 * optional "Sources ▸" disclosure slot.
 *
 * This is a convenience component — AppHeader is the load-bearing piece.
 * Pages may adopt AppHeader directly if PageShell doesn't fit their layout.
 * The sourcesContent slot holds the per-surface "source contract" reference
 * text — a progressively-disclosed footnote, formerly a sidebar aside.
 */
import type { ReactNode } from "react";

import { AppHeader } from "@/components/app-header";

type BreadcrumbItem = {
  href: string;
  label: string;
};

type PageShellProps = {
  breadcrumb?: BreadcrumbItem[];
  children: ReactNode;
  dataAsOf?: Date | string | null;
  sourcesContent?: ReactNode;
  title: string;
};

export function PageShell({
  title,
  dataAsOf,
  breadcrumb,
  sourcesContent,
  children
}: PageShellProps) {
  return (
    <>
      <AppHeader title={title} dataAsOf={dataAsOf} breadcrumb={breadcrumb} />
      <section className="page">{children}</section>
      {sourcesContent != null && (
        <details className="page-sources">
          <summary className="page-sources__summary">Sources ▸</summary>
          <div className="page-sources__body">{sourcesContent}</div>
        </details>
      )}
    </>
  );
}
