# Python Context -- llm-prompt-engineering

Python-specific call shapes, retry loops, and pytest patterns for prompts that reach a production LLM. Load alongside the generic [llm-prompt-engineering](../SKILL.md) skill.

Back to: [../SKILL.md](../SKILL.md)

## SDK Versions Targeted

<!-- last-verified: 2026-04-16 -->

| Library | Version | Role |
|---------|---------|------|
| `anthropic` | 0.84.x | Anthropic Messages API client |
| `openai` | 1.x | OpenAI client (chat.completions, Responses API) |
| `instructor` | 1.14.x | Multi-provider Pydantic-validated structured output + retry loop |
| `pydantic` | 2.x | Validation, `Field(description=...)`, `ValidationError` |
| `pytest` | 8.x | Test runner; `pytest-asyncio` for async providers |

Python 3.13 syntax throughout. Type annotations required -- the Pydantic model is the prompt, so the annotations travel to the model too.

**Version drift.** Always verify current signatures via the [`external-api-docs`](../../external-api-docs/SKILL.md) skill (`chub_search` / `chub_get`) before shipping -- SDK method shapes move quarterly.

## `instructor` + Pydantic Retry Loop (Authoritative)

The dominant 2026 pattern for typed extraction in Python. `instructor` wraps any supported provider (Anthropic, OpenAI, Gemini, Mistral, Bedrock, open-weights via OpenAI-compatible servers), adds `response_model=<BaseModel>`, and runs a bounded retry-on-`ValidationError` loop. The validation error message is fed back into the next attempt so the model self-corrects.

See [`../assets/pydantic-retry-template.py`](../assets/pydantic-retry-template.py) for the minimal runnable template. The pattern in production looks like:

```python
from __future__ import annotations

import instructor
from anthropic import Anthropic
from pydantic import BaseModel, Field, ValidationError

MAX_RETRIES = 3  # cap to avoid token blow-up on degenerate input
MODEL = "claude-sonnet-4-x"  # pinned via external-api-docs, not hard-coded below


class ExtractedFields(BaseModel):
    """One-line doc for the *model*, not a human reader.

    `instructor` serializes this into the tool schema; `Field(description=...)`
    text is visible to the model and shapes output quality.
    """

    title: str = Field(description="Document title, verbatim from the source.")
    summary: str = Field(description="One-sentence summary, <=40 words.")
    tags: list[str] = Field(description="3-5 lowercase topic tags.")


def extract(document: str) -> ExtractedFields:
    client = instructor.from_anthropic(Anthropic())
    return client.messages.create(
        model=MODEL,
        max_tokens=1024,
        max_retries=MAX_RETRIES,
        response_model=ExtractedFields,
        messages=[{"role": "user", "content": _build_prompt(document)}],
    )


def _build_prompt(document: str) -> str:
    return (
        "Extract the structured fields from the document below.\n"
        "<document>\n"
        f"{document}\n"
        "</document>"
    )
```

### Retry tuning

- **2-3 retries is the sweet spot.** Degenerate inputs (truncated text, mojibake, adversarial content) will never parse -- retrying indefinitely drains the token budget. Log and raise on exhaustion.
- **Surface the last `ValidationError`.** When retries are exhausted, `instructor` raises `instructor.exceptions.InstructorRetryException` wrapping the final `ValidationError`. Re-raise with context so production logs point to the failing field, not just "extraction failed".
- **Bound `max_tokens`.** Set per-response limits commensurate with the schema size. A 3-field extraction rarely needs more than 512 tokens; oversizing invites runaway output that forces another round trip.

### Provider switching with one line

`instructor.from_openai(OpenAI())`, `instructor.from_gemini(...)`, and `instructor.from_litellm(...)` produce the same interface. Keep provider selection behind a factory so the Pydantic models and retry policy are provider-agnostic.

## Anthropic SDK Call Shape

When you need lower-level control than `instructor` provides -- custom system prompts, fine-grained tool routing, extended thinking parameters -- call the SDK directly. Structured output on Anthropic goes through tool-use, not a `response_format` equivalent.

```python
from anthropic import Anthropic
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

client = Anthropic()


class Classification(BaseModel):
    label: str = Field(description="One of: bug, feature, question.")
    confidence: float = Field(ge=0.0, le=1.0)


_adapter = TypeAdapter(Classification)

response = client.messages.create(
    model="claude-sonnet-4-x",
    max_tokens=256,
    system="You classify user messages. Call the `classify` tool exactly once.",
    tools=[
        {
            "name": "classify",
            "description": "Record the classification for the user message.",
            "input_schema": Classification.model_json_schema(),
        }
    ],
    tool_choice={"type": "tool", "name": "classify"},
    messages=[{"role": "user", "content": "The login button throws 500 on Safari."}],
)

# Validate at the boundary -- do not trust strict mode alone.
tool_block = next(b for b in response.content if b.type == "tool_use")
try:
    result = _adapter.validate_python(tool_block.input)
except ValidationError:
    raise  # handle upstream; log the failing payload
```

### Call-shape gotchas

- **Anthropic SDK silently rewrites schema constraints.** `minimum`, `maximum`, `minLength`, `pattern` get moved into the description and enforced post-generation, not as decoding constraints. Validate with Pydantic at the boundary regardless.
- **Tool-use adds ~313-346 tokens of system overhead.** Material at scale. If you need 50 concurrent classifications per second, benchmark before concluding tool-based structured output is "free".
- **First request pays grammar compilation latency.** Compiled grammars are cached ~24h. Don't measure steady-state cost from a cold start.
- **Prompt caching** on the Anthropic provider requires 1024-token blocks on Opus/Sonnet (2048 on Haiku). Under-threshold `cache_control` markers silently no-op. See the [`claude-ecosystem`](../../claude-ecosystem/SKILL.md) skill for the full treatment.

