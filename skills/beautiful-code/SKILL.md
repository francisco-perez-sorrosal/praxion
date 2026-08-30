---
name: beautiful-code
description: >
  The eight dimensions of beautiful code — storytelling, simplicity, clarity of
  intent, expressiveness, purity, sustainability, durability, creativity — as
  named, reviewable qualities with their practitioner canon, techniques, and
  review checks. An index over Praxion's existing conventions plus the depth
  they don't yet carry. Triggers: writing or reviewing code with beauty,
  elegance, or readability at stake; milestone code reviews; asking "is there a
  more elegant way"; judging a creative-but-unfamiliar solution; comment and
  narrative discipline; functional core / imperative shell; backward-compat and
  observable-behavior judgment; reconciling cleverness vs insight.
  Operationalizes CLAUDE.md§Structural Beauty.
allowed-tools: [Read, Grep, Glob]
compatibility: Claude Code
metadata:
  principle: CLAUDE.md§Structural Beauty
---

# Beautiful Code

Beauty serves reliability (`CLAUDE.md§Structural Beauty`); this skill makes it
reviewable by decomposing it into eight named dimensions. It is deliberately an
**index plus gap-filler**: several dimensions are already engraved in Praxion's
conventions, so each section names its *canonical home* and adds only what no
other artifact carries. Never restate a convention that lives in `coding-style`
or a sibling skill — cite it.

**Satellite files** (loaded on-demand):

- [references/dimension-canon.md](references/dimension-canon.md) -- the verified practitioner canon per dimension: quotes with confidence labels, exemplar projects (Redis, SQLite, TigerBeetle, Go, TeX, Linux), documented tensions
- [references/beauty-review-checklist.md](references/beauty-review-checklist.md) -- reviewer checks per dimension with golden bad-cases, for milestone reviews and standalone `/code-review` passes

## Gotchas

- **This skill points before it teaches.** If a check already exists in
  `rules/swe/coding-style.md`, the verifier's Phase 5, or a sibling skill, the
  authority is there — a second statement here would drift
- **"Technical debt" means incomplete understanding, not sanctioned
  sloppiness.** Cunningham's original metaphor licenses shipping code that
  reflects your *current* understanding — visibly, with the gap recorded — and
  never licenses writing code poorly. Cite the original meaning
- **Cleverness is not creativity.** The readability-over-cleverness norm
  targets *line-level language-trick exploitation* (Duff's Device, magic bit
  constants). *Design-level insight* — reframing the problem, exploiting a
  documented domain property — is the creativity this canon celebrates, and it
  usually *increases* readability
- **Purity is a continuum, not a gate.** Grade functions by impurity count
  (reads global / writes global / does I/O / mutates parameters) and move code
  toward zero; demanding all-or-nothing purity buries IO-glue in ceremony
- **"Self-documenting code" is a half-truth.** Naming and structure carry the
  *what*; design rationale, invariants, units, and cross-file obligations can
  only live in comments or design docs. Both the minimal-comment school and
  the comments-are-design school are real traditions — the test is whether
  each comment says something the code cannot
- **Dimensions conflict.** Expressiveness can fight simplicity, the
  compatibility ratchet fights the refactoring urge, creativity fights
  convention. The Tensions section carries the resolutions — apply them, don't
  rediscover them

## The Eight Dimensions

