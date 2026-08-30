# Rust Representation Patterns

Rust idioms for the Representation Design Pass: type-driven state elimination, boundary parsing, exhaustiveness, flag sets. Load only when the project language is Rust. Back to [SKILL.md](../SKILL.md).

## Smell -> Remedy: The Checklist

Each remedy below is checkable by a reviewing agent: the smell is a grep-able shape (a `bool` in a signature, a `pub` field beside a "must be"/"only valid if" comment, a runtime `if` gating a method call), and the remedy is a fixed transformation, not a taste call.

| Smell | Remedy | Guideline |
| --- | --- | --- |
| `bool` (or `Option<bool>`) parameter | Enum with named variants | C-CUSTOM-TYPE |
| `pub` field on a type whose doc comment states an invariant | Private field + validating constructor | C-STRUCT-PRIVATE |
| Two fields whose valid combinations are a strict subset of the cross product | Lift into an enum | Effective Rust Item 1 |
| A primitive crossing an API boundary with unit/identity semantics | Newtype | C-NEWTYPE |
| More than 3 optional constructor parameters | Builder | C-BUILDER |
| A method only valid in certain object states, guarded by a runtime check | Typestate | typestate pattern |
| `#[derive]`-able bound written on the type definition | Remove the bound | C-STRUCT-BOUNDS |

## `bool` Parameter -> Enum (C-CUSTOM-TYPE)

**Smell** — the call site is unreadable and the compiler cannot catch an argument swap:

```rust
fn print_page(monochrome: bool, both_sides: bool) { /* ... */ }
print_page(true, false);   // which is which?
```

**Remedy** — named variants, and room to grow (`ExtraLarge` needs no signature change):

```rust
enum ColorMode { Monochrome, Color }
enum Sides { OneSided, Both }

fn print_page(color: ColorMode, sides: Sides) { /* ... */ }
print_page(ColorMode::Monochrome, Sides::Both);
```

## `pub` Field + Invariant Comment -> Private Field + Validating Constructor (C-STRUCT-PRIVATE)

**Smell** — the invariant is prose, not code; nothing stops a caller from breaking it:

```rust
pub struct Guess {
    /// Must be between 1 and 100 inclusive.
    pub value: i32,
}
```

**Remedy** — the type *is* the guarantee; every downstream consumer skips re-validation:

```rust
pub struct Guess {
    value: i32,
}

impl Guess {
    pub fn new(value: i32) -> Result<Self, GuessError> {
        if !(1..=100).contains(&value) {
            return Err(GuessError::OutOfRange(value));
        }
        Ok(Self { value })
    }

    pub fn value(&self) -> i32 {
        self.value
    }
}
```

## Correlated Field Pair -> Enum

**Smell** — the comment encodes a rule the type does not enforce:

```rust
struct DisplayProps {
    monochrome: bool,
    /// Must be (0, 0, 0) when `monochrome` is true.
    fg_color: RgbColor,
}
```

**Remedy** — the illegal combination is no longer representable:

```rust
enum Color {
    Monochrome,
    Foreground(RgbColor),
}
```

## Primitive at a Boundary -> Newtype (C-NEWTYPE)

**Smell** — two same-typed values that must never interchange (the Mars Climate Orbiter failure mode):

```rust
fn set_speed(miles: f64) { /* ... */ }
set_speed(100.0);   // miles, or km? the compiler has no opinion
```

**Remedy**:

```rust
struct Miles(f64);
struct Kilometers(f64);

fn set_speed(speed: Miles) { /* ... */ }
set_speed(Miles(100.0));   // Kilometers(100.0) is now a compile error
```

## More Than 3 Optional Constructor Params -> Builder (C-BUILDER)

**Smell** — an `Option`-heavy `new` forces every caller to pass `None` for fields they don't care about:

```rust
impl Request {
    fn new(
        url: String,
        method: Option<Method>,
        headers: Option<HeaderMap>,
        timeout: Option<Duration>,
        retries: Option<u8>,
    ) -> Self { /* ... */ }
}
```

**Remedy** — non-consuming builder (`&mut self` chaining), the preferred shape (supports both one-liners and staged construction):

```rust
pub struct RequestBuilder { url: String, method: Method, timeout: Duration, retries: u8 }

impl RequestBuilder {
    pub fn new(url: impl Into<String>) -> Self {
        Self { url: url.into(), method: Method::Get, timeout: Duration::from_secs(30), retries: 0 }
    }

    pub fn method(&mut self, method: Method) -> &mut Self {
        self.method = method;
        self
    }

    pub fn timeout(&mut self, timeout: Duration) -> &mut Self {
        self.timeout = timeout;
        self
    }

    pub fn build(&self) -> Request {
        Request { url: self.url.clone(), method: self.method, timeout: self.timeout, retries: self.retries }
    }
}
```

## State-Guarded Method -> Typestate

**Smell** — a runtime check stands in for a type distinction; forgetting the check is a runtime panic, not a compile error:

```rust
struct Connection { open: bool }

impl Connection {
    fn send(&mut self, data: &[u8]) {
        if !self.open { panic!("connection not open"); }
        /* ... */
    }
}
```

**Remedy** — the state is the type; `send` does not exist on `Connection<Closed>`:

