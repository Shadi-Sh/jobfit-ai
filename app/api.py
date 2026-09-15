import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from app.analysis import analyze_job_fit
from app.database import DatabaseError, get_analysis, get_cv, list_analyses, save_analysis, save_cv, update_cv
from app.extraction import ExtractionError
from app.llm import LLMTimeoutError, LLMUnavailableError
from app.matching import MatchingError
from app.models import AnalysisSummary, StoredAnalysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="JobFit AI",
    version="0.1.0",
    description=(
        "Compares a candidate's CV against a job description using a local LLM "
        "(Ollama, OpenAI-compatible API) for requirement extraction and CV matching, "
        "and a deterministic algorithm for the fit score. See README.md for the full "
        "architecture, configuration, and evaluation writeup."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(LLMUnavailableError)
async def handle_llm_unavailable(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The LLM inference server is currently unavailable."},
    )


@app.exception_handler(LLMTimeoutError)
async def handle_llm_timeout(request: Request, exc: LLMTimeoutError) -> JSONResponse:
    return JSONResponse(
        status_code=504,
        content={"detail": "The LLM inference server did not respond in time."},
    )


@app.exception_handler(ExtractionError)
async def handle_extraction_error(request: Request, exc: ExtractionError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "The AI returned an invalid response while extracting job requirements."},
    )


@app.exception_handler(MatchingError)
async def handle_matching_error(request: Request, exc: MatchingError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": "The AI returned an invalid response while matching the CV."},
    )


@app.exception_handler(DatabaseError)
async def handle_database_error(request: Request, exc: DatabaseError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )


class AnalyzeRequest(BaseModel):
    cv_id: int
    job_description: str

    @field_validator("job_description")
    @classmethod
    def job_description_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("job_description must not be empty or whitespace-only")
        return value


class CreateCvRequest(BaseModel):
    cv_text: str

    @field_validator("cv_text")
    @classmethod
    def cv_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cv_text must not be empty or whitespace-only")
        return value


class CreateCvResponse(BaseModel):
    cv_id: int


class CvResponse(BaseModel):
    cv_id: int
    cv_text: str


# Reused across endpoints so the OpenAI/Ollama- and SQLite-related failure modes
# (handled by the global exception handlers above) are visible in /docs, not just
# in this file. Documentation-only: does not change status codes or behavior.
_DB_ERROR_RESPONSES = {500: {"description": "Persisted data could not be read or written."}}
_LLM_ERROR_RESPONSES = {
    502: {"description": "The LLM returned malformed or unexpected output."},
    503: {"description": "The local inference server is unavailable."},
    504: {"description": "The local inference server did not respond in time."},
}


@app.get("/health", summary="Health check")
def health() -> dict:
    """Liveness check. Always returns 200 if the process is up; does not check Ollama or SQLite."""
    return {"status": "ok"}


@app.post("/cv", response_model=CreateCvResponse, summary="Create a CV", responses=_DB_ERROR_RESPONSES)
def create_cv(request: CreateCvRequest) -> CreateCvResponse:
    """Store a new CV and return its generated id. `cv_text` must not be blank."""
    cv_id = save_cv(request.cv_text)
    return CreateCvResponse(cv_id=cv_id)


@app.get(
    "/cv/{cv_id}",
    response_model=CvResponse,
    summary="Get a CV",
    responses={404: {"description": "No CV exists with this id."}, **_DB_ERROR_RESPONSES},
)
def get_cv_by_id(cv_id: int) -> CvResponse:
    """Return the current text of a previously saved CV."""
    cv_text = get_cv(cv_id)
    if cv_text is None:
        raise HTTPException(status_code=404, detail=f"CV {cv_id} not found")
    return CvResponse(cv_id=cv_id, cv_text=cv_text)


@app.put(
    "/cv/{cv_id}",
    response_model=CvResponse,
    summary="Update a CV",
    responses={404: {"description": "No CV exists with this id."}, **_DB_ERROR_RESPONSES},
)
def update_cv_by_id(cv_id: int, request: CreateCvRequest) -> CvResponse:
    """Replace an existing CV's text in place. Past analyses keep their original cv_text_snapshot unchanged."""
    updated = update_cv(cv_id, request.cv_text)
    if not updated:
        raise HTTPException(status_code=404, detail=f"CV {cv_id} not found")
    return CvResponse(cv_id=cv_id, cv_text=request.cv_text)


@app.post(
    "/analyze",
    response_model=StoredAnalysis,
    summary="Run a job-fit analysis",
    responses={404: {"description": "No CV exists with the given cv_id."}, **_LLM_ERROR_RESPONSES, **_DB_ERROR_RESPONSES},
)
def analyze(request: AnalyzeRequest) -> StoredAnalysis:
    """Extract requirements from the job description, match them against the CV, compute the deterministic fit score, and persist the result."""
    request_start = time.perf_counter()

    cv_text = get_cv(request.cv_id)
    if cv_text is None:
        raise HTTPException(status_code=404, detail=f"CV {request.cv_id} not found")

    result = analyze_job_fit(cv_text, request.job_description)

    analysis_id = save_analysis(
        cv_id=request.cv_id,
        cv_text_snapshot=cv_text,
        job_description=request.job_description,
        requirements=result.requirements,
        matches=result.matches,
        fit_score=result.fit_score,
    )

    stored = get_analysis(analysis_id)
    if stored is None:
        # Should be unreachable: save_analysis just committed this row successfully.
        raise HTTPException(
            status_code=500,
            detail="The analysis was saved but could not be retrieved. Please try again.",
        )

    total_request_ms = (time.perf_counter() - request_start) * 1000
    logger.info("POST /analyze request timing: total_request_ms=%.1f", total_request_ms)

    return stored


@app.get(
    "/analyses",
    response_model=list[AnalysisSummary],
    summary="List analysis history",
    responses=_DB_ERROR_RESPONSES,
)
def list_all_analyses() -> list[AnalysisSummary]:
    """Return a compact summary of every stored analysis, newest first."""
    return list_analyses()


@app.get(
    "/analyses/{analysis_id}",
    response_model=StoredAnalysis,
    summary="Get one stored analysis",
    responses={404: {"description": "No analysis exists with this id."}, **_DB_ERROR_RESPONSES},
)
def get_one_analysis(analysis_id: int) -> StoredAnalysis:
    """Return the full stored analysis, including the CV text snapshot at the time it was run."""
    stored = get_analysis(analysis_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return stored


# --- Serve the built React frontend (registered last so it never shadows an API route above) ---

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_API_PATH_PREFIXES = ("health", "cv", "analyze", "analyses", "assets")

if (_FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str) -> FileResponse:
    if full_path.split("/", 1)[0] in _API_PATH_PREFIXES:
        raise HTTPException(status_code=404, detail="Not found")

    index_path = _FRONTEND_DIST / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="Frontend build not found")

    candidate = _FRONTEND_DIST / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index_path)
