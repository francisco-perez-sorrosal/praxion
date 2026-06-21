/**
 * Behavioral tests for the GET /api/health route handler.
 *
 * The dashboard's health check is readiness-lean: 200 only when the target
 * project's `.ai-state/` tree (under the resolved project root) is reachable,
 * 503 otherwise — never an unconditional 200. Tests mock `@/lib/config` (the
 * project-root source) and `node:fs` (the reachability probe).
 *
 * vi.mock hoisting: mocks are top-level so vitest hoists them before the route
 * module is imported.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

const mockAccess = vi.fn();
vi.mock("node:fs", () => ({
  promises: { access: (...args: unknown[]) => mockAccess(...args) },
}));

const mockGetConfig = vi.fn();
vi.mock("@/lib/config", () => ({
  getConfig: () => mockGetConfig(),
}));

import { GET } from "@/app/api/health/route";

describe("GET /api/health", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns 200 and no-store when .ai-state is reachable", async () => {
    mockGetConfig.mockReturnValue({ projectRoot: "/proj" });
    mockAccess.mockResolvedValue(undefined);

    const res = await GET();

    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("no-store");
    await expect(res.json()).resolves.toMatchObject({ status: "ok" });
  });

  it("returns 503 when .ai-state is not reachable", async () => {
    mockGetConfig.mockReturnValue({ projectRoot: "/proj" });
    mockAccess.mockRejectedValue(new Error("ENOENT"));

    const res = await GET();

    expect(res.status).toBe(503);
    await expect(res.json()).resolves.toMatchObject({ status: "unavailable" });
  });

  it("returns 503 when the project root is misconfigured", async () => {
    mockGetConfig.mockImplementation(() => {
      throw new Error("PRAXION_PROJECT_ROOT must be set");
    });

    const res = await GET();

    expect(res.status).toBe(503);
  });
});
