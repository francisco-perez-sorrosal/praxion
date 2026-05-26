# React Context — TypeScript Development

React 19 + Vite + Next.js 15 patterns layered on top of the TypeScript baseline. Back to [SKILL.md](../SKILL.md).

Load [`contexts/typescript.md`](typescript.md) first — this file layers React-specific patterns on top and does not restate tsconfig, Biome/ESLint, Vitest, or pnpm/volta baseline.

## Contents

- [Code quality toolchain — React override](#code-quality-toolchain--react-override)
- [React 19 — Hooks and patterns](#react-19--hooks-and-patterns)
- [Vite scaffolding](#vite-scaffolding)
- [Next.js 15 — App Router](#nextjs-15--app-router)
- [Testing — React Testing Library + Vitest](#testing--react-testing-library--vitest)
- [End-to-end testing — Playwright](#end-to-end-testing--playwright)
- [Package.json scripts](#packagejson-scripts)

## Code quality toolchain — React override

**React projects must use ESLint v9 + `eslint-plugin-react-hooks`, not Biome.**

This overrides the Biome default from `contexts/typescript.md`. The reason is that
`eslint-plugin-react-hooks` has no Biome equivalent — rules like `rules-of-hooks` and
`exhaustive-deps` enforce the React hooks contract at lint time and are required for safe
React development. See `contexts/typescript.md § Code quality toolchain → Path B` for the
full ESLint v9 + `@typescript-eslint` v8 + Prettier install and config baseline; the
section below adds the React-specific plugins on top.

### React-specific ESLint additions

Install on top of the Path B base:

```bash
pnpm add -D eslint-plugin-react-hooks eslint-plugin-react
```

Add to `eslint.config.mjs`:

```js
import reactHooks from "eslint-plugin-react-hooks";
import react from "eslint-plugin-react";

export default tseslint.config(
  // ... base config from contexts/typescript.md Path B ...
  {
    plugins: {
      "react-hooks": reactHooks,
      react,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react/react-in-jsx-scope": "off", // not needed in React 17+
      "react/prop-types": "off",         // TypeScript handles prop types
    },
    settings: {
      react: { version: "detect" },
    },
  }
);
```

---

## React 19 — Hooks and patterns

React 19 ships without a standalone Signals API; it retains the hooks-based model with
React Compiler for automatic memoization. Key patterns:

### Core hooks discipline

```tsx
// Prefer built-in hooks; avoid `useCallback`/`useMemo` in new code —
// React Compiler handles memoization automatically in React 19.
import { useState, useEffect, useRef, useTransition, useDeferredValue } from "react";

// useTransition — non-urgent state updates (navigation, search filtering)
const [isPending, startTransition] = useTransition();
startTransition(() => setFilter(value));

// useDeferredValue — defer re-renders during expensive derivations
const deferred = useDeferredValue(searchQuery);

// useOptimistic — optimistic UI without manual rollback logic (React 19)
const [optimisticItems, addOptimistic] = useOptimistic(items);
```

### React 19 `use()` hook

`use()` is the new primitive for reading a Promise or Context inside render:

```tsx
import { use, Suspense } from "react";

// Read a Context without useContext
const theme = use(ThemeContext);

// Suspend on a Promise (must be wrapped in Suspense + ErrorBoundary)
function UserCard({ promise }: { promise: Promise<User> }) {
  const user = use(promise);  // suspends until resolved
  return <div>{user.name}</div>;
}
```

### React 19 `useActionState` and Server Actions (App Router)

```tsx
// Client component wiring for server actions
"use client";
import { useActionState } from "react";
import { submitForm } from "@/app/actions"; // server action

const [state, formAction, isPending] = useActionState(submitForm, null);
```

### React Compiler

React 19 includes experimental React Compiler (formerly React Forget). With Compiler
enabled, manual `useMemo` and `useCallback` are largely redundant. Enable in
`next.config.ts` (Next.js 15) or `vite.config.ts` (Vite):

```ts
// next.config.ts
const nextConfig = {
  experimental: {
    reactCompiler: true,
  },
};
```

**Gotchas**:
- React Compiler requires all components to follow the Rules of Hooks strictly. ESLint
  `eslint-plugin-react-hooks` must be enabled — Compiler violations surface as runtime
  errors without it.
- `use()` inside a component must always be called at the top level (same rules as all
  hooks). It cannot be called conditionally.
- `useOptimistic` requires React 19; do not polyfill with manual state — the semantics
  differ.

---

## Vite scaffolding

For standalone React apps (not using Next.js):

```bash
npm create vite@latest my-app -- --template react-ts
cd my-app
pnpm install   # switch to pnpm after scaffolding
```

Vite 6+ `vite.config.ts` with React plugin:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";   // uses Babel
// or: import react from "@vitejs/plugin-react-swc"; // uses SWC (faster)

export default defineConfig({
  plugins: [react()],
});
```

**Choosing Babel vs SWC**: use `@vitejs/plugin-react-swc` for faster builds in
development. Use `@vitejs/plugin-react` (Babel) if you need Babel plugins (e.g., styled-
components transform) or React Compiler experimental transforms.

---

## Next.js 15 — App Router

### Project scaffolding

```bash
pnpm create next-app@latest my-app --typescript --eslint --app --src-dir --turbopack
```

The `--app` flag enables the App Router (stable in Next.js 13+; default in Next.js 15).

### React Server Components (RSC)

App Router components are Server Components by default. Mark client-only components at
the top of the file:

```tsx
"use client";  // required for hooks, browser APIs, event handlers

export function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
}
```

RSC composition rules:
- Server Components can import Client Components (leaf boundary is fine)
- Client Components **cannot** import Server Components (would send server code to browser)
- Pass Server Component output to Client Components via `children` prop

```tsx
// ✓ Correct: Server Component passes content to Client Component as children
// app/page.tsx (Server Component)
import { InteractiveWrapper } from "@/components/InteractiveWrapper"; // "use client"
import { fetchData } from "@/lib/data";

export default async function Page() {
  const data = await fetchData();  // runs on server
  return (
    <InteractiveWrapper>
      <ServerRenderedContent data={data} />  {/* RSC output as children */}
    </InteractiveWrapper>
  );
}
```

### Server Actions

Server Actions are async functions that run on the server, invoked from Client or Server
Components. They are the primary data mutation mechanism in App Router.

```ts
// app/actions.ts
"use server";

export async function createUser(formData: FormData) {
  const name = formData.get("name") as string;
  await db.user.create({ data: { name } });
  revalidatePath("/users");  // invalidate cached route
}
```

Invoke from a form (Server Component):

```tsx
// app/new-user/page.tsx — no "use client" needed
import { createUser } from "@/app/actions";

export default function NewUserPage() {
  return (
    <form action={createUser}>
      <input name="name" />
      <button type="submit">Create</button>
    </form>
  );
}
```

**Gotchas**:
- Server Actions **must** be in files with `"use server"` at the top, OR each function
  must have `"use server"` as its first line.
- Form `action` prop only accepts Server Actions (async functions marked `"use server"`).
  Use `useActionState` for client-side state binding.
- `revalidatePath` and `revalidateTag` must be called from Server Actions, Route
  Handlers, or Server Components — never from Client Components.

### Route Handlers

```ts
// app/api/users/route.ts
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const id = searchParams.get("id");
  return Response.json({ id });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  // ... process ...
  return Response.json({ created: true }, { status: 201 });
}
```

Route Handler conventions:
- Named exports match HTTP methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`,
  `OPTIONS`
- Use `NextRequest` (extends standard `Request`) for `nextUrl`, cookies, geo
- Return standard `Response` or `NextResponse`; `Response.json()` is preferred over
  `NextResponse.json()` for forward-compatibility with the standard API

### `next.config.ts`

Next.js 15 supports TypeScript-native config:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Turbopack is the default dev bundler in Next.js 15
  experimental: {
    reactCompiler: true,    // opt-in; enable once compiler is stable for your usage
  },
};

export default nextConfig;
```

---

## Testing — React Testing Library + Vitest

React projects use **React Testing Library (RTL)** layered on top of Vitest. The
`contexts/typescript.md` baseline provides the Vitest setup; this section adds the
React-specific configuration.

### Install

```bash
pnpm add -D @testing-library/react @testing-library/user-event @testing-library/jest-dom
pnpm add -D jsdom                  # JSDOM environment for Vitest
```

### `vitest.config.ts` (React projects)

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";  // or -swc

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,                         // eliminates `import { describe } from "vitest"` boilerplate
    setupFiles: ["./src/setupTests.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
    },
  },
});
```

`src/setupTests.ts`:

```ts
import "@testing-library/jest-dom";
```

### RTL patterns

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Counter } from "./Counter";

describe("Counter", () => {
  it("increments on click", async () => {
    const user = userEvent.setup();
    render(<Counter />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});
```

### Testing Server Components (Next.js)

Server Components cannot be rendered with RTL (they are async functions, not React
components in the browser sense). Test them by:

1. **Unit-test the data layer** — test the `async` data-fetching functions directly
2. **Integration-test via Route Handlers** — use `next-test-api-route-handler` or
   `msw` to mock at the network layer
3. **E2E with Playwright** — the only way to test the full RSC → hydration path

**Gotcha**: Do not import `"use client"` components in Server Component tests run in
Node (they work, but the Client Component boundary is not enforced in unit tests — only
E2E tests catch boundary violations).

---

## End-to-end testing — Playwright

Playwright is the recommended E2E framework for React/Next.js. It handles async hydration,
Server Component rendering, and Client Component interaction.

### Install

```bash
pnpm create playwright
# OR add to existing project:
pnpm add -D @playwright/test
pnpm playwright install --with-deps chromium
```

### `playwright.config.ts`

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
  },
});
```

### Playwright + RTL strategy

- **Unit / component tests** → RTL + Vitest (fast, no browser, no network)
- **E2E / integration** → Playwright (full browser, tests the real app including SSR)

Do not mix the two in the same test file. RTL tests run in Vitest's JSDOM environment;
Playwright tests run in a real browser via the Playwright runner.

---

## Package.json scripts

Recommended `package.json` scripts for a Next.js 15 + RTL + Playwright project:

```json
{
  "scripts": {
    "dev": "next dev --turbopack",
    "build": "next build",
    "start": "next start",
    "lint": "eslint .",
    "format": "prettier --write .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
  }
}
```
