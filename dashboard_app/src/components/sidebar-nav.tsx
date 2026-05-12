"use client";

import type { Route } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { SidebarSignals } from "@/server/view-models/sidebar-signals";

type NavKey =
  | "architecture"
  | "workshops"
  | "adrs"
  | "sentinel"
  | "roadmap"
  | "metrics"
  | "documentation";

type NavItem = {
  href: Route;
  key: NavKey;
  label: string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/architecture", key: "architecture", label: "Architecture" },
  { href: "/workshops", key: "workshops", label: "Workshops" },
  { href: "/adrs", key: "adrs", label: "ADRs" },
  { href: "/sentinel", key: "sentinel", label: "Sentinel" },
  { href: "/roadmap", key: "roadmap", label: "Roadmap" },
  { href: "/metrics", key: "metrics", label: "Metrics" },
  { href: "/documentation", key: "documentation", label: "Documentation" }
];

// 16px inline-SVG icons, stroke-width:1.5, currentColor.
// aria-hidden is set at the usage site.
const ICONS: Record<NavKey, ReactNode> = {
  architecture: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="1" width="6" height="6" rx="1" />
      <rect x="9" y="1" width="6" height="6" rx="1" />
      <rect x="1" y="9" width="6" height="6" rx="1" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
    </svg>
  ),
  workshops: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6.5" />
      <polyline points="8,4.5 8,8 10.5,9.5" />
    </svg>
  ),
  adrs: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 1.5h10a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1z" />
      <line x1="4.5" y1="5.5" x2="11.5" y2="5.5" />
      <line x1="4.5" y1="8" x2="11.5" y2="8" />
      <line x1="4.5" y1="10.5" x2="8" y2="10.5" />
    </svg>
  ),
  sentinel: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 1.5 L14 4 L14 8 C14 11.5 11 14 8 14.5 C5 14 2 11.5 2 8 L2 4 Z" />
      <polyline points="5.5,8 7,9.5 10.5,6" />
    </svg>
  ),
  roadmap: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="2" y1="4" x2="14" y2="4" />
      <line x1="2" y1="8" x2="10" y2="8" />
      <line x1="2" y1="12" x2="12" y2="12" />
      <circle cx="14" cy="4" r="1" fill="currentColor" stroke="none" />
      <circle cx="10" cy="8" r="1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </svg>
  ),
  metrics: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2,12 5,7.5 8,9 11,4.5 14,6" />
    </svg>
  ),
  documentation: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 2.5h7l3 3v8a.5.5 0 0 1-.5.5h-9.5a.5.5 0 0 1-.5-.5v-11a.5.5 0 0 1 .5-.5z" />
      <polyline points="9,2.5 9,5.5 12,5.5" />
      <line x1="4.5" y1="8" x2="11.5" y2="8" />
      <line x1="4.5" y1="10.5" x2="9" y2="10.5" />
    </svg>
  )
};

function gradeChipClass(grade: string): string {
  const letter = grade.toUpperCase();
  if (letter === "A") return "chip chip--grade-a";
  if (letter === "B") return "chip chip--grade-b";
  if (letter === "C") return "chip chip--grade-c";
  return "chip chip--grade-d";
}

type SidebarNavProps = {
  signals: SidebarSignals;
};

export function SidebarNav({ signals }: SidebarNavProps) {
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
            <span className="nav-card__icon" aria-hidden="true">
              {ICONS[item.key]}
            </span>
            <span className="nav-label">{item.label}</span>
            {item.key === "workshops" && signals.activeWorkshops > 0 && (
              <span className="nav-badge" aria-label={`${signals.activeWorkshops} active`}>
                {signals.activeWorkshops}
              </span>
            )}
            {item.key === "sentinel" && signals.sentinelGrade !== null && (
              <span className={gradeChipClass(signals.sentinelGrade)}>
                {signals.sentinelGrade}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
