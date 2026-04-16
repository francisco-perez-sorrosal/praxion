"""Minimal Pydantic + `instructor` retry-on-ValidationError template.

Pattern: feed the ValidationError message back into the next model call so the
model self-corrects. Cap retries; log and raise on exhaustion — never retry
indefinitely on a degenerate input.

Requires (at runtime, not at import):
  pip install instructor anthropic pydantic

This template is illustrative. Adapt model IDs to your project's pinned versions
(verify via the `external-api-docs` skill before shipping).
"""

from __future__ import annotations

MAX_RETRIES = 3
DEFAULT_MODEL = "claude-sonnet-4-x"  # replace with a pinned, verified model ID


def build_extraction_prompt(document: str) -> str:
    """The Pydantic model is the prompt — field names and docstrings travel
    to the model. Keep the user-instruction short; let the schema carry the
    contract."""
    return (
        "Extract the structured fields from the document below.\n"
        "<document>\n"
        f"{document}\n"
        "</document>"
    )


def run() -> None:
    """Illustrative entry point. Kept inside __main__ guard so this file is
    importable without runtime deps."""
    import instructor
    from anthropic import Anthropic
    from pydantic import BaseModel, Field

    class ExtractedFields(BaseModel):
        """Structured extraction target. Docstring and Field descriptions are
        passed to the model — write them for a reader (the model)."""

        title: str = Field(description="Document title, verbatim from the source.")
        summary: str = Field(description="One-sentence summary, <=40 words.")
        tags: list[str] = Field(description="3-5 lowercase topic tags.")

    client = instructor.from_anthropic(Anthropic())

    document = "Replace with the real document text."

    result = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=1024,
        max_retries=MAX_RETRIES,  # instructor handles the validation-retry loop
        response_model=ExtractedFields,
        messages=[{"role": "user", "content": build_extraction_prompt(document)}],
    )

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    run()
