from unittest.mock import MagicMock, patch

import httpx2
import pytest
from openai import APIConnectionError, APITimeoutError

from app.llm import LLMTimeoutError, LLMUnavailableError, create_chat_completion

_FAKE_REQUEST = httpx2.Request("POST", "http://example.com")


@pytest.fixture(autouse=True)
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")


@patch("app.llm.OpenAI")
def test_create_chat_completion_translates_timeout_to_llm_timeout_error(mock_openai_cls):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=_FAKE_REQUEST)
    mock_openai_cls.return_value = mock_client

    with pytest.raises(LLMTimeoutError):
        create_chat_completion([{"role": "user", "content": "hi"}])


@patch("app.llm.OpenAI")
def test_create_chat_completion_translates_connection_error_to_llm_unavailable_error(
    mock_openai_cls,
):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APIConnectionError(request=_FAKE_REQUEST)
    mock_openai_cls.return_value = mock_client

    with pytest.raises(LLMUnavailableError):
        create_chat_completion([{"role": "user", "content": "hi"}])


@patch("app.llm.OpenAI")
def test_create_chat_completion_uses_default_timeout_when_env_var_not_set(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    create_chat_completion([{"role": "user", "content": "hi"}])

    _, kwargs = mock_openai_cls.call_args
    assert kwargs["timeout"] == 30.0


@patch("app.llm.OpenAI")
def test_create_chat_completion_uses_configured_timeout_env_var(mock_openai_cls, monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "5")
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    create_chat_completion([{"role": "user", "content": "hi"}])

    _, kwargs = mock_openai_cls.call_args
    assert kwargs["timeout"] == 5.0


@patch("app.llm.OpenAI")
def test_create_chat_completion_forwards_reasoning_effort_env_var(mock_openai_cls, monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    create_chat_completion([{"role": "user", "content": "hi"}])

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["reasoning_effort"] == "none"


@patch("app.llm.OpenAI")
def test_create_chat_completion_omits_reasoning_effort_when_env_var_unset(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    create_chat_completion([{"role": "user", "content": "hi"}])

    _, kwargs = mock_client.chat.completions.create.call_args
    assert "reasoning_effort" not in kwargs


@patch("app.llm.OpenAI")
def test_create_chat_completion_does_not_overwrite_caller_supplied_reasoning_effort(
    mock_openai_cls, monkeypatch
):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "none")
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    create_chat_completion(
        [{"role": "user", "content": "hi"}], reasoning_effort="high"
    )

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["reasoning_effort"] == "high"
