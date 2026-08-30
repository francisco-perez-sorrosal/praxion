# The Dimension Canon

Per-dimension practitioner canon behind the eight dimensions: verified quotes with confidence labels, exemplar projects with evidence, and the documented tensions. Quote-accuracy discipline: labels record what was verified at a primary source vs converged from secondaries — cite accordingly, and do not upgrade a paraphrase to a quote. Back to [SKILL.md](../SKILL.md).

## Storytelling

**Canon.**
- Knuth, "Literate Programming" (1984), verified: "Instead of imagining that our main task is to instruct a computer what to do, let us concentrate rather on explaining to human beings what we want a computer to do."
- The newspaper metaphor / stepdown rule (Clean Code, 2008): a file reads top-to-bottom like an article — headline names first, detail cascading as you descend.
- antirez, "Writing system software: code comments" (2018, primary-fetched): the nine-category comment taxonomy — Function, Design, Why, Teacher, Checklist, Guide (positive) / Trivial, Debt, Backup (questionable). Redis is his own exemplar: "basically every file you open will contain plenty of [guide comments]."
- Ousterhout (A Philosophy of Software Design): comments are design, not documentation — they carry rationale, invariants, and cross-module decisions code cannot express.
- Commit-as-narrative: git-scm style guidance and the Linux kernel's submitting-patches process independently converge on "each commit is one coherent, revertible step."

