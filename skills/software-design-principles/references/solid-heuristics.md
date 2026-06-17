# SOLID as Balanced-Coupling Heuristics

Per-principle deep tier for the [`software-design-principles`](../SKILL.md) skill.

Each principle below is presented as a lever on **knowledge flow**: what knowledge
it keeps from leaking, and what coupling pole it pushes you away from. The classic
definitions (Martin; the canonical OO statements) are durable — this reference
keeps them but reframes the *why* through balanced coupling, which generalizes the
principle past objects to functions, modules, services, and agent tools.

> The unifying claim (Khononov's balanced coupling, applied to the AI era by
> Vladikk): modularity emerges when integration strength and distance balance.
> SOLID violations are all *imbalances* — knowledge flowing where it shouldn't, or
> failing to flow where it should. AI authorship does not change this; it only
> makes imbalance compound faster.

---

## SRP — Single Responsibility Principle

**Classic:** A unit has one, and only one, reason to change.
**Martin's sharper form:** "Gather together the things that change for the same
reasons; separate things that change for different reasons."

**Knowledge-flow framing:** SRP is the *cohesion* lever. Two responsibilities in
one unit means two unrelated change vectors share a location — a change for reason
A risks code that exists for reason B. The "reason to change" usually traces to a
distinct *actor* or *stakeholder*.

**Smell:** a module named for a layer or a catch-all (`utils`, `helpers`,
`manager`) rather than a domain concept; a class you must edit for unrelated tickets.

**Sketch:**

```
# Entangled: validation, hashing, email, persistence — four reasons to change
UserManager: validate_email · hash_password · send_welcome_email · store_user

# Cohesive: one reason to change each
EmailValidator · PasswordHasher · WelcomeMailer · UserRepository
```

**Do-not-overdo:** splitting parts that genuinely change *together* lowers
cohesion and raises coupling. Cohesion is about shared reasons-to-change, not
about making files small.

---

## OCP — Open/Closed Principle

**Classic:** Open for extension, closed for modification — add behavior without
editing existing code.

**Knowledge-flow framing:** OCP shields a stable core from *modification
coupling*. New behavior arrives through a new implementation of an existing
abstraction, so the existing, tested code is not touched. You are choosing *which
change vector to make cheap* — anticipate the reasonable one, not every
conceivable one.

**Smell:** a growing `if/elif`/`switch` over a type tag that you edit for every
new case; a "god function" every feature appends to.

**Sketch:** replace a type-switch with a polymorphic / strategy abstraction so a
new case is a new file, not an edit to the dispatcher.

**Do-not-overdo:** OCP is the principle most often applied *prematurely*. An
extension seam designed before the second variant exists is speculation. Wait for
the second real case, then abstract along the axis that actually varies
(Incremental Evolution).

---

## LSP — Liskov Substitution Principle

**Classic:** Subtypes must be substitutable for their base type without breaking
correctness.
**Martin's form:** "A program using an interface must not be confused by an
implementation of that interface."

**Knowledge-flow framing:** LSP forbids *implicit* knowledge. A substitute that
strengthens preconditions, weakens postconditions, throws where the base didn't,
or quietly no-ops violates a contract the caller relied on but could not see. That
hidden assumption is coupling with no visible dependency edge — the worst kind.

**Smell:** `isinstance`/type checks in the caller to special-case a subtype;
overrides that raise `NotSupported`; the rectangle/square trap (an override that
breaks an invariant the caller assumes).

**Rule of thumb:** if callers must know *which* implementation they hold, the
abstraction is leaking — fix the contract or split the interface (→ ISP).

---

## ISP — Interface Segregation Principle

**Classic:** No client should be forced to depend on methods it does not use.

**Knowledge-flow framing:** every method on an interface is knowledge exposed to
every client. Unused methods are pure *coupling overhead* — they couple a client
to changes it has no stake in. Segregate fat interfaces into role-specific ones so
each client depends on exactly its slice.

**Smell:** an interface with a dozen methods where most implementers stub half of
them; a "fat" service contract every consumer imports wholesale.

**Sketch:** split `IMultiFunctionDevice(print, scan, fax)` into `IPrinter`,
`IScanner`, `IFax`; a print-only client depends only on `IPrinter`.

**AI-era note:** ISP is acute for agent tool and API surfaces — a fat tool with
twenty optional parameters exposes more than the model needs to reason about, and
every field is decision surface. See [agent-as-consumer.md](agent-as-consumer.md).

---

## DIP — Dependency Inversion Principle

**Classic:** High-level modules must not depend on low-level modules; both depend
on abstractions. Abstractions must not depend on details; details depend on
abstractions.

**Knowledge-flow framing:** DIP controls the *direction* of knowledge flow.
Business policy (high-level, stable, valuable) should not know about mechanism
(low-level, volatile — SQL dialect, HTTP client, file format). Invert so the
detail implements an abstraction the policy owns; volatile knowledge points *up*
toward stable abstractions, never the reverse.

**Smell:** a domain/service class that `new`s a concrete database, SMTP client, or
HTTP library directly; import edges from core logic to vendor SDKs.

**Sketch:**

```
# Concrete dependency — policy bound to mechanism
OrderProcessor() { db = PostgresDatabase(); mailer = SmtpMailer() }

# Inverted — policy depends on abstractions, details are injected
OrderProcessor(db: Database, mailer: Mailer)
```

**Enforcement:** DIP is the SOLID principle most amenable to an executable
fitness function ("the domain layer must not import infrastructure"). Cite
`CLAUDE.md§Balanced Coupling`; see the `architectural-fitness-functions` skill.

**Do-not-overdo:** inversion earns its keep when the mechanism is volatile or
needs swapping/testing in isolation. Inverting a stable, single-implementation
dependency adds an indirection with no payoff.

---

## Cross-cutting: reading the five as one

| If you see… | The leaking knowledge is… | The lever |
|---|---|---|
| One unit edited for unrelated reasons | two change vectors sharing a home | SRP |
| Every feature edits the same code | the variation axis isn't a seam | OCP |
| Callers special-case subtypes | a contract assumption that's invisible | LSP |
| Clients import methods they ignore | exposure beyond need | ISP |
| Core logic imports a vendor SDK | volatile detail flowing into stable policy | DIP |

All five reduce to: *does knowledge live where it changes, and does it flow toward
stability?* Apply the lever that matches the leak — not all five at once.
