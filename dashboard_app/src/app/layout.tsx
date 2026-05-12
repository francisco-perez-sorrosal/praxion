import type { Metadata } from "next";

import { LiveRefresh } from "@/components/live-refresh";
import { SidebarNav } from "@/components/sidebar-nav";
import { getShellConfig } from "@/lib/config";
import { getSidebarSignals } from "@/server/view-models/sidebar-signals";

import "./globals.css";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export const metadata: Metadata = {
  description: "Professional filesystem-driven status portal for Praxion projects",
  title: "Praxion Dashboard Web"
};

export default async function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cfg = getShellConfig();
  const signals = await getSidebarSignals(cfg.projectRoot);

  return (
    <html lang="en">
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

            {/* Sidebar footer: live refresh indicator + version */}
            <footer className="sidebar-footer">
              <LiveRefresh seconds={cfg.pollIntervalSeconds} />
              <span className="sidebar-footer__refresh">
                live · {cfg.pollIntervalSeconds}s
              </span>
              <span className="sidebar-footer__version">v{cfg.dashboardVersion}</span>
            </footer>
          </aside>

          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
