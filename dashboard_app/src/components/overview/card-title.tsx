import type { Route } from "next";
import Link from "next/link";

/**
 * The text of an Overview card title, linking to the surface holding the
 * detail. `SectionCard` supplies the heading element itself.
 */
export function CardTitle({ href, children }: { children: string; href: Route }) {
  return <Link href={href}>{children}</Link>;
}
