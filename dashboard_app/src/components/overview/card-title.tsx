import type { Route } from "next";
import Link from "next/link";

/**
 * The heading of an Overview card: a real heading (so the page has an outline
 * and a card can be named) whose text links to the surface holding the detail.
 */
export function CardTitle({ href, children }: { children: string; href: Route }) {
  return (
    <h2 className="overview-card__title">
      <Link href={href}>{children}</Link>
    </h2>
  );
}
