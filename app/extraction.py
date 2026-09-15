import json

from pydantic import BaseModel, ValidationError

from app.llm import create_chat_completion
from app.models import Requirement

_SYSTEM_PROMPT = (
    "You extract job requirements from a job description. "
    'Respond with ONLY a JSON object of the form '
    '{"requirements": [{"name": "<short requirement name>", "importance": "required" | "preferred"}]}. '
    'Use "required" for must-have requirements and "preferred" for nice-to-have ones. '
    "Do not include any explanation or text outside the JSON object."
)


class ExtractionError(Exception):
    """Raised when the LLM output cannot be parsed into valid requirements."""


class _ExtractedRequirements(BaseModel):
    requirements: list[Requirement]


def extract_requirements(job_description: str) -> list[Requirement]:
    """Ask the local LLM to extract structured requirements from a job description."""
    response = create_chat_completion(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
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
