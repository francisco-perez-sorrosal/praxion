# TypeScript Representation Patterns

TypeScript idioms for the Representation Design Pass: discriminated unions, branded types, boundary parsing, exhaustiveness, immutability. Load only when the project language is TypeScript/JavaScript. Back to [SKILL.md](../SKILL.md).

## Discriminated Unions with Exhaustiveness

**Failure shape — correlated nullables (product type):**

```typescript
interface Job {
  status: string;                 // "pending" | "running" | "done" | "failed"... hopefully
  startedAt?: Date;               // must be set iff status !== "pending"
  result?: Uint8Array;            // must be set iff status === "done"
  error?: string;                 // must be set iff status === "failed"
}
```

**Corrected — one variant per legal state, closed with a `never` check:**

```typescript
type Job =
  | { kind: "pending" }
  | { kind: "running"; startedAt: Date }
  | { kind: "done"; startedAt: Date; result: Uint8Array }
  | { kind: "failed"; startedAt: Date; error: string };

function describe(job: Job): string {
  switch (job.kind) {
    case "pending": return "queued";
    case "running": return `running since ${job.startedAt}`;
    case "done": return "finished";
    case "failed": return job.error;
    default: {
      const unreachable: never = job;   // compile error when a variant is added
      return unreachable;
    }
  }
}
```

The `kind` discriminant narrows automatically inside each branch — no casts, no re-checks. Adding a fifth variant turns every non-exhaustive `switch` in the codebase into a compile error, which is exactly the ripple you want.

## Closed Option Sets: Literal Unions over `enum`

- Prefer a union of string literals (`type Status = "pending" | "shipped" | "delivered"`) — zero runtime, structural, serializes as itself
- When runtime iteration is needed, derive the union from a `const` object so there is one source of truth:

```typescript
const STATUSES = ["pending", "shipped", "delivered"] as const;
type Status = (typeof STATUSES)[number];
```

- Avoid TypeScript `enum` in new code: numeric enums are unsound in both directions, and `const enum` breaks under isolated-module transpilation. The literal-union + `as const` pattern covers the same ground without the pitfalls

## Branded Types: Domain Identity in a Structural Type System

TypeScript's structural typing means two aliases of `string` interchange freely — the brand is what makes them nominal:

```typescript
type AccountId = string & { readonly __brand: "AccountId" };
type OrderId = string & { readonly __brand: "OrderId" };

function accountId(raw: string): AccountId {
  if (!/^acc_[a-z0-9]{12}$/.test(raw)) throw new Error(`invalid account id: ${raw}`);
  return raw as AccountId;              // the single sanctioned cast, here only
}
```

An `OrderId` passed where an `AccountId` is expected is now a compile error, though both are strings underneath. Export the type and the parse/constructor function; never export the cast.

## Parse, Don't Validate: Schema Library at the Boundary

**Failure shape:** `JSON.parse` returns `any`; the value travels typed-as-anything until something crashes at first use, four layers deep.

**Corrected — parse once with a schema library (zod shown), infer the type from the schema:**

```typescript
const CreateUserRequest = z.object({
  email: z.string().email(),
  displayName: z.string().min(1).max(80),
});
type CreateUserRequest = z.infer<typeof CreateUserRequest>;

function handleCreateUser(raw: unknown): UserId {
  const req = CreateUserRequest.parse(raw);   // parse ONCE, fail here
  return userService.create(toDomainUser(req));  // interior sees only domain types
}
```

- Type `JSON.parse` results and network payloads as `unknown`, never `any` — `unknown` forces the parse; `any` silently disables checking for everything it touches
- `z.infer` keeps the schema and the static type from drifting: one artifact is both the runtime validator and the compile-time contract
- The wire type and the domain type may differ; the handler is where one becomes the other

## Immutability Defaults

- `readonly` fields on object types; `ReadonlyArray<T>` / `readonly T[]` in signatures that must not mutate input
- `as const` for literal configuration shapes — freezes both values and types
- `satisfies` to check a value against a contract without widening its inferred type:

```typescript
const config = {
  retries: 3,
  backoff: "exponential",
} satisfies RetryPolicy;   // checked against RetryPolicy, type stays narrow
```

## State Machines: Transitions as Functions Between State Types

```typescript
type DraftOrder = { kind: "draft"; items: LineItem[] };
type SubmittedOrder = { kind: "submitted"; items: LineItem[]; payment: PaymentMethod; submittedAt: Date };

function submit(order: DraftOrder, payment: PaymentMethod): SubmittedOrder {
  if (order.items.length === 0) throw new Error("cannot submit an empty order");
  return { kind: "submitted", items: order.items, payment, submittedAt: new Date() };
}
// submit(submittedOrder, ...) does not compile — submitting twice has no representation
```

## TypeScript-Specific Gotchas

- **Structural typing interchanges same-shaped types** — `{ id: string }` is `{ id: string }` regardless of intent; brand the ones that must never mix
- **Optional property (`x?: T`) vs `x: T | undefined` are different contracts** — the first may be absent, the second must be present-but-possibly-undefined; with `exactOptionalPropertyTypes` the compiler enforces the distinction. Pick per field deliberately: "not yet known" and "known to be empty" are different states
- **Excess-property checking only fires on object literals** — a widened variable assigned to a narrower type sneaks extra fields through; `satisfies` at the definition site catches this
- **`null` vs `undefined`** — pick one absence marker per codebase (idiomatic TS: `undefined` internally, translate `null` at wire boundaries) and encode the policy in the schema layer, not per call site
- **Types are erased at runtime** — like Python's hints, a TS type enforces nothing once compiled; every boundary still needs a runtime parse, and every internal invariant needs a constructor that checks it
