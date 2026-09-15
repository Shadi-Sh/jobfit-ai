import json
from unittest.mock import patch

import pytest

from app.extraction import ExtractionError
from app.llm import LLMTimeoutError, LLMUnavailableError
from app.matching import MatchingError
from app.models import MatchStatus, Requirement, RequirementImportance, RequirementMatch
from evaluation.run_evaluation import evaluate_case, evaluate_extraction, evaluate_matching, load_cases, main

_SIMPLE_CASE = {
    "case_id": "case_01",
    "category": "clear_case",
    "job_description": "Python is required. Docker is preferred.",
    "cv_text": "3 years of Python development.",
    "matching_applicable": True,
    "expected_requirements": [
        {"concept": "python", "canonical_name": "Python", "accepted_names": ["Python"], "importance": "required"},
        {"concept": "docker", "canonical_name": "Docker", "accepted_names": ["Docker"], "importance": "preferred"},
    ],
    "expected_matches": {"python": "match", "docker": "not_found"},
}

_NOT_APPLICABLE_CASE = {
    "case_id": "case_08",
    "category": "out_of_scope_non_job_input",
    "job_description": "Happy birthday! Have a wonderful day.",
    "cv_text": None,
    "matching_applicable": False,
    "expected_requirements": [],
    "expected_matches": None,
}

_NAME_TO_CONCEPT = {"Python": "python", "Docker": "docker"}


def _requirement_match(name, importance, status, evidence=None):
    return RequirementMatch(
        requirement=Requirement(name=name, importance=importance),
        status=status,
        cv_evidence=evidence,
        explanation="test",
    )


# --- load_cases ---


def test_load_cases_returns_exactly_ten_cases():
    cases = load_cases()
    assert len(cases) == 10


def test_load_cases_have_required_schema_fields():
    required_fields = {
        "case_id",
        "category",
        "job_description",
        "cv_text",
        "matching_applicable",
        "expected_requirements",
        "expected_matches",
    }
    for case in load_cases():
        assert required_fields.issubset(case.keys())
        for requirement in case["expected_requirements"]:
            assert {"concept", "canonical_name", "accepted_names", "importance"}.issubset(requirement.keys())


def test_load_cases_case_ids_are_unique():
    cases = load_cases()
    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids))


# --- evaluate_extraction ---


@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_extraction_success(mock_extract):
    mock_extract.return_value = [
        Requirement(name="Python", importance=RequirementImportance.REQUIRED),
        Requirement(name="Docker", importance=RequirementImportance.PREFERRED),
    ]
    result = evaluate_extraction(_SIMPLE_CASE)
    assert result["structured_valid"] is True
    assert result["correct"] is True
    assert result["failure_type"] is None
    assert isinstance(result["latency_ms"], float)


@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_extraction_handles_extraction_error(mock_extract):
    mock_extract.side_effect = ExtractionError("bad json")
    result = evaluate_extraction(_SIMPLE_CASE)
    assert result["structured_valid"] is False
    assert result["correct"] is False
    assert result["failure_type"] == "invalid_structured_output"


@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_extraction_handles_llm_timeout(mock_extract):
    mock_extract.side_effect = LLMTimeoutError("timed out")
    result = evaluate_extraction(_SIMPLE_CASE)
    assert result["structured_valid"] is None
    assert result["correct"] is None
    assert result["failure_type"] == "llm_timeout"


@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_extraction_handles_llm_unavailable(mock_extract):
    mock_extract.side_effect = LLMUnavailableError("unreachable")
    result = evaluate_extraction(_SIMPLE_CASE)
    assert result["structured_valid"] is None
    assert result["correct"] is None
    assert result["failure_type"] == "llm_unavailable"


@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_extraction_marks_incorrect_result_without_raising(mock_extract):
    mock_extract.return_value = [Requirement(name="Python", importance=RequirementImportance.REQUIRED)]
    result = evaluate_extraction(_SIMPLE_CASE)  # Docker missing
    assert result["structured_valid"] is True
    assert result["correct"] is False
    assert result["failure_type"] == "incorrect_result"


# --- evaluate_matching ---


def test_evaluate_matching_returns_none_when_not_applicable():
    with patch("evaluation.run_evaluation.match_cv_to_requirements") as mock_match:
        result = evaluate_matching(_NOT_APPLICABLE_CASE, {})
    assert result is None
    mock_match.assert_not_called()


@patch("evaluation.run_evaluation.match_cv_to_requirements")
def test_evaluate_matching_success(mock_match):
    mock_match.return_value = [
        _requirement_match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, "3 years of Python"),
        _requirement_match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND),
    ]
    result = evaluate_matching(_SIMPLE_CASE, _NAME_TO_CONCEPT)
    assert result["structured_valid"] is True
    assert result["correct"] is True
    assert result["evidence_consistent"] is True
    assert result["failure_type"] is None


