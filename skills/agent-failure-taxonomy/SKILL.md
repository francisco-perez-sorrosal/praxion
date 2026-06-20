---
name: agent-failure-taxonomy
description: >
  Classification rubric for runtime failure modes of agentic AI apps (Microsoft AI Red
  Team taxonomy: prompt injection, excessive agency, tool abuse). Triggers: classify or
  diagnose an observed agent failure, or run a design-time failure-mode review. Diagnosis
  — not prevention (agent-runtime-guardrails), not plugin security (context-security-review).
allowed-tools: [Read, Glob, Grep]
compatibility: Claude Code
---

# Agent Failure Taxonomy

A **classification rubric** for the ways an agentic AI application fails at runtime. It names a failure once observed and routes it to a mitigation owner — it does **not** build the defenses (that is `agent-runtime-guardrails`). Use it to turn "the agent did something weird" into a named, mitigable category.

The rubric is seeded from the **Microsoft AI Red Team Taxonomy of Failure Modes in Agentic AI Systems** (v1.0, April 2025; major update June 2026 grounded in a year of red-teaming deployed agents). Microsoft frames each mode along two axes: a **pillar** — *Security* (an adversary causes the failure) vs *Safety* (the system harms without an adversary) — and *novel* (agentic-specific) vs *existing-amplified* (a pre-existing AI failure that agency makes worse). This skill keeps the pillar tag and reduces the rest to a Praxion-usable rubric.

## How to use the rubric

1. **Observe the failure** — read the agent's trajectory (the OTel agent-span trace; see the `observability` skill's *GenAI & Agent Spans*). The failure has a *shape* in the span tree.
2. **Match it to a mode** — find the row in the rubric below whose *runtime signal* matches what the trajectory shows.
3. **Record the classification** — name the mode in the artifact where the failure surfaced (e.g. the verifier's `.ai-work/<task-slug>/VERIFICATION_REPORT.md`, an incident note, or an ADR). A named mode is searchable; "weird behavior" is not.
4. **Route to mitigation** — each mode names a *primary mitigation* owner. Prevention design lives in `agent-runtime-guardrails`; outcome gating in `agent-evals`; the plugin-supply-chain slice in `context-security-review`.

## The Rubric — 14 runtime failure modes

Pillar: **Sec** = Security (adversary-driven) · **Saf** = Safety (no adversary needed).

| Mode | Pillar | What it is | Runtime signal (in the trajectory) | Primary mitigation |
|---|---|---|---|---|
| **Agent compromise** | Sec | Adversary gains control of the agent's reasoning/actions | Goals or tool calls not derivable from the user task appear mid-trajectory | Input validation + tool-call gating |
| **Agent (prompt) injection** | Sec | Malicious instructions in the user input hijack behavior | Instruction-shaped content in inputs, then off-task actions | Input rails; instruction/data separation |
| **Agent impersonation** | Sec | Attacker/agent poses as a trusted agent, user, or service | Identity attributes on spans inconsistent with the real principal | Authenticated agent identities; signed agent cards |
| **Agent flow manipulation** | Sec | Control flow / orchestration between steps or agents is subverted | Trajectory deviates from the designed state machine | Harness enforces allowed transitions |
| **Memory poisoning** | Sec | Malicious content written to persistent memory taints later runs | Later-run behavior traces to a tainted memory write | Validate memory writes; provenance tags; isolation |
| **Cross-domain prompt injection (XPIA)** | Sec | Injection via external content the agent ingests (web, docs, tool output, other agents) | Behavior change correlated with an external/tool-output span | Treat all tool/external output as untrusted; output validation |
| **Human-in-the-loop bypass** | Sec | Agent circumvents or fatigues the human approval gate | High-impact action span with no preceding approval event | Un-bypassable approval primitive |
| **Supply-chain compromise** | Sec | A compromised tool, model, dependency, or MCP server in the stack | Anomalous behavior tied to a specific tool/dependency version | Pin + verify deps (plugin slice → `context-security-review`) |
| **Tool abuse** | Sec | Legitimate tools misused (by the agent or an attacker via it) to harmful ends | Tool calls within permission but outside task intent | Tool-call gating; least-privilege tool scopes; budgets |
| **Excessive agency** | Saf | Agent takes consequential actions beyond what the task warranted | Side-effecting spans disproportionate to the request | Permission scoping; HITL on high-impact actions; budget gates |
| **Feedback-loop poisoning** | Saf | The agent's own outputs (or a multi-agent loop) degrade subsequent behavior | Drift across turns/iterations; escalating error | Turn/iteration budgets; loop-break conditions; output validation |
| **Goal misalignment** | Saf | Agent optimizes a proxy or misread objective diverging from user intent | On-policy tool use that never advances the actual goal | Explicit goal spec; outcome eval gates (`agent-evals`) |
| **Reasoning-based information leakage** | Saf | Intermediate reasoning leaks sensitive data into outputs, logs, or other agents | Sensitive tokens in reasoning/output spans | Output validation/redaction; scrub reasoning from external surfaces |
| **Autonomy escalation** | Sec/Saf | Agent expands its own permissions/scope/autonomy beyond granted bounds | A span acquires new capabilities/credentials mid-trajectory | Immutable permission boundary enforced by the harness |

The first seven are the v1.0 (April 2025) modes; the last seven are the June 2026 additions. For the expanded per-mode description, a worked example, and the design-time/build-time mitigation checklist, see [references/mitigation-checklist.md](references/mitigation-checklist.md).

## Consumers

- **`verifier`** — classifies an observed failure against the rubric and records the mode in `VERIFICATION_REPORT.md`. Fits the **pre-verification checkpoint** digest ("failures classified: …").
- **`systems-architect`** — at design time, walks the modes applicable to the agent being built and confirms each has a named mitigation in the design (the [mitigation checklist](references/mitigation-checklist.md)).
- **`implementer`** — uses the same checklist as a build-time confirmation that the trajectory cannot exhibit an unmitigated mode.

## Boundaries

- **vs `agent-runtime-guardrails`** — this skill is **diagnosis** (name a failure once observed); guardrails is **prevention** (build the un-bypassable layer that stops it). Classification ends where construction begins; the rubric's *mitigation* column points across the seam.
- **vs `context-security-review`** — that skill owns the **Claude Code plugin-ecosystem** attack surface (hook compromise, secrets, the plugin dependency supply chain). This skill owns the **runtime agentic-app** failure surface (what the *built* app does wrong). Supply-chain compromise touches both: the plugin slice is `context-security-review`'s; the agent's runtime tool/model stack is this skill's.
- **vs `agent-evals`** — outcome correctness (goal misalignment caught by an outcome gate) is graded there; this skill names the *mode*, the eval gate measures the *miss*.

## Sources

- [Microsoft — Updating the taxonomy of failure modes in agentic AI (June 2026)](https://www.microsoft.com/en-us/security/blog/2026/06/04/updating-taxonomy-failure-modes-agentic-ai-systems-year-red-teaming-taught-us/) — the 7 added modes, grounded in a year of red-teaming. **[VERIFIED — Microsoft primary]**
- [Microsoft — Taxonomy of Failure Mode in Agentic AI Systems (whitepaper PDF)](https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Taxonomy-of-Failure-Mode-in-Agentic-AI-Systems-Whitepaper.pdf) — the v1.0 taxonomy and the Security/Safety × novel/existing framing. **[VERIFIED — Microsoft primary]**
