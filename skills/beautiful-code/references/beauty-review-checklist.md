# Beauty Review Checklist

Per-dimension reviewer checks for milestone reviews and standalone code-review passes. Mechanical conventions (sizes, nesting, naming, formatting) are already the verifier's Phase 5 floor — this checklist carries the judgment layer above it. Findings anchor to the named `rules/swe/coding-style.md` section per dimension, or to `CLAUDE.md§Structural Beauty` for design-level findings. Back to [SKILL.md](../SKILL.md).

## Storytelling — anchor: `coding-style § Reading Order and Narrative`

- [ ] Reading only the top-level names/signatures of each changed file describes what it does (newspaper test); detail decreases top-down or the deviation is deliberate and visible
- [ ] Every comment in the diff says something the code cannot (why, invariant, unit, cross-file obligation) — no restatements, no commented-out corpses
- [ ] Cross-file obligations introduced by the change carry a checklist comment at the definition site ("if you change X, update Y")
- [ ] The PR's commit sequence reads as named, revertible steps — not "WIP / fix / more fixes"

Golden bad-case: a 400-line file whose helpers are defined above the entry point in dependency order, forcing bottom-up reading; its three comments all restate the next line (`# increment counter`).

## Simplicity — anchors: behavioral contract `Simplicity First`; `coding-style` size/nesting gates

- [ ] No new shallow module: each added interface hides real implementation (deep-module test), not a pass-through
- [ ] No concern-braiding: no single function mixing state management, I/O, business validation, and notification (decomplecting check)
- [ ] Every parameter, config flag, and abstraction serves a requirement that exists today (YAGNI gate); the subtraction test was attempted
- [ ] The "simple" solution didn't drop essential complexity — no silently narrowed requirement

Golden bad-case: a `DataProviderFactoryInterface` with one implementation, added "for testability," whose interface mirrors the implementation method-for-method.

## Clarity of intent — anchor: `coding-style § Naming`

- [ ] Behavior and side effects are predictable from each new/changed signature alone (intention-revealing test); mutators and queries are distinguishable by name
- [ ] Identifiers are full words or established domain notation — no ad hoc truncations
- [ ] Names use the domain's own vocabulary, not invented synonyms for existing terms

Golden bad-case: `def proc_usr_d(d, flg)` — behavior unknowable without reading the body; `flg` flips between two unrelated modes.

## Expressiveness — anchor: `coding-style § Expressive Constructs`

- [ ] The chosen construct lets a reader reason about the problem without first decoding the notation; density that requires decoding is flagged
- [ ] Declarative forms replaced accumulator boilerplate where they clarify — and were NOT used where ordering/effects/error flow genuinely need the explicit loop
- [ ] Code follows the language's own idioms; imported foreign idioms are justified
- [ ] Surprise is calibrated to the actual reading audience, not the author's habits

Golden bad-case: a triple-nested comprehension with two inline conditionals replacing a 6-line loop — fewer lines, strictly more simulation for the reader.

## Purity — anchor: `coding-style § Side-Effect Discipline`

- [ ] New logic separates gather (inputs at the edge) → compute (pure) → use (effects at the end); effects are not buried mid-call-stack
- [ ] Signature completeness: every value affecting a function's output is visible in its parameters — no hidden globals, singletons, ambient config, or wall-clock reads (purity-theater check)
- [ ] Core logic is testable without mocks; a mock-requiring function is either essential I/O or flagged for effect-extraction
- [ ] The pure/effectful line corresponds to a real file/module boundary, not an informal convention

Golden bad-case: `calculate_invoice(order)` that internally reads `datetime.now()`, a global `TAX_TABLE`, and logs to disk — pure-looking signature, three ambient inputs, untestable without patching.

## Sustainability — anchors: Incremental Evolution; tech-debt ledger conventions

- [ ] Changes to untested code are preceded by characterization tests (Feathers gate)
- [ ] Known-incomplete understanding is visible: ledger row, ADR, or owned TODO with a reason — never silent
- [ ] Boy-scout improvements stay inside the files the change already touches (Stay Surgical bound); drive-by refactors are split out
- [ ] One behavior change did not fan out across many unrelated modules (change-amplification smell)

Golden bad-case: a bug fix in an untested 800-line module with no characterization test, plus opportunistic renames in four unrelated files "while I was in there."

## Durability — anchor: `coding-style § Compatibility and Deprecation`

- [ ] The diff of *observable* public behavior — including error text, ordering, defaults — is empty, or every change rides an explicit deprecation/version path (Hyrum check)
- [ ] A consumer test broken by the change is treated as a bug in the change by default; overrides carry written justification
- [ ] Boundaries reject malformed input with contractual errors — no new silent coercion or swallow-and-continue tolerance
- [ ] Persisted/wire formats changed additively or with a version tag and migration path
- [ ] Durability rigor is proportional: high-blast-radius core logic gains property/fuzz coverage; glue does not gain coverage theater

Golden bad-case: "harmless" reformatting of an API error message that three downstream consumers parse by regex; no version note, no changelog entry.

## Creativity — anchor: `CLAUDE.md§Structural Beauty` (design-level; no line-level convention)

- [ ] Non-obvious solutions are classified: language/environment trick (clever — reject in production paths) vs documented domain property or reframed decomposition (insightful — admissible)
- [ ] Every admitted insight states its premise in a comment, test, or ADR; a premise a future requirement change could silently invalidate is test-guarded
- [ ] "More elegant" claims name their concrete reduction (fewer states, edge cases, smaller reasoning surface) — elegance is functional, never authority
- [ ] Novelty is spent on genuinely novel problems; familiar shapes take conventional solutions
- [ ] REVIEWER GUARD: an unfamiliar-but-justified design is interrogated for its premise — never flagged for nonconformity alone

Golden bad-case (clever pole): a bit-twiddling hash trick with a magic constant and no derivation replacing a clear stdlib call in a non-hot path. Golden bad-case (guard violation): a review finding that reads "this isn't how we usually structure services" against a design whose ADR documents the premise and its measured payoff.

## Verdict Guide

| Finding count | Verdict |
|---------------|---------|
| 0 FAIL, 0 WARN | PASS |
| 0 FAIL, 1–3 WARN | PASS WITH FINDINGS |
| 0 FAIL, 4+ WARN | PASS WITH FINDINGS (significant) |
| 1+ FAIL | FAIL |

FAIL items: silent observable-behavior break on a consumed surface; purity theater on core logic (hidden ambient inputs); an undocumented clever-pole trick in a production path; a dropped essential requirement masquerading as simplification.

WARN items: comment restatements; shallow modules; unbounded boy-scouting; decode-heavy density; missing insight premises; coverage theater.