```rust
struct Open;
struct Closed;
struct Connection<State> { _state: std::marker::PhantomData<State> }

impl Connection<Closed> {
    fn open(self) -> Connection<Open> { Connection { _state: std::marker::PhantomData } }
}

impl Connection<Open> {
    fn send(&mut self, data: &[u8]) { /* ... */ }
    fn close(self) -> Connection<Closed> { Connection { _state: std::marker::PhantomData } }
}
```

`Connection<Closed>::send` is a compile error, not a possible panic — the illegal transition has no representation at all.

## Derivable Bound on the Type Definition -> Remove (C-STRUCT-BOUNDS)

**Smell** — a bound on the struct itself is a permanent, breaking commitment; every user of `Foo<T>` is forced into it even when they never call the method that needs it:

```rust
struct Foo<T: Clone> {
    value: T,
}
```

**Remedy** — bound the `impl` block that actually needs it; `#[derive]` already emits the correct per-impl bound on its own:

```rust
struct Foo<T> {
    value: T,
}

impl<T: Clone> Foo<T> {
    fn duplicate(&self) -> T { self.value.clone() }
}
```

Never bound the type definition on `Clone`, `PartialEq`, `PartialOrd`, `Debug`, `Display`, `Default`, `Error`, `Serialize`, `Deserialize`, or `DeserializeOwned` — the guideline names these as the recurring offenders.

## Boundary Parsing: `serde` at the Edge

Rust's parse-don't-validate mechanism at IO/network/config boundaries is a `serde`-derived struct that only the boundary constructs; the interior sees the already-validated domain type.

**Failure shape** — the wire shape travels deep, re-validated (or not) at every use site:

```rust
#[derive(Deserialize)]
struct RawConfig {
    port: i64,        // could be negative, could overflow u16
    email: String,    // could be anything
}
```

**Corrected** — parse once, at the edge, into a type that carries its own proof:

```rust
#[derive(Deserialize)]
#[serde(try_from = "RawConfig")]
struct Config {
    port: Port,
    email: Email,
}

impl TryFrom<RawConfig> for Config {
    type Error = ConfigError;

    fn try_from(raw: RawConfig) -> Result<Self, Self::Error> {
        Ok(Config { port: Port::new(raw.port)?, email: Email::parse(raw.email)? })
    }
}
```

`#[serde(try_from = "...")]` makes deserialization itself the validation boundary — a malformed `Config` cannot be constructed by `serde_json::from_str` at all; there is no separate "validate after deserialize" step to forget.

## Exhaustive `match` Discipline

Every `match` over a sum type should carry **no wildcard arm** (`_ =>`) unless the omitted variants are genuinely irrelevant to the call site — a wildcard silently absorbs a future variant instead of surfacing it as a compile error.

```rust
enum Job {
    Pending,
    Running { started_at: Instant },
    Done { result: Vec<u8> },
    Failed { error: String },
}

fn describe(job: &Job) -> String {
    match job {
        Job::Pending => "queued".to_string(),
        Job::Running { started_at } => format!("running since {started_at:?}"),
        Job::Done { .. } => "finished".to_string(),
        Job::Failed { error } => error.clone(),
        // no `_` arm: adding a fifth variant is a compile error here, not a silent no-op
    }
}
```

When a wildcard is genuinely warranted (matching one variant out of a large `#[non_exhaustive]` enum from a dependency, for example), name the variants actually handled and let `_` cover only the deliberately-ignored rest — never let it cover a variant you simply forgot.

## Flag Sets: `bitflags`, Not an Enum (C-BITFLAG)

An enum represents exactly one variant at a time — it cannot represent a *combination*. A set of independently-togglable options is a flag set, not a sum type.

**Smell** — a `Vec<Permission>` or a handful of `bool` fields for combinable options:

```rust
struct FilePermissions { read: bool, write: bool, execute: bool }
```

**Remedy**:

```rust
use bitflags::bitflags;

bitflags! {
    struct FilePermissions: u8 {
        const READ    = 0b001;
        const WRITE   = 0b010;
        const EXECUTE = 0b100;
    }
}

let perms = FilePermissions::READ | FilePermissions::WRITE;
assert!(perms.contains(FilePermissions::READ));
```

## Rust-Specific Gotchas

- **A `pub` field is a permanent visibility commitment** — use `pub(crate)` for internals; reserve `pub` for "compound, passive data structures in the C spirit" with no invariant to protect (C-STRUCT-PRIVATE)
- **`#[non_exhaustive]` has no effect inside the defining crate** — it only constrains downstream crates; do not expect it to enforce anything locally
- **A newtype escapes the orphan rule as a side effect** (`struct MyError(String)` can implement `std::error::Error` even though neither `String` nor `Error` is local) — useful, but the primary justification for a newtype is still domain identity, not orphan-rule evasion
- **Typestate transitions must consume `self`** (`fn into_x(self) -> Other`), not take `&self` — a non-consuming transition leaves the prior-state value still callable, which defeats the entire guarantee
- **`bitflags` truncation on construction from raw bits**: the truncating constructor silently drops unknown bits, while the fallible constructor returns `None` on any unknown bit. Pick the fallible form at a trust boundary — silent truncation there is the same failure mode `#[non_exhaustive]` exists to prevent