## OpenAI SDK Call Shape

OpenAI ships two structured-output modes. Prefer the second.

### JSON mode (legacy-ish -- avoid for new builds)

```python
from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-5",
    response_format={"type": "json_object"},
    messages=[
        {
            "role": "system",
            "content": "Return a JSON object with keys: label (string), confidence (number).",
        },
        {"role": "user", "content": "The login button throws 500."},
    ],
)
```

JSON mode constrains output to valid JSON but enforces no schema. The model still hallucinates field names, omits keys, or emits extra properties. **Validate with Pydantic anyway.** For anything beyond a prototype, use the schema-backed mode below.

### Structured Outputs (`json_schema` strict, default)

```python
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

client = OpenAI()


class Classification(BaseModel):
    label: str = Field(description="One of: bug, feature, question.")
    confidence: float = Field(ge=0.0, le=1.0)


response = client.chat.completions.parse(
    model="gpt-5",
    response_format=Classification,  # SDK auto-builds json_schema with strict=True
    messages=[
        {"role": "system", "content": "Classify the user message."},
        {"role": "user", "content": "Please add dark mode."},
    ],
)

parsed: Classification = response.choices[0].message.parsed
```

Equivalently, the manual shape:

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "Classification",
        "schema": Classification.model_json_schema(),
        "strict": True,
    },
}
```

### Strict-mode gotchas

- **`additionalProperties: false` is mandatory.** Every property must also be in `required`. Omitting either produces empty or malformed output on some model versions -- no error raised. Pydantic's `model_json_schema()` does **not** set `additionalProperties: false` by default; patch the schema or use the SDK's `parse()` helper which does it for you.
- **Unions and optionals require care.** `str | None` in Pydantic lowers to `{"anyOf": [...]}`; strict mode accepts this but some model versions still drop the null branch. Test the unhappy path explicitly.
- **Reasoning models cost more per structured call.** GPT-5 at `reasoning_effort="high"` can use ~23x the tokens of `minimal` for ~5% accuracy lift. Profile before bumping effort on a schema-constrained call.

## pytest Integration

Single-prompt tests live next to the code that builds the prompt. For multi-turn trajectory evals, defer to [`agent-evals`](../../agent-evals/SKILL.md).

### Parametrized assertions on prompt output

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from my_package.classifier import Classification, classify_message


CASES: list[tuple[str, str]] = [
    ("The login button throws 500 on Safari 17.", "bug"),
    ("Please add dark mode to the settings panel.", "feature"),
    ("How do I invite teammates?", "question"),
]


@pytest.mark.parametrize("message, expected_label", CASES)
def test_classifier_label(message: str, expected_label: str) -> None:
    result = classify_message(message)
    assert isinstance(result, Classification)
    assert result.label == expected_label
    assert 0.0 <= result.confidence <= 1.0
```

### Snapshot fixtures for structured output

For prompts that produce stable, multi-field output (summarization, extraction), pin the *shape* via schema assertion and the *content* via a sparse snapshot, not exact-match.

```python
import pytest
from syrupy.assertion import SnapshotAssertion  # or use pytest-snapshot


def test_extraction_shape(snapshot: SnapshotAssertion) -> None:
    result = extract("Sample document about Python 3.13 release notes.")
    # Schema shape -- deterministic.
    assert set(result.model_dump().keys()) == {"title", "summary", "tags"}
    assert len(result.tags) in range(3, 6)
    # Sparse content snapshot -- update deliberately.
    assert result.model_dump(include={"title"}) == snapshot
```

### Flaky-model handling pattern

Models drift across backend revisions even at `temperature=0`. The test suite must distinguish **soft fails** (model output varied within spec) from **hard fails** (schema violation, contract broken).

```python
import pytest
from pydantic import ValidationError


@pytest.mark.parametrize("attempt", range(3))  # pass@3
def test_extraction_semantic_soft_fail(attempt: int) -> None:
    """Retry up to 3x on semantic drift; one pass is sufficient."""
    try:
        result = extract(DOCUMENT)
    except ValidationError:
        pytest.fail("schema violation -- hard fail, do not retry")
    assert "python" in result.summary.lower()


def test_extraction_schema_hard_fail() -> None:
    """Schema violations must never retry -- they indicate prompt regression."""
    # If the model returns malformed data, ValidationError bubbles up and the
    # test fails deterministically. Do not wrap in try/except that swallows it.
    result = extract(DOCUMENT)
    assert result  # model_validate ran; structure is guaranteed
```

**Rule.** Retry on soft fail (semantic drift). Fail hard on schema violation. A schema violation means the prompt regressed or the SDK changed -- that is a real bug and should page, not retry.

### DeepEval integration (optional, Python-centric)

`deepeval` provides pytest-style metric assertions for prompt outputs:

```python
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase


def test_summary_relevance() -> None:
    result = extract(DOCUMENT)
    test_case = LLMTestCase(
        input=DOCUMENT,
        actual_output=result.summary,
    )
    assert_test(test_case, [AnswerRelevancyMetric(threshold=0.7)])
```

Prefer deterministic assertions (schema conformance, contains/not-contains, regex) when the output shape allows. LLM-judge metrics like `AnswerRelevancyMetric` should be a last resort, used only where deterministic assertions cannot express the behavior. See the [`agent-evals`](../../agent-evals/SKILL.md) skill for judge design and bias mitigations.

## Version Drift Checkpoint

Before shipping any code against a pinned SDK version, run the [`external-api-docs`](../../external-api-docs/SKILL.md) skill -- `chub_search` for the library, `chub_get` for the specific reference -- and compare the documented call shape against what this file describes. SDK method signatures move quarterly; this context file is a starting point, not a contract.
