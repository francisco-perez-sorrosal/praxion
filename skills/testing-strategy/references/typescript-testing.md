# TypeScript Testing

TypeScript testing patterns with Vitest (recommended) and Jest, type-safe mocking, and integration testing. Back to [SKILL.md](../SKILL.md).

## Framework Selection

| Aspect | Vitest | Jest |
|--------|--------|------|
| **Speed** | Fast (Vite-powered, native ESM) | Slower (transform-heavy) |
| **TypeScript** | Native (via Vite) | Requires `ts-jest` or `@swc/jest` |
| **ESM support** | First-class | Experimental, often painful |
| **API compatibility** | Jest-compatible (`describe`, `it`, `expect`) | Original |
| **Config** | `vitest.config.ts` (or shares `vite.config.ts`) | `jest.config.ts` |
| **Recommendation** | New projects | Existing Jest projects |

**Migrate from Jest to Vitest** when: starting a new project, adopting ESM, or experiencing slow test runs. The API is nearly identical -- most tests need only import changes.

## Vitest Setup

### Installation

```bash
npm install -D vitest @vitest/coverage-v8
```

### Configuration

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,                    // No need to import describe/it/expect
    environment: "node",              // or "jsdom" for browser APIs
    include: ["src/**/*.test.ts", "tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.test.ts", "src/**/*.d.ts"],
    },
    setupFiles: ["./tests/setup.ts"],
    testTimeout: 10_000,
  },
});
```

### Running Tests

```bash
npx vitest                   # Watch mode (default)
npx vitest run               # Single run
npx vitest run --coverage    # With coverage
npx vitest run -t "pattern"  # Filter by test name
npx vitest run src/auth/     # Filter by path
```

## Writing Tests

### Basic Structure

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { UserService } from "./user-service";

describe("UserService", () => {
  let service: UserService;

  beforeEach(() => {
    service = new UserService();
  });

  it("returns user by ID", async () => {
    const user = await service.findById(42);
    expect(user).toEqual({ id: 42, name: "Alice" });
  });

  it("throws for non-existent user", async () => {
    await expect(service.findById(999)).rejects.toThrow("User not found");
  });
});
```

### Common Assertions

```typescript
// Equality
expect(value).toBe(primitive);         // Strict equality (===)
expect(value).toEqual(object);         // Deep equality
expect(value).toStrictEqual(object);   // Deep equality + same type

// Truthiness
expect(value).toBeTruthy();
expect(value).toBeFalsy();
expect(value).toBeNull();
expect(value).toBeUndefined();
expect(value).toBeDefined();

// Numbers
expect(value).toBeGreaterThan(3);
expect(value).toBeCloseTo(0.3, 5);     // Floating point

// Strings
expect(value).toMatch(/pattern/);
expect(value).toContain("substring");

// Arrays
expect(array).toContain(item);
expect(array).toHaveLength(3);
expect(array).toEqual(expect.arrayContaining([1, 2]));

// Objects
expect(obj).toHaveProperty("key", "value");
expect(obj).toMatchObject({ name: "Alice" });

// Errors
expect(() => fn()).toThrow("message");
await expect(asyncFn()).rejects.toThrow(CustomError);
```

## Mocking

### Function Mocks

```typescript
import { vi, describe, it, expect } from "vitest";

// Create a mock function
const mockFn = vi.fn();
mockFn.mockReturnValue(42);
mockFn.mockResolvedValue({ id: 1 });   // Async

// Verify calls
expect(mockFn).toHaveBeenCalledWith("arg1", "arg2");
expect(mockFn).toHaveBeenCalledTimes(1);
```

### Module Mocking

```typescript
import { vi, describe, it, expect } from "vitest";

// Mock an entire module
vi.mock("./database", () => ({
  query: vi.fn().mockResolvedValue([{ id: 1, name: "Alice" }]),
  connect: vi.fn(),
}));

// Import after mocking (Vitest hoists vi.mock)
import { query } from "./database";
import { UserService } from "./user-service";

it("uses mocked database", async () => {
  const service = new UserService();
  const users = await service.listUsers();
  expect(query).toHaveBeenCalledWith("SELECT * FROM users");
  expect(users).toHaveLength(1);
});
```

### Spy on Existing Functions

```typescript
import { vi } from "vitest";

const spy = vi.spyOn(console, "error").mockImplementation(() => {});

// Test code that calls console.error
handleError(new Error("test"));

expect(spy).toHaveBeenCalledWith(expect.stringContaining("test"));
spy.mockRestore();
```

### Type-Safe Mocks

```typescript
interface UserRepository {
  findById(id: number): Promise<User | null>;
  save(user: User): Promise<void>;
}

function createMockRepo(): UserRepository {
  return {
    findById: vi.fn<[number], Promise<User | null>>().mockResolvedValue(null),
    save: vi.fn<[User], Promise<void>>().mockResolvedValue(undefined),
  };
}

it("calls repository with correct ID", async () => {
  const repo = createMockRepo();
  vi.mocked(repo.findById).mockResolvedValue({ id: 1, name: "Alice" });

  const service = new UserService(repo);
  const user = await service.getUser(1);

  expect(repo.findById).toHaveBeenCalledWith(1);
  expect(user?.name).toBe("Alice");
});
```

## Jest Configuration

### Setup (When Required)

```bash
npm install -D jest ts-jest @types/jest
```

