---
id: dec-526
draft_id: dec-draft-77a611dd
title: An import-linter contract carries its citation in broken_contract_guidance, not description
status: accepted
category: architectural
date: 2026-11-24
summary: import-linter 2.16 rejects any contract option no field recognizes, and description was never one, so every contract citing its decision there fails the run on a fresh install. The citation moves to broken_contract_guidance, which 2.14+ prints under a broken contract and older versions ignore; the citation contract itself, and every other clause of dec-101, stands.
tags: [fitness-functions, import-linter, citation-contract, aac-templates, onboarding]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
supersedes_in_part: [dec-101]
dissent: The field upstream named broken_contract_guidance is meant for how to fix a broken contract, and a citation is why the contract exists; a future import-linter could render or validate it as fix guidance only.
affected_files:
  - fitness/import-linter.cfg
  - fitness/tests/test_meta_citation.py
  - fitness/tests/test_judge_seam.py
  - fitness/tests/test_starter_rule.py
  - fitness/README.md
  - claude/aac-templates/fitness-import-linter.cfg.tmpl
  - claude/aac-templates/fitness-test-meta-citation.py.tmpl
  - claude/aac-templates/fitness-README.md.tmpl
  - skills/architectural-fitness-functions/SKILL.md
  - skills/architectural-fitness-functions/contexts/python.md
  - skills/architectural-fitness-functions/references/import-linter-recipes.md
affected_reqs: []
---

## Context

dec-101 put an import-linter contract's citation in a `description=` option, which import-linter accepted silently because it ignored options it did not know. Version 2.16 (2026-11-06) errors on any option no field of the contract recognizes, to catch a misspelled one, and `description` has never been a field: a contract carrying it reads `description: Unrecognized option.` and the run fails. Praxion's own lock holds 2.11, so its CI stayed green, but the fitness canaries resolved 2.17 when run outside `uv run`, and a managed project that `/onboard-project` gives the starter contract and then installs import-linter fresh fails its architecture job on the first run.

## Decision

Each contract's citation lives in `broken_contract_guidance`, the free-text option every built-in contract type has defined since 2.14 and prints under a broken contract; versions before 2.14 ignore it as they ignored `description`. The meta-citation rule reads that field, in Praxion's fitness suite and in the starter template it ships. The canaries run the project's locked import-linter (`uv run --project`), so their verdict does not depend on the caller's environment.

## Considered Options

### Rename to broken_contract_guidance (chosen)

It is the field upstream defined for prose about a contract, it works on every version a project meets, and the citation now reaches the person reading a broken contract, which `description` never did.

### Pin import-linter below 2.16

One line, but it holds Praxion and every managed project on an old version to keep an option upstream never supported, and a project that installs import-linter unpinned still breaks on the shipped template.

### A comment line above each stanza

Version-proof, but configparser drops comments, so the meta-citation rule would parse raw text by hand, and the citation would still never reach the output of a broken run.

## Consequences

- A managed project onboarded before this change keeps `description =` in its own `fitness/import-linter.cfg` and breaks on its first import-linter upgrade past 2.15; the fitness skill's recipes name the error and the one-key rename.
- The citation is printed under a broken contract (2.14+), so a reader sees which decision the boundary serves.

## Disconfirmation

- **Falsifier.** An import-linter release that rejects or restricts `broken_contract_guidance` on a contract type Praxion uses, or a managed project whose architecture job still fails on the rendered starter contract with a current import-linter.
- **Steelmanned runner-up.** Pinning import-linter below 2.16 is one line, keeps dec-101's text exact, and changes nothing a managed project already has. It loses because the shipped template would still break any project that installs import-linter unpinned, and the pin holds every project on a version that stops receiving fixes.
- **Reversal trigger.** Upstream adding a field meant for a contract's rationale (a description in all but name): the citation moves there.

## Prior Decision

dec-101's clause placing an import-linter citation in the `description=` field is narrowed to `broken_contract_guidance`. Every other clause stands: the fitness directory, import-linter plus pytest, the citation contract and its regex, the meta-citation rule, and the waiver pattern.