@patch("evaluation.run_evaluation.match_cv_to_requirements")
def test_evaluate_matching_handles_matching_error(mock_match):
    mock_match.side_effect = MatchingError("bad output")
    result = evaluate_matching(_SIMPLE_CASE, _NAME_TO_CONCEPT)
    assert result["structured_valid"] is False
    assert result["correct"] is False
    assert result["failure_type"] == "invalid_structured_output"


@patch("evaluation.run_evaluation.match_cv_to_requirements")
def test_evaluate_matching_handles_llm_timeout(mock_match):
    mock_match.side_effect = LLMTimeoutError("timed out")
    result = evaluate_matching(_SIMPLE_CASE, _NAME_TO_CONCEPT)
    assert result["structured_valid"] is None
    assert result["correct"] is None
    assert result["failure_type"] == "llm_timeout"


@patch("evaluation.run_evaluation.match_cv_to_requirements")
def test_evaluate_matching_flags_evidence_inconsistency(mock_match):
    mock_match.return_value = [
        _requirement_match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, evidence=None),
        _requirement_match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND),
    ]
    result = evaluate_matching(_SIMPLE_CASE, _NAME_TO_CONCEPT)
    assert result["evidence_consistent"] is False


# --- evaluate_case ---


@patch("evaluation.run_evaluation.match_cv_to_requirements")
@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_case_combines_extraction_and_matching(mock_extract, mock_match):
    mock_extract.return_value = [
        Requirement(name="Python", importance=RequirementImportance.REQUIRED),
        Requirement(name="Docker", importance=RequirementImportance.PREFERRED),
    ]
    mock_match.return_value = [
        _requirement_match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, "evidence"),
        _requirement_match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND),
    ]
    record = evaluate_case(_SIMPLE_CASE, run_number=1)

    assert record["case_id"] == "case_01"
    assert record["run_number"] == 1
    assert record["extraction_correct"] is True
    assert record["matching_correct"] is True


@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_case_sets_matching_fields_to_none_when_not_applicable(mock_extract):
    mock_extract.return_value = []
    record = evaluate_case(_NOT_APPLICABLE_CASE, run_number=1)

    assert record["matching_structured_valid"] is None
    assert record["matching_correct"] is None
    assert record["matching_latency_ms"] is None
    assert record["matching_failure_type"] is None


# --- main() end-to-end, mocked ---


@patch("evaluation.run_evaluation.match_cv_to_requirements")
@patch("evaluation.run_evaluation.extract_requirements")
def test_main_continues_after_a_case_failure_and_writes_results(mock_extract, mock_match, tmp_path):
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps([_SIMPLE_CASE, _NOT_APPLICABLE_CASE]))
    output_dir = tmp_path / "results"

    def extract_side_effect(job_description):
        if job_description == _SIMPLE_CASE["job_description"]:
            raise ExtractionError("simulated failure")
        return []

    mock_extract.side_effect = extract_side_effect
    mock_match.return_value = [
        _requirement_match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, "evidence"),
        _requirement_match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND),
    ]

    result = main(
        [
            "--runs",
            "1",
            "--cases-file",
            str(cases_file),
            "--output-dir",
            str(output_dir),
        ]
    )

    # Both cases were processed despite the first one's extraction failure.
    assert len(result["records"]) == 2
    case_01_record = next(r for r in result["records"] if r["case_id"] == "case_01")
    assert case_01_record["extraction_failure_type"] == "invalid_structured_output"
    # Matching for case_01 is independent of the extraction failure and still ran.
    assert case_01_record["matching_correct"] is True

    output_files = list(output_dir.glob("results_*.json"))
    assert len(output_files) == 1
    written = json.loads(output_files[0].read_text())
    assert written["runs_per_case"] == 1
    assert len(written["records"]) == 2
    assert "summary" in written


@patch("evaluation.run_evaluation.match_cv_to_requirements")
@patch("evaluation.run_evaluation.extract_requirements")
def test_main_respects_runs_argument(mock_extract, mock_match, tmp_path):
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps([_SIMPLE_CASE]))
    output_dir = tmp_path / "results"

    mock_extract.return_value = [
        Requirement(name="Python", importance=RequirementImportance.REQUIRED),
        Requirement(name="Docker", importance=RequirementImportance.PREFERRED),
    ]
    mock_match.return_value = [
        _requirement_match("Python", RequirementImportance.REQUIRED, MatchStatus.MATCH, "evidence"),
        _requirement_match("Docker", RequirementImportance.PREFERRED, MatchStatus.NOT_FOUND),
    ]

    result = main(
        ["--runs", "3", "--cases-file", str(cases_file), "--output-dir", str(output_dir)]
    )

    assert len(result["records"]) == 3
    assert mock_extract.call_count == 3
