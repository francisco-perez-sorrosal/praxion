# Slash Command Reference

Extended examples, patterns, and organization strategies. Loaded on-demand from `SKILL.md`.

## Contents

- [Command Patterns](#command-patterns) -- git commit, code review, project setup, simple template
- [Real-World Examples](#real-world-examples) -- git operations, documentation, testing
- [Quick Start Recipes](#quick-start-recipes) -- copy-paste shell commands to create commands
- [Command Organization Strategies](#command-organization-strategies) -- by category, tool, or workflow

## Command Patterns

### Pattern 1: Git Commit

```markdown
---
allowed-tools: [Bash(git add:*), Bash(git status:*), Bash(git commit:*)]
argument-hint: "[message]"
description: Create git commit with descriptive message
---

## Context

- Status: !`git status`
- Staged: !`git diff --staged`
- Branch: !`git branch --show-current`

## Task

Create commit with message: $ARGUMENTS

Follow conventional commits format:
- type(scope): summary (under 50 chars)
- blank line
- detailed explanation
- reference related issues
```

### Pattern 2: Code Review

```markdown
---
argument-hint: "[file-path] [focus-area]"
description: Review file focusing on specific area
allowed-tools: [Read, Grep]
---

Review @$1 focusing on $2.

Analyze:
1. Code quality
2. Best practices
3. Security considerations
4. Performance implications

Provide actionable recommendations.
```

### Pattern 3: Project Setup

```markdown
---
argument-hint: "[project-name] [optional-tool]"
description: Create new project with specified tool
---

Create project named "$1" using ${2:-default-tool}.

Setup:
- Initialize project structure
- Configure dependencies
- Add basic tests
- Create README
```

### Pattern 4: Simple Template

```markdown
---
description: Generate test names for TDD
---

Generate descriptive test names for this scenario:

[User provides scenario after command]
```

## Real-World Examples

### Git Operations

```markdown
---
allowed-tools: [Bash(git:*)]
description: Create feature branch from main
argument-hint: "[branch-name]"
---

!`git checkout main`
!`git pull`
!`git checkout -b $ARGUMENTS`
```

### Documentation

```markdown
---
allowed-tools: [Read, Write]
description: Generate README for current directory
---

Analyze project structure: !`ls -la`

Create README.md with:
- Project description
- Installation steps
- Usage examples
- Contributing guidelines
```

### Testing

```markdown
---
allowed-tools: [Bash(pytest:*), Bash(npm:*)]
description: Run tests with coverage
---

Run tests: !`pytest --cov=src tests/`

Analyze coverage and suggest improvements.
```

## Quick Start Recipes

### Simple Command

```bash
# Create command directory
mkdir -p .claude/commands

# Create command file
cat > .claude/commands/my-command.md << 'EOF'
---
description: My custom command
argument-hint: "[input]"
---

Process $ARGUMENTS according to project standards.
EOF

# Use it
/my-command test input
```

### Git Commit Command

```bash
cat > .claude/commands/commit.md << 'EOF'
---
allowed-tools: [Bash(git add:*), Bash(git status:*), Bash(git commit:*)]
argument-hint: "[message]"
description: Create descriptive git commit
---

Current status: !`git status`

Create commit with message: $ARGUMENTS

Use conventional commits format.
EOF
```

### Review Command

```bash
cat > .claude/commands/review.md << 'EOF'
---
allowed-tools: [Read, Grep]
argument-hint: "[file-path]"
description: Review file for issues
---

Review @$1 for:
- Code quality
- Security issues
- Performance problems
- Best practices

Provide detailed feedback.
EOF
```

## Command Organization Strategies

### By Category

```
.claude/commands/
├── git/
│   ├── commit.md
│   ├── branch.md
│   └── merge.md
├── code/
│   ├── review.md
│   ├── refactor.md
│   └── test.md
└── docs/
    ├── readme.md
    └── changelog.md
```

### By Tool

```
.claude/commands/
├── docker/
├── kubernetes/
├── terraform/
└── aws/
```

### By Workflow

```
.claude/commands/
├── setup/
├── develop/
├── test/
└── deploy/
```

Subdirectories appear as namespace prefixes in `/help` (e.g., `project:git`).
