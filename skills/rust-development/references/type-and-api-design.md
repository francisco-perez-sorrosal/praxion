# Type & API Design

Part of the [Rust Development](../SKILL.md) skill. Covers the Rust API Guidelines' type-driven
design vocabulary — the C-XXX checklist items that make "make invalid states unrepresentable"
mechanically citable rather than a taste preference.

**Crate-role fork.** Several patterns below matter more, or differently, depending on the crate's
role (see the skill's own [Crate Role](../SKILL.md#crate-role) table). Sealed traits,
`#[non_exhaustive]`, minimized visibility, and eager trait implementation are primarily **library**
concerns — they exist to protect a semver contract the orphan rule and public API make otherwise
fragile. Newtype, builder, and typestate are universal: an internal workspace crate or a binary
benefits from them just as much, because the payoff (illegal states become compile errors) has
nothing to do with who consumes the crate.

## Accept Borrowed, Return Owned

Take the borrowed target type, not the owning wrapper: `&str` not `&String`, `&[T]` not
`&Vec<T>`, `&T` not `&Box<T>`. Deref coercion means the borrowed form accepts strictly more
callers with strictly less indirection — a caller holding an owned `String` still coerces to
`&str` at the call site, but a caller holding only a `&str` cannot call a function that demands
`&String` ([Rust Design Patterns — borrowed arguments](https://rust-unofficial.github.io/patterns/idioms/coercion-arguments.html)).

```rust
// Narrower than necessary — a &str-only caller must allocate a String first
fn word_count(s: &String) -> usize { s.split_whitespace().count() }

// Accepts both &String (via coercion) and &str
fn word_count(s: &str) -> usize { s.split_whitespace().count() }
```

Generalize further with `impl AsRef<Path>` / `AsRef<str>` where the guideline's **C-GENERIC**
applies — `File::open` takes `AsRef<Path>` precisely so callers are not forced to convert first.
The guideline names the cost too: monomorphization grows code size, and a generic parameter forces
*precise* types (`fn binary<T: Trait>(x: T, y: T)` requires both arguments to share exactly one
concrete `T`) ([API Guidelines § Flexibility](https://rust-lang.github.io/api-guidelines/flexibility.html)).

**C-CALLER-CONTROL**: if a function needs ownership, take it — never borrow-and-clone internally
to fake a borrowing signature. If it does not need ownership, take a reference. Ownership decisions
belong to the caller, not the callee's convenience.

**C-INTERMEDIATE**: return the interesting by-product a computation already produced rather than
discarding it — `Vec::binary_search` returns the insertion index on failure; `String::from_utf8`
returns the offending byte offset on failure.

## Generics vs `dyn Trait` (C-OBJECT)

Decide early — the choice changes the trait's shape, not just the call site.

| | Generics (static dispatch) | `dyn Trait` (dynamic dispatch) |
|---|---|---|
| Codegen | Monomorphized per concrete type — inlining, larger binary | Single codegen — smaller binary, one vtable indirection per call |
| Heterogeneity | No — one concrete type per instantiation | Yes — `Vec<Box<dyn Trait>>` holds mixed types |
| Generic methods on the trait | Allowed | **Not allowed** — a trait with a generic method cannot be object-safe |
| `Self` in return position | Allowed | Only in receiver position (`&self`, `self: Box<Self>`) |

Object-safe-by-design traits exclude the problem method with `where Self: Sized` instead of
abandoning object safety for the whole trait:

```rust
trait Shape {
    fn area(&self) -> f64;
    fn clone_boxed(&self) -> Box<dyn Shape>;

    // Excluded from the trait object's vtable, not from the trait itself
    fn make_default() -> Self where Self: Sized;
}
```

`[certainty: high — API Guidelines C-OBJECT and Effective Rust Item 12 converge independently]`

## Newtype (C-NEWTYPE, C-CUSTOM-TYPE)

Wrap a primitive to make a semantic distinction static — `Miles(f64)` vs `Kilometers(f64)` cannot
be passed to each other's functions by accident. The guideline's own justification is the Mars
Climate Orbiter unit-confusion failure: a runtime bug the type system can make a compile error.

```rust
struct Miles(f64);
struct Kilometers(f64);

fn distance_to_target(d: Kilometers) -> Kilometers { /* ... */ d }
```

Two further uses beyond unit confusion:

- **C-NEWTYPE-HIDE** — wrap a complex or unstable return type so its concrete representation
  stays free to change without breaking the public signature.
- **Orphan-rule escape** — `struct MyError(String)` lets a crate implement a foreign trait
  (`std::error::Error`) for a type it now owns, which it could not do for `String` directly.

**Type-design smells and their remedy** — the practical, agent-checkable form of "make illegal
states unrepresentable":

| Smell | Remedy |
|---|---|
| `bool` or `Option<bool>` parameter | Enum (**C-CUSTOM-TYPE**) — `print_page(true, false)` → `print_page(Sides::Both, Output::BlackAndWhite)`; the compiler now catches argument transposition a bool signature accepts silently, and growing the enum (`ExtraLarge`) needs no API restructuring |
| Two fields whose valid combinations are a strict subset of the cross product | Lift into one enum — `struct DisplayProps { monochrome: bool, fg_color: RgbColor }` (comment: "`fg_color` must be black if `monochrome`") → `enum Color { Monochrome, Foreground(RgbColor) }`; a comment-enforced invariant becomes a type-enforced one |
| `pub` field on a type whose doc comment states an invariant ("must be", "only valid if") | Private field + validating constructor (**C-STRUCT-PRIVATE**) |
| Primitive crossing an API boundary with unit/identity semantics (`u64` user id, `f64` metres, bare `String` token) | Newtype (**C-NEWTYPE**) |
| A flag *set*, not a single choice | `bitflags`, not an enum (**C-BITFLAG**) — an enum cannot represent a combination |

## Builder (C-BUILDER)

For types with many optional or interdependent constructor parameters (more than ~3 is the usual
trigger). Two shapes:

```rust
// Non-consuming (&mut self) — preferred: supports one-liners and staged construction
struct RequestBuilder { url: String, timeout_ms: Option<u32> }
impl RequestBuilder {
    fn new(url: impl Into<String>) -> Self { Self { url: url.into(), timeout_ms: None } }
    fn timeout_ms(&mut self, ms: u32) -> &mut Self { self.timeout_ms = Some(ms); self }
    fn build(&self) -> Request { /* ... */ }
}

// Consuming (self) — requires reassignment in loops/conditionals; fine for a strict one-liner API
struct RequestBuilder2 { url: String }
impl RequestBuilder2 {
    fn timeout_ms(self, ms: u32) -> Self { self /* ... */ }
}
```

Prefer the non-consuming shape unless every caller builds in a single fluent chain — the consuming
shape forces `builder = builder.step(x);` inside a loop instead of a plain method call.

## Typestate

Encode the object's *state* in its *type*; transitions are consuming methods
(`fn into_x(self) -> Other`), so the prior state is statically unusable after a transition. A
zero-sized marker type or `PhantomData` carries the state parameter at no runtime cost. Result:
illegal state *sequences* — not just illegal state *values* — become compile errors
([Embedded Rust Book § Typestate Programming](https://docs.rust-embedded.org/book/static-guarantees/typestate-programming.html)).

```rust
struct Locked;
struct Unlocked;

struct Door<State> { _state: std::marker::PhantomData<State> }

impl Door<Locked> {
    fn unlock(self, _key: &Key) -> Door<Unlocked> { Door { _state: std::marker::PhantomData } }
}
impl Door<Unlocked> {
    fn open(&self) { /* ... */ }
    fn lock(self) -> Door<Locked> { Door { _state: std::marker::PhantomData } }
}
```

Calling `.open()` on a `Door<Locked>` is a compile error, not a runtime panic or an `Err` return.
The builder pattern is the degenerate two-state case of this same idea (unbuilt → built).

**Method guarded by a runtime state check** is the type-design smell this pattern remedies — if a
method already begins `if self.state != State::Ready { return Err(...) }`, that check is a
candidate for a typestate split instead.

## Sealed Traits (C-SEALED)

Prevents downstream crates from implementing a public trait, so the trait author can add methods
or change non-public signatures without it being a breaking change:

```rust
pub trait TheTrait: private::Sealed {
    fn public_method(&self);
}

mod private {
    pub trait Sealed {}
    impl Sealed for crate::SomeType {}
}
```

Downstream crates cannot name `private::Sealed` (it is not `pub`), so they cannot satisfy
`TheTrait`'s supertrait bound and therefore cannot implement it. **Document that the trait is
sealed** — the guideline requires this explicitly, since the compile error a downstream
implementer hits is otherwise unexplained.

**Library-vs-application fork**: sealing exists to protect a semver contract across a crate
boundary you do not control. An application's own internal traits, or a trait entirely local to one
workspace crate with no external implementers, gain nothing from sealing — it is a library-role
concern.

## `#[non_exhaustive]`

Applies to structs, enums, and individual enum variants. Downstream effects:

- Cannot construct a non-exhaustive struct with a struct expression (tuple-struct constructors drop
  to `pub(crate)`).
- Must use `..` in struct patterns and a `_` arm on `match`.
- Cannot `as`-cast an enum containing non-exhaustive variants.
- Enum *variants themselves* remain constructible unless the individual variant is also marked.
- **Inside the defining crate it has no effect at all** — the attribute only constrains external
  crates ([Rust Reference § Type system attributes](https://doc.rust-lang.org/reference/attributes/type_system.html)).

Pairs with **C-STRUCT-PRIVATE**: public fields are reserved for "compound, passive data structures
in the C spirit" — anything carrying an invariant hides its fields behind a validating constructor
instead of relying on `#[non_exhaustive]` alone.

**Library-vs-application fork**: `#[non_exhaustive]` is a future-proofing valve for a type crossing
a semver boundary. An application's own enums, consumed only by its own `main`, do not need it —
adding a variant to an internal enum is not a breaking change to anyone.

## Struct Field Visibility & Bounds (C-STRUCT-PRIVATE, C-STRUCT-BOUNDS)

**Don't bake derivable bounds into a type definition.** `#[derive]` emits the correct bound
per-`impl` automatically; writing the bound on the struct itself is a permanent, breaking
commitment that every future consumer inherits whether they need it or not.

```rust
// Wrong: every caller of Foo<T> now needs T: Clone, even ones that never clone
struct Foo<T: Clone> { value: T }

// Right: the bound lives on the impl that actually needs it
struct Foo<T> { value: T }
impl<T: Clone> Foo<T> { fn duplicate(&self) -> Self { /* ... */ } }
```

Never bound the type definition on: `Clone`, `PartialEq`, `PartialOrd`, `Debug`, `Display`,
`Default`, `Error`, `Serialize`, `Deserialize`, `DeserializeOwned`.

**Trait implementation hygiene (C-COMMON-TRAITS, C-CONV-TRAITS)**: implement
`Copy`/`Clone`/`Eq`/`PartialEq`/`Ord`/`PartialOrd`/`Hash`/`Debug`/`Display`/`Default` eagerly — the
orphan rule means a downstream crate cannot add these later if you skip them. Implement
`From`/`TryFrom`/`AsRef`/`AsMut`; **never** implement `Into`/`TryInto` directly (a blanket impl over
`From` already exists — a manual `Into` impl conflicts with it). `Debug` on every public type
(**C-DEBUG**), and never an empty `Debug` output (**C-DEBUG-NONEMPTY**).

**Library-vs-application fork**: eager trait implementation is a library-role concern rooted in the
orphan rule — an application's own types have no downstream crate that could need to add the impl
later, so the "implement it now or never" pressure does not apply with the same force.

## Naming Conventions

**Conversions (C-CONV)** — the method-name prefix encodes cost and ownership; picking the wrong
prefix misleads every caller who has internalized the convention:

| Prefix | Cost | Ownership |
|---|---|---|
| `as_` | Free | Borrowed → borrowed |
| `to_` | Expensive | Borrowed → borrowed, or borrowed/owned → owned |
| `into_` | Variable | Owned → owned (non-`Copy`) |

**Getters (C-GETTER)**: no `get_` prefix except for a single obvious value (`Cell::get`) —
`first()`, not `get_first()`. Validated-access families follow `get`/`get_mut`/`get_unchecked`/
`get_unchecked_mut`.

**Iterators (C-ITER / C-ITER-TY)**: `iter(&self)`, `iter_mut(&mut self)`, `into_iter(self)`; the
returned types are named `Iter`, `IterMut`, `IntoIter` and module-qualified (`vec::IntoIter`).

## Anti-pattern: Deref Polymorphism

Implementing `Deref` to fake inheritance is an explicit anti-pattern, not a stylistic quibble: it
surprises readers, does not create real subtyping (trait implementations do not transfer through
`Deref`), and `self` inside the wrapped type's methods still binds to the wrapped type, not the
wrapper ([Rust Design Patterns § Deref polymorphism](https://rust-unofficial.github.io/patterns/anti_patterns/deref.html)).

```rust
// Anti-pattern: looks like inheritance, isn't
struct Wrapper(Base);
impl std::ops::Deref for Wrapper {
    type Target = Base;
    fn deref(&self) -> &Base { &self.0 }
}
// Wrapper now "has" Base's inherent methods via auto-deref, but Wrapper does not
// implement any trait Base implements, and Base's methods that take &self still
// operate on the Base value, not on any Wrapper-level state.
```

Use a trait or explicit delegation (a method on `Wrapper` that forwards to `self.0`) instead.
Reinforced by two related guideline items: **C-DEREF** — only genuine smart pointers implement
`Deref`/`DerefMut` — and **C-SMART-PTR** — smart pointers add no inherent methods of their own,
so there is nothing on the wrapper itself to collide with the target's namespace.
