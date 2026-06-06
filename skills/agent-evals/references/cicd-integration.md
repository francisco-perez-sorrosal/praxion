# CI/CD Integration

Patterns for integrating agent evaluations into CI/CD pipelines -- GitHub Actions workflows, deployment gates, regression tracking, and cost management. Reference material for the [Agent Evals](../SKILL.md) skill.

For general CI/CD pipeline design, GitHub Actions syntax, caching, and security hardening, see the `cicd` skill. This reference covers only eval-specific CI/CD patterns.

## Integration Patterns

### Eval-on-Commit

Trigger eval runs on changes that affect agent behavior:

```yaml
on:
  pull_request:
    paths:
      - "prompts/**"       # Prompt changes
      - "agent/**"         # Agent logic
      - "tools/**"         # Tool definitions
      - "config/models.*"  # Model configuration
      - "evals/**"         # Eval changes themselves
```

Eval the evals: changes to eval definitions should also trigger a run to verify the eval suite itself is not broken.

### PR-Level Reporting

Post eval results as PR comments for review:

- **Score breakdown**: per-metric scores with pass/fail indicators
- **Baseline comparison**: delta vs. main branch or last release
- **Regression highlights**: any metric that dropped below threshold
- **Cost summary**: total API cost for the eval run

Braintrust and Promptfoo provide this natively. For other frameworks, use a custom reporting step.

### Deployment Gates

Block deployment when evals degrade:

```yaml
- name: Check eval thresholds
  run: |
    python scripts/check_thresholds.py \
      --results results/eval_output.json \
      --min-pass-rate 0.85 \
      --max-cost-per-task 0.50 \
      --max-regression-delta 0.05
```

**Threshold strategy**:

- Regression suite: pass rate must stay >= baseline (zero tolerance for known-good behavior)
- Capability suite: track improvement trend (no hard gate, but flag significant drops)
- Cost metrics: alert on >2x expected cost per task

### Regression Tracking

Maintain historical baselines for trend monitoring:

```python
import json
from pathlib import Path

def check_regression(
    current_results: dict,
    baseline_path: str = "evals/baselines/latest.json",
    max_delta: float = 0.05,
) -> list[str]:
    """Check for regressions against stored baseline."""
    baseline = json.loads(Path(baseline_path).read_text())
    regressions = []

    for metric, current_value in current_results.items():
        baseline_value = baseline.get(metric, 0)
        delta = baseline_value - current_value

        if delta > max_delta:
            regressions.append(
                f"{metric}: {current_value:.3f} (baseline: {baseline_value:.3f}, "
                f"delta: -{delta:.3f})"
            )

    return regressions
```

## GitHub Actions Workflows

### DeepEval Workflow

Pytest-based, integrates with existing test infrastructure:

```yaml
name: Agent Evals (DeepEval)

on:
  pull_request:
    paths: ["prompts/**", "agent/**", "tools/**", "evals/**"]
  schedule:
    - cron: "0 2 * * *"  # Full suite nightly at 2am

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install dependencies
        run: pip install -e ".[eval]"

      - name: Run regression evals
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          deepeval test run tests/evals/regression/ \
            --verbose \
            --output-file results/regression.json

      - name: Run capability evals (nightly only)
        if: github.event_name == 'schedule'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          deepeval test run tests/evals/capability/ \
            --verbose \
            --output-file results/capability.json

      - name: Check thresholds
        run: python scripts/check_eval_thresholds.py --results results/

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-results
          path: results/
```

### Inspect AI Workflow

CLI-based with custom reporting:

```yaml
name: Agent Evals (Inspect AI)

on:
  pull_request:
    paths: ["prompts/**", "agent/**", "tools/**", "evals/**"]

jobs:
  eval:
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:dind
        options: --privileged

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install dependencies
        run: pip install inspect-ai

      - name: Run evals
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          inspect eval evals/coding_tasks.py \
            --model anthropic/claude-sonnet-4-6 \
            -T 3 \
            --log-dir results/

      - name: Parse results and check thresholds
        run: python scripts/parse_inspect_results.py --log-dir results/

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: inspect-results
          path: results/
```

### Promptfoo Workflow

Uses the dedicated GitHub Action with PR comments:

