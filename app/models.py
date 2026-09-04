from enum import Enum

from pydantic import BaseModel, Field


class MatchStatus(str, Enum):
    MATCH = "match"
    MISSING = "missing"
    NOT_FOUND = "not_found"


class Requirement(BaseModel):
    name: str
    importance: str


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