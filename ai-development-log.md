## Episode 1 – Repository inspection and next-step planning

### Task
I asked Claude Code to inspect the current repository structure without changing any files and to propose the smallest sensible next implementation step.

### Agent contribution
Claude analyzed the existing Pydantic models, the empty test directory, the missing dependency declaration, and the absence of FastAPI, persistence, Docker, and local LLM integration. It proposed implementing a deterministic fit-score calculation together with isolated tests as the next step.

### Tools and permissions used
Claude was allowed to inspect the project files in the repository. No file modifications were requested in this step.

### Verification
I reviewed the proposed next step and checked whether it was consistent with the planned architecture and with the requirement to keep deterministic business logic separate from AI-based logic.

### Decision
I accepted the general proposal but decided to define the exact scoring rules myself before implementation.

### Benefit / limitation / risk
The agent helped identify a small and testable next step without unnecessarily expanding the scope. A potential risk was that the agent could otherwise define business rules implicitly, so the scoring logic was specified manually before implementation.


## Episode 2 – Deterministic fit-score implementation and testing

### Task
I asked Claude Code to implement a deterministic fit-score calculator and corresponding tests using the following scoring rules:

- required + match = 2 points
- preferred + match = 1 point
- missing/not_found = 0 points
- score = achieved points / maximum possible points * 100
- an empty list returns 0.0

Claude was instructed to keep the implementation simple, avoid changing the existing models, add only the required files, and run the tests after implementation.

### Agent contribution
Claude created `app/scoring.py` with a `calculate_fit_score()` function. The function assigns weights based on requirement importance, sums achieved points for matched requirements, calculates the maximum possible score, and returns the percentage.

Claude also created `tests/test_scoring.py` with four pytest cases covering:
- an empty input list,
- all required requirements matched,
- all requirements missing,
- a mixed case using both required and preferred requirements.

A minimal `requirements-dev.txt` containing pytest was also added.

### Tools and permissions used
Claude was allowed to read and modify files inside the project workspace and execute the pytest test suite.

### Verification
Claude ran the test suite after implementation. All four tests passed.

I also reviewed the changed files and confirmed that:
- the scoring logic follows the specified deterministic rules,
- `app/models.py` was not modified,
- the implementation remains separate from future AI-based logic,
- the mixed test correctly produces a score of 60%.

### Decision
I accepted the implementation.

### Benefit / limitation / risk
The agent implemented and tested a small unit of deterministic business logic quickly while respecting the requested scope.

A limitation identified during review is that `Requirement.importance` is currently represented as a free string. Unexpected values would therefore receive a weight of zero instead of being rejected during validation. This should be improved later, for example by introducing an enum for supported importance values.


## Episode 3 – Replacing free-text importance with an enum

### Task
I asked Claude Code to replace the free-text `Requirement.importance` field with a restricted enum containing only `required` and `preferred`.

The scoring rules were not supposed to change. Claude was also asked to update the existing tests if necessary and add a validation test showing that unsupported importance values are rejected.

### Agent contribution
Claude added a `RequirementImportance` enum to `app/models.py` with the values:

- `REQUIRED = "required"`
- `PREFERRED = "preferred"`

It changed `Requirement.importance` from `str` to `RequirementImportance`.

Claude also updated `app/scoring.py` so that the importance-weight lookup uses the enum members instead of raw string values.

The existing scoring tests were adapted to use the enum, and a new validation test was added to confirm that an unsupported value such as `"nice_to_have"` raises a Pydantic `ValidationError`.

### Tools and permissions used
Claude was allowed to read and modify project files inside the repository and execute the pytest test suite.

### Verification
Claude ran the full test suite after the changes.

All 5 tests passed.

I reviewed the changes and confirmed that:
- only `required` and `preferred` are now accepted as requirement importance values,
- the scoring rules themselves were not changed,
- unsupported importance values are rejected during validation instead of silently receiving zero points.

### Decision
I accepted the changes.

### Benefit / limitation / risk
The change improves input validation and makes the domain model more explicit and reliable.

Previously, arbitrary strings could be used as importance values, which could lead to incorrect scoring behavior without an obvious error. The enum prevents this class of invalid input.


## Episode 4 – Local LLM integration

