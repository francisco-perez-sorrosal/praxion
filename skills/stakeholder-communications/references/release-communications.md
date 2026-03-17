# Release Communications

Templates and patterns for release announcements, breaking change notifications, and migration guides for downstream consumers.

## Release Announcement Template

```markdown
# [Project Name] [Version] Release

**Release date**: [Date]
**Type**: [Major | Minor | Patch]

## Highlights

- [Most important change -- user-impact language]
- [Second most important change]
- [Third most important change]

## Breaking Changes

[If none: "No breaking changes in this release."]

### [Breaking change title]

**What changed**: [Precise description of the old and new behavior]
**Who is affected**: [Which consumers or use cases]
**Migration**: [Step-by-step instructions or link to migration guide]

## New Features

- **[Feature name]**: [What it does and how to use it. Link to docs if applicable.]

## Bug Fixes

- **[Bug description]**: [What was broken and how it was fixed. Reference issue number.]

## Deprecations

- **[Deprecated item]**: Will be removed in [version]. Use [replacement] instead.

## Upgrade Instructions

[Steps to upgrade from the previous version. Include dependency changes,
configuration changes, and any manual steps required.]

## Full Changelog

[Link to diff or changelog between previous and current version.]
```

### Writing Guidance

- **Highlights**: limit to 3-5 items. These are what most readers will scan. Use user-impact language ("Queries now return results 3x faster") not implementation language ("Optimized query planner")
- **Breaking changes**: always include migration steps. A breaking change without a migration path is a support ticket generator
- **Deprecations**: include the removal timeline and the replacement. "Deprecated" without a timeline is meaningless
- **Upgrade instructions**: test the upgrade path yourself before publishing. Missing a step here costs every consumer time

## Breaking Change Notification

Send before the release when possible -- give consumers time to prepare.

```markdown
# [BREAKING] [Short description] in [Project] [Version]

**Planned release**: [Date]
**Affected versions**: [Which current versions will break]
**Deprecation period**: [If applicable -- when the old behavior was deprecated]

## What Is Changing

[Old behavior] will be replaced by [new behavior].

**Before**:
[Code example showing current usage]

**After**:
[Code example showing required changes]

## Who Is Affected

[Specific criteria: "Anyone using the `FooClient.query()` method with
custom serializers."]

## Migration Steps

1. [Step 1 -- specific, actionable]
2. [Step 2 -- specific, actionable]
3. [Step 3 -- specific, actionable]

## Timeline

- [Date]: Deprecation warning added (version X.Y)
- [Date]: Breaking change released (version X+1.0)
- [Date]: Compatibility shim removed (version X+2.0)

## Support

Contact [name/channel] for migration assistance.
```

## Migration Guide Structure

For complex breaking changes, a standalone migration guide gives consumers a complete reference.

### Sections

1. **Overview** -- what changed and why. 2-3 sentences
2. **Prerequisites** -- minimum version, tools, or configuration needed before migrating
3. **Step-by-step migration** -- ordered list of concrete actions. Include before/after code for every API change
4. **Verification** -- how to confirm the migration succeeded (test commands, expected output)
5. **Rollback** -- how to revert if something goes wrong
6. **Known issues** -- edge cases or unsupported scenarios with workarounds
7. **FAQ** -- common questions from early adopters (add as they come in)

### Migration Guide Principles

- **One guide per breaking change** -- do not combine unrelated migrations
- **Before/after for every change** -- consumers should be able to find-and-replace
- **Test the guide yourself** -- follow every step on a clean checkout before publishing
- **Version the guide** -- update it as consumers report issues or edge cases

## Versioning Communication

Semantic versioning (semver) carries implicit communication. Make the implications explicit.

| Version Bump | Signal to Consumers | Communication Required |
| --- | --- | --- |
| **Patch** (1.0.X) | Bug fix, safe to upgrade | Release notes |
| **Minor** (1.X.0) | New features, backward compatible | Release notes with feature highlights |
| **Major** (X.0.0) | Breaking changes | Release notes + breaking change notification + migration guide |
| **Pre-release** (X.0.0-rc.1) | Not production-ready, feedback welcome | Release notes with explicit stability warning |

## Communication Timing

| Event | When to Communicate | Channel |
| --- | --- | --- |
| Deprecation | At the release that adds the deprecation warning | Release notes + direct notification to known heavy users |
| Upcoming breaking change | 2-4 weeks before the breaking release | Dedicated notification (email, Slack, issue) |
| Breaking change released | At release | Release notes + migration guide |
| Migration deadline | 1 week before compatibility shim removal | Reminder notification |

### Channel Selection

- **Release notes** (changelog, GitHub release): always. This is the permanent record
- **Direct notification** (Slack, email): for breaking changes and deprecations affecting known consumers
- **Issue/ticket**: when a specific consumer needs to take action and you need to track completion
- **Meeting/demo**: when the change requires discussion or the migration is complex enough to warrant a walkthrough
