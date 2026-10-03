import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// A non-UTC zone, set before any `Date` exists, so a test that pins local-time behaviour
// (a local calendar day, a zone-less filename stamp) can fail where CI runs in UTC.
process.env.TZ = "America/Los_Angeles";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": path.join(rootDir, "src"),
      "server-only": path.join(rootDir, "tests", "support", "server-only.ts")
    }
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"]
  }
});
