from enum import Enum

from pydantic import BaseModel, Field


class MatchStatus(str, Enum):
    MATCH = "match"
    MISSING = "missing"
    NOT_FOUND = "not_found"


class RequirementImportance(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class Requirement(BaseModel):
    name: str
    importance: RequirementImportance


class RequirementMatch(BaseModel):
    requirement: Requirement
    status: MatchStatus
    cv_evidence: str | None = None
    explanation: str


class JobFitReport(BaseModel):
    job_title: str
    matches: list[RequirementMatch]
    fit_score: float = Field(ge=0, le=100)
    recommendation: str


class JobFitAnalysis(BaseModel):
    requirements: list[Requirement]
    matches: list[RequirementMatch]
    fit_score: float = Field(ge=0, le=100)


class StoredAnalysis(BaseModel):
    id: int
    cv_id: int
    cv_text_snapshot: str
    job_description: str
    requirements: list[Requirement]
    matches: list[RequirementMatch]
    fit_score: float = Field(ge=0, le=100)
    created_at: str


class AnalysisSummary(BaseModel):
    id: int
    job_description: str
    fit_score: float = Field(ge=0, le=100)
    created_at: str