```yaml
name: Agent Evals (Promptfoo)

on:
  pull_request:
    paths: ["prompts/**", "agent/**", "tools/**", "evals/**"]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run evals
        uses: promptfoo/promptfoo-action@v1
        with:
          config: evals/promptfooconfig.yaml
          github-token: ${{ secrets.GITHUB_TOKEN }}
          comment-on-pr: true
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Cost Management

### Tiered Execution

Balance coverage with budget using execution tiers:

| Tier | Trigger | Scope | Trials | Cost |
| --- | --- | --- | --- | --- |
| **Smoke** | Every commit | 5-10 critical cases | 1 | $ |
| **PR** | Pull request | Regression suite (20-50 cases) | 3 | $$ |
| **Nightly** | Scheduled | Full suite (all cases) | 5 | $$$ |
| **Release** | Pre-release | Full suite + capability evals | 10 | $$$$ |

### Token Budget Tracking

Track and alert on eval costs:

```python
def track_eval_cost(results: list[dict]) -> dict:
    """Track token usage and cost across eval runs."""
    total_input_tokens = sum(r.get("input_tokens", 0) for r in results)
    total_output_tokens = sum(r.get("output_tokens", 0) for r in results)

    # Approximate costs (update with current pricing)
    cost = (total_input_tokens * 3.0 / 1_000_000) + (total_output_tokens * 15.0 / 1_000_000)

    return {
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(cost, 4),
        "cost_per_task": round(cost / len(results), 4) if results else 0,
    }
```

### Environment Strategy

Optimize eval speed and cost with environment choices:

- **Docker containers**: full isolation for tool-using agents (mandatory for file system access)
- **Temp directories**: lighter isolation when Docker is unavailable
- **VCR pattern**: record/replay external API calls for speed and reproducibility
- **Mock APIs**: deterministic responses for integration-heavy agents
- **Git checkpoints**: reset workspace to known state between trials

## Production Monitoring

### When to Monitor vs. When to Eval

| Stage | Tool | Timing | Purpose |
| --- | --- | --- | --- |
| **Development** | Eval suite | Every change | Catch regressions before merge |
| **Pre-launch** | Full eval + A/B | Before release | Validate against production traffic patterns |
| **Post-launch** | Monitoring | Continuous | Detect drift, surface unexpected failures |
| **Calibration** | Human review | Periodic | Validate automated scoring accuracy |

### Monitoring Signals

Watch for these indicators in production:

- **Task completion rate drop**: agent succeeding less often than baseline
- **Cost spike**: agent consuming significantly more tokens than expected
- **Latency increase**: response times climbing (model changes, tool failures)
- **User feedback shift**: thumbs-down or escalation rate changes
- **Distribution drift**: input patterns changing from what evals cover

### Observability Tools

Brief pointers -- production monitoring is a separate concern:

- **Langfuse**: open-source LLM observability, tracing, scoring
- **Datadog LLM Observability**: enterprise monitoring with LLM-specific dashboards
- **Braintrust**: combined eval + monitoring platform
- **Custom pipelines**: structured logging + metrics collection (Prometheus, CloudWatch)

## Rollout Patterns

### Shadow Deployment

Run new agent version in parallel without serving results:

```text
User request --> Production agent (serves response)
             \-> Shadow agent (logs output for eval comparison)
