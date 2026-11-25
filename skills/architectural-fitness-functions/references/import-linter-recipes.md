# Import-Linter Recipes

Common contract patterns for `fitness/import-linter.cfg`. Each recipe includes a
minimal INI stanza with field explanations and a citation example.

Back to [`../SKILL.md`](../SKILL.md).

---

## Recipe 1: Forbidden Imports (Blacklist)

Use when a module must **never** import from another module, regardless of layering.

```ini
[importlinter:contract:no-scripts-import-agents]
name         = scripts must not import from agents
type         = forbidden
source_modules =
    scripts
forbidden_modules =
    agents
broken_contract_guidance =
    CLAUDE.md§Structural Beauty — scripts are standalone utilities; importing
    agent definitions would create a circular knowledge dependency.
```

**Fields:**

| Field | Purpose |
|-------|---------|
| `name` | Human-readable label shown in violation reports |
| `type` | Always `forbidden` for this recipe |
| `source_modules` | One module per line; these are the importers being restricted |
| `forbidden_modules` | One module per line; these must not appear in source_modules' import graph |
| `broken_contract_guidance` | Required citation (`dec-\d{3,}` or `CLAUDE.md§...`) + rationale; printed under a broken contract |
| `ignore_imports` | Optional; one `a.b -> c.d` per line for unavoidable transitive imports |

Use `ignore_imports` sparingly — each entry is a known exception that should be
accompanied by a `# fitness-waiver:` comment at the import site.

---

## Recipe 2: Layered Architecture

Use when the codebase has explicit layers and lower layers must not reach up into
higher ones (e.g., domain must not import from presentation).

```ini
[importlinter:contract:layer-order]
name         = enforce layer ordering
type         = layers
layers =
    skills
    agents
    rules
containers   = .
broken_contract_guidance =
    CLAUDE.md§Structural Beauty — lower layers (skills) must not import
    from higher layers (agents, rules); keep knowledge flow one-way.
```

**Fields:**

| Field | Purpose |
|-------|---------|
| `type` | Always `layers` for this recipe |
| `layers` | Ordered list, **highest layer first**; import is only allowed downward |
| `containers` | Package that contains the listed layers; `.` means the project root |
| `allow_indirect_imports` | Optional boolean; set `true` if transitive cross-layer imports via allowed layers are acceptable |

Tip: start with coarse layers (3-4 entries) and refine as the architecture matures.
Overly fine-grained layer lists become brittle as modules are renamed or split.

---

## Recipe 3: Independence

Use when two sibling modules must not import each other (orthogonal subsystems that
share no code path).

```ini
[importlinter:contract:skills-agents-independence]
name         = skills and agents are independent
type         = independence
modules =
    skills
    agents
broken_contract_guidance =
    CLAUDE.md§Structural Beauty — skills and agents are orthogonal
    subsystems; cross-imports indicate accidental coupling.
```

**Fields:**

| Field | Purpose |
|-------|---------|
| `type` | Always `independence` for this recipe |
| `modules` | Two or more modules that must not import from each other (any direction) |

Independence contracts are symmetric — they catch both `skills → agents` and
`agents → skills` violations with a single contract.

---

## Recipe 4: Choosing Granularity

**Prefer many small contracts over one large contract.**

Each contract cites a single ADR or principle and reports violations with that
citation visible. When multiple unrelated invariants are combined into one contract,
a violation report loses traceability — the reader cannot tell which principle was
breached.

Good:
```ini
[importlinter:contract:no-scripts-import-agents]
...
broken_contract_guidance = CLAUDE.md§Structural Beauty — ...

[importlinter:contract:no-agents-import-fitness]
...
broken_contract_guidance = CLAUDE.md§Root Causes Over Workarounds — ...
```

Avoid:
```ini
[importlinter:contract:everything]
# no clear citation, violation report is ambiguous
```

One contract per invariant also makes it easy to add `ignore_imports` narrowly to
a single contract without accidentally relaxing a different invariant.

---

## Recipe 5: Common Pitfalls

**Star imports defeat static analysis.** `from module import *` is opaque to
import-linter's graph builder. If a contract is known to be unreliable in the
presence of star imports, add a note in the `broken_contract_guidance=` field:
```ini
broken_contract_guidance = dec-NNN — Note: reliability limited if star imports exist in source_modules.
```

**An unknown option fails the run.** Since 2.16 import-linter rejects any option no
field of the contract recognizes (`description: Unrecognized option.`), and earlier
versions ignored it silently. A config written for an older version that carries its
citation in `description =` breaks on the first upgrade: rename the key to
`broken_contract_guidance`, which 2.14+ prints under a broken contract and older
versions ignore.

**Dynamic imports via `importlib` cannot be statically traced.** Code that uses
`importlib.import_module("some.module")` or `__import__()` is invisible to
import-linter. Use `# fitness-waiver: dec-NNN reason` at the dynamic import site
and document the exception. Do not create a blanket `ignore_imports` entry for the
whole module — that would silently permit static imports too.

**Test code is part of the import graph by default.** If your source modules are
the root packages (e.g., `scripts`, `agents`), import-linter traces imports from
test files that import those packages. To exclude tests from the analysis, list
explicit module roots in `[importlinter]` `source_modules` (not the test directories)
and ensure tests are not within the source package tree.

**`[importlinter]` root_packages must match the actual package structure.** If the
project uses a `src/` layout, set `root_packages = src.mypackage` (or configure
`source_paths = src`). Mismatched root packages silently produce zero-finding runs
that look like clean passes.
