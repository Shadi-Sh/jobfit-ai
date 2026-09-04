# JobFit AI

## Project goal

JobFit AI is a small AI-enabled software service that compares a CV with a job description.

The user provides:
- CV text
- job description text

The service should:
1. extract relevant job requirements using a local LLM,
2. identify evidence for these requirements in the CV,
3. validate the structured AI output,
4. calculate a deterministic fit score,
5. store the analysis,
6. display the result in a simple user interface.

## Planned technology

- Python
- Pydantic
- FastAPI
- SQLite
- local LLM through an OpenAI-compatible API
- Docker
- pytest

## Development rules

- Keep the project small and simple.
- Work on one small task at a time.
- Do not add features outside the agreed scope.
- Do not perform large refactorings without explaining them first.
- Keep AI logic separate from deterministic business logic.
- Prefer clear and readable Python over clever solutions.
- Run relevant tests after code changes.
- Do not hard-code credentials, secrets, or machine-specific paths.
- Explain important architectural decisions.