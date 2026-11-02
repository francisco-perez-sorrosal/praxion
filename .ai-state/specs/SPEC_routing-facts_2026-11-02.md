# Spec: routing-facts (every routing surface states the harness's current resolution order and alias facts, the L tier is the `haiku` alias, and the advisory spawn-model check reads real prompts and driver requests correctly)

**Created**: 2026-11-02T13:30:00Z
**Pipeline run**: 2026-11-01 to 2026-11-02
**Status**: completed
**Complexity**: medium (Standard tier; 15 requirements)
**Base commit**: 0d74e8b9 · acceptance design 45cee106 · final head before merge 31176c9b

## Feature Summary

The bundle td-547 + td-550 + td-552 + td-553. Claude Code's documentation (re-read 2026-11-01) contradicted the routing texts: since v2.1.251 the per-spawn `model` comes first and `CLAUDE_CODE_SUBAGENT_MODEL` is a default that overrides everything only with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`; the `haiku` alias resolves to Haiku 5.5 on the Anthropic API and Haiku 4.5 elsewhere, never to Haiku 3.5, so the L tier's `claude-haiku-4-5` pin and its stated reason were stale. The routing texts now state those facts in fewer always-loaded tokens (19,724 → 19,697), the L tier is the `haiku` alias (the doc-engineer floor, the researcher's lookup mode and the implementer's `tier: L` hint, which the step-loop driver now honours), both sanctioned downgrades are named, and the spawn-model check reads markers anywhere, judges driver spawns against the step's own `tier:` field and a pointer-stated light review, reads one-model sessions as unknown, and has the verifier as its reader.

## Requirements

Complexity: Standard. Brownfield: the model-routing move's archived spec is the baseline. This change restates the harness facts that spec carried as they stood, and it amends that spec's spawn-check readings where its own open findings named the gaps. REQ ids are pipeline-local and must not appear in code, tests or docstrings.

### Observable Surface

Declared names (each usable in requirement text):

- `rules/swe/agent-model-routing.md`: the routing rule, which loads in full when a file under `agents/**` or the policy reference is read or edited (the "path-loaded rule"; holds the `### Tier Table`)
- `rules/swe/agent-model-routing-resident.md`: the session-start routing text, which the rule injection delivers at session start
- `skills/agent-crafting/references/model-routing-policy.md`: the routing policy reference
- `agents/doc-engineer.md`: the L-tier definition; its `model:` line is the L-tier floor
- `agents/**`: the agent definitions tree
- `.ai-state/SYSTEM_DEPLOYMENT.md`: the deployment document; its configuration table has a row for `CLAUDE_CODE_SUBAGENT_MODEL`
- `scripts/check_spawn_models.py`: the spawn-model check; `python3 scripts/check_spawn_models.py <transcripts-dir> [--repo-root DIR] [--json]`, exit 0, 1 or 2
- `floor`, `override`, `unexplained`, `unknown`: the spawn-model check's four verdicts
- `scripts/check_model_routing_parity.py`: the parity gate
- `scripts/check_gate_liveness.py`: the gate-liveness check; `python3 scripts/check_gate_liveness.py --check uninvoked-gate`; `GL04`: its finding for a gate nothing invokes
- `scripts/measure_token_budget.py`: the always-loaded and listing reading; `python3 scripts/measure_token_budget.py --json`
- `python3 scripts/check_agent_prompt_size.py --json`: the prompt-size reading
- `scripts/regenerate_rules_manifest.py`: the rules-manifest generator (`--check`)
- `scripts/check_kernel_manifest.py`: the kernel manifest gate
- `scripts/generate_kernels.py`: the kernel generator (`--check`)
- `scripts/sync_canonical_blocks.py`: the canonical-block sync (`--check`)
- `install.sh`: the installer; `bash install.sh --check` verifies an install
- `codex/config/export-codex-pipeline-adapter.py`: the Codex pipeline adapter, which writes the model-routing and pipeline-semantics exports
- `codex/config/export-codex-agents.py`: the Codex agents exporter, which writes per-agent model settings from the tier
- `codex/config/export-codex-rules-bridge.py`: the Codex rules bridge exporter
- `cursor/config/export-cursor-rules.py`: the Cursor exporter
- `CLAUDE_CODE_SUBAGENT_MODEL`: the subagent-model environment variable
- `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`: the forcing setting
- `opus`, `sonnet`, `haiku`, `fable`: model aliases; `inherit`: the `model:` value that selects the main session's model
- `model`, `model:`: the Agent tool's per-spawn parameter, and a definition's frontmatter field
- `claude-haiku-4-5`: today's pinned L-tier id
- `Mode: acceptance-design`, `Mode: light-review`, `tier: H`, `tier: L`, `routine`, `difficulty-hint`: the spawn-prompt and plan markers the deviations key on
- `Task slug:`, `Spawn request:`: a step-loop driver prompt's first line, and its request line
- `discipline-consultant`, `researcher`, `implementer`, `verifier`, `test-engineer`, `doc-engineer`: agent roles
- `Resolved in:`: the line an answered Spec Question carries, naming the resolving commit

Surfaces a session or reader can observe:

- **S, the session-start text.** What the injection delivers before any tool call.
- **P, the path-loaded rule.** The routing rule with its tier table.
- **R, the policy reference.** Read on demand.
- **D, the L-tier definition's `model:` line.** Its value and any trailing comment.
- **Spawn-check verdicts.** One per spawn, with its reason, plus the exit status and the text or `--json` output.
- **Exports.** The Codex pipeline adapter's two JSON files, the Codex agents export, the Codex rules bridge's manifest and session-start pointer, and the Cursor export tree.
- **Readings and gate verdicts.** The always-loaded reading's file list and token counts, the prompt-size findings, and each gate's exit status and findings.