```

Compare shadow outputs against production using offline eval suite. Validate before switching traffic.

### Canary Rollout

Staged traffic with eval-gated progression:

1. **1% traffic** --> monitor for 24h, run eval suite on canary outputs
2. **10% traffic** --> if metrics hold, expand
3. **50% traffic** --> final validation
4. **100% traffic** --> full rollout

Gate each stage on eval metrics staying within acceptable delta of baseline.

### A/B Testing

For significant agent changes, validate user outcomes:

- Route 50/50 traffic between old and new agent versions
- Measure user-facing metrics (task completion, satisfaction, escalation rate)
- Run for statistically significant sample size
- Use eval suite results as supporting evidence alongside user metrics

## Eval Fixture Smoke Test

A lightweight pre-eval gate that validates fixture integrity before committing to a full (expensive) eval run. The smoke test runs on every commit that touches evaluation data or scoring code and completes in under 60 seconds. It is a gate **before** the eval loop starts — `EVAL_RESULTS.md` is written **after** a successful eval loop run.

This smoke test is the implementation of the **eval determinism contract** referenced in `rules/eval/eval-data-governance.md` Rule 4 and the dataset provenance requirement in Rule 3.

### What the Smoke Test Checks

**1. MANIFEST.json presence**

Every directory under `tasks/**` or `data/private/**` that contains scored examples must have a `MANIFEST.json` sibling. Missing MANIFEST files are caught here before they silently corrupt `dataset_sha` linkage in `EVAL_RESULTS.md`.

**2. MANIFEST.json schema validity**

Each `MANIFEST.json` must be valid JSON containing the four required fields (`sha256`, `version`, `source`, `split`). An invalid or incomplete manifest blocks the eval loop — better to fail fast than to record a run with broken provenance.

```python
REQUIRED_MANIFEST_FIELDS = {"sha256", "version", "source", "split"}

def validate_manifest(manifest_path: Path) -> list[str]:
    """Return list of validation errors, or empty list if valid."""
    errors = []
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{manifest_path}: invalid JSON — {exc}"]

    missing = REQUIRED_MANIFEST_FIELDS - set(manifest.keys())
    if missing:
        errors.append(f"{manifest_path}: missing required fields: {sorted(missing)}")
    return errors
```

**3. SHA-256 integrity check**

Compute the SHA-256 of the dataset files and compare against `MANIFEST.json sha256`. A mismatch means the dataset changed without a manifest update — which would corrupt the `dataset_sha` linkage in `EVAL_RESULTS.md`.

```python
import hashlib
from pathlib import Path

def compute_dataset_sha(data_dir: Path) -> str:
    """SHA-256 over all scored example files in a directory (sorted for determinism)."""
    h = hashlib.sha256()
    for path in sorted(data_dir.rglob("*.jsonl")) + sorted(data_dir.rglob("*.json")):
        if path.name == "MANIFEST.json":
            continue
        h.update(path.read_bytes())
    return h.hexdigest()
```

**4. evaluate.py importability**

Verify `evaluate.py` is importable before dispatching a full eval run. A broken import at CI time surfaces immediately rather than after minutes of setup.

```bash
python3 -c "import evaluate; print('evaluate.py importable: OK')"
```

### Determinism Contract

When `MANIFEST.json` contains `"deterministic": false`, the smoke test changes behavior:

| Condition | Threshold gate | Behavior |
| --- | --- | --- |
| `deterministic: true` (or field absent) | Enforced | Run fails if scored metric misses threshold |
| `deterministic: false` | Skipped | WARN emitted; eval proceeds; no threshold FAIL |

This contract is the mechanism referenced in `rules/eval/eval-data-governance.md` Rule 4. Non-deterministic evals produce meaningful results but must not gate on exact numbers. The WARN signals human attention without blocking the pipeline.

```python
def check_determinism_gate(manifest: dict, metric: float, threshold: float) -> str:
    """Return PASS, WARN, or FAIL per determinism contract."""
    if not manifest.get("deterministic", True):
        return f"WARN: deterministic=false — threshold gate skipped (metric={metric})"
    if metric >= threshold:
        return f"PASS: metric={metric} >= threshold={threshold}"
    return f"FAIL: metric={metric} < threshold={threshold}"
```

### CI Job Pattern

Trigger the smoke test on every commit touching evaluation inputs:

```yaml
name: Eval Fixture Smoke Test

on:
  push:
    paths:
      - "tasks/**"
      - "data/**"
      - "evaluate.py"
  pull_request:
    paths:
      - "tasks/**"
      - "data/**"
      - "evaluate.py"

jobs:
  eval-fixture-smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install dependencies
        run: pip install -e ".[eval]"

      - name: Run eval fixture smoke test
        run: python3 scripts/check_eval_fixtures.py

      - name: Verify evaluate.py is importable
        run: python3 -c "import evaluate; print('evaluate.py importable: OK')"
```

`check_eval_fixtures.py` is a managed-project artifact — each project implements it to scan its own `tasks/` and `data/private/` layout. The script performs checks 1–3 above and exits non-zero on any FAIL finding, non-zero-but-with-warn on WARN-only findings. The CI job pattern above is the template; adapt paths to match the project structure.

### Integration with EVAL_RESULTS.md

The smoke test controls whether the eval loop starts. The sequence is:

```
commit → smoke test → [PASS] → eval loop → EVAL_RESULTS.md written → EVAL_LOG.md row appended
                     → [FAIL] → eval loop blocked; EVAL_RESULTS.md not written
                     → [WARN] → eval loop proceeds; EVAL_RESULTS.md written; WARN noted
```

`EVAL_RESULTS.md` is written only after the eval loop completes. The `dataset_sha` field in `EVAL_RESULTS.md` must match the `sha256` in `MANIFEST.json` — the smoke test's integrity check ensures they are in sync before the run starts.

See `skills/agent-evals/references/run-ledger-schema.md` for the full `EVAL_RESULTS.md` schema (including `dataset_sha`) and `EVAL_LOG.md` column definitions. See `rules/eval/eval-data-governance.md` for the governance rules that this smoke test enforces. See `skills/agent-evals/references/data-governance.md` for the MANIFEST.json schema and held-out split design guidance.
