# Unsafe and Concurrency

`unsafe` hygiene, `Send`/`Sync`, and the shared-state-vs-message-passing fork. Reference material
for the [Rust Development](../SKILL.md) skill.

## Unsafe Policy

**Default: don't write it.** The legitimate cases are narrow and enumerated: FFI boundaries,
hardware/direct-memory access, and data structures that cannot be expressed under the borrow
checker. Anything outside those three is a design smell, not a performance argument.

**Encapsulate.** Concentrate `unsafe` in a thin wrapper layer that exposes a *safe* API upholding
the invariants; downstream code should never need `unsafe` to use the type correctly.

### `// SAFETY:` Comments — Form and Placement

`// SAFETY:` comments are mandatory, not optional prose, and have a fixed form: uppercase, colon,
one comment per `unsafe` block. Required on:

- every `unsafe` block,
- every `unsafe fn` body,
- every `unsafe impl`.

The comment states *why* the operation is sound — which invariants it relies on, and which it must
uphold. Inside an otherwise-safe function, the argument may rely only on properly constructed
values and checks performed before the block — never on an unstated caller guarantee.

```rust
// SAFETY: `index < self.len` was checked above, so the offset is in bounds
// and the resulting reference does not alias any other live reference to
// this buffer (we hold `&mut self` for the duration of the call).
unsafe { *self.ptr.add(index) = value; }
```

Enforce presence mechanically with `clippy::undocumented_unsafe_blocks` rather than relying on
review discipline alone.

### `unsafe_op_in_unsafe_fn`

Each unsafe operation inside an `unsafe fn` gets its **own** `unsafe` block — not one block
wrapping the whole function body. This became the default in the 2024 edition. The rationale is
auditability: one block per operation means one `// SAFETY:` comment per operation, so a reviewer
can check each precondition independently instead of one comment trying to justify everything the
function does.

```rust
// Edition 2024 default: the fn body is NOT implicitly unsafe just because
// the fn signature is `unsafe fn`. Each operation needs its own block.
unsafe fn write_at(ptr: *mut u8, offset: usize, value: u8) {
    // SAFETY: caller guarantees `ptr` is valid for writes at `offset`
    // (see the function's `# Safety` rustdoc section).
    unsafe { *ptr.add(offset) = value; }
}
```

### Caller-Facing Docs: `# Safety`

