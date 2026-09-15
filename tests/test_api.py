import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.database import DatabaseError, get_cv, save_analysis, save_cv
from app.extraction import ExtractionError
from app.llm import LLMTimeoutError, LLMUnavailableError
from app.matching import MatchingError
from app.models import JobFitAnalysis, MatchStatus, Requirement, RequirementImportance, RequirementMatch

client = TestClient(app)

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

_ANALYSIS_RESULT = JobFitAnalysis(requirements=_REQUIREMENTS, matches=_MATCHES, fit_score=60.0)


@pytest.fixture(autouse=True)
def temp_db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    return db_path


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_configured_frontend_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_allows_post_to_cv_endpoint():
    response = client.options(
        "/cv",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_cors_preflight_allows_put_to_cv_endpoint():
    response = client.options(
        "/cv/1",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_cors_rejects_other_origins():
    response = client.get("/health", headers={"Origin": "http://example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_create_cv_returns_200_and_generated_cv_id():
    response = client.post("/cv", json={"cv_text": "Experienced Python developer"})

    assert response.status_code == 200
    assert isinstance(response.json()["cv_id"], int)


def test_create_cv_persists_text_retrievable_via_get_cv():
    response = client.post("/cv", json={"cv_text": "Experienced Python developer"})

    cv_id = response.json()["cv_id"]
    assert get_cv(cv_id) == "Experienced Python developer"


def test_get_cv_by_id_returns_correct_cv():
    cv_id = save_cv("Experienced Python developer")

    response = client.get(f"/cv/{cv_id}")

    assert response.status_code == 200
    assert response.json() == {"cv_id": cv_id, "cv_text": "Experienced Python developer"}


def test_get_cv_by_id_with_unknown_id_returns_404():
    response = client.get("/cv/999")

    assert response.status_code == 404


def test_update_cv_by_id_updates_and_returns_the_cv():
    cv_id = save_cv("Original CV text")

    response = client.put(f"/cv/{cv_id}", json={"cv_text": "Updated CV text"})

    assert response.status_code == 200
    assert response.json() == {"cv_id": cv_id, "cv_text": "Updated CV text"}
    assert get_cv(cv_id) == "Updated CV text"


def test_update_cv_by_id_with_unknown_id_returns_404():
    response = client.put("/cv/999", json={"cv_text": "Updated CV text"})

    assert response.status_code == 404


def test_update_cv_by_id_rejects_whitespace_only_text():
    cv_id = save_cv("Original CV text")

    response = client.put(f"/cv/{cv_id}", json={"cv_text": "   \n\t  "})

    assert response.status_code == 422
    # The original text must be untouched by a rejected request.
    assert get_cv(cv_id) == "Original CV text"


@patch("app.api.analyze_job_fit")
def test_analyze_with_valid_cv_returns_200_and_persisted_result(mock_analyze):
    mock_analyze.return_value = _ANALYSIS_RESULT
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )

    assert response.status_code == 200

    mock_analyze.assert_called_once_with(
        "Experienced Python developer", "Looking for a Python developer"
    )

    body = response.json()
    assert isinstance(body["id"], int)
    assert body["cv_id"] == cv_id
    assert body["cv_text_snapshot"] == "Experienced Python developer"
    assert body["job_description"] == "Looking for a Python developer"
    assert body["fit_score"] == 60.0
    assert [r["name"] for r in body["requirements"]] == ["Python", "Kubernetes"]
    assert body["matches"][0]["status"] == "match"
    assert body["matches"][1]["status"] == "not_found"


@patch("app.api.analyze_job_fit")
def test_analyze_logs_total_request_timing_without_leaking_content(mock_analyze, caplog):
    mock_analyze.return_value = _ANALYSIS_RESULT
    cv_id = save_cv("Experienced Python developer")

    with caplog.at_level(logging.INFO, logger="app.api"):
        response = client.post(
            "/analyze",
            json={"cv_id": cv_id, "job_description": "Looking for a Python developer"},
        )

    assert response.status_code == 200

    timing_records = [r for r in caplog.records if "total_request_ms=" in r.getMessage()]
    assert len(timing_records) == 1
    message = timing_records[0].getMessage()
    assert "Experienced Python developer" not in message
    assert "Looking for a Python developer" not in message


@patch("app.api.analyze_job_fit")
def test_analyze_persists_analysis_retrievable_from_database(mock_analyze):
    mock_analyze.return_value = _ANALYSIS_RESULT
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )

    analysis_id = response.json()["id"]

    from app.database import get_analysis

    stored = get_analysis(analysis_id)
    assert stored is not None
    assert stored.fit_score == 60.0
    assert stored.job_description == "Looking for a Python developer"


@patch("app.api.analyze_job_fit")
def test_updating_cv_does_not_change_existing_analysis_snapshot(mock_analyze):
    mock_analyze.return_value = _ANALYSIS_RESULT
    cv_id = save_cv("Original CV text")

    analyze_response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )
    analysis_id = analyze_response.json()["id"]

    update_response = client.put(f"/cv/{cv_id}", json={"cv_text": "Updated CV text"})
    assert update_response.status_code == 200

    stored_analysis = client.get(f"/analyses/{analysis_id}")
    assert stored_analysis.status_code == 200
    assert stored_analysis.json()["cv_text_snapshot"] == "Original CV text"
    assert get_cv(cv_id) == "Updated CV text"


@patch("app.api.analyze_job_fit")
def test_analyze_with_unknown_cv_id_returns_404(mock_analyze):
    response = client.post(
        "/analyze", json={"cv_id": 999, "job_description": "Looking for a Python developer"}
    )

    assert response.status_code == 404
    mock_analyze.assert_not_called()


def _create_analysis(job_description: str, fit_score: float) -> int:
    cv_id = save_cv("Experienced Python developer")
    return save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Experienced Python developer",
        job_description=job_description,
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=fit_score,
    )


