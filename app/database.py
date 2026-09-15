import json
import os
import sqlite3
from datetime import datetime, timezone

from app.models import AnalysisSummary, Requirement, RequirementMatch, StoredAnalysis

_CREATE_CV_TABLE = """
CREATE TABLE IF NOT EXISTS cv (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cv_text TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cv_id INTEGER NOT NULL,
    cv_text_snapshot TEXT NOT NULL,
    job_description TEXT NOT NULL,
    requirements_json TEXT NOT NULL,
    matches_json TEXT NOT NULL,
    fit_score REAL NOT NULL,
    created_at TEXT NOT NULL
)
"""


class DatabaseError(Exception):
    """Raised when a SQLite operation fails. Safe to show to API clients as-is."""


def _get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", "jobfit.db")


def _connect() -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(_get_db_path())
        connection.execute(_CREATE_CV_TABLE)
        connection.execute(_CREATE_ANALYSIS_TABLE)
        return connection
    except sqlite3.Error as error:
        raise DatabaseError("Could not connect to the database.") from error


def save_cv(cv_text: str) -> int:
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO cv (cv_text, updated_at) VALUES (?, ?)",
            (cv_text, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
        return cursor.lastrowid
    except sqlite3.Error as error:
        raise DatabaseError("Could not save the CV.") from error
    finally:
        connection.close()


def get_cv(cv_id: int) -> str | None:
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT cv_text FROM cv WHERE id = ?", (cv_id,)
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error as error:
        raise DatabaseError("Could not load the CV.") from error
    finally:
        connection.close()


def update_cv(cv_id: int, cv_text: str) -> bool:
    """Update an existing CV's text in place. Returns False if cv_id does not exist.

    Does not touch the `analysis` table — existing cv_text_snapshot values are
    untouched, so past analyses keep showing the CV text as it was at the time.
    """
    connection = _connect()
    try:
        cursor = connection.execute(
            "UPDATE cv SET cv_text = ?, updated_at = ? WHERE id = ?",
            (cv_text, datetime.now(timezone.utc).isoformat(), cv_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as error:
        raise DatabaseError("Could not update the CV.") from error
    finally:
        connection.close()


def save_analysis(
    cv_id: int,
    cv_text_snapshot: str,
    job_description: str,
    requirements: list[Requirement],
    matches: list[RequirementMatch],
    fit_score: float,
) -> int:
    """Persist an already completed analysis. Does not call the LLM or recompute anything."""
    requirements_json = json.dumps([requirement.model_dump(mode="json") for requirement in requirements])
    matches_json = json.dumps([match.model_dump(mode="json") for match in matches])

    connection = _connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO analysis (
                cv_id, cv_text_snapshot, job_description,
                requirements_json, matches_json, fit_score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cv_id,
                cv_text_snapshot,
                job_description,
                requirements_json,
                matches_json,
                fit_score,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    except sqlite3.Error as error:
        raise DatabaseError("Could not save the analysis.") from error
    finally:
        connection.close()


def get_analysis(analysis_id: int) -> StoredAnalysis | None:
    connection = _connect()
    try:
        row = connection.execute(
            """
            SELECT id, cv_id, cv_text_snapshot, job_description,
                   requirements_json, matches_json, fit_score, created_at
            FROM analysis WHERE id = ?
            """,
            (analysis_id,),
        ).fetchone()
    except sqlite3.Error as error:
        raise DatabaseError("Could not load the analysis.") from error
    finally:
        connection.close()

    if row is None:
        return None

    (
        id_,
        cv_id,
        cv_text_snapshot,
        job_description,
        requirements_json,
        matches_json,
        fit_score,
        created_at,
    ) = row

    return StoredAnalysis(
        id=id_,
        cv_id=cv_id,
        cv_text_snapshot=cv_text_snapshot,
        job_description=job_description,
        requirements=[
            Requirement.model_validate(item) for item in json.loads(requirements_json)
        ],
        matches=[
            RequirementMatch.model_validate(item) for item in json.loads(matches_json)
        ],
        fit_score=fit_score,
        created_at=created_at,
    )


def list_analyses() -> list[AnalysisSummary]:
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT id, job_description, fit_score, created_at FROM analysis "
            "ORDER BY created_at DESC, id DESC"
        ).fetchall()
    except sqlite3.Error as error:
        raise DatabaseError("Could not load the analysis history.") from error
    finally:
        connection.close()

    return [
        AnalysisSummary(id=row[0], job_description=row[1], fit_score=row[2], created_at=row[3])
        for row in rows
    ]