| Dimension | Essence | Canonical Praxion home today |
| --- | --- | --- |
| **Storytelling** | The code, its files, and its commits read as a narrative a human can follow | `coding-style § Reading Order and Narrative`; planner's module-layout-as-table-of-contents |
| **Simplicity** | Fewest braided concerns; every part earns its place | Behavioral contract `Simplicity First`; `coding-style` size/nesting gates; BDD + Incremental Evolution principles |
| **Clarity of intent** | A reader predicts behavior from names and signatures alone | `coding-style § Naming`, `§ Constants Over Magic Values` |
| **Expressiveness** | The construct chosen says the most with the least decoding | `coding-style § Expressive Constructs`, `§ Data Structures and Invariants`; `data-structure-design` |
| **Purity** | Computation isolated from effect; effects at owned edges | `coding-style § Side-Effect Discipline`, `§ Immutability` |
| **Sustainability** | A team can maintain it indefinitely without accumulating cost | Incremental Evolution principle; tech-debt ledger; boy-scout rule; testing-strategy |
| **Durability** | Observable behavior holds across time, versions, unanticipated use | `coding-style § Compatibility and Deprecation`, `§ Error Handling`; `data-structure-design` evolution contracts |
| **Creativity** | Non-obvious, well-fitted solutions at the design level | systems-architect Phase 3 alternatives; the Methodology's "is there a more elegant way?" prompt |

### Storytelling

Code is written for the human who reads it next (Knuth's literate-programming
thesis). The narrative lives at three scales:

- **Within a file** — top-down decreasing abstraction (the newspaper/stepdown
  reading): the top-level function summarizes; details cascade in call order
