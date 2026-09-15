from unittest.mock import patch

import pytest

from app.extraction import _SYSTEM_PROMPT as PRODUCTION_SYSTEM_PROMPT
from app.models import Requirement, RequirementImportance
from evaluation.prompts import GRANULARITY_ADDENDUM, PROMPT_VARIANTS
from evaluation.run_evaluation import evaluate_case, evaluate_extraction, main

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


# --- prompt definitions ---


def test_baseline_prompt_is_byte_identical_to_production():
    assert PROMPT_VARIANTS["baseline"] == PRODUCTION_SYSTEM_PROMPT


def test_granularity_prompt_is_baseline_plus_addendum_only():
    assert PROMPT_VARIANTS["granularity"] == f"{PRODUCTION_SYSTEM_PROMPT} {GRANULARITY_ADDENDUM}"
    assert PROMPT_VARIANTS["granularity"].startswith(PRODUCTION_SYSTEM_PROMPT)


def test_granularity_prompt_differs_from_baseline():
    assert PROMPT_VARIANTS["granularity"] != PROMPT_VARIANTS["baseline"]


# --- evaluate_extraction prompt selection ---


@patch("evaluation.run_evaluation.extract_requirements_with_prompt")
@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_extraction_baseline_calls_production_function_only(mock_production, mock_variant):
    mock_production.return_value = [
        Requirement(name="Python", importance=RequirementImportance.REQUIRED),
        Requirement(name="Docker", importance=RequirementImportance.PREFERRED),
    ]

    evaluate_extraction(_SIMPLE_CASE, extraction_prompt="baseline")

    mock_production.assert_called_once_with(_SIMPLE_CASE["job_description"])
    mock_variant.assert_not_called()


@patch("evaluation.run_evaluation.extract_requirements_with_prompt")
@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_extraction_granularity_calls_variant_function_with_granularity_prompt(
    mock_production, mock_variant
):
    mock_variant.return_value = [
        Requirement(name="Python", importance=RequirementImportance.REQUIRED),
        Requirement(name="Docker", importance=RequirementImportance.PREFERRED),
    ]

    evaluate_extraction(_SIMPLE_CASE, extraction_prompt="granularity")

    mock_variant.assert_called_once_with(_SIMPLE_CASE["job_description"], PROMPT_VARIANTS["granularity"])
    mock_production.assert_not_called()


@patch("evaluation.run_evaluation.extract_requirements_with_prompt")
@patch("evaluation.run_evaluation.extract_requirements")
def test_evaluate_case_tags_record_with_extraction_prompt(mock_production, mock_variant):
    mock_variant.return_value = []
    with patch("evaluation.run_evaluation.match_cv_to_requirements", return_value=[]):
        record = evaluate_case(_SIMPLE_CASE, run_number=1, extraction_prompt="granularity")

    assert record["extraction_prompt"] == "granularity"


# --- CLI wiring ---


@patch("evaluation.run_evaluation.match_cv_to_requirements")
@patch("evaluation.run_evaluation.extract_requirements_with_prompt")
def test_main_extraction_prompt_flag_selects_granularity_variant(mock_variant, mock_match, tmp_path):
    import json as jsonlib

    cases_file = tmp_path / "cases.json"
    cases_file.write_text(jsonlib.dumps([_SIMPLE_CASE]))
    output_dir = tmp_path / "results"

    mock_variant.return_value = [
        Requirement(name="Python", importance=RequirementImportance.REQUIRED),
        Requirement(name="Docker", importance=RequirementImportance.PREFERRED),
    ]
    mock_match.return_value = []

    result = main(
        [
            "--runs",
            "1",
            "--cases-file",
            str(cases_file),
            "--output-dir",
            str(output_dir),
            "--extraction-prompt",
            "granularity",
        ]
    )

    mock_variant.assert_called_once_with(_SIMPLE_CASE["job_description"], PROMPT_VARIANTS["granularity"])
    assert result["records"][0]["extraction_prompt"] == "granularity"

    output_files = list(output_dir.glob("results_*.json"))
    written = jsonlib.loads(output_files[0].read_text())
    assert written["extraction_prompt"] == "granularity"


def test_main_rejects_unknown_extraction_prompt(tmp_path):
    cases_file = tmp_path / "cases.json"
    cases_file.write_text("[]")

    with pytest.raises(SystemExit):
        main(["--cases-file", str(cases_file), "--extraction-prompt", "not-a-real-variant"])


@patch("evaluation.run_evaluation.match_cv_to_requirements")
@patch("evaluation.run_evaluation.extract_requirements")
def test_main_defaults_to_baseline_extraction_prompt(mock_production, mock_match, tmp_path):
    import json as jsonlib

    cases_file = tmp_path / "cases.json"
    cases_file.write_text(jsonlib.dumps([_SIMPLE_CASE]))
    output_dir = tmp_path / "results"

    mock_production.return_value = []
    mock_match.return_value = []

    result = main(
        ["--runs", "1", "--cases-file", str(cases_file), "--output-dir", str(output_dir)]
    )

    assert result["records"][0]["extraction_prompt"] == "baseline"
    mock_production.assert_called_once()
