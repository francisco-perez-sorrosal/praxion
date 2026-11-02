# TypeScript Agent Eval Patterns

TypeScript-specific tooling for agent evaluations: Vitest as the test runner and Promptfoo for eval orchestration. Reference material for the [Agent Evals](../SKILL.md) skill.

For baseline TypeScript conventions (tsconfig, module resolution, type utilities), see [typescript-development/contexts/typescript.md](../../typescript-development/contexts/typescript.md). This file covers only eval-specific usage.

## Vitest for Agent Evals

Vitest is the recommended test runner for TypeScript eval suites. Native ESM/TypeScript support requires zero config in Vite-based projects; elsewhere a minimal `vitest.config.ts` suffices.

> For deep Vitest setup (coverage, watch mode, path aliases), see `test-coverage/references/typescript.md`.

### Minimal Setup

```bash
npm install -D vitest
```

```ts
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Increase timeout for LLM calls (default 5000 ms is too short)
    testTimeout: 60_000,
    hookTimeout: 30_000,
  },
});
```

### Async Patterns for LLM Calls

LLM calls are inherently async and slow. Key patterns for eval tests:

```ts
import { describe, it, expect } from 'vitest';

// 1. Always await LLM calls — never fire-and-forget
describe('agent task completion', () => {
  it('fixes the unicode bug', async () => {
    const result = await runAgent('Fix the unicode bug in auth.py');
    expect(result.exitCode).toBe(0);
  });

  // 2. Override timeout per test when a single task may take longer
  it('refactors the entire auth module', { timeout: 120_000 }, async () => {
    const result = await runAgent('Refactor auth module to use DI');
    expect(result.output).toContain('dependency injection');
  });
});
```

### Parallel Trial Execution

Run multiple trials concurrently to handle non-determinism:

```ts
import { describe, it, expect } from 'vitest';

const TRIALS = 5;
const PASS_AT_K_THRESHOLD = 0.6; // at least 3/5 must pass

describe('non-deterministic eval with pass@k', () => {
  it(`passes at least ${PASS_AT_K_THRESHOLD * 100}% of trials`, async () => {
    const results = await Promise.all(
      Array.from({ length: TRIALS }, () =>
        runAgent('Fix the SQL injection in auth.py')
      )
    );

    const passed = results.filter((r) => r.testsPassed).length;
    const passRate = passed / TRIALS;

    expect(passRate).toBeGreaterThanOrEqual(PASS_AT_K_THRESHOLD);
  });
});
```

### Structuring Eval Test Files

Mirror the framework-patterns.md Python conventions adapted for TypeScript:

```ts
// evals/coding-tasks.eval.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { setupWorkspace, teardownWorkspace } from '../helpers/sandbox';

describe('coding agent — eval suite', () => {
  let workspaceDir: string;

  beforeAll(async () => {
    workspaceDir = await setupWorkspace('fixtures/auth-project');
  });

  afterAll(async () => {
    await teardownWorkspace(workspaceDir);
  });

  it('adds retry logic to API client', async () => {
    const result = await runAgent(
      'Add retry logic with exponential backoff to src/api-client.ts',
      { workingDir: workspaceDir }
    );

    // Deterministic check first (code grader)
    const fileContent = await fs.readFile(
      `${workspaceDir}/src/api-client.ts`,
      'utf-8'
    );
    expect(fileContent).toMatch(/retry|backoff/i);

    // Then LLM-graded quality check via Promptfoo assertions (see below)
  });
});
```

---

## Promptfoo TypeScript Integration

Promptfoo is the primary eval orchestration tool for TypeScript agent projects. It handles multi-trial runs, assertion evaluation, and CI/CD integration.

Install: `npm install -g promptfoo` (CLI) or `npm install promptfoo` (SDK).

### YAML Configuration Schema

`promptfooconfig.yaml` is the canonical eval definition file:

```yaml
# promptfooconfig.yaml
description: "TypeScript agent coding eval"

providers:
  - id: anthropic:claude-agent-sdk
    config:
      model: claude-sonnet-5-5
      working_dir: ./test-workspace
      append_allowed_tools: ["Write", "Edit", "Bash", "Read", "Glob"]
      max_turns: 20

prompts:
  - "{{task}}"

tests:
  - vars:
      task: "Fix the unicode bug in auth/login.ts"
    assert:
      - type: llm-rubric
        value: "The fix correctly handles unicode in email addresses without breaking ASCII paths"
        threshold: 0.8
      - type: javascript
        value: "output.includes('normalize') || output.includes('unicode')"
      - type: cost
        threshold: 0.30   # USD per eval run
      - type: latency
        threshold: 45000  # ms

  - vars:
      task: "Add retry logic to src/api-client.ts"
    assert:
      - type: llm-rubric
        value: "Retry logic uses exponential backoff and handles transient errors only"
        threshold: 0.8
      - type: trajectory:tool-used
        value: Edit
      - type: trajectory:tool-sequence
        value:
          - Read
          - Edit
```