**Exemplars.** Redis (author's own claim + independent practitioner corroboration). SQLite — published policy of "succinct yet useful comments (no boilerplate), carefully chosen variable names," independently credited by an academic readability study (arXiv 2209.05052).

**Tensions.** Comment rot (narrative comments drift unless maintained); the stepdown read assumes mostly-linear call structure — event-driven and reactive systems have no single "top"; commit-story discipline is the first casualty of deadline pressure ("WIP", "fix", "final fix").

## Simplicity

**Canon.**
- Hickey, "Simple Made Easy" (2011, convergent independent transcripts): simple is objective — un-braided ("complecting" = braiding concerns together); easy is relative to familiarity. Choosing the familiar tool is not choosing the simple one.
- Ousterhout: complexity = "anything related to the structure of a software system that makes it hard to understand and modify"; symptoms — change amplification, cognitive load, unknown unknowns. Deep modules (small interface, real hidden implementation) vs shallow ones.
- Brooks, "No Silver Bullet" (1986, primary): essential vs accidental complexity — only the accidental kind is removable.
- Pike, "Simplicity is Complicated" (dotGo 2015, primary slides): simplicity is a deliberate design achievement — "the art of hiding complexity"; "the bigger the interface, the weaker the abstraction."
- "Simplicity is prerequisite for reliability" — **attribution contested** between Dijkstra (EWD498, 1975) and Hoare (1980 Turing lecture); cite the idea, not a clean single-author quote.
- Saint-Exupéry: the popular "nothing left to take away" one-liner is a **paraphrase** of the translated text ("perfection is finally attained not when there is no longer anything to add, but when there is no longer anything to take away…") — label it as such.
- Fowler, "Yagni" (2015, primary): "Yagni is not a justification for neglecting the health of your code base. Yagni requires (and enables) malleable code."

**Exemplars.** TigerBeetle — TIGER_STYLE.md (primary): "Simplicity is… not the first attempt but the hardest revision," explicitly in the lineage of NASA/JPL's Power of Ten safety rules (independent aerospace convergence). Go's standard library and language design (primary design-team sources + long-standing community consensus).

**Tensions.** Simple vs simplistic — dropping *essential* complexity produces wrong, not simple; YAGNI over-applied to non-malleable code inverts its own trade; a shallow "simplifying" abstraction is net-negative (interface ≈ implementation).

## Clarity of Intent

**Canon.**
- Beck, Smalltalk Best Practice Patterns (1996, primary excerpts): Intention-Revealing Selector — the name communicates what the caller gets, not how it is done.
- Fowler et al., Refactoring (1999): "Any fool can write code that a computer can understand. Good programmers write code that humans can understand." (Text high-confidence; the commonly cited page number is aggregator-sourced.)
- Ousterhout's critique of "good code is self-documenting": some information — rationale, preconditions, invariants — cannot be expressed in code at all.
- Evans, DDD (2003): ubiquitous language reaches *into the source* — a domain expert should recognize the vocabulary in class and method names.
- Empirical: Hofmeister, Siegmund & Holt (EMSE 2019, primary PDF; 72 professional developers): full-word identifiers gave ~19% faster defect location than letters/abbreviations; converges with the earlier Lawrie et al. comprehension studies.

**Exemplars.** SQLite again — "carefully chosen variable names" as stated policy plus independent academic credit.

**Tensions.** The self-documenting-code slogan vs comments-are-design is a live disagreement between real schools — hold the test at "does the comment say what the code cannot"; the full-word finding is scoped to general-purpose code — established domain notation (`i`, `dx`, `dt`) is its own intent-carrying convention.

## Expressiveness

**Canon.**
- Iverson, "Notation as a Tool of Thought" (1979 Turing lecture): notation shapes reasoning — verified at the opening Boole framing ("language is an instrument of human reason…"); further direct quoting needs a re-fetch of the CACM printing (partial-extraction flag).
- Matz on least surprise (Artima interview, primary-adjacent): "The principle of least surprise means principle of least *my* surprise" — POLS is explicitly not a universal law; calibrate to the actual reading audience.
- Fowler/Evans, "Fluent Interface" (2005, primary): DSL-feel API via chaining — powerful and self-limiting (the "finishing problem" of signalling chain completion).
- The Iverson tension is internal to his own tradition: APL's density aids the fluent expert and walls out everyone else — expressiveness and terseness are different axes.

**Exemplars.** None met the two-independent-source bar that Redis/SQLite/TigerBeetle met for their dimensions — Rails, Elm, and RSpec circulate as candidates on community consensus only. An honest gap, recorded rather than force-fit.

**Tensions.** Fluent surfaces can trade away deep-module simplicity for call-site readability; density that must be decoded is cleverness wearing expressiveness' clothes.

## Purity

**Canon.**
- Carmack, "Functional Programming in C++" (2012, primary-fetched, quotes verified): "A pure function only looks at the parameters passed in to it, and all it does is return one or more computed values based on the parameters." Root cause argument: "A large fraction of the flaws in software development are due to programmers not fully understanding all the possible states their code may execute in." And the pragmatics: "It doesn't even have to be all-or-nothing… There is a continuum of value in how pure a function is." Technique: gather → compute (pure) → use.
- Bernhardt, "Boundaries" (2012): values as component boundaries; **"Functional Core, Imperative Shell" is consistently attributed but not primary-verified** (paywalled screencast) — cite as attributed, not verbatim.
- Cockburn, "Hexagonal Architecture" (2005, primary-fetched): "code pertaining to the inside part should not leak into the outside part" — purity's discipline at the module boundary; the core stays "blissfully ignorant of the nature of the input device."

Three independent traditions (game-engine C++, dynamic-language testing, enterprise architecture) converge on the same structural move: segregate pure computation from effectful edges.

**Exemplars.** Elm (language-level purity; the production zero-runtime-exception reports are conference-sourced, medium confidence). Carmack's own account of moving id Software code *toward* purity — a continuum practiced, not an absolute achieved.

**Tensions.** Purity ceremony on IO-heavy glue costs more than it buys; allocation overhead matters on measured hot paths; **purity theater** — a signature hiding an ambient input (singleton "Clock", global config, wall time) — is the named anti-pattern to catch in review.

## Sustainability

**Canon.**
- Cunningham, OOPSLA 1992 (primary-fetched): "Shipping first time code is like going into debt. A little debt speeds development so long as it is paid back promptly with a rewrite… Every minute spent on not-quite-right code counts as interest on that debt." His 2009 clarification (high-confidence convergent secondaries): "I'm never in favor of writing code poorly, but I am in favor of writing code to reflect your current understanding of a problem" — **debt = incomplete understanding made visible, never sanctioned sloppiness**. The popular usage is a drift from the coiner's intent.
- Feathers (2004): "legacy code is simply code without tests" — sustainability is testability; characterization tests convert legacy to covered.
- Boy-scout rule (popularized by Clean Code from scouting folklore): leave code better on every touch — in Praxion, **bounded by Stay Surgical** to the files the change already touches.
- ISO/IEC 25010 maintainability: modularity, reusability, analysability, modifiability, testability — the standards-body vocabulary.
- Eghbal, "Roads and Bridges" (2016): codebase sustainability is inseparable from *maintainer* sustainability — bus-factor and unfunded-labor are engineering metrics, not HR trivia. XP's sustainable pace is the same claim at team scale.

**Exemplars.** PostgreSQL (30+ years, convergent trade-press evidence — medium confidence); the Linux kernel (contributor-trust discipline; overlaps Durability).

**Scope decision.** "Green software" (energy/carbon) is a *different* sustainability with orthogonal checks — excluded from this dimension by decision, not oversight.

**Tensions.** Boy-scouting vs Stay Surgical (resolved: bounded, in-diff cleanup only); over-modularization chases the metric into navigation cost; a durable-looking project can be one burned-out maintainer from stalling.

## Durability

**Canon.**
- SQLite (primary-fetched, both pages): 100% branch and MC/DC coverage on the core under TH3 (the DO-178B-inspired aviation criterion; achieved 2009), ~590× more test code than production code, ~500M fuzz cases daily — and the pledge: "The intent of the developers is to support SQLite through the year 2050," with file-format and API backward compatibility framed as making today's data "as easily accessible to your grandchildren as it is to you."
- Knuth (primary-fetched): TeX's version converges to π ("At that point they will be completely error-free by definition") and the doubling hex-dollar bug bounty — a durability commitment encoded in the version scheme itself.
- Torvalds (convergent secondaries on the 2012 LKML thread): "WE DO NOT BREAK USERSPACE!" — a userspace-visible break is a kernel bug by definition, regardless of what userspace "should" have relied on.
- Hyrum's Law (primary-fetched, exact): "With a sufficient number of users of an API, it does not matter what you promise in the contract: all observable behaviors of your system will be depended on by somebody."
- RFC 9413, "Maintaining Robust Protocols" (IETF, 2023): the modern critique of Postel's robustness principle — liberal acceptance of malformed input erodes interoperability as divergent tolerances calcify; durable systems prefer explicit validation and active contract maintenance. **This is a genuine documented disagreement within the durability tradition**; Praxion takes the RFC 9413 side (it is the same stance as parse-don't-validate), while naming Postel's principle as superseded-in-part rather than omitting it.

