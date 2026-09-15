import json
from unittest.mock import MagicMock, patch

import pytest

from app.extraction import ExtractionError, extract_requirements
from app.llm import LLMUnavailableError
from app.models import RequirementImportance


def _fake_completion(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = content
    return completion


@patch("app.extraction.create_chat_completion")
def test_extract_requirements_returns_validated_requirements(mock_create):
    mock_create.return_value = _fake_completion(
        json.dumps(
            {
                "requirements": [
                    {"name": "Python", "importance": "required"},
                    {"name": "Docker", "importance": "preferred"},
                ]
            }
        )
    )

    requirements = extract_requirements("Some job description")

    assert len(requirements) == 2
    assert requirements[0].name == "Python"
    assert requirements[0].importance == RequirementImportance.REQUIRED
    assert requirements[1].name == "Docker"
    assert requirements[1].importance == RequirementImportance.PREFERRED


@patch("app.extraction.create_chat_completion")
def test_extract_requirements_rejects_malformed_json(mock_create):
    mock_create.return_value = _fake_completion("this is not JSON")

    with pytest.raises(ExtractionError):
        extract_requirements("Some job description")


@patch("app.extraction.create_chat_completion")
def test_extract_requirements_rejects_invalid_importance(mock_create):
    mock_create.return_value = _fake_completion(
        json.dumps({"requirements": [{"name": "Python", "importance": "nice_to_have"}]})
    )

    with pytest.raises(ExtractionError):
        extract_requirements("Some job description")


@patch("app.extraction.create_chat_completion")
def test_extract_requirements_rejects_missing_requirements_key(mock_create):
    mock_create.return_value = _fake_completion(json.dumps({"foo": "bar"}))

    with pytest.raises(ExtractionError):
        extract_requirements("Some job description")


@patch("app.extraction.create_chat_completion")
def test_extract_requirements_propagates_unavailable_llm(mock_create):
    mock_create.side_effect = LLMUnavailableError("Could not reach the LLM inference server")

    with pytest.raises(LLMUnavailableError):
        extract_requirements("Some job description")