- **Across files** — the directory tree reads like a table of contents
  (already the implementation-planner's module-layout duty)
- **Across time** — a PR's commit sequence is named, revertible steps with a
  beginning, middle, and end — never "WIP / fix / final fix"

Comments are narrative instruments, not admissions of failure: *why*-comments
(rationale, invariants), *guide* comments (skimmable section structure), and
*checklist* comments ("if you change X, update Y") each say what code cannot —
antirez's taxonomy, with Redis and SQLite as the evidenced exemplars. The
negative poles — comments restating the code, commented-out corpses — stay
banned. Conventions: `coding-style § Reading Order and Narrative`.

### Simplicity

The most engraved dimension — the behavioral contract's `Simplicity First`,
the BDD principle's "simplest thing that achieves it", and the mechanical
size/nesting gates already govern. What the canon adds:

- **Simple ≠ easy** (Hickey): familiar is not structurally simple; simplicity
  is the absence of *complecting* — concerns braided together that could be
  separate
- **Deep modules** (Ousterhout): simple interface hiding real implementation —
  the structural lever; a shallow module (interface ≈ implementation) adds
  surface without hiding anything
- **Essential vs accidental** (Brooks): before simplifying, ask whether the
  *problem* requires the complexity or the *solution* introduced it. Removing
  essential complexity yields simplistic, not simple
- **Subtraction test** (Saint-Exupéry, paraphrase): what can be removed
  without losing required behavior?

### Clarity of intent

Also engraved: intention-revealing names (Beck), no magic values, verb-phrase
functions — all in `coding-style § Naming`. The canon adds the empirical
anchor (full-word identifiers measurably speed comprehension — Hofmeister
2019, 19% faster defect location) and two tests: predict the behavior from
the signature alone; and check names against the domain's own vocabulary
(Evans' ubiquitous language) rather than invented synonyms.

### Expressiveness

Notation is a tool of thought (Iverson): the right construct lets the reader
reason about the *problem*, not decode the *notation*. Prefer the declarative
form (comprehension, pattern match, pipeline) when it removes accumulator
boilerplate the reader must simulate; write idiomatically for the language so
fluent readers read natively; and calibrate surprise to the *actual audience*,
not the author (Matz's own scoping of least-surprise). The ceiling: density
that must be *decoded* rather than *read* has left expressiveness for
cleverness. Conventions: `coding-style § Expressive Constructs`; type-level
expressiveness is `data-structure-design`'s Representation Design Pass.

### Purity

Isolate computation from effect. Three independent traditions converge on one
move — functional core, imperative shell (attributed to Bernhardt); ports and
adapters (Cockburn); gather-compute-use (Carmack): collect inputs at the edge,
pass them through pure logic, apply effects at the end. The payoffs are
Carmack's state-explosion argument (most bugs are unconsidered states) and
mock-free testability — a function needing mocks to test is effect-entangled.
Watch for *purity theater*: a signature that hides an ambient input (global,
singleton, wall clock) is not pure however it reads. Conventions:
`coding-style § Side-Effect Discipline`.

### Sustainability

Maintainability of the code *and* of the people maintaining it — the two are
inseparable (Eghbal's maintainer-labor lens; XP's sustainable pace; bus-factor
as a real metric). Code-side, the levers are already Praxion machinery:
characterization tests before touching untested code (Feathers: "legacy code
is code without tests"), the tech-debt ledger as *debt visibility* in
Cunningham's original sense, and the boy-scout rule **bounded by Stay
Surgical** — improve within the files the change already touches; drive-by
refactors elsewhere are a separate change. Scope note: energy/carbon "green
software" is a distinct concern with orthogonal checks, deliberately excluded
from this dimension — the omission is a decision, not an oversight.

### Durability

Behavior a consumer can depend on. The canon's converged claim: durability is
an *active commitment*, not a design property — SQLite's proportional
aviation-grade testing of its core and its 2050 pledge, Knuth's asymptotic
version freeze, Torvalds' "we do not break userspace". Operational core:

- **Hyrum's Law governs**: with enough users, *every observable behavior* is
  someone's contract — error text, ordering, timing included. Minimize
  unintended observability; document what can't be hidden
- **A break in observable public behavior is a bug by default**; overriding
  that default takes an explicit deprecation path, not a judgment call mid-PR
- **Explicit rejection over silent tolerance** at boundaries (RFC 9413's
  supersession-in-part of Postel's principle — and the same stance as
  parse-don't-validate): silently coercing malformed input calcifies divergent
  behavior; reject with a contractual error
- **Proportionality**: SQLite-grade rigor for high-blast-radius cores only —
  uniform application is coverage theater

Conventions: `coding-style § Compatibility and Deprecation`; evolution
contracts in `data-structure-design`.

### Creativity

The reconciliation first, because it is the whole point: the
readability-over-cleverness norm targets **clever** code — exploiting language
or environment quirks — and that prohibition stands. **Insightful** code —
exploiting a documented property of the *problem domain* (Wayne's
distinction), or reframing the decomposition itself (Norvig's language-model /
error-model split) — is the creativity this dimension licenses, and done well
it *simplifies*. Knuth's Turing lecture and Dijkstra's elegance-as-functional
framing agree across five decades: art in programming is skill and ingenuity
producing objects of beauty, and elegance must earn itself in reduced
reasoning load, not aesthetic authority. Disciplines:

- Spend the novelty budget on genuinely novel problems; well-trodden shapes
  take the conventional solution
- Every insight documents its premise (comment, test, or ADR) — insight is
  fragile when its domain assumption silently changes
- An elegance claim names its concrete reduction: fewer states, fewer edge
  cases, smaller reasoning surface — or it is challenged
- The most beautiful code is sometimes none: ask whether a reframing deletes
  the need before writing the addition

Creativity lives at design time — the systems-architect's alternatives duty
and the Methodology's "is there a more elegant way?" prompt — and in review as
a *guard*: an unfamiliar-but-justified design is interrogated for its premise,
never flagged for nonconformity alone.

## Tensions Between Dimensions

| Tension | Resolution |
| --- | --- |
| Expressiveness vs Simplicity — a fluent/DSL surface can add builder indirection a deep module wouldn't | Judge by which actually lowers the *reader's* load; a notation that must be decoded lost the trade |
| Storytelling comments vs comment-minimalism | The test is information the code cannot carry: why, invariants, units, cross-file obligations pass; restatements fail |
| Durability's ratchet vs Sustainability's refactoring urge | Resolve by scope: the ratchet binds *public, consumed* surfaces; boy-scout improvement applies to internals behind a stable contract — know which side of the line the diff sits on |
| Purity vs IO-heavy glue | Carmack's continuum: move along it; don't wrap trivial effects in ceremony |
| Creativity vs convention | Clever (language tricks) stays banned; insightful (domain properties, reframing) is licensed with a documented premise |
| Full-word naming vs compact notation | General-purpose logic takes full words (empirically grounded); domain-standard short forms (`dx`, `i`) stand where the domain's own fluent readers expect them |

## Composition with the Pipeline

- **systems-architect** exercises Creativity at design time: genuine
  alternatives and problem reframing for load-bearing decisions (Phase 3)
- **implementation-planner** owns cross-file Storytelling: module layout as
  table of contents; commit-sized, narratively ordered steps
- **implementer** applies the dimensions while writing; the Self-Review
  checklist is the mechanical floor, this skill the judgment layer
- **verifier** inherits the dimension conventions through `coding-style`
  (its Phase 5 list derives from that rule) and runs
  [references/beauty-review-checklist.md](references/beauty-review-checklist.md)
  on milestone reviews; the creativity guard keeps unfamiliar-but-justified
  designs from being flagged as violations
- **`.ai-state/principles.yaml`** carries the dimensions as advisory
  principles in every managed project: `/onboard-project` seeds it from
  `claude/project-baseline/principles.yaml.tmpl` (never overwriting an
  existing one; the project owns and edits it), the planner threads matching
  principles into step acceptance criteria, and the verifier gates them in
  Phase 4.5. Praxion's own instance does the same. This is the mechanism that
  makes the dimensions an *active gate* — not just documentation — when the
  pipeline drives a managed project's research, design, and implementation
- **code-review skill** needs no change to see the dimensions: its Convention
  Check applies every `coding-style` section, so the new sections flow in

## Related Skills

- **[`software-design-principles`](../software-design-principles/SKILL.md)** --
  the coupling lens under Simplicity: deep modules and balanced coupling are
  the same discipline from two vocabularies
- **[`data-structure-design`](../data-structure-design/SKILL.md)** --
  Expressiveness and Durability at the type level: illegal states, evolution
  contracts, schemas as contracts
- **[`refactoring`](../refactoring/SKILL.md)** -- the reactive path back to
  beauty; its Four Pillars are these dimensions applied to drifted code
- **[`code-review`](../code-review/SKILL.md)** -- the review workflow these
  dimensions ride through; checklist here, workflow there
- **[`testing-strategy`](../testing-strategy/SKILL.md)** -- characterization
  tests (Sustainability) and property/fuzz harnesses (Durability)

## Resources

- [Clever vs Insightful Code (Hillel Wayne)](https://www.hillelwayne.com/post/cleverness/) -- the creativity reconciliation
- [Simple Made Easy (Hickey, 2011)](https://github.com/matthiasn/talk-transcripts/blob/master/Hickey_Rich/SimpleMadeEasy-mostly-text.md) -- simple vs easy, complecting
- [Writing system software: code comments (antirez)](https://antirez.com/news/124) -- the comment taxonomy
- [In-depth: Functional programming in C++ (Carmack, 2012)](https://www.gamedeveloper.com/programming/in-depth-functional-programming-in-c-) -- purity as a continuum
- [How SQLite Is Tested](https://sqlite.org/testing.html) + [Long Term Support](https://sqlite.org/lts.html) -- durability as active commitment
- [Hyrum's Law](https://www.hyrumslaw.com/) -- observable behavior is the contract
- [Computer Programming as an Art (Knuth, 1974)](https://www.cs.tufts.edu/~nr/cs257/archive/don-knuth/as-an-art.pdf) -- the art argument
- [The WyCash Portfolio Management System (Cunningham, 1992)](http://c2.com/doc/oopsla92.html) -- what technical debt originally meant

Full per-dimension canon with verified quotes, confidence labels, and exemplar
evidence: [references/dimension-canon.md](references/dimension-canon.md).