Four independent traditions (industry practice, academic typesetting, kernel culture, protocol standards) converge: durability is an active, ongoing commitment — never a one-time design property.

**Exemplars.** SQLite (strongest-evidenced in this canon), TeX/METAFONT, the Linux kernel.

**Tensions.** The compatibility ratchet vs the refactoring urge — resolved by the public/internal line (the ratchet binds consumed surfaces; improvement flows freely behind them); coverage-as-theater when SQLite-grade rigor is applied outside high-blast-radius cores; Lindy-effect optimism ("survived N years ⇒ N more") ignores present maintainer health.

## Creativity

**Canon.**
- Knuth, "Computer Programming as an Art" (1974 Turing lecture, cross-verified mirrors): "computer programming is an art, because it applies accumulated knowledge to the world, because it requires skill and ingenuity, and especially because it produces objects of beauty."
- Dijkstra, EWD648 (the higher-confidence wording — prefer it over the shorter aggregator paraphrase): "How do we convince people that in programming simplicity and clarity — in short: what mathematicians call 'elegance' — are not a dispensable luxury, but a crucial matter that decides between success and failure?" Elegance is functional, never decorative.
- Norvig, "How to Write a Spelling Corrector" (2007, primary-fetched): the creativity is the *decomposition* — an explicit language model and error model, "easier to separate the two out and deal with them explicitly" — with a documented, deliberate accuracy-for-clarity trade.
- Wayne, "Clever vs Insightful Code" (primary-fetched, the load-bearing reconciliation): **clever** exploits language/environment quirks (Duff's Device); **insightful** exploits documented domain properties (bucket-sort by birth date because ages are bounded). Insight simplifies; its named costs — fragility when the domain assumption changes, poor generalization, tacit-knowledge transfer — are exactly why the premise must be documented.
- Graham, "Hackers and Painters" (2003): essayist-tier framing (makers, not process-followers) — motivating, never evidentiary.

Four traditions across five decades converge on the specific point: creativity earns its place at the level of problem framing and domain insight, and becomes a liability as implementation-trick exhibition.

**Exemplars — and a calibrated counter-example.** Norvig's ~21-line corrector is the aspirational pole: creative decomposition, documented trade-offs. The Quake III fast inverse square root (`0x5f3759df` — its own source says "evil floating point bit level hacking", provenance disputed to this day) is the *clever* pole: folklore-celebrated precisely because it is an undocumented trick — the kind production review rightly rejects. Kernighan's regex matcher (Beautiful Code, 2007) circulates as a third exemplar; content unverified here, cite with care.

**Tensions.** Creativity vs convention resolves by level (design insight licensed, line tricks banned); insight vs sustainability (an unteachable insight is a bus-factor risk); celebrated-as-folklore vs fit-for-reviewed-production are different claims about the same code.