**Root normalisation for export comparison.** Some exports write the absolute repository root: the adapter's source paths, and the bridge's root and per-rule source paths. A comparison replaces the root with `<repo>` in every string value, then compares the JSON parsed, not as bytes.

**Statement placement (the oracle for REQ-01 to REQ-05).** "yes" means the surface must carry the statement. "absent" means the surface must not carry it. "—" means it is not required there. Any statement of the base not listed below keeps its base placement and evidence tokens. That covers the title, the per-spawn lever, the capability floor, the fallback, the restated directive and its consultant, acceptance-design and light-review deviations, the pointer to the policy reference, and the scope sentence.

| Id | Statement | S | P | R | D | Evidence |
|---|---|---|---|---|---|---|
| F-01 | Resolution order: per-spawn `model`, then the definition's `model:` floor, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the main session model | yes | yes | yes (per-spawn beats the floor; the floor beats the env var) | — | On S and P, "per-spawn" precedes "capability floor", which precedes `CLAUDE_CODE_SUBAGENT_MODEL`, which precedes "fallback". On R, no sentence places the env var above the floor or the per-spawn model. |
| F-02 | `inherit` as a `model:` value selects the main session's model | — | yes | yes | — | `inherit` |
| F-03 | The env var overrides every other layer only with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` | yes | yes | yes | — | `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`; no sentence calls the env var a kill switch without the forcing condition |
| F-04 | Forcing also makes the harness ignore `model:` and stops a per-spawn `model` being passed | — | — | yes | — | both effects named |
| F-05 | `opus` and `sonnet` track the newest generation | yes | yes | yes | — | "newest generation" |
| F-06 | `haiku` resolves to Haiku 5.5 on the Anthropic API and to Haiku 4.5 on other providers, never below 4.5 | yes (never below 4.5) | yes | yes | no contradicting claim | S: "4.5". P and R: "Haiku 5.5" and "Haiku 4.5". |
| F-07 | `haiku` resolves to Haiku 3.5, and the L tier is the pinned `claude-haiku-4-5` | absent | absent | absent (the Haiku 3.5 claim) | absent | No sentence says `haiku` resolves to or lands on Haiku 3.5. `claude-haiku-4-5` is absent from S, P and D. |
| F-08 | The per-spawn `model` takes only `sonnet`, `opus`, `haiku` or `fable`, never a full id or `inherit` | yes (never a full id) | yes | yes | — | R: `fable`. S and P: a full id is never passed per spawn. |
| F-09 | A family alias resolves to the main session's exact model when that model is of the same family | — | — | yes | — | "same family" |
| F-10 | A full id is pinned only in a definition's `model:` (or the env var), and only when version-locking | yes | yes | yes | — | "version-locking"; no sentence says a full id is pinned at spawn time |
| F-11 | The L tier is the `haiku` alias | — (absent: the tier-table row) | yes (row) | yes | `model: haiku` | P: the `doc-engineer` row reads tier L, alias `haiku` |
| F-12 | A researcher in its simple-lookup mode, and an implementer step hinted `tier: L`, pass `haiku` | yes | yes | yes | — | One sentence names `researcher`, "mode" and `haiku`. One names `implementer`, `tier: L` and `haiku`. No sentence says the L tier is not a value to pass. |
| F-13 | Both sanctioned downgrades: the routine consult and the verifier's light review | — | yes (the consultant row) | yes | — | The consultant row holds "routine" and "light review". "only sanctioned downgrade" is absent on P and R. |
| F-14 | The spawn-model check's readers | — | — | yes | — | Every reader named invokes the check. |

The deployment document's configuration row for `CLAUDE_CODE_SUBAGENT_MODEL` states the forcing condition with any kill-switch claim (F-03).

**Frozen observations this change meets (the oracle for REQ-15).** An earlier change's outer loop pins each observation below. The correction contradicts each one, so it may change only through an answered Spec Question.

| Id | Frozen observation | Pinned in | Conflicts with | Status |
|---|---|---|---|---|
| FO-01 | The prior move's "kill switch first" placement: the kill switch is the first resolution layer. Its ordering scenario puts `CLAUDE_CODE_SUBAGENT_MODEL` before "lever", "capability floor" and "fallback" on S and P. | `tests/acceptance/drivers/model_routing_move.py` (placement row "kill-switch"); `tests/acceptance/test_routing_table_leaves_session_start.py` (resolution-order scenario) | REQ-01 | Answered (SQ-01): REQ-01 stands; the frozen files are amended minimally |
| FO-02 | The prior move's "Haiku 3.5" placement. `claude-haiku-4-5` and "Haiku 3.5" sit on S, P and R, meaning "the L tier pins `claude-haiku-4-5` because bare `haiku` is Haiku 3.5". The literal `doc-engineer` row with `claude-haiku-4-5` sits on P. The spawn-check driver maps the L floor's pinned id to a model id. | `tests/acceptance/drivers/model_routing_move.py` (placement rows "haiku-pin" and "doc-engineer-row"; the floor-to-model-id map) | REQ-02, REQ-03 | Answered (SQ-02): REQ-02 and REQ-03 stand; the frozen rows and map are amended minimally. A token kept in a sentence whose meaning is inverted does not satisfy the frozen statement. |
| FO-03 | The prior move's base-equality pins. The full rule's tier table equals the base's. The full rule differs from the base only by its restated directive, and so does the Cursor routing file. The Codex adapter's exports equal the base's. | `tests/acceptance/test_routing_table_leaves_session_start.py`, `tests/acceptance/test_routing_move_keeps_every_other_reach.py`, base fixtures under `tests/acceptance/fixtures/model_routing_move/` | REQ-01 to REQ-05, REQ-11 | Answered (SQ-03): the requirements stand; the frozen nodes are amended minimally, and REQ-11's declared-difference scenarios against a base frozen at 0d74e8b9 take their place |
| FO-04 | The prior move's one-model reading. Every spawn of a session whose spawns all ran on one model, with differing floors and no model passed, reads `override` as the kill switch. | `tests/acceptance/test_spawn_models_are_checkable_from_transcripts.py` (one-model scenario) | REQ-08 | Answered (SQ-04): REQ-08 stands; the frozen expectation becomes `unknown` |
| FO-05 | td-552's marker shapes. The outer loop sanctions a marker at a line start and a parenthesised hint at a line end. The transcript parser's tests read no marker from a partial word, a negation, a mid-sentence mention or an indented line. | `tests/acceptance/test_spawn_models_are_checkable_from_transcripts.py`; `scripts/test_spawn_transcripts.py` | REQ-06 | Answered (SQ-05): a whole-phrase marker anywhere counts, and negation and quotation are not interpreted. The negation, mid-sentence and indented-line no-marker shapes flip; the partial-word shapes hold. |
| FO-06 | The step-loop driver's low-tier routing: a `tier: L` step is requested at `sonnet`, never at `haiku`. | `tests/acceptance/test_step_loop_spawn_request.py` (step-routing scenario, low-tier case) | REQ-04 | Answered (SQ-06): a `tier: L` step is requested at `haiku` on every path, the driver's included |

The prior move's archived spec stays as history. Its clauses on the kill switch coming first, the Haiku 3.5 trap and the one-model kill-switch reading are superseded by this change, not edited.

Forcing evidence (REQ-08): no known transcript record carries evidence that the operator set the forcing setting. REQ-08 does not require such evidence to exist, so with none recorded, every qualifying one-model session reads `unknown`.

Marker shapes (REQ-06, as ruled on SQ-05). These read as present:

- `Tier: Full. Mode: acceptance-design.` (mid-line)
- ``Step hint: `tier: L`.`` (in backticks)
- `This is not Mode: light-review work.` (the negation is not interpreted)
- `The step is tier: H and a routine one.` (marks `tier: H` and `routine`)

These read as none, because each holds a marker only as part of a longer word: `a tier: High hint`, `routinely`, `Mode: acceptance-designs`.

### REQ-01: Every routing surface states the resolution order the harness applies

**When** a reader opens the session-start routing text, the path-loaded rule or the policy reference, **the system** states the order in which a spawn's model is chosen, as the harness applies it today, on each surface the placement table marks. A per-spawn `model` comes first, then the definition's `model:` floor, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the main session model. Each of those surfaces also states that the environment variable overrides every other layer only when `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` is set, **and** no surface, the deployment document's configuration row included, lists the environment variable first or calls it a kill switch without that condition, **so that** the orchestrator and an operator act on the precedence the harness really applies.

### REQ-02: Alias facts are current on every routing surface

**When** a reader opens any routing surface or the L-tier definition's `model:` line, **the system** states each alias fact the placement table assigns to that surface:

- `opus` and `sonnet` track the newest generation.
- `haiku` resolves to Haiku 5.5 on the Anthropic API and to Haiku 4.5 on the other providers, never below 4.5.
- The per-spawn `model` takes only `sonnet`, `opus`, `haiku` or `fable`, never a full id or `inherit`.
- A family alias resolves to the main session's exact model when that model is of the same family.
- A full id is pinned only in a definition's `model:`, and only when version-locking.

**And** no surface, definition line or check description states that `haiku` resolves to Haiku 3.5, that a full id can be passed per spawn, or that any alias maps to a single version, **so that** no routing choice rests on a retired model or on a parameter value the Agent tool refuses.

### REQ-03: The L tier is the `haiku` alias

**When** a reader opens the tier table, the L-tier definition or the policy reference's researcher modes, **the system** names the L tier as the `haiku` alias: the `doc-engineer` row's alias and that definition's `model:` floor both read `haiku`. The parity gate passes with the consultant's declared floor as its only declared difference, **and** no surface names a pinned full id as the L tier or as the `doc-engineer` floor, **so that** the L tier never runs below today's Haiku 4.5 and runs on the newer Haiku on the Anthropic API.

### REQ-04: The L-tier deviations are passable as `haiku`

**When** the main session reads the spawn directive in the session-start routing text or the path-loaded rule, **the system** tells it to pass `haiku` for a `researcher` in its simple-lookup mode and for an `implementer` step hinted `tier: L`, each in a sentence naming the role, its marker and its model. No surface says the L tier is not a value to pass, and the `doc-engineer` gains no sanctioned per-spawn deviation.

**And** every path that issues an `implementer` spawn honours the step's hint, the step-loop driver's requests included:

- a step hinted `tier: L` is requested at `haiku`;
- a step hinted `tier: H` is requested at `opus`;
- a step with no hint is requested at the definition's floor.

**And** the spawn-model check reads both kinds of spawn as `override` when they passed `haiku` and ran on any Haiku model, and reads a `doc-engineer` spawn that passed `sonnet` as `unexplained`, **so that** both downward deviations can be applied as written on every path, the L tier is reachable through the driver, and the doc-engineer is never routed up.

### REQ-05: Both sanctioned downgrades are named

**When** a reader opens the tier table's `discipline-consultant` row, the policy reference's per-spawn overrides or the description shipped with the parity gate, **the system** names two sanctioned downgrades below a role's tier: the routine consult and the verifier's light review. **And** no text calls either of them the only, or the one, sanctioned downgrade, **so that** no reader takes the sanctioned light review for an unsanctioned downgrade.

### REQ-06: Markers written mid-line or in backticks are read

**When** a spawn prompt writes one of the markers the deviations key on (`Mode: acceptance-design`, `Mode: light-review`, `tier: H`, `tier: L`, `routine`) as a whole phrase anywhere in the prompt, **the system**'s spawn-model check reads that marker as present, exactly as it reads one written bare at a line start. That covers a marker written mid-line, on an indented line, in a parenthesised hint, or inside backticks. The check does not interpret negation or quotation around a marker: a prompt that writes a marker states that routing. **And** text that holds a marker only as part of a longer word holds none (a tier letter that runs on into a word, or a marker word carrying a suffix), **so that** spawns the orchestrator marked in any of these ways stop reading `unexplained` and the reading needs no judgement of the prompt's prose.

### REQ-07: Driver-issued spawns are checked against the routing their request implies

**When** a spawn issued by the step-loop driver ran off its definition's floor, **the system**'s spawn-model check reads it as `override` only when it ran on the model its request implies. A driver-issued spawn is one whose prompt opens with `Task slug:` and carries a `Spawn request:` line. The implied models are:

- `sonnet` for a light-review request;
- `opus` for a step hinted `tier: H`;
- `haiku` for a step hinted `tier: L`;
- the floor itself for a step with no hint.

The check reads what a request implies from the rendered request that the spawn's own transcript records reading. It reads the spawn as `unexplained` when it ran on another model, and as `unknown` when the spawn records no read of its rendered request. A driver-issued spawn that ran on its floor reads as today, **so that** the driver's routing is checked rather than exempted.

### REQ-08: A one-model session reads unknown, not the kill switch

**When** every spawn of a session ran on one model family, their floors differ, none passed a per-spawn `model`, and the recorded transcripts carry no evidence that the operator forced one model, **the system**'s spawn-model check reads each spawn that ran off its floor as `unknown`, with a reason saying the forcing setting cannot be excluded. It reads each spawn on its floor as `floor`, and never reads such a spawn as an `override` attributed to a kill switch. **And** the check's exit codes and output shape stay as today, and it starts no model session, **so that** the check no longer credits a forcing setting it cannot see, now that passing no model is the default.

### REQ-09: The spawn-model check has a reader

**When** the gate-liveness check runs its uninvoked-gate check over the shipped tree, **the system** reports no `GL04` finding for the spawn-model check. That holds because an agent definition responsible for verifying routing changes tells its agent to run the check over the recorded sessions such a change touches. **And** every text that names the check's readers names only readers whose definitions invoke it, **so that** the check's claimed readers are real and its findings reach someone.

### REQ-10: The always-loaded routing text does not grow

**When** the always-loaded reading is taken over the shipped tree, **the system** reports a tokenizer-measured total at or below the base's 19,724 tokens, with the same file list as the base, **so that** correcting the facts costs every session nothing at start.

### REQ-11: Exporter output is unchanged or explained

**When** the Codex pipeline adapter, the Codex agents exporter, the Codex rules bridge and the Cursor exporter run over the shipped tree, **the system** writes output equal to the base's after root normalisation. The only allowed differences are ones that each trace to a statement this change corrects or adds: the L-tier row's alias, the rationale text of rows whose cell changed, and the routing rule's corrected paragraphs. **And** every agent's tier and Codex model settings stay the base's, **so that** Codex and Cursor routing is unchanged and every diff is explained.

### REQ-12: Routing without the hooks falls back to today's behaviour

**When** the session-start injection is absent (under Codex, under Cursor, or in an install whose hooks do not run), **the system** still runs each spawn at its definition's floor, still gives Codex its tier routes keyed on the same tier column, and still gives Cursor the routing rule, **so that** a missing hook leaves routing where it is today and never leaves a session with no routing at all.

### REQ-13: Gates stay green and still bite

**When** the parity gate, the rules-manifest check, the kernel manifest gate, the kernel generator check, the canonical-block sync check and the install check run on the shipped tree, **the system** passes each one. **And** the gates still report two known-bad inputs: a tier-table row that disagrees with its definition, and a session-start routing line that is no line of the routing rule, **so that** the corrections cost no gate its bite.

### REQ-14: Changed shipped texts cite no internal record

**When** a reader opens any shipped text this change edits (the routing rule, the session-start routing text, the policy reference, an agent definition, or a routing check's description), **the system** shows no decision-record id, ledger-row id or archived spec filename, **so that** the texts read correctly in a managed project that holds none of those records.

### REQ-15: Frozen observations change only through answered Spec Questions

**When** an outer-loop observation frozen by an earlier change pins a statement or reading this change corrects (the frozen observations FO-01 to FO-06 under the observable surface), **the system** changes that observation only through a Spec Question answered before the first production change. The answer records the observation, the requirement it conflicts with, and `Resolved in:` naming the resolving commit. **And** every other frozen observation holds over the shipped tree, **so that** no earlier guarantee is rewritten silently.

### Spec Question Answers (round 0)

The orchestrator answered these before design. The requirement text above encodes each answer. Each question's resolution line, with `Resolved in:`, lives in the acceptance design's Spec Questions.

| Question | Answer | Requirement text changed |
|---|---|---|
| SQ-01 | A frozen-guard conflict (FO-01). The corrected order stands, and the test-engineer amends the frozen files minimally. | none |
| SQ-02 | A frozen-guard conflict (FO-02). The L tier as `haiku` stands, and the frozen rows and floor map are amended minimally. | none |
| SQ-03 | A frozen-guard conflict (FO-03). The declared-difference scenarios take the base-equality pins' place, and the frozen nodes are amended minimally. | none |
| SQ-04 | A frozen-guard conflict (FO-04). The one-model reading becomes unknown, and the frozen expectation is amended minimally. | none |
| SQ-05 | A marker written mid-line or inside backticks counts exactly as one written bare at a line start. Negation and quotation around a marker are not interpreted. | REQ-06 (and AC-06, FO-05) |
| SQ-06 | The implementer's `tier: L` hint is honoured on every path that issues an implementer spawn, the step-loop driver's requests included: `haiku` for `tier: L`, `opus` for `tier: H`, the floor for no hint. | REQ-04 (and AC-04, FO-06 added, REQ-15's range) |
| SQ-07 | What a driver spawn's request implies is read from the rendered request the spawn records reading. | REQ-07 (and AC-07) |

## Spec Question Answers

Eight Spec Questions, all answered (full records in the pipeline's ACCEPTANCE_TESTS.md, archived here in summary):
- SQ-01 to SQ-04 and SQ-06: frozen-guard conflicts from the model-routing move (kill-switch-first order; 'Haiku 3.5', the pinned id and the doc-engineer row; the base-equality comparisons of the rule, Cursor file and Codex adapter; the one-model kill-switch reading; the driver's `tier: L` to sonnet test). The new requirements stand; each frozen file was amended minimally in the acceptance-design commit 45cee106.
- SQ-05: a routing marker written mid-line or in backticks counts as a bare one; negation or quotation around it is not interpreted (REQ-06).
- SQ-07: the routing a driver spawn's request implies is read from the request the spawn records reading (REQ-07); the final reading is the step's own `tier:` field plus a pointer-stated light review (rework 9757a403).
- SQ-08: the moved-not-cut guard read this change's restated paragraphs as cuts; they joined its declared rewordings, and its filter now drops by frozen index (2f323f82, before any production commit).

## Traceability

| Requirement | Test(s) | Implementation | Status |
|-------------|---------|----------------|--------|
| REQ-01 | `tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_resolution_order_reads_per_spawn_then_floor_then_the_variable_then_the_session`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_each_surface_names_the_forcing_setting`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_no_surface_calls_the_variable_a_kill_switch_without_its_forcing_condition`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_deployment_row_names_the_forcing_condition_with_any_kill_switch_claim`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_policy_reference_never_ranks_the_variable_above_the_floor_or_the_per_spawn_model`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_policy_reference_names_both_effects_of_forcing`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_inherit_is_named_as_the_floor_value_that_selects_the_main_session_model`<br>`tests/acceptance/test_routing_table_leaves_session_start.py::test_the_resolution_order_names_the_per_spawn_lever_first_and_the_session_model_last` | `scripts/CLAUDE.md`<br>`.ai-state/SYSTEM_DEPLOYMENT.md`<br>`rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml`<br>`skills/agent-crafting/references/model-routing-policy.md` | PASS |
| REQ-02 | `tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_opus_and_sonnet_are_said_to_track_the_newest_generation`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_session_start_text_says_haiku_never_resolves_below_4_5`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_rule_and_reference_name_what_haiku_resolves_to_by_provider`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_no_surface_says_haiku_resolves_to_haiku_3_5`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_no_check_description_says_haiku_resolves_to_haiku_3_5`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_pinned_haiku_id_is_gone_from_the_session_text_the_rule_and_the_floor_line`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_a_full_id_is_said_never_to_be_passed_per_spawn`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_no_surface_says_a_full_id_is_pinned_at_spawn_time`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_policy_reference_names_fable_among_the_per_spawn_values`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_policy_reference_says_a_family_alias_resolves_to_the_session_model_of_that_family`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_full_ids_stay_reserved_for_version_locking` | `rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml`<br>`skills/agent-crafting/references/model-routing-policy.md` | PASS |
| REQ-03 | `tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_tier_tables_doc_engineer_row_reads_tier_l_alias_haiku`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_l_tier_definitions_floor_is_the_haiku_alias`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_policy_reference_names_the_l_tier_as_the_haiku_alias`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_policy_reference_names_no_pinned_id_as_the_l_tier`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_doc_engineer_passing_no_model_on_any_haiku_model_reads_floor`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_named_gate_passes_on_the_shipped_tree`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_parity_gates_declared_difference_is_still_the_consultants_floor`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_parity_gate_reports_an_l_tier_definition_pinned_to_a_full_id` | `rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml`<br>`skills/agent-crafting/references/model-routing-policy.md` | PASS |
| REQ-04 | `scripts/test_plan_step_record.py::test_tier_h_routes_to_opus_tier_l_to_haiku_and_anything_else_to_sonnet`<br>`scripts/test_plan_step_record.py::test_every_routing_the_reader_yields_is_in_the_closed_set`<br>`scripts/test_loop_render_module.py::test_the_agent_call_accepts_haiku`<br>`scripts/test_loop_render_module.py::test_the_agent_call_refuses_a_model_outside_the_routing_set`<br>`scripts/test_loop_render_module.py::test_the_model_follows_the_routing_and_never_the_reviewer`<br>`scripts/test_check_spawn_models.py::test_a_listed_deviation_that_ran_as_requested_is_an_override`<br>`scripts/test_check_spawn_models.py::test_a_per_spawn_model_the_directive_does_not_list_is_unexplained`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_directive_tells_a_researcher_in_its_simple_lookup_mode_to_pass_haiku`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_directive_tells_an_implementer_step_hinted_tier_l_to_pass_haiku`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_no_surface_says_the_l_tier_is_not_a_value_to_pass`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_doc_engineer_gains_no_per_spawn_deviation`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_researcher_in_simple_lookup_mode_passing_haiku_reads_override`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_an_implementer_step_hinted_tier_l_passing_haiku_reads_override`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_doc_engineer_routed_up_to_sonnet_reads_unexplained_and_fails_the_check`<br>`tests/acceptance/test_step_loop_spawn_request.py::test_the_model_follows_the_step_routing_annotation` | `scripts/_plan_steps.py::_read_step`<br>`scripts/_step_loop_render.py::Model`<br>`rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml`<br>`skills/agent-crafting/references/model-routing-policy.md`<br>`scripts/check_spawn_models.py` | PASS |
| REQ-05 | `tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_consultant_row_names_the_routine_consult_and_the_light_review`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_policy_reference_names_the_routine_consult_and_the_light_review`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_parity_gates_description_names_the_routine_consult_and_the_light_review`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_no_routing_surface_calls_either_downgrade_the_only_one`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_the_parity_gates_description_calls_neither_downgrade_the_only_one` | `scripts/check_model_routing_parity.py`<br>`rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml`<br>`skills/agent-crafting/references/model-routing-policy.md` | PASS |
| REQ-06 | `scripts/test_spawn_transcripts.py::test_a_marker_inside_a_longer_word_is_no_marker`<br>`scripts/test_spawn_transcripts.py::test_a_marker_written_as_a_whole_phrase_is_a_marker_wherever_it_stands`<br>`scripts/test_check_spawn_models.py::test_a_session_on_one_model_with_differing_floors_reads_unknown_off_the_floor`<br>`scripts/test_check_spawn_models.py::test_a_session_where_a_spawn_passed_a_model_is_judged_spawn_by_spawn`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_marker_written_mid_line_or_in_backticks_sanctions_its_deviation`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_marker_held_only_inside_a_longer_word_sanctions_nothing` | `scripts/spawn_transcripts.py::_MARKER_PATTERNS`<br>`scripts/check_spawn_models.py` | PASS |
| REQ-07 | `scripts/test_spawn_transcripts.py::test_a_driver_request_implies_the_routing_of_its_steps_own_tier_field`<br>`scripts/test_spawn_transcripts.py::test_a_light_review_the_pointer_states_implies_sonnet_whatever_the_step_hints`<br>`scripts/test_spawn_transcripts.py::test_a_light_review_the_spawn_never_read_still_implies_sonnet_from_its_pointer`<br>`scripts/test_spawn_transcripts.py::test_a_light_review_marker_inside_the_rendered_request_sets_nothing`<br>`scripts/test_spawn_transcripts.py::test_a_marker_in_step_prose_or_a_code_fence_sets_nothing`<br>`scripts/test_spawn_transcripts.py::test_a_tier_line_in_a_section_after_the_step_block_sets_nothing`<br>`scripts/test_spawn_transcripts.py::test_a_driver_request_read_back_only_as_numbered_lines_implies_the_same_routing`<br>`scripts/test_spawn_transcripts.py::test_a_first_part_of_a_longer_request_that_stops_short_of_the_tier_does_not_show_it`<br>`scripts/test_spawn_transcripts.py::test_a_part_of_a_longer_request_that_holds_the_tier_field_shows_it`<br>`scripts/test_spawn_transcripts.py::test_the_tier_field_in_a_later_part_of_the_request_is_found_across_reads`<br>`scripts/test_spawn_transcripts.py::test_a_read_with_no_line_counts_that_asked_for_a_part_is_not_the_whole_request`<br>`scripts/test_spawn_transcripts.py::test_a_read_with_no_line_counts_that_asked_for_no_part_is_the_whole_request`<br>`scripts/test_spawn_transcripts.py::test_a_driver_request_the_spawn_never_read_implies_nothing`<br>`scripts/test_spawn_transcripts.py::test_a_driver_pointer_prompt_names_the_request_it_answers`<br>`scripts/test_check_spawn_models.py::test_a_driver_spawn_off_its_floor_on_another_family_than_its_request_implies_is_unexplained`<br>`scripts/test_check_spawn_models.py::test_a_driver_spawn_off_its_floor_whose_request_is_not_shown_is_unknown`<br>`scripts/test_check_spawn_models.py::test_a_driver_spawn_on_another_family_than_implied_in_a_possibly_forced_session_is_unknown`<br>`scripts/test_check_spawn_models.py::test_a_driver_spawn_on_the_family_its_request_implies_stays_an_override_in_a_lone_session`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_driver_spawn_off_its_floor_on_the_model_its_request_implies_reads_override`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_driver_spawn_on_another_model_than_its_request_implies_reads_unexplained`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_driver_spawn_whose_transcripts_do_not_show_its_step_reads_unknown`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_driver_spawn_on_its_floor_is_never_a_finding` | `scripts/spawn_transcripts.py::_driver_request`<br>`scripts/spawn_transcripts.py::_read_step_routing`<br>`scripts/spawn_transcripts.py::_step_routing`<br>`scripts/spawn_transcripts.py::_request_reads`<br>`scripts/check_spawn_models.py::_driver_verdict` | PASS |
| REQ-08 | `scripts/test_check_spawn_models.py::test_an_unknown_one_model_spawns_reason_says_a_forced_model_cannot_be_excluded`<br>`scripts/test_check_spawn_models.py::test_a_one_model_reading_is_judged_per_session`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_one_model_session_reads_unknown_off_the_floor_and_floor_on_it`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_a_one_model_session_on_haiku_reads_every_off_floor_spawn_unknown`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_an_unknown_one_model_spawns_reason_says_forcing_cannot_be_excluded`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_the_checks_text_output_keeps_one_row_per_spawn_naming_its_role_and_verdict`<br>`tests/acceptance/test_spawn_check_follows_the_corrected_routing.py::test_reading_a_one_model_session_starts_no_model_session`<br>`tests/acceptance/test_spawn_models_are_checkable_from_transcripts.py::test_every_off_floor_spawn_of_a_session_on_one_model_reads_unknown` | `scripts/check_spawn_models.py` | PASS |
| REQ-09 | `tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_uninvoked_gate_check_finds_an_invoker_for_the_spawn_model_check`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_an_agent_definition_tells_its_agent_to_run_the_check_over_routing_sessions`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_every_reader_a_text_names_for_the_check_invokes_it` | `scripts/CLAUDE.md`<br>`agents/verifier.md`<br>`skills/agent-crafting/references/model-routing-policy.md` | PASS |
| REQ-10 | `tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_always_loaded_reading_counts_the_bases_files` | `rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml` | PASS |
| REQ-11 | `tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_codex_adapter_keeps_every_agents_tier_and_codex_route`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_codex_adapter_reads_the_l_tier_alias_as_haiku_and_every_other_alias_as_the_base`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_codex_adapter_changes_rationale_only_on_the_rows_whose_cell_changed`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_codex_adapters_other_exports_equal_the_bases`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_every_codex_agent_keeps_the_bases_model_settings`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_every_codex_agents_instructions_but_the_l_tier_agents_are_the_bases`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_l_tier_agents_codex_instructions_differ_only_by_its_model_line`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_codex_bridge_keeps_the_bases_rule_sets_paths_and_pointer`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_routing_rules_bridge_entry_differs_only_by_a_summary_drawn_from_the_rule`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_cursor_export_writes_the_bases_files_and_all_but_the_routing_rule_unchanged`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_cursor_routing_files_changes_are_the_routing_rules_corrected_paragraphs`<br>`tests/acceptance/test_routing_move_keeps_every_other_reach.py::test_the_codex_adapters_exports_equal_the_bases_but_for_the_corrected_rows` | `rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml` | PASS |
| REQ-12 | `tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_every_agent_definition_carries_its_own_model_floor`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_cursor_still_gets_the_routing_rule_with_its_tier_table`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_codex_adapter_keeps_every_agents_tier_and_codex_route` | `rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml` | PASS |
| REQ-13 | `tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_named_gate_passes_on_the_shipped_tree`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_install_check_reports_no_rule_finding_after_an_install`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_parity_gate_reports_an_l_tier_definition_pinned_to_a_full_id`<br>`tests/acceptance/test_routing_facts_keep_every_other_reach.py::test_the_kernel_gate_reports_a_session_start_routing_line_that_is_no_line_of_the_rule` | `scripts/check_model_routing_parity.py`<br>`rules/swe/agent-model-routing.md`<br>`rules/swe/agent-model-routing-resident.md`<br>`agents/doc-engineer.md` | PASS |
| REQ-14 | `scripts/test_check_spawn_models.py::test_the_module_launches_no_subprocess`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_an_edited_routing_text_cites_no_decision_ledger_or_archived_spec_id`<br>`tests/acceptance/test_routing_surfaces_state_the_harness_facts.py::test_a_routing_checks_description_cites_no_decision_ledger_or_archived_spec_id` | `rules/swe/agent-model-routing-resident.md`<br>`rules/swe/agent-model-routing.md`<br>`agents/doc-engineer.md`<br>`rules/_manifest.yaml`<br>`skills/agent-crafting/references/model-routing-policy.md`<br>`scripts/check_spawn_models.py` | PASS |
| REQ-15 | (none) | `.ai-work/routing-facts/ACCEPTANCE_TESTS.md (Spec Questions SQ-01 to SQ-08, each with Resolved in)`<br>`tests/acceptance/drivers/model_routing_move.py`<br>`tests/acceptance/test_routing_table_leaves_session_start.py`<br>`tests/acceptance/test_routing_move_keeps_every_other_reach.py`<br>`tests/acceptance/test_spawn_models_are_checkable_from_transcripts.py`<br>`tests/acceptance/test_step_loop_spawn_request.py`<br>`tests/acceptance/test_resident_text_is_moved_not_cut.py` | UNTESTED (process requirement; the verifier judged it PASS) |