Every `unsafe fn` and `unsafe trait` carries a rustdoc `# Safety` section spelling out the
invariants the *caller* must uphold — the same C-FAILURE contract covered in
[error-and-panic.md](error-and-panic.md#doc-comment-error-contract--errors--panics--safety). A
public `unsafe fn` with no `# Safety` section is an incomplete contract, not merely under-documented.

### `unsafe_code = "forbid"` — the Two Legitimate Settings

`[lints.rust] unsafe_code = "..."` has exactly two defensible values, and a project should state
one of them rather than leave the policy implicit:

- **`"forbid"`** — the crate contains no `unsafe` and never should. This also makes a Miri CI job
  close to pure cost, so skip it.
- **`"allow"`** — the crate legitimately contains `unsafe` (FFI, performance-critical data
  structures). Pair it with `clippy::undocumented_unsafe_blocks` and gate a Miri job on `unsafe`'s
  presence rather than skipping it.

Leaving both unset is itself a finding — an unstated `unsafe_code` policy means a reviewer cannot
tell whether the crate's zero-`unsafe` state today is a decision or an accident. See the shipped
lint baseline (`assets/cargo-lints.toml`) for the exact commented-pair form these two settings take
in a real `Cargo.toml`.

### Miri: Evidence, Not Proof

`rustup +nightly component add miri`, then `cargo miri test`. Miri detects out-of-bounds and
use-after-free, uninitialized reads, invalid values (bad enum discriminants, a `bool` outside
0/1), intrinsic precondition violations, misalignment, data races, and aliasing violations under
Stacked/Tree Borrows.

**Stated limits, not a caveat to skim past**: Miri only sees UB on paths actually *executed* by the
test suite, cannot prove a safe API sound over all inputs, cannot explore all thread interleavings,
and has gaps around FFI/networking/platform APIs. A green `cargo miri test` run is **evidence that
the exercised paths are UB-free — not a proof that the type is sound.** Treat it exactly the way you
would treat a passing test suite: necessary, not sufficient, and only as strong as the paths it
actually exercises.

## `Send` / `Sync` Are Unsafe Auto Traits

- `T: Send` means it is safe to *move* a value of type `T` to another thread.
- `T: Sync` means it is safe to *share* `&T` across threads; formally, `T: Sync ⟺ &T: Send`.
- Both are **unsafe auto traits**: the compiler derives them structurally for composites of
  `Send`/`Sync` fields, and a *manual* `unsafe impl Send`/`unsafe impl Sync` asserts a property the
  compiler cannot check on its own — it needs the same kind of written safety argument as an
  `unsafe` block.
- Non-`Send`/non-`Sync` landmarks worth recognizing: raw pointers (`*const T`, `*mut T`) are
  neither, deliberately, as a lint so pointer-holding types don't get auto-marked; `UnsafeCell` is
  not `Sync`, which is why `Cell`/`RefCell` are not `Sync`; `Rc` is neither (its refcount is
  unsynchronized).

### C-SEND-SYNC: the Assertion Test

Types should be `Send + Sync` wherever the underlying data supports it, and the guideline's
mechanism for keeping that true is a compile-time assertion test — so a later field addition that
silently removes `Send`/`Sync` fails CI instead of surfacing as a confusing downstream compile
error in a caller's crate:

```rust
fn assert_send<T: Send>() {}
fn assert_sync<T: Sync>() {}

#[test]
fn my_type_is_send_and_sync() {
    assert_send::<MyType>();
    assert_sync::<MyType>();
}
```

The `static_assertions` crate's `assert_impl_all!(MyType: Send, Sync);` is a common one-line
alternative to hand-rolling the two helper functions above; either form satisfies C-SEND-SYNC.

## Shared State vs. Message Passing

The borrow checker eliminates *data races* — it does not eliminate *deadlocks*. Lock inversion
(thread 1 locks `A` then `B`; thread 2 locks `B` then `A`) compiles and passes the borrow checker
just as readily as a correctly-ordered pair of locks.

**Default preference: message passing** — "share memory by communicating" — with channels.
Actor-style ownership, where one task owns a piece of state and all mutation happens through
messages sent to it, is the structural version of the same idea and removes the lock entirely.

**When shared state is unavoidable**, `Arc<Mutex<T>>` with the `MutexGuard`'s RAII release is the
canonical shape. Discipline that goes with it:

- Keep co-varying data under a **single** lock rather than splitting related fields across
  multiple mutexes — the split is what creates an ordering problem in the first place.
- Minimize the critical section: do the least possible work while holding the guard.
- Never hold a guard across a closure call or return it from a function — both extend its
  lifetime past the point a reviewer can see.
- **Document the lock ordering** wherever more than one lock exists, so "always lock `A` before
  `B`" is a written rule a reviewer can check, not an assumption living only in the author's head.
- Run deadlock detection in CI where the runtime supports it, rather than relying on the ordering
  discipline alone.

## Never Block the Executor

Async tasks yield control only at `.await` points, because the scheduler is cooperative. A
blocking call inside a task — synchronous file I/O, a `std::sync::Mutex` lock held across
meaningful work, a tight CPU loop — blocks the entire worker thread it runs on, which starves
every *other* task scheduled onto that same thread. This is a property of cooperative scheduling
itself, not an artifact of any one async runtime.

The concrete mechanism for routing blocking or CPU-bound work off the async worker pool (a
dedicated blocking pool, or a runtime-specific in-place conversion) is runtime-specific and belongs
to the async-runtime survey in [essential-crates.md](essential-crates.md) — a sibling lens's
subject. The rule that you must route it somewhere is not: whichever runtime a project picks,
"never block the executor" holds without exception.

## Cancellation Safety — Contested, Framed Defensively

A future is **cancellation-safe** if dropping it before completion and later recreating it is a
no-op: no lost data, no partial side effect left behind. It matters in practice because a `select!`
inside a loop drops the losing branches' futures on every iteration — if a losing branch was
mid-way through a non-cancel-safe operation, that partial work is silently discarded.

Some operations are documented as cancel-safe (a channel receive, a listener accept, a stream's
`next`); others are documented as **not** cancel-safe (reading or writing an exact number of bytes,
acquiring a mutex or semaphore guard, and similar operations that can be left in an inconsistent
state if dropped mid-flight).

### C6 — the Model Itself Is Disputed

`[certainty: low — active area; the sources are practitioner design documents, blog posts, and
forum threads, not a settled specification]`

The *hazard* — futures can be dropped mid-operation, and dropping some of them mid-operation is
unsafe to do casually — is canonical and must be taught. What is **not** settled:

- Whether "cancellation safety" is even the right framing for the underlying problem, or whether
  it displaces cognitive cost onto every author and reviewer of every `select!` site rather than
  solving it structurally.
- Whether a language- or runtime-level mechanism (proposals resembling a cleanup callback on drop)
  should replace the current convention of memorizing which operations are safe to cancel.
- Cancellation behavior is documented to vary **across async runtimes** — a pattern that is
  cancel-safe under one runtime's primitives is not guaranteed to be cancel-safe under another's.

**Fair statement, and the posture this reference takes**: present this as a live disagreement, not
a solved problem with a canonical remedy. The defensible defensive posture — until a project's own
ADR resolves it for that project's runtime and use case — is:

- Avoid `select!` branches that contain a non-cancel-safe operation (an exact-size read/write, a
  mutex/semaphore acquire) unless you have specifically verified the drop behavior is safe for your
  case.
- Prefer an owning-task or actor design (see message-passing-first, above) over a `select!` loop
  wherever the same behavior can be expressed without racing futures against each other.
- Treat any manual reasoning about "is this cancel-safe" as fragile and worth a comment recording
  the reasoning, the same way an `unsafe` block gets a `// SAFETY:` comment — because the next
  editor of that `select!` arm has no other way to recover why it was written that way.

Do not let a shipped default resolve this contested area — route the actual decision (which
runtime, which patterns are acceptable in this codebase, whether to adopt an owning-task
convention project-wide) to a per-project ADR, the same way [error-and-panic.md](error-and-panic.md#contested-error-granularity-and-anyhow-in-libraries)
routes its own contested items.
