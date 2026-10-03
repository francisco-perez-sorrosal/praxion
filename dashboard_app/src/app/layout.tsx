import type { Metadata } from "next";

import { SidebarNav } from "@/components/sidebar-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { getShellConfig } from "@/lib/config";
import { getSidebarSignals } from "@/server/view-models/sidebar-signals";

import "./globals.css";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export const metadata: Metadata = {
  description: "Professional filesystem-driven status portal for Praxion projects",
  title: "Praxion Dashboard Web"
};

// Runs in <head>, before first paint, so a remembered theme never flashes the
// other one. Inline by design: no external script, no fetch. Keep the key in
// step with THEME_STORAGE_KEY in components/theme-toggle.tsx (pinned by a test).
const THEME_BOOTSTRAP = `try{var t=localStorage.getItem("praxion-theme");if(t==="light"||t==="dark"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}`;

export default async function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cfg = getShellConfig();
  const signals = await getSidebarSignals(cfg.projectRoot);

  return (
    // suppressHydrationWarning: the head script sets data-theme before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            {/* Brand: glyph + product · project name, root path below */}
            <div className="brand">
              <p className="brand__line">
                <span className="brand__glyph" aria-hidden="true">◆</span>
                <span className="brand__name">Praxion · {cfg.projectName}</span>
              </p>
              <p
                className="brand__root"
                title={cfg.projectRoot}
              >
                {cfg.projectRoot}
              </p>
            </div>

            <SidebarNav signals={signals} />

            {/* Sidebar footer: theme choice + version */}
            <footer className="sidebar-footer">
              <ThemeToggle />
              <span className="sidebar-footer__version">v{cfg.dashboardVersion}</span>
            </footer>
          </aside>

          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