### Task
I asked Claude Code to implement the smallest possible integration with a locally hosted language model through an OpenAI-compatible API.

The integration had to:
- read the inference base URL and model name from environment variables,
- use `python-dotenv` for local development,
- use the OpenAI Python client,
- provide a simple function for sending a text prompt and receiving a text response,
- handle an unavailable inference server with a clear exception,
- avoid adding FastAPI, SQLite, or JobFit-specific extraction logic.

### Agent contribution
Claude created `app/llm.py`.

The module loads environment variables from a local `.env` file and defines an `ask_llm(prompt)` function. The function creates an OpenAI-compatible client using the configured `LLM_BASE_URL` and `LLM_MODEL`, sends a user message to the local inference server, and returns the generated text.

Claude also introduced a custom `LLMUnavailableError` that is raised when the inference server cannot be reached.

A `requirements.txt` file was added containing the runtime dependencies `pydantic`, `openai`, and `python-dotenv`.

### Tools and permissions used
Claude was allowed to read and modify files inside the project workspace and execute Python commands and the existing pytest test suite.

### Verification
The failure path was tested by configuring an unreachable inference server. The application raised the expected `LLMUnavailableError` with a clear error message.

The complete existing test suite was also executed and all 5 tests passed, confirming that the scoring behavior was not affected.

A .env.example file was added to document the required LLM_BASE_URL and LLM_MODEL settings, while the actual .env file remained excluded from version control.

A successful end-to-end request against the local Ollama model was also tested.

Using the configured `LLM_BASE_URL` and `LLM_MODEL`, the application sent the prompt:

`Reply with exactly: JobFit works`

The local model returned:

`JobFit works`

This verified that the Python application can successfully communicate with the locally hosted model through the OpenAI-compatible API.

### Decision
I accepted the implementation.

### Benefit / limitation / risk
The integration creates a small abstraction between the application and the local inference server and keeps model configuration outside the application code.

At this stage, only the connection-failure case has been verified. A successful request against the actual local Ollama model still needs to be tested.


## Episode 5 – Structured job-requirement extraction

### Task
I asked Claude Code to implement the smallest possible structured-output extraction step for job requirements.

The function had to:
- accept a job description as plain text,
- use the locally hosted LLM,
- extract requirements with `name` and `importance`,
- validate the result using the existing Pydantic `Requirement` model,
- prefer structured JSON output instead of parsing free-form text,
- handle malformed or invalid model output clearly,
- remain separate from deterministic scoring logic.

CV matching, FastAPI, SQLite, UI, and Docker were explicitly kept out of scope.

### Agent contribution
Claude refactored `app/llm.py` by extracting the common LLM communication logic into a reusable `create_chat_completion()` function. The existing `ask_llm()` behavior was preserved.

Claude created `app/extraction.py` with:

`extract_requirements(job_description: str) -> list[Requirement]`

The function requests a JSON object containing a `requirements` list and uses the existing `Requirement` and `RequirementImportance` models for validation.

Claude also added an `ExtractionError` for two model-output failure cases:
- malformed JSON,
- structurally valid JSON that does not satisfy the Pydantic schema.

Infrastructure failures such as an unavailable inference server remain represented by `LLMUnavailableError`.

### Tools and permissions used
Claude was allowed to inspect and modify files inside the project workspace and execute the pytest test suite.

The extraction tests mock the LLM completion call, so no real network or model request is required during unit testing.

### Verification
Five new tests were added covering:
- successful extraction,
- malformed JSON,
- invalid requirement importance,
- missing `requirements` field,
- propagation of an unavailable-LLM error.

The full test suite was executed and all 10 tests passed.

I reviewed the separation between:
- LLM communication,
- extraction and validation,
- deterministic scoring.

A real integration test against the local Ollama model was also performed.

Using a sample Junior AI Consultant job description, the local model successfully returned structured requirements that were validated into Pydantic `Requirement` objects:

- Python — required
- Generative AI — required
- Docker — preferred
- Communication — required

This confirmed that the structured extraction pipeline works with the actual local inference server, not only with mocked responses.

### Decision
I accepted the implementation.

### Benefit / limitation / risk
The implementation converts nondeterministic LLM output into a validated application data structure before it is used by later business logic.

