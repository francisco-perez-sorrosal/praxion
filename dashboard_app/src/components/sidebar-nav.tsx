"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: Route;
  label: string;
  note: string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/architecture", label: "Architecture", note: "Design, code guide, diagrams" },
  { href: "/workshops", label: "Workshops", note: "Live in-flight pipelines" },
  { href: "/adrs", label: "ADRs", note: "Decisions and drafts" },
  { href: "/sentinel", label: "Sentinel", note: "Health reports" },
  { href: "/roadmap", label: "Roadmap", note: "Project direction" },
  { href: "/metrics", label: "Metrics", note: "KPIs and hot spots" },
  { href: "/documentation", label: "Documentation", note: "Manifest-driven surfaces" }
];

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="sidebar-nav" aria-label="Dashboard pages">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            className={`nav-card${active ? " is-active" : ""}`}
            href={item.href}
          >
            <span className="nav-label">{item.label}</span>
            <span className="nav-note">{item.note}</span>
          </Link>
        );
      })}
    </nav>
  );
}
