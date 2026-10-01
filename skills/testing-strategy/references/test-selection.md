# Test Selection — the Derived Contract

The procedural contract behind Principle 4 ("selection is derived from the code, never hand-kept, and unmapped widens"). Back to [SKILL.md](../SKILL.md).

This file replaces the hand-kept test-topology protocol. There is no `.ai-state/TEST_TOPOLOGY.md` to author or refresh: the resolver derives a test selection directly from the change set, on every invocation, and widens to the full suite whenever it cannot prove a change is covered.

## The Four Edge Sources

The resolver builds one dependency graph per pocket from four sources, then unions all four (not first-match — every source contributes; the order below governs only which source a test's `via` attribution names when more than one connects it):

1. **Layout.** `dir/test_foo.py` / `dir/foo_test.py` depend on `dir/foo.py`. Mirrored layout matches by basename with the longest common directory suffix; ties select all matches. A `conftest.py` (or equivalent) is depended on by every test under its directory.
2. **Import.** Static imports (`ast.Import`/`ast.ImportFrom`, relative imports, `importlib.import_module("<literal>")` for Python). Resolution tries, in order: a sibling file; the dotted path from the pocket root and any configured import root; a flat stem match across the pocket (ambiguous stems connect to all matches).
3. **Path-literal.** String constants anywhere in a pocket module (not just tests), each in exactly one class:
   - *path suffix* — contains `/`, no wildcard: matches the end of a path (the file or one of its directories);
   - *path glob* — contains `/` and a wildcard (`*`, `?`, `[`): matches as a glob;
   - *exact basename* — no `/`, no wildcard: matches only that exact basename, at any depth;
   - *basename pattern* — no `/`, a wildcard, and at least one letter or digit outside the wildcards (`*.md`, `report*`): matches the basename of a **changed** path at any depth and selects only holders that are themselves test modules. Nothing propagates from a holder, and a production module holding one selects nothing through it: a script that globs every Markdown file names no file in particular, and fanning out through such scripts would select most of the suite for any documentation change;
   - *ignored* — empty, `.`, or a wildcard literal with no letter or digit outside its wildcards (`*`, `**`, `?`, `.*`, `*.*`, `[a-z]*`): a separator, a repetition count or a regular expression, never a claim about which files a module reads.

   **Data files narrow, code widens.** A changed file reached only by a basename pattern always selects the test modules that hold it, but it counts as accounted for (no `unmapped-path`) only when it is a data file. A source file of any pocket ecosystem — Python `.py`; JavaScript and TypeScript `.js .jsx .mjs .cjs .ts .tsx .mts .cts .vue .svelte`; Rust `.rs`; Go `.go`; JVM `.java .kt` — reached only by a pattern still widens, and its readers run within that full run: a pattern is a guess about what a module reads, never a substitute for the import and layout tracing that code relies on.
4. **Declared.** Non-code dependencies the first three sources cannot see — see [The Declared List](#the-declared-list-testsdeclared-depstoml) below.

A changed test file always selects itself (`via: self`). Selection is reverse reachability: which test files reach a changed path through any of the four edges.

**Serial threshold.** When the estimated test count (occurrences of `def test_`/`async def test_`) in a Python pocket's selection is at or below the serial threshold (`SERIAL_BELOW_TESTS`, initially 20), the emitted invocation adds `-n 0` — skipping parallel-worker start-up for a run too small to benefit from it. This only applies when the pocket's own config already enables xdist.

## Widening

Unmapped is not silently narrow — a changed path that reaches no test, is not a test itself, and is not exempted as non-source widens every pocket to its full suite. The resolver reports each widen with a machine-readable reason:

| Reason | Trigger |
|---|---|
| `unmapped-path` | A changed path connects to no test, is not itself a test, and is not non-source; or a source file only a basename pattern reaches; or, in a vitest or jest pocket, a changed file that is not a module or a module that no longer exists |
| `selector-changed` | A resolver source file changed (the selector cannot vouch for its own edits) |
| `declared-deps-changed` | `tests/declared-deps.toml` changed |
| `declared-deps-invalid` | The declared-deps file fails to parse or violates an invariant (see below) |
| `pocket-config-changed` | A pocket's runner config or lockfile changed (pocket-scoped, not repo-wide) |
| `no-adapter` | The pocket's ecosystem has no native adapter |
| `tool-unavailable` | The ecosystem's own tool is not on `PATH` |
| `full-requested` | `--full` was passed explicitly |

A repo-level widen (`selector-changed`, `declared-deps-*`, and `unmapped-path` for a path a Python pocket owns) forces every pocket to `full`. A pocket-level widen (`pocket-config-changed`, `no-adapter`, `tool-unavailable`, and `unmapped-path` for a path outside a native pocket's module graph, crate or package, including a vitest or jest module that no longer exists: `related` and `--findRelatedTests` walk outward from a file that must be there, and report no tests with exit 0 when it is gone) forces only that pocket. The other native adapters are unchanged and stay narrow: Maven and Gradle map a path to the module or project owning its directory, so a deleted path still selects its owner; nx and Pants receive the path as given and turbo works from the git diff, and how those three tools treat a deleted path is not yet verified.

Non-source paths (git-ignored, root narrative files, or an explicit `[[inert]]` entry) are exempted from ever triggering `unmapped-path` — each exemption is reported in `ignored_non_source`, auditable rather than an opaque allowlist.

## The Declared List (`tests/declared-deps.toml`)

The only hand-authored artifact left in this protocol — and only for edges the code genuinely cannot reveal (a fixture file no source module names, a generated artifact a test reads by convention).

```toml
# Non-code test dependencies the resolver cannot derive from layout, imports or path literals.
# Any change to this file runs the full suite.
schema = 1

[[dep]]
paths = [".ai-state/decisions/*.md"]              # repo-relative globs (segment-aware; ** crosses dirs)
tests = ["tests/test_adr_frontmatter_parseable.py"] # repo-relative test files/globs
why   = "parses every ADR's frontmatter"

[[inert]]
paths = ["docs/independent-analysis/**"]
why   = "frozen historical analysis; no test reads it"
```

If the file is absent, the resolver reads it as an empty list — no entries required. Every entry is validated at resolve time (never cached) by a smart constructor with six invariants: `schema == 1`; only `schema`/`dep`/`inert` keys at top level; `paths` and `tests` are non-empty lists of non-empty, repo-relative strings (no leading `/`, no `..` segment); `why` is non-empty; every `tests` glob matches at least one tracked test file; a path matched by both a `dep` and an `inert` entry resolves to `dep` (the over-select direction). A violation never drops the entry silently — it widens with `declared-deps-invalid` and names the violation.

## Ecosystem Dispatch

Python is derived (the four edges above, read with stdlib `ast`). Every other ecosystem is dispatched to its own native tool — Praxion derives only where no native tool exists:

| Ecosystem | Tool | Invocation |
|---|---|---|
| Python | (derived) | The four-edge graph above |
| TypeScript/JS (vitest) | vitest | `related` |
| TypeScript/JS (jest) | jest | `--findRelatedTests` |
| Rust | cargo | changed crates plus dependents (`cargo metadata`) |
| Go | go | `go list` packages plus dependents |
| JVM (Maven) | maven | `-pl … -amd` |
| JVM (Gradle) | gradle | project `buildDependents` |
| nx / turbo / pants | (native) | `affected` |
| Bazel | — | no adapter; always widens (use the `rdeps` recipe by hand) |

A missing tool or a missing adapter widens only that pocket (`tool-unavailable` / `no-adapter`) — it never silently skips the pocket.

## Input Modes and Output Contract

Exactly one input mode per invocation: `--changed PATH…` (explicit paths), `--changed-from REF` (`REF...HEAD`, plus uncommitted changes to tracked files, plus untracked files), `--full` (every pocket), or no arguments (working-tree diff against `HEAD` plus untracked files). `--json` emits schema-2 JSON; without it, the resolver prints shell-runnable, runner-prefixed commands on stdout with context on stderr — the same entry point serves agents and humans (`resolve_test_scope.py | sh -e`). A rename counts as both its old and its new path, and a deleted file is never emitted as a test target (a deleted source still selects its surviving tests, except in a vitest or jest pocket, where a deleted module widens that pocket).

```json
{
  "schema": 2,
  "changed": {"source": "working-tree | git-diff:<ref>...HEAD | explicit | full-requested", "paths": ["..."]},
  "decision": "selected | widened | nothing-to-run",
  "widen": [{"reason": "unmapped-path | selector-changed | declared-deps-changed | declared-deps-invalid | pocket-config-changed | no-adapter | tool-unavailable | full-requested",
             "paths": ["..."], "detail": "..."}],
  "ignored_non_source": [{"path": "...", "rule": "git-ignored | root-narrative | declared-inert"}],
  "pockets": [{
    "root": ".", "ecosystem": "python | typescript | rust | go | jvm | monorepo",
    "adapter": "python-derived | vitest | jest | cargo | go | maven | gradle | nx | turbo | pants | none",
    "selection": "tests | native | full | nothing",
    "tests": [{"path": "scripts/test_foo.py", "via": "self | layout | import | path-literal | declared", "because": "scripts/foo.py"}],
    "invocations": [{"cwd": ".", "argv": ["uv", "run", "pytest", "-n", "0", "scripts/test_foo.py"]}]
  }]
}
```

`argv` is runner-prefixed per pocket (`uv run` / `pixi run` / `poetry run` / `pnpm exec` / `yarn` / `npx` / `cargo` / `go`, etc.); `cwd` is relative to the repo root. Exit codes: `0` resolved (including widened); `2` usage or internal error — callers treat `2` as "run the full suite."

## `Tests:` Is Override-Only

A plan step's `Tests:` field, when present, overrides the derived selection: `Tests: full — <reason>` or `Tests: <path> [<path> …] — <reason>`. Absence means derive. The canonical statement of this schema lives in [`document-templates.md`](../../software-planning/references/document-templates.md) — this is a pointer, not a restatement.

## The Selection Audit

`audit_tests.py` closes the loop between "what did selection run" and "what should have run": given a junit file with failures and the change set that produced it, it classifies each failure as `selected`, `widened`, `missed`, or `unattributable`, names a `suggested_edge` for every `missed`, and exits `1` when anything is missed. With a rerun junit file, a failure that flips to pass is classified `flaky` instead of `real`. `--slow N` reports the top-N slowest tests. This is the mechanism that lets selection stay derived rather than hand-audited — a miss is a concrete, closeable finding, not a vague worry about coverage.

## Selection-Size Baseline

Measured 2026-09-29 on Praxion itself: the resolver at `90cbdc2a` run over the change sets of the 50 preceding non-merge commits, root pocket only. The corpus is 267 test files. The dependency graph is today's, not the graph as it stood at each commit.

| Measure | Value |
|---|---|
| Widened to the full suite | 9 of 50 commits (18%) |
| Median / p90 selection, narrow runs only (41) | 96 / 197 files (36% / 74%) |
| Median / p90 selection, widened runs counted as 267 | 120 / 267 files (45% / 100%) |
| Edge attribution across narrow selections | path-literal 63%, declared 33%, import 4% |

The refresh plan's risk trigger ("restrict production path-literal edges if the median selection exceeds 25% of the corpus") **fires**: the narrow median is 36%. Removing path-literal edges would drop at most 44 files from the median narrow selection, roughly 19% of the corpus. That is an upper bound, because `via` names only the first source that connects a test, so some of those files are also reached through a declared edge. Re-measure with the same method before and after any change to the edge sources.

**Re-measured 2026-09-30, before and after basename patterns and the vitest/jest deleted-module widen.** Same method and the same 50 change sets, with both resolvers run over one tree (a 270-file corpus: the tree had gained outer-loop test files since the first measurement).

| Measure | Before | After |
|---|---|---|
| Widened to the full suite | 8 of 50 | 8 of 50 |
| Median / p90, narrow runs only (42) | 98.5 / 199 files (36% / 74%) | 101 / 201 files (37% / 74%) |
| Median / p90, widened runs counted as 270 | 122 / 270 (45% / 100%) | 124 / 270 (46% / 100%) |
| Edge attribution | path-literal 64%, declared 32%, import 4% | path-literal 65%, declared 30%, import 4% |

A first design let a basename pattern select every test reaching its holder. Measured the same way, it moved the narrow median to 82%, because dozens of production scripts hold `*.md`; that is why a pattern selects only holders that are test modules.

## The Five Loops — Operational Copy

The doctrine copy of this table lives in [SKILL.md § The Five Loops](../SKILL.md#the-five-loops). This copy adds the exact command per loop.

| Loop | Trigger | What runs | Command |
|---|---|---|---|
| Inner | Every implementer step and `/test` | Derived selection of the working-tree change | `resolve_test_scope.py --json` → run `invocations` (Praxion self-host: `python3 scripts/resolve_test_scope.py`) |
| Phase checkpoint | A step the planner marks as closing a phase | Selection over the union of changes since the pipeline base | `resolve_test_scope.py --changed-from $(git merge-base HEAD <default-branch>)` |
| Integration checkpoint | The pipeline's final step | Full suite; on failure, the audit against the pipeline diff, misses closed in-pipeline | Full-suite command; `audit_tests.py --junit … --changed-from <base>` |
| Pre-merge CI | Push / PR | Full parallel suite, coverage ratchet, junit artifact | The project's CI test workflow |
| Scheduled | Weekly cron + dispatch | Full suite, one rerun of failures (classify), `large` tests per pocket, audit of real failures against the diff since the last green run, slow top-20 | The project's scheduled test workflow → `audit_tests.py --junit run1.xml --rerun run2.xml --changed-from <last-green-sha> --slow 20` |

Resolver flow: changed set → non-source predicate and declared `inert` → global widen triggers → partition by pocket (longest-prefix root) → per-pocket adapter → per-pocket selection → payload.