```typescript
// jest.config.ts
import type { Config } from "jest";

const config: Config = {
  preset: "ts-jest",
  testEnvironment: "node",
  roots: ["<rootDir>/src", "<rootDir>/tests"],
  testMatch: ["**/*.test.ts"],
  collectCoverageFrom: ["src/**/*.ts", "!src/**/*.d.ts"],
  coverageDirectory: "coverage",
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
};

export default config;
```

### Jest vs Vitest Migration Cheat Sheet

| Jest | Vitest |
|------|--------|
| `jest.fn()` | `vi.fn()` |
| `jest.mock()` | `vi.mock()` |
| `jest.spyOn()` | `vi.spyOn()` |
| `jest.useFakeTimers()` | `vi.useFakeTimers()` |
| `jest.advanceTimersByTime()` | `vi.advanceTimersByTime()` |
| `@types/jest` | Not needed (built-in types) |
| `ts-jest` transform | Not needed (Vite handles TS) |

## Test Patterns

### Testing Async Code

```typescript
it("handles async operations", async () => {
  const result = await fetchData();
  expect(result).toBeDefined();
});

it("handles rejected promises", async () => {
  await expect(failingOperation()).rejects.toThrow("Network error");
});

it("handles callbacks (promisify)", async () => {
  const result = await new Promise<string>((resolve) => {
    legacyCallback((err, data) => resolve(data));
  });
  expect(result).toBe("expected");
});
```

### Testing with Time

```typescript
import { vi, beforeEach, afterEach } from "vitest";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-01-15T10:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

it("expires tokens after 1 hour", () => {
  const token = createToken();
  expect(token.isValid()).toBe(true);

  vi.advanceTimersByTime(61 * 60 * 1000); // 61 minutes
  expect(token.isValid()).toBe(false);
});
```

### Snapshot Testing

```typescript
it("renders component correctly", () => {
  const output = renderComponent({ name: "Alice", role: "admin" });
  expect(output).toMatchSnapshot();
});

// Inline snapshots (no external file)
it("formats error message", () => {
  const msg = formatError(new Error("test"));
  expect(msg).toMatchInlineSnapshot(`"Error: test"`);
});
```

Update snapshots: `npx vitest run --update` or `npx jest --updateSnapshot`.

### Parameterized Tests

```typescript
it.each([
  { input: "", expected: true },
  { input: "hello", expected: false },
  { input: "   ", expected: true },
])("isEmpty($input) returns $expected", ({ input, expected }) => {
  expect(isEmpty(input)).toBe(expected);
});
```

## Integration Testing

### HTTP API Testing with supertest

```bash
npm install -D supertest @types/supertest
```

```typescript
import request from "supertest";
import { createApp } from "./app";

describe("GET /api/users", () => {
  const app = createApp();

  it("returns 200 with user list", async () => {
    const response = await request(app)
      .get("/api/users")
      .set("Authorization", "Bearer test-token")
      .expect(200);

    expect(response.body).toHaveLength(2);
    expect(response.body[0]).toHaveProperty("id");
  });

  it("returns 401 without auth", async () => {
    await request(app).get("/api/users").expect(401);
  });
});
```

### Database Testing

Use transaction rollback for test isolation: `BEGIN` in `beforeEach`, `ROLLBACK` in `afterEach`. This gives each test a clean database state without slow re-seeding.

## Coverage

```bash
# Vitest
npx vitest run --coverage

# Jest
npx jest --coverage
```

Configure coverage thresholds in config:

```typescript
// vitest.config.ts
coverage: {
  thresholds: {
    statements: 80,
    branches: 75,
    functions: 80,
    lines: 80,
  },
}
```

## Gotchas

- **ESM + Jest is painful**: Jest's ESM support requires `--experimental-vm-modules` and `ts-jest/presets/default-esm`. Prefer Vitest for ESM projects.
- **`vi.mock()` is hoisted**: Even if placed inside a test, it runs before imports. This is intentional but surprising. Use `vi.doMock()` for non-hoisted mocking.
- **Mock cleanup**: Call `vi.restoreAllMocks()` in `afterEach` to prevent mock state from leaking between tests. Or set `mockReset: true` in config.
- **Type narrowing in assertions**: `expect(value).toBeDefined()` does not narrow the TypeScript type. Use a type guard or `assert` for subsequent typed access.
- **Test file location**: Vitest defaults to `**/*.test.ts`. Jest defaults to `**/__tests__/**` and `**/*.test.ts`. Ensure config matches your convention.

## Select · Parallelize · Fall Back

**Select**: the resolver dispatches a TypeScript/JS pocket to the project's own test runner -- `vitest related <paths>` or `jest --findRelatedTests <paths>` -- rather than deriving an import graph itself. See [test-selection.md § Ecosystem Dispatch](test-selection.md#ecosystem-dispatch) for the current dispatch table.

**Parallelize**: both Vitest and Jest parallelize by default (worker threads / workers); no extra flag is required for a derived selection.

**Fall back**: when neither `vitest` nor `jest` is discoverable on the pocket (missing config, missing binary), the pocket widens to its full suite (`no-adapter` / `tool-unavailable`) rather than guessing at import relationships.
- **Async test timeout**: Default timeout is 5 seconds (Vitest) or 5 seconds (Jest). Integration tests may need longer: set `testTimeout` in config or per-test with `it("name", async () => {}, 30_000)`.