The use of Pydantic prevents malformed or unsupported requirement values from silently entering the application.

A current limitation is that the new extraction tests use mocked model responses. Therefore, the structured-output behavior still needs to be verified against the actual local Ollama model.


## Episode 6 – CV-to-requirement matching

### Task
I asked Claude Code to implement the smallest possible CV-to-requirement matching step.

The function had to:
- accept CV text and a list of existing `Requirement` objects,
- use the local LLM to evaluate each requirement against the CV,
- return existing `RequirementMatch` objects,
- use the existing `MatchStatus` enum,
- provide CV evidence and a short explanation,
- use structured JSON output,
- remain separate from deterministic scoring logic,
- handle malformed or invalid model output clearly,
- add focused tests without adding FastAPI, SQLite, UI, or Docker.

### Agent contribution
Claude created `app/matching.py` with:

`match_cv_to_requirements(cv_text, requirements) -> list[RequirementMatch]`

The function sends the CV and requirements to the local model using the existing OpenAI-compatible LLM helper.

The model returns structured JSON containing:
- requirement name,
- match status,
- CV evidence,
- explanation.

The response is validated before being converted into `RequirementMatch` objects.

Importantly, the original `Requirement` objects passed into the function are preserved. The model does not recreate or modify requirement importance or wording.

Claude also added a strict coverage check. The model response must contain exactly the same requirement names as the input. Missing, additional, or unknown requirements are rejected with `MatchingError`.

### Tools and permissions used
Claude was allowed to inspect and modify files in the project workspace and execute the pytest test suite.

The matching tests mock the LLM completion call, so they do not depend on a running inference server.

### Verification
Seven new tests were added covering:
- empty requirement input,
- successful matching,
- preservation of original Requirement objects,
- malformed JSON,
- invalid match status,
- missing requirements in the model response,
- unknown requirements in the model response,
- propagation of `LLMUnavailableError`.

The complete test suite was executed and all 17 tests passed.

A real integration test against the local Ollama model was performed.

The model correctly matched Python, Generative AI, and Communication as present in the CV.

For Docker, the CV explicitly stated that there was no professional experience. The model correctly classified this as `MISSING` rather than treating the occurrence of the word “Docker” as positive evidence.

This showed that the matching step considers semantic context and negation instead of relying on simple keyword matching.

### Decision
I accepted the implementation.

### Benefit / limitation / risk
The implementation keeps nondeterministic AI matching separate from deterministic scoring and validates the model response before it is used by later business logic.

The strict coverage check prevents incomplete or hallucinated model output from silently affecting the fit score.

A current limitation is that requirement names are used as identifiers. This assumes that requirement names are unique. If duplicate names become relevant later, a more explicit identifier should be introduced.

### Later observed failure and correction

During a real end-to-end test with the local Ollama model, the original name-based matching contract failed.

The matching implementation expected the model to return requirement names exactly as provided. However, the model changed labels such as:

`Docker`

to:

`Docker (preferred)`

Although the meaning was unchanged, the strict string comparison caused a `MatchingError`.

The issue was detected during a real browser-based integration test and was not caught by the mocked unit tests.

To correct this, the matching contract was changed from requirement names to stable integer indices. The model now returns a `requirement_index`, which is mapped back to the original validated `Requirement` object.

Additional tests were added for missing, duplicate, and out-of-range indices as well as correct mapping back to the original requirements.

After the correction, the full backend test suite passed with 44 tests.

## Episode 7 – Orchestrating the complete JobFit analysis workflow

### Task
I decided to introduce a dedicated workflow function that combines the existing JobFit processing steps.

The workflow should:
1. extract requirements from the job description,
2. match the CV against those requirements,
3. calculate the deterministic fit score,
4. return the complete result as a dedicated Pydantic model.

I chose a structured `JobFitAnalysis` model instead of returning a plain dictionary.

### Agent contribution
Claude added the public Pydantic model `JobFitAnalysis` with:
- `requirements: list[Requirement]`
- `matches: list[RequirementMatch]`
- `fit_score: float` constrained to 0–100

Claude also created `app/analysis.py` containing:

`analyze_job_fit(cv_text, job_description) -> JobFitAnalysis`

