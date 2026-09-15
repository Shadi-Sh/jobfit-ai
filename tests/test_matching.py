import json
from unittest.mock import MagicMock, patch

import pytest

from app.llm import LLMUnavailableError
from app.matching import MatchingError, match_cv_to_requirements
from app.models import MatchStatus, Requirement, RequirementImportance


def _fake_completion(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = content
    return completion


_REQUIREMENTS = [
    Requirement(name="Python", importance=RequirementImportance.REQUIRED),
    Requirement(name="Kubernetes", importance=RequirementImportance.PREFERRED),
]


def test_match_cv_to_requirements_with_no_requirements_skips_llm_call():
    with patch("app.matching.create_chat_completion") as mock_create:
        result = match_cv_to_requirements("Some CV text", [])

    assert result == []
    mock_create.assert_not_called()


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_returns_validated_matches(mock_create):
    mock_create.return_value = _fake_completion(
        json.dumps(
            {
                "matches": [
                    {
                        "requirement_index": 0,
                        "status": "match",
                        "cv_evidence": "5 years of Python development",
                        "explanation": "CV explicitly mentions Python experience",
                    },
                    {
                        "requirement_index": 1,
                        "status": "not_found",
                        "cv_evidence": None,
                        "explanation": "CV does not mention Kubernetes",
                    },
                ]
            }
        )
    )

    matches = match_cv_to_requirements("Some CV text", _REQUIREMENTS)

    assert len(matches) == 2
    assert matches[0].requirement is _REQUIREMENTS[0]
    assert matches[0].status == MatchStatus.MATCH
    assert matches[0].cv_evidence == "5 years of Python development"
    assert matches[1].requirement is _REQUIREMENTS[1]
    assert matches[1].status == MatchStatus.NOT_FOUND
    assert matches[1].cv_evidence is None


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_maps_indices_back_to_original_requirements_even_if_names_differ(
    mock_create,
):
    # Regression test: a real Ollama run returned status/importance annotations baked into
    # names (e.g. "Docker (preferred)") instead of the exact input name. The contract no
    # longer relies on names at all, so mismatched or embellished names must not matter.
    requirements = [
        Requirement(name="Docker", importance=RequirementImportance.PREFERRED),
        Requirement(name="Python and generative AI", importance=RequirementImportance.REQUIRED),
        Requirement(name="communication skills", importance=RequirementImportance.REQUIRED),
    ]
    mock_create.return_value = _fake_completion(
        json.dumps(
            {
                "matches": [
                    {
                        "requirement_index": 2,
                        "status": "match",
                        "cv_evidence": "Led weekly stakeholder updates",
                        "explanation": "CV shows communication experience",
                    },
                    {
                        "requirement_index": 0,
                        "status": "missing",
                        "cv_evidence": None,
                        "explanation": "No Docker experience mentioned",
                    },
                    {
                        "requirement_index": 1,
                        "status": "match",
                        "cv_evidence": "Built GenAI pipelines in Python",
                        "explanation": "CV explicitly mentions Python and generative AI",
                    },
                ]
            }
        )
    )

    matches = match_cv_to_requirements("Some CV text", requirements)

    assert len(matches) == 3
    assert matches[0].requirement is requirements[0]
    assert matches[0].status == MatchStatus.MISSING
    assert matches[1].requirement is requirements[1]
    assert matches[1].status == MatchStatus.MATCH
    assert matches[2].requirement is requirements[2]
    assert matches[2].status == MatchStatus.MATCH


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_rejects_malformed_json(mock_create):
    mock_create.return_value = _fake_completion("this is not JSON")

    with pytest.raises(MatchingError):
        match_cv_to_requirements("Some CV text", _REQUIREMENTS)


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_rejects_invalid_status(mock_create):
    mock_create.return_value = _fake_completion(
        json.dumps(
            {
                "matches": [
                    {
                        "requirement_index": 0,
                        "status": "sort_of",
                        "cv_evidence": None,
                        "explanation": "unclear",
                    },
                    {
                        "requirement_index": 1,
                        "status": "not_found",
                        "cv_evidence": None,
                        "explanation": "unclear",
                    },
                ]
            }
        )
    )

    with pytest.raises(MatchingError):
        match_cv_to_requirements("Some CV text", _REQUIREMENTS)


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_rejects_missing_index(mock_create):
    mock_create.return_value = _fake_completion(
        json.dumps(
            {
                "matches": [
                    {
                        "requirement_index": 0,
                        "status": "match",
                        "cv_evidence": "Python",
                        "explanation": "matches",
                    }
                ]
            }
        )
    )

    with pytest.raises(MatchingError):
        match_cv_to_requirements("Some CV text", _REQUIREMENTS)


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_rejects_duplicate_index(mock_create):
    mock_create.return_value = _fake_completion(
        json.dumps(
            {
                "matches": [
                    {
                        "requirement_index": 0,
                        "status": "match",
                        "cv_evidence": "Python",
                        "explanation": "matches",
                    },
                    {
                        "requirement_index": 0,
                        "status": "not_found",
                        "cv_evidence": None,
                        "explanation": "duplicate index",
                    },
                ]
            }
        )
    )

    with pytest.raises(MatchingError):
        match_cv_to_requirements("Some CV text", _REQUIREMENTS)


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_rejects_out_of_range_index(mock_create):
    mock_create.return_value = _fake_completion(
        json.dumps(
            {
                "matches": [
                    {
                        "requirement_index": 0,
                        "status": "match",
                        "cv_evidence": "Python",
                        "explanation": "matches",
                    },
                    {
                        "requirement_index": 5,
                        "status": "not_found",
                        "cv_evidence": None,
                        "explanation": "out of range",
                    },
                ]
            }
        )
    )

    with pytest.raises(MatchingError):
        match_cv_to_requirements("Some CV text", _REQUIREMENTS)


@patch("app.matching.create_chat_completion")
def test_match_cv_to_requirements_propagates_unavailable_llm(mock_create):
    mock_create.side_effect = LLMUnavailableError("Could not reach the LLM inference server")

    with pytest.raises(LLMUnavailableError):
        match_cv_to_requirements("Some CV text", _REQUIREMENTS)
