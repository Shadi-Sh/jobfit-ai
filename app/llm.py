import os

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI
from openai.types.chat import ChatCompletion

load_dotenv()

_DEFAULT_TIMEOUT_SECONDS = 30.0


class LLMUnavailableError(Exception):
    """Raised when the configured LLM inference server cannot be reached."""


class LLMTimeoutError(Exception):
    """Raised when the LLM inference server does not respond within the configured timeout."""


def _get_timeout_seconds() -> float:
    return float(os.environ.get("LLM_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS))


def create_chat_completion(messages: list[dict], **kwargs) -> ChatCompletion:
    """Send a chat request to the configured OpenAI-compatible server.

    Shared by any AI-logic module that needs to talk to the LLM, so the
    connection setup and error handling live in one place.
    """
    base_url = os.environ["LLM_BASE_URL"]
    model = os.environ["LLM_MODEL"]
    timeout_seconds = _get_timeout_seconds()

    reasoning_effort = os.environ.get("LLM_REASONING_EFFORT")
    if reasoning_effort and "reasoning_effort" not in kwargs:
        kwargs["reasoning_effort"] = reasoning_effort

    client = OpenAI(base_url=base_url, api_key="not-needed", timeout=timeout_seconds)

    try:
        return client.chat.completions.create(model=model, messages=messages, **kwargs)
    # APITimeoutError is a subclass of APIConnectionError, so it must be caught first.
    except APITimeoutError as error:
        raise LLMTimeoutError(
            f"LLM inference server at {base_url} did not respond within {timeout_seconds} seconds"
        ) from error
    except APIConnectionError as error:
        raise LLMUnavailableError(
            f"Could not reach the LLM inference server at {base_url}"
        ) from error


def ask_llm(prompt: str) -> str:
    response = create_chat_completion([{"role": "user", "content": prompt}])
    return response.choices[0].message.content
