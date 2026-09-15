import logging
from unittest.mock import patch

from app.analysis import analyze_job_fit
from app.models import JobFitAnalysis, MatchStatus, Requirement, RequirementImportance, RequirementMatch

_REQUIREMENTS = [
    Requirement(name="Python", importance=RequirementImportance.REQUIRED),
    Requirement(name="Kubernetes", importance=RequirementImportance.PREFERRED),
]

_MATCHES = [
    RequirementMatch(
        requirement=_REQUIREMENTS[0],
        status=MatchStatus.MATCH,
        cv_evidence="5 years of Python",
        explanation="CV mentions Python experience",
    ),
    RequirementMatch(
        requirement=_REQUIREMENTS[1],
        status=MatchStatus.NOT_FOUND,
        cv_evidence=None,
        explanation="CV does not mention Kubernetes",
    ),
]


@patch("app.analysis.calculate_fit_score")
@patch("app.analysis.match_cv_to_requirements")
@patch("app.analysis.extract_requirements")
def test_analyze_job_fit_orchestrates_pipeline_in_order(
    mock_extract, mock_match, mock_score
):
    mock_extract.return_value = _REQUIREMENTS
    mock_match.return_value = _MATCHES
    mock_score.return_value = 60.0

    result = analyze_job_fit("Some CV text", "Some job description")

    mock_extract.assert_called_once_with("Some job description")
    mock_match.assert_called_once_with("Some CV text", _REQUIREMENTS)
    mock_score.assert_called_once_with(_MATCHES)

    assert isinstance(result, JobFitAnalysis)
    assert result.requirements == _REQUIREMENTS
    assert result.matches == _MATCHES
    assert result.fit_score == 60.0


@patch("app.analysis.calculate_fit_score")
@patch("app.analysis.match_cv_to_requirements")
@patch("app.analysis.extract_requirements")
def test_analyze_job_fit_handles_no_requirements(mock_extract, mock_match, mock_score):
    mock_extract.return_value = []
    mock_match.return_value = []
    mock_score.return_value = 0.0

    result = analyze_job_fit("Some CV text", "Some job description")

    mock_match.assert_called_once_with("Some CV text", [])
    mock_score.assert_called_once_with([])
    assert isinstance(result, JobFitAnalysis)
    assert result.requirements == []
    assert result.matches == []
    assert result.fit_score == 0.0


@patch("app.analysis.calculate_fit_score")
@patch("app.analysis.match_cv_to_requirements")
@patch("app.analysis.extract_requirements")
def test_analyze_job_fit_logs_stage_timings_without_leaking_content(
    mock_extract, mock_match, mock_score, caplog
):
    mock_extract.return_value = _REQUIREMENTS
    mock_match.return_value = _MATCHES
    mock_score.return_value = 60.0

    with caplog.at_level(logging.INFO, logger="app.analysis"):
        analyze_job_fit("Some secret CV text", "Some secret job description")

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "extraction_ms=" in message
    assert "matching_ms=" in message
    assert "scoring_ms=" in message
    assert "total_ms=" in message
    assert "Some secret CV text" not in message
    assert "Some secret job description" not in message
