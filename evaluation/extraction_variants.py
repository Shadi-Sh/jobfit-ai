"""Evaluation-only extraction using alternate system prompts.

Mirrors app/extraction.py's request shape and validation exactly (same
create_chat_completion call, same JSON response_format, and the exact same
ExtractionError type and _ExtractedRequirements Pydantic model, reused
directly from app.extraction rather than redefined), so a prompt variant is
scored against precisely the same structured-output contract as production.
The only thing that varies here is the system prompt text itself.

app/extraction.py's own extract_requirements() is not modified or wrapped —
it is called directly, unmodified, whenever the "baseline" prompt is
selected (see evaluation/run_evaluation.py), so the baseline path has zero
risk of drifting from production behavior.
"""
import json

from pydantic import ValidationError

from app.extraction import ExtractionError, _ExtractedRequirements
from app.llm import create_chat_completion
from app.models import Requirement


def extract_requirements_with_prompt(job_description: str, system_prompt: str) -> list[Requirement]:
    """Same request/validation contract as app.extraction.extract_requirements,
    but with a caller-supplied system prompt instead of the production one."""
    response = create_chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": job_description},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content

    try:
        data = json.loads(content)
    except json.JSONDecodeError as error:
        raise ExtractionError(f"LLM did not return valid JSON: {content!r}") from error

    try:
        return _ExtractedRequirements.model_validate(data).requirements
    except ValidationError as error:
        raise ExtractionError(f"LLM output failed validation: {error}") from error
