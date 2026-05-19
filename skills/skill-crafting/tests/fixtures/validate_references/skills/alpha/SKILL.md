---
name: alpha
description: Fixture skill hosting link-class scenarios for validate_references
---

<!-- SCENARIO CATALOG — each numbered line below is one spec row from SYSTEMS_PLAN.md §4.4 -->

# Alpha fixture skill

## Intra-skill links

- OK intra-skill: [target exists](references/valid_target.md)
- FAIL intra-skill: [broken target](references/does_not_exist.md)

## Sibling-skill links

- OK sibling-skill: [beta exists](../beta/SKILL.md)
- FAIL sibling-skill: [gamma missing](../gamma/SKILL.md)

## Cross-artifact links

- OK rules/: [sample rule](../../rules/swe/sample-rule.md)
- FAIL rules/: [broken rule](../../rules/swe/missing-rule.md)
- OK agents/: [sample agent](../../agents/sample-agent.md)
- FAIL agents/: [broken agent](../../agents/missing-agent.md)
- OK commands/: [sample command](../../commands/sample-command.md)
- FAIL commands/: [broken command](../../commands/missing-command.md)

## Same-file anchors

- OK same-file: [jump to section](#same-file-anchors)
- OK em-dash slug: [double-hyphen anchor](#ignore-mechanism--inline)
- FAIL same-file: [nonexistent heading](#this-heading-does-not-exist)

## Cross-file anchors

- OK cross-file: [anchored target](references/anchored.md#real-heading)
- FAIL cross-file missing file: [missing file](references/not_there.md#anything)
- FAIL cross-file missing slug: [file exists slug missing](references/anchored.md#ghost-heading)

## Code-file (allowlisted) links

- OK code-file allowlisted: [real script](../../scripts/sample.py)
- FAIL code-file allowlisted missing: [missing script](../../scripts/missing.py)

## External URLs

- OK external URL: [example.com](https://example.com)
- OK external URL http: [also ignored](http://example.org/page)

## Ignore mechanism — inline

- Would FAIL but ignored: [intentionally broken](references/broken_intentional.md) <!-- validate-references:ignore -->

## WARN — path into ignored dir

- WARN .ai-work path: [paste error](../../.ai-work/should-be-excluded.md)

## Ambiguous slug (WARN — two headings slugify to same anchor)

See `references/anchored.md` for the ambiguous heading case.
