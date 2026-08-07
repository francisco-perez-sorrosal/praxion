---
id: dec-329
title: Specify MCP-dependent checks against Bash-reachable readers
status: accepted
category: behavioral
date: 2026-08-06
summary: Where a check or agent procedure names an MCP tool no agent in the fleet can reach, specify the Bash-reachable reader instead and delete the finding code that could only ever report the unreachability.
tags: [gate-liveness, mcp, tool-grant, sentinel, architect-validator, ac12, likec4, unreachable-reader]
made_by: agent
agent_type: orchestrator
branch: main
re_affirms: dec-323
affected_files:
  - agents/sentinel.md
  - agents/architect-validator.md
  - docs/aac-dac.md
  - claude/aac-templates/likec4-req-ids.c4.frag
---

## Context

The 2026-08-06 sentinel run surfaced two findings that turned out to be one defect with two faces, visible only when reconciled across lenses:

- **Sentinel check AC12** (traceability orphans) named MCP `query-by-metadata` as its only reader. Verified across all 17 agent `tools:` lines: **no agent in the fleet holds a LikeC4 MCP grant.**
- **`agents/architect-validator.md:73-79`** gave an unhedged 5-step ordered `likec4` MCP procedure against a grant of `Read, Glob, Grep, Bash, Write`.

A third instance appeared under the same lens: the sentinel's own **P01–P05** name Task Chronograph MCP, and that surface returns only the live session, so those checks can never observe a historical violation regardless of grant.

Both AC12 and the validator procedure presented as *substrate absence* — "the convention is not populated yet", "no model present". That reading is wrong in a way that actively conceals: the substrate could be fully populated tomorrow and the check would still report nothing, because the reader it names is unreachable. `rules/swe/gate-liveness.md § Existence is not operation` names exactly this — a gate whose interpreter cannot reach it is indistinguishable from no gate, and *none of this is visible from the gate's own tests*, which pass in the author's environment.

The validator additionally carried a `validator-unable-to-query-likec4-mcp` WARN code, whose only possible output was a report that the grant it needs does not exist.

## Decision

**Where a check or agent procedure names an MCP tool no agent in the fleet can reach, specify the Bash-reachable reader as the specification — not as a fallback.**

Concretely:

1. **AC12** now reads the element side from `.c4` source with Bash (`grep -rn 'req_ids' --include='*.c4' .`, splitting each `req_ids = "REQ-01, REQ-03"` value), and the spec side by parsing SPEC frontmatter. MCP `query-by-metadata` is named as the *indexed equivalent for a caller that holds the grant*, not as the primary. `dec-112` had already sanctioned this grep path as the MCP-unavailable fallback; this promotes it to specification, which is both the smaller change and the one that removes the unrunnable-in-principle status outright rather than merely documenting it.
2. **`architect-validator`** leads with `find`/`Read`/`Grep`, with an explicit unavailable-under-current-grant paragraph naming the six unreachable tools. Four dependent sites that would otherwise have re-instructed MCP-first were updated in the same pass.
3. **Skips must name the failed precondition.** "Convention not yet populated" and "reader unreachable" are different states with different remedies; a skip that says only "substrate absent" conceals the second.
4. **The `validator-unable-to-query-likec4-mcp` code is deleted.** Under the corrected framing it would fire on 100% of runs forever. Genuine substrate absence is already covered by the separate `no LikeC4 model present` WARN; a new `likec4-model-unreadable` code covers the real degraded path (files present but unparseable).
5. **`claude/aac-templates/likec4-req-ids.c4.frag`** ships as copy-paste scaffolding so the bidirectional convention has a population path, and `docs/aac-dac.md` gains the reachability precondition alongside the substrate one.

## Considered Options

### A. Grant the MCP tools to the agents that need them

- **Pro**: makes the existing instructions true with no rewriting.
- **Con**: not available by the mechanism assumed. `architect-validator` is plugin-distributed, and plugin-distributed agents ignore `mcpServers` as a security boundary; no agent in the repo declares one. Widening the `tools:` allowlist with `mcp__…` names is technically possible, but the validator's CI `--mode=pre-merge` path cannot depend on an `npx`-spawned server — so Bash is correct in *both* modes, not merely reachable in one.

### B. Record the checks as blocked on a tool grant, changing no behaviour

- **Pro**: minimal, honest, and was the option the sentinel report actually recommended.
- **Con**: leaves the checks inert. It converts a silent failure into a documented one, which is better, but a documented dead gate still catches nothing — and here a working reader was already sanctioned by `dec-112` and merely unpromoted.

### C. Specify against the Bash reader (chosen)

- **Pro**: the check becomes runnable rather than merely honest about being unrunnable; no new tooling; the grep path was already blessed.
- **Con**: a linear grep is not an index — it will be slower than `query-by-metadata` on a large model, and it re-implements parsing the MCP layer would have done. Acceptable at current model size; revisit if `.c4` sources grow substantially.

## Consequences

**Positive.** AC12 moves from unrunnable-in-principle to runnable. The validator's procedure is executable under its declared grant in both invocation modes. A WARN that could only ever fire is gone. The convention gains a population path it previously lacked in any template.

**Negative.** Three ADRs and two archived sentinel reports reference the deleted finding code. Those are historical records that correctly describe what was true when written, and no live surface references it — but a reader encountering the code in `dec-112`, `dec-323`, or `dec-325` will not find it in the current validator.

**Neutral, and worth stating plainly.** The AC12 rewrite immediately tripped GL02's `forbidden-pattern` detector, because stating the golden bad-case concretely (`req_ids = "REQ-99"`) puts a `REQ-NN` literal, a scan verb, and a code target on one line. This is the same collision GL02's *own* catalog row has, and it was resolved the same way: a `gate-liveness:ignore` marker carrying the rationale. The literal is correct authoring — `gate-liveness.md` requires golden bad-cases be concrete, since an abstract paraphrase cannot make a check fire. `id-citation-discipline` exempts `agents/`, and `req_ids` in `.c4` metadata is the sanctioned convention, so the grep can match and the gate is not dead.

**Resolved separately, in the same session.** P01–P05's substrate problem is a different defect wearing the same clothes: their reader *is* reachable by the orchestrator, but the Chronograph surface carries no history, so the checks measure an in-flight session that is trivially clean. That called for a different remedy than the one here — not a reachable reader, but a substrate with a past — and it is recorded in `dec-330`, which retires P01/P02 as unanswerable-in-principle and re-specifies P03/P04 against the `observations.jsonl` WAL. The two decisions share a diagnosis (*a check specified against something that cannot answer it*) and differ in cure, which is why they are separate records rather than one.

## Prior Decision

This **re-affirms `dec-323`** (retire sentinel AC11 as subsumed by AC13) without superseding it. `dec-323`'s operative principle — a check that reports correct behaviour as drift teaches its reader to skip the dimension, which costs more than the check ever returns — is the reasoning that retires `validator-unable-to-query-likec4-mcp` here. `dec-323` remains `accepted`; a future supersession would require evidence that an always-firing diagnostic code carries signal a per-run skip reason does not.

It also **builds on `dec-112`** rather than replacing it. `dec-112` established the bidirectional traceability convention and named the grep path as the MCP-unavailable fallback; this decision promotes that fallback to the specification. No clause of `dec-112` is contradicted.