Run with: `promptfoo eval`

### TypeScript Provider Configuration

Promptfoo's TypeScript providers let you wrap a custom agent and run it as a first-class eval target:

```ts
// providers/my-agent-provider.ts
import type { ApiProvider, ProviderResponse } from 'promptfoo';

export default class MyAgentProvider implements ApiProvider {
  id(): string {
    return 'my-agent-provider';
  }

  async callApi(prompt: string): Promise<ProviderResponse> {
    const result = await runMyAgent(prompt);
    return {
      output: result.finalOutput,
      // Optional metadata for cost/latency tracking
      tokenUsage: {
        total: result.totalTokens,
        prompt: result.promptTokens,
        completion: result.completionTokens,
      },
    };
  }
}
```

Reference the custom provider in config:

```yaml
providers:
  - id: "file://providers/my-agent-provider.ts"
    config:
      # Provider-specific config is passed to the constructor
      workingDir: ./test-workspace
      maxTurns: 20
```

### Eval Result Types and Assertions

Promptfoo assertion types used in TypeScript eval configs:

| Assertion type | When to use | Example value |
|---|---|---|
| `llm-rubric` | Subjective quality checks | `"Code is idiomatic TypeScript"` |
| `javascript` | Deterministic output checks (code grader) | `"output.includes('async')"` |
| `cost` | Budget gate per eval run (USD) | `0.25` |
| `latency` | Timing gate (milliseconds) | `30000` |
| `trajectory:tool-used` | Agent used a required tool | `"Edit"` |
| `trajectory:tool-sequence` | Agent called tools in order | `["Read", "Edit"]` |
| `trajectory:step-count` | Agent called a command N+ times | `{ type: "command", pattern: "tsc*", min: 1 }` |
| `contains` | Output contains a literal string | `"implements"` |
| `regex` | Output matches a pattern | `"/retry.*backoff/i"` |

### CLI vs SDK Usage

**CLI** — preferred for CI/CD and one-off runs:

```bash
# Run all evals defined in promptfooconfig.yaml
promptfoo eval

# Run with specific test filter
promptfoo eval --filter-pattern "unicode"

# Run N trials per test case (non-determinism handling)
promptfoo eval --repeat 5

# Output formats for CI
promptfoo eval --output results.json
promptfoo eval --output results.csv

# Red-team run
promptfoo redteam run
```

**SDK** — preferred when orchestrating evals programmatically from TypeScript code:

```ts
import { evaluate, type EvaluateSummary } from 'promptfoo';

const summary: EvaluateSummary = await evaluate({
  providers: [
    {
      id: 'anthropic:claude-agent-sdk',
      config: { model: 'claude-sonnet-5-5', maxTurns: 20 },
    },
  ],
  prompts: ['Fix the following issue: {{task}}'],
  tests: [
    {
      vars: { task: 'The login form crashes on emoji input' },
      assert: [
        {
          type: 'llm-rubric',
          value: 'Fix correctly handles emoji without crashing',
          threshold: 0.8,
        },
      ],
    },
  ],
  // Run 5 trials per test for pass@k metrics
  repeat: 5,
});

console.log(`Pass rate: ${summary.stats.successes / summary.stats.total}`);
```

Use the SDK when:
- Embedding evals in a larger TypeScript build/test pipeline
- Dynamically generating test cases from a database or fixture files
- Aggregating results across multiple eval suites programmatically

Use the CLI when:
- Running standalone in CI/CD (`promptfoo eval` step in GitHub Actions)
- Iterating locally on YAML configs
- Using red-team features (`promptfoo redteam run`)

### CI/CD Integration

Promptfoo ships a dedicated GitHub Actions integration:

```yaml
# .github/workflows/evals.yml
name: Agent Evals

on:
  push:
    paths:
      - 'src/**'
      - 'promptfooconfig.yaml'

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install promptfoo
        run: npm install -g promptfoo
      - name: Run evals
        run: promptfoo eval --output results.json
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: results.json
```

For deployment gates, parse `results.json` and fail the job if pass rate drops below threshold. See [cicd-integration.md](cicd-integration.md) for the full gate pattern.

---

## Combining Vitest + Promptfoo

The two tools serve complementary roles:

| Role | Tool | When |
|---|---|---|
| Unit evals (single agent call, deterministic grader) | Vitest | Fast feedback during development |
| Suite orchestration (multi-trial, LLM grader, cost tracking) | Promptfoo YAML | Pre-merge, nightly CI, regression suite |
| Programmatic orchestration | Promptfoo SDK | Dynamic test generation, custom reporting |
| Red-teaming | Promptfoo CLI | Security-focused eval campaigns |

A typical workflow: develop and debug with Vitest (fast loop, IDE integration), promote validated evals to `promptfooconfig.yaml` for CI/CD execution with multi-trial runs.
