import sqlite3
from unittest.mock import MagicMock

import pytest

from app.database import DatabaseError, get_analysis, get_cv, list_analyses, save_analysis, save_cv, update_cv
from app.models import MatchStatus, Requirement, RequirementImportance, RequirementMatch

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


@pytest.fixture(autouse=True)
def temp_db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    return db_path


def test_save_cv_returns_generated_integer_id():
    cv_id = save_cv("Experienced Python developer")
    assert isinstance(cv_id, int)


def test_save_cv_ids_are_unique_and_increasing():
    first_id = save_cv("First CV")
    second_id = save_cv("Second CV")
    assert second_id > first_id


def test_get_cv_returns_stored_text():
    cv_id = save_cv("Experienced Python developer")
    assert get_cv(cv_id) == "Experienced Python developer"


def test_get_cv_returns_none_for_unknown_id():
    assert get_cv(999) is None


def test_update_cv_succeeds_and_persists_new_text():
    cv_id = save_cv("Original CV text")

    result = update_cv(cv_id, "Updated CV text")

    assert result is True
    assert get_cv(cv_id) == "Updated CV text"


def test_update_cv_of_unknown_id_returns_false():
    assert update_cv(999, "Some text") is False


def test_save_analysis_returns_generated_integer_id():
    cv_id = save_cv("Experienced Python developer")
    analysis_id = save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Experienced Python developer",
        job_description="Looking for a Python developer",
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=66.7,
    )
    assert isinstance(analysis_id, int)


def test_get_analysis_returns_equivalent_requirements_and_matches():
    cv_id = save_cv("Experienced Python developer")
    analysis_id = save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Experienced Python developer",
        job_description="Looking for a Python developer",
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=66.7,
    )

    stored = get_analysis(analysis_id)

    assert stored is not None
    assert stored.id == analysis_id
    assert stored.cv_id == cv_id
    assert stored.job_description == "Looking for a Python developer"
    assert stored.requirements == _REQUIREMENTS
    assert stored.matches == _MATCHES
    assert stored.fit_score == 66.7
    assert stored.created_at is not None


def test_get_analysis_preserves_cv_snapshot_even_if_cv_later_changes():
    cv_id = save_cv("Original CV text")
    analysis_id = save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Original CV text",
        job_description="Looking for a Python developer",
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=66.7,
    )

    # The CV itself changes later (e.g. a new save_cv call for the same logical CV).
    save_cv("Updated CV text")

    stored = get_analysis(analysis_id)
    assert stored.cv_text_snapshot == "Original CV text"


def test_get_analysis_returns_none_for_unknown_id():
    assert get_analysis(999) is None


def test_list_analyses_returns_all_saved_analyses():
    cv_id = save_cv("Experienced Python developer")
    first_id = save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Experienced Python developer",
        job_description="First job description",
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=50.0,
    )
    second_id = save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Experienced Python developer",
        job_description="Second job description",
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=80.0,
    )

    summaries = list_analyses()

    ids = {summary.id for summary in summaries}
    assert ids == {first_id, second_id}


def test_list_analyses_orders_newest_first():
    cv_id = save_cv("Experienced Python developer")
    first_id = save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Experienced Python developer",
        job_description="First job description",
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=50.0,
    )
    second_id = save_analysis(
        cv_id=cv_id,
        cv_text_snapshot="Experienced Python developer",
        job_description="Second job description",
        requirements=_REQUIREMENTS,
        matches=_MATCHES,
        fit_score=80.0,
    )

    summaries = list_analyses()

    assert [summary.id for summary in summaries] == [second_id, first_id]


def test_connect_failure_raises_database_error(monkeypatch):
    def raise_operational_error(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr("app.database.sqlite3.connect", raise_operational_error)

    with pytest.raises(DatabaseError):
        save_cv("Some CV text")


def _failing_connection() -> MagicMock:
    connection = MagicMock()
    connection.execute.side_effect = sqlite3.OperationalError("disk I/O error")
    return connection


def test_save_cv_wraps_sqlite_errors_as_database_error(monkeypatch):
    monkeypatch.setattr("app.database._connect", _failing_connection)

    with pytest.raises(DatabaseError):
        save_cv("Some CV text")


def test_get_cv_wraps_sqlite_errors_as_database_error(monkeypatch):
    monkeypatch.setattr("app.database._connect", _failing_connection)

    with pytest.raises(DatabaseError):
        get_cv(1)


def test_database_error_message_does_not_leak_sqlite_details(monkeypatch):
    monkeypatch.setattr("app.database._connect", _failing_connection)

    with pytest.raises(DatabaseError) as exc_info:
        get_cv(1)

    message = str(exc_info.value)
    assert "disk I/O error" not in message
    assert message == "Could not load the CV."


def test_failing_connection_is_still_closed(monkeypatch):
    connection = _failing_connection()
    monkeypatch.setattr("app.database._connect", lambda: connection)

    with pytest.raises(DatabaseError):
        save_cv("Some CV text")

    connection.close.assert_called_once()
