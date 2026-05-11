import type { Metadata } from "next";

import { SidebarNav } from "@/components/sidebar-nav";
import { getShellConfig } from "@/lib/config";

import "./globals.css";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export const metadata: Metadata = {
  description: "Professional filesystem-driven status portal for Praxion projects",
  title: "Praxion Dashboard Web"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cfg = getShellConfig();

  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <p className="eyebrow">Praxion project status</p>
              <h1>{cfg.projectName}</h1>
              <p className="brand-body">
                Read-only portal over live `.ai-state`, `.ai-work`, and documentation
                surfaces.
              </p>
            </div>

            <dl className="project-meta">
              <div>
                <dt>Root</dt>
                <dd>{cfg.projectRoot}</dd>
              </div>
              <div>
                <dt>Refresh</dt>
                <dd>{cfg.pollIntervalSeconds}s workshops cadence</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{cfg.dashboardVersion}</dd>
              </div>
            </dl>

            <SidebarNav />
          </aside>

          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
