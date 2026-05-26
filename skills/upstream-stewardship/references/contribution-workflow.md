# Contribution Workflow

Fork-and-PR workflow for contributing fixes to upstream open-source projects. Covers the full lifecycle from forking to PR creation, with conventions for branch naming, commit messages, and maintainer communication. Back to [SKILL.md](../SKILL.md).

Back-link: [Upstream Stewardship Skill](../SKILL.md)

## Prerequisites

Before contributing a fix:

1. **File the issue first** (or confirm one exists). Discuss proposed changes before investing in a PR. Many projects require an issue before accepting PRs.
2. **Read CONTRIBUTING.md** if the project has one: `gh api -H "Accept: application/vnd.github.raw" repos/{owner}/{repo}/contents/CONTRIBUTING.md`
3. **Check the community profile**: `gh api repos/{owner}/{repo}/community/profile` — note any specific requirements
4. **Verify `gh` auth has sufficient scopes**: `gh auth status` — forking and PR creation require `repo` scope

## Fork and Clone

```bash
# Fork the repository (creates a fork under your account)
gh repo fork {owner}/{repo} --clone

# Enter the cloned fork
cd {repo}

# Verify remotes: origin = your fork, upstream = original repo
git remote -v
```

If you already have a fork:

```bash
# Sync your fork with upstream
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

## Branch Naming

Create a descriptive branch from the latest upstream main:

```bash
git checkout -b fix/{short-description} upstream/main
```

Conventions:
- `fix/{description}` — for bug fixes
- `feat/{description}` — for new features
- `docs/{description}` — for documentation changes
- Use kebab-case: `fix/null-check-auth-handler`, not `fix/nullCheckAuthHandler`
- Keep it short but descriptive

## Making Changes

1. **Minimal scope** — one fix per PR. Do not mix unrelated changes.
2. **Atomic commits** — one logical change per commit. Separate refactoring from behavior changes.
3. **Follow the project's style** — match existing code formatting, naming conventions, and patterns.
4. **Run the project's test suite** — ensure all tests pass before committing.
5. **Add tests** if the project has them and your fix addresses a testable behavior.

### Commit Messages for Upstream

Follow the project's commit message conventions if documented. Otherwise, use a clear imperative format:

```
Fix null check in auth handler

The handler was not checking for null user objects before accessing
the session field, causing a NullPointerException when unauthenticated
requests hit the endpoint.

Fixes #{issue_number}
```

Note: Do not include AI authorship lines in upstream commits. The human owns the commit.

## Syncing Before PR

Before creating the PR, ensure your branch is up to date with upstream:

```bash
git fetch upstream
git rebase upstream/main
```

Use rebase, not merge — it produces a cleaner history that maintainers prefer. Resolve any conflicts during rebase.

## Creating the PR

```bash
gh pr create \
  --repo {owner}/{repo} \
  --title "Fix: {short description}" \
  --body "$(cat <<'EOF'
## Summary

{One paragraph describing the fix}

## Root Cause

{What was causing the bug}

## Fix

{What this PR changes and why}

## Testing

{How you verified the fix — test commands, manual verification steps}

Fixes #{issue_number}
EOF
)"
```

### Linking to Issues

Use closing keywords in the PR body to automatically link and close the issue when the PR is merged:

- `Fixes #123` — closes issue #123 when PR merges to default branch
- `Closes #123` — same effect
- `Resolves #123` — same effect
- `Fixes owner/repo#123` — cross-repo reference

**Important**: Auto-close only works when the PR targets the **default branch**. Keywords in commit messages close the issue but do not create the sidebar link.

### PR Best Practices

- **Clean history** — each commit should pass CI independently when possible
- **No conflicts** — rebase on latest upstream before requesting review
- **Descriptive description** — problem, root cause, fix, testing approach
- **Small diff** — smaller PRs get reviewed faster and are more likely to be accepted
- **CI must pass** — check the project's CI requirements before requesting review

## After Submission

- **Respond promptly** to reviewer feedback
- **Make requested changes** in new commits (do not force-push during review unless asked)
- **Be patient** — maintainers have limited bandwidth, especially on volunteer projects
- **Offer to retest** after the fix is deployed
- **Delete your branch** after the PR is merged

## When Not to Contribute a PR

- The fix is trivial and not worth the maintainer's review time (a comment on the issue suffices)
- You are unsure about the correct fix (discuss in the issue first)
- The project does not accept external contributions (check CONTRIBUTING.md or issue history)
- The fix requires deep understanding of the project's internals that you do not have
