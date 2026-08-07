/**
 * REQ<->architectural-element traceability — scaffolding fragment
 *
 * HOW TO USE: copy the `metadata { req_ids = ... }` block below onto the LikeC4
 * elements in your own `.c4` model that implement behavioral requirements, then
 * add the matching `architectural_elements:` key to the archived SPEC's YAML
 * frontmatter (second half of this file). This is a *fragment*, not a standalone
 * model: it does not compile on its own and nothing installs it. It exists so the
 * bidirectional convention has a copy-paste starting point rather than only a
 * prose description.
 *
 * The convention is bidirectional by design — each side answers a question the
 * other cannot:
 *   element -> REQ    "which requirements does this component implement?"
 *   SPEC    -> element "which components implement this spec?"
 * Populating one side only leaves the sentinel's AC12 orphan check able to see
 * drift in a single direction, which is the shape it exists to rule out.
 *
 * Canonical convention: the AaC/DaC guide's REQ<->Architectural-Element
 * Traceability section (`docs/aac-dac.md` in the Praxion source repo).
 */

model {

  // ── Element side ─────────────────────────────────────────────────────────
  // `req_ids` is a comma-separated list of REQ IDs drawn from the spec that
  // owns each requirement. Whitespace around commas is tolerated — readers
  // split on `,` and trim. Spell the IDs exactly as the SPEC spells them: the
  // orphan check matches by literal string, so `REQ-1` and `REQ-01` are two
  // different requirements as far as it is concerned.
  //
  // Elements with no behavioral requirement (layer containers, external
  // actors, document nodes) carry no `req_ids` and are not orphans — the check
  // only inspects elements that declare the key.

  auth_service = component "Auth Service" {
    description "Issues and validates session tokens"

    metadata {
      code_module = "src/auth/service.py"
      req_ids     = "REQ-01, REQ-03, REQ-07"
    }
  }

}

/*
 * ── Spec side ────────────────────────────────────────────────────────────────
 * Add to the archived SPEC's YAML frontmatter at
 * `.ai-state/specs/SPEC_<name>_YYYY-MM-DD.md`. The list is per-spec, not
 * per-REQ — fine-grained REQ->element mapping is the model side's job above.
 * Values are dot-qualified LikeC4 element ids, not titles: a row and its
 * element legitimately carry different names, and id is the only stable bind.
 *
 * ---
 * spec_name: auth-flow
 * status: completed
 * architectural_elements:
 *   - auth.service
 *   - auth.session_store
 *   - api.gateway
 * ---
 *
 * An absent `architectural_elements:` key is not a failure. It means "not yet
 * mapped", which is a distinct state from "untested" and produces no PASS/FAIL
 * noise on existing traceability-matrix rows — the orphan check is what turns
 * a sustained absence into a finding.
 */