## Key Decisions

- **[systems-architect] The L tier routes by the `haiku` alias (ADR draft `dec-draft-47003576`, `behavioral`).** Supersedes in part dec-484 (the clause calling the L tier "not a value to pass"); re-affirms dec-078 and dec-372. Its Disconfirmation section names the reversal trigger (tier: L steps more than 10 points worse than sonnet steps on verifier FAILs or light-review revise verdicts over 20 steps or 90 days), whose reader is still to be built (td-558).
- **[systems-architect] Resident restated in list form (no ADR, not architectural).** The resident keeps its numbered list, reordered: per-spawn, frontmatter, env var with FORCE, fallback. It also gets a tighter aliases line and pointer. Measured at 19,692 tokens with the tokenizer. **Why**: the rule's opening paragraph is the Codex bridge summary, so keeping it byte-identical leaves the bridge unchanged. **Alternatives**: the context-engineer's two-paragraph collapse (19,674), rejected because it changes the bridge summary.
- **[systems-architect] Driver request routing parsed as `DriverRequest.implied` (no ADR, implementation).** It is read from the rendered request that the spawn records reading. **Why**: that read is the only record that survives `.ai-work/` cleanup and carries the step hint. **Alternatives**: the request id (blind to hints); re-reading the plan (deleted at cleanup).
- **[systems-architect] Doc-engineer `model:` comment dropped.** The line is `model: haiku` with no comment. **Why**: an alias needs no justification, and a comment there is a fact that can go stale. **Alternatives**: reword it.
- **[systems-architect] No ADR fragment.** No decision adds, removes or splits a component, or moves a responsibility between components (ADR conventions' `architectural` test).
- **[implementation-planner] Policy reference gets its own step, apart from the rule step (sequencing; no ADR).** **Why**: the architect's risk row suggests one step, but no gate couples the policy reference to the rule (the parity hook watches `agents/*.md`, the rule file and the parity script), and one implementer window cannot hold the rule, the resident, the definition and eight policy-reference edits. **Alternatives**: one combined step, rejected on size.
- **[implementation-planner] The verifier's reader sentence goes into Phase 5 (Convention Compliance), not beside the light-review `### Model` note (no ADR).** **Why**: line 377 sits inside `Mode: light-review`, whose anti-instructions bar extra runs, so the agent that verifies a routing change would never read it there. **Alternatives**: the architect's anchor, kept if the orchestrator prefers it; the acceptance nodes accept any definition sentence naming the script and routing.
- **[implementation-planner] The spawn check changes in three steps: markers (6), verdict rules (7), driver-request reading (8) (sequencing; no ADR).** **Why**: replacing `Spawn.driver_request` and its one consumer must be one commit to keep the system working, so it cannot share a step with the verdict rules; the marker widening is independent and cheap to review on its own. **Alternatives**: one step (too large for a window), or keeping both fields during a transition (a state the design removes).
- **[implementation-planner] The step-loop driver's own routing lands last among implementer steps (10) (sequencing; no ADR).** **Why**: this run is driven by that driver; a broken edit would break `record` for its own step. No step of this plan carries a `tier:` hint, so the new routing alters no request of this run.
- **[implementation-planner] Read-only ownership is disjoint by construction.** A function split across steps lists its parameters per step instead of using a function-level entry plus overrides. **Why**: the verifier cross-checks "each node in exactly one step's field", and a naive count would read a function-level entry plus a parameter-level override as two owners. The ownership map was validated against all 173 outer-loop nodes (every node owned once, no dead entry).
- **[implementation-planner] No ADR fragment of its own.** The architect's draft (`dec-draft-47003576`, commit 35a682a3) carries the one routing-policy decision; the planner's decisions above are sequencing, not architecture.
- **[orchestrator] Quality floor accepted with the guard restated.** `tier: L` only for short mechanical steps; long autonomous coding stays at sonnet or above (the architect's flagged risk; the user's adopted recommendation named the hint as passable).
- **[orchestrator] Rework in place, one round, not five worktrees.** The verifier's five rows were small and disjoint; the consolidated round (a4313b2f, 9757a403, 31176c9b) passed the delta re-verification.

## Verification and Rework

- Final verification: FAIL (2 FAIL, 9 WARN). F-1: a driver request's implied routing was taken from any marker in the request text, so 11 of 13 real implement requests misread (hidden because each ran on its floor). C-1: the policy reference still listed a one-model session among the override readings.
- Rework in place: a4313b2f (C-1, C-2), 9757a403 (F-1, C-3, C-4, C-5), 31176c9b (B-2).
- Delta re-verification: PASS WITH FINDINGS (0 FAIL, 2 WARN: D-1 the reversal trigger's missing reader, td-558; C-6 an ephemeral file's size). On this session's real transcripts the spawn check reads 27 spawns: floor 19, override 8, unexplained 0, unknown 0.
- Step-boundary light reviews: Step 6 revise → accept (guard halves pinned); Step 7 revise → accept (docstring vs code); Step 8 FAIL → accept (the review marker lives in the pointer line; proven on real transcripts before and after); Step 10 accept.
- Suites: root 16,681 passed and eval 3,973 passed at 3a3ea460; the bare root suite was re-run on the reworked head before merge.
- Footprints: FC-01 19,697 (bound 19,724), FC-02 14,268, FC-03 0 files over their fail ceiling; `check_footprint_criteria.py --stage verify` clean.

## Deferred at Close

- td-558: the ADR draft's reversal trigger names a sentinel routing audit as its reader, and none exists.
- `docs/` pages and the rules catalog row still call the env var an operator kill switch without its forcing condition (outside this change's surfaces; a follow-up row).
- The hook-delivered resident is proven only after a release, a plugin update and a restart (a $0 check in the first session after).

## Gotchas Worth Keeping

- **A test fixture that mirrors an assumed shape.** The acceptance driver wrote the light-review phrase into the rendered request body, where the real renderer never puts it, so the driver-spawn nodes passed while every real light review read unexplained. Build fixture shapes through the producer (the renderer), or prove the reading on real records.
- **A YAML list hidden by a later duplicate key.** Two requirements' `implementation:` entries vanished behind a later `implementation: []` in traceability.yml (YAML keeps the last). Merge by key, never append a seeded empty key after a filled one.
- **A frozen guard the acceptance design did not list.** The moved-not-cut guard was frozen by an earlier move and conflicted with this change; the design's frozen-conflict table missed it, and the step gate found it. Run the whole outer loop against the intended edit before freezing the conflict list.
