---
paths:
  - "dashboard_app/**/*.ts"
  - "dashboard_app/**/*.tsx"
  - "streamlit_app/**/*.py"
  - "streamlit_app/**/*.toml"
  - "scripts/praxion-dashboard"
---

## Dashboard Conventions

Declarative constraints for the active dashboard runtime in `dashboard_app/`, the stable launcher contract in `scripts/praxion-dashboard`, and the legacy migration reference in `streamlit_app/`.

### 1. Filesystem Is The Source Of Truth

The dashboard MUST read live project artifacts at render/request time. It MUST NOT create a secondary persistent store, background sync cache, or shadow copy of `.ai-state/`, `.ai-work/`, `docs/`, or other approved project-root surfaces.

Rationale: the product contract is a read-only window over canonical project files. Duplicating that state creates drift and breaks Praxion's "filesystem is the source of truth" model.

### 2. Launcher Contract Stays Stable

Edits to `scripts/praxion-dashboard` MUST preserve these invariants unless an ADR explicitly changes them:

- `/dashboard` remains the user-facing entrypoint through `praxion-dashboard`
- `PRAXION_PROJECT_ROOT` remains the target-project selection contract
- `PRAXION_DASHBOARD_PORT` remains the override hook
- default ports remain deterministic per absolute project path in the 8501-9500 range
- the server binds to `127.0.0.1`
- runtime dependencies live under `~/.praxion-dashboard/`, not in the target project

Rationale: users should not need to relearn the dashboard contract because the internal runtime changed from Streamlit to Next.js.

### 3. Server-Only Filesystem Access

In `dashboard_app/`, filesystem reads MUST stay in server-only modules, server components, or route handlers. Client components MUST NOT import Node filesystem modules or server readers.

In the legacy `streamlit_app/` reference, `streamlit_app/data/` MUST remain pure: no rendering imports or global mutable state. The only permitted Streamlit symbol in that legacy data layer is `st.cache_data`.

Rationale: the active runtime depends on a clean server/client boundary, while the legacy runtime remains maintainable only if its data layer stays isolated from rendering concerns.

### 4. Narrow Live Refresh Only

Live refresh MUST be confined to in-flight workshop surfaces or similarly narrow status views. Full-dashboard polling, whole-route reload loops, or client refresh paths that invalidate unrelated pages are prohibited.

Rationale: most dashboard surfaces are read-mostly reference views. Broad polling adds noise, load, and visual instability without improving operator value.

### 5. Frontmatter Never Renders Raw

Markdown artifacts with YAML frontmatter MUST strip or parse the frontmatter before presentation. Raw `---` blocks and unparsed metadata MUST NOT appear in rendered dashboard surfaces.

Rationale: ADRs, sentinel reports, idea ledgers, and related artifacts carry machine-oriented metadata that is not part of the human-readable body.

### 6. Empty-State Degradation

Every dashboard surface MUST handle missing or unreadable source artifacts gracefully. Pages MUST NOT crash on absent files that are legitimately sparse or ephemeral; they degrade to an informative empty/error state.

Rationale: `.ai-work/` directories disappear after cleanup, `.ai-state/` grows incrementally, and freshly onboarded projects often start without the full artifact set.

### 7. Legacy Streamlit Modules Stay Import-Safe

Each module under `streamlit_app/pages/` MUST continue to export exactly one `render() -> None` callable and MUST NOT execute Streamlit calls at import time.

Rationale: `streamlit_app/` still serves as a migration reference. Keeping its modules import-safe preserves the option to diff behavior or retire it cleanly later.
