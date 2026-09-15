import json

from pydantic import BaseModel, ValidationError

from app.llm import create_chat_completion
from app.models import MatchStatus, Requirement, RequirementMatch

_SYSTEM_PROMPT = (
    "You compare a candidate's CV against a numbered list of job requirements. "
    "For each requirement, decide whether the CV shows a match. "
    'Respond with ONLY a JSON object of the form '
    '{"matches": [{"requirement_index": <integer index from the requirement list>, '
    '"status": "match" | "missing" | "not_found", '
    '"cv_evidence": "<short quote from the CV>" or null, '
    '"explanation": "<short reason for the decision>"}]}. '
    'Use "match" when the CV clearly shows the requirement is met, '
    '"missing" when the CV shows the candidate lacks it, '
    'and "not_found" when the CV gives no information about it. '
    "Include exactly one entry per requirement, using its index exactly as given below. "
    "Do not include any explanation or text outside the JSON object."
)


class MatchingError(Exception):
    """Raised when the LLM output cannot be parsed into valid requirement matches."""


class _MatchResult(BaseModel):
    requirement_index: int
    status: MatchStatus
    cv_evidence: str | None = None
    explanation: str


class _MatchingResponse(BaseModel):
    matches: list[_MatchResult]


def _build_user_prompt(cv_text: str, requirements: list[Requirement]) -> str:
    requirement_lines = "\n".join(
        f"{index}: {requirement.name} ({requirement.importance.value})"
        for index, requirement in enumerate(requirements)
    )
    return f"Job requirements:\n{requirement_lines}\n\nCV:\n{cv_text}"


def match_cv_to_requirements(
    cv_text: str, requirements: list[Requirement]
) -> list[RequirementMatch]:
    """Ask the local LLM to evaluate each requirement against the CV."""
    if not requirements:
        return []

    response = create_chat_completion(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(cv_text, requirements)},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content

    try:
        data = json.loads(content)
    except json.JSONDecodeError as error:
        raise MatchingError(f"LLM did not return valid JSON: {content!r}") from error

    try:
        parsed = _MatchingResponse.model_validate(data)
    except ValidationError as error:
        raise MatchingError(f"LLM output failed validation: {error}") from error

    returned_indices = [result.requirement_index for result in parsed.matches]
    if len(returned_indices) != len(set(returned_indices)):
        raise MatchingError(
            f"LLM output contains duplicate requirement_index values: {returned_indices}"
        )

    expected_indices = set(range(len(requirements)))
    got_indices = set(returned_indices)
    if got_indices != expected_indices:
        raise MatchingError(
            "LLM output does not cover exactly the given requirement indices: "
            f"expected {sorted(expected_indices)}, got {sorted(got_indices)}"
        )

    results_by_index = {result.requirement_index: result for result in parsed.matches}

    return [
        RequirementMatch(
            requirement=requirement,
            status=results_by_index[index].status,
            cv_evidence=results_by_index[index].cv_evidence,
            explanation=results_by_index[index].explanation,
        )
        for index, requirement in enumerate(requirements)
    ]