def test_list_analyses_returns_multiple_stored_analyses():
    first_id = _create_analysis("First job description", 50.0)
    second_id = _create_analysis("Second job description", 80.0)

    response = client.get("/analyses")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {first_id, second_id}


def test_list_analyses_orders_newest_first():
    first_id = _create_analysis("First job description", 50.0)
    second_id = _create_analysis("Second job description", 80.0)

    response = client.get("/analyses")

    ids_in_order = [item["id"] for item in response.json()]
    assert ids_in_order == [second_id, first_id]


def test_get_analysis_by_id_returns_full_analysis():
    analysis_id = _create_analysis("Looking for a Python developer", 66.7)

    response = client.get(f"/analyses/{analysis_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == analysis_id
    assert body["job_description"] == "Looking for a Python developer"
    assert body["cv_text_snapshot"] == "Experienced Python developer"
    assert body["fit_score"] == 66.7
    assert [r["name"] for r in body["requirements"]] == ["Python", "Kubernetes"]
    assert body["matches"][0]["status"] == "match"


def test_get_analysis_with_unknown_id_returns_404():
    response = client.get("/analyses/999")

    assert response.status_code == 404


@patch("app.api.analyze_job_fit")
def test_analyze_returns_503_when_llm_unavailable(mock_analyze):
    mock_analyze.side_effect = LLMUnavailableError("Could not reach the LLM inference server")
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )

    assert response.status_code == 503


@patch("app.api.analyze_job_fit")
def test_analyze_returns_504_when_llm_times_out(mock_analyze):
    mock_analyze.side_effect = LLMTimeoutError("LLM did not respond in time")
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )

    assert response.status_code == 504


@patch("app.api.analyze_job_fit")
def test_analyze_returns_502_when_extraction_fails(mock_analyze):
    mock_analyze.side_effect = ExtractionError("LLM did not return valid JSON")
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )

    assert response.status_code == 502


@patch("app.api.analyze_job_fit")
def test_analyze_returns_502_when_matching_fails(mock_analyze):
    mock_analyze.side_effect = MatchingError("LLM output does not cover the given requirements")
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )

    assert response.status_code == 502


@patch("app.api.save_cv")
def test_create_cv_returns_500_with_generic_message_on_database_error(mock_save_cv):
    mock_save_cv.side_effect = DatabaseError("Could not save the CV.")

    response = client.post("/cv", json={"cv_text": "Experienced Python developer"})

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "internal error" in detail.lower()
    # The generic message must not leak the underlying DatabaseError text or any path.
    assert "Could not save the CV" not in detail
    assert ".db" not in detail


@patch("app.api.get_cv")
def test_get_cv_by_id_returns_500_with_generic_message_on_database_error(mock_get_cv):
    mock_get_cv.side_effect = DatabaseError("Could not load the CV.")

    response = client.get("/cv/1")

    assert response.status_code == 500
    assert "Could not load the CV" not in response.json()["detail"]


def test_create_cv_rejects_empty_text():
    response = client.post("/cv", json={"cv_text": ""})

    assert response.status_code == 422


def test_create_cv_rejects_whitespace_only_text():
    response = client.post("/cv", json={"cv_text": "   \n\t  "})

    assert response.status_code == 422


def test_analyze_rejects_empty_job_description():
    cv_id = save_cv("Experienced Python developer")

    response = client.post("/analyze", json={"cv_id": cv_id, "job_description": ""})

    assert response.status_code == 422


def test_analyze_rejects_whitespace_only_job_description():
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "   \n\t  "}
    )

    assert response.status_code == 422


@patch("app.api.get_analysis")
@patch("app.api.analyze_job_fit")
def test_analyze_returns_500_when_analysis_missing_after_save(mock_analyze, mock_get_analysis):
    mock_analyze.return_value = _ANALYSIS_RESULT
    mock_get_analysis.return_value = None
    cv_id = save_cv("Experienced Python developer")

    response = client.post(
        "/analyze", json={"cv_id": cv_id, "job_description": "Looking for a Python developer"}
    )

    assert response.status_code == 500