The function only coordinates the already existing components:

- `extract_requirements(job_description)`
- `match_cv_to_requirements(cv_text, requirements)`
- `calculate_fit_score(matches)`

The results are combined into one validated `JobFitAnalysis` object.

No new AI logic, scoring logic, persistence, API, UI, or deployment logic was added.

### Tools and permissions used
Claude was allowed to inspect and modify files in the project workspace and execute the pytest test suite.

The orchestration tests use mocks for extraction, matching, and scoring so the workflow can be tested independently of the local LLM.

### Verification
Two new tests were added.

The tests verify that:
- the extracted requirements are passed correctly to the matching step,
- the resulting matches are passed correctly to the scoring step,
- the final result is a valid `JobFitAnalysis`,
- empty requirement lists propagate correctly through the workflow.

The complete test suite was executed and all 19 tests passed.

### Decision
I accepted the implementation.

### Benefit / limitation / risk
The orchestrator provides one clear entry point for the complete JobFit analysis workflow while keeping extraction, matching, and scoring responsibilities separated.

This makes the workflow easier to reuse later from an API or user interface.

A current limitation is that the analysis result is still only held in memory. Persistence has not yet been implemented.


## Episode 8 – First SQLite persistence step

### Task
I decided to introduce persistence incrementally, starting only with storing and loading a reusable CV.

The persistence layer had to:
- use SQLite,
- store CV text,
- return a generated ID,
- retrieve a CV by ID,
- keep the database path externally configurable,
- avoid analysis persistence, update/delete operations, FastAPI, and UI for now,
- use isolated temporary databases during testing.

### Agent contribution
Claude created `app/database.py`.

The module defines a small SQLite persistence layer with:
- a configurable database path using the `DATABASE_PATH` environment variable,
- automatic creation of a `cv` table,
- `save_cv(cv_text: str) -> int`,
- `get_cv(cv_id: int) -> str | None`.

The `cv` table stores:
- an auto-generated integer ID,
- the CV text,
- an `updated_at` timestamp.

Each database operation opens and closes its own SQLite connection.

Claude also updated `.env.example` to document:

`DATABASE_PATH=./jobfit.db`

and updated `.gitignore` with:

`*.db`

to prevent local SQLite database files from being committed accidentally.

### Tools and permissions used
Claude was allowed to inspect and modify project files and execute the test suite.

The database tests use a temporary SQLite file through pytest's `tmp_path` and `monkeypatch`, so the actual local JobFit database is not modified during testing.

### Verification
Four new database tests were added.

The tests verify that:
- `save_cv()` returns an integer ID,
- successive CV records receive distinct IDs,
- stored CV text can be retrieved correctly,
- an unknown CV ID returns `None`.

The complete test suite was executed and all 23 tests passed.

`git status` was also checked to verify that no real `jobfit.db` file had been created in the repository during testing.

### Decision
I accepted the implementation.

### Benefit / limitation / risk
The project now has its first persistent application data instead of keeping all information only in memory.

The database location is configurable and local database files are excluded from version control.

The current persistence layer is intentionally minimal. It only supports storing and retrieving CVs. Analysis history, CV updates, and deletion are not implemented yet.


---

## Environment note (not a numbered episode): sandbox remediation

This is a factual note about the development environment, not a development episode.

A later audit of the Claude Code session used for this project found that its local development setup did not run in a sandboxed or otherwise restricted environment: file reads/writes outside the repository (including listing `~/.ssh` and reading `~/.zshrc`), and outbound network access to an external host, all succeeded, and no project- or user-level Claude Code permission configuration existed to restrict this.

All development work recorded in the numbered episodes above, and the majority of this project's implementation, was carried out under that unrestricted setup. This note does not claim otherwise.

In response, a dedicated dev-only sandbox (`Dockerfile.dev`, `.devcontainer/devcontainer.json`, `scripts/create_dev_sandbox_workspace.sh`) was added to the repository for remaining and future development, bind-mounting only a secret-free copy of the project workspace, as a non-root user, with all Linux capabilities dropped and no other host paths exposed. See the README's "AI agent harness and sandboxing" section for the full audit findings, what the new sandbox does and does not enforce, and the verification performed against a running instance of it.