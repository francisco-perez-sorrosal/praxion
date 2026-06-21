import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

import { NextResponse } from "next/server";

import { getConfig } from "@/lib/config";

// force-dynamic: without it the App Router can statically render this route at
// build time, returning 200 even when the running server cannot reach its data
// root — the "always-200" anti-pattern that suppresses alerts. The check must
// run per request.
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" } as const;

// Readiness-lean health check. The dashboard's one critical dependency is the
// target project's `.ai-state/` tree (resolved from PRAXION_PROJECT_ROOT). Return
// 200 only when that tree is reachable; 503 otherwise. Monitors check the status
// code, not the body, so failure is a 503 — never a 200 with `{ ok: false }`.
export async function GET(): Promise<NextResponse> {
  try {
    const { projectRoot } = getConfig();
    await fs.access(path.join(projectRoot, ".ai-state"));
    return NextResponse.json({ status: "ok" }, { status: 200, headers: NO_STORE });
  } catch (error) {
    const reason = error instanceof Error ? error.message : "unknown";
    return NextResponse.json(
      { status: "unavailable", reason },
      { status: 503, headers: NO_STORE },
    );
  }
}
